"""교차로 CCTV 영상 → 검출·추적·궤적·충돌지점 시각화 — `woo/components/cv_pipeline.py`의
프레임워크 독립 버전.

⚠️ hani가 만든 `services/cv/*`(Tracker, video_to_features, detect_from_features,
extract.COLORS, extract_evidence, make_annotated_video)는 그대로 가져다 쓰기만 하고
수정하지 않습니다.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.cv.detect import KEEP_CLASSES  # noqa: E402
from services.cv.extract import extract_evidence  # noqa: E402
from services.cv.track import Tracker  # noqa: E402

from webapp.services.backend import _local_searcher  # noqa: E402

_tracker_lock = threading.Lock()
_tracker_instance: Tracker | None = None


def _tracker() -> Tracker:
    global _tracker_instance
    if _tracker_instance is None:
        with _tracker_lock:
            if _tracker_instance is None:
                _tracker_instance = Tracker()
    return _tracker_instance


def transcode_for_browser(video_path: str) -> bytes | None:
    """브라우저 호환 코덱(H.264)으로 다시 인코딩합니다 (imageio-ffmpeg 정적 바이너리 사용)."""
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


def analyze_video_evidence(video_path: str, out_dir: str) -> dict:
    """hani의 `extract_evidence()`를 그대로 호출합니다.

    반환: {is_accident, impact_frame, frame_paths, boxes_at_impact}
    """
    tracker = _tracker()
    return extract_evidence(video_path, out_dir, tracker=tracker)


def make_annotated_video_bytes(video_path: str) -> bytes | None:
    """영상 전체에 박스가 따라다니고 충돌 순간엔 빨간 테두리가 뜨는 영상을 만들어
    브라우저에서 바로 재생할 수 있는 바이트로 반환합니다."""
    from services.cv.extract import make_annotated_video

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        raw_out_path = tmp.name
    tracker = _tracker()
    make_annotated_video(video_path, raw_out_path, tracker=tracker)
    return transcode_for_browser(raw_out_path)


def assess_fault_from_evidence(frame_paths: list[str], api_key: str | None = None) -> dict:
    """이미 뽑아둔 근거 프레임(frame_paths)으로 Gemini+RAG 과실 판정만 돌립니다."""
    from services.cv.gemini_fault import assess_fault

    searcher = _local_searcher()
    return assess_fault(frame_paths, searcher, api_key=api_key)


__all__ = [
    "KEEP_CLASSES",
    "analyze_video_evidence", "make_annotated_video_bytes",
    "assess_fault_from_evidence", "transcode_for_browser",
]
