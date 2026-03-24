#!/usr/bin/env bash
# Seestar S50 Observation Planner — desktop launcher
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/gui.py" "$@"
