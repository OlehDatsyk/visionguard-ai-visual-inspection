"""Authentication and ownership checks. A resource owned by someone else returns 404, not 403,
so that the API does not reveal which identifiers exist."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import client_ip, decode_access_token, rate_limiter
from app.database.session import get_db
from app.models import (
    AnalysisJob,
    ComparisonResult,
    Finding,
    InspectionProject,
    InspectionReport,
    UploadedImage,
    User,
    Workspace,
)

_bearer = HTTPBearer(auto_error=False)
NOT_FOUND = "Not found"


def _unauthorised() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if credentials is None:
        raise _unauthorised()
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _unauthorised()
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active or user.token_version != payload["ver"]:
        raise _unauthorised()
    return user


def rate_limit_auth(request: Request) -> None:
    rate_limiter.check(f"auth:{client_ip(request)}", get_settings().auth_rate_limit_per_minute)


def rate_limit_upload(user: User = Depends(get_current_user)) -> None:
    rate_limiter.check(f"upload:{user.id}", get_settings().upload_rate_limit_per_minute)


def rate_limit_assistant(user: User = Depends(get_current_user)) -> None:
    rate_limiter.check(f"assistant:{user.id}", get_settings().assistant_rate_limit_per_minute)


def owned_workspace(db: Session, user: User, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return workspace


def owned_project(db: Session, user: User, project_id: str) -> InspectionProject:
    project = db.scalar(
        select(InspectionProject).join(Workspace).where(InspectionProject.id == project_id, Workspace.owner_id == user.id)
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return project


def owned_image(db: Session, user: User, image_id: str) -> UploadedImage:
    image = db.scalar(
        select(UploadedImage).join(Workspace).where(UploadedImage.id == image_id, Workspace.owner_id == user.id)
    )
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return image


def owned_finding(db: Session, user: User, finding_id: str) -> Finding:
    finding = db.scalar(
        select(Finding).join(UploadedImage).join(Workspace).where(Finding.id == finding_id, Workspace.owner_id == user.id)
    )
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return finding


def owned_job(db: Session, user: User, job_id: str) -> AnalysisJob:
    job = db.scalar(
        select(AnalysisJob).join(Workspace, AnalysisJob.workspace_id == Workspace.id)
        .where(AnalysisJob.id == job_id, Workspace.owner_id == user.id)
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return job


def owned_comparison(db: Session, user: User, comparison_id: str) -> ComparisonResult:
    comparison = db.scalar(
        select(ComparisonResult).join(Workspace, ComparisonResult.workspace_id == Workspace.id)
        .where(ComparisonResult.id == comparison_id, Workspace.owner_id == user.id)
    )
    if comparison is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return comparison


def owned_report(db: Session, user: User, report_id: str) -> InspectionReport:
    report = db.scalar(
        select(InspectionReport).join(InspectionProject).join(Workspace)
        .where(InspectionReport.id == report_id, Workspace.owner_id == user.id)
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return report
