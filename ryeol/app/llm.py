from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

import requests

from .config import settings

logger = logging.getLogger(__name__)


def _error_label(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTPError(HTTP {exc.response.status_code})"
    return type(exc).__name__


def _fallback(context: dict[str, Any]) -> str:
    ratio = context.get("최종과실") or {}
    # ⚠️ 후속질문(follow_up)의 context 는 최초상담과 필드 구조가 다릅니다 —
    # 제목/도표번호가 최상위가 아니라 "기존상담" 안에 들어 있습니다. 여기서
    # context.get("제목")만 보면 항상 None이 되어 "검색된 기준"으로 뭉개지고,
    # 무엇보다 "후속질문"(실제로 물어본 내용)을 전혀 안 쳐다봐서 최초 답변과
    # 똑같은 정형 문장이 매번 반복되는 버그가 있었습니다 — 아래에서 두 가지를 고칩니다:
    # (1) 기존상담 안쪽도 뒤져서 제목을 찾고, (2) 후속질문이면 그 질문을 답변에 반영합니다.
    기존상담 = context.get("기존상담") or {}
    title = (
        context.get("제목") or context.get("도표번호")
        or 기존상담.get("제목") or 기존상담.get("도표번호") or "검색된 기준"
    )
    질문 = context.get("후속질문")
    if 질문:
        return (
            f"'{질문}'에 대해 답변드리면, 지금은 AI 설명 모델을 사용할 수 없어 "
            f"자세한 설명 대신 정형 문장으로 안내드립니다. 앞서 안내드린 {title} 기준 "
            f"과실비율(본인 {ratio.get('A')}%, 상대 {ratio.get('B')}%)은 이 질문으로 바뀌지 "
            "않으며, 구체적인 근거는 지식베이스에서 관련 법령·심의사례를 직접 확인해 주세요."
        )
    return (
        f"{title}을 근거로 계산했습니다. 예상 과실은 본인 {ratio.get('A')}%, "
        f"상대 {ratio.get('B')}%입니다. 실제 판단은 추가 사실과 증거에 따라 달라질 수 있습니다."
    )


def _prompt(context: dict[str, Any]) -> str:
    # ⚠️ 후속질문(follow_up)에서 실제 Gemini 응답이 매번 거의 똑같이 나오는 문제가
    # 있었습니다 — 원인은 "정형 fallback 반복" 버그가 아니라 이 프롬프트 자체였습니다.
    # 아래 "질문이 '적용할_수정요소'에 없는 조건(예: 과속, 신호위반)..." 지시문이 너무
    # 강하게 예시를 박아놔서, 실제 후속질문이 과속·신호위반과 전혀 무관해도(예: "주행
    # 방향이 반대입니다") 모델이 그 예시 패턴을 그대로 따라가며 과속/신호위반 얘기를
    # 반복했습니다. 후속질문일 때는 "실제로 물어본 그 질문에 답하라"를 최우선 지시로
    # 명시하고, 과속/신호위반 안내는 "그 질문이 실제로 그런 조건에 대한 것일 때만"
    # 적용되도록 조건을 분리했습니다.
    후속질문 = context.get("후속질문")
    if 후속질문:
        return (
            "당신은 교통사고 과실비율 상담 보조자입니다. 상담자는 이미 과실비율 계산 결과를 "
            "받았고, 지금은 그 결과에 대해 추가로 궁금한 점을 물어보고 있습니다.\n\n"
            f"이번에 반드시 답해야 할 실제 질문은 아래 '후속질문' 필드입니다: \"{후속질문}\"\n"
            "이전에 했던 답변이나 다른 상담에서 쓸 법한 정형 문구를 그대로 반복하지 말고, "
            "이 질문 내용에 맞춰 새롭게, 구체적으로 답하세요. 질문이 사고 상황(진행 방향·"
            "위치 등)에 대한 설명이나 확인이면 그 내용을 이해했다는 걸 답변에 반영하세요.\n\n"
            "'최종과실' 숫자는 JSON에 적힌 값을 그대로 전달하고, 다른 비율을 새로 "
            "계산하거나 만들어내지 마세요. 법령·판례도 JSON에 없는 내용을 지어내지 마세요.\n\n"
            "질문이 '적용할_수정요소'에 등재되지 않은 조건(예: 과속, 신호위반)에 대한 것일 "
            "**때만** 그 조건이 왜 비율에 반영 안 됐는지 짧게 설명하세요. 질문이 그런 내용이 "
            "아니면 이 설명은 하지 마세요.\n\n"
            "2~4문장, 자연스러운 한국어 대화체로 답하고 JSON 필드명을 그대로 베끼지 마세요. "
            "마지막에 실제 판단은 증거와 사실에 따라 달라질 수 있다고 짧게 덧붙이세요.\n\n"
            "참고 데이터: " + json.dumps(context, ensure_ascii=False)
        )
    return (
        "당신은 교통사고 과실비율 상담 보조자입니다. 아래 참고 데이터(JSON)를 보고 "
        "상담자의 질문에 자연스러운 한국어 문장 2~4개로 답하세요. JSON의 필드명이나 "
        "리스트를 그대로 베끼지 말고 실제 대화체로 풀어서 설명하세요.\n\n"
        "'최종과실' 숫자는 JSON에 적힌 값을 그대로 전달하고, 다른 비율을 새로 "
        "계산하거나 만들어내지 마세요. 법령·판례도 JSON에 없는 내용을 지어내지 마세요.\n\n"
        "질문이 '적용할_수정요소'에 없는 조건(예: 과속, 신호위반)에 대한 것이라면, "
        "그 조건이 교통사고에서 보통 어떤 의미를 갖는지는 일반 상식으로 자연스럽게 "
        "설명하되, 이번 사고유형 기준에는 그 조건이 수정요소로 등재되어 있지 않아 "
        "표시된 비율에는 반영되지 않았다는 점을 함께 알려주세요.\n\n"
        "마지막에 실제 판단은 증거와 사실에 따라 달라질 수 있다고 짧게 덧붙이세요.\n\n"
        "참고 데이터: " + json.dumps(context, ensure_ascii=False)
    )


def _gemini(prompt: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    # ⚠️ Google이 API 키를 "Standard"(AIzaSy...)에서 "Auth key"(AQ....)로 전환했습니다
    # (2026-06 이후 AI Studio는 AQ. 키만 발급). Auth key는 서비스 계정에 바인딩돼 있어서
    # 예전처럼 ?key=쿼리파라미터로 보내면 REST 엔드포인트가 인식을 못 하고 404/401을
    # 반환합니다(Google 공식 문서·포럼에도 보고된 이슈: "New API keys generated with
    # 'AQ.' prefix don't work with REST endpoint"). 공식 권장 방식인 x-goog-api-key
    # 헤더로 바꿔야 AQ. 키가 정상 인증됩니다.
    response = requests.post(
        url,
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            # ⚠️ thinkingConfig.thinkingBudget=0으로 "생각 끄기"를 강제하던 부분을
            # 지웠습니다. Gemini 2.5 세대에서는 유효했지만, 새로 라우팅되는 Gemini 3.x
            # 계열(예: gemini-flash-lite-latest → gemini-3.5-flash-lite)에서는 이
            # 값이 거부되어 매 요청이 "400 INVALID_ARGUMENT"로 실패하고 있었습니다
            # (실측 확인됨). 세대별로 유효한 budget 범위가 달라 안전하게 유지보수하기
            # 어려우므로, 아예 안 보내고 모델 기본 동작에 맡깁니다.
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 1024,
            },
        },
        timeout=settings.gemini_timeout,
    )
    response.raise_for_status()
    candidates = response.json().get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "".join(part.get("text", "") for part in parts).strip()
    if not answer:
        raise ValueError("Gemini returned an empty response")
    return answer


