from taek.search import Hit
from ryeol.app import service
from ryeol.app.schemas import ConsultRequest, FollowUpRequest, RecalculateRequest

PAYLOAD = {
    "standard_id": "MAIN2023-차25", "source_id": "MAIN2023", "diagram_no": "차25",
    "title": "무신호 교차로 직진 대 좌회전", "base_ratio": {"a": 30, "b": 70},
    "modifiers": [{"name": "야간", "target": "A", "adjustment": 10}],
    "source_page": 148, "laws": [], "precedents": [], "parse_flags": [],
}

class FakeSearcher:
    def search(self, *args, **kwargs):
        return [Hit("MAIN2023-차25", 0.9, "standard", "근거", PAYLOAD, "description", [])]
    def cases(self, *args, **kwargs):
        return []
    def laws_for(self, *args, **kwargs):
        return []

def test_consult_then_recalculate(monkeypatch):
    monkeypatch.setattr(service, "explain", lambda context: ("근거 기반 설명", []))
    response = service.consult(FakeSearcher(), ConsultRequest(
        사고설명="무신호 교차로 사고", 상담자측="A", 적용할_수정요소=["야간"]))
    assert response.최종과실.A == 40
    assert response.답변 == "근거 기반 설명"
    recalculated = service.recalculate(RecalculateRequest(
        session_id=response.session_id, 적용할_수정요소=[]))
    assert recalculated.최종과실.A == 30
    follow = service.follow_up(FollowUpRequest(session_id=response.session_id, 질문="근거가 뭐야?"))
    assert follow.답변 == "근거 기반 설명"

class EmptySearcher(FakeSearcher):
    def search(self, *args, **kwargs):
        return []

def test_rejected_query_never_gets_ratio():
    response = service.consult(EmptySearcher(), ConsultRequest(사고설명="보험료 질문"))
    assert response.status == "not_found"
    assert response.최종과실 is None
