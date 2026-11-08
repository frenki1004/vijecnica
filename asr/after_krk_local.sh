#!/bin/bash
# One-off (2026-11-07): Mac offline, so after the local Krk run ends, transcribe the remaining Brod recordings locally, then rebuild.
cd "$(dirname "$0")/.."
while pgrep -f "transcribe_local.py --city krk" >/dev/null; do sleep 60; done
python3 db/build.py
systemd-run --user --scope -p MemoryMax=1500M nice -n 19 .venv/bin/python -u asr/transcribe_local.py --city brod --threads 3
python3 db/build.py
