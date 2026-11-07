"""Single-service mode: the API serves the built web app from the same origin."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import FRONTEND_CSP, mount_frontend


def make_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>VisionGuard</title>", encoding="utf-8")
    (dist / "assets" / "app-123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    assert mount_frontend(app, str(dist))
    return TestClient(app)


def test_index_and_client_routes_get_the_app(tmp_path):
    client = make_client(tmp_path)
    for path in ("/", "/login", "/analytics", "/inspections/abc"):
        response = client.get(path)
        assert response.status_code == 200
        assert "VisionGuard" in response.text
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["content-security-policy"] == FRONTEND_CSP
        assert response.headers["cache-control"] == "no-cache"


def test_assets_are_served_with_correct_types_and_caching(tmp_path):
    client = make_client(tmp_path)
    script = client.get("/assets/app-123.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert "immutable" in script.headers["cache-control"]
    assert client.get("/favicon.svg").headers["content-type"] == "image/svg+xml"


def test_api_routes_are_not_shadowed_and_unknown_api_paths_stay_json_404(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/v1/ping").json() == {"ok": True}
    missing = client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}


def test_files_outside_the_build_are_never_served(tmp_path):
    client = make_client(tmp_path)
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = client.get(path)
        assert "outside" not in response.text


def test_missing_build_serves_api_only(tmp_path):
    app = FastAPI()
    assert mount_frontend(app, str(tmp_path / "nowhere")) is False
    assert TestClient(app).get("/").status_code == 404
