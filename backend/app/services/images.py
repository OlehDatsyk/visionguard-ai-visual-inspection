"""Upload validation and storage. Nothing about a file is trusted until Pillow has decoded it."""
import hashlib
import io
import re
import unicodedata
import uuid
import warnings
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.storage import get_storage
from app.models import ImageMetadata, UploadedImage, Workspace

ALLOWED = {
    "JPEG": {"extensions": {".jpg", ".jpeg"}, "mime": "image/jpeg", "suffix": ".jpg"},
    "PNG": {"extensions": {".png"}, "mime": "image/png", "suffix": ".png"},
    "WEBP": {"extensions": {".webp"}, "mime": "image/webp", "suffix": ".webp"},
}
DISPLAY_MAX_SIDE = 2400
THUMBNAIL_MAX_SIDE = 480
GPS_IFD = 0x8825


class ImageRejected(ValueError):
    pass


def sanitize_filename(name: str | None) -> str:
    """Display-only name. It is never used to build a storage path."""
    raw = (name or "image").replace("\x00", "")
    raw = PureWindowsPath(PurePosixPath(raw).name).name
    raw = unicodedata.normalize("NFKC", raw)
    raw = re.sub(r"[^\w.\- ()]", "_", raw).strip(" .")
    return (raw or "image")[-120:]


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


@dataclass
class ValidatedImage:
    file_format: str
    width: int
    height: int
    had_exif: bool
    had_gps: bool
    checksum: str
    display_jpg: bytes
    thumbnail_jpg: bytes
    display_width: int
    display_height: int


def validate_image(data: bytes, filename: str) -> ValidatedImage:
    settings = get_settings()
    if not data:
        raise ImageRejected("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ImageRejected(f"The file exceeds the {settings.max_upload_size_mb} MB limit.")
    extension = PurePosixPath(filename).suffix.lower()
    if not any(extension in spec["extensions"] for spec in ALLOWED.values()):
        raise ImageRejected("Unsupported file type. Use JPEG, PNG or WebP.")
    sniffed = _sniff(data)
    if sniffed is None:
        raise ImageRejected("The file content is not a JPEG, PNG or WebP image.")
    if extension not in ALLOWED[sniffed]["extensions"]:
        raise ImageRejected("The file extension does not match its actual content.")

    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[sniffed]) as probe:
                width, height = probe.size  # Read from the header, before any pixels are decompressed.
                if width * height > settings.max_image_pixels:
                    raise ImageRejected("The image has too many pixels.")
                if max(width, height) > settings.max_image_dimension:
                    raise ImageRejected(f"The image exceeds {settings.max_image_dimension} pixels on one side.")
                if min(width, height) < settings.min_image_dimension:
                    raise ImageRejected(f"The image must be at least {settings.min_image_dimension} pixels on each side.")
                if getattr(probe, "n_frames", 1) > 1:
                    raise ImageRejected("Animated images are not supported.")
                probe.verify()
            with Image.open(io.BytesIO(data), formats=[sniffed]) as image:
                exif = image.getexif()
                had_exif, had_gps = bool(exif), bool(exif.get_ifd(GPS_IFD))
                image.load()
                upright = ImageOps.exif_transpose(image)
                if upright.mode in ("RGBA", "LA", "PA") or (upright.mode == "P" and "transparency" in upright.info):
                    rgba = upright.convert("RGBA")
                    rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                    rgb.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    rgb = upright.convert("RGB")
    except ImageRejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageRejected("The image has too many pixels.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageRejected("The file is corrupt or is not a valid image.") from exc

    def encode(max_side: int, quality: int) -> tuple[bytes, int, int]:
        copy = rgb.copy()
        copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        # Re-encoding without an exif argument strips GPS and all other metadata from derivatives.
        copy.save(buffer, "JPEG", quality=quality, optimize=True)
        return buffer.getvalue(), copy.width, copy.height

    display, display_w, display_h = encode(DISPLAY_MAX_SIDE, 92)
    thumbnail, _, _ = encode(THUMBNAIL_MAX_SIDE, 82)
    return ValidatedImage(
        sniffed, width, height, had_exif, had_gps, hashlib.sha256(data).hexdigest(),
        display, thumbnail, display_w, display_h,
    )


def store_image(
    db, workspace: Workspace, data: bytes, filename: str, project_id: str | None = None,
    description: str = "", kind: str = "inspection",
) -> UploadedImage:
    clean_name = sanitize_filename(filename)
    valid = validate_image(data, clean_name)
    storage = get_storage()
    image_id = str(uuid.uuid4())
    prefix = f"{workspace.owner_id}/{workspace.id}/images/{image_id}"
    spec = ALLOWED[valid.file_format]
    original_key = f"{prefix}/original{spec['suffix']}"
    display_key = f"{prefix}/display.jpg"
    thumbnail_key = f"{prefix}/thumbnail.jpg"
    storage.save(original_key, data, spec["mime"])
    storage.save(display_key, valid.display_jpg, "image/jpeg")
    storage.save(thumbnail_key, valid.thumbnail_jpg, "image/jpeg")
    image = UploadedImage(
        id=image_id, workspace_id=workspace.id, project_id=project_id, kind=kind, filename=clean_name,
        description=description, storage_prefix=prefix, original_key=original_key, display_key=display_key,
        thumbnail_key=thumbnail_key,
    )
    image.image_metadata = ImageMetadata(
        file_format=valid.file_format, file_size=len(data), width=valid.width, height=valid.height,
        display_width=valid.display_width, display_height=valid.display_height, checksum_sha256=valid.checksum,
        had_exif=valid.had_exif, had_gps=valid.had_gps,
    )
    db.add(image)
    return image
