"""Test fixtures: an isolated SQLite database and storage folder, with a fake detector by default."""
import io
import os
import shutil
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="vg-tests-")
os.environ.update(
    ENVIRONMENT="test",
    # Set TEST_DATABASE_URL to run the suite against PostgreSQL. Its tables are dropped and recreated.
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP).as_posix()}/test.db",
    STORAGE_BACKEND="local",
    STORAGE_ROOT=str(Path(_TMP) / "storage"),
    SECRET_KEY="test-secret-key-that-is-long-enough-0123456789",
    AI_PROVIDER="none",
    AI_API_KEY="",
    AUTH_RATE_LIMIT_PER_MINUTE="1000",
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core.security import rate_limiter  # noqa: E402
from app.database.session import Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.vision.detectors.base import ModelInfo, ObjectDetector  # noqa: E402
from app.vision.detectors.registry import get_detector, set_detector  # noqa: E402
from app.vision.types import Box, ObjectDetection  # noqa: E402

API = "/api/v1"


class FakeDetector(ObjectDetector):
    """Deterministic stand-in, so API tests do not depend on model weights."""

    info = ModelInfo(
        key="fake", name="Fake detector", model_type="test", version="0", licence="n/a", source="n/a",
        weights_file="none", input_requirements="any", processing="none", supported_categories=["widget"],
    )
    available = True

    def is_available(self):
        return self.available

    def unavailable_reason(self):
        return None if self.available else "Not installed in this test."

    def detect(self, bgr, confidence_threshold):
        return [ObjectDetection("widget", 0.82, Box(10, 10, 60, 40))]


@pytest.fixture(autouse=True)
def clean_state():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(Path(_TMP) / "storage" / "files", ignore_errors=True)
    rate_limiter.reset()
    original = get_detector()
    set_detector(FakeDetector())
    yield
    set_detector(original)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client, email="alice@example.com", password="correct-horse-battery") -> dict:
    response = client.post(f"{API}/auth/register", json={"email": email, "full_name": "Test User", "password": password})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def other_auth(client):
    return register(client, "mallory@example.com")


def workspace_id(client, headers) -> str:
    return client.get(f"{API}/workspaces", headers=headers).json()[0]["id"]


def make_project(client, headers, category="surface_material", name="Test project") -> dict:
    response = client.post(
        f"{API}/projects", headers=headers,
        json={"workspace_id": workspace_id(client, headers), "name": name, "category": category},
    )
    assert response.status_code == 201, response.text
    return response.json()


def png_bytes(size=(320, 240), colour=(150, 150, 150), fmt="PNG", **save) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, fmt, **save)
    return buffer.getvalue()


def surface_with_crack() -> bytes:
    """A uniform grey surface with one dark, irregular line: a controlled crack-like input."""
    import cv2

    rng = np.random.default_rng(1)
    image = np.full((400, 600, 3), 160, np.uint8)
    image = np.clip(image + rng.normal(0, 1.5, image.shape), 0, 255).astype(np.uint8)
    points = np.array([[60, 80], [150, 130], [210, 110], [300, 190], [380, 170], [470, 260], [540, 240]], np.int32)
    cv2.polylines(image, [points], False, (35, 35, 35), 3, cv2.LINE_AA)
    return cv2.imencode(".png", image)[1].tobytes()


def upload(client, headers, project_id, files: list[tuple[str, bytes]]):
    return client.post(
        f"{API}/projects/{project_id}/images", headers=headers,
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def run_jobs():
    from app.services.jobs import process_next_job

    while process_next_job():
        pass
