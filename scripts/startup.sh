#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

echo "[STARTUP] Startup script initiated."

# --- Validation Step ---
# Verify that Alembic migration scripts actually exist before trying to run them.
# This prevents silent failures where a misconfigured Docker build leads to an empty versions directory.
MIGRATION_DIR="alembic/versions"
if [ -d "$MIGRATION_DIR" ] && [ -n "$(ls -A $MIGRATION_DIR/*.py 2>/dev/null)" ]; then
    echo "[STARTUP] Found migration scripts in $MIGRATION_DIR."
else
    echo "[STARTUP] FATAL: No migration scripts found in $MIGRATION_DIR. Aborting." >&2
    exit 1
fi

# Run database migrations
echo "[STARTUP] Running database migrations..."
alembic upgrade head
echo "[STARTUP] Database migrations complete."

# Start the application server
# Use exec to replace the shell process with the application process.
# This allows the app to receive signals directly from the container runtime (like  for graceful shutdown).
# We run the module directly to use the centralized server configuration in src/main.py.
echo "[STARTUP] Starting application server..."
exec python -m src.main
