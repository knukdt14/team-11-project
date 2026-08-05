"""
hani 산출물(payloads.json)을 백엔드 없이 직접 읽는 헬퍼.

통계 페이지·지식베이스 탐색 페이지처럼 "검색"이 아니라 "전체 집계/열람"이
필요한 화면에서 씁니다. 상담 흐름은 `api.py`(taek.search 경유)를 그대로 쓰세요 —
여기는 그 아래 원본 데이터를 직접 들여다보는 보조 경로입니다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from taek.paths import PAYLOAD  # noqa: E402

SOURCE_LABELS = {
    "MAIN2023": "인정기준(2023)",
    "PM2021": "PM 비정형기준(2021)",
    "ROUND2025": "회전교차로 비정형기준(2025)",
    "CASES": "심의사례",
    "ROADLAW": "도로교통법",
}


@st.cache_data(show_spinner=False)
def load_payloads() -> dict[str, dict]:
    if not PAYLOAD.exists():
        return {}
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def standards() -> list[dict]:
    """kind == 'standard' (기준 도표)만."""
    return [v for v in load_payloads().values() if v.get("kind") == "standard"]


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id)
