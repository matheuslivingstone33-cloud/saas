#!/bin/sh
set -e
echo "[start-api] aguardando banco e aplicando migrations..."
alembic upgrade head
if [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "[start-api] populando seed..."
  python -m app.db.seed
fi
echo "[start-api] subindo API em 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
