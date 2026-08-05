# 3번(정우렬) 인수인계 — 과실 계산·상담 API

위치: `ryeol/`

## 완료

- FastAPI lifespan에서 `taek.search.Searcher` 1회 초기화
- `/consult`: hybrid + reject + expand + 선택적 GPU rerank
- `taek.adapter`를 통한 단일 A/B 변환
- `apply_modifiers()` 결정론적 계산(합계 100, 범위 제한, 중복 방지)
- `/recalculate`: 검색·LLM 없는 즉시 재계산
- `/follow-up`, `/sessions/{id}`: SQLite 영속 세션과 대화 이력
- `/consult/additional-info`: 되묻기 답변 병합 후 실제 RAG 재검색
- 수정요소별 안정적인 `id`와 사고유형 `대/중/소` 계약
- 심의사례는 참고용으로만 반환하고 계산에서 제외
- 도표 법조항 직접 조회 및 Qwen3:8b 근거 설명
- Qwen 실패 시 계산 결과를 보존하는 정형 문장 폴백
- Docker Compose 백엔드·최소 프론트·Ollama 통합 환경
- Backend GPU 리랭커, HF 캐시, Qwen 자동 다운로드
- `docker compose up --build` CPU·Codespaces 기본 실행과 GPU override 분리
- 계산·세션·상담·재계산·HTTP 계약 테스트
- 실제 RAG 대표 사고 5건 및 실제 Qwen 전체 흐름 검증

## 4번 연결 지점

Swagger `http://localhost:8000/docs`를 API 계약으로 사용합니다. 수정요소 체크박스는 `/recalculate`를 호출하며 `/consult`나 LLM을 다시 호출하지 않습니다. 심의사례에는 반드시 `참고용` 배지를 표시하세요.

## 4번이 할 일

- `frontend_smoke`에서 검증한 호출을 최종 Streamlit 디자인에 옮기기
- `needs_information`일 때 되묻기 화면, `complete`일 때 게이지·근거·수정요소 화면 표시
- 수정요소 `id`를 체크박스 값으로 사용해 `/recalculate` 호출
- 심의사례 참고용 배지와 검수필요 경고 표시

CV는 현재 범위에서 제외했습니다.
