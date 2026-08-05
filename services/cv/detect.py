"""
YOLOv8 검출 래퍼.

프레임(numpy BGR) → 검출 박스 리스트.
차량/이륜/보행자만 남긴다 (과실 관련 객체).

COCO 클래스 기준:
    2 car, 3 motorcycle, 5 bus, 7 truck, 0 person, 1 bicycle
"""
from ultralytics import YOLO

# 과실에 관계있는 객체만 (COCO id: 이름)
KEEP_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


class Detector:
    def __init__(self, weights="yolov8n.pt", conf=0.3, device=None):
        # yolov8n = 가장 가벼운 모델. 정확도 필요하면 yolov8s/m 로.
        self.model = YOLO(weights)
        self.conf = conf
        self.device = device  # None이면 자동(GPU 있으면 GPU)

    def detect(self, frame):
        """
        frame: numpy BGR 이미지
        반환: [{"xyxy": (x1,y1,x2,y2), "cls": int, "name": str, "conf": float}, ...]
        """
        res = self.model.predict(
            frame, conf=self.conf, device=self.device, verbose=False
        )[0]

        boxes = []
        for b in res.boxes:
            cls = int(b.cls[0])
            if cls not in KEEP_CLASSES:
                continue
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append({
                "xyxy": (x1, y1, x2, y2),
                "cls": cls,
                "name": KEEP_CLASSES[cls],
                "conf": float(b.conf[0]),
            })
        return boxes
