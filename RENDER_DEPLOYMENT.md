# Deploying to Render

**Status: prepared and verified locally. It has never been deployed to Render.** Live behaviour is untested, and the Blueprint has not been validated by Render itself.

Render facts here were checked against its documentation on 2026-11-07. Plans change, so check [render.com/pricing](https://render.com/pricing) before you create anything.

## Two ways to deploy

| | Blueprint (`render.yaml`) | One Docker service (root `Dockerfile`) |
|---|---|---|
| Created with | **New > Blueprint** | **New > Web Service**, which picks Docker automatically |
| Services | API, frontend and PostgreSQL | One service runs the API and the web app |
| URLs to enter | `CORS_ORIGINS` and `VITE_API_BASE_URL` | None, because the app and API share one address |
| Database | Free PostgreSQL, expires after 30 days | SQLite inside the container, lost on restart, unless you add `DATABASE_URL` |
| Tested | Render's commands run locally | Start script and app run locally. The Docker build itself was not run, because Docker was unavailable |

### One Docker service

If Render reported `open Dockerfile: no such file or directory`, the service was created as Docker before the root `Dockerfile` existed. Push this version, then:

1. Open the service, then **Settings**. **Root Directory** must be empty, and **Dockerfile Path** must be `./Dockerfile`.
2. Under **Environment**, add `SECRET_KEY`, set to a random value of at least 32 characters. Without it the app still starts, but uses a temporary key, so everyone is signed out on every restart.
3. Optional: add `DATABASE_URL`, set to a PostgreSQL connection string such as the **Internal Database URL** of a Render PostgreSQL database in the same region, so accounts and records survive restarts. Uploaded files are still lost on restart without a disk.
4. Choose **Manual Deploy > Deploy latest commit**. The first build takes several minutes.
5. Open the service's `.onrender.com` address and register. `/health/ready` should return `{"status":"ready","database":"ok"}`.

The image runs in production mode, serves the API under `/api/v1`, and serves the web app with the same security headers as the Blueprint's static site. Don't set `VITE_API_BASE_URL` or `CORS_ORIGINS` for this service. In this mode `/docs` shows the web app's "not found" page instead of returning 404.

The rest of this guide describes the Blueprint.

## Architecture

| Service | Render type | Name |
|---|---|---|
| Frontend | Static Site | `visionguard-frontend` |
| Backend and job worker | Python Web Service | `visionguard-api` |
| Database | PostgreSQL | `visionguard-database` |
| Files | Persistent disk or S3-compatible storage | Not created by default |

No separate worker or Redis is defined, because the job queue runs in the API process using PostgreSQL. A disk can attach to only one service, so a separate worker couldn't reach the files anyway.

## Choose a plan first

`render.yaml` uses **free plans** so that applying it never creates a charge. Free is for demonstrations only:

| Limit | Effect |
|---|---|
| No persistent disk on free web services | **Uploads and reports are lost on restart, redeploy or sleep, while the database keeps pointing to them.** The app shows a warning banner |
| Sleeps after 15 minutes without traffic | The next visit takes about a minute |
| Free PostgreSQL expires after 30 days | There are 14 days to upgrade before deletion. 1 GB. One per workspace |
| 750 free instance hours a month | Shared across the workspace |

For real use, see [Moving to persistent storage](#moving-to-persistent-storage), which is paid.

### Resource estimate

Measured locally on Windows, with PostgreSQL, in production mode:

| Measure | Result |
|---|---|
| Backend memory after the browser test | About 320 MB |
| Peak backend memory | 401 MB with `ONNX_THREADS=1`, and 403 to 445 MB with `ONNX_THREADS=2`, in separate runs |
| Per-image analysis on a 16-thread desktop | About 0.2 to 0.9 seconds |

A 512 MB instance leaves little headroom, and these are Windows figures, so Linux will differ. Large or concurrent images could hit that limit, and the instance would restart. **CPU on small plans is far lower than on the test machine, so expect much slower analysis.** Render does not provide a GPU, and none is needed. `1c-2g` is a safer starting point for real use. These are estimates, and were not measured on Render.

## Prepare locally

From `backend/`, with a virtual environment active:

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

From `frontend/`:

```bash
npm ci
```

```bash
npm test
```

```bash
VITE_API_BASE_URL=https://visionguard-api.onrender.com npm run build
```

## Deploy

Steps 1 to 6 happen in the Render Dashboard.

1. **Account:** create one at [dashboard.render.com](https://dashboard.render.com).
2. **Connect GitHub:** push this repository, then link your GitHub account and grant access to the repository.
3. **Create the Blueprint:** choose **New > Blueprint** and select the repository. Render reads `render.yaml` and lists the resources.
4. **Check the resources:** confirm that all plans say free, unless you changed them. Render may rename a service if the name is taken, so note the final URLs.
5. **Enter the prompted values:**

| Variable | Service | Value |
|---|---|---|
| `CORS_ORIGINS` | `visionguard-api` | `https://visionguard-frontend.onrender.com` |
| `VITE_API_BASE_URL` | `visionguard-frontend` | `https://visionguard-api.onrender.com` |
| `AI_API_KEY` | `visionguard-api` | Empty, unless you enable external AI |

6. **Apply.** PostgreSQL is created from the Blueprint, `SECRET_KEY` is generated, and `DATABASE_URL` is linked. The first build downloads packages and the model.
7. **Correct the URLs if they differ.** If Render assigned other hostnames, update both variables. `CORS_ORIGINS` needs a backend restart. `VITE_API_BASE_URL` is compiled in, so it needs a **new frontend deploy**. The default frontend CSP allows `https://*.onrender.com`. If you use a custom API domain, add it to `connect-src` in `render.yaml`.

## Check the deployment

```bash
curl https://visionguard-api.onrender.com/health
```

```bash
curl https://visionguard-api.onrender.com/health/ready
```

Expect `{"status":"ok"}` and `{"status":"ready","database":"ok"}`. Then, in the browser:

1. Open the frontend and refresh on a deep link such as `/analytics`.
2. Register, upload an image, and wait for the analysis to finish.
3. Check the **Model Information** page says YOLOX-Tiny is available.
4. Generate and download a report.
5. Confirm that `/docs` on the API returns 404.

## Environment variables

Configured on the service in Render, under **Environment**.

| Variable | Service | Source | Required |
|---|---|---|---|
| `DATABASE_URL` | API | Linked from the database | Yes |
| `SECRET_KEY` | API | Generated | Yes |
| `ENVIRONMENT` | API | `production` | Yes |
| `CORS_ORIGINS` | API | Prompted | Yes |
| `PYTHON_VERSION` | API | `3.12.10` | Yes |
| `STORAGE_BACKEND`, `STORAGE_ROOT`, `STORAGE_PERSISTENT` | API | Blueprint | Yes |
| `ONNX_THREADS`, `LOG_LEVEL` | API | Blueprint | No |
| `AI_PROVIDER`, `AI_API_KEY` | API | Blueprint, prompted | No |
| `VITE_API_BASE_URL` | Frontend | Prompted | Yes, public |

All other settings have defaults, listed in [.env.example](.env.example). Never put secrets in `render.yaml`, GitHub or any `VITE_` variable.

## Commands

| | Value |
|---|---|
| API root directory | `backend` |
| API build | `pip install --disable-pip-version-check -r requirements.txt && python scripts/download_models.py` |
| API start | `python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --timeout-graceful-shutdown 20` |
| API health check | `/health`. Lightweight, it doesn't load the model |
| Frontend root directory | `frontend` |
| Frontend build | `npm ci --include=dev --no-fund --no-audit && npm run build` |
| Frontend publish directory | `dist` |

## Database migrations

Migrations run automatically on every start, because `preDeployCommand` is paid-only. That is safe for one instance. If you scale up, move them to a `preDeployCommand`. To run them by hand from the service's **Shell** tab, if your plan offers it:

```bash
python -m alembic upgrade head
```

If the database is unavailable at startup, the migration fails, Render reports a failed deploy, and the previous version stays live.

## Moving to persistent storage

This **costs money**. Check current prices first.

### Option A: persistent disk

Simplest. In `render.yaml`, change the API service:

```yaml
    plan: 1c-2g
    disk:
      name: visionguard-files
      mountPath: /var/data
      sizeGB: 10
```

And change these variables:

```yaml
      - key: STORAGE_ROOT
        value: /var/data/visionguard
      - key: STORAGE_PERSISTENT
        value: "true"
```

Trade-offs, from Render's documentation:

- Only a single instance can use a disk, so the service can't scale horizontally.
- Deploys have a few seconds of downtime, because zero-downtime deploys are disabled.
- Build and pre-deploy commands can't access the disk.

### Option B: S3-compatible storage

Set `STORAGE_BACKEND=s3`, the `S3_*` variables and `STORAGE_PERSISTENT=true`. Add `-r requirements-s3.txt` to the build. Objects stay private, and all reads go through the authorised API, so keep the bucket non-public. This option allows multiple instances, but in-process rate limiting isn't shared between them. The adapter has been tested only against a stubbed client, so test it with your provider first.

### Paid database

Change `plan: free` under `databases` to a paid ID such as `0.5c-1g`. Free databases expire. Back up before changing anything.

## Logs

Open a service, then **Logs**. Application logs go to standard output. Passwords, tokens and file contents are not logged. Failed jobs log the full error on the server, and users see a generic message.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `open Dockerfile: no such file or directory` | The service is Docker, and the repository has no root `Dockerfile` or **Root Directory** is set. Push version 1.0.1 or later and clear Root Directory, or use the Blueprint |
| `mkdir: cannot create directory ''` | A variable such as `STORAGE_ROOT` is defined but blank. Fixed in 1.0.1. Delete blank variables under Environment |
| Docker service logs `SECRET_KEY is not set` | Add `SECRET_KEY` under Environment, or everyone is signed out on each restart |
| Build fails with `VITE_API_BASE_URL must be set` | The prompted value is empty. Set it and redeploy the frontend |
| Build fails with `must use HTTPS` | The value starts with `http://` |
| `vite: not found` during the frontend build | Dev dependencies were skipped. Check that the build uses `--include=dev` |
| API fails with `SECRET_KEY must be ...` | Missing or short value. Set one in the Environment tab |
| API fails with `CORS_ORIGINS must list ...` | The value is a wildcard |
| Browser reports a CORS error | `CORS_ORIGINS` doesn't exactly match the frontend, including `https://` and without a trailing path |
| Requests blocked by Content-Security-Policy | A custom API domain isn't in `connect-src` |
| Blank page or 404 on refresh | The rewrite route is missing from the static site |
| Instance restarts during analysis | Probably out of memory. Use a larger plan, or lower `MAX_IMAGE_PIXELS` |
| "Stored file not found", or images fail to load | The free plan's files were lost in a restart. See persistent storage |
| Detection unavailable | The model download failed in the build. Check the build log and redeploy |
| Database connection errors after 30 days | The free database expired |

## Updating

Push to the linked branch. Render rebuilds automatically. If you change `render.yaml`, the Blueprint syncs its contents. Variables declared with `sync: false` are only prompted once, so later changes are made in the dashboard.

## Rollback

Open the service's **Events** page, find an earlier successful deploy, and choose rollback. Rolling back code does **not** undo database migrations. If a release changes the schema, plan a compatible rollback, and take a backup first. Check what backups your database plan includes.

## Costs

| Resource | Default Blueprint | For real use |
|---|---|---|
| Static site | Free, subject to bandwidth and build limits | Free |
| Web service | Free | Paid plan, required for a disk |
| PostgreSQL | Free, expires after 30 days | Paid plan |
| Disk | None | Paid per GB |

I couldn't retrieve current prices from Render's pricing page, so none are quoted here.

## Local verification of these commands

Render's exact start and frontend build commands were run locally on PostgreSQL 16, with `NODE_ENV=production` and free-plan settings. The only change was binding to `127.0.0.1` instead of `0.0.0.0`. The full browser test then passed. See [TESTING.md](TESTING.md).

## Status

| Item | Status |
|---|---|
| `render.yaml`, build and start commands | Ready for deployment |
| Production-mode backend on PostgreSQL | Verified locally |
| Production frontend build, routing and CORS | Verified locally |
| Prompted URLs and CORS origins | Requires Render configuration |
| Persistent files, paid database | Requires paid infrastructure |
| Single-service mode: start script, API serving the web app, CSP | Verified locally |
| Root `Dockerfile` build | Not tested, because Docker was unavailable |
| Live deployment, HTTPS, Render performance | Not tested |
