#!/bin/sh
set -e
echo "[start-worker] subindo worker RQ"
exec python -m app.workers.worker
