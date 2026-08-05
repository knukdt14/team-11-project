"""
사고 감지 — 규칙 기반. (학습 없음)

trajectory.py가 뽑은 프레임별 feature를 보고 규칙으로 사고를 판단한다.
핵심 신호 두 가지:
  - max_iou  : 두 객체 박스가 겹침 → 충돌하면 급증
  - max_accel: 속도의 급변(급감속/튕김) → 충돌 순간 급증

두 가지를 나눠서 본다:
  1) 사고 여부: 규칙 신호가 한 번이라도 잡히면 사고
  2) 사고 순간: "겹침(IoU)이 최대인 프레임" = 가장 세게 부딪힌 순간
     (임계값을 처음 넘는 순간이 아니라, 실제 충돌 정점을 잡아야
      전후 프레임 추출이 정확해진다)

임계값(iou_th, accel_th)은 손으로 찍지 않는다.
tune_collision.py가 CCD 정답(binlabels)으로 제일 잘 맞는 값을 골라준다.
그 결과를 여기 DEFAULT_* 에 넣어 쓰면 된다.
"""
import numpy as np

# CCD 튜닝으로 채워질 기본 임계값 (tune_collision.py 결과로 갱신)
DEFAULT_IOU_TH = 0.30
DEFAULT_ACCEL_TH = 8.0
# 두 신호를 and로 볼지 or로 볼지도 튜닝에서 결정
DEFAULT_MODE = "or"   # "and" | "or"


def detect_from_features(feats, iou_th=DEFAULT_IOU_TH,
                         accel_th=DEFAULT_ACCEL_TH, mode=DEFAULT_MODE):
    """
    feats: numpy (T, F). trajectory.FEATURE_NAMES 순서.
           [n_objects, max_iou, n_overlaps, mean_speed, max_speed, max_accel]
    반환: (사고여부 bool, 프레임별 사고플래그 (T,), 사고 순간 프레임 or None)

    사고 순간(impact_frame):
      - 규칙에 걸린 프레임들 중 IoU가 가장 큰 프레임.
      - IoU가 전부 0인데 가속도로만 걸렸으면(스침 등) 가속도 최대 프레임.
    """
    max_iou = feats[:, 1]
    max_accel = feats[:, 5]

    iou_hit = max_iou >= iou_th
    accel_hit = max_accel >= accel_th

    if mode == "and":
        frame_flags = iou_hit & accel_hit
    else:
        frame_flags = iou_hit | accel_hit

    is_accident = bool(frame_flags.any())
    if not is_accident:
        return False, frame_flags, None

    # 걸린 프레임들만 후보로
    cand = np.where(frame_flags)[0]
    cand_iou = max_iou[cand]

    if cand_iou.max() > 0:
        # 겹침이 가장 큰 프레임 = 충돌 정점
        impact_frame = int(cand[cand_iou.argmax()])
    else:
        # 겹침이 없으면 가속도 최대 프레임
        impact_frame = int(cand[max_accel[cand].argmax()])

    return True, frame_flags, impact_frame