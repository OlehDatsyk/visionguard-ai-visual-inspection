"""Before-and-after comparison: alignment, similarity metrics and difference regions."""
from dataclasses import dataclass

import cv2
import numpy as np

WORKING_MAX_SIDE = 1200
MIN_INLIERS = 20
MIN_INLIER_RATIO = 0.30

METRIC_EXPLANATIONS = {
    "ssim": (
        "Structural Similarity Index (1.0 = identical). Compares local luminance, contrast and structure. "
        "It measures visual similarity, not physical condition."
    ),
    "changed_area_pct": (
        "Share of the compared area where brightness-corrected pixel differences exceed an automatically "
        "chosen threshold. It can be caused by lighting, shadows, angle or compression."
    ),
    "mean_absolute_difference": "Average per-pixel grey-level difference (0 to 255) after brightness correction.",
    "edge_difference_pct": "Share of detected edges that appear in only one image. Sensitive to alignment and focus.",
    "feature_inlier_ratio": "Share of matched ORB features consistent with one camera transform. Higher means more reliable alignment.",
    "brightness_shift": "Average brightness change from before to after, before correction (grey levels).",
}

LIMITATIONS = [
    "A difference is not proof of physical damage or change.",
    "Lighting, shadows, reflections, camera angle, focus and compression all create differences.",
    "Subtle changes can fall below the threshold for a highlighted region. Check the heatmap for faint differences.",
    "Alignment assumes a mostly flat scene. Objects at different depths cannot align perfectly from different viewpoints.",
]


@dataclass
class ComparisonOutput:
    metrics: dict
    regions: list[dict]
    warnings: list[str]
    width: int
    height: int
    before_jpg: bytes
    aligned_jpg: bytes
    heatmap_jpg: bytes
    mask_png: bytes


