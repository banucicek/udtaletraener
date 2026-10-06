#!/bin/bash
# One-time setup for the Udtaletræner podcast pipeline on a Mac.
# Run from the folder that contains this file:   bash setup.sh
set -e
cd "$(dirname "$0")"

echo "== Checking ffmpeg"
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
  else
    echo "ffmpeg is missing and Homebrew isn't installed."
    echo "Install Homebrew from https://brew.sh, then run:  brew install ffmpeg"
    echo "Then run this setup again."
    exit 1
  fi
fi

echo "== Checking Python"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "python3 not found. Install it with:  brew install python   (or run: xcode-select --install)"
  exit 1
fi
"$PY" -c 'import sys; assert sys.version_info >= (3,9), "Python 3.9+ needed"'

echo "== Creating a private Python environment in .venv"
"$PY" -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null

if [ "$(uname -m)" = "arm64" ]; then
  echo "== Apple Silicon detected: installing mlx-whisper (fast on M-series chips)"
  ./.venv/bin/pip install mlx-whisper
else
  echo "== Intel Mac: installing faster-whisper"
  ./.venv/bin/pip install faster-whisper
fi

echo
echo "Setup done. Start the pipeline with:"
echo "   ./.venv/bin/python monopolet.py --episodes 3     (quick test run)"
echo "   ./.venv/bin/python monopolet.py                  (10 episodes)"
echo "The first run also downloads the Whisper model (about 1.5 GB)."
