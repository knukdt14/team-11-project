"""
CV 데모 — Streamlit 최소 버전 (되는 것부터).

흐름: 영상 업로드 → 사고 프레임 추출(박스) → Gemini+RAG 과실 판정 → 시각화
실행: streamlit run app/streamlit_cv.py  (프로젝트 루트에서)

먼저 되는지 확인용. 예쁘게는 나중에 HTML로 옮김.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="교통사고 과실비율 분석", layout="wide")
st.title("🚗 교통사고 과실비율 자동 분석")
st.caption("블랙박스 영상 업로드 → 사고 순간 감지 → 인정기준 근거로 과실 판정")

# --- 무거운 객체는 한 번만 로드 ---
@st.cache_resource
def load_tools():
    from services.cv.track import Tracker
    from taek.search import Searcher
    return Tracker(), Searcher()

uploaded = st.file_uploader("사고 영상 업로드 (mp4)", type=["mp4", "avi", "mov"])

if uploaded:
    # 업로드 영상을 임시파일로 저장
    tmp = Path(tempfile.mkdtemp())
    video_path = tmp / uploaded.name
    video_path.write_bytes(uploaded.read())

    st.video(str(video_path))

    if st.button("분석 시작", type="primary"):
        from services.cv.extract import extract_evidence
        from services.cv.gemini_fault import assess_fault

        tracker, searcher = load_tools()

        # 1) 사고 프레임 추출
        with st.spinner("사고 순간 감지 + 프레임 추출 중..."):
            out_dir = tmp / "frames"
            ev = extract_evidence(video_path, out_dir, tracker=tracker)

        if not ev["is_accident"]:
            st.warning("사고 순간을 감지하지 못했습니다.")
            st.stop()

        st.success(f"사고 감지! (사고 순간: {ev['impact_frame']}번 프레임)")

        # 2) 프레임 시각화 (wow 포인트)
        st.subheader("📸 사고 근거 프레임")
        paths = ev["frame_paths"]
        cols = st.columns(min(len(paths), 4))
        for i, p in enumerate(paths):
            with cols[i % len(cols)]:
                is_impact = "impact" in Path(p).name
                st.image(p, use_container_width=True)
                if is_impact:
                    st.markdown("**⚡ 충돌 순간**")
                else:
                    st.caption(Path(p).stem)

        # 3) Gemini + RAG 과실 판정
        with st.spinner("인정기준 검색 + 과실 판정 중 (Gemini)..."):
            result = assess_fault(paths, searcher)

        if "error" in result:
            st.error(result["error"])
            st.stop()

        # 4) 결과 표시
        st.subheader("⚖️ 과실비율 판정")
        과실 = result.get("과실", {})
        본인 = 과실.get("본인", 0)
        상대 = 과실.get("상대", 0)

        c1, c2 = st.columns([1, 2])
        with c1:
            # 도넛 차트
            try:
                import plotly.graph_objects as go
                fig = go.Figure(go.Pie(
                    labels=["본인", "상대"], values=[본인, 상대],
                    hole=0.5, marker_colors=["#ff6b6b", "#4dabf7"]))
                fig.update_layout(showlegend=True, height=250, margin=dict(t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.metric("본인 과실", f"{본인}%")
                st.metric("상대 과실", f"{상대}%")
        with c2:
            st.markdown(f"### 본인 {본인}% : 상대 {상대}%")
            st.markdown(f"**상황**: {result.get('상황','')}")
            st.markdown(f"**근거 도표**: {result.get('근거도표','')}")
            st.markdown(f"**설명**: {result.get('설명','')}")
            st.info(result.get("주의", ""))

        with st.expander("검색된 인정기준 후보"):
            for label in result.get("후보기준", []):
                st.write("•", label)