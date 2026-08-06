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
