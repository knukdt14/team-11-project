"""
도로교통법 조문 파서 — 1회성 오프라인 스크립트.

기준 도표의 `laws` 필드("도로교통법 제26조")를 실제 조문 본문과 연결합니다.

이 PDF에는 **같은 조가 두 번 나오는 경우**가 있습니다.
   개정 법률이라 현행 조문과 아직 시행 전인 조문이 함께 실려 있고,
   미시행분 뒤에는 `[시행일: 2027. 6. 3.]` 표기가 붙습니다.
   → 미시행분은 `in_force=False`로 표시하고, 기본 조회에서는 제외합니다.
      (이걸 구분하지 않으면 아직 시행되지 않은 조문을 근거로 답변하게 됩니다.)

사용법
    python parse_law pdf/도로교통법.pdf
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

RE_ARTICLE = re.compile(r"^제(\d+)조(?:의(\d+))?\((.+?)\)", re.M)
RE_EFFECTIVE = re.compile(r"\[시행일:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")
RE_CHAPTER = re.compile(r"^\s*제(\d+)장\s+(.+?)(?:\s*<|$)", re.M)
RE_NOISE = re.compile(r"^(법제처|국가법령정보센터|도로교통법)\s*\d*\s*$", re.M)
RE_PAGE_NOISE = re.compile(r"법제처\s*\d+\s*국가법령정보센터")


def clean(text: str) -> str:
    """페이지 머리말·꼬리말과 줄바꿈으로 끊긴 단어를 정리합니다."""
    text = RE_PAGE_NOISE.sub("\n", text)
    text = RE_NOISE.sub("", text)
    # 조문은 줄바꿈이 잦아 문장이 끊깁니다. 한글 사이 개행은 공백 없이 이어 붙입니다.
    text = re.sub(r"([가-힣,·])\n([가-힣])", r"\1\2", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def parse(pdf: Path) -> list[dict]:
    doc = fitz.open(pdf)

    # 페이지 경계를 기억해 조문마다 출처 페이지를 붙입니다.
    offsets: list[tuple[int, int]] = []  # (문자 시작 위치, 페이지 번호)
    buf: list[str] = []
    pos = 0
    for i in range(doc.page_count):
        t = doc[i].get_text()
        offsets.append((pos, i + 1))
        buf.append(t)
        pos += len(t)
    full = "".join(buf)

    def page_of(idx: int) -> int:
        page = 1
        for start, p in offsets:
            if start <= idx:
                page = p
            else:
                break
        return page

    # 장(章) 매핑
    chapters = [(m.start(), f"제{m.group(1)}장 {m.group(2).strip()}") for m in RE_CHAPTER.finditer(full)]

    def chapter_of(idx: int) -> str | None:
        cur = None
        for start, name in chapters:
            if start <= idx:
                cur = name
            else:
                break
        return cur

    matches = list(RE_ARTICLE.finditer(full))
    records: list[dict] = []

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full)
        body = full[start:end]

        no = f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
        eff = RE_EFFECTIVE.search(body)

        records.append(
            {
                "article_id": f"ROAD-{no}",
                "article_no": no,
                "title": m.group(3).strip(),
                "chapter": chapter_of(start),
                "text": clean(body),
                "source_page": page_of(start),
                # 미시행 표기가 붙은 블록은 아직 효력이 없습니다.
                "in_force": eff is None,
                "effective_from": (
                    f"{eff.group(1)}-{int(eff.group(2)):02d}-{int(eff.group(3)):02d}" if eff else None
                ),
            }
        )

    # 같은 조가 둘이면 현행(in_force=True)을 우선 보이도록 정렬 표시만 남깁니다.
    seen: dict[str, int] = {}
    for r in records:
        seen[r["article_no"]] = seen.get(r["article_no"], 0) + 1
    for r in records:
        r["has_variant"] = seen[r["article_no"]] > 1

    return records


def main() -> None:
    ap = argparse.ArgumentParser(description="도로교통법 조문 파서")
    ap.add_argument("pdf", type=Path)
    a = ap.parse_args()

    records = parse(a.pdf)
    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / "ROADLAW_articles.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    현행 = [r for r in records if r["in_force"]]
    미시행 = [r for r in records if not r["in_force"]]
    print(f"조문 {len(records)}개 추출 → {out}")
    print(f"  현행   : {len(현행)}")
    print(f"  미시행 : {len(미시행)}  (기본 조회에서 제외)")
    if 미시행:
        print("  미시행 목록:", ", ".join(f"{r['article_no']}({r['effective_from']})" for r in 미시행))


if __name__ == "__main__":
    main()