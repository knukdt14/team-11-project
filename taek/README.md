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
python -m taek.evaluate --mode bm25
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
| `evaluate.py` | Top-1·3·10 / MRR / 오답 방지율 측정 |
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

## 3번(정우렬)에게

```python
from taek.search import Searcher
from hani.party import to_consultant_view, describe

searcher = Searcher()          # ⚠️ FastAPI lifespan 에서 1회만 생성
hits = searcher.search("신호 없는 교차로에서 좌회전 차와 충돌")

payload = hits[0].payload
print(describe(payload))
view = to_consultant_view(payload, consultant_side="A")
```

**A/B를 직접 뒤집지 마세요.** `to_consultant_view()` 한 곳에서만 뒤집습니다.

> 📌 이전 안내가 `from hani.search import Searcher` 였습니다. **`taek.search` 로 바뀌었습니다.**

---

## 현재 성능 · 다음 작업

| | Top-1 | Top-3 | MRR |
|---|---:|---:|---:|
| 벡터 (BGE-m3) | 64.3% | **78.6%** | 0.717 |
| BM25 | 50.0% | 57.1% | 0.554 |

다음 우선순위와 근거는 `EVAL.md` 하단 참조. 요약하면 —
**하이브리드보다 동의어 처리(EXP-8)가 먼저**입니다. 남은 실패 3건이 전부
랭킹이 아니라 어휘 불일치(`차선↔차로`, `킥보드↔PM`)이기 때문입니다.
