"""
추적 래퍼.

ultralytics YOLO에 ByteTrack이 내장돼 있어서 model.track()을 그대로 쓴다.
(별도 ByteTrack 설치 불필요 — 복잡성 제거)

영상 하나 → 프레임별 [track_id 달린 박스] 시퀀스.
"""
from ultralytics import YOLO
from .detect import KEEP_CLASSES


class Tracker:
    def __init__(self, weights="yolov8n.pt", conf=0.3, device=None):
        self.model = YOLO(weights)
        self.conf = conf
        self.device = device

    def track_video(self, video_path):
        """
        video_path: mp4 경로
        반환: 프레임 리스트. 각 원소는 그 프레임의 박스 리스트.
              박스 = {"tid": int, "xyxy": (x1,y1,x2,y2), "cls": int,
                      "name": str, "conf": float}
        tid(track_id)로 같은 객체를 프레임 간 연결.
        """
        results = self.model.track(
            source=str(video_path),
            conf=self.conf,
            device=self.device,
            persist=True,          # 프레임 간 id 유지
            tracker="bytetrack.yaml",
            verbose=False,
            stream=True,           # 프레임 단위로 하나씩 (메모리 절약)
        )

        frames = []
        for res in results:
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
            frames.append(boxes)
        return frames
