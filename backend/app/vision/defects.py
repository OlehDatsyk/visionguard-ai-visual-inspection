"""Transparent image-processing heuristics for potential surface defects.

None of these functions recognise what a defect *is*. They measure how visually unusual a region
is on a mostly uniform surface. Scores are uncalibrated and every result needs human review.
Thresholds are documented in COMPUTER_VISION_GUIDE.md.
"""
import math

import cv2
import numpy as np

from app.vision.types import SCORE_HEURISTIC, Box, DefectCandidate


def _sigmoid(value: float, centre: float, slope: float) -> float:
    return 1.0 / (1.0 + math.exp(-(value - centre) / slope))


def _robust_z(values: np.ndarray) -> tuple[np.ndarray, float, float]:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median))) * 1.4826
    mad = max(mad, 1.0)
    return (values - median) / mad, median, mad


def _polygon(contour: np.ndarray, epsilon: float = 1.5) -> list[list[float]]:
    return cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2).astype(float).tolist()


def _contours(mask: np.ndarray) -> list[np.ndarray]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours


def detect_linear_features(gray: np.ndarray) -> list[DefectCandidate]:
    """Thin, long, high-contrast marks. Straight ones are scratch-like; irregular ones are crack-like."""
    height, width = gray.shape
    diagonal = math.hypot(height, width)
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    results: list[DefectCandidate] = []
    responses = (
        ("dark", cv2.morphologyEx(smooth, cv2.MORPH_BLACKHAT, kernel)),
        ("bright", cv2.morphologyEx(smooth, cv2.MORPH_TOPHAT, kernel)),
    )
    for polarity, response in responses:
        z_map, median, mad = _robust_z(response.astype(np.float32))
        threshold = max(median + 5.0 * mad, 18.0)
        mask = (response > threshold).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        for contour in _contours(mask):
            area = cv2.contourArea(contour)
            if area < 12:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            region = np.zeros_like(mask)
            cv2.drawContours(region, [contour], -1, 255, -1)
            inside = region > 0
            thickness = max(2.0 * float(distance[inside].mean()) * 1.5, 1.0)
            length = area / thickness
            elongation = length / thickness
            if length < diagonal * 0.025 or elongation < 5.0 or thickness > diagonal * 0.012:
                continue
            points = contour.reshape(-1, 2).astype(np.float32)
            vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
            deviation = np.abs((points[:, 0] - x0) * vy - (points[:, 1] - y0) * vx)
            straightness_residual = float(np.percentile(deviation, 90))
            contrast = float(response[inside].mean())
            score = (
                0.55 * _sigmoid(contrast, 34.0, 10.0)
                + 0.30 * _sigmoid(length / diagonal, 0.09, 0.03)
                + 0.15 * _sigmoid(elongation, 12.0, 4.0)
            )
            straight = straightness_residual <= max(thickness * 1.6, length * 0.012)
            category = "scratch_like" if straight else "crack_like"
            shape = "a straight, thin" if straight else "an irregular, thin"
            results.append(
                DefectCandidate(
                    category=category,
                    score=round(score, 3),
                    score_type=SCORE_HEURISTIC,
                    box=Box(x, y, w, h),
                    polygon=_polygon(contour),
                    method=f"Morphological {'black-hat' if polarity == 'dark' else 'top-hat'} + shape analysis",
                    explanation=(
                        f"A {polarity} mark with {shape} shape stands out from the surrounding surface. "
                        "Similar patterns are produced by seams, wires, grain, edges and shadows, so a "
                        "person must confirm whether this is real damage."
                    ),
                    metrics={
                        "length_px": round(length, 1),
                        "thickness_px": round(thickness, 1),
                        "elongation": round(elongation, 1),
                        "contrast": round(contrast, 1),
                    },
                )
            )
    return results


