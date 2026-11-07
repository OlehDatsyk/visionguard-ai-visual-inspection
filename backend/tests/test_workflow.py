"""End-to-end API flows: analysis jobs, review, comparison, reports, analytics, assistant and demo."""
from unittest import mock

import pytest
from sqlalchemy import select

from app.ai import providers
from app.ai.records_engine import answer
from app.core.config import get_settings
from app.database.session import new_session
from app.models import AnalysisJob, ReviewDecision
from app.services import jobs as job_service
from tests.conftest import API, make_project, png_bytes, run_jobs, surface_with_crack, upload, workspace_id


def analysed_project(client, auth, category="surface_material"):
    project = make_project(client, auth, category)
    image = upload(client, auth, project["id"], [("crack.png", surface_with_crack())]).json()["accepted"][0]
    job = client.post(f"{API}/projects/{project['id']}/analyze", headers=auth)
    assert job.status_code == 202
    run_jobs()
    return project["id"], image["id"], job.json()["id"]


def test_project_crud_search_filter_and_pagination(client, auth):
    wid = workspace_id(client, auth)
    for i in range(3):
        make_project(client, auth, name=f"Bridge {i}")
    make_project(client, auth, "vehicle_damage", name="Fleet 100% check")
    base = f"{API}/projects?workspace_id={wid}"
    assert client.get(base, headers=auth).json()["total"] == 4
    assert client.get(f"{base}&q=bridge", headers=auth).json()["total"] == 3
    assert client.get(f"{base}&q=100%25", headers=auth).json()["total"] == 1  # A literal %, not a wildcard.
    assert client.get(f"{base}&category=vehicle_damage", headers=auth).json()["total"] == 1
    assert client.get(f"{base}&status=draft", headers=auth).json()["total"] == 4
    page = client.get(f"{base}&page=2&page_size=3", headers=auth).json()
    assert len(page["items"]) == 1 and page["page"] == 2
    pid = page["items"][0]["id"]
    updated = client.patch(f"{API}/projects/{pid}", headers=auth, json={"name": "New", "notes": "Note"}).json()
    assert updated["name"] == "New" and updated["notes"] == "Note"
    assert client.patch(f"{API}/projects/{pid}", headers=auth, json={"archived": True}).json()["status"] == "archived"
    assert client.patch(f"{API}/projects/{pid}", headers=auth, json={"archived": False}).json()["status"] == "draft"
    assert client.delete(f"{API}/projects/{pid}", headers=auth).status_code == 204
    assert client.get(f"{API}/projects/{pid}", headers=auth).status_code == 404


def test_unknown_category_rejected(client, auth):
    response = client.post(f"{API}/projects", headers=auth, json={"workspace_id": workspace_id(client, auth), "name": "x", "category": "nope"})
    assert response.status_code == 422


def test_analysis_job_lifecycle_and_results(client, auth):
    project = make_project(client, auth)
    image = upload(client, auth, project["id"], [("crack.png", surface_with_crack())]).json()["accepted"][0]
    assert image["status"] == "uploaded"
    job = client.post(f"{API}/projects/{project['id']}/analyze", headers=auth).json()
    assert job["status"] == "queued" and job["items_total"] == 1 and job["items_done"] == 0
    assert client.get(f"{API}/projects/{project['id']}", headers=auth).json()["status"] == "processing"
    # A second request while one is active returns the same job, rather than duplicating work.
    assert client.post(f"{API}/projects/{project['id']}/analyze", headers=auth).json()["id"] == job["id"]
    run_jobs()
    finished = client.get(f"{API}/jobs/{job['id']}", headers=auth).json()
    assert finished["status"] == "completed" and finished["items_done"] == 1 and finished["finished_at"]
    results = client.get(f"{API}/images/{image['id']}/results", headers=auth).json()
    assert results["image"]["status"] == "analysed" and results["image"]["has_processed"]
    assert results["objects"][0]["label"] == "widget" and results["objects"][0]["confidence_band"] == "high"
    crack = [f for f in results["findings"] if f["category"] == "crack_like"]
    assert crack and crack[0]["review_status"] == "unreviewed" and crack[0]["score_type"] == "heuristic_anomaly"
    assert crack[0]["confidence_band"] != "high" and crack[0]["method"] and crack[0]["explanation"]
    assert client.get(f"{API}/images/{image['id']}/file?variant=processed", headers=auth).status_code == 200
    assert client.get(f"{API}/projects/{project['id']}", headers=auth).json()["status"] == "requires_review"


