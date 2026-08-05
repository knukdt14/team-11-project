import json
import requests
from .config import settings

def _fallback(context: dict) -> str:
    ratio = context.get("최종과실") or {}
    title = context.get("제목") or context.get("도표번호") or "검색된 기준"
    return (f"{title}을 근거로 계산했습니다. 예상 과실은 본인 {ratio.get('A')}%, "
            f"상대 {ratio.get('B')}%입니다. 실제 판단은 추가 사실과 증거에 따라 달라질 수 있습니다.")

def explain(context: dict):
    if settings.llm_mode == "mock":
        return _fallback(context), ["LLM_MODE=mock: 정형 문장을 사용했습니다."]
    prompt = ("교통사고 과실비율 상담 보조자입니다. 아래 JSON의 사실만 사용하세요. "
              "숫자를 계산하거나 법령·판례를 만들지 말고 최종과실을 그대로 설명하세요. "
              "실제 판단은 증거와 사실에 따라 달라질 수 있음을 명시하세요.\n" +
              json.dumps(context, ensure_ascii=False))
    try:
        response = requests.post(f"{settings.ollama_url.rstrip('/')}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False,
                  "keep_alive": -1, "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 512}},
            timeout=settings.llm_timeout)
        response.raise_for_status()
        text = response.json().get("response", "").strip()
        if not text:
            raise ValueError("empty response")
        return text, []
    except Exception as exc:
        return _fallback(context), [f"Qwen 호출 실패로 정형 문장을 사용했습니다: {type(exc).__name__}"]
