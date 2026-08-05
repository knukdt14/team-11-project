"""
백엔드 호출 모음.

3번(정우렬)의 FastAPI(`ryeol/app/`)가 이제 올라왔습니다. 실제 계약은 이렇습니다
(README 초안의 `/consult` 요청 스키마와는 필드명이 다릅니다 — `ryeol/app/schemas.py`
`ryeol/app/service.py` 가 진짜 소스입니다):

    POST /consult
      요청: {"사고설명": str, "상담자측": "A"|"B", "적용할_수정요소": [id,...], "session_id": str|None}
      응답: {"session_id", "status": "complete"|"needs_information"|"not_found", ...}
      → 세션 기반입니다. 첫 상담에서 받은 session_id를 재계산/추가정보/후속질문에 계속 씁니다.

    POST /recalculate    {"session_id", "적용할_수정요소": [id,...]}
    POST /consult/additional-info   {"session_id", "추가정보", "적용할_수정요소"}
    POST /follow-up       {"session_id", "질문"}   ← 진짜 LLM 답변(답변 필드)

    수정요소는 인덱스가 아니라 **문자열 id**로 가리킵니다 (예: "MAIN2023-차41-1-M01").

여기서는 두 경로를 둡니다.

    backend_available()  True  → 위 실제 FastAPI 호출
                         False → hani/taek 를 직접 import 해서 로컬로 흉내(폴백)

로컬 폴백은 검색·A/B 변환·판례/법령 카드를 2번의 `taek.adapter`로 만들기 때문에
필드 모양이 실제 백엔드와 거의 같습니다. 다만:
  · 세션이 진짜로 서버에 저장되지 않습니다 (recalculate는 그때그때 직접 재계산).
  · `추가정보 확인 로직`(무엇을 더 물어볼지 판단)은 `ryeol/app/service.py` 안에만 있어서
    로컬 폴백은 이걸 못 하고 늘 "complete" 아니면 "not_found"만 냅니다.
  · `답변`(LLM 설명문)이 없습니다 — 대신 정형 문구를 씁니다.
두 경로 모두 페이지 코드가 동일한 모양(`consult()`/`recalculate()`의 반환값)을 받도록
이 파일 안에서 정규화합니다.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import requests
import streamlit as st

# woo/pages/*.py 에서 실행돼도 저장소 루트(hani, taek)를 import 할 수 있도록.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ⚠️ 로컬 개발 PC에 따라 8000번 포트가 Docker Desktop/WSL 등 무관한 프로세스와 겹칠 수
#    있습니다(실제로 이 프로젝트 개발 중 발견). 그럴 땐 실행 시 BACKEND_URL 환경변수로
#    다른 포트를 지정하세요 (예: `uvicorn ryeol.app.main:app --port 8010`).
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
_TIMEOUT = 2.0
# 백엔드(ryeol/app/config.py)의 LLM_TIMEOUT 기본값이 180초입니다 — 우리 쪽 요청
# 타임아웃이 그보다 짧으면(예전엔 60초였음) Qwen이 아직 답변 중인데 우리가 먼저
# 포기해서 "Read timed out"이 뜹니다(실제로 후속질문에서 발생 확인). 여유를 두고 넉넉히.
_LLM_TIMEOUT = 200
_LOCAL_SESSION_ID = "local-session"  # 로컬 폴백은 진짜 세션이 없어 recalculate 분기용 표식만.


# ──────────────────────────────────────────────────────────────────
# 백엔드 상태
# ──────────────────────────────────────────────────────────────────


@st.cache_data(ttl=10)
def backend_available() -> bool:
    """/health 가 응답하면 실제 백엔드를 씁니다. 안 되면 로컬 폴백."""
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=_TIMEOUT)
        return r.ok
    except requests.RequestException:
        return False


@st.cache_data(ttl=10)
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


@st.cache_resource(show_spinner="검색 엔진 로딩 중... (최초 1회, 임베딩 모델 내려받기 포함)")
def _local_searcher():
    from taek.search import Searcher

    return Searcher()


_warmup_started = threading.Event()


def warm_up_search_engine() -> None:
    """
    서버 프로세스가 뜨자마자 백그라운드 스레드에서 검색엔진 + 리랭킹 모델을 미리 불러옵니다.

    `_local_searcher()`는 `st.cache_resource`라 서버 전체에서 딱 한 번만 만들어지고
    모든 세션이 공유합니다. 그래서 아무도 미리 안 데워두면 "서버 켜진 뒤 첫 검색자"가
    rerank 모델 로딩(수십 초)을 그대로 떠안습니다 — 발표 중 첫 질문에서 이 지연을
    보여주는 걸 피하려고, 앱이 열리자마자(모듈 import 시점) 미리 한 번 돌려둡니다.

    이 함수 자체는 여러 세션이 동시에 페이지를 열어도 딱 한 번만 스레드를 띄웁니다
    (threading.Event로 가드). 워밍업이 실패해도 조용히 넘어갑니다 — 실제 사용자가
    검색할 때 정상 경로로 다시 시도되므로 앱 동작에는 지장이 없습니다.
    """
    if _warmup_started.is_set():
        return
    _warmup_started.set()

    def _run() -> None:
        try:
            searcher = _local_searcher()
            searcher.search("워밍업", top_k=1, mode="hybrid", expand=True, rerank=True)
        except Exception:  # noqa: BLE001 — 워밍업 실패는 무시. 본 검색에서 다시 시도됨.
            pass

    threading.Thread(target=_run, daemon=True, name="search-warmup").start()


# 이 모듈이 처음 import되는 순간(=서버 프로세스가 이 앱을 처음 로드하는 순간) 실행됩니다.
# app.py든 pages/*.py든 어느 페이지로 먼저 들어와도 전부 이 모듈을 import하므로 보장됩니다.
warm_up_search_engine()


def _search_with_selective_rerank(searcher, query: str):
    """
    hybrid 1차 검색(빠름) → 1위·2위 점수차가 작아 애매할 때만 rerank(느림, 정확)로 재검색.

    rerank(cross-encoder 정밀 재정렬)는 정확하지만 CPU에서 질문당 ~7초가 듭니다 — 매번
    걸면 상담이 느려지니 이 함수에서 애매한 경우만 골라냅니다. 실측: "야간에 뒤에서 오던
    차가 제 차를 추돌했어요" → 1위(자전거 추돌) vs 2위 점수차 0.03으로 애매 → rerank하면
    자동차 추돌로 정정됨. 명확한 질문은 점수차가 보통 0.3~0.5 이상이라 대부분 이 단계를
    안 타고 빠르게 끝납니다(0.1~0.3초).
    """
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
    """
    apply_modifiers() 임시 대역. 대상=A 는 '나', B 는 '상대'. 수정요소는 id로 골라 적용합니다.
    한쪽이 오르면 합이 100이 되도록 반대쪽을 그만큼 내립니다.
    """
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
    """
    hani/taek 로컬 검색 결과를 실제 `/consult` 응답 계약(`ryeol/app/schemas.py`)과
    최대한 같은 모양으로 만듭니다.

    검색·A/B 변환·판례/법령/사고유형 변환은 2번이 만든 `taek.adapter`를 그대로 씁니다.
    """
    from taek.adapter import to_case_cards, to_consult_payload, to_law_cards

    searcher = _local_searcher()
    # mode="hybrid" + reject=True: 2번의 EVAL.md 기준 최고 성능 조합.
    # reject=True 면 벡터·BM25 둘 다 약할 때 빈 리스트를 돌려줘서 "not_found"로 넘어갑니다
    # (README §10-6 "기준에 없으면 추측 금지" 요구사항과 정확히 맞물림).
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

    # 실제 백엔드(service.py)와 동일한 필드 이름으로 채웁니다:
    #   유사사례 = 검색된 심의사례 카드(rich dict), 판례 = 도표 자체의 참조 판례 문자열 목록
    #   (adapter._diagram()이 이미 채워둠 — 여기서 덮어쓰지 않습니다).
    #   법조항 = 법령 카드(rich dict) — adapter가 준 문자열 목록을 rich dict로 교체.
    법조항_히트 = searcher.laws_for(top_kb.get("laws", []))
    유사사례_히트 = searcher.cases(query, top_k=3)
    payload["법조항"] = to_law_cards(법조항_히트)
    payload["유사사례"] = to_case_cards(유사사례_히트)

    # image_url(adapter)은 백엔드가 StaticFiles로 서빙할 때 쓸 URL이라 로컬에선 파일을 못 엽니다.
    # 로컬 폴백에서는 원본 payload의 image_path(hani/data/ 기준 상대경로)를 그대로 씁니다.
    payload["image_path"] = top_kb.get("image_path")
    payload["pdf_page"] = top_kb.get("source_page")
    payload["검수필요"] = bool(top_kb.get("parse_flags"))
    payload["신뢰도"] = "낮음" if payload["검수필요"] else "높음"

    # ⚠️ "자동차 vs 자동차"류 도표(차대차)는 나_역할/상대_역할만으로는 어느 쪽이 나인지
    # 전혀 구분이 안 됩니다 (예: 후방추돌 도표는 A=뒤차 100% 과실, B=앞차 0% 과실인데
    # 둘 다 "자동차"로만 뜨면 사용자가 반대쪽을 골라 정반대 결과를 받는 사고가 납니다 —
    # 실제로 "뒤에서 추돌당했다"는 질문에 기본값 A(=뒤차, 가해자)를 그대로 골라 100%가
    # 나온 사례로 발견됨). party_a/party_b(도표별 구체 설명, 예: "뒤차(후행) 추돌")를
    # consultant_side에 맞춰 뒤집어서 안내문에 노출시켜 어느 쪽인지 명확히 구분시킵니다.
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

    # 로컬 폴백은 apply_modifiers()가 없으니 여기서 바로 계산해서
    # 실제 백엔드처럼 최종과실/계산_단계/적용_수정요소/미적용_수정요소까지 채웁니다.
    최종과실, 계산_단계 = _local_recalculate(payload["기본과실"], payload["수정요소"], set())
    payload["최종과실"] = 최종과실
    payload["계산_단계"] = 계산_단계
    payload["적용_수정요소"] = []
    payload["미적용_수정요소"] = list(payload["수정요소"])

    # adapter의 _diagram()엔 없는 필드 — 화면(구간 표시, 수정요소 해설 탭)에 필요해서 보강.
    payload["구간"] = top_kb.get("section", "")
    payload["수정요소_해설"] = top_kb.get("modifier_explanation", "")
    payload["되묻기"] = []
    return payload


def _local_additional_info(result: dict, extra_info: str) -> dict:
    """추가정보를 덧붙여 다시 상담(로컬 폴백). 실제 백엔드의 되묻기 판단 로직은 없어서
    그냥 재검색만 합니다 — `ryeol/app/service.py`의 `_missing_information()`처럼 정교하진
    않지만, 문장을 보강해서 재검색하면 대체로 더 나은 결과가 나옵니다."""
    merged = f"{result.get('사고상황') or result.get('질문', '')} {extra_info}".strip()
    new_result = _local_consult(merged, result.get("상담자측", "A"))
    new_result["질문"] = merged
    return new_result


# ──────────────────────────────────────────────────────────────────
# 공개 API — 페이지에서는 이 함수들만 부릅니다
# ──────────────────────────────────────────────────────────────────


def _normalize_backend_response(result: dict) -> dict:
    """
    실제 백엔드는 수정요소를 `적용_수정요소`/`미적용_수정요소`로 나눠서 줍니다.
    로컬 폴백은 하나의 `수정요소` 리스트(전부 미적용 상태)로 시작합니다.
    페이지 코드가 소스에 상관없이 `result["수정요소"]` 하나만 보면 되도록 여기서 합칩니다
    (토글 상태 자체는 `st.session_state["applied_mods"]`가 따로 관리하므로, 여기서의
    `적용됨` 값은 "마지막 서버 계산 시점" 스냅샷일 뿐 — 화면 로직은 이 값을 안 씁니다).
    """
    if "수정요소" not in result:
        result["수정요소"] = [
            *result.get("적용_수정요소", []),
            *result.get("미적용_수정요소", []),
        ]
    return result


def _enrich_guidance(result: dict, consultant_side: str) -> dict:
    """
    ⚠️ 실제 백엔드(`ryeol/app/schemas.py`)의 `ConsultResponse`엔 `party_a`/`party_b`가
    없어서 "안내문"을 못 만듭니다 — 그러면 차대차 후방추돌처럼 나_역할/상대_역할이
    둘 다 "자동차"인 도표에서 사용자가 어느 쪽인지 구분 못 해 반대쪽을 고르는 사고가
    재발합니다(이 프로젝트에서 실제로 한 번 발견된 문제). 계산에는 관여하지 않는
    순수 표시용 정보라서, hani 원본 payload에서 party_a/party_b를 직접 찾아 여기서
    보강합니다 — 백엔드 계산 결과(기본과실/최종과실 등)는 절대 건드리지 않습니다.
    """
    if result.get("status") != "complete" or not result.get("도표번호") or not result.get("출처"):
        return result
    try:
        from woo.components.kb_data import load_payloads

        standard_id = f"{result['출처']}-{result['도표번호']}"
        top_kb = load_payloads().get(standard_id, {})
    except Exception:  # noqa: BLE001 — 안내문은 부가정보라 실패해도 상담 자체는 계속되게.
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
            st.warning(f"백엔드 호출 실패, 로컬 폴백으로 전환합니다: {e}")
    result = _local_consult(query, consultant_side)
    result["상담자측"] = consultant_side
    return result


def additional_info(result: dict, extra_info: str) -> dict:
    """되묻기(추가정보)에 답한 뒤 다시 상담."""
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
            st.warning(f"백엔드 호출 실패, 로컬 폴백으로 전환합니다: {e}")
    new_result = _local_additional_info(result, extra_info)
    new_result["상담자측"] = result.get("상담자측", "A")
    return new_result


def follow_up_chat(result: dict, question: str) -> str:
    """상담 결과를 보고 후속 질문(반박·추가 질문)에 답합니다. 실제 백엔드는 LLM(Qwen)
    답변을, 로컬 폴백은 정형 안내 문구를 돌려줍니다."""
    if result.get("백엔드_사용") and backend_available():
        try:
            r = requests.post(
                f"{BACKEND_URL}/follow-up",
                json={"session_id": result["session_id"], "질문": question},
                timeout=_LLM_TIMEOUT,
            )
            r.raise_for_status()
            return r.json().get("답변", "")
        except requests.RequestException as e:
            return f"⚠️ 백엔드 호출 실패: {e}"
    return (
        "지금은 로컬 검색 모드라 실제 LLM 답변 대신 안내만 드려요. "
        "말씀하신 내용을 반영하려면 위 입력창에 다시 자세히 적어서 '상담 시작'을 눌러주세요."
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
