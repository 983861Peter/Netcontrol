#!/bin/sh
set -e

echo "[entrypoint] Starting entrypoint script..."

# default to absolute DB path in /data if DATABASE_URL not provided
if [ -z "$DATABASE_URL" ]; then
  export DATABASE_URL="sqlite:////data/network_mgmt.db"
  echo "[entrypoint] DATABASE_URL not set; defaulting to $DATABASE_URL"
else
  echo "[entrypoint] Using DATABASE_URL=$DATABASE_URL"
fi

# ensure /data exists and is writable (for mounted persistent disk)
mkdir -p /data
chown -R 1000:1000 /data || true

# Run DB initializer (safe create_all script)
echo "[entrypoint] Running DB init (router_sim._init_db)..."
python -m router_sim._init_db

echo "[entrypoint] DB init complete. Starting application..."
exec uvicorn router_sim.router_api:app --host 0.0.0.0 --port 8080
