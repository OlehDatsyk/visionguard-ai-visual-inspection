# Installing and using VisionGuard AI

This guide assumes you have never used the project before.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 or newer | 3.12 is the tested version |
| Node.js and npm | Node 20 or newer | Node 24 was used in testing |
| Disk space | About 1 GB | Packages and the 20 MB model |
| PostgreSQL | Optional | SQLite is used by default |
| Internet | First start only | To download packages and the model |

## Starting the application

### The simple way

- **Windows:** double-click `Start App.bat`.
- **macOS:** open Terminal in this folder and run `chmod +x "Start App.command"` once. Then double-click the file. If macOS blocks it, right-click it and choose **Open**.

The script checks your tools, creates `.env` and the virtual environment on first run, downloads the model, migrates the database, starts both servers and opens your browser. Press **Ctrl+C** in its window to stop. It never deletes your data.

Useful commands (use `python3` on macOS):

```bash
python scripts/start.py --check
```

```bash
python scripts/start.py --setup
```

### Manual installation

**1. Environment**

```bash
cp .env.example .env
```

For anything beyond local testing, replace `SECRET_KEY` with the output of:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**2. Backend** (in a terminal, from `backend/`)

```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on macOS and Linux, then:

```bash
pip install -r requirements.txt
```

```bash
python scripts/download_models.py
```

```bash
python -m alembic upgrade head
```

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

**3. Frontend** (in a second terminal, from `frontend/`)

```bash
npm ci
```

```bash
npm run dev
```

Open <http://127.0.0.1:5173>.

## Environment setup

Every setting is explained in [.env.example](.env.example).

| Setting | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | In production | Signs login tokens |
| `CORS_ORIGINS` | In production | Frontend addresses allowed to call the API |
| `DATABASE_URL` | No | Empty uses SQLite |
| `STORAGE_ROOT` | No | Where files are kept. Empty uses `storage/` |
| `AI_PROVIDER`, `AI_API_KEY` | No | Optional external AI |
| `VITE_API_BASE_URL` | For production builds | The API address the frontend calls |

## Database setup

SQLite needs no setup: the file is created at `storage/visionguard.db`.

To use PostgreSQL, create an empty database, set the URL in `.env`, and run migrations from `backend/`:

```text
DATABASE_URL=postgresql://user:password@localhost:5432/visionguard
```

```bash
python -m alembic upgrade head
```

Schema changes always go through Alembic. The app never creates tables on its own at startup.

## Using the application

### Create an inspection and upload images

1. Choose **New Inspection**.
2. Name the project and select a category. The panel lists which checks run and what the category **cannot** assess.
3. Drop JPEG, PNG or WebP images, up to 20 MB each. Preview them, add descriptions, and remove any you don't want.
4. Choose **Run analysis**. Files the server rejects are listed with the reason, and valid ones continue.

Analysis runs in the background, and the progress bar counts images actually finished.

### Read the results

The workspace groups results by what they mean:

| Group | Meaning |
|---|---|
| **Potential defects** | Unusual regions flagged by a heuristic. Unverified until reviewed |
| **Insufficient confidence** | Weak signals. Do not rely on these without looking |
| **Manual inspection needed** | Areas the analysis could not see, such as blown-out highlights |
| **Objects** | What the detector recognised. A detected object is not a defect |
| **Not assessed** | Checks this category cannot do reliably |

Viewer controls are zoom, fit to screen, reset to 100%, full screen, and original or processed view. You can toggle the object and finding overlays and adjust mask opacity. Click a region to open its finding, and drag to pan.

### Review findings

Select a finding, optionally add a note, then choose **Confirmed**, **False positive**, **Needs review** or **Resolved**. Each decision is kept in the finding's history and appears in reports and analytics. A project shows **Requires review** until its findings have decisions other than "needs review".

**Re-analyse** replaces findings and their review decisions, so it asks you to confirm first.

The **Defect Analysis** page lists findings across the whole workspace, with filters.

### Compare images

Open **Image Comparison**, choose a before and an after image, and select **Compare**. For useful results, shoot from the same position in the same light. Read any warnings first, because they tell you when the numbers may mostly reflect lighting or misalignment. See [IMAGE_COMPARISON_GUIDE.md](IMAGE_COMPARISON_GUIDE.md).

### Ask the assistant

The **Assistant** tab in a workspace, or the panel on a comparison, answers from the stored records. See [AI_ASSISTANT_GUIDE.md](AI_ASSISTANT_GUIDE.md).

### Generate reports

Choose **Generate report** in a workspace, add final notes, and generate. The report opens for preview, and the **Reports** page keeps previous ones for download.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| "Port 8010 is already used" | Another program holds the port. Stop it, or set `BACKEND_PORT` or `FRONTEND_PORT` in `.env` |
| "DLL load failed ... filename or extension is too long" on Windows | The folder path is too long for OpenCV. Move the project somewhere shorter, such as `C:\Projects\visionguard` |
| The server cannot be reached from the app | The backend isn't running, or `VITE_API_BASE_URL` points to the wrong address |
| The browser reports a CORS error | Add the frontend's exact address to `CORS_ORIGINS`, then restart the backend |
| Object detection shows as unavailable | Weights are missing. Run `python scripts/download_models.py` from `backend/` |
| "SECRET_KEY must be a unique value" | Production mode refuses weak secrets. Set a long random value |
| "Surface heuristics were skipped" | The image is a complex scene. Photograph the surface close up |
| No findings on an obvious defect | The heuristics have limits, and low-contrast marks can be missed. Inspect manually |
| Too many false findings | Labels, seams and patterns also look unusual. Mark them as false positives, or crop more tightly |
| `npm run build` asks for `VITE_API_BASE_URL` | Production builds require it. `npm run dev` does not |
| A package fails to install on a very new Python | Use Python 3.12, the tested version |