def detect_surface_anomalies(gray: np.ndarray, exclude: list[DefectCandidate] | None = None) -> list[DefectCandidate]:
    """Blobs whose brightness or texture departs strongly from the rest of the image.

    Regions already explained by a more specific check are excluded, so that this generic check
    reports only what the others did not.
    """
    height, width = gray.shape
    total = height * width
    sigma = max(height, width) / 12
    data = gray.astype(np.float32)
    covered = np.zeros(gray.shape, np.uint8)
    for candidate in exclude or []:
        if candidate.polygon and len(candidate.polygon) >= 3:
            cv2.fillPoly(covered, [np.array(candidate.polygon, dtype=np.int32)], 255)
    covered = cv2.dilate(covered, np.ones((15, 15), np.uint8))
    # Fill explained regions with the typical surface value first. Otherwise a large dark patch drags down
    # the blurred background estimate and creates a false halo of "anomaly" around itself.
    data[covered > 0] = float(np.median(data[covered == 0])) if (covered == 0).any() else float(np.median(data))
    background = cv2.GaussianBlur(data, (0, 0), sigma)
    residual = np.abs(cv2.GaussianBlur(data, (0, 0), 2.0) - background)
    mean = cv2.blur(data, (15, 15))
    texture = np.sqrt(np.maximum(cv2.blur(data * data, (15, 15)) - mean * mean, 0))
    z_residual, _, _ = _robust_z(residual)
    z_texture, _, _ = _robust_z(texture)
    z_map = np.maximum(z_residual, z_texture)
    mask = (z_map > 6.0).astype(np.uint8) * 255
    mask[cv2.dilate(covered, np.ones((17, 17), np.uint8)) > 0] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    results: list[DefectCandidate] = []
    for contour in _contours(mask):
        area = cv2.contourArea(contour)
        if area < total * 0.0008 or area > total * 0.30:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        region = np.zeros_like(mask)
        cv2.drawContours(region, [contour], -1, 255, -1)
        mean_z = float(z_map[region > 0].mean())
        score = 0.8 * _sigmoid(mean_z, 12.0, 4.0) + 0.2 * _sigmoid(area / total, 0.01, 0.01)
        results.append(
            DefectCandidate(
                category="surface_anomaly",
                score=round(score, 3),
                score_type=SCORE_HEURISTIC,
                box=Box(x, y, w, h),
                polygon=_polygon(contour, 2.5),
                method="Robust z-score of local brightness and texture",
                explanation=(
                    "Brightness or texture here differs strongly from the typical surface in this image "
                    f"(mean robust z-score {mean_z:.1f}). This measures unusualness only: labels, fixtures, "
                    "reflections and intentional features can score highly too."
                ),
                metrics={"mean_robust_z": round(mean_z, 1), "area_pct": round(area / total * 100, 2)},
            )
        )
    return results


