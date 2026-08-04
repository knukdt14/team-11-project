"""
임베딩 백엔드.

SentenceTransformer 하나만 씁니다. 모델은 EMBEDDING_MODEL 로 지정합니다.

    EMBEDDING_MODEL=BAAI/bge-m3              (기본값 · 한국어 성능 좋음 · 1024차원)
    EMBEDDING_MODEL=jhgan/ko-sroberta-multitask   (가볍고 빠름 · 768차원)

    EMBEDDING_DEVICE=cpu    GPU가 있어도 CPU 강제
    EMBEDDING_BATCH=8       VRAM 부족할 때 낮추기

⚠️ **인덱스와 질의는 반드시 같은 모델**이어야 합니다.
   모델이 다르면 차원이 다르거나(→ Chroma 오류), 차원이 같아도 벡터 공간이 달라
   결과가 조용히 엉망이 됩니다. search.py 가 인덱스 메타와 대조해 불일치면 중단시킵니다.

⚠️ 모델을 바꾸면 인덱스를 **폴더째 지우고** 다시 만드세요.
       rmdir /s /q data\\processed\\vector_index
       python build_vector.py
"""

from __future__ import annotations

import os


class Embedder:
    """SentenceTransformer 래퍼. GPU가 있으면 자동으로 사용합니다."""

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

        # GPU에서는 fp16으로 2배 가까이 빨라집니다. CPU는 오히려 느려 건너뜁니다.
        if device == "cuda":
            try:
                self.model = self.model.half()
            except Exception:  # noqa: BLE001
                pass

        try:
            self.dim = self.model.get_embedding_dimension()
        except AttributeError:  # sentence-transformers 구버전 호환
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

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


def build_embedder(model_id: str | None = None) -> Embedder:
    return Embedder(model_id)