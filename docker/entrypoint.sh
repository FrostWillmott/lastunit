#!/bin/sh
# Run migrations and the seed before the app; `exec "$@"` then replaces this
# process with the CMD (uvicorn). DATABASE_URL comes from the compose environment.
set -e
alembic upgrade head
python -m app.seed
exec "$@"
