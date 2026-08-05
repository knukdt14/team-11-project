# 3번 정우렬 — 과실 계산·상담 API

1·2번 산출물을 FastAPI에 연결합니다. 숫자는 `apply_modifiers()`만 계산하며 LLM은 계산된 결과를 설명만 합니다.

LLM 기본 정책은 `Gemini → EXAONE → 정형 템플릿`입니다. Gemini가 정상일 때는 Gemini를 사용하고, API 키 누락·무료 한도 초과(HTTP 429)·타임아웃·API 오류가 발생하면 Ollama의 `exaone3.5:2.4b`로 자동 전환합니다. EXAONE도 실패해도 계산과 RAG 결과는 유지하고 정형 설명을 반환합니다.

## 실행

```powershell
cd ryeol
Copy-Item .env.example .env
docker compose up --build -d
```

통합 UI를 포함한 실행은 저장소 루트에서 다음 명령을 사용합니다.

```powershell
Copy-Item ryeol/.env.example .env
# .env에 GEMINI_API_KEY 입력
docker compose up --build -d
```

Docker의 Ollama는 사용 가능한 장치에 맞춰 실행되며, GPU가 없어도 동일한 Compose 명령을 사용할 수 있습니다. EXAONE은 Gemini 장애 시에만 호출되므로 평상시 응답 속도는 Gemini 기준입니다.

`ollama-init`이 `exaone3.5:2.4b`를 최초 1회 자동 다운로드하며 모델과 세션은 Docker 볼륨에 보존됩니다.

- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health
- 프론트 연동 점검: http://localhost:8501

- `POST /consult`: 하이브리드 검색, A/B 변환, 계산, 사례·법령 조회, Gemini/EXAONE 설명, 세션 저장
- `POST /consult/additional-info`: 되묻기 답변을 기존 사고설명에 합쳐 같은 세션으로 재검색
- `POST /recalculate`: LLM 없이 즉시 재계산
- `POST /follow-up`: 기존 상담 근거와 대화 이력을 사용한 후속 질문
- `GET /sessions/{session_id}`: 프론트의 대화 이력 복원

```powershell
python -m pytest ryeol/tests -q
```

심의사례는 참고용이며 계산에 사용하지 않습니다. A/B 변환은 `hani.party.to_consultant_view()` 한 곳에서만 수행됩니다.

## 4번 UI 연결 계약

1. `/consult`의 `status`가 `needs_information`이면 `되묻기[]`를 표시하고 최종과실을 표시하지 않습니다.
2. 추가 답변은 `/consult/additional-info`로 보냅니다.
3. 수정요소 체크박스의 값은 `조건` 문자열이 아니라 안정적인 `id`를 사용합니다.
4. 체크박스 변경 시 `/recalculate`만 호출합니다. 검색과 LLM은 다시 호출하지 않습니다.
5. `유사사례[].참고용=true`는 반드시 참고용 배지와 함께 표시합니다.
6. `검수필요` 또는 `신뢰도=낮음`인 도표는 경고 배지를 표시합니다.

자동 폴백은 Gemini 성공, Gemini 실패 후 EXAONE 성공, 두 모델 실패 후 템플릿 반환의 세 경로를 단위 테스트합니다.
