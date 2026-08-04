"""
과실비율 기준 PDF 파서 — 문서 3종 지원.

문서마다 도표 표기·기본과실 표기·수정요소 표기가 전부 다릅니다.
그래서 **문서별 프로파일**로 규칙을 분리했습니다.

  MAIN2023   차15-1 / "A30 B70" / "A 현저한 과실 +10"
             보 챕터는 "보행자 기본 과실비율" 다음 줄에 숫자 하나만 옵니다.
  PM2021     "20. 교차로 부근 …(PM)" / "A 0 B 100" / "A 현저한 과실 +10"
  ROUND2025  회전-8 / "레드20 블루80" / "레드(A) 서행불이행 +10"

사용법
    python parse_pdf.py diagnose "pdf/파일.pdf"
    python parse_pdf.py index    "pdf/파일.pdf" --source-id PM2021
    python parse_pdf.py extract  "pdf/파일.pdf" --source-id PM2021
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    raise SystemExit("PyMuPDF가 필요합니다:  pip install pymupdf") from None

from schema import Modifier, Ratio, Standard

ROOT = Path(__file__).resolve().parent
INTERIM = ROOT / "data" / "interim"

RE_VALUE = re.compile(r"^([+\-−]\s*\d{1,3})\s*%?$")
RE_LAW = re.compile(r"(도로교통법\s*제\s*\d+조(?:의\d+)?)")
RE_PRECEDENT = re.compile(
    r"(대법원|[가-힣]+법원[가-힣\s]*)\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*선고\s*\S+"
)
RE_LEGACY = re.compile(r"※?\s*舊\s*([0-9,\s]+)\s*기준")


# ---------------------------------------------------------------------------
# 문서 프로파일
# ---------------------------------------------------------------------------


@dataclass
class Profile:
    source_id: str
    diagram_no: re.Pattern
    ratio_pair: re.Pattern
    party_a: re.Pattern
    party_b: re.Pattern
    section_labels: list[str]
    noise_prefixes: tuple[str, ...] = ()
    section_header: re.Pattern | None = None
    title_on_same_line: bool = False
    mod_prefixes: list[tuple[str, str]] = field(default_factory=list)  # (접두어, 대상)
    ped_ratio_label: re.Pattern | None = None
    require_text: str = "기본"
    loose_modifier: bool = False   # 접두어 없는 수정요소도 허용 (PM 문서)


PROFILES: dict[str, Profile] = {
    "MAIN2023": Profile(
        source_id="MAIN2023",
        diagram_no=re.compile(r"^(보|차|거)(\d{1,3})(?:-(\d{1,2}))?$"),
        ratio_pair=re.compile(r"^A\s*(\d{1,3})\s*B\s*(\d{1,3})$"),
        # 보행자 챕터는 (A)/(B) 대신 (보)/(차) 로 적혀 있습니다.
        party_a=re.compile(r"^\((?:A|보)\)\s*(.*)$"),
        party_b=re.compile(r"^\((?:B|차)\)\s*(.*)$"),
        section_labels=[
            "사고 상황", "기본 과실비율 해설",
            "수정요소(인과관계를 감안한 과실비율 조정) 해설", "수정요소 해설",
            "관련 법규", "참고 판례", "활용시 참고 사항",
        ],
        noise_prefixes=("제1장.", "제2장.", "제3장.", "제4장.", "제5장.",
                        "자동차사고 과실비율 인정기준", "목차"),
        section_header=re.compile(r"\[((?:보|차|거)\d{1,3})\]"),
        mod_prefixes=[("A", "A"), ("B", "B")],
        ped_ratio_label=re.compile(r"^보행자\s*기본\s*과실비율$"),
        require_text="기본 과실비율",
    ),
    "PM2021": Profile(
        source_id="PM2021",
        diagram_no=re.compile(r"^(\d{1,2})\.\s*(\S.*사고.*)$"),
        ratio_pair=re.compile(r"^A\s*(\d{1,3})\s*B\s*(\d{1,3})$"),
        party_a=re.compile(r"^(?:PM|자동차|자전거)?\s*A\s*[:：]\s*(.*)$"),
        party_b=re.compile(r"^(?:PM|자동차|자전거)?\s*B\s*[:：]\s*(.*)$"),
        section_labels=["사고 상황 :", "기본과실 해설 :", "수정요소 해설 :"],
        noise_prefixes=("- ", "[도표해설]"),
        title_on_same_line=True,
        mod_prefixes=[("A", "A"), ("B", "B")],
        require_text="기본",
        loose_modifier=True,
    ),
    "ROUND2025": Profile(
        source_id="ROUND2025",
        diagram_no=re.compile(r"^(회전)-(\d{1,2})$"),
        ratio_pair=re.compile(r"^레드\s*(\d{1,3})\s*블루\s*(\d{1,3})$"),
        party_a=re.compile(r"^레드\(A\)\s*[:：]\s*(.*)$"),
        party_b=re.compile(r"^블루\(B\)\s*[:：]\s*(.*)$"),
        section_labels=["사고 상황", "기본 과실비율 해설", "수정요소 해설",
                        "관련 법규", "참고 판례", "활용시 참고 사항"],
        noise_prefixes=("2차로형 회전교차로 사고 과실비율 비정형 기준",),
        mod_prefixes=[("레드(A)", "A"), ("블루(B)", "B")],
        require_text="기본 과실비율",
    ),
}


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------


def page_lines(page, prof: Profile) -> list[str]:
    """
    페이지 텍스트를 줄 단위로. 머리말·꼬리말 제거.

    ⚠️ 단독 숫자는 **앞 6줄에서만** 페이지 번호로 보고 버립니다.
       본문의 단독 숫자는 보행자 기본과실 값이라 지우면 안 됩니다.
    """
    out: list[str] = []
    for idx, raw in enumerate(page.get_text().splitlines()):
        s = raw.strip()
        if not s:
            continue
        if s.isdigit() and idx < 6:
            continue
        if any(s.startswith(p) for p in prof.noise_prefixes):
            continue
        out.append(s)
    return out


def book_page_of(page) -> int | None:
    for raw in page.get_text().splitlines()[:6]:
        s = raw.strip().lstrip("- ").rstrip(" -").strip()
        if s.isdigit():
            return int(s)
    return None


def norm_no(prof: Profile, m: re.Match) -> str:
    if prof.source_id == "MAIN2023":
        return m.group(0)
    if prof.source_id == "PM2021":
        return m.group(1)
    return f"회전-{m.group(2)}"


def cut_at_next(lines: list[str], diagram_no: str, prof: Profile) -> list[str]:
    """자기 도표번호 이후, 다음 도표번호 직전까지만 남깁니다."""
    try:
        begin = lines.index(diagram_no)
    except ValueError:
        begin = 0
    out = [lines[begin]] if begin < len(lines) else []
    for ln in lines[begin + 1:]:
        m = prof.diagram_no.match(ln)
        if m and norm_no(prof, m) != diagram_no:
            break
        out.append(ln)
    return out


# ---------------------------------------------------------------------------
# 1) diagnose
# ---------------------------------------------------------------------------


def cmd_diagnose(pdf: Path, sample: int = 14) -> None:
    doc = fitz.open(pdf)
    n = doc.page_count
    print(f"파일 : {pdf.name}\n쪽수 : {n}\n")
    print(f"{'쪽':>5} {'텍스트자수':>10} {'이미지':>6}  판정")
    print("-" * 46)
    idx = [max(1, round(i * n / sample)) for i in range(1, sample + 1)]
    ok_cnt = 0
    for p in idx:
        pg = doc[p - 1]
        t = pg.get_text().strip()
        ok = len(t) > 300
        ok_cnt += ok
        print(f"{p:>5} {len(t):>10} {len(pg.get_images(full=True)):>6}  "
              f"{'텍스트 기반' if ok else '이미지 위주(주의)'}")
    print("\n[요약]")
    print("  ✅ 자동 추출 가능" if ok_cnt >= sample * 0.6 else "  ⚠️ 수기 보정 또는 OCR 필요")
    print(f"  '기본' 포함 페이지 : {sum(1 for i in range(n) if '기본' in doc[i].get_text())}")
    print(f"  '舊' 포함 페이지   : {sum(1 for i in range(n) if '舊' in doc[i].get_text())}")


# ---------------------------------------------------------------------------
# 2) index
# ---------------------------------------------------------------------------


def build_index(doc, prof: Profile) -> list[dict]:
    """
    도표 시작 지점 목록.

    ⚠️ 도표번호는 본문 상호참조와 권말 색인에도 나옵니다.
       그래서 그 페이지에 기본과실 표기가 있어야 진짜 도표로 인정하고,
       같은 번호는 첫 등장만 채택합니다.
    """
    markers: list[dict] = []
    seen: set[str] = set()
    section = None

    for i in range(doc.page_count):
        text = doc[i].get_text()
        is_diagram_page = prof.require_text in text
        lines = page_lines(doc[i], prof)

        for ln in lines:
            if prof.section_header:
                sm = prof.section_header.search(ln)
                if sm and len(ln) > 6:
                    section = ln
            if not is_diagram_page:
                continue
            m = prof.diagram_no.match(ln)
            if not m:
                continue
            no = norm_no(prof, m)
            if no in seen:
                continue
            seen.add(no)
            markers.append({
                "diagram_no": no,
                "page": i + 1,
                "section": section,
                "title_inline": m.group(2).strip() if prof.title_on_same_line else None,
            })

    markers.sort(key=lambda x: x["page"])
    return markers


def cmd_index(pdf: Path, source_id: str) -> None:
    prof = PROFILES[source_id]
    doc = fitz.open(pdf)
    markers = build_index(doc, prof)
    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / f"{source_id}_index.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for m in markers:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"[{source_id}] 도표 {len(markers)}개 발견 → {out}\n")
    for m in markers[:10]:
        label = m["title_inline"] or (m["section"] or "")
        print(f"  {m['diagram_no']:<10} p.{m['page']:<4} {label[:46]}")
    if len(markers) > 10:
        print(f"  … 외 {len(markers)-10}개")


# ---------------------------------------------------------------------------
# 3) extract
# ---------------------------------------------------------------------------


def parse_block(lines: list[str], mk: dict, prof: Profile) -> dict:
    res: dict = {
        "title": mk.get("title_inline") or "",
        "party_a": "", "party_b": "",
        "base_ratio": None, "base_ratio_variants": {},
        "modifiers": [], "legacy_nos": [], "flags": [],
    }

    if not res["title"]:
        try:
            start = lines.index(mk["diagram_no"])
        except ValueError:
            start = 0
        for ln in lines[start + 1: start + 4]:
            if not prof.party_a.match(ln) and "기본" not in ln:
                res["title"] = ln
                break

    ratios_a: list[int] = []
    ratios_b: list[int] = []
    conditions: list[str] = []
    cur_condition: str | None = None
    cur_note: str | None = None
    pending: tuple[str, str] | None = None
    ped_mode = prof.ped_ratio_label is not None and mk["diagram_no"].startswith("보")
    expect_ped = False

    for ln in lines:
        if ped_mode and prof.ped_ratio_label.match(ln):
            expect_ped = True
            continue
        if expect_ped and re.fullmatch(r"\d{1,3}", ln):
            v = int(ln)
            if 0 <= v <= 100:
                ratios_a.append(v)          # A = 보행자
                ratios_b.append(100 - v)
                expect_ped = False
            continue

        if m := prof.party_a.match(ln):
            res["party_a"] = res["party_a"] or m.group(1).strip()
            continue
        if m := prof.party_b.match(ln):
            res["party_b"] = res["party_b"] or m.group(1).strip()
            continue
        if m := RE_LEGACY.search(ln):
            res["legacy_nos"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
            continue
        if m := re.fullmatch(r"\((가|나|다|라|마)\)", ln):
            cur_condition = m.group(1)
            conditions.append(cur_condition)
            continue
        if m := re.fullmatch(r"([①-⑳])", ln):
            cur_note = m.group(1)
            continue

        if m := prof.ratio_pair.match(ln):
            ratios_a.append(int(m.group(1)))
            ratios_b.append(int(m.group(2)))
            continue
        if m := re.fullmatch(r"A\s*(\d{1,3})", ln):
            ratios_a.append(int(m.group(1)))
            continue
        if m := re.fullmatch(r"B\s*(\d{1,3})", ln):
            ratios_b.append(int(m.group(1)))
            continue

        # 수정요소: 이름 줄 → 값 줄
        if m := RE_VALUE.match(ln):
            if pending:
                target, name = pending
                res["modifiers"].append({
                    "name": name, "target": target,
                    "adjustment": int(m.group(1).replace(" ", "").replace("−", "-")),
                    "condition": cur_condition, "note_ref": cur_note,
                })
                pending, cur_note = None, None
            continue

        name = ln.strip()
        hit = None
        for pre, target in prof.mod_prefixes:
            if name.startswith(pre):
                hit = (target, name[len(pre):].strip())
                break
        if hit and hit[1]:
            pending = hit
            continue
        if ped_mode and 1 < len(name) < 30 and not name.startswith(("※", "⊙", "(")):
            pending = ("B" if name.startswith("차의") else "A", name)
            continue
        if prof.loose_modifier and 1 < len(name) < 24 and not name.startswith(
            ("※", "⊙", "[", "-", "사고", "기본", "수정")
        ):
            pending = ("A", name)

    pairs = list(zip(ratios_a, ratios_b, strict=False))
    valid = [(a, b) for a, b in pairs if a + b == 100]
    if not pairs:
        res["flags"].append("기본과실_미검출")
    elif not valid:
        res["flags"].append("기본과실_합계_불일치")
    else:
        res["base_ratio"] = {"a": valid[0][0], "b": valid[0][1]}
        if len(valid) > 1:
            labels = conditions or [f"case{i+1}" for i in range(len(valid))]
            for lab, (a, b) in zip(labels, valid, strict=False):
                res["base_ratio_variants"][lab] = {"a": a, "b": b}
            res["flags"].append("조건별_기본과실_다수")
    if not res["modifiers"]:
        res["flags"].append("수정요소_미검출")
    return res


def parse_sections(lines: list[str], prof: Profile) -> dict:
    out: dict[str, list[str]] = {k: [] for k in prof.section_labels}
    cur = None
    for ln in lines:
        hit = next((lab for lab in prof.section_labels if ln.startswith(lab)), None)
        if hit:
            cur = hit
            rest = ln[len(hit):].strip(" :：")
            if rest:
                out[cur].append(rest)
            continue
        if cur:
            out[cur].append(ln.lstrip("⊙●•\t ").strip())
    return {k: " ".join(v).strip() for k, v in out.items()}


def pick(sec: dict, *keys: str) -> str:
    for k in keys:
        if sec.get(k):
            return sec[k]
    return ""


def cmd_extract(pdf: Path, source_id: str, limit: int | None = None) -> None:
    prof = PROFILES[source_id]
    doc = fitz.open(pdf)
    markers = build_index(doc, prof)
    if limit:
        markers = markers[:limit]

    records: list[Standard] = []
    errors: list[dict] = []

    for i, mk in enumerate(markers):
        start = mk["page"]
        end = markers[i + 1]["page"] - 1 if i + 1 < len(markers) else min(start + 2, doc.page_count)
        end = max(start, min(end, start + 3))

        lines: list[str] = []
        for p in range(start, end + 1):
            lines += page_lines(doc[p - 1], prof)

        # ⚠️ 한 페이지에 도표가 둘 이상 실리는 경우가 있습니다(예: 보3과 보4가 같은 쪽).
        #    다음 도표번호가 나오면 거기서 잘라야 옆 도표의 기본과실을 먹지 않습니다.
        lines = cut_at_next(lines, mk["diagram_no"], prof)

        try:
            parsed = parse_block(lines, mk, prof)
            sec = parse_sections(lines, prof)
            # \xa0(non-breaking space)가 섞여 있으면 법조항 매칭이 실패합니다.
            body = " ".join(lines).replace("\u00a0", " ")

            records.append(Standard(
                standard_id=f"{source_id}-{mk['diagram_no']}",
                source_id=source_id,
                diagram_no=mk["diagram_no"],
                section=mk["section"],
                title=parsed["title"],
                party_a=parsed["party_a"],
                party_b=parsed["party_b"],
                base_ratio=Ratio(**parsed["base_ratio"]) if parsed["base_ratio"] else None,
                base_ratio_variants={
                    k: Ratio(**v) for k, v in parsed["base_ratio_variants"].items()
                },
                modifiers=[Modifier(**m) for m in parsed["modifiers"]],
                accident_description=pick(sec, "사고 상황", "사고 상황 :"),
                base_ratio_explanation=pick(sec, "기본 과실비율 해설", "기본과실 해설 :"),
                modifier_explanation=pick(
                    sec, "수정요소(인과관계를 감안한 과실비율 조정) 해설",
                    "수정요소 해설", "수정요소 해설 :"),
                laws=sorted({re.sub(r"\s+", " ", x).strip() for x in RE_LAW.findall(body)}),
                precedents=sorted({m.group(0) for m in RE_PRECEDENT.finditer(body)}),
                legacy_nos=parsed["legacy_nos"],
                source_page=start,
                book_page=book_page_of(doc[start - 1]),
                page_span=end - start + 1,
                parse_flags=parsed["flags"],
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append({"diagram_no": mk["diagram_no"], "page": start, "error": str(exc)})

    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / f"{source_id}_standards.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")
    if errors:
        (INTERIM / f"{source_id}_parse_errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[{source_id}] 추출 {len(records)}개 / 실패 {len(errors)}개 → {out}")
    print(f"  기본과실 확보  : {sum(1 for r in records if r.base_ratio)}")
    print(f"  수정요소 확보  : {sum(1 for r in records if r.modifiers)}")
    print(f"  舊 기준 매핑   : {sum(1 for r in records if r.legacy_nos)}")
    flagged = [r for r in records if r.parse_flags]
    if flagged:
        import collections
        c = collections.Counter(f for r in flagged for f in r.parse_flags)
        print(f"  검수 필요      : {len(flagged)}")
        for k, v in c.most_common():
            print(f"      {k}: {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description="과실비율 기준 PDF 파서")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in [("diagnose", "표가 텍스트인지 판정"),
                        ("index", "도표번호 → 페이지 매핑"),
                        ("extract", "구조화 JSONL 생성")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("pdf", type=Path)
        if name != "diagnose":
            p.add_argument("--source-id", required=True, choices=list(PROFILES))
        if name == "extract":
            p.add_argument("--limit", type=int, default=None)

    a = ap.parse_args()
    if a.cmd == "diagnose":
        cmd_diagnose(a.pdf)
    elif a.cmd == "index":
        cmd_index(a.pdf, a.source_id)
    else:
        cmd_extract(a.pdf, a.source_id, a.limit)


if __name__ == "__main__":
    main()