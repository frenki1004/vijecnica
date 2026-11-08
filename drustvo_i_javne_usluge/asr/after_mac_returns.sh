#!/bin/bash
# One-off: wait for the Mac (up to 12 h), transcribe Slavonski Brod, then Zagreb sessions 14 and 13, rebuild DB.
cd "$(dirname "$0")/.."
python3 -u asr/run_queue.py --city brod --wait 720 && python3 db/build.py
python3 -u asr/run_queue.py --sessions 14,13 --wait 120 && python3 db/build.py
