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
    analyze_video_evidence,
    assess_fault_from_evidence,
    make_annotated_video_bytes,
    transcode_bytes_for_browser,
)
from woo.components.widgets import hero, inject_css, mascot_say, ratio_hero, sidebar_nav  # noqa: E402

st.set_page_config(page_title="영상 분석 · 과실비율", page_icon="🎥", layout="wide")
inject_css()
sidebar_nav("video")
hero(
    "🎥 CCTV 영상 분석",
    "교차로 CCTV 사고 영상을 올리면 차량 검출·추적·궤적·충돌 지점을 화면에 그려서 보여드립니다.",
)

st.session_state.setdefault("cv_result", None)
st.session_state.setdefault("cv_video_path", None)
st.session_state.setdefault("cv_fps", 10.0)

if st.session_state["cv_result"] is None:
    mascot_say("안녕하세요! 저는 사고 조사관이에요 🔍 교차로 CCTV 영상을 올려주시면 제가 차량을 하나하나 추적해서 충돌 순간을 찾아드릴게요.")

uploaded = st.file_uploader("사고 영상 업로드", type=["mp4", "avi", "mov"])

if uploaded is not None:
    # ⚠️ 업로드 영상이 FMP4(구형 MPEG-4) 코덱이면 브라우저 <video> 태그가 아예
    # 재생을 못 해서 검은 화면(0:00)만 보였습니다 — H.264로 다시 인코딩해서 보여줍니다.
    # 분석 자체(OpenCV 읽기)는 원본 코덱 그대로 문제없이 되므로 분석에는 안 씁니다.
    with st.spinner("미리보기용으로 변환 중..."):
        preview_bytes = transcode_bytes_for_browser(uploaded.getvalue(), Path(uploaded.name).suffix)
    if preview_bytes:
        st.video(preview_bytes)
    else:
        st.caption("⚠️ 이 영상은 브라우저 미리보기로 변환하지 못했습니다 (분석은 정상 진행됩니다).")

if uploaded is not None and st.button("🔍 분석 시작", type="primary", use_container_width=True):
    # ⚠️ NamedTemporaryFile(delete=False)를 씁니다 — services/cv의 Tracker.track_video는
    # 실제 "파일 경로"를 받아 cv2.VideoCapture로 여는데, delete=True(기본값)면 파일이
    # 닫히자마자 지워져서 그 경로를 못 엽니다. 이 임시 파일은 세션 동안만 쓰고
    # OS가 알아서 정리하도록 남겨둡니다. out_dir(근거 프레임 저장 폴더)도 마찬가지로
    # TemporaryDirectory(with문)를 쓰면 이 블록이 끝나자마자 지워져서 화면에 못 보여주니
    # mkdtemp()로 세션 동안 남겨둡니다.
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
        tmp.write(uploaded.getvalue())
        video_path = tmp.name
    out_dir = tempfile.mkdtemp()

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    cap.release()

    # ⚠️ hani가 검증한 extract_evidence()를 그대로 씁니다(왜인지는 아래 함수 docstring 참고)
    # — 화면에 보여주는 프레임과 AI 판정에 넣는 프레임이 항상 동일하다는 것도 보장됩니다.
    with st.spinner("영상 분석 중입니다 (차량 검출·추적)... 영상 길이에 따라 시간이 걸릴 수 있어요"):
        result = analyze_video_evidence(video_path, out_dir)

    st.session_state["cv_result"] = result
    st.session_state["cv_video_path"] = video_path
    st.session_state["cv_fps"] = fps
    st.rerun()

if st.session_state["cv_result"] is not None:
    result = st.session_state["cv_result"]
    fps = st.session_state["cv_fps"]

    if not result["is_accident"]:
        mascot_say("음... 이 영상에서는 사고 신호를 찾지 못했어요 🤔 다른 영상으로 시도해보시겠어요?")
        st.warning("이 영상에서는 사고 신호가 감지되지 않았습니다.")
    else:
        impact = result["impact_frame"]
        mascot_say(
            f"찾았어요! **{impact}번째 프레임**(약 {impact / fps:.1f}초 지점)에서 부딪힌 것 같아요 ⚡ "
            "아래에서 근거 프레임을 직접 확인해보세요."
        )
        st.success(f"✅ 사고 감지됨 — 충돌 순간: {impact}프레임 (약 {impact / fps:.1f}초)")

        st.markdown("**🎬 YOLO 추적 영상**")
        # ⚠️ 근거 프레임 추출과 별개로 영상 전체를 다시 한 번 추적합니다(계산량 있음) —
        # 그래서 자동이 아니라 버튼으로만 돌립니다. 박스가 계속 따라다니는 영상 + 충돌
        # 순간 빨간 테두리는 근거 프레임(정지 이미지)보다 한눈에 훨씬 잘 들어옵니다.
        if st.button("🎬 추적 영상 만들기", use_container_width=True):
            with st.spinner("영상 전체에 박스 추적 그리는 중... (조금 걸립니다)"):
                annotated_bytes = make_annotated_video_bytes(st.session_state["cv_video_path"])
            if annotated_bytes:
                st.video(annotated_bytes)
                st.caption("차량에 박스가 따라다니며, 빨간 테두리가 충돌 순간입니다.")
            else:
                st.caption("⚠️ 추적 영상을 브라우저 재생용으로 변환하지 못했습니다.")

        st.markdown("**📸 사고 근거 프레임**")
        paths = result["frame_paths"]
        cols = st.columns(min(len(paths), 4) or 1)
        for i, p in enumerate(paths):
            with cols[i % len(cols)]:
                is_impact = "impact" in Path(p).name
                st.image(p, use_container_width=True)
                st.markdown("**⚡ 충돌 순간**" if is_impact else f"`{Path(p).stem}`")

        st.write("")
        st.markdown("**⚖️ AI 과실비율 판정**")
        # ⚠️ hani의 assess_fault()는 GEMINI_API_KEY가 없으면 RuntimeError를 던집니다
        # (환경변수 없이 조용히 mock으로 넘어가지 않음) — 여기서 잡아서 "키가 없어서
        # 못 돌렸다"를 명확히 보여줍니다. woo/.env에 GEMINI_API_KEY=... 한 줄만 추가하면
        # 다음 실행부터 자동으로 픽업됩니다(api.py의 _load_local_env 재사용).
        if st.button("🧠 AI로 과실비율까지 판정하기", use_container_width=True):
            try:
                with st.spinner("Gemini + 인정기준 검색으로 과실 판정 중..."):
                    fault = assess_fault_from_evidence(result["frame_paths"])
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
                    mascot_say(f"영상이랑 인정기준을 같이 살펴보니, 본인 {본인}% : 상대 {상대}%로 보여요. 자세한 이유는 아래에 적어뒀어요 👇")
                    st.markdown(ratio_hero(본인, 상대, "본인", "상대"), unsafe_allow_html=True)
                    st.markdown(f"**상황**: {fault.get('상황', '')}")
                    st.markdown(f"**근거 도표**: {fault.get('근거도표', '')}")
                    st.markdown(f"**설명**: {fault.get('설명', '')}")
                    st.info(fault.get("주의", ""))
                    if fault.get("후보기준"):
                        with st.expander("검색된 인정기준 후보"):
                            for label in fault["후보기준"]:
                                st.write("•", label)