def test_analyze_needs_pending_images(client, auth):
    project = make_project(client, auth)
    assert client.post(f"{API}/projects/{project['id']}/analyze", headers=auth).status_code == 409


def test_upload_blocked_during_processing(client, auth):
    project = make_project(client, auth)
    upload(client, auth, project["id"], [("a.png", png_bytes())])
    client.post(f"{API}/projects/{project['id']}/analyze", headers=auth)
    assert upload(client, auth, project["id"], [("b.png", png_bytes())]).status_code == 409
    assert client.delete(f"{API}/projects/{project['id']}", headers=auth).status_code == 409
    run_jobs()


def test_failing_job_retries_then_fails_safely_and_can_be_retried(client, auth):
    project = make_project(client, auth)
    upload(client, auth, project["id"], [("a.png", png_bytes())])
    job_id = client.post(f"{API}/projects/{project['id']}/analyze", headers=auth).json()["id"]
    with mock.patch.object(job_service, "analyse_image", side_effect=RuntimeError("C:\\secret\\path exploded")):
        assert job_service.process_next_job()
        assert client.get(f"{API}/jobs/{job_id}", headers=auth).json()["status"] == "queued"  # Automatic retry.
        assert job_service.process_next_job()
    failed = client.get(f"{API}/jobs/{job_id}", headers=auth).json()
    assert failed["status"] == "failed" and failed["attempts"] == 2
    assert "secret" not in failed["error_message"]  # Internal details stay out of API responses.
    assert client.get(f"{API}/projects/{project['id']}", headers=auth).json()["status"] == "draft"
    assert client.post(f"{API}/jobs/{job_id}/retry", headers=auth).status_code == 202
    run_jobs()
    assert client.get(f"{API}/jobs/{job_id}", headers=auth).json()["status"] == "completed"
    assert client.post(f"{API}/jobs/{job_id}/retry", headers=auth).status_code == 409


def test_stale_running_job_is_requeued(client, auth):
    from datetime import UTC, datetime, timedelta

    project = make_project(client, auth)
    upload(client, auth, project["id"], [("a.png", png_bytes())])
    job_id = client.post(f"{API}/projects/{project['id']}/analyze", headers=auth).json()["id"]
    with new_session() as db:
        job = db.get(AnalysisJob, job_id)
        job.status, job.attempts = "running", 1
        job.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    assert job_service.requeue_stale_jobs() == 1
    run_jobs()
    assert client.get(f"{API}/jobs/{job_id}", headers=auth).json()["status"] == "completed"


def test_review_is_recorded_with_history_and_updates_status(client, auth):
    project_id, image_id, _ = analysed_project(client, auth)
    findings = client.get(f"{API}/images/{image_id}/results", headers=auth).json()["findings"]
    fid = findings[0]["id"]
    assert client.patch(f"{API}/findings/{fid}/review", headers=auth, json={"decision": "invalid"}).status_code == 422
    first = client.patch(f"{API}/findings/{fid}/review", headers=auth, json={"decision": "needs_review", "note": "Check on site"}).json()
    assert first["review_status"] == "needs_review" and first["reviews"][0]["note"] == "Check on site"
    second = client.patch(f"{API}/findings/{fid}/review", headers=auth, json={"decision": "confirmed"}).json()
    assert [r["decision"] for r in second["reviews"]] == ["needs_review", "confirmed"]
    for finding in findings:
        client.patch(f"{API}/findings/{finding['id']}/review", headers=auth, json={"decision": "false_positive"})
    assert client.get(f"{API}/projects/{project_id}", headers=auth).json()["status"] == "completed"
    with new_session() as db:
        assert len(list(db.scalars(select(ReviewDecision)))) >= 3


def test_findings_list_filters(client, auth):
    _, image_id, _ = analysed_project(client, auth)
    wid = workspace_id(client, auth)
    all_items = client.get(f"{API}/findings?workspace_id={wid}", headers=auth).json()
    assert all_items["total"] >= 1 and all_items["items"][0]["image_filename"] == "crack.png"
    assert client.get(f"{API}/findings?workspace_id={wid}&review_status=confirmed", headers=auth).json()["total"] == 0
    assert client.get(f"{API}/findings?workspace_id={wid}&category=crack_like", headers=auth).json()["total"] >= 1
    detail = client.get(f"{API}/findings/{all_items['items'][0]['id']}", headers=auth).json()
    assert detail["reviews"] == []


