"""
규칙 임계값을 CCD 정답(binlabels)으로 자동 선택 + 감지 성능 채점.
(딥러닝 학습 대신 이걸 돌린다. 몇 초~몇 분)

prepare_ccd.py가 만든 ccd_features.npz를 읽어서:
  1) iou_th / accel_th / mode 후보들을 다 넣어보고
  2) "사고 여부 F1"과 "사고 순간 정확도"를 함께 보고 제일 좋은 조합을 고른다
  3) 고른 값과 성능을 출력 → collision.py DEFAULT_* 에 반영

사고 순간 정확도까지 보는 이유:
  전후 프레임을 뽑아 LLM에 넘기는 게 목적이라, 사고 여부만 맞고
  순간이 엉뚱하면 근거 프레임이 틀린다. 그래서 프레임 오차도 최적화한다.

실행 (저장소 루트에서):
    python -m train.tune_collision --data data/ccd_features.npz
"""
import argparse
import numpy as np

from services.cv.collision import detect_from_features

# 사고 순간이 정답과 이만큼(프레임) 이내면 "제대로 짚었다"로 본다. 10fps 기준 0.5초.
HIT_TOL = 5


def video_gt(binl):
    """CCD 영상 정답: (사고여부, 사고 시작 프레임 or None).
       binlabels에서 1이 시작되는 지점 = 사고 순간."""
    binl = np.asarray(binl)
    if binl.max() > 0:
        return True, int(np.argmax(binl))
    return False, None


def score(X, y, iou_th, accel_th, mode):
    """
    반환: dict(f1, prec, rec, mae, hit_rate)
      - f1/prec/rec : 사고 여부 감지
      - mae         : 맞춘 영상의 사고 순간 평균 오차(프레임)
      - hit_rate    : 사고 순간을 HIT_TOL 이내로 짚은 비율
    """
    tp = fp = fn = 0
    frame_errs = []
    hits = 0
    for feats, binl in zip(X, y):
        pred_acc, _, pred_f = detect_from_features(
            feats, iou_th=iou_th, accel_th=accel_th, mode=mode)
        gt_acc, gt_f = video_gt(binl)

        if pred_acc and gt_acc:
            tp += 1
            if pred_f is not None and gt_f is not None:
                err = abs(pred_f - gt_f)
                frame_errs.append(err)
                if err <= HIT_TOL:
                    hits += 1
        elif pred_acc and not gt_acc:
            fp += 1
        elif not pred_acc and gt_acc:
            fn += 1

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    mae = float(np.mean(frame_errs)) if frame_errs else None
    hit_rate = hits / tp if tp else 0.0
    return {"f1": f1, "prec": prec, "rec": rec, "mae": mae, "hit_rate": hit_rate}


def combined(m):
    """
    조합 점수: 사고 여부(F1)와 사고 순간(hit_rate)을 함께 본다.
    둘 다 0~1이라 평균. 순간을 잘 짚는 조합이 뽑히게.
    """
    return 0.5 * m["f1"] + 0.5 * m["hit_rate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    args = ap.parse_args()

    data = np.load(args.data, allow_pickle=True)
    X, y = list(data["X"]), list(data["y"])
    print(f"영상 {len(X)}개로 튜닝 (사고순간 허용오차 {HIT_TOL}프레임 = {HIT_TOL/10:.1f}s)\n")

    iou_grid = [0.1, 0.2, 0.3, 0.4, 0.5]
    accel_grid = [4, 6, 8, 10, 15, 20]
    modes = ["or", "and"]

    best = None
    for mode in modes:
        for iou_th in iou_grid:
            for accel_th in accel_grid:
                m = score(X, y, iou_th, accel_th, mode)
                c = combined(m)
                if best is None or c > best[0]:
                    best = (c, iou_th, accel_th, mode, m)

    c, iou_th, accel_th, mode, m = best
    print("=== 최적 임계값 (CCD 기준) ===")
    print(f"  iou_th={iou_th}  accel_th={accel_th}  mode={mode}")
    print(f"  [사고 여부]  F1={m['f1']:.3f}  정밀도={m['prec']:.3f}  재현율={m['rec']:.3f}")
    print(f"  [사고 순간]  적중률={m['hit_rate']:.3f} (오차 {HIT_TOL}프레임 이내)", end="")
    if m["mae"] is not None:
        print(f"  평균오차={m['mae']:.1f}프레임 ({m['mae']/10:.2f}s)")
    else:
        print()
    print("\ncollision.py 의 DEFAULT_* 를 위 값으로 바꿔 쓰면 됨.")


if __name__ == "__main__":
    main()