#!/usr/bin/env python3
"""Generate the endpoint reference in API_DOCUMENTATION.md from the real OpenAPI schema.

Run from the repository root with the backend's virtual environment:
    backend/.venv/Scripts/python scripts/generate_api_docs.py
Generating it means the document cannot list an endpoint that does not exist.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "documentation-generation-only-0123456789")

from app.main import app  # noqa: E402

MARKER = "<!-- ENDPOINTS -->"
schema = app.openapi()
ERRORS = {
    "400": "Bad request", "401": "Not authenticated", "404": "Not found, or owned by another user",
    "409": "Conflict with the current state", "413": "Too large", "422": "Validation failed", "429": "Rate limited",
}


def type_name(node: dict | None) -> str:
    if not node:
        return ""
    if "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    if node.get("type") == "array":
        return f"list of {type_name(node.get('items'))}"
    for key in ("anyOf", "oneOf"):
        if key in node:
            return " or ".join(t for t in (type_name(n) for n in node[key]) if t and t != "null")
    return node.get("type", "")


def body_of(content: dict | None) -> str:
    for media, item in (content or {}).items():
        name = type_name(item.get("schema"))
        if media == "application/json":
            return name or "JSON"
        if media.startswith("multipart"):
            return "multipart form"
    return ""


groups: dict[str, list[str]] = {}
for path, methods in schema["paths"].items():
    for method, op in methods.items():
        params = [
            f"`{p['name']}`" + ("" if p.get("required") else " (optional)")
            for p in op.get("parameters", []) if p["in"] == "query"
        ]
        request = body_of(op.get("requestBody", {}).get("content"))
        success = next((c for c in op["responses"] if c.startswith("2")), "200")
        response = body_of(op["responses"][success].get("content")) or ("none" if success == "204" else "file or JSON")
        response = re.sub(r"^Page_(\w+)_$", lambda m: f"Page of {m.group(1)}", response)
        if path.endswith("/file"):
            response = "binary file"
        elif response == "JSON" and path == "/api/v1/projects/{project_id}/images":
            response = "UploadResult"
        secured = "Yes" if op.get("security") else "No"
        inputs = ", ".join(filter(None, [", ".join(params), f"body: {request}" if request else ""])) or "None"
        row = f"| `{method.upper()}` | `{path}` | {op.get('summary', '')} | {secured} | {inputs} | {success}: {response} |"
        groups.setdefault(op.get("tags", ["Other"])[0], []).append(row)

lines = [MARKER, ""]
for tag, rows in groups.items():
    lines += [f"### {tag}", "", "| Method | Path | Purpose | Auth | Input | Success |", "|---|---|---|---|---|---|", *rows, ""]

target = ROOT / "API_DOCUMENTATION.md"
text = target.read_text(encoding="utf-8")
head = text.split(MARKER)[0]
target.write_text(head + "\n".join(lines), encoding="utf-8")
print(f"Documented {sum(len(r) for r in groups.values())} operations")
