"""SQLAlchemy ORM models. All tenant data is reachable only through Workspace.owner_id."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def _id() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=_uuid)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _id()
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    settings: Mapped["AppSetting | None"] = relationship(back_populates="user", cascade="all, delete-orphan")


class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = _updated()
    user: Mapped[User] = relationship(back_populates="settings")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = _id()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    owner: Mapped[User] = relationship(back_populates="workspaces")
    projects: Mapped[list["InspectionProject"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    images: Mapped[list["UploadedImage"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", overlaps="project"
    )
    comparisons: Mapped[list["ComparisonResult"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class InspectionProject(Base):
    __tablename__ = "inspection_projects"
    id: Mapped[str] = _id()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    images: Mapped[list["UploadedImage"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    reports: Mapped[list["InspectionReport"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class UploadedImage(Base):
    __tablename__ = "uploaded_images"
    id: Mapped[str] = _id()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("inspection_projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="inspection")  # inspection | comparison
    filename: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    storage_prefix: Mapped[str] = mapped_column(String(200))
    original_key: Mapped[str] = mapped_column(String(220))
    display_key: Mapped[str] = mapped_column(String(220))
    thumbnail_key: Mapped[str] = mapped_column(String(220))
    processed_key: Mapped[str | None] = mapped_column(String(220))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded | analysed | failed
    analysis_notes: Mapped[list] = mapped_column(JSON, default=list)
    unsupported_checks: Mapped[list] = mapped_column(JSON, default=list)
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    workspace: Mapped[Workspace] = relationship(back_populates="images", overlaps="project")
    project: Mapped[InspectionProject | None] = relationship(back_populates="images", overlaps="workspace")
    image_metadata: Mapped["ImageMetadata"] = relationship(
        back_populates="image", cascade="all, delete-orphan", uselist=False
    )
    objects: Mapped[list["DetectedObject"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    findings: Mapped[list["Finding"]] = relationship(back_populates="image", cascade="all, delete-orphan")


class ImageMetadata(Base):
    """Technical metadata only. GPS and other EXIF values are never stored: just whether they existed."""

    __tablename__ = "image_metadata"
    image_id: Mapped[str] = mapped_column(ForeignKey("uploaded_images.id", ondelete="CASCADE"), primary_key=True)
    file_format: Mapped[str] = mapped_column(String(10))
    file_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    display_width: Mapped[int] = mapped_column(Integer)
    display_height: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    had_exif: Mapped[bool] = mapped_column(Boolean, default=False)
    had_gps: Mapped[bool] = mapped_column(Boolean, default=False)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    image: Mapped[UploadedImage] = relationship(back_populates="image_metadata")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[str] = _id()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("inspection_projects.id", ondelete="CASCADE"), index=True)
    comparison_id: Mapped[str | None] = mapped_column(ForeignKey("comparison_results.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(20))  # analysis | comparison
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    items_total: Mapped[int] = mapped_column(Integer, default=0)
    items_done: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(120), default="Waiting in queue")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    error_message: Mapped[str | None] = mapped_column(String(300))
    queued_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project: Mapped[InspectionProject | None] = relationship(back_populates="jobs")


class DetectedObject(Base):
    __tablename__ = "detected_objects"
    id: Mapped[str] = _id()
    image_id: Mapped[str] = mapped_column(ForeignKey("uploaded_images.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(60), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_band: Mapped[str] = mapped_column(String(20))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    polygon: Mapped[list | None] = mapped_column(JSON)
    segmentation_method: Mapped[str | None] = mapped_column(String(40))
    model_name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = _created()
    image: Mapped[UploadedImage] = relationship(back_populates="objects")


class Finding(Base):
    """A potential defect or manual-inspection area. Never a confirmed defect until a person says so."""

    __tablename__ = "findings"
    id: Mapped[str] = _id()
    image_id: Mapped[str] = mapped_column(ForeignKey("uploaded_images.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(40), index=True)
    finding_type: Mapped[str] = mapped_column(String(30), index=True)  # potential_defect | manual_inspection
    score: Mapped[float] = mapped_column(Float)
    score_type: Mapped[str] = mapped_column(String(30))
    confidence_band: Mapped[str] = mapped_column(String(20), index=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    polygon: Mapped[list | None] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(80))
    explanation: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", index=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    image: Mapped[UploadedImage] = relationship(back_populates="findings")
    reviews: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="ReviewDecision.created_at"
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[str] = _id()
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
    finding: Mapped[Finding] = relationship(back_populates="reviews")


class ComparisonResult(Base):
    __tablename__ = "comparison_results"
    id: Mapped[str] = _id()
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("inspection_projects.id", ondelete="SET NULL"), index=True)
    before_image_id: Mapped[str] = mapped_column(ForeignKey("uploaded_images.id", ondelete="CASCADE"))
    after_image_id: Mapped[str] = mapped_column(ForeignKey("uploaded_images.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    regions: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    storage_prefix: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = _created()
    workspace: Mapped[Workspace] = relationship(back_populates="comparisons")
    before_image: Mapped[UploadedImage] = relationship(foreign_keys=[before_image_id])
    after_image: Mapped[UploadedImage] = relationship(foreign_keys=[after_image_id])
    project: Mapped[InspectionProject | None] = relationship()


class InspectionReport(Base):
    __tablename__ = "inspection_reports"
    id: Mapped[str] = _id()
    project_id: Mapped[str] = mapped_column(ForeignKey("inspection_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    final_notes: Mapped[str] = mapped_column(Text, default="")
    storage_key: Mapped[str] = mapped_column(String(220))
    file_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()
    project: Mapped[InspectionProject] = relationship(back_populates="reports")


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("inspection_projects.id", ondelete="CASCADE"), index=True)
    comparison_id: Mapped[str | None] = mapped_column(ForeignKey("comparison_results.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = _created()
    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at"
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[str] = _id()
    conversation_id: Mapped[str] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="user")  # user | records | anthropic
    created_at: Mapped[datetime] = _created()
    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


Index("ix_findings_image_review", Finding.image_id, Finding.review_status)
