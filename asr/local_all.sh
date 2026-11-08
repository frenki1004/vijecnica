#!/bin/bash
# Local-only transcription (user, 2026-11-07: don't wait for the Mac). Brod → Rijeka → Zagreb newest first.
# 1500M cap got OOM-killed (model + ffmpeg + per-file build.py share the scope), so 2300M; a killed run resumes
# from <id>.partial.json, up to 5 retries per city.
cd "$(dirname "$0")/.."
for c in brod rijeka zagreb; do
  for try in 1 2 3 4 5; do
    systemd-run --user --scope -p MemoryMax=2300M -p MemorySwapMax=500M nice -n 19 .venv/bin/python -u asr/transcribe_local.py --city $c --threads 3 && break
    echo "$(date +%T) $c run $try failed, retrying in 60 s"; sleep 60
  done
  python3 db/build.py >/dev/null
done
