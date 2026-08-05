import os
import requests
import streamlit as st

API = os.getenv("BACKEND_URL", "http://backend:8000")
st.title("Team 11 상담 API 통합 점검")
try:
    health = requests.get(f"{API}/health", timeout=10).json()
    st.success(f"FastAPI 연결 · 검색: {health['search_ready']} · LLM: {health['llm_mode']}")
except Exception as exc:
    st.error(f"FastAPI 연결 실패: {exc}")

description = st.text_area("사고 상황", "신호 없는 교차로에서 직진 중 좌회전 차량과 충돌했습니다.")
side = st.selectbox("도표에서 내 위치", ["A", "B"])
if st.button("상담 요청"):
    with st.spinner("검색 및 Qwen 설명 생성 중..."):
        response = requests.post(f"{API}/consult", json={"사고설명": description, "상담자측": side}, timeout=240)
    st.write("HTTP", response.status_code)
    st.json(response.json())
