"""Application configuration, read from environment variables and an optional .env file."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    enable_docs: bool | None = None  # None: enabled except in production

    secret_key: str = DEV_SECRET
    access_token_ttl_minutes: int = Field(default=720, ge=5, le=43200)

    database_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    storage_backend: Literal["local", "s3"] = "local"
    storage_root: str = ""
    # Set to false where local files do not survive a restart, such as a free Render web service.
    # The interface then warns users that uploads and reports can disappear.
    storage_persistent: bool = True
    s3_bucket: str = ""
    s3_region: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    max_upload_size_mb: int = Field(default=20, ge=1, le=200)
    max_files_per_upload: int = Field(default=20, ge=1, le=100)
    max_image_pixels: int = Field(default=40_000_000, ge=10_000)
    max_image_dimension: int = Field(default=12_000, ge=64)
    min_image_dimension: int = Field(default=32, ge=1)

    model_dir: str = ""
    detector_input_size: int = 416
    detector_confidence_threshold: float = Field(default=0.25, ge=0.01, le=0.99)
    onnx_threads: int = Field(default=2, ge=1, le=32)

    run_worker_in_api: bool = True
    worker_poll_seconds: float = Field(default=1.0, gt=0)
    job_max_attempts: int = Field(default=2, ge=1, le=5)
    job_stale_after_seconds: int = Field(default=600, ge=30)

    ai_provider: Literal["none", "anthropic"] = "none"
    ai_api_key: str = ""
    ai_model: str = "claude-opus-5-5"
    ai_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    ai_daily_message_limit: int = Field(default=50, ge=0)

    auth_rate_limit_per_minute: int = Field(default=10, ge=1)
    upload_rate_limit_per_minute: int = Field(default=30, ge=1)
    assistant_rate_limit_per_minute: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def _finalise(self) -> "Settings":
        if not self.storage_root:
            self.storage_root = str(REPO_DIR / "storage")
        if not self.model_dir:
            self.model_dir = str(BACKEND_DIR / "model_weights")
        if not self.database_url:
            db_path = (Path(self.storage_root) / "visionguard.db").as_posix()
            self.database_url = f"sqlite:///{db_path}"
        # Hosting providers hand out postgres:// or postgresql:// URLs; select the psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix):]
                break
        if self.environment == "production":
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be a unique value of at least 32 characters in production")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must list explicit origins in production")
        if self.ai_provider != "none" and not self.ai_api_key:
            # Missing AI credentials must never stop core inspection features.
            self.ai_provider = "none"
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production" if self.enable_docs is None else self.enable_docs

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