def detect_discolouration(bgr: np.ndarray) -> list[DefectCandidate]:
    """Regions whose colour is far from the image's robust median colour."""
    height, width = bgr.shape[:2]
    total = height * width
    lab = cv2.cvtColor(cv2.GaussianBlur(bgr, (0, 0), 3), cv2.COLOR_BGR2LAB).astype(np.float32)
    # Chroma carries most of the signal; lightness is down-weighted to tolerate uneven lighting.
    delta_a = lab[:, :, 1] - np.median(lab[:, :, 1])
    delta_b = lab[:, :, 2] - np.median(lab[:, :, 2])
    delta_l = (lab[:, :, 0] - np.median(lab[:, :, 0])) * 0.3
    distance = np.sqrt(delta_a**2 + delta_b**2 + delta_l**2)
    z_map, median, mad = _robust_z(distance)
    threshold = max(median + 5.0 * mad, 12.0)
    mask = (distance > threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    results: list[DefectCandidate] = []
    for contour in _contours(mask):
        area = cv2.contourArea(contour)
        if area < total * 0.002 or area > total * 0.40:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        region = np.zeros_like(mask)
        cv2.drawContours(region, [contour], -1, 255, -1)
        delta = float(distance[region > 0].mean())
        score = 0.8 * _sigmoid(delta, 18.0, 6.0) + 0.2 * _sigmoid(area / total, 0.02, 0.015)
        results.append(
            DefectCandidate(
                category="discolouration",
                score=round(score, 3),
                score_type=SCORE_HEURISTIC,
                box=Box(x, y, w, h),
                polygon=_polygon(contour, 2.5),
                method="CIE LAB colour distance from robust median",
                explanation=(
                    f"The colour here differs from the image's typical colour (mean LAB distance {delta:.1f}). "
                    "Lighting, shadows, printed labels and multi-coloured materials can cause the same result."
                ),
                metrics={"mean_lab_distance": round(delta, 1), "area_pct": round(area / total * 100, 2)},
            )
        )
    return results


def detect_corrosion_like(bgr: np.ndarray) -> list[DefectCandidate]:
    """Rust-coloured and textured regions. Colour alone cannot confirm corrosion."""
    height, width = bgr.shape[:2]
    total = height * width
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    colour = cv2.inRange(hsv, (3, 70, 35), (24, 255, 215))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mean = cv2.blur(gray, (9, 9))
    texture = np.sqrt(np.maximum(cv2.blur(gray * gray, (9, 9)) - mean * mean, 0))
    mask = cv2.morphologyEx(colour, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    results: list[DefectCandidate] = []
    for contour in _contours(mask):
        area = cv2.contourArea(contour)
        if area < total * 0.002 or area > total * 0.60:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        region = np.zeros_like(mask)
        cv2.drawContours(region, [contour], -1, 255, -1)
        inside = region > 0
        mean_texture = float(texture[inside].mean())
        mean_saturation = float(hsv[:, :, 1][inside].mean())
        if mean_texture < 4.0:  # Smooth orange areas are likely paint or objects, not a rough corroded surface.
            continue
        score = 0.5 * _sigmoid(mean_texture, 12.0, 4.0) + 0.5 * _sigmoid(mean_saturation, 130.0, 30.0)
        results.append(
            DefectCandidate(
                category="corrosion_like",
                score=round(score, 3),
                score_type=SCORE_HEURISTIC,
                box=Box(x, y, w, h),
                polygon=_polygon(contour, 2.5),
                method="HSV rust-colour range with local texture",
                explanation=(
                    "This region combines a rust-like orange-brown colour with a rough texture. Paint, wood, "
                    "dirt and warm lighting look similar; chemical corrosion cannot be confirmed from a photo."
                ),
                metrics={
                    "mean_texture": round(mean_texture, 1),
                    "mean_saturation": round(mean_saturation, 1),
                    "area_pct": round(area / total * 100, 2),
                },
            )
        )
    return results


def merge_overlaps(candidates: list[DefectCandidate], limit: int = 40) -> list[DefectCandidate]:
    """Keep the strongest candidate where boxes overlap heavily, preferring more specific categories."""
    specificity = {"crack_like": 3, "scratch_like": 3, "corrosion_like": 2, "discolouration": 1, "surface_anomaly": 0}

    def contained(inner: Box, outer: Box) -> float:
        ix = max(0.0, min(inner.x + inner.width, outer.x + outer.width) - max(inner.x, outer.x))
        iy = max(0.0, min(inner.y + inner.height, outer.y + outer.height) - max(inner.y, outer.y))
        area = inner.width * inner.height
        return ix * iy / area if area > 0 else 0.0

    ordered = sorted(candidates, key=lambda c: (specificity.get(c.category, 0), c.score), reverse=True)
    kept: list[DefectCandidate] = []
    for candidate in ordered:
        if any(candidate.box.iou(k.box) > 0.5 or contained(candidate.box, k.box) > 0.8 for k in kept):
            continue
        kept.append(candidate)
    # A weak fragment inside a stronger specific region (for example, pits within rust) is not its own finding.
    final = [
        c for c in kept
        if not any(
            other is not c and other.category != "surface_anomaly" and other.score > c.score
            and other.box.width * other.box.height > c.box.width * c.box.height and contained(c.box, other.box) > 0.8
            for other in kept
        )
    ]
    return sorted(final, key=lambda c: c.score, reverse=True)[:limit]
