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

from woo.components.cv_pipeline import (  # noqa: E402
    analyze_video,
    assess_fault_from_video,
    render_annotated_frames,
)
from woo.components.widgets import hero, inject_css, ratio_hero, sidebar_nav  # noqa: E402

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

        st.write("")
        st.markdown("**⚖️ AI 과실비율 판정**")
        # ⚠️ hani의 assess_fault()는 GEMINI_API_KEY가 없으면 RuntimeError를 던집니다
        # (환경변수 없이 조용히 mock으로 넘어가지 않음) — 여기서 잡아서 "키가 없어서
        # 못 돌렸다"를 명확히 보여줍니다. woo/.env에 GEMINI_API_KEY=... 한 줄만 추가하면
        # 다음 실행부터 자동으로 픽업됩니다(api.py의 _load_local_env 재사용).
        if st.button("🧠 AI로 과실비율까지 판정하기", use_container_width=True):
            with tempfile.TemporaryDirectory() as frame_dir:
                try:
                    with st.spinner("근거 프레임 추출 + Gemini 과실 판정 중..."):
                        fault = assess_fault_from_video(
                            st.session_state["cv_video_path"], frame_dir,
                        )
                except RuntimeError as exc:
                    st.error(f"⚠️ AI 과실 판정을 실행할 수 없습니다: {exc}")
                    st.caption(
                        "woo/.env 파일에 `GEMINI_API_KEY=발급받은키` 한 줄을 추가하면 됩니다 "
                        "(Google AI Studio에서 무료 발급)."
                    )
                else:
                    if "error" in fault:
                        st.warning(fault["error"])
                    else:
                        본인 = fault.get("과실", {}).get("본인", 0)
                        상대 = fault.get("과실", {}).get("상대", 0)
                        st.markdown(ratio_hero(본인, 상대, "본인", "상대"), unsafe_allow_html=True)
                        st.markdown(f"**상황**: {fault.get('상황', '')}")
                        st.markdown(f"**근거 도표**: {fault.get('근거도표', '')}")
                        st.markdown(f"**설명**: {fault.get('설명', '')}")
                        st.info(fault.get("주의", ""))
                        if fault.get("후보기준"):
                            with st.expander("검색된 인정기준 후보"):
                                for label in fault["후보기준"]:
                                    st.write("•", label)
