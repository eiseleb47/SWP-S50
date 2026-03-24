#!/usr/bin/env bash
# Removes the Seestar S50 Planner desktop integration.
# Does NOT delete the project directory or the venv.
set -euo pipefail

APP_ID="seestar-planner"
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

REMOVED=0

# ── .desktop entry ────────────────────────────────────────────────────────────
if [ -f "$APPS_DIR/$APP_ID.desktop" ]; then
    rm "$APPS_DIR/$APP_ID.desktop"
    echo "Removed: $APPS_DIR/$APP_ID.desktop"
    REMOVED=1
else
    echo "Not found: $APPS_DIR/$APP_ID.desktop (already removed?)"
fi

# ── Icon ──────────────────────────────────────────────────────────────────────
if [ -f "$ICON_DIR/$APP_ID.svg" ]; then
    rm "$ICON_DIR/$APP_ID.svg"
    echo "Removed: $ICON_DIR/$APP_ID.svg"
    REMOVED=1
else
    echo "Not found: $ICON_DIR/$APP_ID.svg (already removed?)"
fi

# ── Refresh desktop database ──────────────────────────────────────────────────
if [ "$REMOVED" -eq 1 ]; then
    update-desktop-database "$APPS_DIR"                         2>/dev/null || true
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    kbuildsycoca6 --noincremental                               2>/dev/null || true  # KDE
fi

echo ""
echo "Desktop integration removed."
echo "The project files and virtual environment are untouched."
echo "To reinstall, run: ./install-desktop.sh"
