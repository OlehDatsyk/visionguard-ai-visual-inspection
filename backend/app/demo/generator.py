"""Procedurally generated sample surfaces. These are artificial images, not real inspections."""
import cv2
import numpy as np


def _encode(image: np.ndarray) -> bytes:
    return cv2.imencode(".png", image)[1].tobytes()


def _noise(rng, shape, scale, blur) -> np.ndarray:
    field = rng.normal(0, scale, shape).astype(np.float32)
    return cv2.GaussianBlur(field, (0, 0), blur) * (blur * 2.5)


def concrete(rng, size=(760, 1100)) -> np.ndarray:
    h, w = size
    base = 158 + _noise(rng, size, 5, 18) + _noise(rng, size, 3, 1.2)
    return np.clip(np.dstack((base - 3, base, base + 2)), 0, 255).astype(np.uint8)


def steel(rng, size=(760, 1100)) -> np.ndarray:
    h, w = size
    streaks = cv2.blur(rng.normal(0, 5, size).astype(np.float32), (61, 1))
    gradient = np.tile(np.linspace(-6, 6, w, dtype=np.float32), (h, 1))
    base = 176 + streaks * 2 + gradient
    return np.clip(np.dstack((base + 3, base + 1, base)), 0, 255).astype(np.uint8)


def painted(rng, size=(760, 1100), colour=(148, 92, 42)) -> np.ndarray:
    noise = _noise(rng, size, 1.4, 1.0)
    layers = [np.clip(c + noise, 0, 255) for c in colour]
    return np.dstack(layers).astype(np.uint8)


def draw_crack(image, rng, start, steps=46, step_len=16, heading=0.35) -> None:
    x, y = start
    angle = heading
    points = [(x, y)]
    for _ in range(steps):
        angle += rng.normal(0, 0.42)
        angle = 0.75 * angle + 0.25 * heading
        x += step_len * np.cos(angle)
        y += step_len * np.sin(angle)
        points.append((x, y))
    cv2.polylines(image, [np.array(points, np.int32)], False, (42, 42, 44), 3, cv2.LINE_AA)


def draw_scratch(image, p1, p2, colour=(225, 228, 230)) -> None:
    cv2.line(image, p1, p2, colour, 2, cv2.LINE_AA)


def draw_rust(image, rng, centre, radius) -> None:
    h, w = image.shape[:2]
    field = _noise(rng, (h, w), 22, 9)
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(xx - centre[0], yy - centre[1]) / radius
    mask = np.clip((1.05 - dist) * 2.5 + field / 25, 0, 1)[..., None]
    grain = _noise(rng, (h, w), 16, 1.0)
    rust = np.dstack((30 + grain * 0.4, 72 + grain * 0.8, 150 + grain))
    blended = image.astype(np.float32) * (1 - mask) + rust.astype(np.float32) * mask
    image[:] = np.clip(blended, 0, 255).astype(np.uint8)


def draw_stain(image, rng, centre, axes, tint=(-26, -8, 26)) -> None:
    h, w = image.shape[:2]
    mask = np.zeros((h, w), np.float32)
    cv2.ellipse(mask, centre, axes, 18, 0, 360, 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), 12)[..., None]
    blended = image.astype(np.float32) + mask * np.array(tint, np.float32)
    image[:] = np.clip(blended, 0, 255).astype(np.uint8)


def _add_fixtures(image: np.ndarray) -> None:
    """Formwork ties and stencilled marks give feature matching something to lock on to."""
    height, width = image.shape[:2]
    for row, y in enumerate(range(70, height, 155)):
        for column, x in enumerate(range(70, width, 160)):
            jitter = (row * 7 + column * 13) % 19
            cv2.circle(image, (x + jitter, y - jitter), 9 + jitter % 4, (88, 90, 92), -1, cv2.LINE_AA)
            cv2.circle(image, (x + jitter, y - jitter), 3 + jitter % 3, (205, 205, 200), -1, cv2.LINE_AA)
            cv2.putText(image, f"{row}{chr(65 + column)}", (x + 22, y + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (70, 72, 74), 1, cv2.LINE_AA)


def build_samples(seed: int = 7) -> dict[str, bytes]:
    rng = np.random.default_rng(seed)
    wall = concrete(rng)
    draw_crack(wall, rng, (130, 170), heading=0.42)
    draw_stain(wall, rng, (820, 580), (150, 85))

    plate = steel(rng)
    draw_scratch(plate, (170, 150), (820, 310))
    draw_scratch(plate, (320, 610), (760, 560))
    draw_rust(plate, rng, (860, 560), 120)

    panel = painted(rng)
    draw_scratch(panel, (210, 240), (880, 420), (205, 190, 175))

    before = concrete(np.random.default_rng(21))
    _add_fixtures(before)
    after = before.copy()
    draw_crack(after, np.random.default_rng(22), (520, 180), steps=24, heading=1.1)
    draw_stain(after, np.random.default_rng(23), (240, 560), (120, 70), tint=(-30, -12, 22))
    matrix = cv2.getRotationMatrix2D((550, 380), 1.2, 1.0)
    matrix[:, 2] += (9, -6)  # The second photo was "taken" from a slightly different position.
    after = cv2.warpAffine(after, matrix, (1100, 760), borderMode=cv2.BORDER_REFLECT)

    return {
        "demo_concrete_wall.png": _encode(wall),
        "demo_steel_plate.png": _encode(plate),
        "demo_painted_panel.png": _encode(panel),
        "demo_before.png": _encode(before),
        "demo_after.png": _encode(after),
    }
