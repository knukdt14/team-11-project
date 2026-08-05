import os
import requests
import streamlit as st

API = os.getenv("BACKEND_URL", "http://backend:8000")
st.title("Team 11 상담 API 통합 점검")

try:
    health = requests.get(f"{API}/health", timeout=10).json()
    st.success(f"FastAPI 연결 · 검색: {health['search_ready']} · LLM: {health['llm_mode']} · 리랭킹: {health['rerank']}")
except Exception as exc:
    st.error(f"FastAPI 연결 실패: {exc}")

description = st.text_area("사고 상황", "신호 없는 교차로에서 직진 중 좌회전 차량과 충돌했습니다.")
side = st.selectbox("검색 도표에서 내 위치", ["A", "B"])
if st.button("상담 요청", type="primary"):
    with st.spinner("RAG 검색 및 Qwen 설명 생성 중..."):
        response = requests.post(f"{API}/consult",
            json={"사고설명": description, "상담자측": side}, timeout=300)
    st.session_state.result = response.json()

result = st.session_state.get("result")
if result:
    st.write("상태", result.get("status"))
    if result.get("경고"):
        st.warning(result["경고"])
    if result.get("되묻기"):
        for question in result["되묻기"]:
            st.info(question)
        additional = st.text_input("추가정보")
        if st.button("추가정보 반영 후 다시 검색") and additional:
            response = requests.post(f"{API}/consult/additional-info", json={
                "session_id": result["session_id"], "추가정보": additional}, timeout=300)
            st.session_state.result = response.json()
            st.rerun()
    if result.get("최종과실"):
        ratio = result["최종과실"]
        st.metric("내 과실", f"{ratio['A']}%", help=f"상대 과실 {ratio['B']}%")
        modifiers = result.get("적용_수정요소", []) + result.get("미적용_수정요소", [])
        selected = [m["id"] for m in modifiers if st.checkbox(
            f"{m['조건']} ({m['대상']} {m['값']:+d})", value=m.get("적용됨", False), key=m["id"])]
        if st.button("선택한 수정요소로 재계산"):
            recalculated = requests.post(f"{API}/recalculate", json={
                "session_id": result["session_id"], "적용할_수정요소": selected}, timeout=30)
            st.json(recalculated.json())
        st.subheader("근거 기반 설명")
        st.write(result.get("답변"))
        with st.expander("전체 API 응답"):
            st.json(result)
