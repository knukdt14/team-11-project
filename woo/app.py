"""홈 — 서비스 소개, 예시 질문 카드, 백엔드 연결 상태 배지."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from woo.components.api import backend_available, health_info  # noqa: E402
from woo.components.widgets import (  # noqa: E402
    disclaimer,
    hero,
    inject_css,
    status_pill,
    topnav,
)

st.set_page_config(
    page_title="과실비율 상담 대시보드",
    page_icon="🚦",
    layout="wide",
)
inject_css()
topnav("home")

top_l, top_r = st.columns([4, 1])
with top_l:
    hero(
        "🚦 사고 영상으로 보는 과실비율 대시보드",
        "사고 상황을 말씀해 주시면 공식 인정기준 근거를 찾아 예상 과실비율을 계산해 드립니다.",
    )
with top_r:
    st.write("")
    st.write("")
    ok = backend_available()
    st.markdown(
        status_pill(ok, "백엔드 연결됨", "로컬 검색 모드"),
        unsafe_allow_html=True,
    )
    if ok:
        info = health_info()
        if info:
            with st.popover("상태 상세"):
                st.json(info, expanded=False)
    else:
        with st.popover("왜 로컬 모드죠?"):
            st.caption(
                "3번 담당의 FastAPI 백엔드가 아직 없거나 꺼져 있어요. "
                "지금은 hani/taek 검색을 직접 불러와 동작합니다.\n\n"
                "`BACKEND_URL` 환경변수로 주소를 바꿀 수 있어요 (기본 http://localhost:8000)."
            )

st.markdown('<div class="fr-section-title">💡 예시로 바로 시작해보기</div>', unsafe_allow_html=True)

examples = [
    ("🚗", "신호 없는 교차로에서 직진하다 좌회전 차와 부딪혔어요"),
    ("🌙", "야간에 뒤에서 오던 차가 제 차를 추돌했어요"),
    ("🛴", "전동킥보드로 직진하는데 신호 없는 교차로에서 좌회전 차가 들이받았어요"),
]

cols = st.columns(len(examples))
for col, (emoji, ex) in zip(cols, examples, strict=False):
    with col:
        with st.container(border=True):
            st.markdown(
                f'<div class="fr-example-card">'
                f'<div style="font-size:1.6rem;">{emoji}</div>'
                f'<div class="fr-example-q">{ex}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("이 예시로 상담하기", key=f"ex_{ex}", use_container_width=True):
                st.session_state["prefill_query"] = ex
                st.switch_page("pages/2_상담.py")

st.write("")
st.page_link("pages/2_상담.py", label="✏️ 직접 상황을 입력해서 상담하기", icon="💬")

st.write("")
with st.container(border=True):
    st.markdown("**📚 지식베이스 둘러보기**")
    st.caption("상담 없이 도표·판례·법령을 바로 검색해볼 수 있어요.")
    st.page_link("pages/3_지식베이스.py", label="지식베이스로 이동", icon="📚")

st.divider()
disclaimer()
