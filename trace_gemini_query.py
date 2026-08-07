"""
1차 Gemini 쿼리 추적 — 프레임을 Gemini에 붙였을 때
  (1) 어떤 프롬프트 + 이미지를 넘기는지
  (2) Gemini가 어떤 상황/검색쿼리를 돌려주는지
를 터미널에 그대로 출력한다.

실행 (프로젝트 루트 team-11-project 에서):
    python trace_gemini_query.py
    python trace_gemini_query.py --video CarCrash/videos/Crash-1500/000044.mp4

필요: GEMINI_API_KEY 환경변수 (또는 아래 직접 입력),  google-genai
"""
import os
import sys
import json
import argparse
from pathlib import Path

# ── 루트 경로 잡기 (services / taek import 되게) ─────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from google import genai
from google.genai import types

from services.cv.extract import extract_evidence
from services.cv.gemini_fault import _client, _load_images, MODEL
from services.cv.gemini_fault import _situation  # 실제 파이프라인이 쓰는 함수


def hr(title=""):
    print("\n" + "=" * 60)
    if title:
        print(f" {title}")
        print("=" * 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=r"C:\Users\KDT005\Desktop\CV_DATA\CarCrash\videos\Crash-1500\000044.mp4")
    ap.add_argument("--out", default="trace_frames")
    ap.add_argument("--api_key", default=None, help="안 주면 GEMINI_API_KEY 환경변수 사용")
    args = ap.parse_args()

    # API 키 (환경변수 없으면 여기 직접 넣어도 됨)
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] GEMINI_API_KEY 없음. 환경변수로 넣거나 --api_key 로 전달하세요.")
        sys.exit(1)

    hr("STEP 1. 사고 프레임 추출")
    print(f"입력 영상: {args.video}")
    ev = extract_evidence(args.video, args.out)
    if not ev["is_accident"]:
        print("사고 미감지 → 종료")
        sys.exit(0)
    print(f"충돌 순간 프레임: {ev['impact_frame']}")
    print(f"추출된 근거 프레임 {len(ev['frame_paths'])}장:")
    for p in ev["frame_paths"]:
        print("   -", p)

    # ── 1차 Gemini에 넘어가는 '입력' 그대로 재현 ──────────────
    hr("STEP 2. 1차 Gemini에 넘기는 입력 (PROMPT + 이미지)")
    prompt = (
        "다음은 교통사고 블랙박스 영상에서 뽑은 연속 프레임입니다. "
        "차량 위치와 진행 방향을 보고 사고 상황을 한국어로 간결히 파악하세요. "
        "과실비율은 아직 판단하지 말고, 아래 JSON만 출력하세요:\n"
        '{"상황":"사고 상황 한 문장","검색쿼리":"인정기준 검색용 짧은 한국어 문구"}'
    )
    print("[PROMPT] 텍스트로 넘기는 지시문:\n")
    print(prompt)
    print(f"\n[IMAGES] 함께 넘기는 이미지: {min(len(ev['frame_paths']), 6)}장 (jpeg 바이트)")

    # ── 실제 호출 ────────────────────────────────────────────
    hr("STEP 3. Gemini 호출 → 응답(raw)")
    client = _client(api_key)
    image_parts = _load_images(ev["frame_paths"])   # 파이프라인과 동일하게 로드
    resp = client.models.generate_content(
        model=MODEL,
        contents=[prompt, *image_parts],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    print(f"모델: {MODEL}")
    print("응답 원문(raw text):\n")
    print(resp.text)

    # ── 파싱된 결과 (실제로 다음 단계에 넘어가는 값) ──────────
    hr("STEP 4. 파싱된 결과 = RAG 검색에 넘어가는 값")
    try:
        parsed = json.loads(resp.text)
    except Exception:
        # gemini_fault의 관대한 파서로 재시도
        from services.cv.gemini_fault import _parse_json_lenient
        parsed = _parse_json_lenient(resp.text)

    상황 = parsed.get("상황", "")
    검색쿼리 = parsed.get("검색쿼리", "")
    print(f"상황     : {상황}")
    print(f"검색쿼리 : {검색쿼리}   ← 이 문자열이 taek Searcher.search()로 넘어감")

    # ── 그 쿼리로 실제 검색까지 (Gemini 호출 없음, 무료) ──────
    hr("STEP 5. 검색쿼리 → RAG 검색 결과 (인정기준 도표)")
    try:
        from taek.search import Searcher
        searcher = Searcher()
        hits = searcher.search(검색쿼리 or 상황, top_k=3)
        for h in hits:
            print("   •", h.label)
    except Exception as e:
        print(f"[검색 생략/실패] {e}")

    hr("완료")


if __name__ == "__main__":
    main()