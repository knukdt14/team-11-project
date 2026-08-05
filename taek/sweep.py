"""
설정 스윕 — 여러 검색 설정을 한 번에 비교합니다.

`evaluate.py` 를 설정마다 따로 돌리면 매번 임베딩 모델을 다시 올려서 느립니다.
여기서는 `Searcher` 를 한 번만 만들고 설정만 바꿔 가며 잽니다.

    python -m taek.sweep
    python -m taek.sweep --gold taek/gold_team.csv --out taek/results/sweep.md

⚠️ **같은 평가셋에서 하이퍼파라미터를 고르고 그 점수를 보고하면 낙관 편향이 생깁니다.**
   여기서 고른 k·alpha 는 "이 평가셋 기준 최적"이지 일반적으로 최적은 아닙니다.
   새 평가 문항이 들어오면 **고른 값을 그대로 두고** 다시 재서 확인하세요.
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
    return [x.strip() for x in cell.split(";") if x.strip()]


def measure(s: Searcher, rows: list[dict], top_k: int, **kw) -> dict:
    """설정 하나로 전체 평가셋을 돌려 지표를 냅니다."""
    ranks: list[int | None] = []
    거절 = 0
    답없음 = 0
    for r in rows:
        hits = s.search(r["query"], top_k=top_k, **kw)
        ids = [h.chunk_id for h in hits]
        golds = gold_ids(r["gold_id"])
        if not golds:                    # 후보를 내지 않아야 정답인 문항
            답없음 += 1
            거절 += not hits
            continue
        순위 = [ids.index(g) + 1 for g in golds if g in ids]
        ranks.append(min(순위) if 순위 else None)

    n = len(ranks)
    return {
        "top1": sum(1 for x in ranks if x == 1) / n,
        "top3": sum(1 for x in ranks if x and x <= 3) / n,
        "top10": sum(1 for x in ranks if x and x <= 10) / n,
        "mrr": sum(1 / x for x in ranks if x) / n,
        "reject": 거절 / max(1, 답없음),
        "n": n,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="검색 설정 스윕")
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--expand", action="store_true", help="질의 확장 적용 후 스윕")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    rows = list(csv.DictReader(a.gold.open(encoding="utf-8-sig")))
    s = Searcher()
    ex = {"expand": a.expand}

    설정: list[tuple[str, dict]] = [
        ("벡터 단독", {"mode": "vector"}),
        ("BM25 단독", {"mode": "bm25"}),
    ]
    설정 += [(f"RRF k={k}", {"mode": "hybrid", "rrf_k": k}) for k in (1, 5, 10, 20, 40, 60, 100)]
    설정 += [(f"가중합 α={α}", {"mode": "wsum", "alpha": α})
             for α in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)]

    print(f"\n평가셋: {a.gold.name} · 질의확장: {'ON' if a.expand else 'OFF'}\n")
    hdr = f"| {'설정':<14} | {'Top-1':>7} | {'Top-3':>7} | {'Top-10':>7} | {'MRR':>6} | {'오답방지':>8} |"
    print(hdr)
    print("|" + "-" * 16 + "|" + ("-" * 9 + "|") * 3 + "-" * 8 + "|" + "-" * 10 + "|")

    결과 = []
    for 이름, kw in 설정:
        m = measure(s, rows, a.top_k, **kw, **ex)
        결과.append((이름, m))
        print(f"| {이름:<14} | {m['top1']*100:6.1f}% | {m['top3']*100:6.1f}% | "
              f"{m['top10']*100:6.1f}% | {m['mrr']:6.3f} | {m['reject']*100:7.1f}% |")

    best = max(결과, key=lambda x: x[1]["top3"])
    print(f"\nTop-3 최고: {best[0]}  ({best[1]['top3']*100:.1f}%)")
    print("⚠️ 같은 평가셋에서 고른 값입니다. 새 문항이 오면 그대로 두고 다시 재세요.")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8") as f:
            f.write(f"# 스윕 결과 — {a.gold.name} (질의확장 {'ON' if a.expand else 'OFF'})\n\n")
            f.write("| 설정 | Top-1 | Top-3 | Top-10 | MRR | 오답방지 |\n")
            f.write("|---|---:|---:|---:|---:|---:|\n")
            for 이름, m in 결과:
                f.write(f"| {이름} | {m['top1']*100:.1f}% | {m['top3']*100:.1f}% | "
                        f"{m['top10']*100:.1f}% | {m['mrr']:.3f} | {m['reject']*100:.1f}% |\n")
        print(f"→ {a.out}")


if __name__ == "__main__":
    main()
