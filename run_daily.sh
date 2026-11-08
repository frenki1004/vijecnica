#!/bin/bash
# Refresh: new videos + documents, transcribe up to 3 new recordings on the Mac (when idle), rebuild the DB.
set -u
cd "$(dirname "$0")"
mkdir -p logs
exec >> logs/daily-$(date +%F).log 2>&1
echo "== $(date -Is)"
.venv/bin/python collect/list_videos.py | tail -3
.venv/bin/python collect/docs.py --refresh-latest 2
.venv/bin/python db/build.py
timeout 5h .venv/bin/python -u asr/run_queue.py --max 3 --wait 60
.venv/bin/python db/build.py
.venv/bin/python eval_minutes.py --city zagreb --session 14 > /dev/null
.venv/bin/python eval_brod.py --session 9 | tail -1
.venv/bin/python clerk_time.py --session 14 > /dev/null
.venv/bin/python export/export.py | tail -1
