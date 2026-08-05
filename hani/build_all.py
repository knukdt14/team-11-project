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
    # 파일명이 조금씩 달라서 아래 KEYWORDS 로 찾습니다.
    "ROADLAW": "도로교통법",
}


def run(args: list[str]) -> None:
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run([sys.executable, *args], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"실패: {' '.join(args)}")


# 파일명 대신 이 키워드로 PDF를 찾습니다(파일명이 팀원마다 달라도 동작).
KEYWORDS = {
    "MAIN2023": ["인정기준"],
    "PM2021": ["PM대자동차", "PM"],
    "ROUND2025": ["회전교차로"],
    "CASES": ["심의사례"],
    "ROADLAW": ["도로교통법"],
}


def find(sid: str) -> Path:
    exact = PDF_DIR / PDFS[sid]
    if exact.exists():
        return exact
    for kw in KEYWORDS[sid]:
        for c in sorted(PDF_DIR.glob("*.pdf")):
            if kw in c.name:
                return c
    raise SystemExit(f"PDF를 찾을 수 없습니다: {name}\n  pdf/ 안의 파일: "
                     + ", ".join(c.name for c in PDF_DIR.glob('*.pdf')))


def main() -> None:
    for sid in ("MAIN2023", "PM2021", "ROUND2025"):
        run(["parse_pdf.py", "extract", str(find(sid)), "--source-id", sid])
        run(["extract_images.py", str(find(sid)), "--source-id", sid])
    run(["parse_cases.py", str(find("CASES"))])
    run(["parse_law.py", str(find("ROADLAW"))])
    run(["build_chunks.py"])
    run(["build_vector.py"])
    print("\n완료. 검색 확인:")
    print('  cd .. && python -m taek.search "회전교차로 진입하다 사고"')


if __name__ == "__main__":
    main()