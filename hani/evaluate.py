"""
검색 성능 평가.

    python evaluate.py                    # 기본 (gold_queries.csv)
    python evaluate.py --top-k 5
    python evaluate.py --out results.csv

측정 지표
  Top-1 / Top-3 / Top-10 정확도   정답 도표가 몇 위 안에 들어왔나
  MRR                            정답 순위의 역수 평균 (1위=1.0, 3위=0.33)
  오답 방지율                     기준이 없는 질문에 후보를 안 내놓는 비율

⚠️ '범위밖'·'정보부족' 문항은 gold_id 가 비어 있습니다.
   이건 **후보를 내놓지 않아야** 정답입니다. 억지 답변은 정확도가 아니라 신뢰 문제입니다.
   지금은 임계값이 없어 무조건 뭔가를 반환하므로 이 항목이 0%로 나옵니다.
   → 3번(검색·RAG) 담당이 점수 임계값·메타 필터를 붙이면 올라갑니다.

⚠️ 모델·청킹을 바꾼 뒤에는 반드시 인덱스를 다시 만들고 이 스크립트를 돌리세요.
   그래야 개선인지 후퇴인지 숫자로 확인됩니다.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from search import Searcher

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold_queries.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description="검색 성능 평가")
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--out", type=Path, default=ROOT / "eval_results.csv")
    ap.add_argument("--threshold", type=float, default=None,
                    help="이 점수 미만이면 후보 없음으로 처리 (미지정 시 필터 없음)")
    a = ap.parse_args()

    rows = list(csv.DictReader(a.gold.open(encoding="utf-8-sig")))
    s = Searcher()

    답있음 = [r for r in rows if r["gold_id"].strip()]
    답없음 = [r for r in rows if not r["gold_id"].strip()]

    results = []
    ranks: list[int | None] = []

    print(f"\n{'질문':<44} {'정답':<20} 순위")
    print("-" * 76)

    for r in 답있음:
        hits = s.search(r["query"], top_k=a.top_k)
        if a.threshold is not None:
            hits = [h for h in hits if h.score >= a.threshold]
        ids = [h.chunk_id for h in hits]
        rank = ids.index(r["gold_id"]) + 1 if r["gold_id"] in ids else None
        ranks.append(rank)
        top1 = hits[0].chunk_id if hits else "-"
        results.append({
            "query": r["query"], "gold_id": r["gold_id"], "type": r["type"],
            "rank": rank or "", "top1": top1,
            "top1_score": round(hits[0].score, 4) if hits else "",
            "top1_facet": hits[0].facet if hits else "",
        })
        mark = "✓" if rank == 1 else (f"{rank}위" if rank else "✗")
        print(f"{r['query'][:42]:<44} {r['gold_id']:<20} {mark}")

    # 기준 없는 질문 — 아무것도 안 내놔야 정답
    거절 = 0
    for r in 답없음:
        hits = s.search(r["query"], top_k=a.top_k)
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