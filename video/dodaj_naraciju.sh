#!/bin/sh
# Ugradi snimljenu naraciju (naracija.wav iz deploy/demo_video/naracija.html) u video, pa i titlove u sliku.
#   video/dodaj_naraciju.sh ~/Downloads/naracija.wav
# Izlaz: deploy/demo_video/demo_naracija.mp4 (za YouTube, uz demo.srt) i demo_naracija_titlovi.mp4 (za WhatsApp)
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR="$ROOT/deploy/demo_video"
NAR=${1:?"zadaj putanju do naracija.wav"}
ffmpeg -y -loglevel error -i "$DIR/demo_clean.mp4" -i "$NAR" -filter_complex "\
[1:a]aresample=48000,highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=150,pan=stereo|c0=c0|c1=c0,\
loudnorm=I=-16:TP=-1.5:LRA=11,apad[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest "$DIR/demo_naracija.mp4"
echo "gotovo: $DIR/demo_naracija.mp4"
cd "$ROOT" && uv run --with pillow python web/burn_subtitles.py "$DIR/demo_naracija.mp4" "$DIR/demo_naracija_titlovi.mp4"
