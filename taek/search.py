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

# ── 후보 없음 판정 임계값 ──────────────────────────────────────────
# 두 신호가 **모두** 약할 때만 거절합니다(AND). 하나라도 강하면 후보를 냅니다.
#
# ⭐ 왜 AND 인가 — 두 신호가 서로 다른 것을 놓치기 때문입니다.
#    "킥보드로 인도에서 내려와…"(정답 있음)는 코사인 0.578로 낮지만 BM25가 높아 살아남고,
#    "공장에서 지게차에…"(정답 없음)는 코사인 0.643으로 높지만 BM25가 낮아 걸러집니다.
#    OR 로 묶으면 정답 있는 질문이 대량으로 잘립니다.
#
# ⚠️ 융합 점수(RRF)로는 거절 판정을 못 합니다. RRF 는 순위만 반영해서
#    엉뚱한 질문에도 1위가 생기면 점수가 똑같이 높게 나옵니다.
#
# 64문항 기준 측정값: 오답 방지 13/16(81.3%), Top-3 손실 0
REJECT_VECTOR = 0.65     # 벡터 top1 코사인
REJECT_BM25 = 30.0       # BM25 top1 점수

# ── 특수기준 라우팅 ────────────────────────────────────────────────
# 인정기준(MAIN2023)은 일반기준이고, 아래 문서는 **특수기준**입니다.
# 특수기준이 있는 사고유형은 그쪽이 우선합니다.
#
# 다만 **하드 필터가 아니라 부스트**입니다. 해당 문서만 검색하는 전용 랭킹을
# 하나 더 만들어 RRF 에 함께 넣습니다. 키워드가 잘못 걸려도 일반 랭킹이 살아 있어
# 결과가 무너지지 않습니다.
#
# 64문항 기준 키워드 정밀도:
#   PM        재현 6/6, 오탐 0
#   회전교차로  재현 4/4, 오탐 2 — 그 2건도 MAIN2023 차54(회전교차로 장)라 실질 오탐 아님
#   ⚠️ '회전' 만 쓰면 좌회전·우회전에 걸려 오탐이 19건으로 늘어납니다. 반드시 '회전교차로'로.
ROUTE: dict[str, tuple[str, ...]] = {
    "PM2021": ("킥보드", "전동킥보드", "PM", "개인형 이동장치", "씽씽이"),
    "ROUND2025": ("회전교차로", "로터리"),
}


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
        self._reranker = None      # 지연 생성 — rerank=True 일 때만 (모델이 무겁습니다)

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

    @property
    def reranker(self):
        """cross-encoder 는 무거워서 rerank=True 로 처음 부를 때만 로드합니다."""
        if self._reranker is None:
            try:
                from .rerank import Reranker
            except ImportError:
                from rerank import Reranker
            self._reranker = Reranker()
        return self._reranker

    # ------------------------------------------------------------------
    # 융합 (벡터 + BM25)
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf(rankings: list[list[Hit]], k: int = 60) -> list[Hit]:
        """
        Reciprocal Rank Fusion — 순위만 쓰고 점수는 안 씁니다.

            score(d) = Σ_r  1 / (k + rank_r(d))

        ⭐ 왜 점수를 안 더하나
           코사인은 0~1, BM25는 0~수십입니다. 그냥 더하면 BM25가 다 먹습니다.
           정규화를 해도 분포 모양이 달라서 가중치가 데이터마다 흔들립니다.
           RRF 는 **순위만** 보므로 스케일 문제가 없고 튜닝할 게 k 하나뿐입니다.

        k 는 상위권 쏠림을 눌러 주는 상수입니다(관례상 60).
        작을수록 1위에 큰 가중치가 갑니다.

        ⚠️ 부모(도표) 랭킹끼리 융합합니다. 면 단위로 하면 면이 많은 도표가
           같은 이유로 여러 번 가산되어 부당하게 유리해집니다.
        """
        점수: dict[str, float] = {}
        대표: dict[str, Hit] = {}
        for ranking in rankings:
            for i, h in enumerate(ranking, 1):
                점수[h.chunk_id] = 점수.get(h.chunk_id, 0.0) + 1.0 / (k + i)
                기존 = 대표.get(h.chunk_id)
                # 두 랭킹에 다 있으면 더 잘 맞은 면을 대표로 남깁니다
                if 기존 is None or h.score > 기존.score:
                    대표[h.chunk_id] = h

        out = []
        for cid, sc in sorted(점수.items(), key=lambda x: x[1], reverse=True):
            h = 대표[cid]
            out.append(Hit(chunk_id=cid, score=round(sc, 6), kind=h.kind, text=h.text,
                           payload=h.payload, facet=h.facet, facets=h.facets))
        return out

    @staticmethod
    def _wsum(vec: list[Hit], bm: list[Hit], alpha: float = 0.5) -> list[Hit]:
        """
        min-max 정규화 후 가중합 — RRF 의 비교군입니다.

            score(d) = alpha · norm(vector) + (1-alpha) · norm(bm25)

        ⚠️ 각 랭킹 안에서만 정규화합니다. 질의마다 점수 분포가 달라서
           전역 정규화는 불가능합니다. 그래서 RRF 보다 불안정합니다.
        """
        def norm(hits: list[Hit]) -> dict[str, float]:
            if not hits:
                return {}
            vals = [h.score for h in hits]
            lo, hi = min(vals), max(vals)
            rng = (hi - lo) or 1.0
            return {h.chunk_id: (h.score - lo) / rng for h in hits}

        nv, nb = norm(vec), norm(bm)
        대표 = {h.chunk_id: h for h in bm}
        대표.update({h.chunk_id: h for h in vec})   # 벡터 쪽 면을 우선 대표로

        점수 = {
            cid: alpha * nv.get(cid, 0.0) + (1 - alpha) * nb.get(cid, 0.0)
            for cid in set(nv) | set(nb)
        }
        out = []
        for cid, sc in sorted(점수.items(), key=lambda x: x[1], reverse=True):
            h = 대표[cid]
            out.append(Hit(chunk_id=cid, score=round(sc, 6), kind=h.kind, text=h.text,
                           payload=h.payload, facet=h.facet, facets=h.facets))
        return out

    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        kind: str | None = "standard",
        source_id: str | None = None,
        mode: str = "vector",
        expand: bool = False,
        alpha: float = 0.5,
        rrf_k: float = 1.0,
        reject: bool = False,
        min_vector: float | None = None,
        min_bm25: float | None = None,
        route: bool = True,
        only_computable: bool = True,
        rerank: bool = False,
    ) -> list[Hit]:
        """
        kind='standard' 가 기본입니다. 법 조문까지 함께 보려면 kind=None.
        source_id 로 문서를 좁힐 수 있습니다(MAIN2023 / PM2021 / ROUND2025 / ROADLAW).

        mode
          vector  임베딩 코사인 (기본)
          bm25    키워드 (문자 n-gram)
          hybrid  RRF 융합 — 순위만 사용, 스케일 문제 없음 (rrf_k 로 조절)
          wsum    min-max 정규화 가중합 — RRF 비교군 (alpha 로 조절)

        rrf_k
          RRF 감쇠 상수. 원논문 관례는 60이지만 **기본값을 1로 낮췄습니다.**
          60은 검색기를 수십 개 융합할 때(개별적으로 잡음이 큼) 합의로 잡음을 거르는 값입니다.
          여기는 검색기가 2개이고 64문항 중 21문항이 **한쪽만** 맞힙니다.
          합의를 중시하면 그 21문항을 스스로 눌러버립니다. 근거는 EVAL.md §EXP-3.

        reject
          True 면 두 신호가 모두 약할 때 **빈 리스트**를 반환합니다(후보 없음).
          기준 없는 질문에 억지로 답하지 않기 위한 장치입니다. 임계값은 위 상수 참조.

        route
          질문에 특수기준 키워드(킥보드·회전교차로 등)가 있으면 해당 문서 전용 랭킹을
          하나 더 만들어 RRF 에 넣습니다. 하드 필터가 아니라 부스트입니다. hybrid 전용.

        only_computable
          기본과실이 없는 도표를 결과에서 뺍니다(243개 중 17개). 과실비율을 계산할 수
          없어 후보로 낼 의미가 없고, 평가셋에서 정답이 된 적도 0건입니다.

        rerank
          cross-encoder 로 상위 후보를 다시 정렬합니다. 정확하지만 **느립니다**.
          모델은 처음 쓸 때만 로드합니다. 지연 시간은 EVAL.md §EXP-7 참조.

        expand
          True 면 질의에 문서 어휘를 덧붙입니다(킥보드 → PM 등). synonyms.py 참조.
          인덱스는 건드리지 않으므로 두 mode 모두에 적용됩니다.

        ⚠️ vector 와 bm25 는 **점수 스케일이 다릅니다**(코사인 0~1 vs BM25 0~수십).
           단독 비교·순위 용도로만 쓰고, 두 점수를 직접 더하지 마세요.
        """
        원질의 = query
        if expand:
            try:
                from .synonyms import expand_query
            except ImportError:
                from synonyms import expand_query
            query, _ = expand_query(query)

        n = min(top_k * 8, 200)          # 면 단위로 넓게 뽑은 뒤 부모로 합칩니다
        깊이 = 200                        # 융합은 깊게 — 얕으면 한쪽에만 있는 후보가 안 보입니다

        vec = bm = None
        if mode in ("vector", "hybrid", "wsum") or reject:
            vec = self._merge_to_parent(
                self._vector_rows(query, 깊이 if mode != "vector" else n, kind, source_id))
        if mode in ("bm25", "hybrid", "wsum") or reject:
            bm = self._merge_to_parent(
                self._bm25_rows(query, 깊이 if mode != "bm25" else n, kind, source_id))

        # 후보 없음 판정 — 두 신호가 모두 약하면 아무것도 내지 않습니다.
        #
        # ⚠️ 게이트는 **원본 질의**로 잽니다. 확장 질의로 재면 안 됩니다.
        #    확장은 문서 어휘를 덧붙이므로 범위 밖 질문("보험료가 얼마나 오르나요")의
        #    BM25 점수까지 같이 올라가 게이트가 덜 걸립니다.
        #    "이 질문이 우리 범위인가"는 **사용자가 실제로 쓴 말**로 판단해야 합니다.
        #    실측: 확장 질의로 재면 오답 방지가 81.2% → 75.0% 로 떨어집니다.
        if reject:
            if expand:
                g_vec = self._merge_to_parent(self._vector_rows(원질의, 20, kind, source_id))
                g_bm = self._merge_to_parent(self._bm25_rows(원질의, 20, kind, source_id))
            else:
                g_vec, g_bm = vec, bm
            v0 = g_vec[0].score if g_vec else 0.0
            b0 = g_bm[0].score if g_bm else 0.0
            if v0 < (min_vector if min_vector is not None else REJECT_VECTOR) and \
               b0 < (min_bm25 if min_bm25 is not None else REJECT_BM25):
                return []

        if mode == "vector":
            결과 = vec
        elif mode == "bm25":
            결과 = bm
        elif mode in ("hybrid", "wsum"):
            랭킹 = [vec, bm]
            # 특수기준 라우팅 — 전용 랭킹을 하나 더 얹어 부스트합니다(하드 필터 아님).
            if route and mode == "hybrid":
                for src, kws in ROUTE.items():
                    if src == source_id or not any(w in 원질의 for w in kws):
                        continue
                    전용 = self._merge_to_parent(self._vector_rows(query, 깊이, kind, src))
                    if 전용:
                        랭킹.append(전용)
            결과 = self._rrf(랭킹, k=rrf_k) if mode == "hybrid" else self._wsum(vec, bm, alpha)
        else:
            raise ValueError(f"알 수 없는 mode: {mode} (vector | bm25 | hybrid | wsum)")

        # 기본과실이 없는 도표는 과실비율을 계산할 수 없어 후보로 낼 의미가 없습니다.
        # 243개 중 17개가 여기 해당하고, 평가셋 64문항에서 정답이 된 적은 0건입니다.
        if only_computable:
            결과 = [h for h in 결과 if h.kind != "standard"
                    or h.payload.get("base_ratio") or h.payload.get("base_ratio_variants")]

        # 리랭킹은 필터링이 끝난 뒤에 합니다 — 걸러질 후보에 모델을 돌리는 건 낭비입니다.
        if rerank and 결과:
            return self.reranker.rerank(원질의, 결과, top_k=top_k)
        return 결과[:top_k]

    @staticmethod
    def _law_id(no: str) -> str:
        """
        "도로교통법 제26조" → "ROAD-제26조"

        ⚠️ PDF에서 non-breaking space(\xa0)가 섞여 나오는 경우가 있어
           단순 문자열 치환으로는 매칭이 실패합니다. 공백을 모두 정규화합니다.
        """
        s = no.replace("\u00a0", " ").replace("도로교통법", "")
        cleaned = re.sub(r'[\s]+', '', s)
        return f"ROAD-{cleaned}"

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