# 프론트엔드(Streamlit) 이미지.
#
# ⚠️ 백엔드(3번 FastAPI)가 아직 없어서, 이 이미지 혼자서도 상담이 되도록
#    hani/taek 코드와 requirements.txt 전체(torch·chromadb 등 포함)를 넣습니다.
#    나중에 backend 컨테이너가 생기면 이 이미지는 streamlit·plotly·requests만
#    남기고 훨씬 가볍게 줄일 수 있습니다 — components/api.py 가 backend_available()로
#    자동 전환하므로 로컬 폴백 코드는 그대로 둬도, 없애도 무방합니다.
#
# 빌드는 반드시 저장소 루트를 컨텍스트로 잡아야 합니다:
#   docker build -f woo/Dockerfile -t fault-ratio-frontend .
# 또는 docker-compose.yml 로 실행하세요.

FROM python:3.13-slim

WORKDIR /app

# 이미지 레이어 캐싱: 의존성 설치를 코드 복사보다 먼저.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hani/ ./hani/
COPY taek/ ./taek/
COPY woo/ ./woo/
COPY .streamlit/ ./.streamlit/

ENV BACKEND_URL=http://backend:8000 \
    EMBEDDING_DEVICE=cpu \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "woo/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
