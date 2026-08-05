"""
검색용 청크 생성 — 부모(도표) / 자식(면) 구조.

⭐ 왜 도표 하나를 여러 청크로 쪼개나
   도표 하나에는 성격이 다른 덩어리가 섞여 있습니다.
     · 유형 요약   "무신호교차로 직진 대 좌회전, A30:B70"
     · 사고 상황   "신호기 없는 교차로에서 직진하는 A차량과 …"
     · 기본과실 해설 "도로교통법 제26조 제4항에 따라 …"
     · 수정요소     "A 현저한 과실 +10 ; B 서행불이행 +10 …"
   이걸 한 벡터로 뭉치면 서로 다른 내용이 평균돼서 **모든 도표가 비슷해집니다.**
   실제로 그렇게 만들었더니 상위 5개 점수가 0.599~0.606에 몰렸습니다.

   그래서 면(facet)마다 따로 임베딩하고, 검색 결과는 `parent_id` 로 합칩니다.
   질문이 사고 상황에 가까우면 '상황' 면이, 법리에 가까우면 '해설' 면이 뽑힙니다.

⭐ 수정요소 나열은 별도 면으로 분리했습니다.
   "A 현저한 과실 +10 / A 중대한 과실 +20" 는 거의 모든 도표에 똑같이 나옵니다.
   본문에 섞어 두면 도표끼리 30% 이상 같아져서 유사도가 평평해집니다.

⭐ 긴 법 조문은 항(①②③) 단위로 자릅니다.
   제2조는 5,600자가 넘어 통째로는 무슨 조문인지 흐려집니다.

⭐ 검색용 텍스트(text)와 화면 표시용 구조 데이터(payload)는 계속 분리합니다.
   image_path 는 절대 임베딩하지 않습니다.

사용법
    python build_chunks.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:                                    # 패키지로 import 될 때 (backend 등 외부에서)
    from .party import roles_of
except ImportError:                     # 스크립트로 직접 실행할 때 (python build_chunks.py)
    from party import roles_of

ROOT = Path(__file__).resolve().parent
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

MIN_LEN = 12          # 이보다 짧은 면은 만들지 않습니다 (노이즈)
LAW_SPLIT_OVER = 900  # 이 길이를 넘는 조문만 항 단위로 자릅니다
RE_HANG = re.compile(r"(?=[①-⑳])")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def make(parent_id: str, facet: str, text: str, kind: str, source_id: str,
         meta_extra: dict) -> dict:
    """자식 청크 하나. payload 는 부모에만 두고 여기엔 넣지 않습니다."""
    return {
        "chunk_id": f"{parent_id}#{facet}",
        "parent_id": parent_id,
        "facet": facet,
        "kind": kind,
        "source_id": source_id,
        "text": text.strip(),
        "meta": {"kind": kind, "source_id": source_id, "parent_id": parent_id,
                 "facet": facet, **meta_extra},
    }


# ---------------------------------------------------------------------------
# 기준 도표
# ---------------------------------------------------------------------------


def standard_chunks(s: dict) -> tuple[list[dict], dict]:
    pid = s["standard_id"]
    기본 = s.get("base_ratio")
    변형 = s.get("base_ratio_variants") or {}
    수정 = s.get("modifiers") or []

    유형 = " ".join(x for x in [s.get("section"), s.get("title")] if x)
    유형 = re.sub(r"^\(?\d+\)?[).]\s*", "", 유형)          # "4) " 같은 번호 제거
    유형 = re.sub(r"\[(?:보|차|거)\d+\]", "", 유형).strip()

    meta = {
        "diagram_no": s["diagram_no"],
        "party_prefix": s["diagram_no"][0],
        "has_base_ratio": bool(기본),
        "needs_review": bool(s.get("parse_flags")),
    }
    out: list[dict] = []

    # ① 요약 — 도표를 식별하는 가장 짧고 밀도 높은 면
    요약 = "\n".join(x for x in [
        f"{유형}",
        f"A: {s.get('party_a','')} / B: {s.get('party_b','')}".strip(),
        (f"기본과실 A{기본['a']} 대 B{기본['b']}" if 기본 else ""),
        (" ".join(f"({k}) A{v['a']}대B{v['b']}" for k, v in 변형.items()) if 변형 else ""),
    ] if x)
    out.append(make(pid, "요약", 요약, "standard", s["source_id"], meta))

    # ② 사고 상황 — 사용자의 서술과 가장 가까운 면
    if len(s.get("accident_description", "")) >= MIN_LEN:
        out.append(make(pid, "상황", s["accident_description"], "standard", s["source_id"], meta))

    # ③ 기본과실 해설 — 법리 질문용
    if len(s.get("base_ratio_explanation", "")) >= MIN_LEN:
        out.append(make(pid, "해설", s["base_ratio_explanation"], "standard", s["source_id"], meta))

    # ④ 수정요소 — 보일러플레이트라 따로 뺍니다
    if 수정:
        txt = "수정요소 " + ", ".join(
            f"{m['target']} {m['name']} {m['adjustment']:+d}" for m in 수정
        )
        out.append(make(pid, "수정요소", txt, "standard", s["source_id"], meta))

    role_a, role_b = roles_of(s["source_id"], s["diagram_no"])
    payload = {
        "kind": "standard",
        "source_id": s["source_id"],
        "diagram_no": s["diagram_no"],
        # ⚠️ A/B가 각각 무엇인지. 상담자 기준 변환은 party.to_consultant_view() 에서만.
        "role_a": role_a,
        "role_b": role_b,
        "title": s.get("title", ""),
        "section": s.get("section"),
        "party_a": s.get("party_a", ""),
        "party_b": s.get("party_b", ""),
        "base_ratio": 기본,
        "base_ratio_variants": 변형,
        "modifiers": 수정,
        "laws": s.get("laws", []),
        "precedents": s.get("precedents", []),
        "legacy_nos": s.get("legacy_nos", []),
        "accident_description": s.get("accident_description", ""),
        "base_ratio_explanation": s.get("base_ratio_explanation", ""),
        "source_page": s.get("source_page"),
        "book_page": s.get("book_page"),
        "image_path": s.get("diagram_image"),   # ← 임베딩 대상 아님
        "parse_flags": s.get("parse_flags", []),
    }
    return out, payload


# ---------------------------------------------------------------------------
# 심의사례
# ---------------------------------------------------------------------------


def case_chunks(c: dict) -> tuple[list[dict], dict]:
    """
    ⚠️ 사례는 **참고용**입니다. 계산에 쓰면 안 됩니다.
       기본비율과 결정비율이 다른 사례가 많습니다.
    """
    pid = c["case_id"]
    기본, 결정 = c.get("base_ratio"), c.get("decision_ratio")
    meta = {
        "review_no": c["review_no"],
        "ratio_differs": bool(기본 and 결정 and 기본 != 결정),
    }
    out: list[dict] = []

    요약 = "\n".join(x for x in [
        c.get("title", ""),
        (f"기본비율 A{기본['a']} 대 B{기본['b']}" if 기본 else ""),
        (f"결정비율 A{결정['a']} 대 B{결정['b']}" if 결정 else ""),
    ] if x)
    if len(요약) >= MIN_LEN:
        out.append(make(pid, "요약", 요약, "case", "CASES", meta))
    if len(c.get("accident_description", "")) >= MIN_LEN:
        out.append(make(pid, "상황", c["accident_description"], "case", "CASES", meta))
    if len(c.get("decision_reason", "")) >= MIN_LEN:
        out.append(make(pid, "결정이유", c["decision_reason"], "case", "CASES", meta))

    payload = {
        "kind": "case",
        "source_id": "CASES",
        "review_no": c["review_no"],
        "title": c.get("title", ""),
        "base_ratio": 기본,
        "decision_ratio": 결정,
        # ⚠️ A가 청구인지 피청구인지는 사례마다 뒤바뀝니다. 놓치면 과실이 정반대가 됩니다.
        "a_party": c.get("a_party"),
        "b_party": c.get("b_party"),
        "referenced_standard_original": c.get("referenced_standard_original"),
        "referenced_standard_current": c.get("referenced_standard_current"),
        "mapping_status": c.get("mapping_status"),
        "accident_description": c.get("accident_description", ""),
        "decision_reason": c.get("decision_reason", ""),
        "source_page": c.get("source_page"),
    }
    return out, payload


# ---------------------------------------------------------------------------
# 법 조문
# ---------------------------------------------------------------------------


def law_chunks(a: dict) -> tuple[list[dict], dict]:
    pid = a["article_id"]
    head = f"{a['article_no']}({a['title']})"
    meta = {"article_no": a["article_no"], "in_force": bool(a.get("in_force", True))}
    body = a["text"]
    out: list[dict] = []

    if len(body) <= LAW_SPLIT_OVER:
        out.append(make(pid, "전문", body, "law", "ROADLAW", meta))
    else:
        # 긴 조문은 항(①②③) 단위로. 각 조각에 조 제목을 붙여 맥락을 유지합니다.
        parts = [p.strip() for p in RE_HANG.split(body) if len(p.strip()) >= MIN_LEN]
        for i, p in enumerate(parts, 1):
            out.append(make(pid, f"항{i}", f"{head} {p}", "law", "ROADLAW", meta))

    payload = {
        "kind": "law",
        "source_id": "ROADLAW",
        "article_no": a["article_no"],
        "title": a["title"],
        "chapter": a.get("chapter"),
        "text": body,
        "source_page": a.get("source_page"),
        "in_force": a.get("in_force", True),
        "effective_from": a.get("effective_from"),
    }
    return out, payload


# ---------------------------------------------------------------------------


def main() -> None:
    chunks: list[dict] = []
    payloads: dict[str, dict] = {}

    for src in ("MAIN2023", "PM2021", "ROUND2025"):
        rows = load_jsonl(INTERIM / f"{src}_standards.jsonl")
        for r in rows:
            cs, pl = standard_chunks(r)
            chunks += cs
            payloads[r["standard_id"]] = pl
        if rows:
            print(f"  {src}: 도표 {len(rows)}건")

    cases = load_jsonl(INTERIM / "CASES_reviews.jsonl")
    for c in cases:
        cs, pl = case_chunks(c)
        chunks += cs
        payloads[c["case_id"]] = pl
    if cases:
        print(f"  CASES: 심의사례 {len(cases)}건")

    laws = [a for a in load_jsonl(INTERIM / "ROADLAW_articles.jsonl") if a.get("in_force", True)]
    for a in laws:
        cs, pl = law_chunks(a)
        chunks += cs
        payloads[a["article_id"]] = pl
    if laws:
        print(f"  ROADLAW: 현행 조문 {len(laws)}건")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    with (PROCESSED / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (PROCESSED / "payloads.json").write_text(
        json.dumps(payloads, ensure_ascii=False), encoding="utf-8")

    if not chunks:
        print("\n⚠️ 청크가 0개입니다. data/interim/ 이 비어 있습니다.")
        print("   파서를 먼저 실행하세요:  python build_all.py")
        return

    import collections
    facet = collections.Counter(c["facet"] for c in chunks)
    길이 = [len(c["text"]) for c in chunks]
    print(f"\n부모 {len(payloads)}개 → 자식 청크 {len(chunks)}개")
    print("  면별:", dict(facet))
    print(f"  평균 {sum(길이)//max(1,len(길이))}자 / 최소 {min(길이)} / 최대 {max(길이)}")
    print(f"  → {PROCESSED/'chunks.jsonl'}")


if __name__ == "__main__":
    main()