from copy import deepcopy
from threading import RLock
from uuid import uuid4

class SessionStore:
    def __init__(self):
        self._items, self._lock = {}, RLock()
    def save(self, data: dict, session_id: str | None = None) -> str:
        sid = session_id or str(uuid4())
        with self._lock:
            history = self._items.get(sid, {}).get("history", [])
            self._items[sid] = {**deepcopy(data), "history": history}
        return sid
    def get(self, session_id: str):
        with self._lock:
            value = self._items.get(session_id)
            return deepcopy(value) if value else None
    def append(self, session_id: str, role: str, content: str):
        with self._lock:
            if session_id not in self._items:
                raise KeyError(session_id)
            self._items[session_id].setdefault("history", []).append({"role": role, "content": content})

sessions = SessionStore()
