# Single-service image: the API also serves the web app, so one web service runs everything.
# Used when a host such as Render builds this repository with Docker. See RENDER_DEPLOYMENT.md.

# 1. Build the frontend. "/" makes it call the API on the same origin, so no URL is baked in.
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-fund --no-audit
COPY frontend/ ./
ENV VITE_API_BASE_URL=/
RUN npm run build

# 2. The API, with the frontend build alongside it.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN adduser --system --group --home /app visionguard
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --disable-pip-version-check -r requirements.txt

COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
RUN python scripts/download_models.py --dir /app/model_weights
COPY --from=frontend /build/dist ./frontend_dist

RUN sed -i 's/\r$//' scripts/container_start.sh \
 && mkdir -p /data && chown -R visionguard:visionguard /data
USER visionguard

# Production by default. SECRET_KEY and DATABASE_URL come from the host; see scripts/container_start.sh.
# Files under /data are lost on restart unless a persistent disk is mounted there (then set STORAGE_PERSISTENT=true).
ENV ENVIRONMENT=production \
    STORAGE_BACKEND=local STORAGE_ROOT=/data STORAGE_PERSISTENT=false \
    MODEL_DIR=/app/model_weights FRONTEND_DIR=/app/frontend_dist \
    CORS_ORIGINS="" ONNX_THREADS=1 AI_PROVIDER=none
EXPOSE 8010
CMD ["sh", "scripts/container_start.sh"]
