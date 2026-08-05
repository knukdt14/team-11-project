# 3번(정우렬) 인수인계 — 과실 계산·상담 API

위치: `ryeol/`

## 완료

- FastAPI lifespan에서 `taek.search.Searcher` 1회 초기화
- `/consult`: hybrid + reject + expand + 선택적 GPU rerank
- `taek.adapter`를 통한 단일 A/B 변환
- `apply_modifiers()` 결정론적 계산(합계 100, 범위 제한, 중복 방지)
- `/recalculate`: 검색·LLM 없는 즉시 재계산
- `/follow-up`, `/sessions/{id}`: 메모리 세션과 대화 이력
- 심의사례는 참고용으로만 반환하고 계산에서 제외
- 도표 법조항 직접 조회 및 Qwen3:8b 근거 설명
- Qwen 실패 시 계산 결과를 보존하는 정형 문장 폴백
- Docker Compose 백엔드·최소 프론트·Ollama 통합 환경
- 계산·세션·상담·재계산 테스트

## 4번 연결 지점

Swagger `http://localhost:8000/docs`를 API 계약으로 사용합니다. 수정요소 체크박스는 `/recalculate`를 호출하며 `/consult`나 LLM을 다시 호출하지 않습니다. 심의사례에는 반드시 `참고용` 배지를 표시하세요.

## 남은 협업

- 4번 최종 Streamlit UI를 `frontend_smoke` 대신 Compose에 연결
- 운영 환경에서는 메모리 세션을 Redis/DB로 교체
- 3·4번 검색 평가 질문을 추가한 뒤 2번 설정을 고정한 재평가
- CV가 추가되면 CV의 후보를 사용자 확인 후 `/consult` 입력으로 변환