def _exaone(prompt: str) -> str:
    response = requests.post(
        f"{settings.ollama_url.rstrip('/')}/api/generate",
        json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 512},
        },
        timeout=settings.ollama_timeout,
    )
    response.raise_for_status()
    answer = response.json().get("response", "").strip()
    if not answer:
        raise ValueError("EXAONE returned an empty response")
    return answer


def explain(context: dict[str, Any]) -> tuple[str, list[str]]:
    """auto mode uses Gemini, then EXAONE, then a deterministic template."""
    prompt = _prompt(context)
    fallback = _fallback(context)
    mode = settings.llm_mode
    warnings: list[str] = []

    if mode == "mock":
        return fallback, ["LLM_MODE=mock: 정형 문장을 사용했습니다."]

    if mode in {"auto", "gemini"}:
        started = perf_counter()
        try:
            answer = _gemini(prompt)
            logger.info("LLM provider=gemini elapsed_seconds=%.2f", perf_counter() - started)
            return answer, warnings
        except Exception as exc:
            label = _error_label(exc)
            logger.warning(
                "LLM provider=gemini failed=%s elapsed_seconds=%.2f",
                label,
                perf_counter() - started,
            )
            warnings.append(f"Gemini 호출 실패로 대체 모델을 사용합니다: {label}")
            if mode == "gemini":
                return fallback, warnings

    if mode in {"auto", "exaone", "ollama"}:
        started = perf_counter()
        try:
            answer = _exaone(prompt)
            logger.info("LLM provider=exaone elapsed_seconds=%.2f", perf_counter() - started)
            return answer, warnings
        except Exception as exc:
            label = _error_label(exc)
            logger.warning(
                "LLM provider=exaone failed=%s elapsed_seconds=%.2f",
                label,
                perf_counter() - started,
            )
            warnings.append(f"EXAONE 호출 실패로 정형 문장을 사용했습니다: {label}")
            return fallback, warnings

    return fallback, [f"지원하지 않는 LLM_MODE입니다: {mode}"]
