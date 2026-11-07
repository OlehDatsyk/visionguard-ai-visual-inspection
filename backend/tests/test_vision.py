"""Vision tests on controlled inputs, plus real-model tests that skip when weights are absent."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.vision import defects
from app.vision.comparison import compare_images, ssim_map
from app.vision.detectors.registry import set_detector
from app.vision.detectors.yolox_onnx import COCO_LABELS, YoloxOnnxDetector
from app.vision.pipeline import decode_image, render_annotated, run_pipeline
from app.vision.profiles import CATEGORIES, UNSUPPORTED
from app.vision.quality import manual_inspection_areas, measure_quality
from app.vision.segmentation import refine_with_grabcut
from app.vision.types import SCORE_HEURISTIC, SCORE_MODEL, Box, ObjectDetection, confidence_band
from tests.conftest import surface_with_crack

SAMPLES = Path(__file__).resolve().parents[1] / "app" / "demo" / "samples"


def uniform(size=(400, 600), value=160, noise=1.5, seed=3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((*size, 3), value, np.float32) + rng.normal(0, noise, (*size, 3))
    return np.clip(image, 0, 255).astype(np.uint8)


def test_confidence_bands():
    assert confidence_band(0.9, SCORE_MODEL) == "high"
    assert confidence_band(0.5, SCORE_MODEL) == "medium"
    assert confidence_band(0.3, SCORE_MODEL) == "low"
    assert confidence_band(0.1, SCORE_MODEL) == "unverified"


def test_heuristic_scores_can_never_be_high_confidence():
    assert confidence_band(1.0, SCORE_HEURISTIC) == "medium"
    assert confidence_band(0.5, SCORE_HEURISTIC) == "low"
    assert confidence_band(0.3, SCORE_HEURISTIC) == "unverified"


def test_clean_surface_produces_no_defects():
    result = run_pipeline(uniform(), "surface_material")
    assert [f for f in result.findings if f.finding_type == "potential_defect"] == []


def test_irregular_line_located_as_crack_like():
    gray = cv2.cvtColor(decode_image(surface_with_crack()), cv2.COLOR_BGR2GRAY)
    found = defects.detect_linear_features(gray)
    assert found and found[0].category == "crack_like"
    box = found[0].box
    assert box.x < 80 and box.x + box.width > 500  # Spans the drawn line, from x=60 to x=540.
    assert found[0].polygon and "person must confirm" in found[0].explanation


def test_straight_line_located_as_scratch_like():
    image = uniform()
    cv2.line(image, (60, 60), (520, 300), (230, 230, 230), 2, cv2.LINE_AA)
    found = defects.detect_linear_features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    assert found and found[0].category == "scratch_like"


def test_stain_located_as_discolouration():
    image = uniform()
    cv2.circle(image, (300, 200), 50, (110, 150, 200), -1)
    found = defects.detect_discolouration(cv2.GaussianBlur(image, (5, 5), 0))
    assert len(found) == 1
    box = found[0].box
    assert abs(box.x + box.width / 2 - 300) < 15 and abs(box.y + box.height / 2 - 200) < 15


def test_rough_rust_coloured_area_is_corrosion_like_but_smooth_is_not():
    rng = np.random.default_rng(5)
    rough = uniform()
    patch = np.zeros((120, 120, 3), np.float32) + (35, 80, 165)
    rough[140:260, 240:360] = np.clip(patch + rng.normal(0, 18, patch.shape), 0, 255).astype(np.uint8)
    assert [f.category for f in defects.detect_corrosion_like(rough)] == ["corrosion_like"]
    smooth = uniform(noise=0.2)
    smooth[140:260, 240:360] = (35, 80, 165)
    # Flat paint has no surface roughness inside the region, apart from its boundary.
    results = defects.detect_corrosion_like(cv2.GaussianBlur(smooth, (3, 3), 0))
    assert all(f.score < 0.6 for f in results)


def test_surface_anomaly_found_and_excludes_explained_regions():
    gray = cv2.cvtColor(uniform(), cv2.COLOR_BGR2GRAY)
    cv2.circle(gray, (300, 200), 25, 60, -1)
    found = defects.detect_surface_anomalies(gray)
    assert len(found) >= 1 and found[0].category == "surface_anomaly"
    assert defects.detect_surface_anomalies(gray, found) == []


def test_overlap_merge_prefers_specific_category():
    make = lambda c, s, b: defects.DefectCandidate(c, s, SCORE_HEURISTIC, Box(*b), "m", "e")
    merged = defects.merge_overlaps([make("surface_anomaly", 0.9, (10, 10, 100, 100)), make("crack_like", 0.5, (12, 12, 95, 95))])
    assert [c.category for c in merged] == ["crack_like"]


def test_complex_scene_skips_heuristics_and_says_so():
    rng = np.random.default_rng(1)
    busy = uniform()
    for _ in range(600):
        p = rng.integers(0, [600, 400], 2).tolist()
        cv2.rectangle(busy, p, (p[0] + 20, p[1] + 20), rng.integers(0, 255, 3).tolist(), 1)
    result = run_pipeline(busy, "surface_material")
    assert any("skipped" in note for note in result.notes)
    assert [f for f in result.findings if f.finding_type == "potential_defect"] == []


def test_clipped_exposure_becomes_manual_inspection_area():
    image = uniform()
    image[50:200, 100:300] = 255
    areas = manual_inspection_areas(image)
    assert areas and areas[0].finding_type == "manual_inspection" and areas[0].score_type == "image_quality"
    assert confidence_band(areas[0].score, areas[0].score_type) == "unverified"


def test_unsupported_checks_are_reported_for_categories():
    result = run_pipeline(uniform(), "vehicle_damage")
    assert any(u["check"] == "dents" for u in result.unsupported)
    assert set(CATEGORIES["vehicle_damage"]["unsupported"]) <= set(UNSUPPORTED)


def test_object_recognition_category_runs_no_defect_heuristics():
    result = run_pipeline(decode_image(surface_with_crack()), "object_recognition")
    assert result.findings == []


def test_unavailable_detector_is_reported_not_faked():
    class Missing(YoloxOnnxDetector):
        def unavailable_reason(self):
            return "Model weights are not installed."

    set_detector(Missing())
    result = run_pipeline(uniform(), "surface_material")
    assert result.objects == []
    assert any("did not run" in note for note in result.notes)


def test_annotated_image_is_valid_and_input_is_unchanged():
    image = decode_image(surface_with_crack())
    before = image.copy()
    output = render_annotated(image, run_pipeline(image, "surface_material"))
    assert decode_image(output).shape == image.shape
    assert np.array_equal(image, before)


def test_quality_measures():
    quality = measure_quality(uniform())
    assert quality["edge_density"] < 0.01 and 150 < quality["mean_brightness"] < 170


def test_grabcut_outlines_a_contrasting_object():
    image = uniform(value=210, noise=3)
    cv2.circle(image, (300, 200), 70, (40, 40, 180), -1)
    detection = ObjectDetection("thing", 0.9, Box(215, 115, 170, 170))
    refine_with_grabcut(image, [detection])
    assert detection.segmentation_method == "grabcut_from_box" and len(detection.polygon) >= 3
    xs = [p[0] for p in detection.polygon]
    assert 215 <= min(xs) <= 250 and 350 <= max(xs) <= 385


# Comparison ---------------------------------------------------------------------------------------
@pytest.fixture
def textured():
    return cv2.imread(str(SAMPLES / "coffee.png"))


def test_ssim_identical_is_one():
    image = cv2.cvtColor(uniform(noise=10), cv2.COLOR_BGR2GRAY)
    assert ssim_map(image, image).mean() == pytest.approx(1.0)


def test_identical_images(textured):
    output = compare_images(textured, textured.copy())
    assert output.metrics["ssim"] > 0.999
    assert output.metrics["changed_area_pct"] == 0
    assert output.regions == []


def test_alignment_recovers_camera_shift_and_finds_real_change(textured):
    height, width = textured.shape[:2]
    matrix = np.float32([[1, 0, 18], [0, 1, -12]])
    after = textured.copy()
    cv2.rectangle(after, (240, 150), (320, 230), (30, 30, 230), -1)
    moved = cv2.warpAffine(after, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
    output = compare_images(textured, moved)
    assert output.metrics["alignment_status"] == "aligned"
    assert output.metrics["feature_inlier_ratio"] > 0.5
    assert output.regions
    region = output.regions[0]
    assert abs(region["x"] + region["width"] / 2 - 280) < 25
    assert abs(region["y"] + region["height"] / 2 - 190) < 25


def test_uniform_lighting_change_warns_and_is_not_a_region(textured):
    brighter = np.clip(textured.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    output = compare_images(textured, brighter)
    assert any("lighting" in warning for warning in output.warnings)
    assert output.metrics["brightness_shift"] > 20
    assert output.metrics["changed_area_pct"] < 5


def test_unrelated_images_warn_about_alignment(textured):
    other = cv2.imread(str(SAMPLES / "chelsea.png"))
    output = compare_images(textured, other)
    assert output.metrics["alignment_status"] == "not_aligned"
    assert any("alignment" in warning.lower() for warning in output.warnings)
    assert output.metrics["ssim"] < 0.8


def test_low_texture_images_do_not_crash():
    output = compare_images(uniform(noise=0), uniform(noise=0))
    assert output.metrics["alignment_status"] == "not_aligned" and output.metrics["ssim"] > 0.99


# Real model, skipped when weights have not been downloaded ----------------------------------------
detector = YoloxOnnxDetector()
needs_model = pytest.mark.skipif(not detector.is_available(), reason="YOLOX weights are not installed")


@needs_model
@pytest.mark.parametrize("filename,label", [("chelsea.png", "cat"), ("coffee.png", "cup")])
def test_real_yolox_finds_expected_object(filename, label):
    image = cv2.imread(str(SAMPLES / filename))
    results = detector.detect(image, 0.25)
    match = [d for d in results if d.label == label]
    assert match and match[0].confidence > 0.5
    box = match[0].box
    assert 0 <= box.x and box.x + box.width <= image.shape[1] and box.width > 50


@needs_model
def test_real_yolox_finds_no_cat_on_a_blank_surface():
    assert not [d for d in detector.detect(uniform(), 0.5) if d.label == "cat"]


def test_label_list_is_complete():
    assert len(COCO_LABELS) == 80 and "traffic light" in COCO_LABELS
