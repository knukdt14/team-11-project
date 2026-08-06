"""교차로 CCTV 사고 영상 업로드 → 검출·추적·궤적·충돌지점 시각화 페이지.

실제 계산(YOLO 검출·추적·사고판단)은 services/cv(hani 담당)를 그대로 호출만 하고,
그 결과를 화면에 그려서 보여주는 부분만 새로 만들었습니다(woo/components/cv_pipeline.py
참고). README §2·3에 나온 대로 대시캠(블랙박스)이 아니라 고정 카메라로 찍힌 교차로
CCTV 영상을 전제로 합니다 — 대시캠은 자차 궤적을 관측할 수 없어 분석 대상이 아닙니다.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from woo.components.cv_pipeline import analyze_video, render_annotated_frames  # noqa: E402
from woo.components.widgets import hero, inject_css, sidebar_nav  # noqa: E402

st.set_page_config(page_title="영상 분석 · 과실비율", page_icon="🎥", layout="wide")
inject_css()
sidebar_nav("video")
hero(
    "🎥 CCTV 영상 분석",
    "교차로 CCTV 사고 영상을 올리면 차량 검출·추적·궤적·충돌 지점을 화면에 그려서 보여드립니다.",
)

st.info(
    "⚠️ 대시캠(블랙박스) 영상은 자차 시점이라 궤적 분석이 어렵습니다 — "
    "**고정 카메라로 촬영된 교차로 CCTV 영상**을 올려주세요.",
    icon="📹",
)

st.session_state.setdefault("cv_result", None)
st.session_state.setdefault("cv_video_path", None)
st.session_state.setdefault("cv_fps", 10.0)

uploaded = st.file_uploader("사고 영상 업로드", type=["mp4", "avi", "mov"])

if uploaded is not None and st.button("🔍 분석 시작", type="primary", use_container_width=True):
    # ⚠️ NamedTemporaryFile(delete=False)를 씁니다 — services/cv의 Tracker.track_video는
    # 실제 "파일 경로"를 받아 cv2.VideoCapture로 여는데, delete=True(기본값)면 파일이
    # 닫히자마자 지워져서 그 경로를 못 엽니다. 이 임시 파일은 세션 동안만 쓰고
    # OS가 알아서 정리하도록 남겨둡니다.
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
        tmp.write(uploaded.getvalue())
        video_path = tmp.name

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    cap.release()

    with st.spinner("영상 분석 중입니다 (차량 검출·추적)... 영상 길이에 따라 시간이 걸릴 수 있어요"):
        result = analyze_video(video_path)

    st.session_state["cv_result"] = result
    st.session_state["cv_video_path"] = video_path
    st.session_state["cv_fps"] = fps
    st.rerun()

if st.session_state["cv_result"] is not None:
    result = st.session_state["cv_result"]
    fps = st.session_state["cv_fps"]

    if not result["is_accident"]:
        st.warning("이 영상에서는 사고 신호가 감지되지 않았습니다.")
    else:
        impact = result["impact_frame"]
        st.success(f"✅ 사고 감지됨 — 충돌 순간: {impact}프레임 (약 {impact / fps:.1f}초)")

        frames = render_annotated_frames(
            st.session_state["cv_video_path"], result["frames_boxes"], impact, fps=fps,
        )
        st.markdown("**궤적·충돌 지점 시각화** (파란 선: 이동 궤적 · 빨간 별: 충돌 지점)")
        cols = st.columns(4)
        for i, (idx, img) in enumerate(frames):
            with cols[i % 4]:
                caption = f"프레임 {idx}" + (" (충돌 순간)" if idx == impact else "")
                st.image(
                    cv2.cvtColor(img, cv2.COLOR_BGR2RGB),
                    caption=caption,
                    use_container_width=True,
                )
