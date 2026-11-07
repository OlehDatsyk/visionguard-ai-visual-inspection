"""Builds the structured facts the assistant may use. Both answer engines read only from this."""
from sqlalchemy import select

from app.models import ComparisonResult, InspectionProject, InspectionReport, Workspace
from app.vision.profiles import CATEGORIES


def project_context(db, project: InspectionProject) -> dict:
    images = []
    for image in project.images:
        images.append({
            "filename": image.filename,
            "status": image.status,
            "description": image.description,
            "analysis_notes": image.analysis_notes,
            "not_assessed": image.unsupported_checks,
            "objects": [
                {"label": o.label, "confidence": o.confidence, "band": o.confidence_band,
                 "box_xywh": [round(o.x), round(o.y), round(o.width), round(o.height)]}
                for o in image.objects
            ],
            "findings": [
                {"id": f.code, "type": f.finding_type, "category": f.category, "score": f.score,
                 "score_type": f.score_type, "band": f.confidence_band, "review_status": f.review_status,
                 "box_xywh": [round(f.x), round(f.y), round(f.width), round(f.height)],
                 "method": f.method, "explanation": f.explanation}
                for f in image.findings
            ],
        })
    comparisons = list(db.scalars(select(ComparisonResult).where(ComparisonResult.project_id == project.id)))
    reports = list(db.scalars(select(InspectionReport).where(InspectionReport.project_id == project.id)))
    return {
        "scope": "project",
        "project": {
            "name": project.name, "category": CATEGORIES.get(project.category, {}).get("label", project.category),
            "status": project.status, "description": project.description, "notes": project.notes,
            "is_demo_data": project.workspace.is_demo,
        },
        "images": images,
        "comparisons": [comparison_facts(c) for c in comparisons],
        "reports": [{"title": r.title, "created_at": r.created_at.isoformat()} for r in reports],
    }


def comparison_facts(comparison: ComparisonResult) -> dict:
    return {
        "name": comparison.name, "status": comparison.status, "metrics": comparison.metrics,
        "changed_regions": comparison.regions[:10], "region_count": len(comparison.regions),
        "warnings": comparison.warnings,
        "before": comparison.before_image.filename, "after": comparison.after_image.filename,
    }


def workspace_context(db, workspace: Workspace) -> dict:
    projects = list(db.scalars(
        select(InspectionProject).where(InspectionProject.workspace_id == workspace.id)
        .order_by(InspectionProject.updated_at.desc()).limit(25)
    ))
    return {
        "scope": "workspace",
        "workspace": {"name": workspace.name, "is_demo_data": workspace.is_demo},
        "projects": [project_context(db, p) for p in projects],
    }


def comparison_context(comparison: ComparisonResult) -> dict:
    return {"scope": "comparison", "comparison": comparison_facts(comparison)}
