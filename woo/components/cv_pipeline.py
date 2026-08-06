"""교차로 CCTV 영상 → 검출·추적·궤적·충돌지점 시각화.

⚠️ hani가 만든 `services/cv/*`(Tracker, video_to_features, detect_from_features,
extract.COLORS)는 그대로 가져다 쓰기만 하고 수정하지 않습니다. 여기서 새로 만든 건
"궤적 선 + 충돌 지점을 프레임에 그려서 화면에 보여주는" 부분뿐입니다 — hani의
extract.py는 박스만 그려서 저장하는 용도(Gemini 입력용)라 화면용 궤적 시각화는
없었습니다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.cv.collision import detect_from_features  # noqa: E402
from services.cv.detect import KEEP_CLASSES  # noqa: E402
from services.cv.extract import COLORS, extract_evidence  # noqa: E402
from services.cv.track import Tracker  # noqa: E402
from services.cv.trajectory import video_to_features  # noqa: E402

from woo.components.api import _local_searcher  # noqa: E402

_TRAJ_COLOR = (255, 200, 0)  # BGR — 하늘색 계열, 이동 궤적 선
_IMPACT_COLOR = (0, 0, 255)  # BGR — 빨강, 충돌 지점 마커


@st.cache_resource(show_spinner=False)
def _tracker() -> Tracker:
    return Tracker()


def _center(xyxy) -> tuple[int, int]:
    x1, y1, x2, y2 = xyxy
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def transcode_for_browser(video_path: str) -> bytes | None:
    """`st.video()`로 재생되게 브라우저 호환 코덱(H.264)으로 다시 인코딩합니다.

    ⚠️ 실제로 원인을 잡아보니, 업로드된 영상이 FMP4(구형 MPEG-4 Part 2) 코덱이었습니다
    — OpenCV는 이걸 잘 읽지만(그래서 분석 자체는 문제없었음), 브라우저 <video> 태그는
    H.264/VP9/AV1 정도만 재생 가능해서 FMP4는 그냥 검은 화면(0:00)으로 보였던 것입니다.
    시스템에 ffmpeg를 따로 설치할 필요 없이 imageio-ffmpeg가 받아둔 정적 바이너리를
    씁니다. 실패해도(변환 자체가 안 되는 특이 파일 등) None을 반환할 뿐 분석은 계속
    정상 진행됩니다 — 미리보기는 그냥 안 보여줄 뿐입니다.
    """
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


@st.cache_data(show_spinner=False)
def transcode_bytes_for_browser(data: bytes, suffix: str) -> bytes | None:
    """업로드 바이트를 그대로 받아 변환합니다 — 같은 파일이면 다시 인코딩하지 않도록 캐시."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        in_path = tmp.name
    return transcode_for_browser(in_path)


def analyze_video(video_path: str) -> dict:
    """영상 하나를 검출→추적→사고판단까지 전부 돌립니다. 프레임을 딱 한 번만 읽습니다.

    반환: {frames_boxes, raw_frames, feats, is_accident, impact_frame}
    frames_boxes[i] = i번째 프레임의 박스 리스트(track.py 형식, tid 포함).
    raw_frames[i]   = 바로 그 i번째 프레임의 원본 BGR 이미지.

    ⚠️ 예전엔 hani의 `Tracker.track_video(video_path)`(자체 디코딩)로 박스만 뽑고,
    화면에 그릴 프레임은 `render_annotated_frames()`에서 `cv2.VideoCapture`로
    같은 파일을 "다시" 읽었습니다 — 특이 인코딩(가변 프레임레이트 등) 영상에서
    두 디코딩의 프레임 순서가 어긋나서 "27번 프레임(충돌 순간)"이라고 표시된
    이미지가 실제로는 전혀 다른 장면으로 나오는 버그가 있었습니다(사용자 실측
    확인: 단일 연속 영상인데 뒷부분 프레임이 완전히 다른 화면으로 나옴). 지금은
    영상을 한 번만 읽으면서 그 자리에서 바로 추적도 하고 원본 프레임도 같이
    저장해서, 박스와 이미지의 인덱스가 구조적으로 절대 어긋날 수 없게 했습니다.
    (model.track()에 파일 경로 대신 프레임 하나씩 넣어도 persist=True면 추적
    ID가 프레임 간에 계속 유지됩니다 — track.py의 Tracker.model을 그대로 재사용.)
    """
    tracker = _tracker()
    cap = cv2.VideoCapture(str(video_path))
    frames_boxes: list[list[dict]] = []
    raw_frames: list[np.ndarray] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        res = tracker.model.track(
            frame, conf=tracker.conf, device=tracker.device,
            persist=True, tracker="bytetrack.yaml", verbose=False,
        )[0]
        boxes = []
        if res.boxes is not None and res.boxes.id is not None:
            for b in res.boxes:
                cls = int(b.cls[0])
                if cls not in KEEP_CLASSES:
                    continue
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                boxes.append({
                    "tid": int(b.id[0]),
                    "xyxy": (x1, y1, x2, y2),
                    "cls": cls,
                    "name": KEEP_CLASSES[cls],
                    "conf": float(b.conf[0]),
                })
        frames_boxes.append(boxes)
        raw_frames.append(frame)
    cap.release()

    feats = video_to_features(frames_boxes)
    is_accident, _frame_flags, impact_frame = detect_from_features(feats)
    return {
        "frames_boxes": frames_boxes,
        "raw_frames": raw_frames,
        "feats": feats,
        "is_accident": is_accident,
        "impact_frame": impact_frame,
    }


