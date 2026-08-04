"""
기본 벡터 검색.

담당 범위는 **"질문을 넣으면 후보 도표가 나온다"** 까지

사용
    from search import Searcher
    s = Searcher()
    for hit in s.search("야간에 신호 없는 교차로에서 직진하다 좌회전 차와 부딪혔어요"):
        print(hit.chunk_id, hit.score)

CLI
    python search "신호 없는 교차로 직진 좌회전"
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VECTOR_DIR = ROOT / "data" / "processed" / "vector_index"
PAYLOAD = ROOT / "data" / "processed" / "payloads.json"
COLLECTION = "fault_ratio"


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

    인덱스를 만든 백엔드와 **같은 백엔드로 질의를 임베딩**
       다르면 경고를 띄웁니다 — 섞이면 결과가 무의미해집니다.
    """

    def __init__(self) -> None:
        import chromadb

        from embedder import build_embedder

        if not VECTOR_DIR.exists():
            raise SystemExit("벡터 인덱스가 없습니다. `python build_vector` 먼저 실행")

        client = chromadb.PersistentClient(path=str(VECTOR_DIR))
        self.col = client.get_collection(COLLECTION)
        self.embedder = build_embedder()

        인덱스_백엔드 = (self.col.metadata or {}).get("embedder")
        if 인덱스_백엔드 and 인덱스_백엔드 != self.embedder.name:
            print(
                f"⚠️ 인덱스는 '{인덱스_백엔드}' 로 만들었는데 질의는 '{self.embedder.name}' 입니다.\n"
                f"   EMBEDDING_BACKEND 를 맞추거나 인덱스를 다시 만드세요.",
                file=sys.stderr,
            )

        self.payloads: dict[str, dict] = (
            json.loads(PAYLOAD.read_text(encoding="utf-8")) if PAYLOAD.exists() else {}
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        kind: str | None = "standard",
        source_id: str | None = None,
    ) -> list[Hit]:
        """
        kind='standard' 가 기본입니다. 법 조문까지 함께 보려면 kind=None.
        source_id 로 문서를 좁힐 수 있습니다(MAIN2023 / PM2021 / ROUND2025 / ROADLAW).
        """
        conds = []
        if kind:
            conds.append({"kind": kind})
        if source_id:
            conds.append({"source_id": source_id})
        where = None if not conds else (conds[0] if len(conds) == 1 else {"$and": conds})

        # 면 단위로 넓게 뽑은 뒤 부모로 합칩니다.
        res = self.col.query(
            query_embeddings=[self.embedder.encode_one(query)],
            n_results=min(top_k * 8, 100),
            where=where,
        )
        if not res["ids"] or not res["ids"][0]:
            return []

        best: dict[str, Hit] = {}
        for cid, dist, doc, meta in zip(
            res["ids"][0], res["distances"][0], res["documents"][0], res["metadatas"][0],
            strict=False,
        ):
            pid = meta.get("parent_id") or cid
            score = round(max(0.0, 1.0 - float(dist)), 4)
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
                if score > hit.score:      # 부모 점수 = 가장 잘 맞은 면의 점수
                    hit.score, hit.text, hit.facet = score, doc, facet

        hits = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def laws_for(self, article_nos: list[str]) -> list[Hit]:
        """도표의 laws 필드로 조문 본문을 가져옵니다 (검색이 아니라 직접 조회)."""
        ids = [f"ROAD-{no.replace('도로교통법 ', '').strip()}" for no in article_nos]
        ids = [i for i in ids if i in self.payloads]
        if not ids:
            return []
        res = self.col.get(ids=ids)
        return [
            Hit(chunk_id=i, score=1.0, kind="law", text=d, payload=self.payloads.get(i, {}))
            for i, d in zip(res["ids"], res["documents"], strict=False)
        ]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('사용법: python search "질문"')
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