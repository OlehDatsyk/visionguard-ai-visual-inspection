import io
import struct
import zlib

import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.storage import LocalStorage, StorageError
from app.services.images import sanitize_filename
from tests.conftest import API, make_project, png_bytes, upload


def _rejected(client, auth, name, data):
    project = make_project(client, auth)
    response = upload(client, auth, project["id"], [(name, data)])
    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == []
    return body["rejected"][0]["reason"]


@pytest.mark.parametrize("name,fmt", [("a.png", "PNG"), ("b.jpg", "JPEG"), ("c.jpeg", "JPEG"), ("d.webp", "WEBP")])
def test_supported_formats_accepted(client, auth, name, fmt):
    project = make_project(client, auth)
    body = upload(client, auth, project["id"], [(name, png_bytes(fmt=fmt))]).json()
    assert len(body["accepted"]) == 1
    meta = body["accepted"][0]["metadata"]
    assert meta["file_format"] == fmt and meta["width"] == 320 and len(meta["checksum_sha256"]) == 64


def test_multiple_upload_reports_each_file(client, auth):
    project = make_project(client, auth)
    body = upload(client, auth, project["id"], [("ok.png", png_bytes()), ("bad.png", b"not an image")]).json()
    assert [i["filename"] for i in body["accepted"]] == ["ok.png"]
    assert body["rejected"][0]["filename"] == "bad.png"


def test_unsupported_extension_rejected(client, auth):
    assert "Unsupported" in _rejected(client, auth, "shell.php", b"<?php system($_GET[0]); ?>")


def test_gif_and_svg_rejected(client, auth):
    buffer = io.BytesIO()
    Image.new("P", (40, 40)).save(buffer, "GIF")
    assert "Unsupported" in _rejected(client, auth, "a.gif", buffer.getvalue())
    assert "Unsupported" in _rejected(client, auth, "a.svg", b"<svg onload='alert(1)'/>")


def test_script_disguised_as_image_rejected(client, auth):
    assert "not a JPEG" in _rejected(client, auth, "evil.png", b"<html><script>alert(1)</script></html>")


def test_extension_must_match_content(client, auth):
    assert "does not match" in _rejected(client, auth, "photo.jpg", png_bytes())


def test_truncated_image_rejected(client, auth):
    data = png_bytes(size=(600, 600), colour=(10, 200, 30))
    assert "corrupt" in _rejected(client, auth, "broken.png", data[: len(data) // 2])


def test_empty_file_rejected(client, auth):
    assert "empty" in _rejected(client, auth, "empty.png", b"")


def test_oversized_file_rejected(client, auth):
    settings = get_settings()
    original = settings.max_upload_size_mb
    settings.max_upload_size_mb = 1
    try:
        big = b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10)
        assert "limit" in _rejected(client, auth, "big.png", big)
    finally:
        settings.max_upload_size_mb = original


def _png_header_claiming(width: int, height: int) -> bytes:
    """A tiny PNG whose header claims huge dimensions: the classic decompression-bomb shape."""
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + chunk(b"IEND", b"")


def test_decompression_bomb_rejected(client, auth):
    assert "too many pixels" in _rejected(client, auth, "bomb.png", _png_header_claiming(30000, 30000))


def test_dimension_limits(client, auth):
    assert "at least" in _rejected(client, auth, "tiny.png", png_bytes(size=(10, 10)))
    settings = get_settings()
    original = settings.max_image_dimension
    settings.max_image_dimension = 200
    try:
        assert "exceeds" in _rejected(client, auth, "wide.png", png_bytes(size=(300, 100)))
    finally:
        settings.max_image_dimension = original


def test_animated_image_rejected(client, auth):
    buffer = io.BytesIO()
    frames = [Image.new("RGB", (64, 64), (i * 40, 0, 0)) for i in range(3)]
    frames[0].save(buffer, "WEBP", save_all=True, append_images=frames[1:])
    assert "Animated" in _rejected(client, auth, "anim.webp", buffer.getvalue())


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd.png", "passwd.png"),
    ("..\\..\\windows\\system32\\x.png", "x.png"),
    ("/abs/path/photo.jpg", "photo.jpg"),
    ("na<me>\"x'.png", "na_me__x_.png"),
    ("\x00.png", "png"),
    (None, "image"),
])
def test_filename_sanitised(raw, expected):
    assert sanitize_filename(raw) == expected


def test_path_traversal_filename_stays_contained(client, auth):
    project = make_project(client, auth)
    body = upload(client, auth, project["id"], [("../../../evil.png", png_bytes())]).json()
    assert body["accepted"][0]["filename"] == "evil.png"
    assert "storage" not in str(body) and "original" not in str(body)


def test_storage_rejects_traversal_keys(tmp_path):
    storage = LocalStorage(str(tmp_path))
    for key in ("../outside.txt", "a/../../b", "/abs", "a\\b", "..", "C:/x"):
        with pytest.raises(StorageError):
            storage.save(key, b"x")
    storage.save("user/a.txt", b"hello")
    assert storage.read("user/a.txt") == b"hello" and storage.exists("user/a.txt")
    storage.delete_prefix("user")
    assert not storage.exists("user/a.txt")


def _with_gps_exif() -> bytes:
    image = Image.new("RGB", (200, 200), (120, 120, 120))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 30.0, 0.0)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def test_exif_flagged_stripped_from_derivatives_and_original_kept(client, auth):
    project = make_project(client, auth)
    data = _with_gps_exif()
    assert b"SecretCameraMaker" in data
    response = upload(client, auth, project["id"], [("gps.jpg", data)]).json()["accepted"][0]
    assert response["metadata"]["had_exif"] is True and response["metadata"]["had_gps"] is True
    assert "51" not in str(response["metadata"]["quality"])
    display = client.get(f"{API}/images/{response['id']}/file?variant=display", headers=auth)
    thumbnail = client.get(f"{API}/images/{response['id']}/file?variant=thumbnail", headers=auth)
    assert display.status_code == thumbnail.status_code == 200
    assert b"SecretCameraMaker" not in display.content and b"SecretCameraMaker" not in thumbnail.content
    assert not Image.open(io.BytesIO(display.content)).getexif()
    original = client.get(f"{API}/images/{response['id']}/file?variant=original", headers=auth)
    assert original.content == data  # The upload itself stays unchanged.
    assert "attachment" in original.headers["content-disposition"]


def test_variant_parameter_is_validated(client, auth):
    project = make_project(client, auth)
    image_id = upload(client, auth, project["id"], [("a.png", png_bytes())]).json()["accepted"][0]["id"]
    assert client.get(f"{API}/images/{image_id}/file?variant=../../secret", headers=auth).status_code == 422
    assert client.get(f"{API}/images/{image_id}/file?variant=processed", headers=auth).status_code == 404


def test_too_many_files_rejected(client, auth):
    settings = get_settings()
    original = settings.max_files_per_upload
    settings.max_files_per_upload = 1
    try:
        project = make_project(client, auth)
        response = upload(client, auth, project["id"], [("a.png", png_bytes()), ("b.png", png_bytes())])
        assert response.status_code == 413
    finally:
        settings.max_files_per_upload = original
