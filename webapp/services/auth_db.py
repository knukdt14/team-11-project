"""로그인 계정 + 상담 히스토리 영구 저장 (SQLite).

⚠️ 이전엔 `app.storage.tab`(브라우저 탭 닫으면 사라짐)에 상담 기록을 뒀는데,
"상담한 내용이 저장됐으면 좋겠다"는 요청 + 실제 로그인 요청이 같이 들어와서
아예 SQLite로 옮겼습니다 — 계정별로 기록이 남고, 서버를 껐다 켜도 유지됩니다.
비밀번호는 bcrypt로 해시해서 저장합니다(평문 저장 금지).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import bcrypt

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consult_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                diagram_no TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


init_db()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# 계정
# ──────────────────────────────────────────────────────────────────


def create_user(username: str, password: str) -> tuple[bool, str]:
    """반환: (성공여부, 에러메시지). 성공하면 에러메시지는 빈 문자열."""
    username = username.strip()
    if not username or not password:
        return False, "아이디와 비밀번호를 모두 입력해주세요."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, _now()),
            )
        return True, ""
    except sqlite3.IntegrityError:
        return False, "이미 있는 아이디입니다."


def verify_user(username: str, password: str) -> int | None:
    """아이디/비밀번호가 맞으면 user_id, 아니면 None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        return row["id"]
    return None


# ──────────────────────────────────────────────────────────────────
# 상담 히스토리
# ──────────────────────────────────────────────────────────────────


def save_consult(user_id: int, query: str, diagram_no: str, result: dict) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO consult_history (user_id, query, diagram_no, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, query, diagram_no, json.dumps(result, ensure_ascii=False), _now()),
        )
        history_id = cur.lastrowid
    _trim_history(user_id, keep=30)
    return history_id


def _trim_history(user_id: int, keep: int) -> None:
    with _connect() as conn:
        ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM consult_history WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        ]
        stale = ids[keep:]
        if stale:
            conn.executemany("DELETE FROM consult_history WHERE id = ?", [(i,) for i in stale])


def load_consult_history(user_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, query, diagram_no, result_json, created_at FROM consult_history "
            "WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "질문": r["query"],
            "도표번호": r["diagram_no"],
            "result": json.loads(r["result_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def delete_consult(history_id: int, user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM consult_history WHERE id = ? AND user_id = ?", (history_id, user_id)
        )


def clear_consult_history(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM consult_history WHERE user_id = ?", (user_id,))
