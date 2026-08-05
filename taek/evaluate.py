"""
검색 성능 평가.

    python -m taek.evaluate                       # 벡터 (기본)
    python -m taek.evaluate --mode bm25
    python -m taek.evaluate --top-k 5 --out taek/results/eval_x.csv

측정 지표
  Top-1 / Top-3 / Top-10 정확도   정답 도표가 몇 위 안에 들어왔나
  MRR                            정답 순위의 역수 평균 (1위=1.0, 3위=0.33)
  오답 방지율                     기준이 없는 질문에 후보를 안 내놓는 비율

⭐ gold_id 는 `;` 로 **복수 정답**을 적을 수 있습니다.

     MAIN2023-보1;MAIN2023-보2

   기준서에는 **질문만으로는 구분할 수 없는 도표 쌍**이 있습니다.
   예) 보1과 보2는 제목이 글자 그대로 같고 자동차 신호(녹색/황색)만 다릅니다.
   질문에 그 정보가 없으면 어느 쪽을 골라도 틀린 답이 아닙니다.
   하나만 정답으로 두면 **맞는 답을 오답으로 세게 되어** 개선폭이 가려집니다.
   → 여러 개 중 **가장 높은 순위**를 그 문항의 순위로 봅니다.

⚠️ '범위밖'·'정보부족' 문항은 gold_id 가 비어 있습니다.
   이건 **후보를 내놓지 않아야** 정답입니다. 억지 답변은 정확도가 아니라 신뢰 문제입니다.
   지금은 임계값이 없어 무조건 뭔가를 반환하므로 이 항목이 0%로 나옵니다.
   → 점수 임계값·메타 필터(2번 담당)를 붙이면 올라갑니다.

⚠️ 모델·청킹을 바꾼 뒤에는 반드시 인덱스를 다시 만들고 이 스크립트를 돌리세요.
   그래야 개선인지 후퇴인지 숫자로 확인됩니다.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:                                    # 패키지로 import 될 때
    from .paths import GOLD, RESULTS
    from .search import Searcher
except ImportError:                     # 스크립트로 직접 실행할 때
    from paths import GOLD, RESULTS
    from search import Searcher


def gold_ids(cell: str) -> list[str]:
    """`;` 로 구분된 복수 정답을 리스트로. 공백·빈 항목은 버립니다."""
    return [x.strip() for x in cell.split(";") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="검색 성능 평가")
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--out", type=Path, default=None,
                    help="기본값: taek/results/eval_{mode}.csv")
    ap.add_argument("--threshold", type=float, default=None,
                    help="이 점수 미만이면 후보 없음으로 처리 (미지정 시 필터 없음)")
    ap.add_argument("--mode", default="vector",
                    choices=["vector", "bm25", "hybrid", "wsum"],
                    help="검색 방식 (기본 vector)")
    ap.add_argument("--alpha", type=float, default=0.5,
                    help="wsum 전용 — 벡터 가중치 (0=BM25만, 1=벡터만)")
    ap.add_argument("--rrf-k", type=float, default=1.0,
                    help="hybrid 전용 — RRF 상수 (기본 1, 근거는 EVAL.md §EXP-3)")
    ap.add_argument("--reject", action="store_true",
                    help="후보 없음 판정 적용 (벡터·BM25 둘 다 약하면 결과 없음)")
    ap.add_argument("--no-route", action="store_true",
                    help="특수기준 라우팅 끄기 (기본은 켜짐)")
    ap.add_argument("--keep-uncomputable", action="store_true",
                    help="기본과실 없는 도표도 후보에 포함 (기본은 제외)")
    ap.add_argument("--rerank", action="store_true",
                    help="cross-encoder 리랭킹 적용 (느림)")
    ap.add_argument("--expand", action="store_true",
                    help="질의 확장(동의어) 적용 — synonyms.py")
    a = ap.parse_args()
    if a.out is None:
        RESULTS.mkdir(parents=True, exist_ok=True)
        tag = a.mode + (f'_a{a.alpha}' if a.mode == 'wsum' else '') + ('_reject' if a.reject else '')
        tag += '_rerank' if a.rerank else ''
        tag += f'_k{a.rrf_k}' if a.mode == 'hybrid' and a.rrf_k != 60 else ''
        a.out = RESULTS / f"eval_{tag}{'_expand' if a.expand else ''}.csv"

    rows = list(csv.DictReader(a.gold.open(encoding="utf-8-sig")))
    s = Searcher()

    답있음 = [r for r in rows if r["gold_id"].strip()]
    답없음 = [r for r in rows if not r["gold_id"].strip()]

    results = []
    ranks: list[int | None] = []

    print(f"\n{'질문':<44} {'맞힌 정답':<24} 순위")
    print("-" * 80)

    for r in 답있음:
        hits = s.search(r["query"], top_k=a.top_k, mode=a.mode, expand=a.expand,
                        alpha=a.alpha, rrf_k=a.rrf_k, reject=a.reject,
                        route=not a.no_route,
                        only_computable=not a.keep_uncomputable,
                        rerank=a.rerank)
        if a.threshold is not None:
            hits = [h for h in hits if h.score >= a.threshold]
        ids = [h.chunk_id for h in hits]
        # 복수 정답 중 가장 높은 순위를 그 문항의 순위로 봅니다.
        정답들 = gold_ids(r["gold_id"])
        순위들 = [ids.index(g) + 1 for g in 정답들 if g in ids]
        rank = min(순위들) if 순위들 else None
        맞힌정답 = ids[rank - 1] if rank else ""
        ranks.append(rank)
        top1 = hits[0].chunk_id if hits else "-"
        results.append({
            "query": r["query"], "gold_id": r["gold_id"], "type": r["type"],
            "rank": rank or "", "matched_gold": 맞힌정답, "top1": top1,
            "top1_score": round(hits[0].score, 4) if hits else "",
            "top1_facet": hits[0].facet if hits else "",
        })
        mark = "✓" if rank == 1 else (f"{rank}위" if rank else "✗")
        표시 = (맞힌정답 or 정답들[0]) + (f" 외{len(정답들)-1}" if len(정답들) > 1 else "")
        print(f"{r['query'][:42]:<44} {표시:<24} {mark}")

    # 기준 없는 질문 — 아무것도 안 내놔야 정답
    거절 = 0
    for r in 답없음:
        hits = s.search(r["query"], top_k=a.top_k, mode=a.mode, expand=a.expand,
                        alpha=a.alpha, rrf_k=a.rrf_k, reject=a.reject,
                        route=not a.no_route,
                        only_computable=not a.keep_uncomputable,
                        rerank=a.rerank)
        if a.threshold is not None:
            hits = [h for h in hits if h.score >= a.threshold]
        거절 += not hits
        results.append({
            "query": r["query"], "gold_id": "", "type": r["type"],
            "rank": "", "top1": hits[0].chunk_id if hits else "(없음)",
            "top1_score": round(hits[0].score, 4) if hits else "",
            "top1_facet": hits[0].facet if hits else "",
        })

    n = len(ranks)
    hit1 = sum(1 for x in ranks if x == 1)
    hit3 = sum(1 for x in ranks if x and x <= 3)
    hit10 = sum(1 for x in ranks if x and x <= 10)
    mrr = sum(1 / x for x in ranks if x) / n if n else 0

    print("\n" + "=" * 46)
    print(f"검색 방식   : {a.mode}{' + 질의확장' if a.expand else ''}")
    if a.mode == "hybrid":
        print(f"RRF k       : {a.rrf_k}")
    if a.mode == "wsum":
        print(f"alpha(벡터) : {a.alpha}")
    if a.reject:
        from .search import REJECT_BM25, REJECT_VECTOR
        print(f"후보없음 판정: 벡터<{REJECT_VECTOR} AND BM25<{REJECT_BM25}")
    print(f"임베딩      : {s.embedder.name}")
    if a.threshold is not None:
        print(f"점수 임계값 : {a.threshold}")
    print(f"평가 문항   : 정답 있음 {n} / 기준 없음 {len(답없음)}")
    print("-" * 46)
    print(f"Top-1  정확도 : {hit1}/{n}  {hit1/n*100:5.1f}%")
    print(f"Top-3  정확도 : {hit3}/{n}  {hit3/n*100:5.1f}%   ← 핵심 지표")
    print(f"Top-10 정확도 : {hit10}/{n}  {hit10/n*100:5.1f}%")
    print(f"MRR           : {mrr:.3f}")
    print(f"오답 방지     : {거절}/{len(답없음)}  {거절/max(1,len(답없음))*100:5.1f}%")
    print("=" * 46)

    with a.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    print(f"상세 결과 → {a.out}")


if __name__ == "__main__":
    main()