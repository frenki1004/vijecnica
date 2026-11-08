#!/bin/bash
# One-off (2026-11-07): after after_krk_local.sh (Brod), keep transcribing on the G710: Rijeka, then Zagreb newest first.
cd "$(dirname "$0")/.."
while pgrep -f "after_krk_local.sh|transcribe_local.py" >/dev/null; do sleep 60; done
for c in rijeka zagreb; do
  systemd-run --user --scope -p MemoryMax=1500M nice -n 19 .venv/bin/python -u asr/transcribe_local.py --city $c --threads 3
  python3 db/build.py
done
