"""
Gemini + RAG 과실 판정.  (방식 α — hani 인정기준 도표를 근거로 사용)

흐름:
  1) Gemini 1차: 사고 프레임 이미지들을 보고 사고 상황을 파악,
     인정기준 검색에 쓸 한국어 쿼리를 만든다.
  2) taek Searcher: 그 쿼리로 인정기준 도표를 검색 (A:B 기본과실 + 근거).
  3) Gemini 2차: 이미지 + 검색된 도표를 함께 주고,
     이 도표를 근거로 최종 과실비율과 설명을 생성.

CV(extract)가 뽑은 frame_paths 만 넣으면 된다.
과실 판단의 '근거'는 hani 도표에서 나온다 (Gemini가 지어내지 않게 프롬프트로 제약).

필요: pip install google-genai
      환경변수 GEMINI_API_KEY (Google AI Studio 무료 발급)
"""
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# 어느 진입점(streamlit_cv.py, woo/, 단독 스크립트)에서 import되든 .env를 자동으로
# 읽도록 모듈 로드 시점에 한 번 로드한다. 이 파일 기준 두 단계 위(repo 루트)의 .env.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

MODEL = "gemini-flash-lite-latest"   # 이미지 판단 + 무료 티어 (flash 대비 TPM 30배 여유)


def _parse_json_lenient(text):
    """flash-lite가 완전한 JSON 뒤에 문장 조각을 더 흘려보내는 경우가 있어서,
    첫 번째 완전한 JSON 객체만 파싱하고 뒤에 붙는 쓰레기는 무시한다."""
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text.strip())
    return obj


def _client(api_key=None):
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 없음. Google AI Studio에서 무료 발급 후 환경변수로.")
    return genai.Client(api_key=key)


def _load_images(frame_paths, max_n=6):
    """프레임 이미지들을 Gemini Part로. 너무 많으면 앞·중간·뒤에서 골라 max_n장."""
    paths = list(frame_paths)
    if len(paths) > max_n:
        # 고르게 샘플링 (사고 전·순간·후가 다 들어가게)
        idx = [round(i * (len(paths) - 1) / (max_n - 1)) for i in range(max_n)]
        paths = [paths[i] for i in sorted(set(idx))]
    parts = []
    for p in paths:
        with open(p, "rb") as f:
            parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))
    return parts


def _situation(client, image_parts):
    """1차: 이미지 → 사고 상황 파악 + 검색 쿼리."""
    prompt = (
        "다음은 교통사고 블랙박스 영상에서 뽑은 연속 프레임입니다. "
        "차량 위치와 진행 방향을 보고 사고 상황을 한국어로 간결히 파악하세요. "
        "과실비율은 아직 판단하지 말고, 아래 JSON만 출력하세요:\n"
        '{"상황":"사고 상황 한 문장","검색쿼리":"인정기준 검색용 짧은 한국어 문구"}'
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt, *image_parts],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return _parse_json_lenient(resp.text)


def _final(client, image_parts, situation, hits):
    """2차: 이미지 + 검색된 도표 → 최종 과실 + 설명."""
    # 검색된 인정기준을 근거 텍스트로 정리
    기준목록 = []
    for h in hits:
        r = h.payload.get("base_ratio") or {}
        기준목록.append({
            "도표": h.payload.get("diagram_no", ""),
            "제목": h.payload.get("title", ""),
            "기본과실": f"A{r.get('a','?')}:B{r.get('b','?')}",
            "설명": h.text[:200],
        })

    prompt = (
        "교통사고 과실비율 상담입니다. 아래 '검색된 인정기준'의 사실만 근거로 쓰세요. "
        "기준에 없는 법령·판례·숫자를 지어내지 마세요.\n\n"
        f"사고 상황: {situation.get('상황','')}\n"
        f"검색된 인정기준: {json.dumps(기준목록, ensure_ascii=False)}\n\n"
        "이미지와 위 기준을 종합해 아래 JSON만 출력하세요:\n"
        '{"과실":{"본인":숫자,"상대":숫자},"근거도표":"도표번호",'
        '"설명":"왜 이 비율인지 2~3문장","주의":"실제 판단은 증거·사실에 따라 달라질 수 있음"}'
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt, *image_parts],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return _parse_json_lenient(resp.text)


def assess_fault(frame_paths, searcher, api_key=None, top_k=3):
    """
    frame_paths : extract_evidence 결과의 frame_paths (박스 그려진 사고 프레임)
    searcher    : taek.search.Searcher 인스턴스 (hani RAG)
    반환: dict {상황, 검색쿼리, 후보기준[list], 과실{본인,상대}, 근거도표, 설명, 주의,
                image_path, pdf_page, 법조항[list], 유사사례[list]}
    """
    if not frame_paths:
        return {"error": "프레임 없음 (사고 미감지)"}

    client = _client(api_key)
    image_parts = _load_images(frame_paths)

    # 1) 상황 파악 + 검색 쿼리
    sit = _situation(client, image_parts)

    # 2) hani RAG 검색
    hits = searcher.search(sit.get("검색쿼리", sit.get("상황", "")), top_k=top_k)

    # 3) 최종 판정
    result = _final(client, image_parts, sit, hits)

    # 상황·후보도 함께 반환 (화면 근거 표시용)
    result["상황"] = sit.get("상황", "")
    result["검색쿼리"] = sit.get("검색쿼리", "")
    result["후보기준"] = [h.label for h in hits]

    # ── 근거자료 보강: 상담탭(/consult)은 근거도표 이미지·관련 법조항·유사 심의사례를
    # 같이 보여주는데, 영상분석은 "과실{본인,상대}" 숫자와 설명 문장만 나가서 근거가
    # 빠져 있었습니다. Gemini가 고른 근거도표(result["근거도표"])와 매칭되는 검색
    # hit을 찾아 같은 방식(taek.adapter)으로 변환해 붙입니다 — 새 로직을 만들지 않고
    # 상담탭이 쓰는 변환 함수를 그대로 재사용합니다.
    from taek.adapter import to_case_cards, to_law_cards

    matched = next(
        (h for h in hits if h.payload.get("diagram_no") == result.get("근거도표")), None
    ) or (hits[0] if hits else None)
    result["법조항"] = []
    if matched:
        p = matched.payload
        result["image_path"] = p.get("image_path")
        result["pdf_page"] = p.get("source_page")
        try:
            result["법조항"] = to_law_cards(searcher.laws_for(p.get("laws", [])))
        except Exception:  # noqa: BLE001 — 법조항 조회 실패해도 나머지 결과는 그대로 보여줍니다.
            pass

    try:
        result["유사사례"] = to_case_cards(
            searcher.cases(sit.get("검색쿼리") or sit.get("상황", ""))
        )
    except Exception:  # noqa: BLE001 — 유사사례 조회 실패해도 나머지 결과는 그대로 보여줍니다.
        result["유사사례"] = []

    return result