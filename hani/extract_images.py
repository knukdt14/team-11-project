"""
도표 이미지 추출 — 1회성 오프라인 스크립트.

화면에 "근거 도표"를 띄우려면 이미지 파일이 있어야 합니다.
파서는 도표의 **페이지**를 알고 있으므로, 그 페이지에서 이미지를 뽑아 도표번호로 저장합니다.

두 가지 방식
  embedded  PDF에 박힌 이미지 객체만 추출 (깔끔하지만 도표가 벡터 그림이면 못 잡음)
  render    페이지 상단 영역을 통째로 렌더 (항상 성공 · **기본값**)

⚠️ 한 페이지에 도표가 둘 이상 실린 경우가 있어(보3·보4), 페이지 전체를 렌더하면
   옆 도표까지 담깁니다. 그래서 --render 는 페이지를 세로로 나눠 해당 도표 순번의
   구역만 잘라냅니다(같은 쪽 도표 수로 균등 분할).

사용법
    python extract_images.py "pdf/230630_….pdf" --source-id MAIN2023
    python extract_images.py "pdf/….pdf" --source-id PM2021 --mode embedded

산출
    data/images/{standard_id}.png
    data/interim/{source_id}_standards.jsonl 의 diagram_image 필드 갱신
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    raise SystemExit("PyMuPDF가 필요합니다:  pip install pymupdf") from None

ROOT = Path(__file__).resolve().parent
INTERIM = ROOT / "data" / "interim"
IMAGES = ROOT / "data" / "images"

MIN_PX = 120  # 이보다 작은 이미지는 아이콘으로 보고 버립니다


def render_clip(doc, page_no: int, slot: int, slots: int, dpi: int) -> "fitz.Pixmap":
    """
    페이지를 세로로 slots 등분해 slot번째 구역을 렌더합니다.
    도표가 한 개면 페이지 상단 65%만 잘라 해설 텍스트를 덜어냅니다.
    """
    page = doc[page_no - 1]
    r = page.rect
    if slots <= 1:
        clip = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + r.height * 0.65)
    else:
        h = r.height / slots
        clip = fitz.Rect(r.x0, r.y0 + h * slot, r.x1, r.y0 + h * (slot + 1))
    return page.get_pixmap(dpi=dpi, clip=clip)


def extract_embedded(doc, page_no: int) -> list[dict]:
    page = doc[page_no - 1]
    out = []
    for info in page.get_images(full=True):
        base = doc.extract_image(info[0])
        if base["width"] < MIN_PX or base["height"] < MIN_PX:
            continue
        out.append(base)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="도표 이미지 추출")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--mode", choices=["render", "embedded"], default="render")
    ap.add_argument("--dpi", type=int, default=150)
    a = ap.parse_args()

    src = INTERIM / f"{a.source_id}_standards.jsonl"
    if not src.exists():
        raise SystemExit(f"{src} 가 없습니다. parse_pdf.py extract 를 먼저 실행하세요.")

    rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
    doc = fitz.open(a.pdf)
    IMAGES.mkdir(parents=True, exist_ok=True)

    # 같은 페이지에 실린 도표들을 묶어 순번을 매깁니다.
    by_page: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("source_page"):
            by_page[r["source_page"]].append(r)

    saved = failed = 0
    for page_no, group in sorted(by_page.items()):
        group.sort(key=lambda r: r["diagram_no"])
        for slot, r in enumerate(group):
            dest = IMAGES / f"{r['standard_id']}.png"
            try:
                if a.mode == "embedded":
                    imgs = extract_embedded(doc, page_no)
                    if not imgs:
                        raise ValueError("임베드 이미지 없음")
                    big = max(imgs, key=lambda b: b["width"] * b["height"])
                    dest = IMAGES / f"{r['standard_id']}.{big['ext']}"
                    dest.write_bytes(big["image"])
                else:
                    pix = render_clip(doc, page_no, slot, len(group), a.dpi)
                    pix.save(dest)
                r["diagram_image"] = f"images/{dest.name}"
                saved += 1
            except Exception as exc:  # noqa: BLE001
                r["diagram_image"] = None
                failed += 1
                if failed <= 3:
                    print(f"  실패 {r['standard_id']} p.{page_no}: {exc}")

    with src.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    다중 = sum(1 for g in by_page.values() if len(g) > 1)
    print(f"[{a.source_id}] 이미지 {saved}개 저장 / 실패 {failed} → {IMAGES}")
    print(f"  같은 쪽에 도표 2개 이상인 페이지 : {다중}  (세로 분할로 처리)")
    print(f"  {src.name} 의 diagram_image 갱신 완료")



if __name__ == "__main__":
    main()