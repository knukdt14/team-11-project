"""
RRF k 선택이 통계적으로 믿을 만한지 검증합니다.

스윕에서 `k=1` 이 최고로 나왔는데, 두 가지가 의심스럽습니다.
  · RRF 관례값은 60인데 극단으로 갔다
  · **같은 평가셋에서 고르고 그 점수를 보고**하면 낙관 편향이 섞인다

문항을 더 받지 않고도 여기서 답할 수 있습니다.

  ① 부트스트랩    문항을 복원추출로 재표집해 Top-3 신뢰구간을 낸다.
                  구간이 겹치면 "k=1이 더 낫다"고 말할 수 없다.
  ② 반분 선택     절반에서 k를 고르고 나머지 절반에서 점수를 잰다.
                  이걸 반복한 평균과 "전체에서 고른 최고점"의 차이가 곧 낙관 편향의 크기.
  ③ 경계 확인     k<1 까지 내려 보면 k=1 이 진짜 봉우리인지 절벽 끝인지 알 수 있다.

    python -m taek.validate_k
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

try:
    from .paths import GOLD
    from .search import Searcher
except ImportError:
    from paths import GOLD
    from search import Searcher

K_GRID = [0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0]
B = 2000            # 부트스트랩 반복
SPLITS = 400        # 반분 반복
TOP = 3


def gold_ids(cell: str) -> list[str]:
    return [x.strip() for x in cell.split(";") if x.strip()]


def rank_vector(s: Searcher, rows: list[dict], top_k: int, **kw) -> list[int | None]:
    """설정 하나에 대해 문항별 정답 순위를 구합니다 (없으면 None)."""
    out = []
    for r in rows:
        golds = gold_ids(r["gold_id"])
        if not golds:
            continue
        ids = [h.chunk_id for h in s.search(r["query"], top_k=top_k, **kw)]
        순위 = [ids.index(g) + 1 for g in golds if g in ids]
        out.append(min(순위) if 순위 else None)
    return out


def top3(ranks: list[int | None], idx: list[int]) -> float:
    return sum(1 for i in idx if ranks[i] and ranks[i] <= TOP) / len(idx)


def main() -> None:
    ap = argparse.ArgumentParser(description="RRF k 선택 검증")
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    random.seed(a.seed)
    rows = list(csv.DictReader(a.gold.open(encoding="utf-8-sig")))
    s = Searcher()

    설정: dict[str, dict] = {"벡터": {"mode": "vector"}, "BM25": {"mode": "bm25"}}
    설정.update({f"RRF k={k:g}": {"mode": "hybrid", "rrf_k": k} for k in K_GRID})

    print("문항별 순위 계산 중…")
    ranks = {name: rank_vector(s, rows, a.top_k, **kw) for name, kw in 설정.items()}
    n = len(next(iter(ranks.values())))
    전체 = list(range(n))
    print(f"정답 있는 문항: {n}\n")

    # ── ① 점 추정 + 부트스트랩 신뢰구간 ─────────────────────────────
    print(f"① Top-3 점 추정과 95% 신뢰구간 (부트스트랩 B={B})\n")
    print(f"| {'설정':<12} | {'Top-3':>7} | {'95% CI':>16} |")
    print("|" + "-" * 14 + "|" + "-" * 9 + "|" + "-" * 18 + "|")
    boots: dict[str, list[float]] = {}
    표본 = [[random.randrange(n) for _ in range(n)] for _ in range(B)]
    for name, rk in ranks.items():
        vals = sorted(top3(rk, idx) for idx in 표본)
        boots[name] = vals
        lo, hi = vals[int(B * 0.025)], vals[int(B * 0.975)]
        print(f"| {name:<12} | {top3(rk, 전체)*100:6.1f}% | "
              f"[{lo*100:5.1f}%, {hi*100:5.1f}%] |")

    # ── 짝비교: k=1 이 정말 벡터/k=60 보다 나은가 ────────────────────
    print("\n② 짝비교 — 같은 재표집에서 A가 B보다 나은 비율")
    def 짝비교(A: str, Bn: str) -> None:
        ra, rb = ranks[A], ranks[Bn]
        diff = [top3(ra, idx) - top3(rb, idx) for idx in 표본]
        승 = sum(1 for d in diff if d > 0) / B
        diff.sort()
        lo, hi = diff[int(B * 0.025)], diff[int(B * 0.975)]
        판정 = "유의" if lo > 0 else "판단 불가(0 포함)"
        print(f"   {A:<10} > {Bn:<10} : {승*100:5.1f}%   차이 95% CI "
              f"[{lo*100:+5.1f}%p, {hi*100:+5.1f}%p]  → {판정}")

    for other in ("벡터", "BM25", "RRF k=60"):
        짝비교("RRF k=1", other)

    # ── ③ 반분 선택 — 낙관 편향의 크기 ──────────────────────────────
    print(f"\n③ 반분 선택 (반복 {SPLITS}회) — 절반에서 k를 고르고 나머지 절반에서 채점")
    k이름 = [f"RRF k={k:g}" for k in K_GRID]
    고른것: dict[str, int] = {}
    검증점수 = []
    for _ in range(SPLITS):
        idx = 전체[:]
        random.shuffle(idx)
        half = n // 2
        A, Bh = idx[:half], idx[half:]
        best = max(k이름, key=lambda nm: top3(ranks[nm], A))
        고른것[best] = 고른것.get(best, 0) + 1
        검증점수.append(top3(ranks[best], Bh))

    낙관 = top3(ranks["RRF k=1"], 전체) - sum(검증점수) / len(검증점수)
    print(f"   선택된 k 분포 : " + ", ".join(
        f"{k.replace('RRF ','')}×{c}" for k, c in sorted(고른것.items(), key=lambda x: -x[1])))
    print(f"   전체에서 고른 최고점      : {top3(ranks['RRF k=1'], 전체)*100:.1f}%")
    print(f"   반분 선택 후 검증 평균     : {sum(검증점수)/len(검증점수)*100:.1f}%")
    print(f"   → 낙관 편향 추정          : {낙관*100:+.1f}%p")

    print("\n④ k 경계 — 값을 더 내려도 계속 좋아지나")
    for k in K_GRID:
        nm = f"RRF k={k:g}"
        print(f"   {nm:<12} Top-3 {top3(ranks[nm], 전체)*100:5.1f}%")


if __name__ == "__main__":
    main()
