from __future__ import annotations
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import RLock
from uuid import uuid4
from .config import settings

class SessionStore:
    """재시작 후에도 상담 이력을 보존하는 SQLite 세션 저장소."""
    def __init__(self, path: str | None = None):
        self.path = Path(path or settings.session_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, data: dict, session_id: str | None = None) -> str:
        sid = session_id or str(uuid4())
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()
            history = json.loads(row[0]).get("history", []) if row else []
            value = {**deepcopy(data), "history": history}
            conn.execute("INSERT OR REPLACE INTO sessions(id, data) VALUES (?, ?)",
                         (sid, json.dumps(value, ensure_ascii=False)))
        return sid

    def get(self, session_id: str):
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def update(self, session_id: str, **fields):
        state = self.get(session_id)
        if not state:
            raise KeyError(session_id)
        state.update(deepcopy(fields))
        history = state.pop("history", [])
        self.save(state, session_id)
        with self._lock, self._connect() as conn:
            state = self.get(session_id) or {}
            state["history"] = history
            conn.execute("UPDATE sessions SET data=? WHERE id=?",
                         (json.dumps(state, ensure_ascii=False), session_id))

    def append(self, session_id: str, role: str, content: str):
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise KeyError(session_id)
            state = json.loads(row[0])
            state.setdefault("history", []).append({"role": role, "content": content})
            conn.execute("UPDATE sessions SET data=? WHERE id=?",
                         (json.dumps(state, ensure_ascii=False), session_id))

sessions = SessionStore()
