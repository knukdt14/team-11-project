# 2번(오현택) 인수인계 — 검색·평가

> **넘기는 것**: 질문을 넣으면 근거 도표 후보가 나오는 검색기 + 성능 측정 도구
> **받는 사람**: 3번(정우렬) — API 연결 / 4번(전승우) — 화면 표시
> **위치**: `taek/` · 사용법 상세는 [`taek/README.md`](../taek/README.md), 실험 근거는 [`taek/EVAL.md`](../taek/EVAL.md)

---

## ⚠️ 먼저 알아야 할 3가지

### 1. import 경로가 바뀌었습니다

```python
from hani.search import Searcher     # ❌ 예전 안내
from taek.search import Searcher     # ✅ 지금
```

역할 경계에 맞춰 검색·평가를 `taek/` 으로 분리했습니다.
`hani/` 는 데이터 파이프라인(PDF→청크→인덱스), `taek/` 는 검색입니다.
데이터는 `hani/data/processed/` 를 **읽기 전용**으로 씁니다.

실행은 **저장소 루트에서 `-m`** 으로 합니다. `cd taek && python search.py` 는 안 됩니다.

### 2. A/B 를 직접 뒤집지 마세요

도표의 `A`·`B` 는 **도표 고정 당사자**입니다(A=보행자·자전거·PM, B=자동차).
서비스의 `A`·`B` 는 **상담자·상대**입니다. 상담자가 자동차면 뒤집어야 합니다.

뒤집기는 `hani.party.to_consultant_view()` **한 곳에서만** 일어납니다.
`taek/adapter.py` 가 이미 그걸 호출하므로, 3번은 `consultant_side` 만 넘기면 됩니다.

> 두 곳에서 뒤집으면 원위치로 돌아와 **오류 없이 조용히 틀립니다.** 가장 잡기 어려운 버그입니다.

### 3. 심의사례의 A/B 는 도표의 A/B 와 다릅니다

```
도표 : A = 보행자·자전거·PM 등   B = 자동차
사례 : A = 청구인               B = 피청구인   ← 사건마다 뒤바뀜
```

그래서 사례는 `to_consultant_view()` 에 **넣지 않습니다.** 원문 표기를 그대로 노출합니다.
게다가 226건 중 **90건이 기본비율 ≠ 결정비율**이고 현행 도표 매핑이 전부 미완이라,
**참고 표시용이지 계산에 쓰면 안 됩니다.**

---

## 바로 쓰는 법 (3번)

```python
from taek.search import Searcher
from taek.adapter import to_consult_payload, to_case_cards, to_law_cards

searcher = Searcher()          # ⚠️ FastAPI lifespan 에서 1회만. 모델 로딩이 무겁습니다.

hits = searcher.search(질문, mode="hybrid", reject=True, expand=True)
payload = to_consult_payload(hits, consultant_side="A")

if payload["경고"]:
    return payload             # 해당 기준 없음 — 최종과실 None, 되묻기[] 포함
```

`payload` 에 들어 있는 것:

```
도표번호 · 제목 · 출처 · 나_역할 · 상대_역할 · 기본과실{A,B}
수정요소[{조건, 대상, 값, 적용됨, 근거}] · 후보[] · 해설 · 사고상황
판례[] · 법조항[] · image_url · pdf_page · 검수필요
최종과실 = None   ← 3번의 apply_modifiers() 가 채웁니다
```

**숫자는 검색이 만들지 않습니다.** 기본과실과 수정요소 목록까지만 넘깁니다.

참고 사례·법조항:

```python
to_case_cards(searcher.cases(질문))              # 참고용 배지 필수
to_law_cards(searcher.laws_for(payload["법조항"]))
```

### 후보 없음 판정

`reject=True` 면 범위 밖 질문에 **빈 리스트**를 반환합니다.
그게 곧 README §11 의 `"경고": "해당 기준을 찾을 수 없습니다"` + `최종과실: null` 입니다.

