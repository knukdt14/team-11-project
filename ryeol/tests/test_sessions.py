from ryeol.app.sessions import SessionStore

def test_session_history_survives_update():
    store = SessionStore()
    sid = store.save({"value": 1})
    store.append(sid, "user", "질문")
    store.save({"value": 2}, sid)
    assert store.get(sid)["history"] == [{"role": "user", "content": "질문"}]