def test_reanalysis_replaces_results(client, auth):
    project_id, image_id, _ = analysed_project(client, auth)
    before = client.get(f"{API}/images/{image_id}/results", headers=auth).json()
    assert client.post(f"{API}/projects/{project_id}/analyze", headers=auth).status_code == 409
    assert client.post(f"{API}/projects/{project_id}/analyze", headers=auth, json={"reanalyze": True}).status_code == 202
    run_jobs()
    after = client.get(f"{API}/images/{image_id}/results", headers=auth).json()
    assert len(after["findings"]) == len(before["findings"])
    assert {f["id"] for f in after["findings"]}.isdisjoint({f["id"] for f in before["findings"]})


def test_delete_image_and_project_remove_stored_files(client, auth):
    from app.core.storage import get_storage

    project = make_project(client, auth)
    images = upload(client, auth, project["id"], [("a.png", png_bytes()), ("b.png", png_bytes())]).json()["accepted"]
    with new_session() as db:
        from app.models import UploadedImage

        keys = [db.get(UploadedImage, i["id"]).display_key for i in images]
    assert all(get_storage().exists(k) for k in keys)
    assert client.delete(f"{API}/images/{images[0]['id']}", headers=auth).status_code == 204
    assert not get_storage().exists(keys[0]) and get_storage().exists(keys[1])
    assert client.delete(f"{API}/projects/{project['id']}", headers=auth).status_code == 204
    assert not get_storage().exists(keys[1])


# Comparison ---------------------------------------------------------------------------------------
def test_comparison_flow_and_permissions(client, auth, other_auth):
    wid = workspace_id(client, auth)
    data = surface_with_crack()
    response = client.post(
        f"{API}/comparisons", headers=auth, data={"workspace_id": wid, "name": "Wall"},
        files={"before": ("before.png", png_bytes((600, 400), (160, 160, 160))), "after": ("after.png", data)},
    )
    assert response.status_code == 202, response.text
    cid = response.json()["id"]
    assert response.json()["status"] == "queued"
    assert client.get(f"{API}/comparisons/{cid}/file?variant=heatmap", headers=auth).status_code == 404
    run_jobs()
    done = client.get(f"{API}/comparisons/{cid}", headers=auth).json()
    assert done["status"] == "completed" and 0 <= done["metrics"]["ssim"] <= 1
    assert done["regions"] and done["limitations"] and "ssim" in done["metric_explanations"]
    for variant in ("before", "aligned", "heatmap", "mask"):
        assert client.get(f"{API}/comparisons/{cid}/file?variant={variant}", headers=auth).status_code == 200
    assert client.get(f"{API}/comparisons/{cid}/file?variant=../x", headers=auth).status_code == 422
    assert client.get(f"{API}/comparisons/{cid}", headers=other_auth).status_code == 404
    assert client.get(f"{API}/comparisons?workspace_id={wid}", headers=auth).json()["total"] == 1
    assert client.delete(f"{API}/comparisons/{cid}", headers=other_auth).status_code == 404
    assert client.delete(f"{API}/comparisons/{cid}", headers=auth).status_code == 204
    assert client.get(f"{API}/comparisons?workspace_id={wid}", headers=auth).json()["total"] == 0


def test_comparison_rejects_invalid_image(client, auth):
    response = client.post(
        f"{API}/comparisons", headers=auth, data={"workspace_id": workspace_id(client, auth)},
        files={"before": ("a.png", b"junk"), "after": ("b.png", png_bytes())},
    )
    assert response.status_code == 422


# Reports ------------------------------------------------------------------------------------------
def test_report_generation_download_and_contents(client, auth, other_auth):
    project_id, image_id, _ = analysed_project(client, auth)
    response = client.post(f"{API}/projects/{project_id}/reports", headers=auth, json={"title": "Wall survey", "final_notes": "Reviewed on site."})
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["title"] == "Wall survey" and report["page_count"] >= 2 and report["file_size"] > 1000
    file = client.get(f"{API}/reports/{report['id']}/file", headers=auth)
    assert file.headers["content-type"] == "application/pdf" and file.content.startswith(b"%PDF")
    download = client.get(f"{API}/reports/{report['id']}/file?download=true", headers=auth)
    assert "attachment" in download.headers["content-disposition"]
    assert client.get(f"{API}/reports/{report['id']}/file", headers=other_auth).status_code == 404
    wid = workspace_id(client, auth)
    assert client.get(f"{API}/reports?workspace_id={wid}", headers=auth).json()["total"] == 1
    assert client.delete(f"{API}/reports/{report['id']}", headers=auth).status_code == 204


