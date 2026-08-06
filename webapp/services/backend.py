"""
백엔드 호출 모음 — `woo/components/api.py`의 프레임워크 독립 버전.

Streamlit 전용 API(`st.cache_data`, `st.cache_resource`, `st.warning`)를 걷어내고
순수 파이썬 캐시/로깅으로 바꾼 것 말고는 로직이 동일합니다. 3번(정우렬)의 FastAPI
(`ryeol/app/`) 계약은 이렇습니다:

    POST /consult
      요청: {"사고설명": str, "상담자측": "A"|"B", "적용할_수정요소": [id,...], "session_id": str|None}
      응답: {"session_id", "status": "complete"|"needs_information"|"not_found", ...}

    POST /recalculate    {"session_id", "적용할_수정요소": [id,...]}
    POST /consult/additional-info   {"session_id", "추가정보", "적용할_수정요소"}
    POST /follow-up       {"session_id", "질문"}   ← 실제 LLM 답변(답변 필드)

    수정요소는 인덱스가 아니라 문자열 id로 가리킵니다 (예: "MAIN2023-차41-1-M01").

backend_available() 이 True면 위 실제 FastAPI를 호출하고, False면 hani/taek를 직접
import해서 로컬로 흉내(폴백)합니다. 두 경로 모두 동일한 응답 모양으로 정규화합니다.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_local_env() -> None:
    """`webapp/.env`(커밋 안 됨)가 있으면 읽어서 os.environ 기본값으로 채웁니다."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
_TIMEOUT = 2.0
_LLM_TIMEOUT = 200
_LOCAL_SESSION_ID = "local-session"


# ──────────────────────────────────────────────────────────────────
# 간단한 TTL 캐시 / 지연 싱글턴 (st.cache_data / st.cache_resource 대체)
# ──────────────────────────────────────────────────────────────────


def _ttl_cache(ttl_seconds: float):
    """인자 없는 함수용 초간단 TTL 캐시 데코레이터."""

    def deco(fn):
        state: dict[str, Any] = {"value": None, "at": 0.0}

        def wrapper():
            now = time.monotonic()
            if state["value"] is None or (now - state["at"]) > ttl_seconds:
                state["value"] = fn()
                state["at"] = now
            return state["value"]

        return wrapper

    return deco


def _lazy_singleton(fn):
    """인자 없는 함수의 결과를 최초 1회만 계산해서 재사용 (스레드 안전)."""
    lock = threading.Lock()
    state: dict[str, Any] = {}

    def wrapper():
        if "value" not in state:
            with lock:
                if "value" not in state:
                    state["value"] = fn()
        return state["value"]

    return wrapper


# ──────────────────────────────────────────────────────────────────
# 백엔드 상태
# ──────────────────────────────────────────────────────────────────


@_ttl_cache(10)
def backend_available() -> bool:
    """/health 가 응답하면 실제 백엔드를 씁니다. 안 되면 로컬 폴백."""
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=_TIMEOUT)
        return r.ok
    except requests.RequestException:
        return False


@_ttl_cache(10)
def health_info() -> dict[str, Any]:
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return {}


# ──────────────────────────────────────────────────────────────────
# 로컬 폴백 — hani/taek 직접 호출
# ──────────────────────────────────────────────────────────────────


@_lazy_singleton
def _local_searcher():
    from taek.search import Searcher

    return Searcher()


_warmup_started = threading.Event()


def warm_up_search_engine() -> None:
    """서버 프로세스가 뜨자마자 백그라운드 스레드에서 검색엔진 + 리랭킹 모델을 미리 불러옵니다."""
    if _warmup_started.is_set():
        return
    _warmup_started.set()

    def _run() -> None:
        try:
            searcher = _local_searcher()
            searcher.search("워밍업", top_k=1, mode="hybrid", expand=True, rerank=True)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_run, daemon=True, name="search-warmup").start()


warm_up_search_engine()


