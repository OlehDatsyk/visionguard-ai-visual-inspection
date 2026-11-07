"""YOLOX-Tiny object detection (Apache-2.0) running on CPU through ONNX Runtime."""
import threading
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings
from app.vision.detectors.base import ModelInfo, ObjectDetector
from app.vision.types import Box, ObjectDetection

COCO_CLASSES = (
    "person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign "
    "parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag tie "
    "suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard "
    "tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot "
    "hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote keyboard "
    "cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear hair_drier toothbrush"
).split()
COCO_LABELS = [c.replace("_", " ") for c in COCO_CLASSES]

WEIGHTS_FILE = "yolox_tiny.onnx"

INFO = ModelInfo(
    key="yolox_tiny",
    name="YOLOX-Tiny",
    model_type="Single-stage, anchor-free object detector (ONNX)",
    version="0.1.1rc0 release, COCO 2017 weights",
    licence="Apache-2.0 (Megvii YOLOX). Weights were trained on COCO; review COCO image terms for your use.",
    source="https://github.com/Megvii-BaseDetection/YOLOX",
    weights_file=WEIGHTS_FILE,
    input_requirements="BGR image, letterboxed to 416 x 416 pixels. Images are resized automatically.",
    processing="CPU inference through ONNX Runtime. No GPU required.",
    supported_categories=COCO_LABELS,
    limitations=[
        "Recognises only the 80 everyday COCO categories. It does not know industrial parts or defects.",
        "It cannot detect cracks, corrosion or damage; these come from separate image-processing heuristics.",
        "The tiny variant favours speed and misses small or heavily occluded objects more often than larger models.",
        "Confidence is the model's internal score, not a calibrated probability of being correct.",
    ],
)


class YoloxOnnxDetector(ObjectDetector):
    info = INFO

    def __init__(self) -> None:
        self._session = None
        self._lock = threading.Lock()

    @property
    def weights_path(self) -> Path:
        return Path(get_settings().model_dir) / WEIGHTS_FILE

    def is_available(self) -> bool:
        return self.unavailable_reason() is None

    def unavailable_reason(self) -> str | None:
        if not self.weights_path.is_file():
            return "Model weights are not installed. Run: python scripts/download_models.py"
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return "ONNX Runtime is not installed."
        return None

    def _load(self):
        # Loaded on first use so that startup and health checks stay fast.
        with self._lock:
            if self._session is None:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = get_settings().onnx_threads
                self._session = ort.InferenceSession(
                    str(self.weights_path), options, providers=["CPUExecutionProvider"]
                )
        return self._session

    def detect(self, bgr: np.ndarray, confidence_threshold: float) -> list[ObjectDetection]:
        session = self._load()
        size = get_settings().detector_input_size
        height, width = bgr.shape[:2]
        ratio = min(size / height, size / width)
        new_w, new_h = int(width * ratio), int(height * ratio)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[:new_h, :new_w] = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        blob = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        output = session.run(None, {session.get_inputs()[0].name: blob})[0][0]
        return self._decode(output, size, ratio, width, height, confidence_threshold)

    @staticmethod
    def _decode(output, size, ratio, width, height, threshold) -> list[ObjectDetection]:
        grids, strides = [], []
        for stride in (8, 16, 32):
            cells = size // stride
            xs, ys = np.meshgrid(np.arange(cells), np.arange(cells))
            grids.append(np.stack((xs, ys), axis=2).reshape(-1, 2))
            strides.append(np.full((cells * cells, 1), stride))
        grid, stride = np.concatenate(grids), np.concatenate(strides)
        centres = (output[:, :2] + grid) * stride
        sizes = np.exp(output[:, 2:4]) * stride
        class_scores = output[:, 5:] * output[:, 4:5]
        class_ids = class_scores.argmax(axis=1)
        scores = class_scores[np.arange(len(class_ids)), class_ids]
        keep = scores >= threshold
        if not keep.any():
            return []
        centres, sizes, scores, class_ids = centres[keep] / ratio, sizes[keep] / ratio, scores[keep], class_ids[keep]
        boxes = np.concatenate((centres - sizes / 2, sizes), axis=1)
        # Class-aware non-maximum suppression.
        results: list[ObjectDetection] = []
        for class_id in np.unique(class_ids):
            idx = np.where(class_ids == class_id)[0]
            kept = cv2.dnn.NMSBoxes(boxes[idx].tolist(), scores[idx].tolist(), threshold, 0.45)
            for i in np.array(kept).flatten():
                x, y, w, h = boxes[idx[i]]
                x1, y1 = max(0.0, float(x)), max(0.0, float(y))
                x2, y2 = min(float(width), float(x + w)), min(float(height), float(y + h))
                if x2 - x1 >= 2 and y2 - y1 >= 2:
                    results.append(
                        ObjectDetection(
                            COCO_LABELS[int(class_id)], float(scores[idx[i]]), Box(x1, y1, x2 - x1, y2 - y1)
                        )
                    )
        return sorted(results, key=lambda d: d.confidence, reverse=True)