def test_report_text_has_required_sections_and_no_private_paths(client, auth):
    from app.core.storage import get_storage
    from app.models import InspectionReport
    from pathlib import Path

    project_id, _, _ = analysed_project(client, auth)
    report = client.post(f"{API}/projects/{project_id}/reports", headers=auth, json={}).json()
    with new_session() as db:
        pdf = get_storage().read(db.get(InspectionReport, report["id"]).storage_key)
    text = pdf_text(pdf)
    for section in ("VisionGuard AI", "Project information", "Analysis summary", "Detected objects", "Potential defects",
                    "Limitations and disclaimers", "Final inspection notes", "not certified"):
        assert section in text, section
    assert get_settings().secret_key not in text
    assert str(Path(get_settings().storage_root)) not in text and "storage/" not in text


def pdf_text(pdf: bytes) -> str:
    """Minimal text extraction for the uncompressed-after-decoding streams reportlab writes."""
    import base64
    import re
    import zlib

    text = []
    for stream in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        raw = stream.strip().removesuffix(b"~>")
        try:
            data = zlib.decompress(base64.a85decode(raw, adobe=False))
        except Exception:  # noqa: BLE001 - image streams and others are not text
            continue
        text += [m.decode("latin-1") for m in re.findall(rb"\((.*?)\) Tj", data, re.S)]
    return " ".join(text)


def test_report_needs_analysis(client, auth):
    project = make_project(client, auth)
    assert client.post(f"{API}/projects/{project['id']}/reports", headers=auth, json={}).status_code == 409


# Analytics ----------------------------------------------------------------------------------------
def test_empty_dashboard_reports_zeros(client, auth):
    data = client.get(f"{API}/analytics/overview?workspace_id={workspace_id(client, auth)}", headers=auth).json()
    assert data["totals"] == {"inspections": 0, "images_analysed": 0, "potential_defects": 0, "requiring_review": 0}
    assert data["recent_projects"] == [] and sum(d["count"] for d in data["inspection_trend"]) == 0


def test_analytics_match_records(client, auth):
    _, image_id, _ = analysed_project(client, auth)
    wid = workspace_id(client, auth)
    findings = client.get(f"{API}/images/{image_id}/results", headers=auth).json()["findings"]
    defects = [f for f in findings if f["finding_type"] == "potential_defect"]
    overview = client.get(f"{API}/analytics/overview?workspace_id={wid}", headers=auth).json()
    assert overview["totals"]["inspections"] == 1 and overview["totals"]["images_analysed"] == 1
    assert overview["totals"]["potential_defects"] == len(defects) and overview["totals"]["requiring_review"] == 1
    assert overview["inspection_trend"][-1]["count"] == 1
    empty = client.get(f"{API}/analytics/insights?workspace_id={wid}", headers=auth).json()
    assert empty["false_positive"]["rate"] is None  # No decisions yet, so there is no rate to invent.
    client.patch(f"{API}/findings/{defects[0]['id']}/review", headers=auth, json={"decision": "false_positive"})
    insights = client.get(f"{API}/analytics/insights?workspace_id={wid}", headers=auth).json()
    assert insights["false_positive"]["rate"] == 1.0 and insights["false_positive"]["decided"] == 1
    assert insights["top_objects"][0]["label"] == "widget"
    assert insights["review_decisions_recorded"] == 1
    assert sum(w["count"] for w in insights["inspections_over_time"]) == 1


def test_model_information_is_honest(client, auth):
    from app.vision.detectors.registry import get_detector

    data = client.get(f"{API}/models", headers=auth).json()
    assert data["performance_statistics"] is None and "ground-truth" in data["performance_note"]
    get_detector().available = False
    data = client.get(f"{API}/models", headers=auth).json()
    assert data["object_detectors"][0]["available"] is False and data["object_detectors"][0]["unavailable_reason"]


# Assistant ----------------------------------------------------------------------------------------
def conversation(client, auth, **body):
    return client.post(f"{API}/assistant/conversations", headers=auth, json=body).json()["id"]


