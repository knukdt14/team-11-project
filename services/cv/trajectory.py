"""
추적 결과(track.py) → 프레임별 사고 판단 feature.

사고의 물리적 특징을 숫자로 뽑는다:
  - 두 객체 박스가 겹치는 정도 (최대 IoU)  → 충돌은 겹침이 커짐
  - 겹치는 쌍 개수
  - 객체들의 속도 변화(가속도)의 최대치      → 충돌은 급감속/급변
  - 평균 속도
  - 화면 안 객체 수

이 feature 시퀀스(프레임 x feature수)를 collision 모델이 보고 사고를 판단한다.
같은 궤적이 LLM 정황 입력(features.py)으로도 재활용된다.
"""
import numpy as np


def iou(box_a, box_b):
    """두 박스(xyxy) IoU."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


# 프레임당 feature 개수 (모델 입력 차원)
FEATURE_NAMES = [
    "n_objects",     # 화면 안 객체 수
    "max_iou",       # 아무 두 객체 최대 겹침
    "n_overlaps",    # IoU>0.1 인 쌍 개수
    "mean_speed",    # 평균 이동 속도(px/frame)
    "max_speed",     # 최대 이동 속도
    "max_accel",     # 최대 속도변화(가속도) 절댓값
]
N_FEATURES = len(FEATURE_NAMES)


def video_to_features(frames):
    """
    frames: track.track_video() 결과 (프레임별 박스 리스트)
    반환: numpy 배열 (T, N_FEATURES). T=프레임 수.
    """
    T = len(frames)
    feats = np.zeros((T, N_FEATURES), dtype=np.float32)

    prev_centers = {}   # tid -> (x, y)  이전 프레임 위치
    prev_speeds = {}    # tid -> speed   이전 프레임 속도

    for t, boxes in enumerate(frames):
        n = len(boxes)

        # --- 겹침 (충돌 신호) ---
        max_iou = 0.0
        n_overlaps = 0
        for i in range(n):
            for j in range(i + 1, n):
                v = iou(boxes[i]["xyxy"], boxes[j]["xyxy"])
                max_iou = max(max_iou, v)
                if v > 0.1:
                    n_overlaps += 1

        # --- 속도·가속도 ---
        speeds, accels = [], []
        cur_centers, cur_speeds = {}, {}
        for b in boxes:
            tid = b["tid"]
            cx, cy = center(b["xyxy"])
            cur_centers[tid] = (cx, cy)
            if tid in prev_centers:
                px, py = prev_centers[tid]
                sp = np.hypot(cx - px, cy - py)   # 이번 프레임 이동거리 = 속도
                cur_speeds[tid] = sp
                speeds.append(sp)
                if tid in prev_speeds:
                    accels.append(abs(sp - prev_speeds[tid]))

        feats[t, 0] = n
        feats[t, 1] = max_iou
        feats[t, 2] = n_overlaps
        feats[t, 3] = np.mean(speeds) if speeds else 0.0
        feats[t, 4] = np.max(speeds) if speeds else 0.0
        feats[t, 5] = np.max(accels) if accels else 0.0

        prev_centers = cur_centers
        prev_speeds = cur_speeds

    return feats
