"""Before-and-after image comparison endpoints."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owned_comparison, owned_project, owned_workspace, rate_limit_upload
from app.api.inspections import file_response
from app.core.config import get_settings
from app.core.storage import get_storage
from app.database.session import get_db
from app.models import AnalysisJob, ComparisonResult, User
from app.schemas.common import ComparisonOut, JobOut, Page
from app.services import jobs as job_service
from app.services.images import ImageRejected, store_image
from app.vision.comparison import LIMITATIONS, METRIC_EXPLANATIONS

router = APIRouter(tags=["Image comparison"])


def _out(db: Session, comparison: ComparisonResult) -> ComparisonOut:
    out = ComparisonOut.model_validate(comparison)
    out.before_filename = comparison.before_image.filename
    out.after_filename = comparison.after_image.filename
    out.metric_explanations = METRIC_EXPLANATIONS
    out.limitations = LIMITATIONS
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.comparison_id == comparison.id).order_by(AnalysisJob.queued_at.desc()).limit(1)
    )
    out.job = JobOut.model_validate(job) if job else None
    return out


@router.post("/comparisons", response_model=ComparisonOut, status_code=202, dependencies=[Depends(rate_limit_upload)])
async def create_comparison(
    workspace_id: str = Form(...), name: str = Form(default="", max_length=160), project_id: str | None = Form(default=None),
    before: UploadFile = File(...), after: UploadFile = File(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    workspace = owned_workspace(db, user, workspace_id)
    if project_id:
        if owned_project(db, user, project_id).workspace_id != workspace.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    limit = get_settings().max_upload_bytes + 1
    try:
        before_data, after_data = await before.read(limit), await after.read(limit)
        before_image = await run_in_threadpool(store_image, db, workspace, before_data, before.filename or "before", kind="comparison")
        after_image = await run_in_threadpool(store_image, db, workspace, after_data, after.filename or "after", kind="comparison")
    except ImageRejected as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.flush()
    comparison = ComparisonResult(
        workspace_id=workspace.id, project_id=project_id or None, before_image_id=before_image.id,
        after_image_id=after_image.id, name=name.strip() or f"{before_image.filename} vs {after_image.filename}",
    )
    db.add(comparison)
    db.flush()
    job_service.enqueue_comparison(db, comparison)
    db.commit()
    return _out(db, comparison)


@router.get("/comparisons", response_model=Page[ComparisonOut])
def list_comparisons(
    workspace_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    owned_workspace(db, user, workspace_id)
    query = select(ComparisonResult).where(ComparisonResult.workspace_id == workspace_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ComparisonResult.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[_out(db, c) for c in rows], total=total, page=page, page_size=page_size)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, owned_comparison(db, user, comparison_id))


@router.get("/comparisons/{comparison_id}/file")
def comparison_file(
    comparison_id: str, variant: str = Query(pattern="^(before|aligned|heatmap|mask)$"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    comparison = owned_comparison(db, user, comparison_id)
    if comparison.status != "completed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This comparison has not finished.")
    extension = "png" if variant == "mask" else "jpg"
    return file_response(f"{comparison.storage_prefix}/{variant}.{extension}")


@router.delete("/comparisons/{comparison_id}", status_code=204)
def delete_comparison(comparison_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    comparison = owned_comparison(db, user, comparison_id)
    if comparison.status in ("queued", "processing"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for this comparison to finish before deleting it.")
    prefixes = [comparison.storage_prefix, comparison.before_image.storage_prefix, comparison.after_image.storage_prefix]
    images = [comparison.before_image, comparison.after_image]
    db.delete(comparison)
    db.flush()
    for image in images:
        db.delete(image)
    db.commit()
    for prefix in filter(None, prefixes):
        get_storage().delete_prefix(prefix)
