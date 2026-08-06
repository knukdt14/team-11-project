"""교차로 CCTV 영상 → 검출·추적·궤적·충돌지점 시각화.

⚠️ hani가 만든 `services/cv/*`(Tracker, video_to_features, detect_from_features,
extract.COLORS)는 그대로 가져다 쓰기만 하고 수정하지 않습니다. 여기서 새로 만든 건
"궤적 선 + 충돌 지점을 프레임에 그려서 화면에 보여주는" 부분뿐입니다 — hani의
extract.py는 박스만 그려서 저장하는 용도(Gemini 입력용)라 화면용 궤적 시각화는
없었습니다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.cv.collision import detect_from_features  # noqa: E402
from services.cv.extract import COLORS  # noqa: E402
from services.cv.track import Tracker  # noqa: E402
from services.cv.trajectory import video_to_features  # noqa: E402

_TRAJ_COLOR = (255, 200, 0)  # BGR — 하늘색 계열, 이동 궤적 선
_IMPACT_COLOR = (0, 0, 255)  # BGR — 빨강, 충돌 지점 마커


@st.cache_resource(show_spinner=False)
def _tracker() -> Tracker:
    return Tracker()


def _center(xyxy) -> tuple[int, int]:
    x1, y1, x2, y2 = xyxy
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def analyze_video(video_path: str) -> dict:
    """영상 하나를 검출→추적→사고판단까지 전부 돌립니다.

    반환: {frames_boxes, feats, is_accident, impact_frame}
    frames_boxes[i] = i번째 프레임의 박스 리스트(track.py 형식, tid 포함).
    """
    tracker = _tracker()
    frames_boxes = tracker.track_video(video_path)
    feats = video_to_features(frames_boxes)
    is_accident, _frame_flags, impact_frame = detect_from_features(feats)
    return {
        "frames_boxes": frames_boxes,
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


def render_annotated_frames(
    video_path: str,
    frames_boxes: list,
    impact_frame: int,
    window_sec: float = 1.5,
    stride: int = 3,
    fps: float = 10.0,
) -> list[tuple[int, np.ndarray]]:
    """충돌 프레임 전후로 궤적·박스·충돌지점이 그려진 프레임 이미지를 뽑습니다.

    반환: [(frame_idx, BGR 이미지), ...] — impact_frame 포함, 시간순 정렬.

    ⚠️ 궤적은 "화면에 그릴 프레임만" 골라서가 아니라 영상 처음부터 매 프레임 누적해야
    선이 끊기지 않습니다 — stride로 건너뛴 프레임도 trails 갱신은 계속합니다.
    """
    half = int(window_sec * fps)
    start = max(0, impact_frame - half)
    end = min(len(frames_boxes) - 1, impact_frame + half)
    want = set(range(start, end + 1, stride)) | {impact_frame}

    cap = cv2.VideoCapture(str(video_path))
    trails: dict[int, list[tuple[int, int]]] = {}
    results: list[tuple[int, np.ndarray]] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        boxes = frames_boxes[idx] if idx < len(frames_boxes) else []
        for b in boxes:
            trails.setdefault(b["tid"], []).append(_center(b["xyxy"]))
        if idx in want:
            img = _draw_frame(frame, boxes, trails, is_impact=(idx == impact_frame))
            results.append((idx, img))
        idx += 1
    cap.release()
    return sorted(results, key=lambda r: r[0])
