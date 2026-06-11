#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

FFMPEG_PATH="$(command -v ffmpeg)"
FFPROBE_PATH="$(command -v ffprobe)"

pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "Auralis" \
  --icon "assets/Auralis.icns" \
  --add-data "assets:assets" \
  --add-data "Resources:Resources" \
  --add-binary "${FFMPEG_PATH}:." \
  --add-binary "${FFPROBE_PATH}:." \
  Auralis_launcher.py

echo "Built: ${ROOT}/dist/Auralis.app"
