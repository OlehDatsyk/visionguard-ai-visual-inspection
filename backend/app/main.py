"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from app import __version__
from app.api import auth, comparisons, insights, inspections
from app.core.config import get_settings
from app.database.session import get_engine
from app.services.jobs import Worker

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("visionguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = None
    if settings.run_worker_in_api and settings.environment != "test":
        worker = Worker()
        worker.start()
    log.info("VisionGuard AI %s started (%s)", __version__, settings.environment)
    yield
    if worker:
        worker.stop()
        worker.join(timeout=5)


app = FastAPI(
    title="VisionGuard AI API",
    version=__version__,
    description="AI-assisted visual inspection. Findings require human verification.",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # Authentication uses a bearer header, never cookies.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Reject oversized bodies early when the client declares a length.
    declared = request.headers.get("content-length")
    limit = (settings.max_upload_bytes + 1024 * 1024) * settings.max_files_per_upload
    if declared and declared.isdigit() and int(declared) > limit:
        return JSONResponse({"detail": "The request is too large."}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path not in ("/docs", "/redoc"):
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if settings.environment == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    # Only field and message: submitted values, such as passwords, are never echoed back.
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()
    ]
    return JSONResponse({"detail": "The submitted data is not valid.", "errors": errors}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse({"detail": "An internal error occurred."}, status_code=500)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def ready():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - details belong in the logs, not the response
        log.exception("Readiness check failed")
        return JSONResponse({"status": "unavailable", "database": "unreachable"}, status_code=503)
    return {"status": "ready", "database": "ok"}


for module in (auth, inspections, comparisons, insights):
    app.include_router(module.router, prefix="/api/v1")


# Policy for the web app's pages when the API serves them (single-service mode). Everything is same-origin.
FRONTEND_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
    "font-src 'self'; connect-src 'self'; frame-src blob:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
# Explicit types, so a host's own MIME registry can never break module scripts under nosniff.
FRONTEND_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
    ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
}


def mount_frontend(application: FastAPI, directory: str) -> bool:
    """Serve a production frontend build from the API, with client-side routes falling back to index.html."""
    root = Path(directory).resolve()
    index = root / "index.html"
    if not index.is_file():
        log.warning("FRONTEND_DIR is set but %s has no index.html; serving the API only", root)
        return False

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith(("api/", "health")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            media_type = FRONTEND_TYPES.get(candidate.suffix.lower(), "application/octet-stream")
            return FileResponse(candidate, media_type=media_type, headers={"Cache-Control": cache})
        return FileResponse(
            index, media_type=FRONTEND_TYPES[".html"],
            headers={"Cache-Control": "no-cache", "Content-Security-Policy": FRONTEND_CSP},
        )

    log.info("Serving the web app from %s", root)
    return True


if settings.frontend_dir:
    mount_frontend(app, settings.frontend_dir)
