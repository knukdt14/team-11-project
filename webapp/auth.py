"""로그인 가드 — 각 페이지 맨 위에서 `if not await auth.require_login(): return` 로 씁니다.

`app.storage.user`는 NiceGUI가 서명된 쿠키로 관리하는 영구 저장소라(브라우저 탭을
닫아도, 서버를 재시작해도 유지됨) 여기에 로그인 상태를 저장합니다.
"""

from __future__ import annotations

from nicegui import app, ui


async def require_login() -> bool:
    """로그인 안 됐으면 /login 으로 보내고 False를 반환합니다.
    페이지 함수에서 `if not await auth.require_login(): return` 형태로 씁니다."""
    await ui.context.client.connected()
    if not app.storage.user.get("authenticated"):
        ui.navigate.to("/login")
        return False
    return True


def current_user_id() -> int | None:
    return app.storage.user.get("user_id")


def current_username() -> str:
    return app.storage.user.get("username", "")


def logout() -> None:
    app.storage.user.clear()
    ui.navigate.to("/login")
