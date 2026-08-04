"""
과실비율분쟁 심의사례 파서 — 1회성 오프라인 스크립트.

⚠️ **기준(계산용)과 사례(참고용)는 반드시 분리합니다.**
   기준의 기본과실이 20:80이어도 심의 결정은 30:70이 될 수 있습니다.
   섞으면 계산이 틀립니다. 그래서 별도 파일·별도 스키마로 저장합니다.

문서 구조 (사례 1건 = 2쪽)
    p.N     제목 / 참고기준 208 / 심의번호 2018-054446
            결정비율 A(청구) : B(피청구) = 20 : 80
            사고내용 · 참고 인정기준 · 기본비율 · 주장 내용
    p.N+1   입증 자료 · 주요 쟁점 · 결정 근거 · 결정 이유

사용법
    python parse_cases.py "pdf/(최종)과실비율심의사례_(54MB).pdf"
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    raise SystemExit("PyMuPDF가 필요합니다:  pip install pymupdf") from None

ROOT = Path(__file__).resolve().parent
INTERIM = ROOT / "data" / "interim"

RE_REVIEW_NO = re.compile(r"^(\d{4}-\d{6})$")
# ⚠️ A/B가 청구·피청구 중 어느 쪽인지는 사례마다 뒤바뀝니다.
#    "A(청구) : B(피청구)" 도 있고 "A(피청구) : B(청구)" 도 있어서 라벨을 함께 잡습니다.
RE_DECISION = re.compile(
    r"A\((청구|피청구)\)\s*[:：]\s*B\((청구|피청구)\)\s*=\s*(\d{1,3})\s*[:：]\s*(\d{1,3})"
)
RE_BASE = re.compile(r"기본비율\s*A\s*[:：]\s*B\s*=\s*(\d{1,3})\s*[:：]\s*(\d{1,3})")
RE_STANDALONE_NO = re.compile(r"^\d{1,3}$")

NOISE = ("자동차사고 과실비율분쟁 심의 사례", "1. 자동차와 자동차의 사고",
         "2. 자동차와 이륜차의 사고", "3. 고속도로의 사고", "목차보기")

LABELS = ["사례 개요", "심의번호", "결정비율", "사고내용", "참고", "인정기준",
          "주장 내용", "청구인", "피청구인", "입증 자료", "주요 쟁점",
          "결정 근거", "결정 이유", "(기본과실)", "참고기준"]


def page_lines(page) -> list[str]:
    out = []
    for raw in page.get_text().splitlines():
        s = raw.strip()
        if not s or any(s.startswith(p) for p in NOISE):
            continue
        out.append(s)
    return out


def collect(lines: list[str], start_label: str, stop_labels: list[str]) -> str:
    """라벨 다음부터 다음 라벨 전까지 모읍니다."""
    buf: list[str] = []
    on = False
    for ln in lines:
        if ln == start_label or ln.startswith(start_label):
            on = True
            rest = ln[len(start_label):].strip(" :：")
            if rest:
                buf.append(rest)
            continue
        if on and any(ln == s or ln.startswith(s) for s in stop_labels):
            break
        if on:
            buf.append(ln.lstrip("•●⊙\t ").strip())
    return " ".join(buf).strip()


def parse(pdf: Path) -> list[dict]:
    doc = fitz.open(pdf)

    # 심의번호가 있는 쪽 = 사례 시작 쪽
    starts: list[int] = []
    for i in range(doc.page_count):
        if any(RE_REVIEW_NO.match(l) for l in page_lines(doc[i])):
            starts.append(i + 1)

    records: list[dict] = []
    for idx, start in enumerate(starts):
        end = min(start + 1, doc.page_count)
        if idx + 1 < len(starts):
            end = min(end, starts[idx + 1] - 1)
        lines: list[str] = []
        for p in range(start, end + 1):
            lines += page_lines(doc[p - 1])
        body = " ".join(lines)

        no = next((l for l in lines if RE_REVIEW_NO.match(l)), None)
        if not no:
            continue

        dm = RE_DECISION.search(body)
        bm = RE_BASE.search(body)

        # 참고기준(구 기준번호): "참고기준" 다음의 단독 숫자
        legacy = None
        for j, ln in enumerate(lines):
            if ln.startswith("참고기준"):
                for k in range(j + 1, min(j + 4, len(lines))):
                    if RE_STANDALONE_NO.match(lines[k]):
                        legacy = lines[k]
                        break
                break

        # 제목: 심의번호 앞쪽에서 가장 긴 문장
        head = lines[: lines.index(no)]
        title = max((h for h in head if 6 < len(h) < 80), key=len, default="")

        records.append({
            "case_id": f"CASE-{no}",
            "review_no": no,
            "title": title,
            # 구 기준번호 → 현 기준 매핑은 확신할 수 없으면 비워 둡니다.
            # 인정기준 PDF의 "※舊 214, 324 기준" 표기와 대조해 채워야 합니다.
            "referenced_standard_original": legacy,
            "referenced_standard_current": None,
            "mapping_status": "review_required",
            "accident_description": collect(lines, "사고내용", ["참고", "인정기준", "기본비율", "주장 내용"]),
            "base_ratio": {"a": int(bm.group(1)), "b": int(bm.group(2))} if bm else None,
            "a_party": dm.group(1) if dm else None,   # A가 청구인지 피청구인지
            "b_party": dm.group(2) if dm else None,
            "decision_ratio": {"a": int(dm.group(3)), "b": int(dm.group(4))} if dm else None,
            "decision_reason": collect(lines, "결정 이유", ["2.", "3.", "목차"]),
            "key_issues": collect(lines, "주요 쟁점", ["결정 근거", "결정 이유"]),
            "source_page": start,
            "page_span": end - start + 1,
            "parse_flags": [] if (dm and bm) else ["비율_미검출"],
        })

    return records


def main() -> None:
    ap = argparse.ArgumentParser(description="심의사례 파서")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N건만")
    a = ap.parse_args()

    records = parse(a.pdf)
    if a.limit:
        records = records[: a.limit]

    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / "CASES_reviews.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    다름 = [
        r for r in records
        if r["base_ratio"] and r["decision_ratio"] and r["base_ratio"] != r["decision_ratio"]
    ]
    print(f"심의사례 {len(records)}건 추출 → {out}")
    print(f"  결정비율 확보  : {sum(1 for r in records if r['decision_ratio'])}")
    print(f"  기본비율 확보  : {sum(1 for r in records if r['base_ratio'])}")
    print(f"  참고기준 번호  : {sum(1 for r in records if r['referenced_standard_original'])}")
    print(f"  기준≠결정      : {len(다름)}건  ← 기준과 사례를 분리해야 하는 이유")
    print(f"  검수 필요      : {sum(1 for r in records if r['parse_flags'])}")


if __name__ == "__main__":
    main()