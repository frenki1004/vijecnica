"""Transcription queue (runs on the G710): download session audio here, transcribe on the Mac mini.

For each video in data/videos.json without data/transcripts/<id>.json (newest session first,
or only the ids/sessions given on the command line):
  1. download audio to data/audio/<id>.<ext> (yt-dlp, best audio, no re-encode)
  2. wait until the Mac is idle (Mac lock convention, see hr-prices/CLAUDE.md), take .lock-vijecnica
  3. ship audio to /Volumes/g710jobs/vijecnica/work, run transcribe.py, pull JSON back, delete on Mac
Yields between videos when another job writes /Volumes/g710jobs/.want-*.

Usage: python asr/run_queue.py [--city brod] [--max N] [--sessions 14,13] [ids...]
Brod and Krk recordings are MP3s already in data/<city>/audio (collect/<city>.py --audio); Rijeka's are
YouTube, downloaded to data/rijeka/audio like Zagreb's.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# compute host and its job volume; override for another machine (see README "Transkripcija")
sys.path.insert(0, str(ROOT))
try:
    import config_local as _cfg  # machine-specific, not in git
except ImportError:
    _cfg = None
MAC = os.environ.get("VIJECNICA_ASR_HOST", getattr(_cfg, "ASR_HOST", "user@mac-hostname"))
JOBS = os.environ.get("VIJECNICA_ASR_ROOT", "/Volumes/g710jobs")
J = f"{JOBS}/vijecnica"
YTDLP = [os.path.expanduser("~/.local/bin/yt-dlp"), "--js-runtimes", "node", "--no-warnings", "-q"]
ENV = (f"export PATH=/opt/homebrew/bin:$PATH TMPDIR={J}/tmp HF_HOME={JOBS}/hf "
       f"UV_CACHE_DIR={J}/uv-cache;")


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def ssh(cmd, check=True, timeout=None):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", MAC, ENV + cmd], capture_output=True,
                          text=True, check=check, timeout=timeout)


def mac_busy():
    """Reason the Mac is not idle, or None."""
    now = datetime.now()
    if (now.hour, now.minute) >= (7, 15) and (now.hour, now.minute) <= (7, 45):
        return "daily quiz window"
    r = ssh("curl -s localhost:11434/api/ps; echo; memory_pressure | tail -1; "
            f"ls -a {JOBS} | grep -E '^\\.(lock|want)-' || true", check=False, timeout=60)
    if r.returncode:
        return "ssh failed"
    lines = r.stdout.splitlines()
    try:
        if json.loads(lines[0]).get("models"):
            return "ollama model loaded"
    except (ValueError, IndexError):
        pass
    free = [l for l in lines if "free percentage" in l]
    if free and int(free[0].rsplit(" ", 1)[1].rstrip("%")) < 35:
        return "memory pressure"
    others = [l for l in lines[1:] if l.startswith((".lock-", ".want-")) and "vijecnica" not in l]
    if others:
        # stale locks (past expires) do not count
        live = []
        for f in others:
            if f.startswith(".lock-"):
                c = ssh(f"cat {JOBS}/{f}", check=False).stdout
                try:
                    if json.loads(c).get("expires", 0) < time.time():
                        continue
                except ValueError:
                    pass
            live.append(f)
        if live:
            return "other job: " + ",".join(live)
    return None


def take_lock(hours=2):
    now = int(time.time())
    lock = json.dumps({"job": "vijecnica", "host": "g710", "pid": os.getpid(), "started": now,
                       "expires": now + hours * 3600})
    ssh(f"echo '{lock}' > {JOBS}/.lock-vijecnica")


def drop_lock():
    ssh(f"rm -f {JOBS}/.lock-vijecnica", check=False)


def download(v, base=DATA):
    have = list((base / "audio").glob(f"{v['id']}.*"))
    have = [p for p in have if not p.name.endswith((".part", ".ytdl"))]
    if have:
        return have[0]
    log("download", v["id"], v["title"])
    subprocess.run(YTDLP + ["-f", "bestaudio", "-o", str(base / "audio" / "%(id)s.%(ext)s"),
                            f"https://www.youtube.com/watch?v={v['id']}"], check=True)
    return next(p for p in (base / "audio").glob(f"{v['id']}.*") if not p.name.endswith(".part"))


def transcribe(v, audio, base=DATA, city="zagreb"):
    out = base / "transcripts" / f"{v['id']}.json"
    remote = f"{J}/work/{audio.name}"
    ssh(f"mkdir -p {J}/work")
    subprocess.run(["scp", "-q", str(ROOT / "asr" / "transcribe.py"), f"{MAC}:{J}/transcribe.py"], check=True)
    subprocess.run(["scp", "-q", str(audio), f"{MAC}:{remote}"], check=True)
    try:
        r = ssh(f"cd {J} && .venv/bin/python transcribe.py work/{audio.name} work/{v['id']}.json mlx_models/hr-parla {city} "
                "2>&1 | grep -v -e frames -e Warning -e warnings.warn | tail -2", timeout=4 * 3600)
        log(r.stdout.strip())
        subprocess.run(["scp", "-q", f"{MAC}:{J}/work/{v['id']}.json", str(out)], check=True)
        d = json.loads(out.read_text())
        d["video"] = v
        out.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    finally:
        ssh(f"rm -f {remote} {J}/work/{v['id']}.json", check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--max", type=int, default=99)
    ap.add_argument("--sessions", default="")
    ap.add_argument("--wait", type=int, default=0, help="minutes to wait for an idle Mac")
    ap.add_argument("--city", default="zagreb", choices=["zagreb", "brod", "krk", "rijeka"])
    a = ap.parse_args()
    base = DATA if a.city == "zagreb" else DATA / a.city
    (base / "audio").mkdir(parents=True, exist_ok=True)
    (base / "transcripts").mkdir(parents=True, exist_ok=True)
    if a.city == "zagreb":
        videos = json.loads((DATA / "videos.json").read_text())
    else:
        videos = [{**r, "upload_date": (r["date"] or "").replace("-", "")}
                  for r in json.loads((base / "recordings.json").read_text())]
    sessions = {int(s) for s in a.sessions.split(",") if s}
    todo = [v for v in videos
            if not (base / "transcripts" / f"{v['id']}.json").exists()
            and (not a.ids or v["id"] in a.ids) and (not sessions or v["session"] in sessions)]
    todo.sort(key=lambda v: v["upload_date"], reverse=True)
    done = 0
    for v in todo[:a.max]:
        if (base / "transcripts" / f"{v['id']}.json").exists():  # done meanwhile (e.g. transcribe_local.py)
            continue
        audio = download(v, base) if a.city in ("zagreb", "rijeka") else base / "audio" / f"{v['id']}.mp3"  # YouTube cities
        deadline = time.time() + a.wait * 60
        while (why := mac_busy()):
            if time.time() > deadline:
                log("Mac busy:", why, "- stopping")
                return
            log("Mac busy:", why, "- waiting")
            time.sleep(120)
        take_lock()
        try:
            log("transcribe", v["id"], v["upload_date"], v["title"])
            transcribe(v, audio, base, a.city)
            done += 1
        finally:
            drop_lock()
    log(f"done {done}, left {len(todo) - done}")


if __name__ == "__main__":
    sys.exit(main())
