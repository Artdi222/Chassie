#!/usr/bin/env bash
# One-time (and re-runnable) Chassie setup for Linux x86_64.
# Creates .venv with Python 3.12, installs packages, downloads the voice, vision,
# speaker and memory models into .chassie/, and links the memory plugin into Hermes.
# Finished parts are skipped, so running it again only does what is missing.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"
summary=()
ok() { summary+=("OK $1"); echo "OK $1"; }
bad() { summary+=("!! $1"); echo "!! $1"; }

echo "== Chassie setup in $ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "!! uv was not found. Install it, open a new terminal, then run this again:"
  echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ ! -x "$PY" ]; then
  uv venv --python 3.12 .venv || { echo "!! Could not create .venv with Python 3.12"; exit 1; }
fi
ok "Python environment (.venv, $("$PY" -c 'import sys;print(sys.version.split()[0])'))"

echo "== Installing Python packages (a few minutes, about 3 GB the first time)"
if uv pip install --python "$PY" -r requirements.txt -r requirements-overlay.txt; then
  # faster-whisper pulls the CPU onnxruntime; it must not shadow onnxruntime-gpu.
  if uv pip show --python "$PY" onnxruntime >/dev/null 2>&1; then
    uv pip uninstall --python "$PY" onnxruntime >/dev/null 2>&1
    uv pip install --python "$PY" --reinstall "onnxruntime-gpu[cuda]==1.26.0" >/dev/null
  fi
  ok "Python packages"
else
  bad "Python packages: the install above failed; fix the error it shows and run this again"
fi

echo
echo "== Voice: VOICEVOX with the Mochiko-san voice (about 190 MB)"
if [ -f .chassie/voicevox/models/vvms/15.vvm ]; then
  answer=yes
else
  echo "Chassie speaks Japanese through VOICEVOX. Installing it accepts the VOICEVOX"
  echo "software and voice terms: https://voicevox.hiroshiba.jp/term/"
  echo "(credit: VOICEVOX:もち子(cv 明日葉よもぎ); full terms land in .chassie/voicevox/models/TERMS.txt)"
  read -r -p "Type yes to accept and install: " answer
fi
if [ "$answer" = "yes" ]; then
  if "$PY" scripts/install_voicevox.py; then ok "voice VOICEVOX Mochiko-san"; else bad "voice: run '.venv/bin/python scripts/install_voicevox.py' to see the error"; fi
else
  bad "voice not installed: its terms were not accepted (run this again and type yes)"
fi

echo
echo "== Eyes: face detection and recognition (about 220 MB)"
if "$PY" scripts/install_vision.py; then ok "vision models"; else bad "vision models: run '.venv/bin/python scripts/install_vision.py' to see the error"; fi

echo "== Ears: voice recognition of the owner (about 26 MB)"
if "$PY" scripts/install_speaker.py >/dev/null; then ok "speaker model"; else bad "speaker model: run '.venv/bin/python scripts/install_speaker.py' to see the error"; fi

echo "== Memory: local embedding model (about 350 MB)"
if "$PY" scripts/install_memory_model.py; then ok "memory model"; else bad "memory model: run '.venv/bin/python scripts/install_memory_model.py' to see the error"; fi

echo
HERMES="${HERMES_HOME:-$HOME/.hermes}"
if [ -d "$HERMES" ]; then
  if scripts/install_hermes_plugin.sh >/dev/null; then ok "memory plugin linked into $HERMES/plugins/chassie"; else bad "memory plugin: run scripts/install_hermes_plugin.sh"; fi
else
  bad "Hermes not found ($HERMES): install Hermes, then run this again (README, steps 3 and 4)"
fi

if scripts/install_desktop_entry.sh >/dev/null; then ok "Chassie in the application menu"; else bad "application menu entry: run scripts/install_desktop_entry.sh"; fi

if find model -name '*.model3.json' -print -quit 2>/dev/null | grep -q .; then
  ok "Live2D model found in model/"
else
  ok "Live2D model: none yet, you add one when Chassie first opens (README, step 6)"
fi

if [ -f .chassie/hermes-api-key ]; then
  ok "Hermes API key (.chassie/hermes-api-key)"
else
  bad "no Hermes API key yet: README, step 4"
fi

echo
echo "== Chassie setup summary"
printf '%s\n' "${summary[@]}"
echo
echo "Done. Next: start her with  .venv/bin/python launch.py"