거절 못 하는 유형이 있습니다 — `사거리에서 좌회전하다가 사고났습니다` 처럼
**진짜 교차로 사고인데 정보가 부족한** 질문입니다. 이건 검색 실패가 아니라
**되묻기로 넘겨야 할 대상**입니다. `payload["되묻기"]` 에 기본 질문 3개를 넣어 뒀으니
3번이 사고유형에 맞게 다듬어 쓰시면 됩니다.

---

## 1번(이한이)에게 인계받아 바꾼 것

`git log --follow` 로 원저작이 추적됩니다.

| 파일 | 원저작 | 2번이 한 것 |
|---|---|---|
| `search.py` | 1번 — 기본 벡터 검색 | 하이브리드·거절 판정·라우팅·부모 병합 분리 |
| `evaluate.py` | 1번 — 지표 계산 | 복수 정답(`;`)·모드 스위치·`matched_gold` |
| `gold_queries.csv` | 1번 — 80문항 작성 | 라벨 3건 정정 (근거는 `EVAL.md` §EXP-1) |
| `bm25.py` `synonyms.py` `rerank.py` `adapter.py` `sweep.py` `validate_k.py` `paths.py` | — | 2번 신규 |

파서 버그 2건(보행자 도표 수정요소 당사자 오배정, 해설 누락·오염)도 인계받아 고쳤습니다.
이건 이미 `main` 에 머지됐습니다(이슈 #4·#5).

---

## 현재 성능

평가셋 80문항(정답 64 / 정답 없음 16).

| 구성 | Top-1 | Top-3 | Top-10 | MRR | 오답 방지 |
|---|---:|---:|---:|---:|---:|
| 벡터 단독 (시작점) | 32.8% | 51.6% | 73.4% | 0.447 | 0.0% |
| + RRF 융합 | 39.1% | 60.9% | 84.4% | 0.526 | 0.0% |
| + 거절 임계값 | 39.1% | 60.9% | 82.8% | 0.523 | 81.2% |
| + 질의 확장 | 42.2% | 64.1% | 84.4% | 0.558 | 81.2% |
| + 메타 필터 | 46.9% | 65.6% | 87.5% | 0.593 | 81.2% |
| **+ 리랭킹** | **54.7%** | **79.7%** | **92.2%** | **0.670** | **81.2%** |

리랭킹은 **기본 OFF** 입니다. CPU 에서 요청당 6.9초라 GPU 없는 환경에서는 못 씁니다.
GPU(RTX 4070)에서는 0.494초로 시연 가능합니다. 3번이 환경 보고 켜세요.

```python
hits = searcher.search(질문, mode="hybrid", reject=True, expand=True, rerank=True)
```

### 이 숫자를 발표에 쓸 때 반드시 함께 말할 것

- **통계적 유의성은 없습니다.** 64문항으로는 이 정도 차이의 신뢰구간이 0을 포함합니다.
  "재표집 96%에서 우세했으나 유의성은 주장할 수 없다"가 정확한 표현입니다.
- **하이퍼파라미터를 같은 평가셋에서 골랐습니다.** 낙관 편향은 반분 검증으로 +0.4%p로 측정했습니다. 작지만 0은 아닙니다.
- **평가셋 작성자가 1번 한 사람**입니다. 3·4번 문항이 오면 **설정을 고정한 채** 다시 재세요.

---

## 왜 이렇게 만들었나 (설명 필요할 때)

**RRF `k=1`** — 원논문 관례값은 60입니다. 60은 검색기를 수십 개 융합할 때 합의로 잡음을 거르는 값입니다.
우리는 검색기가 2개이고 **64문항 중 21문항을 한쪽만** 맞힙니다. 합의를 중시하면 그 21문항을 스스로 눌러버립니다.

**거절은 AND** — 벡터와 BM25가 **모두** 약할 때만 거절합니다. 각각 단독으로는 정답을 3~8건 잃는데,
AND 로 묶으면 **손실 0으로 81.2%** 를 거릅니다. 두 신호가 서로 다른 것을 놓치기 때문입니다.

**거절 판정은 원본 질의로** — 질의 확장은 문서 어휘를 덧붙이므로 범위 밖 질문의 점수까지 올립니다.
확장 질의로 게이트를 재면 오답 방지가 81.2% → 75.0% 로 떨어집니다.
*"이 질문이 우리 범위인가"* 는 사용자가 실제로 쓴 말로 판단해야 합니다.

**라우팅은 부스트, 필터 아님** — 특수기준(PM·회전교차로) 키워드가 있으면 해당 문서 전용 랭킹을
하나 더 만들어 RRF 에 넣습니다. 키워드가 잘못 걸려도 일반 랭킹이 살아 있어 결과가 무너지지 않습니다.
`회전` 만 쓰면 좌회전·우회전에 걸려 오탐이 19건이 되니 반드시 `회전교차로` 로 쓰세요.

---

## 아직 안 된 것

| | 내용 |
|---|---|
| 심의사례 매핑 | 226건 전부 `mapping_status="review_required"`. 현행 도표와 연결 안 됨 |
| 재검증 | 3·4번 평가 문항 도착 시 전 설정 고정한 채 재측정 |
| 4번과 협의 | 참고 사례 배지·검수필요 도표 표시 방식 |

---

## 재현

```bash
conda activate team-11-project        # Python 3.13
python -m taek.evaluate --mode hybrid --reject --expand --rerank   # 최종 구성
python -m taek.evaluate --mode hybrid --reject --expand            # 리랭킹 없이 (CPU용)
python -m taek.sweep                                      # 설정 18종 비교
python -m taek.validate_k                                 # k 선택 통계 검증
python -m taek.search "뒤에서 오던 차가 제 차를 들이받았어요"
```

> 💡 **GPU 가 있으면** 리랭킹이 6.87초 → 0.494초가 됩니다. 검색 결과는 동일합니다.
> ```
> pip install --no-deps --force-reinstall --index-url https://download.pytorch.org/whl/cu126 torch==2.13.0
> ```
> `requirements.txt` 는 고치지 마세요 — 버전이 같아서 핀은 그대로 유효하고,
> GPU 없는 팀원은 기본 설치로 CPU 를 받아야 합니다.

> ⚠️ **Python 3.12 미만은 안 됩니다.** 코드가 f-string 안에서 백슬래시를 쓰는데
> PEP 701(3.12+) 문법입니다. 3.11 에서는 `SyntaxError` 로 죽습니다.

> ⚠️ `hani/` 에서 `build_chunks.py` 를 돌렸으면 **`build_vector.py` 도** 돌리세요.
> 안 그러면 문서와 벡터가 어긋난 채로 검색이 조용히 돌아갑니다.
> (`Searcher` 가 chunks 지문을 대조해 경고를 띄웁니다.)

## 파일

```
taek/
├── search.py       Searcher — vector / bm25 / hybrid / wsum + 거절 · 라우팅
├── bm25.py         문자 2~3-gram BM25
├── rerank.py       cross-encoder 리랭킹 (기본 OFF · GPU 권장)
├── synonyms.py     질의 확장 사전 (동결 — 점수 보고 고치면 과적합)
├── adapter.py      Hit → API 계약 변환   ★ 3번이 쓰는 지점
├── paths.py        hani/data 참조 단일 소스
├── evaluate.py     지표 측정
├── sweep.py        설정 비교
├── validate_k.py   부트스트랩 · 반분 검증
├── gold_queries.csv  평가셋 80문항
├── EVAL.md         실험 기록 (모든 수치의 근거)
├── README.md       사용 설명서
└── results/        실험별 상세 CSV
```
