"""Storage abstraction. Callers only ever handle opaque keys, never filesystem paths."""
import re
import shutil
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-.]+)*$")


class StorageError(RuntimeError):
    pass


def _check_key(key: str) -> str:
    if not _KEY_RE.fullmatch(key) or ".." in key:
        raise StorageError("Invalid storage key")
    return key


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    @abstractmethod
    def read(self, key: str) -> bytes: ...
    @abstractmethod
    def exists(self, key: str) -> bool: ...
    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        (self.root / "files").mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        base = (self.root / "files").resolve()
        path = (base / _check_key(key)).resolve()
        if not path.is_relative_to(base):
            raise StorageError("Invalid storage key")
        return path

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("Stored file not found") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)


class S3Storage(Storage):
    """S3-compatible object storage. Objects stay private; all reads go through the authorised API."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("STORAGE_BACKEND=s3 requires: pip install -r requirements-s3.txt") from exc
        s = get_settings()
        if not s.s3_bucket:
            raise StorageError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            region_name=s.s3_region or None,
            endpoint_url=s.s3_endpoint_url or None,
            aws_access_key_id=s.s3_access_key_id or None,
            aws_secret_access_key=s.s3_secret_access_key or None,
        )

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=_check_key(key), Body=data, ContentType=content_type)

    def read(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=_check_key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise StorageError("Stored file not found") from exc

    def exists(self, key: str) -> bool:
        result = self.client.list_objects_v2(Bucket=self.bucket, Prefix=_check_key(key), MaxKeys=1)
        return any(o["Key"] == key for o in result.get("Contents", []))

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=_check_key(prefix)):
            items = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if items:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": items})


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    return S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.storage_root)
