#!/usr/bin/env bash
# Installs the Seestar S50 Planner as a desktop application.
# Run once; after that it appears in your application launcher.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="seestar-planner"
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

# ── 1. Check / install PySide6 ────────────────────────────────────────────────
PYTHON="$SCRIPT_DIR/.venv/bin/python"
PIP="$SCRIPT_DIR/.venv/bin/pip"

if ! "$PYTHON" -c "import PySide6.QtWebEngineWidgets" 2>/dev/null; then
    echo "Installing PySide6 (this is a one-time ~250 MB download)…"
    "$PIP" install --quiet "PySide6>=6.6.0"
fi

# ── 2. Make launcher executable ───────────────────────────────────────────────
chmod +x "$SCRIPT_DIR/launch.sh"

# ── 3. Install icon ───────────────────────────────────────────────────────────
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/assets/icon.svg" "$ICON_DIR/$APP_ID.svg"

# ── 4. Write .desktop entry ───────────────────────────────────────────────────
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/$APP_ID.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Seestar S50 Planner
GenericName=Astronomy Planner
Comment=7-day weather & observation planner for the ZWO Seestar S50
Exec=$SCRIPT_DIR/launch.sh
Icon=$APP_ID
Terminal=false
Categories=Science;Astronomy;Education;
Keywords=astronomy;telescope;weather;seestar;observation;planning;
StartupNotify=true
StartupWMClass=Seestar S50 Planner
EOF
chmod +x "$APPS_DIR/$APP_ID.desktop"

# ── 5. Refresh desktop database ───────────────────────────────────────────────
update-desktop-database "$APPS_DIR"                         2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
kbuildsycoca6 --noincremental                               2>/dev/null || true  # KDE

echo ""
echo "Done!"
echo "  App entry : $APPS_DIR/$APP_ID.desktop"
echo "  Icon      : $ICON_DIR/$APP_ID.svg"
echo "  Launcher  : $SCRIPT_DIR/launch.sh"
echo ""
echo "The app now appears in your application menu as 'Seestar S50 Planner'."
echo "You can also run it directly:  $SCRIPT_DIR/launch.sh"
