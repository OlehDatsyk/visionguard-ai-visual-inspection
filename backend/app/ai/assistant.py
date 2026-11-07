"""Assistant orchestration: choose the engine, enforce limits and persist messages."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.ai import providers, records_engine
from app.ai.context import comparison_context, project_context, workspace_context
from app.core.config import get_settings
from app.models import AIConversation, AIMessage, ComparisonResult, InspectionProject, Workspace


def external_used_today(db, user_id: str) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    return db.scalar(
        select(func.count()).select_from(AIMessage).join(AIConversation).where(
            AIConversation.user_id == user_id, AIMessage.role == "assistant",
            AIMessage.source.notin_(("records", "user")), AIMessage.created_at >= since,
        )
    ) or 0


def status(db, user_id: str) -> dict:
    settings = get_settings()
    provider = providers.get_provider()
    return {
        "provider": provider.name if provider else "none",
        "external_ai_enabled": provider is not None,
        "model": provider.model if provider else None,
        "daily_limit": settings.ai_daily_message_limit,
        "used_today": external_used_today(db, user_id),
        "message": (
            f"Answers are written by {provider.name} using only your inspection records."
            if provider else "No external AI is configured. Answers come directly from your inspection records."
        ),
    }


def _context_for(db, conversation: AIConversation, workspace_id: str | None) -> dict:
    if conversation.project_id:
        return project_context(db, db.get(InspectionProject, conversation.project_id))
    if conversation.comparison_id:
        return comparison_context(db.get(ComparisonResult, conversation.comparison_id))
    workspace = db.get(Workspace, workspace_id) if workspace_id else None
    if workspace is None or workspace.owner_id != conversation.user_id:
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == conversation.user_id, Workspace.is_demo.is_(False)))
    return workspace_context(db, workspace)


def ask(db, conversation: AIConversation, question: str, workspace_id: str | None = None) -> AIMessage:
    context = _context_for(db, conversation, workspace_id)
    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    db.add(AIMessage(conversation_id=conversation.id, role="user", content=question, source="user"))

    provider = providers.get_provider()
    settings = get_settings()
    source, prefix, text = "records", "", None
    if provider is not None:
        if external_used_today(db, conversation.user_id) >= settings.ai_daily_message_limit:
            prefix = "The daily external AI limit has been reached, so this answer comes directly from the records.\n\n"
        else:
            try:
                text = provider.complete(context, history, question)
                source = provider.name
            except providers.ProviderUnavailable as exc:
                prefix = f"{exc} This answer comes directly from the records instead.\n\n"
    if text is None:
        text = prefix + records_engine.answer(context, question)
    reply = AIMessage(conversation_id=conversation.id, role="assistant", content=text, source=source)
    db.add(reply)
    return reply