def _draw_frame(frame, boxes, trails: dict[int, list[tuple[int, int]]], is_impact: bool):
    """박스 + 지금까지 누적된 궤적 선 + (충돌 프레임이면) 충돌 지점을 그려서 반환."""
    img = frame.copy()

    for pts in trails.values():
        for i in range(1, len(pts)):
            cv2.line(img, pts[i - 1], pts[i], _TRAJ_COLOR, 2, cv2.LINE_AA)

    for b in boxes:
        x1, y1, x2, y2 = map(int, b["xyxy"])
        color = COLORS.get(b["name"], (200, 200, 200))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f'{b["name"]} #{b.get("tid", "")}'
        cv2.putText(
            img, label, (x1, max(y1 - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )

    if is_impact:
        # 충돌 순간엔 화면에 있는 객체들 중심의 평균점에 별 마커를 찍습니다
        # (정확한 접촉점 좌표까진 아니지만, "여기서 부딪혔다"를 직관적으로 보여주기엔 충분).
        pts = [_center(b["xyxy"]) for b in boxes]
        if len(pts) >= 2:
            cx = int(np.mean([p[0] for p in pts]))
            cy = int(np.mean([p[1] for p in pts]))
            cv2.drawMarker(img, (cx, cy), _IMPACT_COLOR, cv2.MARKER_STAR, 40, 3, cv2.LINE_AA)
            cv2.putText(
                img, "충돌 지점", (cx + 15, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, _IMPACT_COLOR, 2, cv2.LINE_AA,
            )
    return img


def analyze_video_evidence(video_path: str, out_dir: str) -> dict:
    """hani의 `extract_evidence()`를 그대로 호출합니다 — 저희 자체 추적 로직 없음.

    ⚠️ 원래 화면 표시용으로 model.track()을 프레임 단위로 직접 호출하는 자체 파이프라인
    (analyze_video/render_annotated_frames, 위)을 새로 만들었었는데, 실제 사용자 영상으로
    비교해보니 hani가 검증한 `Tracker.track_video(video_path)`(ultralytics가 영상 경로를
    직접 받아 자체적으로 디코딩) 방식보다 충돌 시점 판정이 부정확했습니다 — 아마
    ultralytics가 소스 파일을 직접 열 때와 프레임을 한 장씩 넘길 때 내부적으로 전처리가
    미묘하게 달라지는 듯합니다. 그래서 화면 표시도 hani의 실제 검증된 함수를 그대로
    쓰도록 바꿨습니다(정확도 우선, 궤적 선 오버레이는 나중에 다시 붙이기로).

    반환: {is_accident, impact_frame, frame_paths, boxes_at_impact}
    """
    tracker = _tracker()
    return extract_evidence(video_path, out_dir, tracker=tracker)


def assess_fault_from_evidence(frame_paths: list[str], api_key: str | None = None) -> dict:
    """이미 뽑아둔 근거 프레임(frame_paths)으로 Gemini+RAG 과실 판정만 돌립니다.

    `analyze_video_evidence()`가 이미 프레임을 뽑아뒀다면 그 결과를 그대로 넘기세요 —
    영상을 또 열어서 다시 추적하지 않아도 됩니다(화면에 보여준 프레임 = Gemini가 보는
    프레임이 항상 같다는 것도 보장됨).
    """
    from services.cv.gemini_fault import assess_fault

    searcher = _local_searcher()
    return assess_fault(frame_paths, searcher, api_key=api_key)


def render_annotated_frames(
    raw_frames: list[np.ndarray],
    frames_boxes: list,
    impact_frame: int,
    window_sec: float = 1.5,
    stride: int = 3,
    fps: float = 10.0,
) -> list[tuple[int, np.ndarray]]:
    """충돌 프레임 전후로 궤적·박스·충돌지점이 그려진 프레임 이미지를 뽑습니다.

    raw_frames/frames_boxes는 반드시 `analyze_video()`가 같이 반환한 것을 그대로
    넘기세요 — 둘 다 같은 한 번의 디코딩에서 나온 것이라 인덱스가 서로 정확히
    대응합니다(더 이상 파일을 다시 읽지 않습니다).

    반환: [(frame_idx, BGR 이미지), ...] — impact_frame 포함, 시간순 정렬.

    ⚠️ 궤적은 "화면에 그릴 프레임만" 골라서가 아니라 처음부터 매 프레임 누적해야
    선이 끊기지 않습니다 — stride로 건너뛴 프레임도 trails 갱신은 계속합니다.
    """
    half = int(window_sec * fps)
    start = max(0, impact_frame - half)
    end = min(len(frames_boxes) - 1, impact_frame + half)
    want = set(range(start, end + 1, stride)) | {impact_frame}

    trails: dict[int, list[tuple[int, int]]] = {}
    results: list[tuple[int, np.ndarray]] = []
    for idx in range(0, end + 1):
        boxes = frames_boxes[idx] if idx < len(frames_boxes) else []
        for b in boxes:
            trails.setdefault(b["tid"], []).append(_center(b["xyxy"]))
        if idx in want:
            img = _draw_frame(raw_frames[idx], boxes, trails, is_impact=(idx == impact_frame))
            results.append((idx, img))
    return sorted(results, key=lambda r: r[0])
