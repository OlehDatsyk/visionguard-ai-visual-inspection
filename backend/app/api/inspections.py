"""Inspection projects, images, analysis jobs, findings and reports."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import (
    get_current_user,
    owned_finding,
    owned_image,
    owned_job,
    owned_project,
    owned_report,
    owned_workspace,
    rate_limit_upload,
)
from app.core.config import get_settings
from app.core.storage import StorageError, get_storage
from app.database.session import get_db
from app.models import (
    AnalysisJob,
    DetectedObject,
    Finding,
    InspectionProject,
    InspectionReport,
    ReviewDecision,
    UploadedImage,
    User,
)
from app.schemas.common import (
    AnalyzeIn,
    FindingDetail,
    FindingOut,
    ImageMetadataOut,
    ImageOut,
    ImageResults,
    ImageUpdate,
    JobOut,
    ObjectOut,
    Page,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    ReportCreate,
    ReportOut,
    ReviewIn,
    UploadRejection,
    UploadResult,
)
from app.services import jobs as job_service
from app.services.images import ImageRejected, sanitize_filename, store_image
from app.services.reports import create_report
from app.vision.profiles import CATEGORIES

router = APIRouter()
MEDIA_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf"}


def file_response(key: str, filename: str | None = None) -> Response:
    try:
        data = get_storage().read(key)
    except StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from exc
    headers = {"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"}
    if filename:
        safe = sanitize_filename(filename).encode("ascii", "replace").decode()
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'
    return Response(data, media_type=MEDIA_TYPES.get(key.rsplit(".", 1)[-1], "application/octet-stream"), headers=headers)


def image_out(image: UploadedImage) -> ImageOut:
    return ImageOut(
        id=image.id, project_id=image.project_id, filename=image.filename, description=image.description,
        status=image.status, analysis_notes=image.analysis_notes or [], unsupported_checks=image.unsupported_checks or [],
        analysed_at=image.analysed_at, created_at=image.created_at, has_processed=bool(image.processed_key),
        metadata=ImageMetadataOut.model_validate(image.image_metadata),
    )


def project_out(db: Session, project: InspectionProject) -> ProjectOut:
    image_ids = select(UploadedImage.id).where(UploadedImage.project_id == project.id)
    out = ProjectOut.model_validate(project)
    out.image_count = db.scalar(select(func.count()).select_from(image_ids.subquery())) or 0
    out.finding_count = db.scalar(select(func.count()).select_from(Finding).where(Finding.image_id.in_(image_ids))) or 0
    out.unreviewed_count = db.scalar(
        select(func.count()).select_from(Finding).where(Finding.image_id.in_(image_ids), Finding.review_status == "unreviewed")
    ) or 0
    out.object_count = db.scalar(select(func.count()).select_from(DetectedObject).where(DetectedObject.image_id.in_(image_ids))) or 0
    out.thumbnail_image_id = db.scalar(
        select(UploadedImage.id).where(UploadedImage.project_id == project.id).order_by(UploadedImage.created_at).limit(1)
    )
    return out


def _check_category(category: str) -> None:
    if category not in CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown inspection category.")


@router.get("/categories", tags=["Inspection projects"])
def categories(user: User = Depends(get_current_user)):
    from app.vision.profiles import MODULE_INFO, unsupported_for

    return [
        {
            "key": key, "label": value["label"],
            "checks": [MODULE_INFO[m]["name"] for m in value["modules"]],
            "not_assessed": unsupported_for(key),
        }
        for key, value in CATEGORIES.items()
    ]


@router.get("/projects", response_model=Page[ProjectOut], tags=["Inspection projects"])
def list_projects(
    workspace_id: str, q: str | None = Query(default=None, max_length=120), project_status: str | None = Query(default=None, alias="status"),
    category: str | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    owned_workspace(db, user, workspace_id)
    query = select(InspectionProject).where(InspectionProject.workspace_id == workspace_id)
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(InspectionProject.name.ilike(pattern, escape="\\"), InspectionProject.description.ilike(pattern, escape="\\")))
    if project_status:
        query = query.where(InspectionProject.status == project_status)
    if category:
        query = query.where(InspectionProject.category == category)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(InspectionProject.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[project_out(db, p) for p in rows], total=total, page=page, page_size=page_size)


@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["Inspection projects"])
def create_project(body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_workspace(db, user, body.workspace_id)
    _check_category(body.category)
    project = InspectionProject(**body.model_dump())
    db.add(project)
    db.commit()
    return project_out(db, project)


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["Inspection projects"])
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return project_out(db, owned_project(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["Inspection projects"])
def update_project(project_id: str, body: ProjectUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    values = body.model_dump(exclude_unset=True)
    archived = values.pop("archived", None)
    if values.get("category"):
        _check_category(values["category"])
    for key, value in values.items():
        if value is not None:
            setattr(project, key, value)
    if archived is True:
        project.status = "archived"
    elif archived is False and project.status == "archived":
        project.status = "draft"
        job_service.refresh_project_status(db, project)
    db.commit()
    return project_out(db, project)


@router.delete("/projects/{project_id}", status_code=204, tags=["Inspection projects"])
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    if project.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for processing to finish before deleting this project.")
    storage = get_storage()
    prefixes = [i.storage_prefix for i in project.images]
    reports = [r.storage_key for r in project.reports]
    db.delete(project)
    db.commit()
    for key in prefixes + reports:
        storage.delete_prefix(key)


# Images -------------------------------------------------------------------------------------------
@router.post("/projects/{project_id}/images", response_model=UploadResult, status_code=201, tags=["Images"],
             dependencies=[Depends(rate_limit_upload)])
async def upload_images(
    project_id: str, files: list[UploadFile] = File(...), descriptions: list[str] = Form(default=[]),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    settings = get_settings()
    project = owned_project(db, user, project_id)
    if project.status in ("processing", "archived"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Images cannot be added while the project is {project.status}.")
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Upload at most {settings.max_files_per_upload} files at a time.")
    accepted, rejected = [], []
    for index, upload in enumerate(files):
        # Read one byte past the limit, so that an oversized file is never held in memory in full.
        data = await upload.read(settings.max_upload_bytes + 1)
        name = sanitize_filename(upload.filename)
        description = descriptions[index][:2000] if index < len(descriptions) else ""
        try:
            # Decoding is CPU work: run it off the event loop, so other requests keep being served.
            accepted.append(await run_in_threadpool(store_image, db, project.workspace, data, name, project.id, description))
        except ImageRejected as exc:
            rejected.append(UploadRejection(filename=name, reason=str(exc)))
    db.commit()
    return UploadResult(accepted=[image_out(i) for i in accepted], rejected=rejected)


@router.get("/projects/{project_id}/images", response_model=list[ImageOut], tags=["Images"])
def list_images(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    rows = db.scalars(
        select(UploadedImage).options(joinedload(UploadedImage.image_metadata))
        .where(UploadedImage.project_id == project.id).order_by(UploadedImage.created_at)
    )
    return [image_out(i) for i in rows]


@router.patch("/images/{image_id}", response_model=ImageOut, tags=["Images"])
def update_image(image_id: str, body: ImageUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    image = owned_image(db, user, image_id)
    image.description = body.description
    db.commit()
    return image_out(image)


@router.delete("/images/{image_id}", status_code=204, tags=["Images"])
def delete_image(image_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    image = owned_image(db, user, image_id)
    if image.kind != "inspection":
        raise HTTPException(status.HTTP_409_CONFLICT, "Delete the comparison to remove this image.")
    project = image.project
    if project and project.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for processing to finish before deleting images.")
    prefix = image.storage_prefix
    db.delete(image)
    db.flush()
    if project:
        job_service.refresh_project_status(db, project)
    db.commit()
    get_storage().delete_prefix(prefix)


@router.get("/images/{image_id}/file", tags=["Images"])
def image_file(
    image_id: str, variant: str = Query(default="display", pattern="^(display|thumbnail|processed|original)$"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    image = owned_image(db, user, image_id)
    if variant == "original":
        # The exact upload, which may contain EXIF. Delivered only to its owner, always as a download.
        return file_response(image.original_key, image.filename)
    key = {"display": image.display_key, "thumbnail": image.thumbnail_key, "processed": image.processed_key}[variant]
    if not key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This image has not been processed yet.")
    return file_response(key)


@router.get("/images/{image_id}/results", response_model=ImageResults, tags=["Analysis"])
def image_results(image_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    image = owned_image(db, user, image_id)
    return ImageResults(
        image=image_out(image),
        objects=[ObjectOut.model_validate(o) for o in sorted(image.objects, key=lambda o: -o.confidence)],
        findings=[FindingOut.model_validate(f) for f in sorted(image.findings, key=lambda f: -f.score)],
    )


# Analysis jobs ------------------------------------------------------------------------------------
@router.post("/projects/{project_id}/analyze", response_model=JobOut, status_code=202, tags=["Analysis"])
def start_analysis(project_id: str, body: AnalyzeIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    reanalyze = bool(body and body.reanalyze)
    if project.status == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "Unarchive this project before analysing it.")
    active = db.scalar(select(AnalysisJob).where(AnalysisJob.project_id == project.id, AnalysisJob.status.in_(job_service.ACTIVE)))
    if active:
        return active
    pending = select(func.count()).select_from(UploadedImage).where(UploadedImage.project_id == project.id)
    if not reanalyze:
        pending = pending.where(UploadedImage.status != "analysed")
    if not db.scalar(pending):
        raise HTTPException(status.HTTP_409_CONFLICT, "There are no images waiting for analysis.")
    job = job_service.enqueue_analysis(db, project, reanalyze)
    db.commit()
    return job


@router.get("/jobs/{job_id}", response_model=JobOut, tags=["Analysis"])
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_job(db, user, job_id)


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut], tags=["Analysis"])
def project_jobs(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    return list(db.scalars(select(AnalysisJob).where(AnalysisJob.project_id == project.id).order_by(AnalysisJob.queued_at.desc()).limit(20)))


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202, tags=["Analysis"])
def retry_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = owned_job(db, user, job_id)
    if job.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a failed job can be retried.")
    job.status, job.stage, job.attempts, job.error_message, job.finished_at = "queued", "Waiting in queue", 0, None, None
    if job.project_id:
        db.get(InspectionProject, job.project_id).status = "processing"
    db.commit()
    return job


# Findings -----------------------------------------------------------------------------------------
def _finding_out(finding: Finding, model=FindingOut):
    out = model.model_validate(finding)
    out.image_filename = finding.image.filename
    out.project_id = finding.image.project_id
    out.project_name = finding.image.project.name if finding.image.project else None
    return out


@router.get("/findings", response_model=Page[FindingOut], tags=["Findings"])
def list_findings(
    workspace_id: str, category: str | None = None, review_status: str | None = None, band: str | None = None,
    finding_type: str | None = None, project_id: str | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    owned_workspace(db, user, workspace_id)
    query = select(Finding).join(UploadedImage).where(UploadedImage.workspace_id == workspace_id)
    if category:
        query = query.where(Finding.category == category)
    if review_status:
        query = query.where(Finding.review_status == review_status)
    if band:
        query = query.where(Finding.confidence_band == band)
    if finding_type:
        query = query.where(Finding.finding_type == finding_type)
    if project_id:
        query = query.where(UploadedImage.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.options(selectinload(Finding.image).selectinload(UploadedImage.project))
        .order_by(Finding.created_at.desc(), Finding.score.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(items=[_finding_out(f) for f in rows], total=total, page=page, page_size=page_size)


@router.get("/findings/{finding_id}", response_model=FindingDetail, tags=["Findings"])
def get_finding(finding_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _finding_out(owned_finding(db, user, finding_id), FindingDetail)


@router.patch("/findings/{finding_id}/review", response_model=FindingDetail, tags=["Findings"])
def review_finding(finding_id: str, body: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    finding = owned_finding(db, user, finding_id)
    finding.review_status = body.decision
    db.add(ReviewDecision(finding_id=finding.id, user_id=user.id, decision=body.decision, note=body.note.strip()))
    if finding.image.project:
        db.flush()
        job_service.refresh_project_status(db, finding.image.project)
    db.commit()
    db.refresh(finding)
    return _finding_out(finding, FindingDetail)


# Reports ------------------------------------------------------------------------------------------
def report_out(report: InspectionReport) -> ReportOut:
    out = ReportOut.model_validate(report)
    out.project_name = report.project.name
    return out


@router.post("/projects/{project_id}/reports", response_model=ReportOut, status_code=201, tags=["Reports"])
def generate_report(project_id: str, body: ReportCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = owned_project(db, user, project_id)
    if not any(i.status == "analysed" for i in project.images):
        raise HTTPException(status.HTTP_409_CONFLICT, "Analyse at least one image before generating a report.")
    report = create_report(db, project, body.title, body.final_notes)
    db.commit()
    return report_out(report)


@router.get("/reports", response_model=Page[ReportOut], tags=["Reports"])
def list_reports(
    workspace_id: str, project_id: str | None = None, page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    owned_workspace(db, user, workspace_id)
    query = select(InspectionReport).join(InspectionProject).where(InspectionProject.workspace_id == workspace_id)
    if project_id:
        query = query.where(InspectionReport.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(InspectionReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[report_out(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/reports/{report_id}/file", tags=["Reports"])
def report_file(report_id: str, download: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = owned_report(db, user, report_id)
    return file_response(report.storage_key, "visionguard-report.pdf" if download else None)


@router.delete("/reports/{report_id}", status_code=204, tags=["Reports"])
def delete_report(report_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = owned_report(db, user, report_id)
    key = report.storage_key
    db.delete(report)
    db.commit()
    get_storage().delete_prefix(key)
