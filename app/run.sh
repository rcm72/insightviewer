#!/usr/bin/env sh
set -e

# Default sensible values
: "${APP_ENV:=production}"
: "${PORT:=5000}"

if [ "$APP_ENV" = "production" ]; then
  echo "Starting Gunicorn (production)..."
  exec gunicorn \
    -w 2 \
    -k gthread \
    --threads 4 \
    --timeout 60 \
    -b 0.0.0.0:${PORT} \
    app:app
else
  echo "Starting Flask dev server with reload..."
  # FLASK_APP should be set via compose; fallback here just in case
  export FLASK_APP="${FLASK_APP:-app.py}"
  exec flask run --host=0.0.0.0 --port="${PORT}" --debug
fi
