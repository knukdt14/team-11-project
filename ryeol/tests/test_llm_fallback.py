from types import SimpleNamespace

from ryeol.app import llm


CONTEXT = {"제목": "교차로 사고", "최종과실": {"A": 30, "B": 70}}


def test_auto_uses_gemini_first(monkeypatch):
    monkeypatch.setattr(llm, "settings", SimpleNamespace(llm_mode="auto"))
    monkeypatch.setattr(llm, "_gemini", lambda prompt: "Gemini 답변")
    monkeypatch.setattr(llm, "_exaone", lambda prompt: (_ for _ in ()).throw(AssertionError()))

    answer, warnings = llm.explain(CONTEXT)

    assert answer == "Gemini 답변"
    assert warnings == []


def test_auto_falls_back_to_exaone(monkeypatch):
    monkeypatch.setattr(llm, "settings", SimpleNamespace(llm_mode="auto"))
    monkeypatch.setattr(llm, "_gemini", lambda prompt: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(llm, "_exaone", lambda prompt: "EXAONE 답변")

    answer, warnings = llm.explain(CONTEXT)

    assert answer == "EXAONE 답변"
    assert "Gemini 호출 실패" in warnings[0]


def test_auto_falls_back_to_template_when_both_fail(monkeypatch):
    monkeypatch.setattr(llm, "settings", SimpleNamespace(llm_mode="auto"))
    monkeypatch.setattr(llm, "_gemini", lambda prompt: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(llm, "_exaone", lambda prompt: (_ for _ in ()).throw(RuntimeError()))

    answer, warnings = llm.explain(CONTEXT)

    assert "본인 30%" in answer
    assert len(warnings) == 2


def test_followup_fallback_differs_from_initial_and_echoes_question(monkeypatch):
    """회귀 테스트: 후속질문이 LLM 실패로 fallback을 타면, 최초상담 fallback과
    똑같은 문장이 반복되던 버그가 있었습니다 (기존상담 안쪽 제목을 못 찾고,
    후속질문 내용을 아예 안 쳐다봤음). 이제는 후속질문 문구를 답변에 반영해야 합니다."""
    monkeypatch.setattr(llm, "settings", SimpleNamespace(llm_mode="auto"))
    monkeypatch.setattr(llm, "_gemini", lambda prompt: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(llm, "_exaone", lambda prompt: (_ for _ in ()).throw(RuntimeError()))

    initial_answer, _ = llm.explain(CONTEXT)

    followup_context = {
        "기존상담": {"제목": "교차로 사고"},
        "최종과실": {"A": 30, "B": 70},
        "후속질문": "왜 이렇게 나왔어?",
        "대화이력": [],
    }
    followup_answer, _ = llm.explain(followup_context)

    assert followup_answer != initial_answer
    assert "왜 이렇게 나왔어?" in followup_answer
    assert "교차로 사고" in followup_answer