def _resize(image: np.ndarray, size: tuple[int, int] | None = None) -> np.ndarray:
    if size is None:
        scale = min(1.0, WORKING_MAX_SIDE / max(image.shape[:2]))
        return image if scale == 1.0 else cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def align_images(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Register `after` onto `before` with ORB + RANSAC. Falls back to a plain resize when unreliable."""
    height, width = before.shape[:2]
    resized = cv2.resize(after, (width, height), interpolation=cv2.INTER_AREA)
    full_mask = np.full((height, width), 255, np.uint8)
    info = {"status": "not_aligned", "matches": 0, "inliers": 0, "inlier_ratio": 0.0}
    orb = cv2.ORB_create(4000)
    gray_a = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)
    if des_a is None or des_b is None or len(kp_a) < 8 or len(kp_b) < 8:
        return resized, full_mask, info
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des_b, des_a, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    info["matches"] = len(good)
    if len(good) < MIN_INLIERS:
        return resized, full_mask, info
    src = np.float32([kp_b[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_a[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if matrix is None or inlier_mask is None:
        return resized, full_mask, info
    inliers = int(inlier_mask.sum())
    ratio = inliers / len(good)
    info.update(inliers=inliers, inlier_ratio=round(ratio, 3))
    determinant = float(np.linalg.det(matrix[:2, :2]))
    if inliers < MIN_INLIERS or ratio < MIN_INLIER_RATIO or not 0.3 < determinant < 3.0:
        return resized, full_mask, info
    aligned = cv2.warpPerspective(after, matrix, (width, height), flags=cv2.INTER_LINEAR)
    valid = cv2.warpPerspective(np.full(after.shape[:2], 255, np.uint8), matrix, (width, height), flags=cv2.INTER_NEAREST)
    valid = cv2.erode(valid, np.ones((5, 5), np.uint8))
    info["status"] = "aligned"
    return aligned, valid, info


def ssim_map(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Standard SSIM with an 11 x 11 Gaussian window (sigma 1.5)."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    a, b = a.astype(np.float64), b.astype(np.float64)
    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)
    var_a = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu_a**2
    var_b = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu_b**2
    cov = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_a * mu_b
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a**2 + mu_b**2 + c1) * (var_a + var_b + c2))


def _encode(ext: str, image: np.ndarray, params=None) -> bytes:
    ok, encoded = cv2.imencode(ext, image, params or [])
    if not ok:
        raise ValueError("Could not encode comparison output")
    return encoded.tobytes()


def compare_images(before_raw: np.ndarray, after_raw: np.ndarray) -> ComparisonOutput:
    before = _resize(before_raw)
    height, width = before.shape[:2]
    after = _resize(after_raw)
    aligned, valid, alignment = align_images(before, after)
    warnings: list[str] = []

    aspect_a = before_raw.shape[1] / before_raw.shape[0]
    aspect_b = after_raw.shape[1] / after_raw.shape[0]
    if abs(aspect_a - aspect_b) / aspect_a > 0.03 and alignment["status"] != "aligned":
        warnings.append("The images have different shapes and could not be aligned, so one was stretched to fit.")
    if alignment["status"] != "aligned":
        warnings.append(
            "Reliable alignment was not possible. If the images were not taken from the same position, "
            "most of the reported difference may simply be misalignment."
        )

    usable = valid > 0
    overlap = float(usable.mean())
    if overlap < 0.7:
        warnings.append(f"The aligned images overlap by only {overlap * 100:.0f}%. Only the overlap was compared.")

    gray_a = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    shift = float(gray_b[usable].mean() - gray_a[usable].mean())
    if abs(shift) > 15:
        warnings.append(
            f"Average brightness changed by {shift:+.0f} grey levels, which suggests different lighting. "
            "Treat the differences with caution."
        )
    # Remove the global brightness offset, so a uniform lighting change is not reported as a region.
    corrected = np.clip(gray_b.astype(np.float32) - shift, 0, 255).astype(np.uint8)
    similarity = ssim_map(gray_a, corrected)
    mean_ssim = float(similarity[usable].mean())

    blur_a = cv2.GaussianBlur(gray_a, (5, 5), 0)
    blur_b = cv2.GaussianBlur(corrected, (5, 5), 0)
    absdiff = cv2.absdiff(blur_a, blur_b)
    absdiff[~usable] = 0
    otsu, _ = cv2.threshold(absdiff[usable].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(float(otsu), 25.0)  # Floor avoids amplifying sensor noise in near-identical images.
    mask = (absdiff > threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    edges_a = cv2.Canny(blur_a, 60, 160) > 0
    edges_b = cv2.Canny(blur_b, 60, 160) > 0
    near_a = cv2.dilate(edges_a.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    near_b = cv2.dilate(edges_b.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    only_one = ((edges_a & ~near_b) | (edges_b & ~near_a)) & usable
    edge_total = int(((edges_a | edges_b) & usable).sum())

    total = int(usable.sum())
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < total * 0.0005:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        regions.append(
            {"x": x, "y": y, "width": w, "height": h, "area_pct": round(area / total * 100, 2)}
        )
        if len(regions) == 25:
            break

    metrics = {
        "ssim": round(mean_ssim, 4),
        "changed_area_pct": round(float((mask > 0)[usable].mean() * 100), 2),
        "mean_absolute_difference": round(float(absdiff[usable].mean()), 2),
        "edge_difference_pct": round(float(only_one.sum()) / edge_total * 100, 2) if edge_total else 0.0,
        "feature_inlier_ratio": alignment["inlier_ratio"],
        "brightness_shift": round(shift, 1),
        "alignment_status": alignment["status"],
        "feature_matches": alignment["matches"],
        "feature_inliers": alignment["inliers"],
        "overlap_pct": round(overlap * 100, 1),
        "difference_threshold": round(threshold, 1),
    }

    normalised = cv2.normalize(cv2.GaussianBlur(absdiff, (0, 0), 3), None, 0, 255, cv2.NORM_MINMAX)
    colour = cv2.applyColorMap(normalised.astype(np.uint8), cv2.COLORMAP_TURBO)
    base = cv2.cvtColor(gray_a, cv2.COLOR_GRAY2BGR)
    heatmap = cv2.addWeighted(base, 0.45, colour, 0.55, 0)
    heatmap[~usable] = (40, 30, 25)
    jpeg = [cv2.IMWRITE_JPEG_QUALITY, 88]
    return ComparisonOutput(
        metrics, regions, warnings, width, height,
        _encode(".jpg", before, jpeg), _encode(".jpg", aligned, jpeg), _encode(".jpg", heatmap, jpeg), _encode(".png", mask),
    )
