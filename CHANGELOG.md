# Changelog

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
