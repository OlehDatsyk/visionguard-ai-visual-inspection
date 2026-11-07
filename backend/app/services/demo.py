"""Optional demo workspace. It is isolated from real records and can be removed at any time."""
from pathlib import Path

from sqlalchemy import select

from app.core.storage import get_storage
from app.demo.generator import build_samples
from app.models import ComparisonResult, Finding, InspectionProject, ReviewDecision, User, Workspace
from app.services.images import store_image
from app.services.jobs import analyse_image, refresh_project_status, run_comparison

SAMPLES = Path(__file__).resolve().parents[1] / "demo" / "samples"
DEMO_NOTE = "Demonstration data. Images are generated or CC0 sample photos, and were analysed by the real pipeline."


def _project(db, workspace, name, category, description, files: dict[str, bytes]) -> InspectionProject:
    project = InspectionProject(
        workspace_id=workspace.id, name=f"[DEMO] {name}", description=description, category=category, notes=DEMO_NOTE,
    )
    db.add(project)
    db.flush()
    for filename, data in files.items():
        store_image(db, workspace, data, filename, project.id, "Demonstration sample image")
    db.flush()
    db.refresh(project)
    for image in project.images:
        analyse_image(db, image, category, None)
    db.flush()
    refresh_project_status(db, project)
    return project


def seed_demo(db, user: User) -> Workspace:
    existing = db.scalar(select(Workspace).where(Workspace.owner_id == user.id, Workspace.is_demo.is_(True)))
    if existing:
        return existing
    workspace = Workspace(owner_id=user.id, name="Demo workspace", is_demo=True)
    db.add(workspace)
    db.flush()
    samples = build_samples()
    surfaces = _project(
        db, workspace, "Surface condition survey", "surface_material",
        "Generated concrete and steel surfaces with artificial marks.",
        {k: samples[k] for k in ("demo_concrete_wall.png", "demo_steel_plate.png")},
    )
    _project(
        db, workspace, "Painted panel check", "vehicle_damage", "A generated painted panel with an artificial scratch.",
        {"demo_painted_panel.png": samples["demo_painted_panel.png"]},
    )
    _project(
        db, workspace, "Object recognition sample", "object_recognition", "CC0 sample photos for the object detector.",
        {p.name: p.read_bytes() for p in (SAMPLES / "coffee.png", SAMPLES / "chelsea.png")},
    )
    before = store_image(db, workspace, samples["demo_before.png"], "demo_before.png", kind="comparison")
    after = store_image(db, workspace, samples["demo_after.png"], "demo_after.png", kind="comparison")
    db.flush()
    comparison = ComparisonResult(
        workspace_id=workspace.id, project_id=surfaces.id, before_image_id=before.id, after_image_id=after.id,
        name="[DEMO] Wall before and after", status="processing",
    )
    db.add(comparison)
    db.flush()
    run_comparison(db, comparison)
    # Example review decisions, so that review analytics have something to show in the demo.
    findings = list(db.scalars(
        select(Finding).join(Finding.image).where(
            Finding.image.has(project_id=surfaces.id), Finding.finding_type == "potential_defect"
        ).order_by(Finding.score.desc())
    ))
    decisions = ("confirmed", "needs_review", "false_positive")
    for finding, decision in zip(findings, decisions):
        finding.review_status = decision
        db.add(ReviewDecision(finding_id=finding.id, user_id=user.id, decision=decision, note="Example demo decision."))
    db.flush()
    refresh_project_status(db, surfaces)
    db.commit()
    return workspace


def reset_demo(db, user: User) -> bool:
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id, Workspace.is_demo.is_(True)))
    if workspace is None:
        return False
    get_storage().delete_prefix(f"{user.id}/{workspace.id}")
    db.delete(workspace)
    db.commit()
    return True
