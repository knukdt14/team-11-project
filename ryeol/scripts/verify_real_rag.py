"""실제 Chroma/BM25/리랭커 대표 질문 점검. 저장소 루트에서 -m으로 실행."""
from taek.search import Searcher
from ryeol.app.service import _source_for_query

CASES = [
    ("신호 없는 교차로에서 자동차로 직진 중 맞은편 좌회전 자동차와 충돌했습니다", "MAIN2023"),
    ("전동킥보드로 직진하다 좌회전 자동차와 충돌했습니다", "PM2021"),
    ("회전교차로에서 회전 중 진입 차량과 충돌했습니다", "ROUND2025"),
    ("횡단보도를 건너던 보행자를 자동차가 충격했습니다", "MAIN2023"),
    ("앞차를 뒤에서 추돌했습니다", "MAIN2023"),
]

def main():
    searcher = Searcher()
    for query, expected_source in CASES:
        source = _source_for_query(query)
        assert source == expected_source
        hits = searcher.search(query, source_id=source, mode="hybrid", reject=True,
                               expand=True, rerank=True)
        assert hits, f"검색 결과 없음: {query}"
        top = hits[0].payload
        assert top.get("source_id") == expected_source
        assert top.get("base_ratio") or top.get("base_ratio_variants")
        print(expected_source, top.get("diagram_no"), top.get("title"))

if __name__ == "__main__":
    main()
