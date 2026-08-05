# 실행 방법

> **팀원은 이 문서만 따라 하면 됩니다.** 5분이면 검색까지 확인됩니다.

---

## 0. Docker로 웹 전체 실행

GPU가 없는 PC와 GitHub Codespaces를 포함해 기본 명령은 동일합니다.

```bash
cd ryeol
docker compose up --build -d
```

기본 구성은 실제 RAG·계산·세션과 mock 설명을 사용합니다. Streamlit은 8501, FastAPI Swagger는 8000 포트입니다.

NVIDIA GPU PC에서 Qwen과 GPU 리랭킹까지 사용하려면:

```bash
cd ryeol
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

Codespaces의 자세한 실행법은 [`CODESPACES.md`](CODESPACES.md)를 참고하세요.

---

## 1. 가상환경 만들기 (최초 1회)

팀 전원이 **같은 파이썬(3.13) · 같은 패키지 버전**을 씁니다.
버전이 다르면 `vector_index/` 를 못 읽거나 검색 결과가 달라집니다.

### conda (권장 — 파이썬 버전까지 고정됩니다)

```bash
conda create -n team-11-project python=3.13 -y
```

```bash
conda activate team-11-project
```

```bash
pip install -r requirements.txt
```

### conda가 없다면 venv

```bash
py -3.13 -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
```

> ⚠️ **3.12 미만은 쓰지 마세요.** 코드가 f-string 안에서 백슬래시를 쓰는데
> 이건 **3.12(PEP 701) 이상에서만** 되는 문법입니다. 3.11에서는 `SyntaxError` 로 죽습니다.

---

## 2. 설치 확인

```bash
python -c "import fitz, pydantic, chromadb, sentence_transformers, fastapi, streamlit; print('OK')"
```

---

## 3. 검색 돌려보기

`hani/data/processed/` 에 청크·벡터 인덱스가 이미 커밋돼 있으므로 **PDF 없이 바로 검색됩니다.**

```bash
python -m taek.search "뒤에서 오던 차가 제 차를 들이받았어요"
```

기대 결과 — 상위에 `차41-1 양 차량 주행 중 후방 추돌` 계열이 나옵니다.

> 🕐 **처음 실행할 때만** 임베딩 모델(`BAAI/bge-m3`, 약 2.2GB)을 내려받습니다. 이후로는 캐시를 씁니다.

---

## 4. 검색 성능 측정

```bash
python -m taek.evaluate
```

Top-1 / Top-3 / MRR / 오답 방지율이 나오고 `taek/results/eval_vector.csv` 에 상세가 저장됩니다.
BM25로 재보려면 `--mode bm25` (→ `eval_bm25.csv`).

**검색을 손보기 전에 먼저 돌려서 기준선을 남기세요.** 그래야 개선인지 후퇴인지 알 수 있습니다.
실험 기록과 지금까지의 결과는 [taek/EVAL.md](taek/EVAL.md) 에 있습니다.

---

## 5. 백엔드에서 검색 모듈 쓰기

`hani`(데이터) 와 `taek`(검색) 두 패키지입니다. **저장소 루트에서** import 하세요.

```python
from taek.search import Searcher
from hani.party import to_consultant_view, describe

searcher = Searcher()                     # ⚠️ FastAPI lifespan에서 1회만 생성
hits = searcher.search("신호 없는 교차로에서 좌회전 차와 충돌")

payload = hits[0].payload
print(describe(payload))                  # "이 기준에서 A는 …, B는 … 본인이 어느 쪽인지 선택하세요"

view = to_consultant_view(payload, consultant_side="A")   # 상담자가 A인지 B인지
print(view["나_역할"], view["기본과실"])
```

**A/B를 직접 뒤집지 마세요.** `to_consultant_view()` 한 곳에서만 뒤집습니다.
두 곳에서 뒤집으면 원위치로 돌아와 조용히 틀립니다. 자세한 규칙은 `hani/party.py` 참조.

---

## 6. 데이터를 다시 만들어야 할 때 (파서를 고친 사람만)

원본 PDF는 저작권 때문에 저장소에 없습니다. 직접 받아 `pdf/` 에 넣으세요.

```bash
cd hani && python build_all.py
```

부분 실행:

```bash
python parse_pdf.py extract "../pdf/230630_자동차사고 과실비율 인정기준_최종.pdf" --source-id MAIN2023
```

```bash
python extract_images.py "../pdf/230630_자동차사고 과실비율 인정기준_최종.pdf" --source-id MAIN2023
```

```bash
python build_chunks.py && python build_vector.py
```

> ⚠️ `parse_pdf.py extract` 는 interim JSONL을 덮어쓰면서 `diagram_image` 필드를 지웁니다.
> **`extract_images.py` 를 반드시 이어서 실행**하세요.
>
> ⚠️ `build_chunks.py` 를 돌렸으면 **`build_vector.py` 도 돌려야** 합니다.
> 안 그러면 문서와 벡터가 어긋난 채로 검색이 조용히 돌아갑니다.
> (`taek/search.py` 가 chunks 지문을 대조해 경고를 띄웁니다.)

---

## 자주 겪는 문제

| 증상 | 원인 · 해결 |
|---|---|
| `임베딩 모델 불일치` 로 중단 | 인덱스와 다른 모델로 질의한 것. `EMBEDDING_MODEL` 을 맞추거나 `vector_index/` 를 지우고 `build_vector.py` |
| `chunks.jsonl 이 인덱스를 만든 뒤에 바뀌었습니다` 경고 | `build_vector.py` 실행 |
| `벡터 인덱스가 없습니다` | `hani/data/processed/vector_index/` 가 받아졌는지 확인 (Git LFS 아님, 일반 커밋) |
| 모델 다운로드가 느림 | 최초 1회만. `EMBEDDING_DEVICE=cpu` 로 GPU 없이도 동작 |
| GPU가 있는데 CPU로 돈다 | 아래 §7 참조. 검색 결과는 동일하고 속도만 달라집니다 |
| 리랭킹이 너무 느림 | CPU에서 요청당 ~6.9초입니다. GPU로 바꾸거나 `rerank=False`(기본값)로 쓰세요 |

---

## 7. GPU 쓰기 (선택)

`requirements.txt` 의 torch 는 **CPU 빌드**입니다. 팀 전원이 한 파일로 동일하게 설치되도록
일부러 그렇게 뒀습니다. GPU가 있으면 각자 교체하세요.

```bash
pip install --no-deps --force-reinstall --index-url https://download.pytorch.org/whl/cu126 torch==2.13.0
```

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

버전이 `2.13.0` 으로 같아서 **`requirements.txt` 를 고칠 필요가 없습니다.**

측정된 차이 (요청 1건, 후보 20개):

| | 리랭킹 OFF | 리랭킹 ON |
|---|---:|---:|
| CPU | ~0.57s | 6.87s |
| GPU (RTX 4070 Laptop) | 0.098s | 0.494s |

**검색 결과는 완전히 동일합니다.** 속도만 달라집니다.
