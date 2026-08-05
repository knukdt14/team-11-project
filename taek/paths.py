"""
경로 단일 소스.

⚠️ **데이터는 `hani/data/` 에 있고 코드는 `taek/` 에 있습니다.**
   1번(데이터 파이프라인)이 만든 산출물을 2번(검색)이 읽는 구조입니다.
   경로를 각 모듈에 흩어 두면 폴더를 옮길 때마다 여기저기 깨지므로 이 파일에만 둡니다.

   데이터를 옮기거나 폴더 이름을 바꾸면 **여기 한 곳만** 고치세요.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAEK = Path(__file__).resolve().parent

# ── 1번 산출물 (읽기 전용) ─────────────────────────────────────────
PROCESSED = REPO / "hani" / "data" / "processed"
CHUNKS = PROCESSED / "chunks.jsonl"
PAYLOAD = PROCESSED / "payloads.json"
VECTOR_DIR = PROCESSED / "vector_index"

# ── 2번 산출물 ────────────────────────────────────────────────────
GOLD = TAEK / "gold_queries.csv"
RESULTS = TAEK / "results"

COLLECTION = "fault_ratio"
