"""Analytics, model information, assistant, demo mode."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import assistant
from app.api.deps import (
    get_current_user,
    owned_comparison,
    owned_project,
    owned_workspace,
    rate_limit_assistant,
)
from app.api.inspections import project_out
from app.core.config import get_settings
from app.database.session import get_db
from app.models import AIConversation, User
from app.schemas.common import (
    AssistantStatus,
    ConversationCreate,
    ConversationOut,
    Message,
    MessageIn,
    MessageOut,
    WorkspaceOut,
)
from app.services import analytics
from app.services.demo import reset_demo, seed_demo
from app.vision.detectors.registry import get_detector
from app.vision.profiles import CATEGORIES, MODULE_INFO

router = APIRouter()


@router.get("/analytics/overview", tags=["Analytics"])
def overview(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_workspace(db, user, workspace_id)
    data = analytics.overview(db, workspace_id)
    data["recent_projects"] = [project_out(db, p).model_dump(mode="json") for p in data["recent_projects"]]
    return data


@router.get("/analytics/insights", tags=["Analytics"])
def insights(
    workspace_id: str, days: int = Query(default=90, ge=7, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    owned_workspace(db, user, workspace_id)
    return analytics.insights(db, workspace_id, days)


@router.get("/system/status", tags=["Model information"])
def system_status(user: User = Depends(get_current_user)):
    settings = get_settings()
    return {
        "storage_persistent": settings.storage_persistent or settings.storage_backend == "s3",
        "object_detection_available": get_detector().is_available(),
    }


@router.get("/models", tags=["Model information"])
def models(user: User = Depends(get_current_user)):
    detector = get_detector()
    info = detector.info
    settings = get_settings()
    return {
        "object_detectors": [{
            "key": info.key, "name": info.name, "type": info.model_type, "version": info.version,
            "licence": info.licence, "source": info.source, "available": detector.is_available(),
            "unavailable_reason": detector.unavailable_reason(), "input_requirements": info.input_requirements,
            "processing": info.processing, "supported_categories": info.supported_categories,
            "limitations": info.limitations, "confidence_threshold": settings.detector_confidence_threshold,
        }],
        "image_processing_modules": [
            {"key": key, **value, "available": True, "type": "Classical image processing (OpenCV), no trained model",
             "licence": "Project code. OpenCV is Apache-2.0.",
             "limitations": ["Scores are uncalibrated.", "Assumes a mostly uniform surface.", "Needs human review."]}
            for key, value in MODULE_INFO.items()
        ],
        "segmentation": {
            "name": "GrabCut from detector box", "type": "Classical image segmentation (OpenCV), no trained model",
            "available": detector.is_available(),
            "limitations": ["Outlines are approximate and do not use class knowledge."],
        },
        "performance_statistics": None,
        "performance_note": (
            "No accuracy, precision or recall figures are shown, because no labelled ground-truth data has been "
            "evaluated. Model confidence is not model accuracy."
        ),
        "inspection_categories": [{"key": k, "label": v["label"]} for k, v in CATEGORIES.items()],
    }


# Assistant ----------------------------------------------------------------------------------------
@router.get("/assistant/status", response_model=AssistantStatus, tags=["AI assistant"])
def assistant_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return assistant.status(db, user.id)


@router.post("/assistant/conversations", response_model=ConversationOut, status_code=201, tags=["AI assistant"])
def create_conversation(body: ConversationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = "Workspace questions"
    if body.project_id:
        title = owned_project(db, user, body.project_id).name
    elif body.comparison_id:
        title = owned_comparison(db, user, body.comparison_id).name
    elif body.workspace_id:
        owned_workspace(db, user, body.workspace_id)
    conversation = AIConversation(
        user_id=user.id, project_id=body.project_id, comparison_id=None if body.project_id else body.comparison_id, title=title[:160],
    )
    db.add(conversation)
    db.commit()
    return conversation


def _conversation(db: Session, user: User, conversation_id: str) -> AIConversation:
    conversation = db.get(AIConversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return conversation


@router.get("/assistant/conversations", response_model=list[ConversationOut], tags=["AI assistant"])
def list_conversations(
    project_id: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    query = select(AIConversation).where(AIConversation.user_id == user.id)
    if project_id:
        query = query.where(AIConversation.project_id == project_id)
    return list(db.scalars(query.order_by(AIConversation.created_at.desc()).limit(30)))


@router.get("/assistant/conversations/{conversation_id}", response_model=ConversationOut, tags=["AI assistant"])
def get_conversation(conversation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _conversation(db, user, conversation_id)


@router.post("/assistant/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201,
             tags=["AI assistant"], dependencies=[Depends(rate_limit_assistant)])
def post_message(
    conversation_id: str, body: MessageIn, workspace_id: str | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    conversation = _conversation(db, user, conversation_id)
    reply = assistant.ask(db, conversation, body.content, workspace_id)
    db.commit()
    return reply


# Demo mode ----------------------------------------------------------------------------------------
@router.post("/demo", response_model=WorkspaceOut, status_code=201, tags=["Demo"])
def create_demo(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return seed_demo(db, user)


@router.delete("/demo", response_model=Message, tags=["Demo"])
def delete_demo(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    removed = reset_demo(db, user)
    return Message(message="Demo data removed" if removed else "No demo data exists")
