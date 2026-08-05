# 3번 정우렬 — 과실 계산·상담 API

1·2번 산출물을 FastAPI에 연결합니다. 숫자는 `apply_modifiers()`만 계산하며 Qwen은 계산된 결과를 설명만 합니다.

## 실행

```powershell
cd ryeol
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec ollama ollama pull qwen3:8b
docker compose restart backend
```

- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health
- 프론트 연동 점검: http://localhost:8501

- `POST /consult`: 하이브리드 검색, A/B 변환, 계산, 사례·법령 조회, Qwen 설명, 세션 저장
- `POST /recalculate`: LLM 없이 즉시 재계산
- `POST /follow-up`: 기존 상담 근거와 대화 이력을 사용한 후속 질문
- `GET /sessions/{session_id}`: 프론트의 대화 이력 복원

```powershell
python -m pytest ryeol/tests -q
```

심의사례는 참고용이며 계산에 사용하지 않습니다. A/B 변환은 `hani.party.to_consultant_view()` 한 곳에서만 수행됩니다.
