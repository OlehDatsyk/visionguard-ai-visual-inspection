import jwt
import pytest
from pydantic import ValidationError

from app.core.config import DEV_SECRET, Settings
from app.core.security import hash_password, rate_limiter, verify_password
from tests.conftest import API, make_project, png_bytes, register, upload, workspace_id


def test_register_login_and_me(client):
    headers = register(client)
    assert client.get(f"{API}/users/me", headers=headers).json()["email"] == "alice@example.com"
    response = client.post(f"{API}/auth/login", json={"email": "ALICE@example.com", "password": "correct-horse-battery"})
    assert response.status_code == 200
    assert "password" not in str(response.json())


def test_passwords_are_hashed(client):
    from sqlalchemy import select
    from app.database.session import new_session
    from app.models import User

    register(client)
    with new_session() as db:
        stored = db.scalar(select(User)).password_hash
    assert stored.startswith("$argon2") and "correct-horse" not in stored
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("wrong", hash_password("right"))
    assert not verify_password("anything", None)


def test_duplicate_email_rejected(client):
    register(client)
    response = client.post(f"{API}/auth/register", json={"email": "alice@example.com", "full_name": "B", "password": "another-long-password"})
    assert response.status_code == 409


def test_short_password_rejected_without_echo(client):
    response = client.post(f"{API}/auth/register", json={"email": "a@example.com", "full_name": "A", "password": "short-pw"})
    assert response.status_code == 422
    assert "short-pw" not in response.text


def test_wrong_password_and_unknown_user_look_identical(client):
    register(client)
    wrong = client.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": "nope"})
    unknown = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.parametrize("path", ["/users/me", "/workspaces", "/settings", "/models", "/assistant/status"])
def test_protected_routes_need_a_token(client, path):
    assert client.get(f"{API}{path}").status_code == 401


def test_invalid_and_forged_tokens_rejected(client):
    headers = register(client)
    assert client.get(f"{API}/users/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    user_id = client.get(f"{API}/users/me", headers=headers).json()["id"]
    forged = jwt.encode({"sub": user_id, "ver": 0, "exp": 9999999999}, "attacker-key-" * 4, algorithm="HS256")
    assert client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_logout_revokes_token(client):
    headers = register(client)
    assert client.post(f"{API}/auth/logout", headers=headers).status_code == 200
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401


def test_password_change_revokes_old_token(client):
    headers = register(client)
    bad = client.post(f"{API}/users/me/password", headers=headers, json={"current_password": "wrong", "new_password": "brand-new-password"})
    assert bad.status_code == 400
    good = client.post(f"{API}/users/me/password", headers=headers, json={"current_password": "correct-horse-battery", "new_password": "brand-new-password"})
    assert good.status_code == 200
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401


def test_rate_limit_returns_429(client):
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.auth_rate_limit_per_minute
    settings.auth_rate_limit_per_minute = 3
    try:
        codes = [client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "p"}).status_code for _ in range(5)]
    finally:
        settings.auth_rate_limit_per_minute = original
        rate_limiter.reset()
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_users_cannot_reach_each_others_records(client, auth, other_auth):
    project = make_project(client, auth)
    image_id = upload(client, auth, project["id"], [("a.png", png_bytes())]).json()["accepted"][0]["id"]
    pid = project["id"]
    attempts = [
        ("get", f"/projects/{pid}"), ("delete", f"/projects/{pid}"), ("get", f"/projects/{pid}/images"),
        ("post", f"/projects/{pid}/analyze"), ("get", f"/images/{image_id}/file"), ("get", f"/images/{image_id}/results"),
        ("get", f"/images/{image_id}/file?variant=original"), ("delete", f"/images/{image_id}"),
        ("get", f"/projects?workspace_id={project['workspace_id']}"), ("get", f"/findings?workspace_id={project['workspace_id']}"),
        ("get", f"/analytics/overview?workspace_id={project['workspace_id']}"),
    ]
    for method, path in attempts:
        response = getattr(client, method)(f"{API}{path}", headers=other_auth)
        assert response.status_code == 404, f"{method} {path} returned {response.status_code}"
    assert client.get(f"{API}/projects/{pid}", headers=auth).status_code == 200
    denied = client.post(f"{API}/projects", headers=other_auth, json={"workspace_id": project["workspace_id"], "name": "x", "category": "surface_material"})
    assert denied.status_code == 404


