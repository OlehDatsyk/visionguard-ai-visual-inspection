# Backend image for local Docker Compose use. Render uses its native Python runtime instead (see render.yaml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN adduser --system --group --home /app visionguard
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
RUN python scripts/download_models.py --dir /app/model_weights

RUN mkdir -p /data && chown -R visionguard:visionguard /data
USER visionguard

ENV STORAGE_ROOT=/data MODEL_DIR=/app/model_weights
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)"
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8010 --timeout-graceful-shutdown 20"]
