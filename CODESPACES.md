# GitHub Codespaces 실행

Codespace를 생성하면 `.devcontainer/devcontainer.json`이 Docker와 포트 8000·8501을 준비합니다.

저장소 루트에서:

```bash
docker compose up --build -d
docker compose ps -a
curl http://localhost:8000/health
```

기본 모드는 GPU가 필요 없는 `LLM_MODE=mock`, `SEARCH_RERANK=false`입니다. Chroma·BM25 RAG, 과실 계산, 법령·사례, 세션, 재계산은 실제 기능이며 마지막 자연어 설명만 정형 문장을 사용합니다.

프론트엔드는 실제 팀 대시보드(`woo/`)가 뜹니다 — `ryeol/frontend_smoke`는 3번(정우렬)의 API 스모크테스트 전용이라 여기서는 사용하지 않습니다.

화면은 Codespaces의 **PORTS** 탭에서 `Streamlit`(8501)을 여세요. 로컬 PC의 `localhost:8501`을 직접 여는 방식이 아닙니다. FastAPI Swagger는 전달된 8000 포트의 `/docs`입니다.

## GPU 없이 실제 AI 설명 문장 받기 (선택)

`LLM_MODE=mock`은 설명 문장이 정형 문구로 고정됩니다. [Google AI Studio](https://aistudio.google.com/)에서 무료 Gemini API 키를 받으면, GPU 없이도(Codespaces 포함) 실제 AI가 쓴 설명을 받을 수 있습니다.

```bash
GEMINI_API_KEY=발급받은키 LLM_MODE=gemini docker compose up --build -d
```

검색 정밀 재정렬(`SEARCH_RERANK`)은 이 키와 무관한 별도 기능이며, CPU에서 느려서 계속 꺼져 있습니다.

## GPU가 있는 PC

EXAONE 실답변과 GPU 리랭킹까지 쓰려면 Codespaces 설정 대신 이걸 실행하세요.

```powershell
docker compose -f docker-compose.gpu.yml up --build -d
```
