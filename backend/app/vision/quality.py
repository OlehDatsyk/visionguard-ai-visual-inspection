"""Image quality measurements and areas that need a person to look at them."""
import cv2
import numpy as np

from app.vision.types import SCORE_QUALITY, Box, DefectCandidate

LOW_FOCUS = 40.0
COMPLEX_SCENE_EDGE_DENSITY = 0.09


def measure_quality(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    return {
        "focus_measure": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1),
        "mean_brightness": round(float(gray.mean()), 1),
        "contrast": round(float(gray.std()), 1),
        "underexposed_pct": round(float((gray < 12).mean() * 100), 2),
        "overexposed_pct": round(float((gray > 248).mean() * 100), 2),
        "edge_density": round(float((edges > 0).mean()), 4),
    }


def quality_notes(quality: dict) -> list[str]:
    notes = []
    if quality["focus_measure"] < LOW_FOCUS:
        notes.append("Little fine detail was measured. The image may be out of focus, or the surface may simply be smooth; fine defects could be missed.")
    if quality["contrast"] < 12:
        notes.append("The image has low overall contrast. Faint marks may not be separated from the background.")
    if quality["mean_brightness"] < 40:
        notes.append("The image is dark. Defects in shadow may be missed.")
    if quality["mean_brightness"] > 225:
        notes.append("The image is very bright. Detail may be lost to overexposure.")
    return notes


def is_complex_scene(quality: dict) -> bool:
    """Surface heuristics assume a mostly uniform surface; busy scenes would produce noise."""
    return quality["edge_density"] > COMPLEX_SCENE_EDGE_DENSITY


def manual_inspection_areas(bgr: np.ndarray) -> list[DefectCandidate]:
    """Flag regions where analysis could not see properly: clipped exposure areas."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    total = height * width
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    results: list[DefectCandidate] = []
    for name, mask in (("overexposed", gray > 250), ("underexposed", gray < 8)):
        clean = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            area = cv2.contourArea(contour)
            if area < total * 0.01:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            polygon = cv2.approxPolyDP(contour, 3, True).reshape(-1, 2).astype(float).tolist()
            results.append(
                DefectCandidate(
                    category="manual_inspection",
                    finding_type="manual_inspection",
                    score=0.0,
                    score_type=SCORE_QUALITY,
                    box=Box(x, y, w, h),
                    polygon=polygon,
                    method=f"Exposure clipping check ({name})",
                    explanation=(
                        f"This area is {name}, so surface detail is lost and it could not be analysed. "
                        "Inspect it manually or retake the photo."
                    ),
                    metrics={"area_pct": round(area / total * 100, 2)},
                )
            )
    return results
