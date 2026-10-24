#!/bin/sh
set -e

# Allow one-off commands, e.g. `docker compose run --rm backend pytest`.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Apply database migrations before accepting traffic (idempotent).
alembic upgrade head

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${UVICORN_WORKERS:-1}" \
  --timeout-keep-alive 5 \
  --no-access-log
