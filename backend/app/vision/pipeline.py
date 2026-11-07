"""Orchestrates quality checks, object detection and defect heuristics for a single image."""
import time

import cv2
import numpy as np

from app.core.config import get_settings
from app.vision import defects, quality as quality_mod
from app.vision.detectors.registry import get_detector
from app.vision.profiles import CATEGORIES, unsupported_for
from app.vision.segmentation import refine_with_grabcut
from app.vision.types import Box, DefectCandidate, ObjectDetection, PipelineResult

WORKING_MAX_SIDE = 1400


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image could not be decoded")
    return image


def _resize_for_work(bgr: np.ndarray) -> tuple[np.ndarray, float]:
    scale = min(1.0, WORKING_MAX_SIDE / max(bgr.shape[:2]))
    if scale == 1.0:
        return bgr, 1.0
    return cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), scale


def _rescale(finding: DefectCandidate, factor: float) -> DefectCandidate:
    if factor != 1.0:
        finding.box = finding.box.scaled(factor)
        if finding.polygon:
            finding.polygon = [[p[0] * factor, p[1] * factor] for p in finding.polygon]
    return finding


def run_pipeline(bgr: np.ndarray, category: str, confidence_threshold: float | None = None) -> PipelineResult:
    profile = CATEGORIES[category]
    threshold = confidence_threshold or get_settings().detector_confidence_threshold
    notes: list[str] = []
    timings: dict[str, int] = {}

    def timed(name, func, *args):
        started = time.perf_counter()
        result = func(*args)
        timings[name] = int((time.perf_counter() - started) * 1000)
        return result

    working, scale = _resize_for_work(bgr)
    back = 1.0 / scale
    quality = timed("quality", quality_mod.measure_quality, working)
    notes.extend(quality_mod.quality_notes(quality))

    objects: list[ObjectDetection] = []
    detector = get_detector()
    if detector.is_available():
        objects = timed("object_detection", detector.detect, bgr, threshold)
        timed("segmentation", refine_with_grabcut, bgr, objects)
    else:
        notes.append(f"Object detection did not run: {detector.unavailable_reason()}")

    findings: list[DefectCandidate] = []
    modules = profile["modules"]
    if modules:
        if quality_mod.is_complex_scene(quality):
            # Heuristics assume a mostly uniform surface. Reporting them on a busy scene would be noise.
            notes.append(
                "Surface heuristics were skipped: this image is a visually complex scene (edge density "
                f"{quality['edge_density']:.3f}), and these checks only work on mostly uniform surfaces. "
                "Photograph the surface close up, or inspect it manually."
            )
        else:
            gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
            candidates: list[DefectCandidate] = []
            if "linear" in modules:
                candidates += timed("linear_features", defects.detect_linear_features, gray)
            if "discolouration" in modules:
                candidates += timed("discolouration", defects.detect_discolouration, working)
            if "corrosion" in modules:
                candidates += timed("corrosion_like", defects.detect_corrosion_like, working)
            if "surface_anomaly" in modules:  # Runs last: it ignores regions the specific checks explain.
                candidates += timed("surface_anomaly", defects.detect_surface_anomalies, gray, candidates)
            findings = defects.merge_overlaps([c for c in candidates if c.score >= 0.25])
        findings += quality_mod.manual_inspection_areas(working)

    findings = [_rescale(f, back) for f in findings]
    return PipelineResult(objects, findings, quality, notes, unsupported_for(category), timings)


COLOURS = {
    "high": (246, 211, 45), "medium": (70, 170, 250), "low": (120, 200, 250), "unverified": (170, 170, 170),
}


def render_annotated(bgr: np.ndarray, result: PipelineResult) -> bytes:
    """Create the separate processed image. The original stays untouched."""
    canvas = bgr.copy()
    overlay = canvas.copy()
    thickness = max(2, round(max(bgr.shape[:2]) / 700))
    font_scale = max(0.45, max(bgr.shape[:2]) / 1800)

    def label(text: str, x: int, y: int, colour) -> None:
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        top = max(th + 6, y)
        cv2.rectangle(canvas, (x, top - th - 6), (x + tw + 6, top), colour, -1)
        cv2.putText(canvas, text, (x + 3, top - 4), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (15, 15, 15), 1, cv2.LINE_AA)

    for finding in result.findings:
        if finding.polygon and len(finding.polygon) >= 3:
            points = np.array(finding.polygon, dtype=np.int32)
            cv2.fillPoly(overlay, [points], (60, 80, 240))
    canvas = cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0)
    for obj in result.objects:
        box: Box = obj.box
        p1, p2 = (int(box.x), int(box.y)), (int(box.x + box.width), int(box.y + box.height))
        cv2.rectangle(canvas, p1, p2, (246, 211, 45), thickness)
        label(f"{obj.label} {obj.confidence:.2f}", p1[0], p1[1], (246, 211, 45))
    for finding in result.findings:
        box = finding.box
        p1, p2 = (int(box.x), int(box.y)), (int(box.x + box.width), int(box.y + box.height))
        cv2.rectangle(canvas, p1, p2, (60, 80, 240), thickness)
        label(finding.category.replace("_", " "), p1[0], p1[1], (110, 130, 250))
    ok, encoded = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Could not encode processed image")
    return encoded.tobytes()
