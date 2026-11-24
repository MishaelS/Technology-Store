#!/bin/sh
set -e

# 1. Create/upgrade tables
alembic upgrade head
# 2. Load test data (only if the database is empty)
python -m app.seed
# 3. Start the API (--reload restarts the server on code changes)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
