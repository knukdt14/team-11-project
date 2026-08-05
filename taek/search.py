"""
기본 벡터 검색.

담당 범위는 **"질문을 넣으면 후보 도표가 나온다"** 까지입니다.
리랭킹·문서 우선순위·LLM 답변 생성은 다른 담당의 영역입니다.

사용
    from taek.search import Searcher
    s = Searcher()
    for hit in s.search("야간에 신호 없는 교차로에서 직진하다 좌회전 차와 부딪혔어요"):
        print(hit.chunk_id, hit.score)

CLI (저장소 루트에서)
    python -m taek.search "신호 없는 교차로 직진 좌회전"
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

try:                                    # 패키지로 import 될 때
    from .paths import CHUNKS, COLLECTION, PAYLOAD, VECTOR_DIR
except ImportError:                     # 스크립트로 직접 실행할 때
    from paths import CHUNKS, COLLECTION, PAYLOAD, VECTOR_DIR


@dataclass
class Hit:
    chunk_id: str          # 부모 id (도표/사례/조문 단위)
    score: float
    kind: str
    text: str              # 점수가 가장 높았던 면의 원문
    payload: dict
    facet: str = ""        # 어느 면이 걸렸는지 (요약/상황/해설/수정요소/항N)
    facets: dict = field(default_factory=dict)   # 면별 점수

    @property
    def label(self) -> str:
        if self.kind == "standard":
            r = self.payload.get("base_ratio")
            비율 = f"A{r['a']}:B{r['b']}" if r else "기본과실 미상"
            return f"{self.payload.get('diagram_no')} {self.payload.get('title','')} ({비율})"
        return f"{self.payload.get('article_no')} {self.payload.get('title','')}"


class Searcher:
    """
    Chroma 인덱스를 감싼 검색기.

    ⚠️ 인덱스를 만든 백엔드와 **같은 백엔드로 질의를 임베딩**합니다.
       다르면 경고를 띄웁니다 — 섞이면 결과가 무의미해집니다.
    """

    def __init__(self) -> None:
        import chromadb

        # 임베딩 백엔드는 1번(데이터 파이프라인) 것을 그대로 씁니다.
        # ⚠️ 인덱스를 만든 코드와 질의 코드가 **같은 임베더**여야 합니다. 복사하지 마세요.
        from hani.embedder import build_embedder

        if not VECTOR_DIR.exists():
            raise SystemExit(
                "벡터 인덱스가 없습니다. 먼저 만드세요:\n"
                "  cd hani && python build_vector.py"
            )

        client = chromadb.PersistentClient(path=str(VECTOR_DIR))
        self.col = client.get_collection(COLLECTION)
        self.embedder = build_embedder()

        인덱스_백엔드 = (self.col.metadata or {}).get("embedder")
        if 인덱스_백엔드 and 인덱스_백엔드 != self.embedder.name:
            # 차원이 다르면 Chroma가 터지고, 같아도 벡터 공간이 달라 결과가 무의미합니다.
            # 경고로 넘기면 조용히 틀린 결과가 나오므로 여기서 중단합니다.
            raise SystemExit(
                f"임베딩 모델 불일치\n"
                f"  인덱스: {인덱스_백엔드}\n  질의  : {self.embedder.name}\n"
                f"  EMBEDDING_MODEL 을 맞추거나, vector_index 폴더를 지우고\n"
                f"  cd hani && python build_vector.py 로 인덱스를 다시 만드세요."
            )

        # 청킹·파싱을 고쳤는데 인덱스를 다시 안 만들면 문서와 벡터가 어긋납니다.
        # 오류가 안 나고 검색 품질만 조용히 떨어지므로 여기서 알려 줍니다.
        from hani.index_meta import chunks_fingerprint

        저장된_지문 = (self.col.metadata or {}).get("chunks_fp")
        현재_지문 = chunks_fingerprint(CHUNKS)
        if not 저장된_지문:
            # 지문 기록 이전에 만든 인덱스 — 최신인지 확인할 방법이 없습니다.
            print(
                "⚠️ 이 인덱스에는 chunks 지문이 없습니다(지문 기록 전에 만든 인덱스).\n"
                "   현재 chunks.jsonl 과 일치하는지 확인할 수 없으니 한 번 다시 만드세요:\n"
                "     cd hani && python build_vector.py",
                file=sys.stderr,
            )
        elif 현재_지문 and 저장된_지문 != 현재_지문:
            print(
                "⚠️ chunks.jsonl 이 인덱스를 만든 뒤에 바뀌었습니다.\n"
                "   검색 결과가 현재 데이터와 어긋납니다. 인덱스를 다시 만드세요:\n"
                "     cd hani && python build_vector.py",
                file=sys.stderr,
            )

        self.payloads: dict[str, dict] = (
            json.loads(PAYLOAD.read_text(encoding="utf-8")) if PAYLOAD.exists() else {}
        )
        self._bm25 = None          # 지연 생성 — bm25/hybrid 모드에서만 만듭니다

    # ------------------------------------------------------------------
    # 면(facet) → 부모(도표) 병합
    # ------------------------------------------------------------------

    def _merge_to_parent(self, rows: list[tuple[str, float, str, dict]]) -> list[Hit]:
        """
        (chunk_id, score, text, meta) 목록을 부모 단위로 합칩니다.

        부모 점수 = **가장 잘 맞은 면의 점수**. 평균이 아닙니다 —
        도표 하나에 성격이 다른 면이 섞여 있어서 평균을 내면 신호가 묻힙니다.
        """
        best: dict[str, Hit] = {}
        for cid, score, doc, meta in rows:
            pid = meta.get("parent_id") or cid
            facet = meta.get("facet", "")
            hit = best.get(pid)
            if hit is None:
                best[pid] = Hit(
                    chunk_id=pid, score=score, kind=meta.get("kind", ""),
                    text=doc, payload=self.payloads.get(pid, {}),
                    facet=facet, facets={facet: score},
                )
            else:
                hit.facets[facet] = max(score, hit.facets.get(facet, 0.0))
                if score > hit.score:
                    hit.score, hit.text, hit.facet = score, doc, facet
        return sorted(best.values(), key=lambda h: h.score, reverse=True)

    # ------------------------------------------------------------------
    # 개별 검색기 (면 단위 · 부모 병합 전)
    # ------------------------------------------------------------------

    def _vector_rows(
        self, query: str, n: int, kind: str | None, source_id: str | None,
    ) -> list[tuple[str, float, str, dict]]:
        conds = []
        if kind:
            conds.append({"kind": kind})
        if source_id:
            conds.append({"source_id": source_id})
        where = None if not conds else (conds[0] if len(conds) == 1 else {"$and": conds})

        res = self.col.query(
            query_embeddings=[self.embedder.encode_one(query)],
            n_results=min(n, 200),
            where=where,
        )
        if not res["ids"] or not res["ids"][0]:
            return []
        return [
            (cid, round(max(0.0, 1.0 - float(dist)), 4), doc, meta)
            for cid, dist, doc, meta in zip(
                res["ids"][0], res["distances"][0], res["documents"][0], res["metadatas"][0],
                strict=False,
            )
        ]

    @property
    def bm25(self):
        """BM25 색인은 처음 쓸 때만 만듭니다(벡터만 쓸 때 비용 0)."""
        if self._bm25 is None:
            try:
                from .bm25 import BM25Index
            except ImportError:
                from bm25 import BM25Index
            self._bm25 = BM25Index()
        return self._bm25

    def _bm25_rows(
        self, query: str, n: int, kind: str | None, source_id: str | None,
    ) -> list[tuple[str, float, str, dict]]:
        return self.bm25.search(query, top_k=n, kind=kind, source_id=source_id)

    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        kind: str | None = "standard",
        source_id: str | None = None,
        mode: str = "vector",
        expand: bool = False,
    ) -> list[Hit]:
        """
        kind='standard' 가 기본입니다. 법 조문까지 함께 보려면 kind=None.
        source_id 로 문서를 좁힐 수 있습니다(MAIN2023 / PM2021 / ROUND2025 / ROADLAW).

        mode
          vector  임베딩 코사인 (기본)
          bm25    키워드 (문자 n-gram)

        expand
          True 면 질의에 문서 어휘를 덧붙입니다(킥보드 → PM 등). synonyms.py 참조.
          인덱스는 건드리지 않으므로 두 mode 모두에 적용됩니다.

        ⚠️ vector 와 bm25 는 **점수 스케일이 다릅니다**(코사인 0~1 vs BM25 0~수십).
           단독 비교·순위 용도로만 쓰고, 두 점수를 직접 더하지 마세요.
        """
        if expand:
            try:
                from .synonyms import expand_query
            except ImportError:
                from synonyms import expand_query
            query, _ = expand_query(query)

        n = min(top_k * 8, 200)          # 면 단위로 넓게 뽑은 뒤 부모로 합칩니다
        if mode == "vector":
            rows = self._vector_rows(query, n, kind, source_id)
        elif mode == "bm25":
            rows = self._bm25_rows(query, n, kind, source_id)
        else:
            raise ValueError(f"알 수 없는 mode: {mode} (vector | bm25)")
        return self._merge_to_parent(rows)[:top_k]

    @staticmethod
    def _law_id(no: str) -> str:
        """
        "도로교통법 제26조" → "ROAD-제26조"

        ⚠️ PDF에서 non-breaking space(\xa0)가 섞여 나오는 경우가 있어
           단순 문자열 치환으로는 매칭이 실패합니다. 공백을 모두 정규화합니다.
        """
        s = no.replace("\u00a0", " ").replace("도로교통법", "")
        return f"ROAD-{re.sub(r'[\s]+', '', s)}"

    def cases(self, query: str, top_k: int = 3) -> list[Hit]:
        """
        심의사례 검색.

        ⚠️ **참고용입니다. 계산에 쓰지 마세요.**
           기본비율과 결정비율이 다른 사례가 226건 중 90건입니다.
           또 A가 청구인인지 피청구인인지가 사례마다 뒤바뀌므로
           payload 의 `a_party` / `b_party` 를 반드시 함께 표시하세요.
           현행 도표와의 매핑은 아직 전부 `mapping_status="review_required"` 입니다.
        """
        return self.search(query, top_k=top_k, kind="case")

    def laws_for(self, article_nos: list[str]) -> list[Hit]:
        """도표의 laws 필드로 조문 본문을 가져옵니다 (검색이 아니라 직접 조회)."""
        ids = [i for i in map(self._law_id, article_nos) if i in self.payloads]
        if not ids:
            return []
        res = self.col.get(where={"parent_id": {"$in": ids}})
        best: dict[str, Hit] = {}
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"], strict=False):
            pid = meta.get("parent_id", cid)
            if pid not in best:
                best[pid] = Hit(chunk_id=pid, score=1.0, kind="law", text=doc,
                                payload=self.payloads.get(pid, {}), facet=meta.get("facet", ""))
        return list(best.values())


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('사용법: python -m taek.search "질문"')
    q = " ".join(sys.argv[1:])
    s = Searcher()
    print(f"질문: {q}\n")
    for i, h in enumerate(s.search(q), 1):
        print(f"{i}. [{h.score:.3f}] {h.label}")
        면 = " ".join(f"{k}:{v:.2f}" for k, v in sorted(h.facets.items(), key=lambda x: -x[1]))
        print(f"   {h.chunk_id} · p.{h.payload.get('source_page')} · 매칭[{h.facet}]")
        print(f"   면별 {면}")


if __name__ == "__main__":
    main()