def _search_with_selective_rerank(searcher, query: str):
    """hybrid 1차 검색(빠름) → 1위·2위 점수차가 작아 애매할 때만 rerank(느림, 정확)."""
    t0 = time.perf_counter()
    hits = searcher.search(query, top_k=5, mode="hybrid", expand=True, reject=True)
    trace = [
        {
            "step": 1,
            "tool": "search_kb (hybrid, 로컬 폴백)",
            "결과": f"{len(hits)}건",
            "소요ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    ]

    AMBIGUOUS_MARGIN = 0.15
    if len(hits) >= 2 and (hits[0].score - hits[1].score) < AMBIGUOUS_MARGIN:
        t1 = time.perf_counter()
        hits = searcher.search(query, top_k=5, mode="hybrid", expand=True, reject=True, rerank=True)
        trace.append(
            {
                "step": 2,
                "tool": "rerank (1·2위 점수차 작아 정밀 재정렬)",
                "결과": f"{len(hits)}건",
                "소요ms": round((time.perf_counter() - t1) * 1000, 1),
            }
        )
    return hits, trace


def _local_recalculate(기본과실: dict, 수정요소: list[dict], applied_ids: set[str]) -> tuple[dict, list[dict]]:
    a = 기본과실["A"]
    계산_단계 = [{"라벨": "기본과실", "값": a}]
    for m in 수정요소:
        if m["id"] not in applied_ids:
            continue
        delta = m["값"] if m["대상"] == "A" else -m["값"]
        a = max(0, min(100, a + delta))
        부호 = f"+{m['값']}" if m["값"] >= 0 else str(m["값"])
        계산_단계.append({"라벨": f"{m['조건']} {부호}", "값": a})
    최종 = {"A": a, "B": 100 - a}
    return 최종, 계산_단계


def _local_consult(query: str, consultant_side: str) -> dict:
    from taek.adapter import to_case_cards, to_consult_payload, to_law_cards

    searcher = _local_searcher()
    hits, trace = _search_with_selective_rerank(searcher, query)

    payload = to_consult_payload(hits, consultant_side=consultant_side, top_k=4)
    payload["session_id"] = _LOCAL_SESSION_ID
    payload["status"] = "not_found" if payload["경고"] else "complete"
    payload["trace"] = trace
    payload["백엔드_사용"] = False
    payload["신뢰도"] = "낮음"
    payload["답변"] = ""

    if payload["status"] != "complete":
        return payload

    top_kb = next(h.payload for h in hits if h.kind == "standard")
    trace.append(
        {"step": len(trace) + 1, "tool": "to_consult_payload (로컬)", "결과": payload["나_역할"], "소요ms": 0.1}
    )

    법조항_히트 = searcher.laws_for(top_kb.get("laws", []))
    유사사례_히트 = searcher.cases(query, top_k=3)
    payload["법조항"] = to_law_cards(법조항_히트)
    payload["유사사례"] = to_case_cards(유사사례_히트)

    payload["image_path"] = top_kb.get("image_path")
    payload["pdf_page"] = top_kb.get("source_page")
    payload["검수필요"] = bool(top_kb.get("parse_flags"))
    payload["신뢰도"] = "낮음" if payload["검수필요"] else "높음"

    party_a = top_kb.get("party_a", "")
    party_b = top_kb.get("party_b", "")
    나_설명, 상대_설명 = (party_a, party_b) if consultant_side == "A" else (party_b, party_a)
    payload["나_설명"] = 나_설명
    payload["상대_설명"] = 상대_설명
    if 나_설명 or 상대_설명:
        payload["안내문"] = (
            f"나({payload['나_역할']}): {나_설명 or '해당 없음'}  ·  "
            f"상대({payload['상대_역할']}): {상대_설명 or '해당 없음'}  — 내 상황과 맞는지 확인해주세요."
        )
    else:
        payload["안내문"] = f"{payload['나_역할']} vs {payload['상대_역할']} — 본인이 어느 쪽인지 확인해주세요."

    최종과실, 계산_단계 = _local_recalculate(payload["기본과실"], payload["수정요소"], set())
    payload["최종과실"] = 최종과실
    payload["계산_단계"] = 계산_단계
    payload["적용_수정요소"] = []
    payload["미적용_수정요소"] = list(payload["수정요소"])

    payload["구간"] = top_kb.get("section", "")
    payload["수정요소_해설"] = top_kb.get("modifier_explanation", "")
    payload["되묻기"] = []
    return payload


def _local_additional_info(result: dict, extra_info: str) -> dict:
    merged = f"{result.get('사고상황') or result.get('질문', '')} {extra_info}".strip()
    new_result = _local_consult(merged, result.get("상담자측", "A"))
    new_result["질문"] = merged
    return new_result


# ──────────────────────────────────────────────────────────────────
# 공개 API — 페이지에서는 이 함수들만 부릅니다
# ──────────────────────────────────────────────────────────────────


def _normalize_backend_response(result: dict) -> dict:
    if "수정요소" not in result:
        result["수정요소"] = [
            *result.get("적용_수정요소", []),
            *result.get("미적용_수정요소", []),
        ]
    return result


def _enrich_guidance(result: dict, consultant_side: str) -> dict:
    if result.get("status") != "complete" or not result.get("도표번호") or not result.get("출처"):
        return result
    try:
        from webapp.services.kb_data import load_payloads

        standard_id = f"{result['출처']}-{result['도표번호']}"
        top_kb = load_payloads().get(standard_id, {})
    except Exception:  # noqa: BLE001
        top_kb = {}

    party_a = top_kb.get("party_a", "")
    party_b = top_kb.get("party_b", "")
    나_설명, 상대_설명 = (party_a, party_b) if consultant_side == "A" else (party_b, party_a)
    if 나_설명 or 상대_설명:
        result["안내문"] = (
            f"나({result.get('나_역할')}): {나_설명 or '해당 없음'}  ·  "
            f"상대({result.get('상대_역할')}): {상대_설명 or '해당 없음'}  — 내 상황과 맞는지 확인해주세요."
        )
    else:
        result["안내문"] = f"{result.get('나_역할')} vs {result.get('상대_역할')} — 본인이 어느 쪽인지 확인해주세요."
    return result


def consult(query: str, consultant_side: str = "A") -> dict:
    """상담 시작. 백엔드 있으면 세션 기반 실제 API, 없으면 로컬 폴백."""
    if backend_available():
        try:
            r = requests.post(
                f"{BACKEND_URL}/consult",
                json={
                    "사고설명": query,
                    "상담자측": consultant_side,
                    "적용할_수정요소": [],
                    "session_id": None,
                },
                timeout=_LLM_TIMEOUT,
            )
            r.raise_for_status()
            result = r.json()
            result["백엔드_사용"] = True
            result["상담자측"] = consultant_side
            result["질문"] = query
            result = _normalize_backend_response(result)
            return _enrich_guidance(result, consultant_side)
        except requests.RequestException as e:
            logger.warning("백엔드 호출 실패, 로컬 폴백으로 전환합니다: %s", e)
    result = _local_consult(query, consultant_side)
    result["상담자측"] = consultant_side
    return result


def additional_info(result: dict, extra_info: str) -> dict:
    if result.get("백엔드_사용") and backend_available():
        try:
            r = requests.post(
                f"{BACKEND_URL}/consult/additional-info",
                json={
                    "session_id": result["session_id"],
                    "추가정보": extra_info,
                    "적용할_수정요소": [],
                },
                timeout=_LLM_TIMEOUT,
            )
            r.raise_for_status()
            new_result = r.json()
            new_result["백엔드_사용"] = True
            side = result.get("상담자측", "A")
            new_result["상담자측"] = side
            new_result = _normalize_backend_response(new_result)
            return _enrich_guidance(new_result, side)
        except requests.RequestException as e:
            logger.warning("백엔드 호출 실패, 로컬 폴백으로 전환합니다: %s", e)
    new_result = _local_additional_info(result, extra_info)
    new_result["상담자측"] = result.get("상담자측", "A")
    return new_result


def follow_up_chat(result: dict, question: str) -> tuple[str, list[str]]:
    """반환값 (답변, warnings)."""
    if result.get("백엔드_사용") and backend_available():
        try:
            r = requests.post(
                f"{BACKEND_URL}/follow-up",
                json={"session_id": result["session_id"], "질문": question},
                timeout=_LLM_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("답변", ""), data.get("warnings", [])
        except requests.RequestException as e:
            return f"⚠️ 백엔드 호출 실패: {e}", []
    return (
        "지금은 로컬 검색 모드라 실제 LLM 답변 대신 안내만 드려요. "
        "말씀하신 내용을 반영하려면 위 입력창에 다시 자세히 적어서 '상담 시작'을 눌러주세요.",
        [],
    )


def recalculate(result: dict, applied_ids: set[str]) -> tuple[dict, list[dict]]:
    """수정요소 토글 즉시 재계산."""
    if result.get("백엔드_사용") and backend_available():
        try:
            r = requests.post(
                f"{BACKEND_URL}/recalculate",
                json={"session_id": result["session_id"], "적용할_수정요소": sorted(applied_ids)},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return data["최종과실"], data["계산_단계"]
        except requests.RequestException:
            pass
    return _local_recalculate(result["기본과실"], result["수정요소"], applied_ids)
