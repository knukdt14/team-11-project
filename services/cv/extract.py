"""
사고 순간 전후 프레임 추출 + YOLO 박스 시각화.  (방법 2: CV는 시각화만)

입력 영상에서:
  1) 사고 순간(impact_frame)을 collision으로 찾고
  2) 그 전후 window초 범위의 프레임을 stride 간격으로 뽑아
  3) 각 프레임에 YOLO 박스를 그려 이미지로 저장한다.

저장된 이미지들이:
  - Streamlit 화면에 "근거 사진"으로 표시되고
  - 그대로 Gemini에 넘겨져 과실 판단 재료가 된다.

근거 텍스트/과실 판단은 여기서 안 한다 (Gemini 몫).
"""
from pathlib import Path

import cv2

from .track import Tracker
from .trajectory import video_to_features
from .collision import detect_from_features

# 클래스별 박스 색 (BGR)
COLORS = {
    "car": (0, 200, 0), "truck": (0, 150, 255), "bus": (0, 150, 255),
    "motorcycle": (255, 100, 0), "bicycle": (255, 100, 0), "person": (0, 0, 255),
}


def draw_boxes(frame, boxes):
    """프레임(numpy BGR)에 박스+라벨 그려서 반환."""
    img = frame.copy()
    for b in boxes:
        x1, y1, x2, y2 = map(int, b["xyxy"])
        color = COLORS.get(b["name"], (200, 200, 200))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f'{b["name"]} #{b.get("tid","")}'
        cv2.putText(img, label, (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return img


def _refine_impact_by_brightness(video_path, impact, n_frames, search=8):
    """
    IoU 기반 impact를 밝기 급락으로 보정.
    impact 이후 search 프레임 안에서 '밝기가 가장 크게 떨어지는' 프레임을 찾는다.
    급락이 뚜렷하지 않으면(평범한 영상) 원래 impact를 그대로 둔다.
    """
    cap = cv2.VideoCapture(str(video_path))
    bright = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        bright.append(float(f.mean()))
    cap.release()

    if len(bright) < 2:
        return impact

    # 프레임별 밝기 변화량 (음수 = 어두워짐)
    lo = impact
    hi = min(n_frames - 1, impact + search)
    best_frame, best_drop = impact, 0.0
    for t in range(lo + 1, hi + 1):
        if t >= len(bright):
            break
        drop = bright[t] - bright[t - 1]   # 음수일수록 급락
        if drop < best_drop:
            best_drop = drop
            best_frame = t

    # 급락이 확실할 때만 보정 (밝기 -20 이상 떨어질 때). 아니면 원래대로.
    return best_frame if best_drop <= -20 else impact


def extract_evidence(video_path, out_dir, tracker=None,
                     window_sec=1.0, stride=2, fps=10):
    """
    video_path : 입력 영상
    out_dir    : 근거 이미지 저장 폴더
    tracker    : Tracker 인스턴스 (없으면 새로 만듦)
    window_sec : 사고 순간 앞뒤로 뽑을 범위(초)
    stride     : 몇 프레임마다 한 장 뽑을지
    fps        : 영상 fps (CCD는 10)

    반환: dict {
       is_accident, impact_frame, frame_paths[list], boxes_at_impact
    }
    frame_paths 가 Streamlit 표시 + Gemini 입력에 쓰인다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker = tracker or Tracker()

    # 1) 추적 → feature → 사고 순간
    frames_boxes = tracker.track_video(video_path)
    feats = video_to_features(frames_boxes)
    is_acc, _, impact = detect_from_features(feats)

    if not is_acc:
        return {"is_accident": False, "impact_frame": None,
                "frame_paths": [], "boxes_at_impact": []}

    # 1-b) 충돌 순간 보정 (밝기 급락)
    #   충돌 직전 차가 코앞으로 들어오면 카메라 시야가 막혀 화면이 급격히 어두워진다.
    #   IoU 최대 지점은 '스쳐 보인 순간'일 수 있어, 감지 이후 구간에서
    #   밝기가 가장 크게 떨어지는 프레임을 실제 충돌로 본다.
    impact = _refine_impact_by_brightness(video_path, impact, len(frames_boxes))

    # 2) 뽑을 프레임 범위 정하기 (impact ± window)
    half = int(window_sec * fps)
    start = max(0, impact - half)
    end = min(len(frames_boxes) - 1, impact + half)
    pick = list(range(start, end + 1, stride))
    if impact not in pick:
        pick.append(impact)
        pick.sort()

    # 3) 원본 영상에서 해당 프레임 이미지를 읽어 박스 그려 저장
    cap = cv2.VideoCapture(str(video_path))
    frame_paths = []
    idx = 0
    want = set(pick)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in want:
            boxes = frames_boxes[idx] if idx < len(frames_boxes) else []
            img = draw_boxes(frame, boxes)
            tag = "impact" if idx == impact else f"{idx:03d}"
            p = out_dir / f"frame_{idx:03d}_{tag}.jpg"
            cv2.imwrite(str(p), img)
            frame_paths.append(str(p))
        idx += 1
    cap.release()

    return {
        "is_accident": True,
        "impact_frame": impact,
        "frame_paths": frame_paths,
        "boxes_at_impact": frames_boxes[impact] if impact < len(frames_boxes) else [],
    }


def make_annotated_video(video_path, out_path, tracker=None, fps=10):
    """
    영상 전체에 YOLO 박스를 그려 새 mp4로 저장. (박스가 계속 따라다니는 영상)
    추출 프레임(띄엄띄엄)이 아니라 원본 전 프레임을 원본 fps로 처리해 부드럽다.

    반환: (out_path, impact_frame)  impact는 밝기 보정된 충돌 순간.
    브라우저 재생 호환을 위해 avc1(H.264) 코덱 우선, 실패 시 mp4v.
    """
    tracker = tracker or Tracker()
    frames_boxes = tracker.track_video(video_path)

    # 충돌 순간(밝기 보정 포함)
    feats = video_to_features(frames_boxes)
    is_acc, _, impact = detect_from_features(feats)
    if is_acc:
        impact = _refine_impact_by_brightness(video_path, impact, len(frames_boxes))

    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or fps

    out_path = str(out_path)
    # 브라우저 호환 코덱 우선
    writer = None
    for cc in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*cc), src_fps, (w, h))
        if writer.isOpened():
            break
    if writer is None or not writer.isOpened():
        cap.release()
        raise RuntimeError("VideoWriter 열기 실패")

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        boxes = frames_boxes[idx] if idx < len(frames_boxes) else []
        img = draw_boxes(frame, boxes)
        # 충돌 순간 프레임엔 빨간 테두리 + 문구
        if is_acc and idx == impact:
            cv2.rectangle(img, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)
            cv2.putText(img, "COLLISION", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
        writer.write(img)
        idx += 1

    cap.release()
    writer.release()
    return out_path, (impact if is_acc else None)
