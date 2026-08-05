"""
사고 감지 진단 — 적중률이 왜 낮은지 원인을 가른다.
ccd_features.npz만 읽으면 됨 (영상 재처리 X). 몇 초.

보는 것:
  1) IoU 충돌 신호(박스 겹침)가 실제로 잡히는 영상 비율
     → 낮으면 1인칭 시점 한계(내 차가 화면에 없어 겹침이 안 생김)
  2) 겹침 있는 영상 vs 없는 영상, 각각 사고순간 적중률
     → 겹침 있는 쪽만 잘 맞으면 "IoU는 맞고, 나머지가 문제"
  3) IoU 최대 지점이 정답 사고프레임과 얼마나 가까운지 분포

실행:
    python -m train.diagnose_ccd --data data/ccd_features.npz
"""
import argparse
import numpy as np


def gt_frame(binl):
    binl = np.asarray(binl)
    return int(np.argmax(binl)) if binl.max() > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--iou_min", type=float, default=0.1,
                    help="이 값 넘으면 '겹침 있음'으로 본다")
    ap.add_argument("--tol", type=int, default=5, help="적중 허용오차(프레임)")
    args = ap.parse_args()

    data = np.load(args.data, allow_pickle=True)
    X, y = list(data["X"]), list(data["y"])
    n = len(X)

    has_overlap = 0
    # 그룹별 IoU최대지점 오차 모으기
    err_overlap = []      # 겹침 있는 영상: IoU 최대 프레임 vs 정답
    err_no_overlap = []   # 겹침 없는 영상: 가속도 최대 프레임 vs 정답
    peak_iou_vals = []

    for feats, binl in zip(X, y):
        feats = np.asarray(feats)
        gt = gt_frame(binl)
        if gt is None:
            continue
        max_iou = feats[:, 1]
        max_accel = feats[:, 5]
        peak_iou = max_iou.max()
        peak_iou_vals.append(peak_iou)

        if peak_iou >= args.iou_min:
            has_overlap += 1
            pred = int(max_iou.argmax())          # 겹침 최대 지점
            err_overlap.append(abs(pred - gt))
        else:
            pred = int(max_accel.argmax())        # 가속도 최대 지점
            err_no_overlap.append(abs(pred - gt))

    def summ(errs, tol):
        if not errs:
            return "해당없음"
        errs = np.array(errs)
        hit = (errs <= tol).mean()
        return f"{len(errs)}개, 적중률={hit:.2f}, 평균오차={errs.mean():.1f}프레임({errs.mean()/10:.2f}s)"

    print(f"=== 진단 (사고영상 {sum(1 for b in y if np.asarray(b).max()>0)}개) ===\n")
    print(f"[1] IoU 겹침(>={args.iou_min}) 잡히는 영상: {has_overlap}개 "
          f"({has_overlap/n*100:.1f}%)")
    print(f"    → 이게 낮으면 1인칭 시점 한계 (내 차가 화면에 없어 겹침 안 생김)\n")

    print(f"[2] 그룹별 사고순간 적중 (허용 {args.tol}프레임)")
    print(f"    겹침 있는 영상: {summ(err_overlap, args.tol)}")
    print(f"    겹침 없는 영상: {summ(err_no_overlap, args.tol)}\n")

    pv = np.array(peak_iou_vals)
    print(f"[3] 영상별 최대 IoU 분포")
    print(f"    0(전혀 안겹침): {(pv==0).mean()*100:.0f}%   "
          f"0~0.1: {((pv>0)&(pv<0.1)).mean()*100:.0f}%   "
          f">=0.1: {(pv>=0.1).mean()*100:.0f}%")
    print(f"    중앙값={np.median(pv):.3f}  평균={pv.mean():.3f}")


if __name__ == "__main__":
    main()