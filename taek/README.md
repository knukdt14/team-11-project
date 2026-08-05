# taek — 검색 · 평가 (2번 · 오현택)

역할표 §14의 **2번: 검색 성능·근거 검색** 담당 모듈입니다.

```
hani/   PDF → JSONL → 청크 → 벡터 인덱스     (1번 · 데이터 파이프라인)
taek/   질문 → 후보 도표 → 성능 측정          (2번 · 검색)
```

데이터는 `hani/data/processed/` 를 **읽기 전용**으로 씁니다. 경로는 `paths.py` 한 곳에만 있습니다.

---

## 실행 (저장소 루트에서)

```bash
python -m taek.search "뒤에서 오던 차가 제 차를 들이받았어요"
```

```bash
python -m taek.bm25 "회전교차로 차로변경"
```

```bash
python -m taek.evaluate --mode hybrid --reject --expand    # 권장 구성
python -m taek.sweep                                       # 설정 비교표
python -m taek.validate_k                                  # k 선택 통계 검증
```

> ⚠️ `cd taek && python search.py` 는 동작하지 않습니다.
> `hani` 를 cross-import 하므로 **루트에서 `-m` 으로** 돌려야 합니다.

---

## 파일

| 파일 | 내용 |
|---|---|
| `paths.py` | `hani/data` 참조 단일 소스. 데이터 위치가 바뀌면 **여기만** 고칩니다 |
| `search.py` | `Searcher` — 면(facet) 검색 → 부모(도표) 병합. `mode="vector"\|"bm25"` |
| `bm25.py` | 문자 2~3-gram 토크나이저 + BM25 색인 |
| `synonyms.py` | 질의 확장 사전 (킥보드→PM 등). **동결** — 점수 보고 고치면 과적합 |
| `adapter.py` | **`Hit` → README §11 API 계약 변환 (3번 인도 지점)** |
| `evaluate.py` | Top-1·3·10 / MRR / 오답 방지율 측정 |
| `sweep.py` | 설정 18종 일괄 비교 |
| `validate_k.py` | 부트스트랩 신뢰구간 · 반분 선택 검증 |
| `gold_queries.csv` | 평가셋 20문항 (정답 14 / 정답 없음 6) |
| `EVAL.md` | **실험 기록 — EXP-0~2 결과와 판단 근거** |
| `results/` | 실험별 상세 CSV (`eval_vector.csv`, `eval_bm25.csv`) |

---

## 인계 사실 (출처 표기)

이 폴더의 일부는 **1번(이한이)이 먼저 만든 것을 인계받아 확장**한 것입니다.
`git log --follow` 로 원저작 히스토리가 그대로 추적됩니다.

| 파일 | 원저작 | 2번이 한 것 |
|---|---|---|
| `search.py` | 1번 — 기본 벡터 검색 | `mode` 분기 · `_merge_to_parent()` 분리 · `cases()` · 인덱스 지문 검사 |
| `evaluate.py` | 1번 — 지표 계산 | **복수 정답(`;`) 지원** · `--mode` · `matched_gold` 컬럼 |
| `gold_queries.csv` | 1번 — 20문항 작성<br/>*(원래 4명 공통 업무)* | 라벨 3건 정정 (근거는 `EVAL.md` §EXP-1) |
| `bm25.py` · `paths.py` · `EVAL.md` | — | 2번 신규 |

---

## 3번(정우렬)에게 — 이것만 쓰시면 됩니다

```python
from taek.search import Searcher
from taek.adapter import to_consult_payload, to_case_cards, to_law_cards

searcher = Searcher()          # ⚠️ FastAPI lifespan 에서 1회만 생성

hits = searcher.search(질문, mode="hybrid", reject=True, expand=True)
payload = to_consult_payload(hits, consultant_side="A")   # 상담자가 A인지 B인지

if payload["경고"]:            # 거절됨 = "해당 기준을 찾을 수 없습니다"
    return {**payload}         # 최종과실 None, 되묻기[] 가 들어 있습니다

# payload 에 도표번호·기본과실·수정요소·후보·해설·판례·법조항·image_url 이 들어 있습니다.
# ⚠️ 최종과실은 None 입니다 — 숫자는 3번의 apply_modifiers() 만 만듭니다.
```

참고 사례와 법조항:

```python
to_case_cards(searcher.cases(질문))            # ⚠️ 참고용. 계산 금지
to_law_cards(searcher.laws_for(payload["법조항"]))
```

**A/B를 직접 뒤집지 마세요.** `adapter.py` 가 `hani.party.to_consultant_view()` 한 곳으로만 넘깁니다.
두 곳에서 뒤집으면 원위치로 돌아와 조용히 틀립니다.

> ⚠️ **심의사례의 A/B 는 도표의 A/B 와 다릅니다.**
> 도표: A = 보행자·자전거·PM 등 / B = 자동차
> 사례: A = 청구인 / B = 피청구인 — **사건마다 뒤바뀝니다.**
> 그래서 사례는 `to_consultant_view()` 에 넣지 않고 원문 표기를 그대로 노출합니다.

> 📌 이전 안내가 `from hani.search import Searcher` 였습니다. **`taek.search` 로 바뀌었습니다.**

---

## 현재 성능

평가셋 80문항(정답 64 / 정답 없음 16) 기준.

| 구성 | Top-1 | Top-3 | Top-10 | MRR | 오답 방지 |
|---|---:|---:|---:|---:|---:|
| 벡터 단독 (시작점) | 32.8% | 51.6% | 73.4% | 0.447 | 0.0% |
| BM25 단독 | 29.7% | 56.2% | 78.1% | 0.454 | 0.0% |
| + RRF 융합 (k=1) | 39.1% | 60.9% | 84.4% | 0.526 | 0.0% |
| + 거절 임계값 | 39.1% | 60.9% | 82.8% | 0.523 | 81.2% |
| + 질의 확장 | 42.2% | 64.1% | 84.4% | 0.558 | 81.2% |
| **+ 메타 필터 정책** | **46.9%** | **65.6%** | **87.5%** | **0.593** | **81.2%** |

**Top-3 +14.0%p · MRR +0.146 · 오답 방지 0% → 81.2%.**
근거와 실험 과정은 [`EVAL.md`](EVAL.md).

### ⚠️ 해석 시 주의

- 64문항으로는 이 차이를 **통계적으로 유의하다고 주장할 수 없습니다** (신뢰구간이 0을 포함).
- 하이퍼파라미터(`k`·임계값)를 **같은 평가셋에서 골랐습니다.** 낙관 편향은 +0.4%p로 작지만 0은 아닙니다.
- 평가셋 작성자가 1번 한 사람입니다. 3·4번 문항이 오면 **설정을 고정한 채 다시 재세요.**

## 남은 작업

| | |
|---|---|
| EXP-7 | cross-encoder 리랭킹 — 하이브리드 상한 70.3% 중 남은 여지 |
| — | 심의사례 ↔ 현행 도표 매핑 (226건 전부 `review_required`) |
| — | 3·4번 평가 문항 도착 후 전 설정 재검증 |
