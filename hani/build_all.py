"""
전체 재생성 — 파서 5종 → 청킹 → 임베딩 → Chroma 를 한 번에.

    python build_all.py

PDF 파일명이 다르면 아래 PDFS 딕셔너리만 고치면 됩니다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "pdf" if (ROOT / "pdf").exists() else ROOT.parent / "pdf"

PDFS = {
    "MAIN2023": "230630_자동차사고 과실비율 인정기준_최종.pdf",
    "PM2021": "!!210624_PM대자동차사고과실비율비정형기준_송부(2021).pdf",
    "ROUND2025": "250624_2차로형 회전교차로사고 과실비율 비정형기준.pdf",
    "CASES": "(최종)과실비율심의사례_(54MB).pdf",
    "ROADLAW": "도로교통법_법률__제21246호__20260701_.pdf",
}


def run(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run([sys.executable, *args], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"실패: {' '.join(args)}")


def find(name: str) -> Path:
    p = PDF_DIR / name
    if p.exists():
        return p
    # 파일명이 조금 달라도 찾아봅니다.
    key = name.split("_")[0][:8]
    for c in PDF_DIR.glob("*.pdf"):
        if key in c.name:
            return c
    raise SystemExit(f"PDF를 찾을 수 없습니다: {name}\n  pdf/ 안의 파일: "
                     + ", ".join(c.name for c in PDF_DIR.glob('*.pdf')))


def main() -> None:
    for sid in ("MAIN2023", "PM2021", "ROUND2025"):
        run(["parse_pdf.py", "extract", str(find(PDFS[sid])), "--source-id", sid])
    run(["parse_cases.py", str(find(PDFS["CASES"]))])
    run(["parse_law.py", str(find(PDFS["ROADLAW"]))])
    run(["build_chunks.py"])
    run(["build_vector.py"])
    print("\n완료. 검색 확인:")
    print('  python search.py "회전교차로 진입하다 사고"')


if __name__ == "__main__":
    main()