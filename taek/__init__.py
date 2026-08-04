"""
검색 · 평가 모듈 (2번 · 오현택).

역할 경계
    hani/   PDF → JSONL → 청크 → 벡터 인덱스   (1번 · 데이터 파이프라인)
    taek/   질문 → 후보 도표 → 성능 측정        (2번 · 검색 성능·근거 검색)

데이터는 `hani/data/processed/` 를 **읽기 전용**으로 씁니다. 경로는 `taek/paths.py` 참조.

사용
    from taek.search import Searcher
    from hani.party import to_consultant_view, describe

    s = Searcher()                              # ⚠️ FastAPI lifespan 에서 1회만
    hits = s.search("신호 없는 교차로에서 좌회전 차와 충돌")
    view = to_consultant_view(hits[0].payload, consultant_side="A")

⚠️ 여기서 `Searcher` 를 미리 import 하지 않습니다.
   chromadb·임베딩 모델 로딩이 무거워서 패키지를 건드리기만 해도 기동이 느려집니다.

CLI (저장소 루트에서)
    python -m taek.search "뒤에서 추돌당했습니다"
    python -m taek.bm25   "회전교차로 차로변경"
    python -m taek.evaluate --mode bm25
"""

__all__ = ["paths", "bm25", "search"]