def test_account_deletion_removes_data(client):
    headers = register(client)
    make_project(client, headers)
    assert client.post(f"{API}/users/me/delete", headers=headers, json={"password": "bad"}).status_code == 400
    assert client.post(f"{API}/users/me/delete", headers=headers, json={"password": "correct-horse-battery"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": "correct-horse-battery"}).status_code == 401


def test_workspace_rules(client, auth):
    only = workspace_id(client, auth)
    assert client.delete(f"{API}/workspaces/{only}", headers=auth).status_code == 409
    created = client.post(f"{API}/workspaces", headers=auth, json={"name": "Second"}).json()
    assert client.patch(f"{API}/workspaces/{created['id']}", headers=auth, json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.delete(f"{API}/workspaces/{created['id']}", headers=auth).status_code == 204


def test_production_refuses_insecure_configuration():
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key=DEV_SECRET, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="x" * 40, cors_origins="*", _env_file=None)
    settings = Settings(environment="production", secret_key="x" * 40, cors_origins="https://a.example", _env_file=None)
    assert settings.docs_enabled is False


def test_database_url_normalised_and_ai_key_optional():
    settings = Settings(database_url="postgres://u:p@h/db", ai_provider="anthropic", ai_api_key="", _env_file=None)
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.ai_provider == "none"


def test_health_endpoints_and_headers(client):
    health = client.get("/health")
    assert health.json() == {"status": "ok"} and health.headers["x-content-type-options"] == "nosniff"
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["database"] == "ok"
    assert "sqlite" not in ready.text


def test_cors_allows_only_configured_origin(client):
    allowed = client.options(f"{API}/users/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.options(f"{API}/users/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers


def test_openapi_docs_available_in_development(client):
    assert client.get("/docs").status_code == 200
    assert "/api/v1/projects" in client.get("/openapi.json").json()["paths"]


def test_system_status_reports_storage_state(client, auth):
    from app.core.config import get_settings

    assert client.get(f"{API}/system/status").status_code == 401
    assert client.get(f"{API}/system/status", headers=auth).json()["storage_persistent"] is True
    settings = get_settings()
    settings.storage_persistent = False
    try:
        assert client.get(f"{API}/system/status", headers=auth).json()["storage_persistent"] is False
    finally:
        settings.storage_persistent = True


def test_s3_storage_uses_private_objects_and_checks_keys(monkeypatch):
    """Exercises our adapter against a stubbed client. It does not contact real object storage."""
    import sys
    from unittest import mock

    from app.core.config import get_settings
    from app.core.storage import S3Storage, StorageError

    settings = get_settings()
    monkeypatch.setattr(settings, "s3_bucket", "bucket")
    fake = mock.Mock()
    fake.exceptions.NoSuchKey = KeyError
    monkeypatch.setitem(sys.modules, "boto3", mock.Mock(client=mock.Mock(return_value=fake)))
    storage = S3Storage()
    storage.save("user/a.png", b"x", "image/png")
    fake.put_object.assert_called_once_with(Bucket="bucket", Key="user/a.png", Body=b"x", ContentType="image/png")
    assert "ACL" not in fake.put_object.call_args.kwargs  # Objects stay private.
    with pytest.raises(StorageError):
        storage.save("../escape", b"x")
    fake.get_object.side_effect = KeyError
    with pytest.raises(StorageError):
        storage.read("user/missing.png")
