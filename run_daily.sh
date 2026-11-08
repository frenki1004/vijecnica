#!/bin/bash
# Daily refresh of all 19 units: collect -> data.gov.hr -> DB -> transcribe new recordings -> DB -> new post drafts
# -> feed, images, Reddit files, open-data export and the static demo build.
# It does not publish: new drafts wait for a person to review them, then deploy by hand:
#   npx vercel deploy deploy/vijecnica --prod
# Cron (06:00): 0 6 * * * /path/to/drustvo_i_javne_usluge/run_daily.sh
set -u
cd "$(dirname "$0")"
PY=${PY:-../.venv/bin/python}
mkdir -p logs
exec >> logs/daily-$(date +%F).log 2>&1
echo "== $(date -Iseconds)"
step() { echo "-- $*"; "$@" || echo "!! failed: $*"; }   # one failing source must not stop the rest

# 1. collect (each collector caches what it already has; --fresh re-reads only the session lists)
step $PY collect/list_videos.py
step $PY collect/docs.py --refresh-latest 2
step $PY collect/brod.py --audio
step $PY collect/krk.py --audio
step $PY collect/rijeka.py --fresh
step $PY collect/osijek.py --fresh
step $PY collect/sibenik.py --fresh
step $PY collect/netcom.py --fresh
step $PY collect/datagovhr.py
step $PY db/build.py

# 2. transcribe new MP3 recordings on this Mac (mlx-whisper; skips what is already transcribed), then rebuild
step timeout 5h $PY -u asr/transcribe_mlx_local.py --city brod
step timeout 5h $PY -u asr/transcribe_mlx_local.py --city krk
step $PY db/build.py

# 3. new post drafts for every unit with votes (Claude API; skipped without a key), then feed and outputs
for c in zagreb brod krk rijeka osijek sibenik opatija kastav senj ogulin viskovo punat; do
  step sh -c "$PY posts/build_queue.py --city $c > data/posts/queue_full_$c.json"
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then step $PY posts/write.py data/posts/queue_full_$c.json --out drafts_full_$c.json; fi
done
step $PY posts/assemble.py
step $PY posts/export_reddit.py
step $PY export/export.py
step $PY web/build_static.py
echo "== done; review new drafts in data/posts/ before: npx vercel deploy deploy/vijecnica --prod"
