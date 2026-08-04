"""
임베딩 백엔드.

두 가지를 같은 인터페이스로 제공합니다.

  st    SentenceTransformer (BGE-m3 등) — 실제 운영용. 모델 다운로드 필요.
  hash  문자 3-gram 해싱 — **모델 없이 동작하는 개발·검증용.**

⚠️ `hash` 는 의미 검색이 아니라 표기 유사도입니다. 파이프라인(청킹→인덱싱→검색)이
   제대로 연결됐는지 확인하는 용도이며, 최종 검색 품질 측정에 쓰면 안 됩니다.
   모델을 받을 수 있는 환경에서 `st` 로 바꿔 인덱스를 다시 만드세요.

  EMBEDDING_BACKEND=st  EMBEDDING_MODEL=BAAI/bge-m3  python build_vector

⚠️ 어떤 백엔드를 쓰든 **질의도 같은 백엔드로 임베딩**해야 합니다.
   인덱스와 질의의 백엔드가 다르면 검색 결과가 무의미해집니다.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

DEFAULT_DIM = 512


class Embedder(ABC):
    name: str
    dim: int

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        """L2 정규화된 벡터를 반환합니다 (코사인 유사도 전제)."""

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


# ---------------------------------------------------------------------------


class HashEmbedder(Embedder):
    """
    문자 3-gram 해싱 임베더. 외부 모델·네트워크 불필요.

    - 한글은 형태 변화가 많아 단어 단위보다 문자 n-gram이 안정적입니다.
    - 문서 길이 편향을 줄이려고 L2 정규화합니다.
    """

    name = "hash"

    def __init__(self, dim: int = DEFAULT_DIM, n: int = 3):
        self.dim = dim
        self.n = n

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _grams(self, text: str) -> list[str]:
        t = self._normalize(text)
        grams = [w for w in t.split() if w]  # 토큰 자체도 신호로 사용
        compact = t.replace(" ", "")
        grams += [compact[i : i + self.n] for i in range(max(0, len(compact) - self.n + 1))]
        return grams

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for g in self._grams(text):
                h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "big") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


# ---------------------------------------------------------------------------


class STEmbedder(Embedder):
    """
    SentenceTransformer 기반. 운영용.

    GPU가 있으면 자동으로 사용합니다.
      EMBEDDING_DEVICE=cpu   로 강제 지정 가능
      EMBEDDING_BATCH=32     배치 크기 (VRAM 부족하면 낮추세요)
    """

    name = "st"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self.model_id = model_id or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

        device = os.getenv("EMBEDDING_DEVICE")
        if not device:
            try:
                import torch  # noqa: PLC0415

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self.device = device

        self.model = SentenceTransformer(self.model_id, device=device)

        # GPU에서는 fp16으로 2배 가까이 빨라집니다. CPU는 fp16이 오히려 느려 건너뜁니다.
        if device == "cuda":
            try:
                self.model = self.model.half()
            except Exception:  # noqa: BLE001
                pass

        try:
            self.dim = self.model.get_embedding_dimension()
        except AttributeError:  # 구버전 호환
            self.dim = self.model.get_sentence_embedding_dimension()

        self.batch = int(os.getenv("EMBEDDING_BATCH", "32" if device == "cuda" else "8"))
        self.name = f"st:{self.model_id}"
        print(f"  device={device} batch={self.batch}")

    def encode(self, texts: list[str]) -> list[list[float]]:
        # normalize_embeddings=True 필수 — 안 하면 코사인 유사도가 틀어집니다.
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=self.batch,
            show_progress_bar=len(texts) > 64,
        ).tolist()


# ---------------------------------------------------------------------------


def build_embedder(backend: str | None = None) -> Embedder:
    key = (backend or os.getenv("EMBEDDING_BACKEND", "hash")).lower()
    if key == "st":
        return STEmbedder()
    if key != "hash":
        raise SystemExit(f"알 수 없는 EMBEDDING_BACKEND: {key} (st | hash)")
    return HashEmbedder()