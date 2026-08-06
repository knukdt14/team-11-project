"""상담 페이지 — 핵심 기능의 중심 화면.

레이아웃은 사용자가 제시한 참고 목업(상단 가로 네비바 + 좌: 상담 채팅 기록 /
중앙: 단계별 입력·결과 / 우: 상세 분석·법률 참조 3단 구성)을 따릅니다. 단, 목업의
"속도/도로상태/차선 수" 같은 입력 필드나 "AI 사고 재구성" 그림은 저희 실제 파이프라인이
만들어내지 않는 가짜 데이터라 넣지 않았습니다 — 실제로 우리 백엔드가 쓰는 입력(사고
설명 자유 텍스트)과 실제로 반환하는 데이터(안내문·기본과실·수정요소·법조항·유사사례·
trace)만으로 같은 레이아웃 언어(번호 매긴 스텝 카드, 3단 배치)를 구현했습니다.

⚠️ NiceGUI는 Streamlit과 달리 "위젯 하나 바뀌면 스크립트 전체가 처음부터 다시
실행"되지 않습니다 — 대신 각 영역(result_area/summary_box/side_panel 등)을 우리가
직접 clear()+다시 그리기 해서 그 부분만 갱신합니다.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import app, run, ui

from webapp import auth, theme
from webapp.pages.home import EXAMPLES
from webapp.services.auth_db import clear_consult_history, delete_consult, load_consult_history, save_consult
from webapp.services.backend import additional_info, consult, follow_up_chat, recalculate

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def step_header(num: str, title: str) -> None:
    ui.html(
        f'<div class="fr-step-header"><span class="fr-step-num">{num}</span>{title}</div>'
    ).classes("w-full")


@ui.page("/consult")
async def consult_page() -> None:
    if not await auth.require_login():
        return
    theme.inject_head()
    user_id = auth.current_user_id()

    state = {
        "result": None,
        "applied_mods": set(),
        "side": "A",
        "chat_history": [],  # (role, msg, warned)
    }
    # ⚠️ 예전엔 app.storage.tab(브라우저 탭 닫으면 사라짐)에 뒀는데, "상담 내용이
    # 저장됐으면 좋겠다"는 요청으로 SQLite(webapp/services/auth_db.py)로 옮겼습니다 —
    # 계정별로 남고 서버를 재시작해도 유지됩니다. `history`는 그 스냅샷이라, DB를
    # 바꾸는 조작(저장/삭제) 뒤에는 반드시 다시 불러와서 이 리스트를 갱신합니다.
    history: list[dict] = load_consult_history(user_id)

    with theme.page_frame("consult") as main:
        with ui.row().classes("w-full items-start no-wrap").style("gap:20px"):

            # ══════════ 왼쪽: 상담 채팅 기록 ══════════════════════
            with ui.column().style("width:200px; flex-shrink:0;"):
                with ui.element("div").classes("fr-card w-full"):
                    def render_history() -> None:
                        hist_box.clear()
                        with hist_box:
                            with ui.row().classes("w-full items-center justify-between no-wrap"):
                                ui.label("🕘 상담 채팅 기록").classes("font-bold text-sm")
                                if history:
                                    def clear_all():
                                        clear_consult_history(user_id)
                                        history[:] = load_consult_history(user_id)
                                        render_history()

                                    ui.button(icon="delete", on_click=clear_all).props(
                                        "flat dense size=sm"
                                    )
                            if not history:
                                ui.label("아직 상담 기록이 없어요.").classes(
                                    "text-xs text-gray-400 mt-2"
                                )
                            # ⚠️ load_consult_history()가 이미 최신순(id DESC)으로 주므로
                            # 여기서 다시 reversed() 하지 않습니다.
                            for h in history:
                                hid = h["id"]
                                label = (
                                    f"{h['도표번호'] or '?'} · "
                                    f"{h['질문'][:14]}{'…' if len(h['질문']) > 14 else ''}"
                                )
                                with ui.row().classes("w-full items-center no-wrap").style(
                                    "gap:2px; margin-top:4px;"
                                ):
                                    def load(h=h):
                                        state["result"] = h["result"]
                                        state["applied_mods"] = set()
                                        state["chat_history"] = [("user", h["질문"], False)]
                                        refresh_results()

                                    ui.button(label, on_click=load).props(
                                        "flat dense align=left"
                                    ).classes("flex-1 text-xs justify-start")

                                    def delete(hid=hid):
                                        delete_consult(hid, user_id)
                                        history[:] = load_consult_history(user_id)
                                        render_history()

                                    ui.button(icon="close", on_click=delete).props(
                                        "flat dense size=sm"
                                    )

                    hist_box = ui.column().classes("w-full gap-0")
                    render_history()

            # ══════════ 중앙: 입력 → 결과 ══════════════════════════
            with ui.column().classes("flex-1 min-w-0"):
                ui.html('<div class="fr-section-title">💡 예시로 바로 시작해보기</div>')
                with ui.row().classes("w-full no-wrap").style("gap:16px; margin-bottom:8px;"):
                    for emoji, ex in EXAMPLES:
                        with ui.column().classes("flex-1 min-w-0"):
                            def fill(ex=ex):
                                query_input.value = ex

                            with ui.element("div").classes("fr-example-card").on("click", fill):
                                ui.html(f'<div style="font-size:1.6rem;">{emoji}</div>')
                                ui.html(f'<div class="fr-example-q">{ex}</div>')
                                ui.button("이 예시로 상담하기", on_click=fill).classes(
                                    "w-full fr-btn-primary"
                                ).props("unelevated")

                step_header("1", "사고 상황 입력")
                with ui.element("div").classes("fr-step-body w-full"):
                    prefill = app.storage.tab.pop("prefill_query", "")
                    query_input = ui.textarea(
                        placeholder="예) 신호 없는 교차로에서 직진하다 좌회전하던 차와 부딪혔어요",
                        value=prefill,
                    ).classes("w-full").props("outlined autogrow")

                    with ui.row().classes("w-full items-center no-wrap").style("margin-top:8px;"):
                        side_radio = ui.radio(
                            {"A": "피해차량", "B": "가해차량"}, value="A"
                        ).props("inline")
                        ui.space()
                        run_btn = ui.button("🔍 상담 시작").classes("fr-btn-primary").style(
                            "white-space:nowrap;"
                        ).props("unelevated")

                    ui.label(
                        "공식 과실비율 도표에서는 보통 가해차량의 과실이 더 큽니다(신호위반·추돌 등 선행과실) — "
                        "본인이 피해차량인지 가해차량인지 아직 모르면 우선 피해차량으로 시작하세요"
                    ).classes("text-xs text-gray-500").style("margin-top:6px;")

                result_area = ui.column().classes("w-full")

                async def run_consult() -> None:
                    q = query_input.value.strip()
                    if not q:
                        return
                    run_btn.props("loading")
                    try:
                        new_result = await run.io_bound(consult, q, side_radio.value)
                    finally:
                        run_btn.props(remove="loading")
                    state["result"] = new_result
                    state["applied_mods"] = set()
                    state["side"] = side_radio.value
                    state["chat_history"] = [("user", q, False)]
                    if new_result.get("status") == "complete":
                        save_consult(user_id, q, new_result.get("도표번호", ""), new_result)
                        history[:] = load_consult_history(user_id)
                        render_history()
                    refresh_results()

                run_btn.on_click(run_consult)

            # ══════════ 오른쪽: 상세 분석 및 법률 참조 ═══════════════
            with ui.column().style("width:260px; flex-shrink:0;"):
                ui.html('<div class="fr-section-title" style="font-size:1rem;">📚 상세 분석 및 법률 참조</div>')
                side_panel = ui.column().classes("w-full gap-0")
                with side_panel:
                    ui.label("상담을 시작하면 여기에 법조항·유사사례·근거가 표시됩니다.").classes(
                        "text-xs text-gray-400"
                    )

        # ── 결과 렌더링 ──────────────────────────────────────────
        def refresh_results() -> None:
            result_area.clear()
            side_panel.clear()
            result = state["result"]
            with result_area:
                if result is None:
                    return
                _render_result(result)
            if result is None:
                with side_panel:
                    ui.label("상담을 시작하면 여기에 법조항·유사사례·근거가 표시됩니다.").classes(
                        "text-xs text-gray-400"
                    )

        def _render_result(result: dict) -> None:
            status = result.get("status", "complete")

            if status == "not_found":
                step_header("2", "결과")
                with ui.element("div").classes("fr-step-body w-full"):
                    ui.label(f"⚠️ {result.get('경고', '해당 기준을 찾을 수 없습니다')}").classes(
                        "text-red-600 font-bold"
                    )
                    _render_chips(result.get("되묻기", []), "notfound")
                    theme.disclaimer()
                return

            if status == "needs_information":
                step_header("2", "결과")
                with ui.element("div").classes("fr-step-body w-full"):
                    if result.get("도표번호"):
                        ui.label(
                            f"🔎 지금까지 찾은 기준: {result.get('도표번호')} {result.get('제목', '')} "
                            "— 조금만 더 알려주시면 정확히 계산해드려요."
                        ).classes("text-blue-700")
                    else:
                        ui.label("🔎 조금만 더 알려주시면 정확히 계산해드려요.").classes(
                            "text-blue-700"
                        )
                    _render_chips(result.get("되묻기", []), "needinfo")
                    후보 = result.get("후보", [])
                    if 후보:
                        with ui.expansion("🔎 지금까지 찾은 비슷한 기준 더 보기"):
                            for s in 후보:
                                ui.label(f"- {s.get('도표번호')} {s.get('제목', '')}")
                    theme.disclaimer()
                return

            기본과실 = result["기본과실"]
            수정요소 = result["수정요소"]

            step_header("2", "AI 사고 분석 결과")
            with ui.element("div").classes("fr-step-body w-full"):
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    유형 = result.get("사고유형") or {}
                    breadcrumb = " › ".join(
                        p for p in [유형.get("대", ""), result.get("출처", ""), result.get("도표번호", "")]
                        if p
                    )
                    ui.label(breadcrumb or "인정기준").classes("text-xs text-gray-400")

                    def reset():
                        state["result"] = None
                        state["applied_mods"] = set()
                        state["chat_history"] = []
                        refresh_results()

                    ui.button("🔄 처음부터", on_click=reset).props("flat dense")

                badge_html = theme.confidence_badge_html(result.get("신뢰도", "낮음"))
                ui.html(f"<h3 style='margin:4px 0;'>{result.get('도표번호', '')} — {result.get('제목', '')} {badge_html}</h3>")

                with ui.row().classes("w-full items-stretch no-wrap").style("gap:12px"):
                    with ui.element("div").style(
                        "flex:1; display:flex; align-items:center; background:#F0FAF9; "
                        "border:1px solid #CFEEEA; border-radius:14px; padding:14px 18px;"
                    ):
                        ui.html(f"🧭 <b>{result.get('안내문', '')}</b>")

                    other_side = "B" if state["side"] == "A" else "A"

                    async def switch_side(other_side=other_side):
                        switch_btn.props("loading")
                        try:
                            new_result = await run.io_bound(consult, result["질문"], other_side)
                        finally:
                            switch_btn.props(remove="loading")
                        state["result"] = new_result
                        state["applied_mods"] = set()
                        state["side"] = other_side
                        refresh_results()

                    switch_btn = ui.button(
                        f"↔ 반대쪽({other_side})이에요", on_click=switch_side
                    ).props("outline").style("flex-shrink:0;")

                if not result.get("백엔드_사용", False):
                    ui.label("🔧 로컬 검색 모드 결과입니다 (백엔드 미연결)").classes(
                        "text-xs text-gray-400"
                    )

                with ui.tabs().classes("w-full") as tabs:
                    tab_scene = ui.tab("🖼 사고 상황")
                    tab_apply = ui.tab("✅ 적용요소")
                    tab_expl = ui.tab("📖 기본과실 해설")
                with ui.tab_panels(tabs, value=tab_apply).classes("w-full"):
                    with ui.tab_panel(tab_scene):
                        image_shown = False
                        if result.get("image_path"):
                            img_path = REPO_ROOT / "hani" / "data" / result["image_path"]
                            if img_path.exists():
                                ui.image(str(img_path)).classes("rounded border").style(
                                    "max-width:900px; width:100%;"
                                )
                                ui.label(
                                    f"{result.get('도표번호', '')} · p.{result.get('pdf_page', '?')}"
                                ).classes("text-xs text-gray-400")
                                image_shown = True
                        elif result.get("image_url"):
                            from webapp.services.backend import BACKEND_URL

                            ui.image(f"{BACKEND_URL}{result['image_url']}").classes(
                                "rounded border"
                            ).style("max-width:900px; width:100%;")
                            image_shown = True
                        if result.get("사고상황"):
                            ui.markdown(result["사고상황"])
                        if not image_shown and not result.get("사고상황"):
                            ui.label("이 기준에는 사고 상황 설명/이미지가 없습니다.").classes(
                                "text-gray-400"
                            )

                    with ui.tab_panel(tab_apply):
                        summary_box = ui.column().classes("w-full")
                        gauge_box = ui.column().classes("w-full items-center")

                        with ui.row().classes("w-full items-start no-wrap").style("gap:16px"):
                            with ui.element("div").style(
                                "flex:1; border:1px solid rgba(15,23,42,.08); border-radius:14px; padding:14px 16px;"
                            ):
                                ui.markdown(f"**🚙 나({result.get('나_역할', 'A')}) 가감요소**")
                                target_a = [m for m in 수정요소 if m["대상"] == "A"]
                                if not target_a:
                                    ui.label("해당 없음").classes("text-gray-400 text-sm")
                                for m in target_a:
                                    _mod_toggle(m, state, summary_box, gauge_box, result)
                            with ui.element("div").style(
                                "flex:1; border:1px solid rgba(15,23,42,.08); border-radius:14px; padding:14px 16px;"
                            ):
                                ui.markdown(f"**🚗 상대({result.get('상대_역할', 'B')}) 가감요소**")
                                target_b = [m for m in 수정요소 if m["대상"] == "B"]
                                if not target_b:
                                    ui.label("해당 없음").classes("text-gray-400 text-sm")
                                for m in target_b:
                                    _mod_toggle(m, state, summary_box, gauge_box, result)

                        _render_summary(summary_box, gauge_box, result, state)

                    with ui.tab_panel(tab_expl):
                        if result.get("해설"):
                            ui.markdown(f"**기본과실 해설**\n\n{result['해설']}")
                        if result.get("수정요소_해설"):
                            ui.markdown(f"**수정요소 해설**\n\n{result['수정요소_해설']}")
                        if not result.get("해설") and not result.get("수정요소_해설"):
                            ui.label("해설 데이터가 없습니다.").classes("text-gray-400")

                if result.get("답변"):
                    ui.html('<div class="fr-section-title" style="margin-top:16px;">🤖 AI 설명</div>')
                    if result.get("warnings"):
                        ui.label(
                            "⚠️ AI가 지금 답변을 만들지 못해서, 대신 정해진 문구를 보여드리고 있어요."
                        ).classes("text-orange-600 text-sm")
                    ui.label(result["답변"])
                    if result.get("warnings"):
                        with ui.expansion("자세한 원인 (기술 정보)"):
                            for w in result["warnings"]:
                                ui.label(w).classes("text-xs text-gray-400")

            # ── 3. 대화형 후속 질문 (목업의 "사고 정보 수정" 입력) ─────
            step_header("3", "사고 정보 수정 (추가로 물어보거나 반박하기)")
            with ui.element("div").classes("fr-step-body w-full"):
                if result.get("백엔드_사용"):
                    ui.label("실제 LLM이 답변합니다.").classes("text-xs text-gray-400")
                else:
                    ui.label(
                        "🔧 로컬 검색 모드에서는 정형 안내만 드려요 — 백엔드가 붙으면 실제 LLM이 답합니다."
                    ).classes("text-xs text-gray-400")

                chat_box = ui.column().classes("w-full gap-0")
                with chat_box:
                    for entry in state["chat_history"]:
                        role, msg, warned = entry
                        with theme.chat_bubble(
                            "나" if role == "user" else "AI", sent=(role == "user")
                        ):
                            if warned:
                                ui.label("⚠️ AI가 직접 쓴 답이 아니라 정해진 문구입니다").classes(
                                    "text-xs text-orange-300"
                                )
                            ui.label(msg)

                with ui.row().classes("w-full no-wrap items-center").style("margin-top:8px;"):
                    chat_input = ui.input(
                        placeholder="예) 제가 과속을 하고있었는데 과실 변경이 없나요"
                    ).classes("flex-1 min-w-0").style("font-size:0.78rem;").props("outlined dense")

                    async def send_chat():
                        q = chat_input.value.strip()
                        if not q:
                            return
                        chat_input.value = ""
                        state["chat_history"].append(("user", q, False))
                        with chat_box:
                            with ui.chat_message(name="나", sent=True):
                                ui.label(q)
                            with ui.chat_message(name="AI") as bubble:
                                ui.spinner()
                        answer, warns = await run.io_bound(follow_up_chat, result, q)
                        bubble.clear()
                        with bubble:
                            if warns:
                                ui.label(
                                    "⚠️ AI가 직접 쓴 답이 아니라 정해진 문구입니다"
                                ).classes("text-xs text-orange-500")
                            ui.label(answer)
                        state["chat_history"].append(("assistant", answer, bool(warns)))

                    chat_input.on("keydown.enter", send_chat)
                    ui.button(icon="send", on_click=send_chat).props("unelevated round").classes(
                        "fr-btn-primary"
                    )

            theme.disclaimer()
            _render_side_panel(side_panel, result)

        def _render_chips(questions: list[str], prefix: str) -> None:
            if not questions:
                return
            ui.label("확인이 필요해요 — 아래 중 해당하는 것을 눌러 알려주세요").classes(
                "text-xs text-gray-500"
            )
            with ui.row().classes("w-full"):
                for q in questions:
                    async def pick(q=q):
                        new_result = await run.io_bound(additional_info, state["result"], q)
                        state["result"] = new_result
                        state["applied_mods"] = set()
                        refresh_results()

                    ui.html(f'<div class="fr-chip">{q}</div>').on("click", pick)

        refresh_results()


def _render_side_panel(side_panel, result: dict) -> None:
    """오른쪽 "상세 분석 및 법률 참조" 패널 — 법조항 / 유사사례 / trace."""
    with side_panel:
        법조항 = result.get("법조항", [])
        with ui.element("div").classes("fr-card w-full"):
            ui.markdown("**📜 관련 법규**")
            if not 법조항:
                ui.label("관련 법령이 없습니다.").classes("text-gray-400 text-xs")
            for law in 법조항:
                with ui.expansion(f"{law.get('조', '조문')} {law.get('제목', '')}").classes(
                    "text-sm"
                ):
                    ui.label(law.get("내용", "")).classes("text-xs")
                    if not law.get("시행중", True):
                        ui.label("⚠️ 현재 시행 중이 아닌 조문입니다.").classes(
                            "text-xs text-gray-400"
                        )

        유사사례 = result.get("유사사례", [])
        with ui.element("div").classes("fr-card w-full"):
            ui.markdown("**⚖️ 유사사례 (심의사례)**")
            if not 유사사례:
                ui.label("관련 심의사례가 없습니다.").classes("text-gray-400 text-xs")
            for c in 유사사례:
                제목 = c.get("제목") or "심의사례"
                심의번호 = c.get("심의번호")
                표시명 = f"{제목} · 심의 {심의번호}" if 심의번호 else 제목
                with ui.expansion(표시명).classes("text-sm"):
                    ui.label(
                        f"청구인측: {c.get('A_당사자', '-')} · 피청구인측: {c.get('B_당사자', '-')}"
                    ).classes("text-xs text-gray-400")
                    기본 = c.get("기본비율")
                    결정 = c.get("결정비율")
                    if 기본:
                        ui.label(f"기본비율: A {기본['A']}% : B {기본['B']}%").classes("text-xs")
                    if 결정:
                        ui.label(f"실제 결정비율: A {결정['A']}% : B {결정['B']}%").classes("text-xs")
                    if c.get("비율_달라짐"):
                        ui.label(
                            "⚠️ 기본비율과 실제 결정비율이 다릅니다."
                        ).classes("text-xs text-orange-600")

        if result.get("판례"):
            with ui.element("div").classes("fr-card w-full"):
                ui.markdown("**참조 판례**")
                ui.label(", ".join(result["판례"])).classes("text-xs text-gray-400")

        후보 = result.get("후보", [])
        with ui.element("div").classes("fr-card w-full"):
            with ui.expansion("🔎 유사 사고유형 더 보기").classes("text-sm w-full"):
                if not 후보:
                    ui.label("유사 사고유형이 없습니다.").classes("text-gray-400 text-xs")
                for s in 후보:
                    ui.label(
                        f"- {s.get('도표번호')} {s.get('제목', '')} (관련도 {s.get('검색점수', 0):.2f})"
                    ).classes("text-xs")


def _mod_toggle(m: dict, state: dict, summary_box, gauge_box, result: dict) -> None:
    sign = "+" if m["값"] >= 0 else ""
    on = m["id"] in state["applied_mods"]

    async def toggle(e, m=m):
        if e.value:
            state["applied_mods"].add(m["id"])
        else:
            state["applied_mods"].discard(m["id"])
        _render_summary(summary_box, gauge_box, result, state)

    ui.switch(f"{m['조건']} ({sign}{m['값']})", value=on, on_change=toggle)
    if m.get("근거"):
        ui.label(m["근거"]).classes("text-xs text-gray-400 ml-8 -mt-2 mb-1")


def _render_summary(summary_box, gauge_box, result: dict, state: dict) -> None:
    summary_box.clear()
    최종과실, _계산_단계 = recalculate(result, state["applied_mods"])
    with summary_box:
        with ui.element("div").classes("fr-card w-full"):
            ui.html(
                theme.ratio_hero_html(
                    최종과실["A"], 최종과실["B"], result.get("나_역할", "나"), result.get("상대_역할", "상대")
                )
            )
            ui.label("기본과실 → 위 수정요소를 켜면 이 숫자가 즉시 바뀝니다 (재검색 없음)").classes(
                "text-xs text-gray-400"
            )

            applied_names = [m["조건"] for m in result["수정요소"] if m["id"] in state["applied_mods"]]
            report = theme.consult_report_text(result, 최종과실, applied_names)
            ui.button(
                "📥 이 결과 리포트 다운로드",
                on_click=lambda: ui.download(
                    report.encode("utf-8"), f"과실비율_{result.get('도표번호', 'result')}.txt"
                ),
            ).props("outline").classes("w-full")

    theme.fault_gauge(
        gauge_box, 최종과실["A"], 최종과실["B"], result.get("나_역할", "나"), result.get("상대_역할", "상대"),
        gauge_id=f"gauge-{id(result)}",
    )
