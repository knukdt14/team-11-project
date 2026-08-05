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
    title = context.get("제목") or context.get("도표번호") or "검색된 기준"
    return (
        f"{title}을 근거로 계산했습니다. 예상 과실은 본인 {ratio.get('A')}%, "
        f"상대 {ratio.get('B')}%입니다. 실제 판단은 추가 사실과 증거에 따라 달라질 수 있습니다."
    )


def _prompt(context: dict[str, Any]) -> str:
    return (
        "교통사고 과실비율 상담 보조자입니다. 아래 JSON의 사실과 근거만 사용하세요. "
        "숫자를 새로 계산하거나 법령·판례를 만들지 말고 최종과실을 그대로 설명하세요. "
        "실제 판단은 증거와 사실에 따라 달라질 수 있음을 명시하세요.\n"
        + json.dumps(context, ensure_ascii=False)
    )


def _gemini(prompt: str) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    response = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
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
