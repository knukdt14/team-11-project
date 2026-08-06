"""로그인 / 회원가입 — 실제 아이디·비밀번호 기반 (SQLite + bcrypt)."""

from __future__ import annotations

from nicegui import app, ui

from webapp import theme
from webapp.services.auth_db import create_user, verify_user


@ui.page("/login")
async def login_page() -> None:
    await ui.context.client.connected()
    theme.inject_head()

    if app.storage.user.get("authenticated"):
        ui.navigate.to("/")
        return

    with ui.element("div").classes("fr-shell").style(
        "min-height:100vh; display:flex; align-items:center; justify-content:center;"
    ):
        with ui.element("div").classes("fr-card").style("width:380px;"):
            ui.html(
                '<div style="text-align:center;margin-bottom:6px;">'
                '<div class="fr-topbar-brand" style="justify-content:center;color:#0F172A;'
                f'font-size:1.3rem;">🚦 과실비율 상담</div></div>'
            )
            ui.label("로그인").classes("text-lg font-bold").style("margin-top:8px;")

            username_input = ui.input("아이디").classes("w-full").props("outlined")
            password_input = ui.input("비밀번호", password=True, password_toggle_button=True).classes(
                "w-full"
            ).props("outlined")
            error_label = ui.label("").classes("text-red-600 text-xs")

            async def do_login() -> None:
                uid = verify_user(username_input.value, password_input.value)
                if uid is None:
                    error_label.text = "아이디 또는 비밀번호가 올바르지 않습니다."
                    return
                app.storage.user.update({
                    "authenticated": True, "user_id": uid, "username": username_input.value.strip(),
                })
                ui.navigate.to("/")

            password_input.on("keydown.enter", do_login)
            ui.button("로그인", on_click=do_login).classes("w-full fr-btn-primary").props(
                "unelevated"
            ).style("margin-top:6px;")

            ui.separator().classes("my-3")
            ui.label("계정이 없으신가요?").classes("text-xs text-gray-500 text-center w-full")

            reg_username = ui.input("새 아이디").classes("w-full").props("outlined dense")
            reg_password = ui.input("새 비밀번호 (4자 이상)", password=True, password_toggle_button=True).classes(
                "w-full"
            ).props("outlined dense")
            reg_error = ui.label("").classes("text-red-600 text-xs")
            reg_success = ui.label("").classes("text-green-600 text-xs")

            def do_register() -> None:
                reg_error.text = ""
                reg_success.text = ""
                ok, msg = create_user(reg_username.value, reg_password.value)
                if not ok:
                    reg_error.text = msg
                    return
                reg_success.text = "회원가입 완료! 위에서 로그인해주세요."
                username_input.value = reg_username.value.strip()
                reg_username.value = ""
                reg_password.value = ""

            ui.button("회원가입", on_click=do_register).classes("w-full").props("outline")

            ui.label(
                "⚠️ 팀 프로젝트 데모용 계정 시스템입니다 — 실제 개인정보를 쓰지 마세요."
            ).classes("text-xs text-gray-400 text-center w-full").style("margin-top:10px;")
