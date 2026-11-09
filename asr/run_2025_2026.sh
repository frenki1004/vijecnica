#!/bin/bash
# Transcribe every remaining recording of the 2025-2029 term (all of them are from 2025 and 2026) on this Mac.
#   nohup asr/run_2025_2026.sh > logs/asr_2025_2026.log 2>&1 &
# 1. Waits while the demo video is being recorded (CPU contention breaks its fixed clock).
# 2. First pass: the newest session of every unit that has no transcript yet, so each has at least one.
# 3. Then everything else, newest first, small units before Rijeka and Zagreb (~180 h of Zagreb alone).
# The DB is rebuilt after the first pass and after each unit, never while a demo recording runs.
# Stop any time (kill the script); finished transcripts stay, the next run skips them.
cd "$(dirname "$0")/.."
PY=../.venv/bin/python

busy() { pgrep -f "record_demo.py|burn_subtitles.py|record_film.py" >/dev/null; }
wait_free() { while busy; do echo "$(date +%T) demo recording runs, waiting"; sleep 60; done; }
rebuild() { wait_free; $PY db/build.py 2>&1 | tail -1; }
newest() {  # newest session of a unit without a transcript
  python3 -c "
import json, os, sys
c = sys.argv[1]; r = json.load(open(f'data/{c}/recordings.json'))
d = f'data/{c}/transcripts'; done = {f[:-5] for f in os.listdir(d)} if os.path.isdir(d) else set()
print(max((x['session'] for x in r if x['id'] not in done), default=''))" "$1"
}
run() { wait_free; nice -n 10 $PY -u asr/transcribe_mlx_local.py --city "$@"; }

guard() {  # a recording that starts mid-transcription: pause transcription (SIGSTOP) until it ends
  while true; do
    if busy; then pkill -STOP -f "asr/transcribe.py|transcribe_mlx_local.py|yt-dlp"; else pkill -CONT -f "asr/transcribe.py|transcribe_mlx_local.py|yt-dlp"; fi
    sleep 5
  done
}
guard & trap 'kill $! 2>/dev/null; pkill -CONT -f "asr/transcribe.py|transcribe_mlx_local.py|yt-dlp"' EXIT

echo "$(date +%T) start"
for c in zadar varazdin ploce kastela karlovac dubrovnik bjelovar; do
  s=$(newest $c); [ -n "$s" ] && run $c --sessions "$s"
done
rebuild
for c in krk ploce bjelovar kastela sibenik osijek varazdin dubrovnik ogulin zadar karlovac rijeka zagreb; do
  run $c
  rebuild
done
echo "$(date +%T) all done"
