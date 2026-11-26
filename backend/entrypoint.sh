#!/bin/sh
set -e

# 1. Create/upgrade tables
alembic upgrade head
# 2. Load test data (only if the database is empty)
python -m app.seed
# 3. Start the API. Development: --reload restarts it on code changes.
#    Server (RELOAD=0, docker-compose.prod.yml): no reload; addresses of visitors come from the proxy headers.
#    One worker on purpose: the auto backup task must run once (app/main.py).
if [ "${RELOAD:-1}" = "1" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
fi
