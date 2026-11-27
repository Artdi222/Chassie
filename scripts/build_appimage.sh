#!/usr/bin/env bash
# Build dist/Chassie-<version>-x86_64.AppImage (CPU only) from a relocatable Python 3.12.
# Runs on GitHub Actions (.github/workflows/appimage.yml); needs curl, git and about 6 GB free.
# Not inside: Hermes, VOICEVOX and the speech/vision/memory models (downloaded on first run),
# the Live2D model (the person's own) and CUDA (GPU acceleration stays a git-install option).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-$(git describe --tags --always)}"
PYTHON_URL=https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux_2_28_x86_64.AppImage
TOOL_URL=https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
VOICEVOX_WHEEL=https://github.com/VOICEVOX/voicevox_core/releases/download/0.17.0/voicevox_core-0.17.0-cp310-abi3-manylinux_2_34_x86_64.whl
WORK=build/appimage APPDIR=build/appimage/squashfs-root
export APPIMAGE_EXTRACT_AND_RUN=1  # No FUSE on CI runners.

rm -rf "$WORK" && mkdir -p "$WORK" dist
curl -fsSL -o "$WORK/python.AppImage" "$PYTHON_URL" && chmod +x "$WORK/python.AppImage"
(cd "$WORK" && ./python.AppImage --appimage-extract >/dev/null)
PY="$APPDIR/opt/python3.12/bin/python3.12"

echo "== Python packages (CPU onnxruntime instead of onnxruntime-gpu and the CUDA libraries)"
grep -vE '^(onnxruntime-gpu|nvidia-)' requirements.txt > "$WORK/requirements.txt"
echo "voicevox_core @ $VOICEVOX_WHEEL" >> "$WORK/requirements.txt"
"$PY" -m pip install --no-cache-dir --no-warn-script-location -r "$WORK/requirements.txt" -r requirements-overlay.txt

echo "== Chassie $VERSION"
mkdir -p "$APPDIR/opt/chassie"
git ls-files -z -- . ':!tests' ':!docs' ':!.github' ':!packaging' | tar --null -T - -cf - | tar -xf - -C "$APPDIR/opt/chassie"
echo "$VERSION" > "$APPDIR/opt/chassie/VERSION"
PYTHONPATH="$APPDIR/opt/chassie" "$PY" -c 'import brain.orchestrator, desktop.qt_app, speech.voicevox_tts, voicevox_core, live2d, faster_whisper, sherpa_onnx, onnxruntime, cv2, mediapipe'

echo "== AppDir"
rm -f "$APPDIR"/*.desktop "$APPDIR"/*.png "$APPDIR"/.DirIcon
rm -rf "$APPDIR"/usr/share/applications "$APPDIR"/usr/share/metainfo
cp packaging/AppRun "$APPDIR/AppRun"
cp packaging/chassie.desktop "$APPDIR/"
cp ui/public/chassie-icon.png "$APPDIR/chassie.png" && cp "$APPDIR/chassie.png" "$APPDIR/.DirIcon"
chmod -R u+rwX,go+rX "$APPDIR"  # The extracted image is 0700; the AppImage must be readable by everyone.
find "$APPDIR" -name __pycache__ -type d -prune -exec rm -rf {} +

curl -fsSL -o "$WORK/appimagetool" "$TOOL_URL" && chmod +x "$WORK/appimagetool"
ARCH=x86_64 "$WORK/appimagetool" "$APPDIR" "dist/Chassie-$VERSION-x86_64.AppImage"
ls -lh dist
