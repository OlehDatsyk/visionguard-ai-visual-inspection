# Image comparison guide

Image Comparison shows where two images differ. **A difference is not proof of physical damage or change.**

## Views

- **Side by side:** the before image and the aligned after image, with highlighted regions on both.
- **Overlay:** the after image over the before image, with a transparency slider.
- **Difference:** a heatmap over the before image. It is normalised to this pair, so warmer means larger *for this pair*. Colours can't be compared between different comparisons.

## Image alignment

1. ORB finds up to 4000 features in each image, downsized to at most 1200 pixels.
2. Lowe's ratio test (0.75) keeps distinctive matches.
3. RANSAC estimates a perspective transform.
4. Alignment is accepted only with at least 20 inliers, an inlier ratio of at least 0.30 and a plausible scale. Otherwise the after image is simply resized, and a prominent warning appears.

Areas outside the overlap are excluded from all metrics.

Alignment assumes a mostly flat scene or a very similar viewpoint. Objects at different depths cannot all line up after moving the camera. Low-texture surfaces offer few features and often can't be aligned.

## Difference detection

The average brightness shift is removed first, so a uniform lighting change is not reported as a region. Then the absolute difference is thresholded, using Otsu's method with a floor of 25 grey levels, and small specks are cleaned up. Regions of at least 0.05% of the area are outlined, up to 25.

Because the threshold adapts to the strongest differences, a faint change can stay below it when a strong one exists. Check the heatmap for faint differences.

## Similarity metrics

| Metric | Meaning | Be careful |
|---|---|---|
| **SSIM** | Structural similarity from luminance, contrast and structure. 1.0 means identical | Measures visual similarity, not condition |
| **Changed area** | Percentage of the compared area above the threshold | Inflated by shadows and misalignment |
| **Mean absolute difference** | Average grey-level difference, 0 to 255, after brightness correction | Sensitive to noise and compression |
| **Edge difference** | Share of edges found in only one image | Sensitive to focus and alignment |
| **Brightness shift** | Average brightness change, before correction | Suggests lighting differences |
| **Feature inlier ratio** | Share of matches consistent with one camera transform | Low values mean less reliable alignment |

## Lighting and camera-angle limitations

Differences can come from all of these without any physical change:

- Lighting, shadows and reflections
- Camera angle and position
- Focus and depth of field
- Compression, noise and processing
- Moved objects, dirt or water

The app warns you when alignment fails, overlap falls below 70%, shapes differ without alignment, or brightness shifts by more than 15 grey levels.

## Getting useful results

- Use a tripod or a marked position.
- Keep the lighting the same.
- Use the same camera and settings.
- Include some fixed, textured features in frame.
- Have a person confirm any highlighted change.
