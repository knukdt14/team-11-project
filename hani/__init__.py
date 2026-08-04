"""
과실비율 지식베이스 · 검색 모듈.

외부(백엔드)에서는 이렇게 씁니다.

    from hani.search import Searcher
    from hani.party import to_consultant_view, describe

    s = Searcher()
    hits = s.search("신호 없는 교차로에서 좌회전 차와 충돌")
    view = to_consultant_view(hits[0].payload, consultant_side="A")

⚠️ 여기서 `Searcher` 를 미리 import 하지 않습니다.
   chromadb·sentence-transformers 로딩이 무거워서, 패키지를 건드리기만 해도
   모델이 올라가면 FastAPI 기동이 느려집니다. 필요한 곳에서 직접 import 하세요.
   (백엔드는 `lifespan` 에서 Searcher 를 **1회만** 만들어 재사용하세요.)

CLI 스크립트는 그대로 동작합니다.

    python parse_pdf.py extract "pdf/….pdf" --source-id MAIN2023
    python extract_images.py "pdf/….pdf" --source-id MAIN2023
    python build_chunks.py
    python build_vector.py
    python search.py "뒤에서 추돌당했습니다"
    python evaluate.py
"""

__all__ = ["party", "schema", "search"]
