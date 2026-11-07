"""Deterministic assistant. It answers from stored records with no external service."""
from collections import Counter

HELP = (
    "I answer from the stored inspection records. You can ask: what objects were detected, which areas need "
    "further inspection, what a finding means (for example \"explain F-1A2B-01\"), which findings have not been "
    "reviewed, for a summary of this inspection, what differs between compared images, or how to prepare a report."
)


def _projects(context: dict) -> list[dict]:
    if context["scope"] == "project":
        return [context]
    return context.get("projects", [])


def _images(context: dict) -> list[tuple[str, dict]]:
    return [(p["project"]["name"], image) for p in _projects(context) for image in p["images"]]


def _comparisons(context: dict) -> list[dict]:
    if context["scope"] == "comparison":
        return [context["comparison"]]
    return [c for p in _projects(context) for c in p["comparisons"]]


def _pretty(value: str) -> str:
    return value.replace("_", " ")


def _objects(context: dict) -> str:
    counts: Counter = Counter()
    lines = []
    for _, image in _images(context):
        for obj in image["objects"]:
            counts[obj["label"]] += 1
        if image["objects"]:
            top = sorted(image["objects"], key=lambda o: -o["confidence"])[:5]
            listed = ", ".join(f"{o['label']} ({o['confidence']:.2f}, {o['band']})" for o in top)
            lines.append(f"- {image['filename']}: {listed}")
    if not counts:
        analysed = any(image["status"] == "analysed" for _, image in _images(context))
        return "No objects are recorded." if analysed else "No objects are recorded because no image has been analysed yet."
    total = ", ".join(f"{label} x{n}" for label, n in counts.most_common())
    return (
        f"Recorded detections: {total}.\n" + "\n".join(lines) +
        "\nThe numbers are the detector's own confidence scores, not probabilities of being correct."
    )


def _further(context: dict) -> str:
    lines = []
    for _, image in _images(context):
        for f in image["findings"]:
            if f["type"] == "manual_inspection":
                lines.append(f"- {f['id']} in {image['filename']}, at {f['box_xywh']}: {f['explanation']}")
            elif f["review_status"] in ("unreviewed", "needs_review"):
                lines.append(
                    f"- {f['id']} in {image['filename']}, at {f['box_xywh']}: possible {_pretty(f['category'])}, "
                    f"{f['band']} band, score {f['score']:.2f}, status {_pretty(f['review_status'])}"
                )
        for note in image["analysis_notes"]:
            lines.append(f"- {image['filename']}: {note}")
    if not lines:
        return "The records list no areas needing further inspection. That does not prove there are no defects."
    return "These records call for a person to look:\n" + "\n".join(lines[:30])


def _unreviewed(context: dict) -> str:
    lines = [
        f"- {f['id']} ({_pretty(f['category'])}) in {image['filename']}"
        for _, image in _images(context) for f in image["findings"] if f["review_status"] == "unreviewed"
    ]
    if not lines:
        return "All recorded findings have a review decision, or there are no findings yet."
    return f"{len(lines)} findings have not been reviewed:\n" + "\n".join(lines[:40])


def _explain(context: dict, finding_id: str) -> str:
    for _, image in _images(context):
        for f in image["findings"]:
            if f["id"].upper() == finding_id.upper():
                return (
                    f"{f['id']} in {image['filename']} is recorded as {_pretty(f['category'])} "
                    f"({_pretty(f['type'])}). Score {f['score']:.2f} ({_pretty(f['score_type'])}), band {f['band']}, "
                    f"location {f['box_xywh']} (x, y, width, height in pixels). Method: {f['method']}.\n{f['explanation']}\n"
                    f"Review status: {_pretty(f['review_status'])}."
                )
    return f"I can't find a finding with the ID {finding_id} in these records."


def _difference(context: dict) -> str:
    comparisons = _comparisons(context)
    if not comparisons:
        return "No image comparison is recorded for this scope."
    lines = []
    for c in comparisons[:5]:
        if c["status"] != "completed":
            lines.append(f"- {c['name']}: status {c['status']}, no metrics yet.")
            continue
        m = c["metrics"]
        lines.append(
            f"- {c['name']} ({c['before']} to {c['after']}): SSIM {m['ssim']}, changed area {m['changed_area_pct']}%, "
            f"{c['region_count']} changed regions, alignment {_pretty(m['alignment_status'])}."
        )
        lines.extend(f"  Warning: {w}" for w in c["warnings"])
    lines.append("A difference is not proof of physical change. Lighting, angle and compression can cause it too.")
    return "\n".join(lines)


def _summary(context: dict) -> str:
    projects = _projects(context)
    if context["scope"] == "comparison":
        return _difference(context)
    if not projects:
        return "No inspection records exist in this workspace yet."
    parts = []
    for p in projects[:10]:
        images = p["images"]
        findings = [f for image in images for f in image["findings"]]
        defects = [f for f in findings if f["type"] == "potential_defect"]
        categories = Counter(_pretty(f["category"]) for f in defects)
        reviewed = sum(1 for f in findings if f["review_status"] != "unreviewed")
        objects = sum(len(image["objects"]) for image in images)
        analysed = sum(1 for image in images if image["status"] == "analysed")
        demo = " [demonstration data]" if p["project"]["is_demo_data"] else ""
        text = (
            f"{p['project']['name']}{demo} ({p['project']['category']}, status {_pretty(p['project']['status'])}): "
            f"{analysed} of {len(images)} images analysed, {objects} objects detected, {len(defects)} potential defects"
        )
        if categories:
            text += " (" + ", ".join(f"{k}: {v}" for k, v in categories.most_common()) + ")"
        text += f", {reviewed} of {len(findings)} findings reviewed."
        parts.append(text)
    parts.append("Potential defects remain unverified until a person reviews them.")
    return "\n".join(parts)


def _report(context: dict) -> str:
    if context["scope"] != "project":
        return "Open a project, then use Generate report in its workspace, or use the Reports page."
    reports = context["reports"]
    existing = f" {len(reports)} report(s) already exist for it." if reports else ""
    return (
        "To prepare a report, choose Generate report in this inspection. The PDF uses these records:\n"
        + _summary(context) + existing
    )


def answer(context: dict, question: str) -> str:
    import re

    q = question.lower()
    match = re.search(r"\bf-[0-9a-z]{4}-\d{2}\b", q)
    if match:
        return _explain(context, match.group(0))
    if any(w in q for w in ("not been reviewed", "unreviewed", "not reviewed", "haven't been reviewed", "pending review")):
        return _unreviewed(context)
    if any(w in q for w in ("difference", "differ", "compare", "comparison", "changed", "ssim", "before and after")):
        return _difference(context)
    if any(w in q for w in ("further inspection", "manual", "attention", "which areas", "where should", "look at")):
        return _further(context)
    if any(w in q for w in ("object", "detected", "what is in", "what's in", "recogni")):
        return _objects(context)
    if "report" in q:
        return _report(context)
    if any(w in q for w in ("summar", "overview", "status", "finding", "defect", "result", "how many")):
        return _summary(context)
    if any(w in q for w in ("mean", "confidence", "score")):
        return (
            "Bands summarise scores. Detector confidence is the model's internal score, not a probability of being "
            "correct. Heuristic scores measure visual unusualness and are capped at the medium band because they are "
            "uncalibrated. Ask about a specific finding ID for details."
        )
    return "The records I can read don't answer that directly. " + HELP
