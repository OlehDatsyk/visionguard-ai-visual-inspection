# Computer vision guide

## Three different things

These are not interchangeable, and the application keeps them apart everywhere.

| Term | Question it answers | Here |
|---|---|---|
| **Object detection** | What known thing is this? | A neural network, for 80 COCO categories |
| **Anomaly detection** | Does this region look unusual compared with the rest of the image? | OpenCV heuristics, reported as *potential* defects |
| **Confirmed defect identification** | Is this actually damage? | **Only a person can decide**, by marking a finding as confirmed |

A high anomaly score never means a confirmed defect.

## Supported images

JPEG, PNG and WebP. By default, up to 20 MB, 40 megapixels and 12,000 pixels per side, with at least 32 pixels per side. Animated images are refused. Other formats, including GIF and SVG, are refused.

## Processing pipeline

1. **Validate and store** the upload. The original stays byte-identical.
2. **Create the display copy:** EXIF orientation applied, EXIF removed, at most 2400 pixels on the long side. All analysis uses this copy, downsized to 1400 pixels for the heuristics.
3. **Measure quality:** focus measure, brightness, contrast, clipping and edge density.
4. **Detect objects,** if the model is installed.
5. **Run the category's heuristics,** unless the scene is too complex.
6. **Flag manual inspection areas** where exposure clipping hides detail.
7. **Save results,** and render a separate annotated image.

## Object detection

| Property | Value |
|---|---|
| Model | YOLOX-Tiny, COCO weights |
| Runtime | ONNX Runtime on CPU, no GPU needed |
| Input | Letterboxed to 416 x 416 |
| Default threshold | 0.25, adjustable in Settings |
| Licence | Apache-2.0 |

Weights are downloaded by `backend/scripts/download_models.py`, verified by SHA-256 and never committed. The model loads on first use, so startup and health checks stay fast. If the weights are missing, detection reports itself as unavailable, and the note appears on each analysed image. Nothing is faked.

## Defect-analysis methods

Each module reports its method in plain language with every finding.

| Finding | Method | Also triggered by |
|---|---|---|
| **Crack-like, scratch-like** | Morphological black-hat and top-hat, then components filtered on length, thickness and elongation. Line-fit residual separates straight from irregular | Seams, wires, grain, edges, shadows |
| **Surface anomaly** | Background-subtracted brightness and local texture, scored by robust z-score (median and MAD). Ignores regions other checks already explain | Labels, fixtures, reflections |
| **Discolouration** | CIE LAB distance from the image's robust median colour, with lightness down-weighted | Shadows, printed labels, multi-coloured materials |
| **Corrosion-like** | HSV rust-colour range combined with local roughness | Paint, wood, dirt, warm light |
| **Manual inspection area** | Clipped highlights or shadows covering at least 1% of the image | Reports only that analysis was not possible |

### What it cannot assess

Each category lists its gaps in the UI and in reports. They include dents (no depth from a single photo), missing components (needs a reference, so use Image Comparison), structural integrity, internal damage and mechanical function.

### When heuristics are skipped

The methods assume a mostly uniform surface. Above an edge density of 0.09, they are skipped and a note explains why, because running them would mostly produce noise.

## Segmentation

- **Findings** carry outlines from their threshold masks.
- **Objects:** up to 8 detections per image get a GrabCut outline, seeded by the detector's box. GrabCut uses colour statistics and knows nothing about the object class, so outlines are labelled as approximate. If the result is degenerate, the object keeps only its box.

## Detection confidence

| Band | Model confidence | Heuristic score |
|---|---|---|
| High | 0.70 or more | Not available |
| Medium | 0.45 to 0.69 | 0.70 or more |
| Low | 0.25 to 0.44 | 0.45 to 0.69 |
| Unverified | Below 0.25 | Below 0.45 |

- Model confidence is the model's internal score, **not** a calibrated probability of being correct.
- Heuristic scores are hand-designed functions of measured contrast and shape. They are comparable only roughly, and they rank "how unusual", not "how likely to be damage".
- Heuristic findings under 0.25 are discarded.

No accuracy, precision or recall figures are given anywhere, because no labelled ground-truth dataset has been evaluated. The thresholds were tuned on generated samples, so test on your own images.

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `MODEL_DIR` | `backend/model_weights` | Location of the weights |
| `DETECTOR_INPUT_SIZE` | 416 | Must match the model |
| `DETECTOR_CONFIDENCE_THRESHOLD` | 0.25 | Default threshold. Users can override it in Settings |
| `ONNX_THREADS` | 2 | CPU threads for inference |

Categories and their modules are defined in `backend/app/vision/profiles.py`.

## Adding another model

1. Check the licence of the code **and** the weights for your intended use.
2. Implement `ObjectDetector` from `vision/detectors/base.py`:

```python
class MyDetector(ObjectDetector):
    info = ModelInfo(key="my_model", name="My model", ...)  # Shown on the Model Information page

    def is_available(self) -> bool: ...                     # Must not load the model
    def unavailable_reason(self) -> str | None: ...
    def detect(self, bgr, confidence_threshold) -> list[ObjectDetection]: ...
```

3. Register it in `vision/detectors/registry.py`.
4. Add a fetch script or instructions. Do not commit weights.
5. Add tests using known images, as `tests/test_vision.py` does for YOLOX.

A trained defect model should report `SCORE_MODEL` scores, and its limitations should state what it was trained on. Do not claim a capability you have not measured.
