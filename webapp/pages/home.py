"""홈 — 서비스 소개, 예시 질문 카드, 백엔드 연결 상태 배지, 지식베이스 현황."""

from __future__ import annotations

from collections import Counter

from nicegui import app, ui

from webapp import auth, theme
from webapp.services.backend import backend_available
from webapp.services.kb_data import source_label, standards

EXAMPLES = [
    ("🚧", "중앙선을 침범하여 주행하는 반대편 차량과 추돌사고 발생"),
    ("🌙", "야간에 뒤에서 오던 차가 제 차를 추돌했어요"),
    ("🛴", "전동킥보드로 직진하는데 신호 없는 교차로에서 좌회전 차가 들이받았어요"),
]

STEPS = [
    ("1", "사고 상황을 입력", "채팅하듯 편하게 적어주세요"),
    ("2", "근거 기준을 확인", "공식 인정기준 도표·법령·판례"),
    ("3", "수정요소로 조정", "토글 하나로 즉시 재계산"),
]


def _num_badge(num: str) -> None:
    ui.html(
        f'<div style="flex-shrink:0;width:34px;height:34px;border-radius:50%;'
        f'background:linear-gradient(135deg,{theme.나_색},{theme.나_색2});color:white;'
        f'display:flex;align-items:center;justify-content:center;'
        f'font-size:16px;font-weight:800;">{num}</div>'
    )


@ui.page("/")
async def home_page() -> None:
    if not await auth.require_login():
        return
    theme.inject_head()
    with theme.page_frame("home"):
        # ── 히어로 (우상단에 백엔드 상태 배지를 겹쳐서 빈 공간 없이 채움) ──
        ok = backend_available()
        theme.hero(
            "사고 과실 비율 AI 가이드",
            "사고 상황을 말씀해 주시면 공식 인정기준 근거를 찾아 예상 과실비율을 계산해 드립니다.",
            badge_html=theme.status_pill_html(ok, "백엔드 연결됨", "로컬 검색 모드"),
        )

        ui.link("💬 지금 바로 상담 시작하기", "/consult").classes(
            "fr-nav-link fr-btn-primary"
        ).style("display:inline-flex; width:auto; margin-top:4px; padding:10px 20px; color:white !important;")

        # ── 우리는 이런 서비스예요 (크게, 전체 폭) ──────────────────
        ui.html('<div class="fr-section-title" style="margin-top:32px;">🚦 우리는 이런 서비스예요</div>')

        docs = standards()
        counts = Counter(d.get("source_id", "") for d in docs)
        with ui.row().classes("w-full no-wrap").style("gap:16px"):
            with ui.element("div").classes("fr-card").style("flex:1.3;"):
                ui.markdown("**📊 지식베이스 현황**")
                ui.label(f"총 {len(docs)}건").classes("text-4xl font-extrabold").style(
                    f"color:{theme.나_색}; margin-top:6px;"
                )
                ui.label("의 공식 인정기준 도표를 근거로 씁니다").classes(
                    "text-sm text-gray-500"
                )
                with ui.row().classes("w-full no-wrap").style("gap:20px; margin-top:14px;"):
                    for source_id, n in counts.most_common():
                        with ui.column().classes("gap-0"):
                            ui.label(str(n)).classes("text-xl font-extrabold").style(
                                f"color:{theme.나_색};"
                            )
                            ui.label(source_label(source_id)).classes(
                                "text-xs text-gray-500"
                            )

            with ui.element("div").classes("fr-card").style(
                f"flex:1; display:flex; flex-direction:column; justify-content:center; "
                f"background:linear-gradient(135deg,{theme.나_색}10,{theme.나_색2}10);"
            ):
                ui.markdown("**📚 지식베이스 직접 검색하기**")
                ui.label("상담 없이 도표·판례·법령을 바로 검색해볼 수 있어요.").classes(
                    "text-sm text-gray-500"
                )
                ui.link("지식베이스로 이동 →", "/kb").classes("fr-nav-link").style(
                    "display:inline-flex; width:auto; margin-top:8px; padding-left:0;"
                    f"color:{theme.나_색}; font-weight:700;"
                )

        ui.html('<div class="fr-section-title" style="margin-top:28px;">▶ 이용 방법</div>')
        with ui.row().classes("w-full no-wrap").style("gap:16px"):
            for num, title, desc in STEPS:
                with ui.element("div").classes("fr-card").style("flex:1;"):
                    with ui.row().classes("items-center no-wrap").style("gap:10px;"):
                        _num_badge(num)
                        ui.label(title).classes("font-bold").style("font-size:1.05rem;")
                    ui.label(desc).classes("text-sm text-gray-500").style("margin-top:4px;")

        ui.separator().classes("my-4")
        theme.disclaimer()