def ask(client, auth, cid, text):
    response = client.post(f"{API}/assistant/conversations/{cid}/messages", headers=auth, json={"content": text})
    assert response.status_code == 201, response.text
    return response.json()


def test_assistant_answers_from_records_without_external_ai(client, auth):
    project_id, image_id, _ = analysed_project(client, auth)
    status = client.get(f"{API}/assistant/status", headers=auth).json()
    assert status["external_ai_enabled"] is False
    cid = conversation(client, auth, project_id=project_id)
    objects = ask(client, auth, cid, "What objects were detected?")
    assert "widget" in objects["content"] and objects["source"] == "records"
    finding = client.get(f"{API}/images/{image_id}/results", headers=auth).json()["findings"][0]
    assert "crack" in ask(client, auth, cid, "Can you summarise this inspection?")["content"]
    assert finding["code"] in ask(client, auth, cid, "Which findings have not been reviewed?")["content"]
    explained = ask(client, auth, cid, f"What does {finding['code']} mean?")["content"]
    assert finding["method"] in explained and f"{finding['score']:.2f}" in explained
    assert "can't find" in ask(client, auth, cid, "Explain F-ZZZZ-99")["content"]
    assert "No image comparison" in ask(client, auth, cid, "What is the difference between these two images?")["content"]
    assert "don't answer" in ask(client, auth, cid, "What is the capital of France?")["content"]
    history = client.get(f"{API}/assistant/conversations/{cid}", headers=auth).json()
    assert len(history["messages"]) == 14


def test_assistant_conversation_isolated_between_users(client, auth, other_auth):
    project = make_project(client, auth)
    assert client.post(f"{API}/assistant/conversations", headers=other_auth, json={"project_id": project["id"]}).status_code == 404
    cid = conversation(client, auth, project_id=project["id"])
    assert client.get(f"{API}/assistant/conversations/{cid}", headers=other_auth).status_code == 404
    assert client.post(f"{API}/assistant/conversations/{cid}/messages", headers=other_auth, json={"content": "hi"}).status_code == 404


def test_assistant_empty_records_do_not_invent_results():
    empty = {"scope": "project", "project": {"name": "P", "category": "c", "status": "draft", "description": "", "notes": "", "is_demo_data": False},
             "images": [], "comparisons": [], "reports": []}
    assert "no image has been analysed" in answer(empty, "what objects were detected?")
    assert "does not prove" in answer(empty, "which areas require further inspection?")


class StubProvider(providers.AIProvider):
    name = "anthropic"
    model = "stub"

    def __init__(self, error=None):
        self.error = error
        self.seen = None

    def complete(self, context, history, question):
        self.seen = context
        if self.error:
            raise self.error
        return "Provider answer"


def test_provider_gets_records_and_failure_falls_back(client, auth):
    project_id, _, _ = analysed_project(client, auth)
    cid = conversation(client, auth, project_id=project_id)
    stub = StubProvider()
    with mock.patch.object(providers, "get_provider", return_value=stub):
        reply = ask(client, auth, cid, "Summarise")
        assert reply["content"] == "Provider answer" and reply["source"] == "anthropic"
        assert stub.seen["images"][0]["filename"] == "crack.png"
    with mock.patch.object(providers, "get_provider", return_value=StubProvider(providers.ProviderUnavailable("The AI provider could not be reached."))):
        reply = ask(client, auth, cid, "What objects were detected?")
        assert reply["source"] == "records" and "could not be reached" in reply["content"] and "widget" in reply["content"]


def test_external_usage_limit_enforced(client, auth):
    project_id, _, _ = analysed_project(client, auth)
    cid = conversation(client, auth, project_id=project_id)
    settings = get_settings()
    original = settings.ai_daily_message_limit
    settings.ai_daily_message_limit = 1
    try:
        with mock.patch.object(providers, "get_provider", return_value=StubProvider()):
            assert ask(client, auth, cid, "Summarise")["source"] == "anthropic"
            limited = ask(client, auth, cid, "Summarise")
            assert limited["source"] == "records" and "limit" in limited["content"]
    finally:
        settings.ai_daily_message_limit = original


