#!/usr/bin/env bash
# Link Chassie's memory plugin into Hermes, so the repo copy is the one Hermes loads.
# An existing plugin folder is moved aside first (chassie.bak-<time>).
set -euo pipefail
source_dir="$(cd "$(dirname "$0")/.." && pwd)/hermes_plugin/chassie"
target="${HERMES_HOME:-$HOME/.hermes}/plugins/chassie"
mkdir -p "$(dirname "$target")"
if [ -L "$target" ]; then
  rm "$target"
elif [ -e "$target" ]; then
  mv "$target" "$target.bak-$(date +%Y%m%d-%H%M%S)"
fi
ln -s "$source_dir" "$target"
echo "Linked $target -> $source_dir"
echo "Set vault_path in ${HERMES_HOME:-$HOME/.hermes}/chassie.json, then restart Hermes (systemctl --user restart hermes-gateway)."
