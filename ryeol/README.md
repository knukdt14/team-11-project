# 3번 정우렬 — 과실 계산·상담 API

1·2번 산출물을 FastAPI에 연결합니다. 숫자는 `apply_modifiers()`만 계산하며 Qwen은 계산된 결과를 설명만 합니다.

## 실행

```powershell
cd ryeol
Copy-Item .env.example .env
docker compose up --build -d
```

이 기본 명령은 GPU가 없는 PC와 Codespaces에서 실행됩니다. 실제 RAG·계산을 사용하고 자연어 설명만 mock입니다.

GPU PC에서 Qwen과 리랭커까지 활성화하려면:

```powershell
Copy-Item .env.gpu.example .env -Force
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

GPU 구성에서는 `ollama-init`이 `qwen3:8b`를 최초 1회 자동 다운로드합니다. BGE·Qwen 모델과 세션은 Docker 볼륨에 보존됩니다.

- API 문서: http://localhost:8000/docs
- 상태 확인: http://localhost:8000/health
- 프론트 연동 점검: http://localhost:8501

- `POST /consult`: 하이브리드 검색, A/B 변환, 계산, 사례·법령 조회, Qwen 설명, 세션 저장
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

실제 검증 결과: 대표 사고 5건 RAG 성공, Backend CUDA 리랭커 활성화, 실제 Qwen 응답 성공, HTTP·계산·세션 테스트 통과.
