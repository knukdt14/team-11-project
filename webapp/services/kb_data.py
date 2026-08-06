"""hani 산출물(payloads.json)을 백엔드 없이 직접 읽는 헬퍼 — `woo/components/kb_data.py`의
프레임워크 독립 버전."""

from __future__ import annotations

import json
import sys
from pathlib import Path

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

_cache: dict[str, dict] | None = None


def load_payloads() -> dict[str, dict]:
    global _cache
    if _cache is None:
        _cache = json.loads(PAYLOAD.read_text(encoding="utf-8")) if PAYLOAD.exists() else {}
    return _cache


def standards() -> list[dict]:
    return [v for v in load_payloads().values() if v.get("kind") == "standard"]


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id)
