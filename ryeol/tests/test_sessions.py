from ryeol.app.sessions import SessionStore

def test_session_history_survives_update(tmp_path):
    store = SessionStore(str(tmp_path / "sessions.sqlite3"))
    sid = store.save({"value": 1})
    store.append(sid, "user", "질문")
    store.save({"value": 2}, sid)
    assert store.get(sid)["history"] == [{"role": "user", "content": "질문"}]

def test_session_survives_new_store_instance(tmp_path):
    path = str(tmp_path / "sessions.sqlite3")
    first = SessionStore(path)
    sid = first.save({"value": 1})
    assert SessionStore(path).get(sid)["value"] == 1
