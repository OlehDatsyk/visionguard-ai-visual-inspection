"""Database-backed job queue and worker.

Jobs live in PostgreSQL or SQLite, so no extra queue service is needed. A job is claimed with an
atomic UPDATE, so more than one worker can run safely. Progress is the real count of finished images.
"""
import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.core.storage import get_storage
from app.database.session import new_session
from app.models import (
    AnalysisJob,
    AppSetting,
    ComparisonResult,
    DetectedObject,
    Finding,
    InspectionProject,
    UploadedImage,
    Workspace,
)
from app.models.entities import utcnow
from app.vision.comparison import compare_images
from app.vision.detectors.registry import get_detector
from app.vision.pipeline import decode_image, render_annotated, run_pipeline
from app.vision.types import SCORE_MODEL, confidence_band

log = logging.getLogger("visionguard.worker")
ACTIVE = ("queued", "running")


def refresh_project_status(db, project: InspectionProject) -> None:
    if project.status == "archived":
        return
    active = db.scalar(
        select(func.count()).select_from(AnalysisJob).where(
            AnalysisJob.project_id == project.id, AnalysisJob.job_type == "analysis", AnalysisJob.status.in_(ACTIVE)
        )
    )
    if active:
        project.status = "processing"
        return
    analysed = db.scalar(
        select(func.count()).select_from(UploadedImage).where(
            UploadedImage.project_id == project.id, UploadedImage.status == "analysed"
        )
    )
    if not analysed:
        project.status = "draft"
        return
    open_findings = db.scalar(
        select(func.count()).select_from(Finding).join(UploadedImage).where(
            UploadedImage.project_id == project.id, Finding.review_status.in_(("unreviewed", "needs_review"))
        )
    )
    project.status = "requires_review" if open_findings else "completed"


def enqueue_analysis(db, project: InspectionProject, reanalyze: bool = False) -> AnalysisJob:
    query = select(func.count()).select_from(UploadedImage).where(UploadedImage.project_id == project.id)
    if not reanalyze:
        query = query.where(UploadedImage.status != "analysed")
    total = db.scalar(query) or 0
    job = AnalysisJob(
        workspace_id=project.workspace_id, project_id=project.id, job_type="analysis", items_total=total,
        options={"reanalyze": reanalyze}, max_attempts=get_settings().job_max_attempts,
    )
    db.add(job)
    project.status = "processing"
    return job


def enqueue_comparison(db, comparison: ComparisonResult) -> AnalysisJob:
    job = AnalysisJob(
        workspace_id=comparison.workspace_id, comparison_id=comparison.id, job_type="comparison", items_total=1,
        max_attempts=get_settings().job_max_attempts,
    )
    db.add(job)
    return job


def _claim_next(db) -> str | None:
    candidate = db.scalar(
        select(AnalysisJob.id).where(AnalysisJob.status == "queued").order_by(AnalysisJob.queued_at).limit(1)
    )
    if not candidate:
        return None
    now = utcnow()
    claimed = db.execute(
        update(AnalysisJob)
        .where(AnalysisJob.id == candidate, AnalysisJob.status == "queued")
        .values(status="running", started_at=now, heartbeat_at=now, attempts=AnalysisJob.attempts + 1,
                stage="Starting", error_message=None)
    )
    db.commit()
    return candidate if claimed.rowcount == 1 else None


def _detector_threshold(db, workspace_id: str) -> float | None:
    owner = db.scalar(select(Workspace.owner_id).where(Workspace.id == workspace_id))
    setting = db.scalar(select(AppSetting).where(AppSetting.user_id == owner))
    return (setting.preferences or {}).get("detector_confidence_threshold") if setting else None


def analyse_image(db, image: UploadedImage, category: str, threshold: float | None) -> None:
    """Run the pipeline on one image and persist its results, replacing any previous ones."""
    storage = get_storage()
    bgr = decode_image(storage.read(image.display_key))
    result = run_pipeline(bgr, category, threshold)
    db.execute(delete(DetectedObject).where(DetectedObject.image_id == image.id))
    db.execute(delete(Finding).where(Finding.image_id == image.id))
    model_name = get_detector().info.name
    for obj in result.objects:
        db.add(
            DetectedObject(
                image_id=image.id, label=obj.label, confidence=round(obj.confidence, 4),
                confidence_band=confidence_band(obj.confidence, SCORE_MODEL), x=obj.box.x, y=obj.box.y,
                width=obj.box.width, height=obj.box.height, polygon=obj.polygon,
                segmentation_method=obj.segmentation_method, model_name=model_name,
            )
        )
    for index, finding in enumerate(result.findings, start=1):
        db.add(
            Finding(
                image_id=image.id, code=f"F-{image.id[:4].upper()}-{index:02d}", category=finding.category,
                finding_type=finding.finding_type, score=finding.score, score_type=finding.score_type,
                confidence_band=confidence_band(finding.score, finding.score_type), x=finding.box.x,
                y=finding.box.y, width=finding.box.width, height=finding.box.height, polygon=finding.polygon,
                method=finding.method, explanation=finding.explanation, metrics=finding.metrics,
            )
        )
    processed_key = f"{image.storage_prefix}/processed.jpg"
    storage.save(processed_key, render_annotated(bgr, result), "image/jpeg")
    image.processed_key = processed_key
    image.status = "analysed"
    image.analysis_notes = result.notes
    image.unsupported_checks = result.unsupported
    image.analysed_at = utcnow()
    image.image_metadata.quality = {**result.quality, "processing_ms": result.processing_ms}


