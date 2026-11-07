"""Pydantic request and response models for the REST API."""
from datetime import UTC, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; every stored timestamp is UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


UTCDatetime = Annotated[datetime, AfterValidator(_as_utc)]
ProjectStatus = Literal["draft", "processing", "completed", "requires_review", "archived"]
ReviewStatus = Literal["unreviewed", "confirmed", "false_positive", "needs_review", "resolved"]
ReviewChoice = Literal["confirmed", "false_positive", "needs_review", "resolved"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str


# Authentication and users -------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: str
    email: str
    full_name: str
    created_at: UTCDatetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class AccountDelete(BaseModel):
    password: str = Field(max_length=128)


# Workspaces and settings --------------------------------------------------------------------------
class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WorkspaceOut(ORM):
    id: str
    name: str
    is_demo: bool
    created_at: UTCDatetime


class SettingsIn(BaseModel):
    default_category: str | None = None
    detector_confidence_threshold: float = Field(default=0.25, ge=0.05, le=0.95)
    overlay_opacity: float = Field(default=0.45, ge=0, le=1)


# Projects -----------------------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    category: str
    notes: str = Field(default="", max_length=8000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = None
    notes: str | None = Field(default=None, max_length=8000)
    archived: bool | None = None


class ProjectOut(ORM):
    id: str
    workspace_id: str
    name: str
    description: str
    category: str
    status: ProjectStatus
    notes: str
    created_at: UTCDatetime
    updated_at: UTCDatetime
    image_count: int = 0
    finding_count: int = 0
    unreviewed_count: int = 0
    object_count: int = 0
    thumbnail_image_id: str | None = None


# Images -------------------------------------------------------------------------------------------
class ImageMetadataOut(ORM):
    file_format: str
    file_size: int
    width: int
    height: int
    display_width: int
    display_height: int
    checksum_sha256: str
    had_exif: bool
    had_gps: bool
    quality: dict


class ImageOut(ORM):
    id: str
    project_id: str | None
    filename: str
    description: str
    status: str
    analysis_notes: list
    unsupported_checks: list
    analysed_at: UTCDatetime | None
    created_at: UTCDatetime
    has_processed: bool = False
    metadata: ImageMetadataOut | None = None


class ImageUpdate(BaseModel):
    description: str = Field(max_length=2000)


class UploadRejection(BaseModel):
    filename: str
    reason: str


class UploadResult(BaseModel):
    accepted: list[ImageOut]
    rejected: list[UploadRejection]


# Results ------------------------------------------------------------------------------------------
class ObjectOut(ORM):
    id: str
    image_id: str
    label: str
    confidence: float
    confidence_band: str
    x: float
    y: float
    width: float
    height: float
    polygon: list | None
    segmentation_method: str | None
    model_name: str


class ReviewOut(ORM):
    id: str
    decision: str
    note: str
    created_at: UTCDatetime


class FindingOut(ORM):
    id: str
    image_id: str
    code: str
    category: str
    finding_type: str
    score: float
    score_type: str
    confidence_band: str
    x: float
    y: float
    width: float
    height: float
    polygon: list | None
    method: str
    explanation: str
    metrics: dict
    review_status: ReviewStatus
    created_at: UTCDatetime
    updated_at: UTCDatetime
    project_id: str | None = None
    project_name: str | None = None
    image_filename: str | None = None


class FindingDetail(FindingOut):
    reviews: list[ReviewOut] = []


class ReviewIn(BaseModel):
    decision: ReviewChoice
    note: str = Field(default="", max_length=2000)


class ImageResults(BaseModel):
    image: ImageOut
    objects: list[ObjectOut]
    findings: list[FindingOut]


class AnalyzeIn(BaseModel):
    reanalyze: bool = False


class JobOut(ORM):
    id: str
    job_type: str
    status: str
    project_id: str | None
    comparison_id: str | None
    items_total: int
    items_done: int
    stage: str
    attempts: int
    max_attempts: int
    error_message: str | None
    queued_at: UTCDatetime
    started_at: UTCDatetime | None
    finished_at: UTCDatetime | None


# Comparison ---------------------------------------------------------------------------------------
class ComparisonOut(ORM):
    id: str
    workspace_id: str
    project_id: str | None
    name: str
    status: str
    metrics: dict
    regions: list
    warnings: list
    width: int
    height: int
    before_filename: str = ""
    after_filename: str = ""
    created_at: UTCDatetime
    metric_explanations: dict = {}
    limitations: list[str] = []
    job: JobOut | None = None


# Reports ------------------------------------------------------------------------------------------
class ReportCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    final_notes: str = Field(default="", max_length=8000)


class ReportOut(ORM):
    id: str
    project_id: str
    project_name: str = ""
    title: str
    final_notes: str
    file_size: int
    page_count: int
    created_at: UTCDatetime


# Assistant ----------------------------------------------------------------------------------------
class ConversationCreate(BaseModel):
    project_id: str | None = None
    comparison_id: str | None = None
    workspace_id: str | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty")
        return value


class MessageOut(ORM):
    id: str
    role: str
    content: str
    source: str
    created_at: UTCDatetime


class ConversationOut(ORM):
    id: str
    project_id: str | None
    comparison_id: str | None
    title: str
    created_at: UTCDatetime
    messages: list[MessageOut] = []


class AssistantStatus(BaseModel):
    provider: str
    external_ai_enabled: bool
    model: str | None
    daily_limit: int
    used_today: int
    message: str