def test_anthropic_provider_error_mapping_and_refusal():
    import anthropic
    import httpx2

    settings = get_settings()
    settings.ai_api_key = "test-key"
    try:
        provider = providers.AnthropicProvider()
        client = mock.Mock()
        provider._client = client
        context = {"scope": "project"}
        client.beta.messages.create.side_effect = anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com"))
        with pytest.raises(providers.ProviderUnavailable, match="in time"):
            provider.complete(context, [], "q")
        client.beta.messages.create.side_effect = None
        client.beta.messages.create.return_value = mock.Mock(stop_reason="refusal", content=[])
        with pytest.raises(providers.ProviderUnavailable, match="declined"):
            provider.complete(context, [], "q")
        client.beta.messages.create.return_value = mock.Mock(stop_reason="end_turn", content=[mock.Mock(type="text", text=" Answer ")])
        assert provider.complete(context, [], "q") == "Answer"
        sent = client.beta.messages.create.call_args.kwargs
        assert "test-key" not in str(sent) and "inspection_records" in sent["messages"][-1]["content"]
    finally:
        settings.ai_api_key = ""


# Demo and settings --------------------------------------------------------------------------------
def test_demo_is_labelled_isolated_and_resettable(client, auth):
    real_wid = workspace_id(client, auth)
    demo = client.post(f"{API}/demo", headers=auth)
    assert demo.status_code == 201 and demo.json()["is_demo"] is True
    assert client.post(f"{API}/demo", headers=auth).json()["id"] == demo.json()["id"]  # Idempotent.
    demo_wid = demo.json()["id"]
    real = client.get(f"{API}/analytics/overview?workspace_id={real_wid}", headers=auth).json()
    assert real["totals"]["inspections"] == 0  # Demo records never reach real statistics.
    data = client.get(f"{API}/analytics/overview?workspace_id={demo_wid}", headers=auth).json()
    assert data["totals"]["inspections"] == 3 and data["totals"]["potential_defects"] > 0
    assert all(p["name"].startswith("[DEMO]") for p in client.get(f"{API}/projects?workspace_id={demo_wid}", headers=auth).json()["items"])
    comparisons = client.get(f"{API}/comparisons?workspace_id={demo_wid}", headers=auth).json()["items"]
    assert comparisons[0]["metrics"]["alignment_status"] == "aligned"
    project = client.get(f"{API}/projects?workspace_id={demo_wid}&q=Surface", headers=auth).json()["items"][0]
    report = client.post(f"{API}/projects/{project['id']}/reports", headers=auth, json={}).json()
    from app.core.storage import get_storage
    from app.models import InspectionReport

    with new_session() as db:
        assert "DEMONSTRATION DATA" in pdf_text(get_storage().read(db.get(InspectionReport, report["id"]).storage_key))
    assert client.delete(f"{API}/demo", headers=auth).json()["message"] == "Demo data removed"
    assert all(not w["is_demo"] for w in client.get(f"{API}/workspaces", headers=auth).json())
    assert client.delete(f"{API}/demo", headers=auth).json()["message"] == "No demo data exists"


def test_settings_roundtrip_and_threshold_applied(client, auth):
    assert client.get(f"{API}/settings", headers=auth).json()["detector_confidence_threshold"] == 0.25
    saved = client.put(f"{API}/settings", headers=auth, json={"detector_confidence_threshold": 0.6, "overlay_opacity": 0.3, "default_category": "vehicle_damage"})
    assert saved.status_code == 200
    assert client.get(f"{API}/settings", headers=auth).json()["default_category"] == "vehicle_damage"
    assert client.put(f"{API}/settings", headers=auth, json={"detector_confidence_threshold": 5}).status_code == 422
    assert client.put(f"{API}/settings", headers=auth, json={"default_category": "nope"}).status_code == 422


def test_internal_errors_do_not_leak(client, auth):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as safe:
        with mock.patch("app.services.analytics.overview", side_effect=RuntimeError("password=hunter2 at C:/private")):
            response = safe.get(f"{API}/analytics/overview?workspace_id={workspace_id(client, auth)}", headers=auth)
    assert response.status_code == 500
    assert response.json() == {"detail": "An internal error occurred."}


def test_migrations_build_the_same_schema_as_the_models(tmp_path):
    """alembic upgrade creates every table, and autogenerate finds nothing further to change."""
    import subprocess
    import sys
    import os
    from pathlib import Path

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{(tmp_path / 'm.db').as_posix()}"}
    cwd = Path(__file__).resolve().parents[1]
    for command in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run([sys.executable, "-m", "alembic", *command], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
