"""
키워드 검색 (BM25).

⭐ 왜 형태소 분석기를 안 쓰나
   한국어를 공백으로만 자르면 조사 때문에 매칭이 깨집니다.
       질문 "교차로에서"  vs  문서 "교차로를"   → 다른 토큰
   보통 형태소 분석기(konlpy·mecab)를 쓰지만 Windows 설치 비용이 크고
   requirements.txt 가 무거워집니다(JVM 또는 C 빌드).

   대신 **문자 n-gram**을 씁니다.
       "교차로에서" → 교차, 차로, 로에, 에서, 교차로, 차로에, 로에서
       "교차로를"   → 교차, 차로, 로를, 교차로, 차로를
   → `교차`, `차로`, `교차로` 가 겹쳐서 조사에 흔들리지 않습니다.
   설치가 필요 없고, 오타·띄어쓰기 흔들림에도 강합니다.

⚠️ n-gram 은 **없는 단어를 만들어내지는 못합니다.**
   "킥보드"는 코퍼스에 0회 등장하므로 BM25로도 못 찾습니다(동의어 사전이 필요 — EVAL.md §4).

⚠️ 벡터 검색과 **같은 면(facet) 단위**로 인덱싱합니다.
   벡터는 자식(면)으로 검색해 `parent_id` 로 합치는데, BM25만 부모 단위로 만들면
   두 랭킹의 단위가 어긋나서 결합(RRF·가중합)이 조용히 이상해집니다.

사용
    from taek.bm25 import BM25Index
    idx = BM25Index()
    for chunk_id, score in idx.search("회전교차로 차로변경", top_k=10):
        ...
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:                                    # 패키지로 import 될 때
    from .paths import CHUNKS
except ImportError:                     # 스크립트로 직접 실행할 때
    from paths import CHUNKS

NGRAM_SIZES = (2, 3)
RE_KEEP = re.compile(r"[^0-9a-z가-힣]+")


def tokenize(text: str, sizes: tuple[int, ...] = NGRAM_SIZES) -> list[str]:
    """
    어절 + 문자 n-gram.

    어절을 함께 넣는 이유: `PM`, `보1` 처럼 짧고 변형이 없는 표기는
    n-gram 으로 쪼개면 오히려 흔해져서 변별력이 떨어집니다.
    """
    t = RE_KEEP.sub(" ", text.lower()).strip()
    if not t:
        return []
    words = t.split()
    compact = t.replace(" ", "")
    grams = [
        compact[i : i + n]
        for n in sizes
        for i in range(len(compact) - n + 1)
    ]
    return words + grams


class BM25Index:
    """chunks.jsonl 전체를 메모리에 올린 BM25. 1,900건 규모라 저장 없이 매번 만듭니다."""

    def __init__(self, chunks_path: Path = CHUNKS) -> None:
        from rank_bm25 import BM25Okapi  # noqa: PLC0415

        if not chunks_path.exists():
            raise SystemExit(
                f"{chunks_path} 가 없습니다. 먼저 만드세요:\n"
                "  cd hani && python build_chunks.py"
            )

        rows = [json.loads(l) for l in chunks_path.open(encoding="utf-8") if l.strip()]
        self.ids: list[str] = [r["chunk_id"] for r in rows]
        self.docs: list[str] = [r["text"] for r in rows]
        self.metas: list[dict] = [r["meta"] for r in rows]
        self.bm25 = BM25Okapi([tokenize(t) for t in self.docs])

    def __len__(self) -> int:
        return len(self.ids)

    def search(
        self,
        query: str,
        top_k: int = 40,
        kind: str | None = "standard",
        source_id: str | None = None,
    ) -> list[tuple[str, float, str, dict]]:
        """(chunk_id, score, text, meta) 를 점수순으로. 필터는 벡터 쪽과 같은 의미입니다."""
        q = tokenize(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)

        cand = []
        for i, sc in enumerate(scores):
            if sc <= 0:
                continue
            m = self.metas[i]
            if kind and m.get("kind") != kind:
                continue
            if source_id and m.get("source_id") != source_id:
                continue
            cand.append((self.ids[i], float(sc), self.docs[i], m))

        cand.sort(key=lambda x: x[1], reverse=True)
        return cand[:top_k]


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        raise SystemExit('사용법: python -m taek.bm25 "질문"')
    q = " ".join(sys.argv[1:])
    idx = BM25Index()
    print(f"질문: {q}  (색인 {len(idx)}개 면)\n")
    for i, (cid, sc, _doc, meta) in enumerate(idx.search(q, top_k=10), 1):
        print(f"{i:>2}. {sc:7.3f}  {meta.get('parent_id', cid):<22} [{meta.get('facet','')}]")


if __name__ == "__main__":
    main()
