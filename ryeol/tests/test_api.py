from fastapi.testclient import TestClient
from taek.search import Hit
from ryeol.app import main, service

PAYLOAD = {
    "standard_id": "MAIN2023-차15-1", "source_id": "MAIN2023", "diagram_no": "차15-1",
    "title": "직진 대 맞은편 좌회전", "section": "신호 없는 교차로", "base_ratio": {"a": 30, "b": 70},
    "modifiers": [{"name": "야간", "target": "A", "adjustment": 10}],
    "source_page": 100, "image_path": "images/MAIN2023-차15-1.png",
    "laws": [], "precedents": [], "parse_flags": [],
}

class FakeSearcher:
    def search(self, *args, **kwargs):
        return [Hit("MAIN2023-차15-1", 0.9, "standard", "근거", PAYLOAD, "description", [])]
    def cases(self, *args, **kwargs):
        return []
    def laws_for(self, *args, **kwargs):
        return []

def test_http_contract(monkeypatch):
    monkeypatch.setattr(main, "Searcher", FakeSearcher)
    monkeypatch.setattr(service, "explain", lambda context: ("근거 기반 설명", []))
    with TestClient(main.app) as client:
        assert client.get("/health").json()["search_ready"] is True
        response = client.post("/consult", json={
            "사고설명": "신호 없는 교차로에서 직진 중 맞은편 좌회전 차량과 충돌",
            "상담자측": "A"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "complete"
        assert body["image_url"] == "/images/MAIN2023-차15-1.png"
        modifier_id = body["미적용_수정요소"][0]["id"]
        recalculated = client.post("/recalculate", json={
            "session_id": body["session_id"], "적용할_수정요소": [modifier_id]})
        assert recalculated.json()["최종과실"] == {"A": 40, "B": 60}
        history = client.get(f"/sessions/{body['session_id']}")
        assert history.status_code == 200
