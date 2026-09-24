#!/bin/sh
set -e

# ── MimicGate Application Startup Script (executed by jlesage/baseimage-gui) ──

echo "============================================================"
echo "  MimicGate Gateway — Starting Backend Server & Browser Session"
echo "============================================================"

# Navigate to application root
cd /app

export PATH="/opt/venv/bin:$PATH"
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1

# Run the FastAPI server (which manages Patchright/Chromium lifecycle)
exec /opt/venv/bin/python -m src.api.server
