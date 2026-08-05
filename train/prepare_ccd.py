"""
CCD 영상 전체 → feature+정답 데이터 생성.  (한 번만 돌리면 됨. GPU로 1~3시간)

각 영상을 YOLO+추적으로 돌려 프레임별 feature를 뽑고,
Crash-1500.txt의 binlabels를 정답지로 붙여서 .npz 하나에 저장한다.
이후 규칙 튜닝/채점(tune_collision.py)이 이 .npz만 읽어서 몇 초~몇 분.

실행 (저장소 루트에서):
    python -m train.prepare_ccd \
        --videos /path/CarCrash/videos \
        --ann     /path/CarCrash/videos/Crash-1500.txt \
        --out     data/ccd_features.npz \
        --weights yolov8n.pt

정상영상(Normal)도 넣고 싶으면 --normal 로 개수 지정 (기본 0 = 사고영상만).
"""
import argparse
from pathlib import Path

import numpy as np

from services.cv.track import Tracker
from services.cv.trajectory import video_to_features, N_FEATURES
from services.cv.ccd_labels import load_labels


def process_split(tracker, video_dir, labels, out_X, out_y, out_ids):
    """video_dir 안의 사고영상들을 돌려 X(feature)/y(라벨) 누적."""
    video_dir = Path(video_dir)
    vids = sorted(labels.keys())
    total = len(vids)

    for i, vid in enumerate(vids, 1):
        mp4 = video_dir / f"{vid}.mp4"
        if not mp4.exists():
            print(f"[skip] 파일 없음 {mp4}")
            continue

        frames = tracker.track_video(mp4)
        feats = video_to_features(frames)          # (T, F)
        binl = np.array(labels[vid]["binlabels"], dtype=np.float32)

        # 프레임 수 안 맞으면 짧은 쪽에 맞춤 (추적이 프레임 하나 놓칠 수 있음)
        T = min(len(feats), len(binl))
        out_X.append(feats[:T])
        out_y.append(binl[:T])
        out_ids.append(vid)

        if i % 50 == 0 or i == total:
            print(f"  {i}/{total} 처리됨 (마지막 {vid}, T={T})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, help="CarCrash/videos 폴더")
    ap.add_argument("--ann", required=True, help="Crash-1500.txt 경로")
    ap.add_argument("--out", default="data/ccd_features.npz")
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--device", default=None, help="cuda:0 등. 비우면 자동")
    args = ap.parse_args()

    print("라벨 로딩...")
    labels = load_labels(args.ann)
    print(f"  사고영상 {len(labels)}개")

    tracker = Tracker(weights=args.weights, conf=args.conf, device=args.device)

    X, y, ids = [], [], []
    crash_dir = Path(args.videos) / "Crash-1500"
    print(f"사고영상 처리 시작 ({crash_dir})")
    process_split(tracker, crash_dir, labels, X, y, ids)

    # 가변 길이 시퀀스라 object 배열로 저장
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        X=np.array(X, dtype=object),
        y=np.array(y, dtype=object),
        ids=np.array(ids),
        feature_dim=N_FEATURES,
    )
    print(f"저장 완료: {out}  (영상 {len(X)}개, feature차원 {N_FEATURES})")


if __name__ == "__main__":
    main()
