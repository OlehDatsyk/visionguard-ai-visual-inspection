"""The active object detector. Tests replace it through set_detector()."""
from app.vision.detectors.base import ObjectDetector
from app.vision.detectors.yolox_onnx import YoloxOnnxDetector

_detector: ObjectDetector = YoloxOnnxDetector()


def get_detector() -> ObjectDetector:
    return _detector


def set_detector(detector: ObjectDetector) -> None:
    global _detector
    _detector = detector
