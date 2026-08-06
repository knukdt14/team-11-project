"""과실비율 대시보드 — Flask 프론트엔드.

목업 HTML/CSS/JS를 그대로 서빙합니다. 상담·재계산·후속질문·세션은 이미 동작하는
ryeol FastAPI(기본 http://localhost:8000)를 브라우저 JS가 직접 호출합니다(CORS 허용됨) —
여기서 다시 구현하지 않습니다.

이 Flask 앱은 ryeol에 없는 것만 API로 감쌉니다:
  - /api/kb/list, /api/kb/<id>   → hani/data/processed/payloads.json (kb_data.py 재사용)
  - /api/stats                   → 위와 동일 소스로 집계
  - /api/video/analyze           → services/cv (hani가 만든 YOLO+Gemini 파이프라인) 재사용

실행 (저장소 루트에서):
    python -m flaskapp.app
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from woo.components.kb_data import load_payloads, source_label, standards  # noqa: E402

HANI_DATA = REPO_ROOT / "hani" / "data"
TMP_FRAMES = Path(__file__).resolve().parent / "static" / "tmp"
TMP_FRAMES.mkdir(parents=True, exist_ok=True)


def _transcode_for_browser(video_path: str) -> bytes | None:
    """브라우저 호환 코덱(H.264)으로 재인코딩 (imageio-ffmpeg 정적 바이너리 사용).

    webapp/services/cv_pipeline.py의 transcode_for_browser()와 동일한 방식 —
    hani의 make_annotated_video()가 만드는 mp4v 코덱은 크롬/엣지에서 재생이
    안 되는 경우가 있어서, ffmpeg로 libx264로 다시 인코딩합니다.
    """
    import subprocess

    import imageio_ffmpeg

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        out_path = tmp.name
    cmd = [
        ffmpeg_exe, "-y", "-i", str(video_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        out_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        return Path(out_path).read_bytes()
    except Exception:
        return None
    finally:
        Path(out_path).unlink(missing_ok=True)

app = Flask(__name__)
# ⚠️ 개발 중 static/js/app.js·css를 자주 고치는데, 브라우저가 캐시해둔 예전 파일을
# 계속 쓰는 바람에 "고쳤는데도 예전 동작 그대로"인 혼란이 반복됐습니다(영상 재생 버튼을
# 눌렀는데 파일선택창이 열리던 것도 예전 app.js 캐시였을 가능성이 높음) — 캐시를 아예 끕니다.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.get("/media/<path:relpath>")
def media(relpath: str):
    """hani/data/ 안의 파일만 안전하게 서빙 (KB 도표 이미지 등). 경로 탈출 방지."""
    target = (HANI_DATA / relpath).resolve()
    if HANI_DATA.resolve() not in target.parents and target != HANI_DATA.resolve():
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(target)


@app.get("/")
def index():
    return render_template("index.html")


def _by_kind(kind: str) -> list[dict]:
    """standards()는 kind=='standard'만 주기 때문에(법령·심의사례는 원래
    빠져있었음 — 지식베이스에 도로교통법이 안 보이던 원인), kind로 직접 필터."""
    return [v for v in load_payloads().values() if v.get("kind") == kind]


def _to_list_item(kind: str, p: dict, score: float | None = None) -> dict:
    """standard/law/case 세 종류를 화면에서 공통으로 다룰 수 있게 같은 모양으로 변환."""
    no_field = {"standard": "diagram_no", "law": "article_no", "case": "review_no"}[kind]
    no = p.get(no_field)
    item = {
        "id": f"{p.get('source_id')}::{no}",
        "kind": kind,
        "source_id": p.get("source_id"),
        "source_label": source_label(p.get("source_id", "")),
        "diagram_no": no,
        "title": p.get("title", ""),
        "base_ratio": p.get("base_ratio"),
        "image_path": p.get("image_path"),
        # 법령·심의사례는 이미지·과실비율이 없어서, 카드에 보여줄 짧은 미리보기 텍스트.
        "preview": (p.get("text") or p.get("accident_description") or "")[:90],
    }
    if score is not None:
        item["score"] = round(score, 3)
    return item


@app.get("/api/kb/list")
def kb_list():
    """목록. ?kind=standard|law|case (기본 standard), ?source=MAIN2023 출처 필터,
    ?limit=30&offset=0 페이지네이션."""
    kind = request.args.get("kind", "standard")
    source = (request.args.get("source") or "").strip()
    limit = int(request.args.get("limit", 30))
    offset = int(request.args.get("offset", 0))

    items = _by_kind(kind)
    if source and source != "전체":
        items = [s for s in items if s.get("source_id") == source]

    total = len(items)
    page = items[offset : offset + limit]
    return jsonify({"total": total, "items": [_to_list_item(kind, s) for s in page]})


@app.get("/api/kb/sources")
def kb_sources():
    kind = request.args.get("kind", "standard")
    items = _by_kind(kind)
    sids = sorted({s.get("source_id") for s in items if s.get("source_id")})
    return jsonify([{"id": sid, "label": source_label(sid)} for sid in sids])


@app.get("/api/kb/search")
def kb_search():
    """도표+법령+심의사례를 한 번에 검색 (예: "역주행" → 관련 도표와 관련 법조항 같이).

    taek.Searcher(하이브리드 검색+거절판정)를 그대로 재사용합니다 — 지식베이스
    검색은 Streamlit 버전엔 있었는데 Flask로 옮기며 빠뜨렸던 기능입니다.
    """
    q = (request.args.get("q") or "").strip()
    kind = request.args.get("kind") or None  # 없으면 전체 종류
    if not q:
        return jsonify({"items": []})

    from taek.search import Searcher  # noqa: F401 (타입 참고용)
    from woo.components.api import _local_searcher

    searcher = _local_searcher()
    hits = searcher.search(q, top_k=30, kind=kind, mode="hybrid", expand=True, reject=True)
    items = [_to_list_item(h.kind, h.payload, h.score) for h in hits]
    return jsonify({"items": items})


@app.get("/api/kb/<path:item_id>")
def kb_detail(item_id: str):
    source_id, _, no = item_id.partition("::")
    for v in load_payloads().values():
        if v.get("source_id") != source_id:
            continue
        if no in (v.get("diagram_no"), v.get("article_no"), v.get("review_no")):
            return jsonify(v)
    return jsonify({"error": "not found"}), 404


@app.get("/api/stats")
def stats():
    payloads = load_payloads()
    전체 = list(payloads.values())
    기준도표 = standards()

    법령 = set()
    판례 = set()
    for s in 기준도표:
        법령.update(s.get("laws") or [])
        판례.update(s.get("precedents") or [])
    사례수 = sum(1 for v in 전체 if v.get("kind") == "case")

    by_source: dict[str, int] = {}
    for s in 기준도표:
        label = source_label(s.get("source_id", ""))
        by_source[label] = by_source.get(label, 0) + 1

    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for s in 기준도표:
        a = (s.get("base_ratio") or {}).get("a")
        if a is None:
            continue
        idx = min(int(a) // 20, 4)
        buckets[list(buckets.keys())[idx]] += 1

    return jsonify({
        "diagram_count": len(기준도표),
        "precedent_count": len(판례),
        "law_count": len(법령),
        "case_count": 사례수,
        "by_source": by_source,
        "ratio_buckets": buckets,
    })


@app.post("/api/video/analyze")
def video_analyze():
    """영상 업로드 → 검출·추적·충돌감지 → (가능하면) Gemini+RAG 과실판정.

    hani가 만든 services/cv 파이프라인을 그대로 재사용합니다 — 여기서 YOLO/추적
    로직을 새로 만들지 않습니다. 프레임은 flaskapp/static/tmp/<job>/ 에 저장해서
    Flask 기본 정적 서빙으로 바로 브라우저에 보여줍니다.
    """
    from services.cv.extract import extract_evidence, make_annotated_video
    from services.cv.track import Tracker

    file = request.files.get("video")
    if file is None or not file.filename:
        return jsonify({"error": "영상 파일이 없습니다."}), 400

    job_id = uuid.uuid4().hex
    suffix = Path(file.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        video_path = tmp.name

    out_dir = TMP_FRAMES / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        tracker = Tracker()
        result = extract_evidence(video_path, out_dir, tracker=tracker)
    except Exception as exc:  # noqa: BLE001 — 사용자에게 원인을 그대로 보여주기 위함
        Path(video_path).unlink(missing_ok=True)
        return jsonify({"error": f"영상 분석 실패: {exc}"}), 500

    if not result["is_accident"]:
        Path(video_path).unlink(missing_ok=True)
        return jsonify({"is_accident": False})

    frames = []
    for p in result["frame_paths"]:
        rel = Path(p).relative_to(TMP_FRAMES.parent)  # "tmp/<job>/frame_x.jpg" → /static/tmp/...
        frames.append({"url": f"/static/{rel.as_posix()}", "is_impact": "impact" in Path(p).name})

    payload = {
        "is_accident": True,
        "impact_frame": result["impact_frame"],
        "frames": frames,
    }

    # ── YOLO 박스가 따라다니는 추적 영상 (브라우저 재생용 H.264로 트랜스코딩) ──
    # video_path는 여기까지 쓰고 나서 지웁니다 — 이 시점보다 먼저 지우면 원본 영상이
    # 없어서 추적 영상을 못 만듭니다(예전에 분석 직후 바로 지워서 생기던 버그).
    try:
        raw_tracked = out_dir / "tracked_raw.mp4"
        make_annotated_video(video_path, str(raw_tracked), tracker=tracker)
        tracked_bytes = _transcode_for_browser(str(raw_tracked))
        raw_tracked.unlink(missing_ok=True)
        if tracked_bytes:
            tracked_path = out_dir / "tracked.mp4"
            tracked_path.write_bytes(tracked_bytes)
            rel = tracked_path.relative_to(TMP_FRAMES.parent)
            payload["tracked_video_url"] = f"/static/{rel.as_posix()}"
    except Exception:  # noqa: BLE001 — 추적 영상은 실패해도 나머지 결과는 그대로 보여줍니다.
        pass
    finally:
        Path(video_path).unlink(missing_ok=True)

    try:
        from services.cv.gemini_fault import assess_fault
        from woo.components.api import _local_searcher

        searcher = _local_searcher()
        fault = assess_fault(result["frame_paths"], searcher)
        if "error" not in fault:
            payload["fault"] = fault
    except Exception as exc:  # noqa: BLE001 — 실패해도 영상 분석 결과(프레임)는 그대로 보여주되,
        # 왜 AI 판정만 빠졌는지는 화면에 알려줘야 합니다 — 조용히 숨기면
        # "원래 이 기능이 없다"고 오해하게 됩니다 (이 프로젝트 전체의 원칙과 동일).
        payload["fault_error"] = str(exc)

    return jsonify(payload)


if __name__ == "__main__":
    # ⚠️ use_reloader=True(디폴트)면 ultralytics가 내부적으로 건드리는 설정 파일을
    # "소스 변경"으로 오인해서 영상 분석(YOLO) 요청 도중 서버가 재시작돼버립니다
    # (curl 요청이 connection reset으로 끊김) — 그래서 리로더만 끕니다.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
