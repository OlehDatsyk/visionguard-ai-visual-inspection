# VisionGuard AI v1.0.0: Initial Release

VisionGuard AI is an AI-assisted visual inspection platform. It detects objects, flags visually unusual regions for review, compares before-and-after images, and produces PDF reports recording human decisions.

## Main functionality

- **Inspection management:** workspaces, projects, multi-image upload, search, filters, and a review history for every finding
- **Computer vision:** YOLOX-Tiny object detection on CPU, OpenCV heuristics for crack-like and scratch-like marks, surface anomalies, discolouration and corrosion-like patterns, with region outlines
- **Image comparison:** side-by-side, overlay and difference views, with ORB and RANSAC alignment, SSIM and warnings about lighting and alignment
- **Reporting:** PDF reports with highlighted regions, confidence, review decisions and limitations, plus analytics from stored records
- **Assistant:** answers from stored records with no external service, with optional Claude integration
- **Demo mode:** an isolated workspace analysed by the real pipeline

## Technology stack

React, TypeScript, Vite, Tailwind CSS, FastAPI, SQLAlchemy, Alembic, PostgreSQL or SQLite, OpenCV, ONNX Runtime and ReportLab.

## Installation

You need Python 3.11 or newer (3.12 tested) and Node.js 20 or newer. On Windows run `Start App.bat`. On macOS run `chmod +x "Start App.command"`, then open it. See [INSTRUCTION.md](../INSTRUCTION.md).

## Known limitations

- Not certified for safety-critical, medical, structural or regulatory inspections. Human verification is required.
- Defect findings are uncalibrated heuristics, tuned on generated samples. **No accuracy figures exist.**
- It cannot assess dents, missing components, structural integrity or internal damage.
- The object detector knows only 80 COCO categories.
- macOS startup, Docker, real S3 and the live Anthropic API, and live Render deployment have not been tested. See [TESTING.md](../TESTING.md).
