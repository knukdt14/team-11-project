"""
Cross-encoder 리랭킹.

⭐ 검색(bi-encoder)과 무엇이 다른가
   벡터 검색은 질문과 문서를 **따로** 임베딩해 코사인을 잽니다. 미리 계산해 둘 수 있어 빠르지만,
   질문과 문서가 서로를 보지 못합니다.
   cross-encoder 는 **(질문, 문서)를 함께** 모델에 넣어 점수를 냅니다. 훨씬 정확하지만
   후보마다 모델을 돌려야 해서 느립니다.

   → 그래서 **검색으로 후보를 좁히고, 그 위에서만 리랭킹**합니다.

⭐ 상한은 후보 풀의 재현율입니다
   리랭킹은 이미 뽑힌 후보의 순서만 바꿉니다. 후보에 정답이 없으면 아무 일도 못 합니다.

     후보 10개 재현율 87.5%  ← 여기까지가 상한
     후보 20개 재현율 92.2%
     후보 30개 재현율 95.3%

   후보를 늘리면 상한은 오르지만 **지연 시간이 선형으로 늘어납니다.**

⚠️ **CPU 에서는 느립니다.** 요청당 후보 20개면 수 초가 걸릴 수 있습니다.
   시연에서 쓸지 여부는 아래 latency 측정을 보고 판단하세요(EVAL.md §EXP-7).

모델
    RERANK_MODEL 환경변수로 교체 가능. 기본값은 임베딩과 같은 계열(bge)입니다.
    한국어 특화가 필요하면 Dongjin-kr/ko-reranker 등을 시도해 보세요.

사용
    from taek.rerank import Reranker
    rr = Reranker()
    hits = rr.rerank("질문", hits, top_k=3)
"""

from __future__ import annotations

import os

DEFAULT_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# 리랭킹에 넣을 후보 수. 늘리면 상한이 오르고 느려집니다.
CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))


class Reranker:
    """CrossEncoder 래퍼. 모델은 처음 쓸 때 로드합니다."""

    def __init__(self, model_id: str | None = None) -> None:
        from sentence_transformers import CrossEncoder  # noqa: PLC0415

        self.model_id = model_id or DEFAULT_MODEL

        device = os.getenv("RERANK_DEVICE")
        if not device:
            try:
                import torch  # noqa: PLC0415

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self.device = device
        self.model = CrossEncoder(self.model_id, device=device, max_length=512)
        self.batch = int(os.getenv("RERANK_BATCH", "16"))

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        pairs = [(query, t) for t in texts]
        out = self.model.predict(pairs, batch_size=self.batch, show_progress_bar=False)
        return [float(x) for x in out]

    def rerank(self, query: str, hits: list, top_k: int = 5, candidates: int | None = None):
        """
        상위 `candidates` 개만 다시 점수 매겨 정렬합니다.

        ⚠️ 리랭킹 대상 밖(candidates 뒤쪽)은 **원래 순서를 유지한 채 뒤에 붙입니다.**
           잘라 버리면 Top-10 같은 깊은 지표가 근거 없이 떨어집니다.

        ⚠️ 어느 텍스트로 점수를 매기나 — `hit.text` 는 '가장 잘 맞은 면' 하나뿐이라
           맥락이 부족합니다. 도표 제목과 사고상황을 함께 넣어 줍니다.
        """
        n = candidates if candidates is not None else CANDIDATES
        머리, 꼬리 = hits[:n], hits[n:]
        if not 머리:
            return hits[:top_k]

        texts = []
        for h in 머리:
            p = h.payload or {}
            조각 = [p.get("title", ""), p.get("accident_description", ""), h.text or ""]
            texts.append(" ".join(x for x in 조각 if x)[:1000])

        점수 = self.score(query, texts)
        재정렬 = [h for _, h in sorted(zip(점수, 머리), key=lambda x: x[0], reverse=True)]
        for s, h in zip(점수, 머리):
            h.score = round(float(s), 6)
        return (재정렬 + 꼬리)[:top_k]


def main() -> None:
    import sys
    import time

    try:
        from .search import Searcher
    except ImportError:
        from search import Searcher

    if len(sys.argv) < 2:
        raise SystemExit('사용법: python -m taek.rerank "질문"')
    q = " ".join(sys.argv[1:])
    s = Searcher()
    t0 = time.perf_counter()
    hits = s.search(q, top_k=CANDIDATES, mode="hybrid", reject=True, expand=True)
    t1 = time.perf_counter()
    if not hits:
        print("후보 없음 (범위 밖 질문)")
        return
    rr = Reranker()
    t2 = time.perf_counter()
    out = rr.rerank(q, hits, top_k=5)
    t3 = time.perf_counter()

    print(f"질문: {q}\n")
    for i, h in enumerate(out, 1):
        print(f"{i}. [{h.score:8.3f}] {h.label}")
    print(f"\n검색 {t1-t0:.2f}s · 모델로드 {t2-t1:.1f}s · 리랭킹 {t3-t2:.2f}s "
          f"({len(hits)}개 후보, {rr.device})")


if __name__ == "__main__":
    main()
