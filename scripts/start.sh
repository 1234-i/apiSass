#!/usr/bin/env bash
set -euo pipefail
python -m app.db.init_db
exec uvicorn app.main:app --host 0.0.0.0 --port 8080
