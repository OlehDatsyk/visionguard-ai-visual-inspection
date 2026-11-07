#!/bin/sh
# Start command for the single-service image built by the root Dockerfile.
set -e

if [ -z "$SECRET_KEY" ]; then
  # Safe fallback rather than a crash: a random key that lives only as long as this container.
  # Everyone is signed out on each restart. Set SECRET_KEY in the host's environment to avoid that.
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export SECRET_KEY
  echo "WARNING: SECRET_KEY is not set. Using a temporary random key; sign-ins end when the container restarts."
fi

if [ -z "$DATABASE_URL" ]; then
  echo "WARNING: DATABASE_URL is not set. Using SQLite in $STORAGE_ROOT, which is lost if that folder is not persistent."
fi

mkdir -p "$STORAGE_ROOT"
python -m alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8010}" --timeout-graceful-shutdown 20