def _run_analysis(db, job: AnalysisJob) -> None:
    project = db.get(InspectionProject, job.project_id)
    query = select(UploadedImage).where(UploadedImage.project_id == project.id).order_by(UploadedImage.created_at)
    if not job.options.get("reanalyze"):
        query = query.where(UploadedImage.status != "analysed")
    images = list(db.scalars(query))
    job.items_total, job.items_done = len(images), 0
    threshold = _detector_threshold(db, project.workspace_id)
    db.commit()
    for image in images:
        job.stage = f"Analysing {image.filename}"
        job.heartbeat_at = utcnow()
        db.commit()
        analyse_image(db, image, project.category, threshold)
        job.items_done += 1
        job.heartbeat_at = utcnow()
        db.commit()


def run_comparison(db, comparison: ComparisonResult) -> None:
    storage = get_storage()
    before = decode_image(storage.read(comparison.before_image.display_key))
    after = decode_image(storage.read(comparison.after_image.display_key))
    output = compare_images(before, after)
    prefix = f"{comparison.workspace.owner_id}/{comparison.workspace_id}/comparisons/{comparison.id}"
    storage.save(f"{prefix}/before.jpg", output.before_jpg, "image/jpeg")
    storage.save(f"{prefix}/aligned.jpg", output.aligned_jpg, "image/jpeg")
    storage.save(f"{prefix}/heatmap.jpg", output.heatmap_jpg, "image/jpeg")
    storage.save(f"{prefix}/mask.png", output.mask_png, "image/png")
    comparison.storage_prefix = prefix
    comparison.metrics, comparison.regions, comparison.warnings = output.metrics, output.regions, output.warnings
    comparison.width, comparison.height = output.width, output.height
    comparison.status = "completed"


def _execute(job_id: str) -> None:
    with new_session() as db:
        job = db.get(AnalysisJob, job_id)
        try:
            if job.job_type == "analysis":
                _run_analysis(db, job)
                job.status, job.stage, job.finished_at = "completed", "Finished", utcnow()
                refresh_project_status(db, db.get(InspectionProject, job.project_id))
            else:
                comparison = db.get(ComparisonResult, job.comparison_id)
                comparison.status = "processing"
                job.stage = "Comparing images"
                db.commit()
                run_comparison(db, comparison)
                job.items_done = 1
                job.status, job.stage, job.finished_at = "completed", "Finished", utcnow()
            db.commit()
        except Exception:  # noqa: BLE001 - any failure must be recorded on the job, not lost in the thread
            log.exception("Job %s failed on attempt %s", job_id, job.attempts)
            db.rollback()
            job = db.get(AnalysisJob, job_id)
            if job.attempts < job.max_attempts:
                job.status, job.stage = "queued", "Retrying after an error"
            else:
                job.status, job.stage, job.finished_at = "failed", "Failed", utcnow()
                job.error_message = "Processing failed. Check that the images are readable, then retry."
                if job.comparison_id:
                    comparison = db.get(ComparisonResult, job.comparison_id)
                    if comparison:
                        comparison.status = "failed"
                if job.project_id:
                    project = db.get(InspectionProject, job.project_id)
                    db.flush()
                    refresh_project_status(db, project)
            db.commit()


def process_next_job() -> bool:
    with new_session() as db:
        job_id = _claim_next(db)
    if job_id is None:
        return False
    _execute(job_id)
    return True


def requeue_stale_jobs() -> int:
    """Recover jobs left 'running' by a process that crashed or was restarted."""
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().job_stale_after_seconds)
    with new_session() as db:
        stale = list(db.scalars(
            select(AnalysisJob).where(AnalysisJob.status == "running", AnalysisJob.heartbeat_at < cutoff)
        ))
        for job in stale:
            if job.attempts < job.max_attempts:
                job.status, job.stage = "queued", "Re-queued after a worker restart"
            else:
                job.status, job.stage, job.finished_at = "failed", "Failed", utcnow()
                job.error_message = "The worker stopped while processing this job. Retry it."
        db.commit()
        return len(stale)


class Worker(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="visionguard-worker", daemon=True)
        self._stop_event = threading.Event()

    def run(self) -> None:
        interval = get_settings().worker_poll_seconds
        log.info("Worker started")
        while not self._stop_event.is_set():
            try:
                requeue_stale_jobs()
                if process_next_job():
                    continue
            except Exception:  # noqa: BLE001 - e.g. the database is briefly unavailable; keep polling
                log.exception("Worker loop error")
            self._stop_event.wait(interval)

    def stop(self) -> None:
        self._stop_event.set()
