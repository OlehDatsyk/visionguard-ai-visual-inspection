"""Object segmentation masks using GrabCut seeded by detector boxes.

This classical method separates foreground from background using colour statistics inside a box.
It does not know the object class, and is reported to users as an approximate outline.
"""
import cv2
import numpy as np

from app.vision.types import ObjectDetection

MAX_SIDE = 220


def refine_with_grabcut(bgr: np.ndarray, detections: list[ObjectDetection], limit: int = 8) -> None:
    height, width = bgr.shape[:2]
    for detection in detections[:limit]:
        box = detection.box
        pad_x, pad_y = box.width * 0.06, box.height * 0.06
        x1, y1 = int(max(0, box.x - pad_x)), int(max(0, box.y - pad_y))
        x2, y2 = int(min(width, box.x + box.width + pad_x)), int(min(height, box.y + box.height + pad_y))
        crop = bgr[y1:y2, x1:x2]
        if crop.shape[0] < 24 or crop.shape[1] < 24:
            continue
        scale = min(1.0, MAX_SIDE / max(crop.shape[:2]))
        small = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        mask = np.zeros(small.shape[:2], np.uint8)
        rect = (
            max(1, int((box.x - x1) * scale)),
            max(1, int((box.y - y1) * scale)),
            max(2, min(small.shape[1] - 2, int(box.width * scale))),
            max(2, min(small.shape[0] - 2, int(box.height * scale))),
        )
        try:
            cv2.grabCut(small, mask, rect, np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_RECT)
        except cv2.error:
            continue
        foreground = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8) * 255
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        coverage = cv2.contourArea(contour) / max(1.0, rect[2] * rect[3])
        if coverage < 0.08 or coverage > 0.98:  # A degenerate mask adds nothing beyond the box.
            continue
        points = cv2.approxPolyDP(contour, 1.5, True).reshape(-1, 2).astype(float) / scale
        points += [x1, y1]
        detection.polygon = points.tolist()
        detection.segmentation_method = "grabcut_from_box"
