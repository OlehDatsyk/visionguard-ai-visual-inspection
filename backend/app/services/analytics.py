"""Dashboard and analytics aggregates. Every figure is computed from stored records."""
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select

from app.models import DetectedObject, Finding, InspectionProject, InspectionReport, ReviewDecision, UploadedImage
from app.vision.profiles import CATEGORIES


def _as_date(value) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).date().isoformat()


def _daily_series(values: list, days: int) -> list[dict]:
    counts = Counter(_as_date(v) for v in values)
    today = datetime.now(UTC).date()
    return [
        {"date": (d := today - timedelta(days=days - 1 - i)).isoformat(), "count": counts.get(d.isoformat(), 0)}
        for i in range(days)
    ]


def overview(db, workspace_id: str) -> dict:
    project_filter = InspectionProject.workspace_id == workspace_id
    in_workspace = select(UploadedImage.id).where(
        UploadedImage.workspace_id == workspace_id, UploadedImage.kind == "inspection"
    )
    projects = db.scalar(select(func.count()).select_from(InspectionProject).where(project_filter)) or 0
    images = db.scalar(
        select(func.count()).select_from(UploadedImage).where(
            UploadedImage.workspace_id == workspace_id, UploadedImage.status == "analysed"
        )
    ) or 0
    defects = db.scalar(
        select(func.count()).select_from(Finding).where(
            Finding.image_id.in_(in_workspace), Finding.finding_type == "potential_defect",
            Finding.review_status != "false_positive",
        )
    ) or 0
    review = db.scalar(
        select(func.count()).select_from(InspectionProject).where(project_filter, InspectionProject.status == "requires_review")
    ) or 0
    recent = list(db.scalars(
        select(InspectionProject).where(project_filter).order_by(InspectionProject.updated_at.desc()).limit(6)
    ))
    created = list(db.scalars(select(InspectionProject.created_at).where(project_filter)))
    categories = Counter(db.scalars(select(InspectionProject.category).where(project_filter)))
    reports = list(db.execute(
        select(InspectionReport.id, InspectionReport.title, InspectionReport.created_at, InspectionProject.name)
        .join(InspectionProject).where(project_filter).order_by(InspectionReport.created_at.desc()).limit(5)
    ))
    return {
        "totals": {
            "inspections": projects, "images_analysed": images, "potential_defects": defects,
            "requiring_review": review,
        },
        "recent_projects": recent,
        "defect_distribution": _finding_categories(db, in_workspace),
        "inspection_trend": _daily_series(created, 30),
        "frequent_categories": [
            {"category": k, "label": CATEGORIES.get(k, {}).get("label", k), "count": v} for k, v in categories.most_common(6)
        ],
        "recent_reports": [
            {"id": r.id, "title": r.title, "project_name": r.name, "created_at": r.created_at} for r in reports
        ],
    }


def _finding_categories(db, image_ids) -> list[dict]:
    rows = db.execute(
        select(Finding.category, func.count()).where(
            Finding.image_id.in_(image_ids), Finding.finding_type == "potential_defect"
        ).group_by(Finding.category).order_by(func.count().desc())
    )
    return [{"category": c, "count": n} for c, n in rows]


def insights(db, workspace_id: str, days: int = 90) -> dict:
    project_filter = InspectionProject.workspace_id == workspace_id
    image_ids = select(UploadedImage.id).where(
        UploadedImage.workspace_id == workspace_id, UploadedImage.kind == "inspection"
    )
    created = list(db.scalars(select(InspectionProject.created_at).where(project_filter)))
    since = datetime.now(UTC) - timedelta(days=days)
    review_counts = dict(db.execute(
        select(Finding.review_status, func.count()).where(
            Finding.image_id.in_(image_ids), Finding.finding_type == "potential_defect"
        ).group_by(Finding.review_status)
    ).all())
    confirmed = review_counts.get("confirmed", 0) + review_counts.get("resolved", 0)
    false_positive = review_counts.get("false_positive", 0)
    decided = confirmed + false_positive
    by_category = db.execute(
        select(
            Finding.category,
            func.sum(case((Finding.review_status.in_(("confirmed", "resolved")), 1), else_=0)),
            func.sum(case((Finding.review_status == "false_positive", 1), else_=0)),
            func.count(),
        ).where(Finding.image_id.in_(image_ids), Finding.finding_type == "potential_defect").group_by(Finding.category)
    )
    statuses = db.execute(
        select(InspectionProject.status, func.count()).where(project_filter).group_by(InspectionProject.status)
    )
    objects = db.execute(
        select(DetectedObject.label, func.count()).where(DetectedObject.image_id.in_(image_ids))
        .group_by(DetectedObject.label).order_by(func.count().desc()).limit(10)
    )
    decisions = db.scalar(
        select(func.count()).select_from(ReviewDecision).join(Finding).where(Finding.image_id.in_(image_ids))
    ) or 0
    return {
        "window_days": days,
        "inspections_over_time": _weekly([c for c in created if (c if c.tzinfo else c.replace(tzinfo=UTC)) >= since], days),
        "findings_by_category": _finding_categories(db, image_ids),
        "review_outcomes": [{"status": k, "count": v} for k, v in sorted(review_counts.items())],
        "false_positive": {
            "confirmed": confirmed, "false_positive": false_positive, "decided": decided,
            "unconfirmed": sum(review_counts.values()) - decided,
            # Only people's review decisions feed this rate. It is not a model accuracy measure.
            "rate": round(false_positive / decided, 4) if decided else None,
            "by_category": [
                {"category": c, "confirmed": int(a), "false_positive": int(b), "total": t,
                 "rate": round(int(b) / (int(a) + int(b)), 4) if int(a) + int(b) else None}
                for c, a, b, t in by_category
            ],
        },
        "status_distribution": [{"status": s, "count": n} for s, n in statuses],
        "top_objects": [{"label": l, "count": n} for l, n in objects],
        "review_decisions_recorded": decisions,
    }


def _weekly(values: list, days: int) -> list[dict]:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    weeks = (days + 6) // 7
    counts = [0] * weeks
    for value in values:
        counts[min(weeks - 1, (datetime.fromisoformat(_as_date(value)).date() - start).days // 7)] += 1
    return [{"week_start": (start + timedelta(days=7 * i)).isoformat(), "count": n} for i, n in enumerate(counts)]
