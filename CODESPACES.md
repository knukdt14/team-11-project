# GitHub Codespaces 실행

Codespace를 생성하면 `.devcontainer/devcontainer.json`이 Docker와 포트 8000·8501을 준비합니다.

```bash
cd ryeol
docker compose up --build -d
docker compose ps -a
curl http://localhost:8000/health
```

기본 모드는 GPU가 필요 없는 `LLM_MODE=mock`, `SEARCH_RERANK=false`입니다. Chroma·BM25 RAG, 과실 계산, 법령·사례, 세션, 재계산은 실제 기능이며 마지막 자연어 설명만 정형 문장을 사용합니다.

화면은 Codespaces의 **PORTS** 탭에서 `Streamlit`(8501)을 여세요. 로컬 PC의 `localhost:8501`을 직접 여는 방식이 아닙니다. FastAPI Swagger는 전달된 8000 포트의 `/docs`입니다.

GPU PC에서는 Codespaces 설정이 아니라 아래 로컬 명령을 사용합니다.

```powershell
cd ryeol
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```
