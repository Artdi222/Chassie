#!/usr/bin/env bash
# Add Chassie to the application menu (~/.local/share/applications), pointing at this folder.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
target="${XDG_DATA_HOME:-$HOME/.local/share}/applications/chassie.desktop"
mkdir -p "$(dirname "$target")"
cat > "$target" <<ENTRY
[Desktop Entry]
Version=1.0
Type=Application
Name=Chassie
Comment=Local Live2D companion
Exec="$root/.venv/bin/python" "$root/launch.py"
Path=$root
Icon=$root/ui/public/chassie-icon.png
Terminal=false
Categories=Utility;
StartupWMClass=chassie-overlay
ENTRY
echo "Added $target"
