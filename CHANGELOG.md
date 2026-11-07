# Changelog

## 1.0.1: single-service Docker deployment

### Fixed

- Render failed with `open Dockerfile: no such file or directory` when the repository was deployed as a Docker web service, because there was no `Dockerfile` at the repository root.
- The container stopped with `mkdir: cannot create directory ''` when the host defined `STORAGE_ROOT` with a blank value. Blank variables now fall back to their defaults, both in the start script and in the app's settings.

### Added

- A root `Dockerfile` that builds the frontend and serves it from the API, so one web service runs the whole app with no URLs to configure.
- `FRONTEND_DIR` setting: the API serves a production frontend build, with client-side routes, security headers and long caching for hashed assets.
- `VITE_API_BASE_URL=/` builds the frontend to call the API on the same origin.
- The container start script uses a temporary random `SECRET_KEY`, with a warning, when none is set, instead of failing to start.
- `.dockerignore`, so local secrets, databases, uploads and dependencies never enter an image.

## 1.0.0: initial release

The first version of VisionGuard AI. No earlier releases exist.

### Added

- Object detection with YOLOX-Tiny through ONNX Runtime
- Potential defect heuristics: crack-like, scratch-like, surface anomaly, discolouration and corrosion-like
- Manual inspection areas from exposure clipping, and region outlines with adjustable opacity
- Inspection workspace with an image viewer and human review history
- Before-and-after comparison with alignment, SSIM and a difference heatmap
- Database-backed background jobs with retries and crash recovery
- Inspection assistant answering from stored records, with optional Claude integration
- PDF reports, a dashboard and analytics based on stored records
- Accounts, workspaces, per-user isolation and upload validation
- Demo mode in an isolated workspace
- Alembic migrations, PostgreSQL and SQLite support, and local and S3 storage backends
- Startup scripts, a Render Blueprint, and Docker files (the Docker files are untested)
