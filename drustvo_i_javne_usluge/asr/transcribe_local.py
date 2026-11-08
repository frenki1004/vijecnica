"""Stopgap while the Mac mini is offline: transcribe on the G710 CPU (faster-whisper large-v3-turbo, int8).

~0.9x realtime on 4 threads (i5-4200M), so it is slow; runs niced, newest recording first, and stops
as soon as the Mac answers again only with --stop-for-mac (user, 2026-11-07: keep transcribing locally until told otherwise).
Zagreb and Rijeka audio is downloaded from YouTube first (run_queue.download).
Audio is decoded and transcribed in 10-minute windows (a whole 3.6 h file in memory got the process
OOM-killed at 3.8 GB on 2026-11-05); progress is saved to <id>.partial.json after every window and
resumed from there. Run it under a memory cap (systemd-run --user --scope -p MemoryMax=1500M).
Same output format as transcribe.py: data/<city>/transcripts/<id>.json.

Usage: nice -n 19 python asr/transcribe_local.py --city brod [--threads 3]
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = {
    "zagreb": "Sjednica Gradske skupštine Grada Zagreba. Gradonačelnik Tomislav Tomašević, zastupnici.",
    "brod": ("Sjednica Gradskog vijeća Grada Slavonskog Broda. Predsjednik Gradskog vijeća Hrvoje Andrić, "
             "gradonačelnik Mirko Duspara, vijećnici, aktualni sat."),
    "krk": ("Sjednica Gradskog vijeća Grada Krka. Predsjednica Gradskog vijeća Iva Tabar, gradonačelnik Darijo "
            "Vasilić, vijećnici, dnevni red, točka, aktualni sat, glasovanje, zaključak, prijedlog odluke."),
    "rijeka": ("Sjednica Gradskog vijeća Grada Rijeke. Gradonačelnica Iva Rinčić, vijećnici, dnevni red, točka, "
               "aktualni sat, glasovanje, amandman, zaključak, prijedlog odluke."),
}


from run_queue import MAC, download  # noqa: E402  (asr/ is on sys.path when run as a script)


def mac_online():
    return subprocess.run(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", MAC,
                           "true"], capture_output=True).returncode == 0


WINDOW = 600  # seconds of audio per transcribe call


def load(path, start, length):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(start), "-t", str(length), "-i", str(path),
                          "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="brod")
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--stop-for-mac", action="store_true")
    a = ap.parse_args()
    base = ROOT / "data" / a.city if a.city != "zagreb" else ROOT / "data"
    if a.city == "zagreb":
        recs = [{**v, "date": v["upload_date"], "url": f"https://www.youtube.com/watch?v={v['id']}"}
                for v in json.loads((base / "videos.json").read_text())]
    else:
        recs = json.loads((base / "recordings.json").read_text())
    recs.sort(key=lambda r: r["date"] or "", reverse=True)
    model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8", cpu_threads=a.threads)
    for r in recs:
        out = base / "transcripts" / f"{r['id']}.json"
        if out.exists():
            continue
        if a.stop_for_mac and mac_online():
            print("Mac is back, stopping (run_queue.py takes over)", flush=True)
            return
        t0 = time.time()
        dur = r.get("duration") or 0
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_suffix(".partial.json")
        state = json.loads(part.read_text()) if part.exists() else {"next": 0, "segments": [], "seconds": 0}
        rows = state["segments"]
        if a.city in ("zagreb", "rijeka"):
            (base / "audio").mkdir(parents=True, exist_ok=True)
            src = download(r, base)
        else:
            src = base / "audio" / f"{r['id']}.mp3"
        while state["next"] < dur:
            if a.stop_for_mac and mac_online():
                print("Mac is back, stopping (run_queue.py takes over)", flush=True)
                return
            w0 = state["next"]
            t1 = time.time()
            audio = load(src, w0, WINDOW)
            segs, _ = model.transcribe(audio, language="hr", vad_filter=True, beam_size=1,
                                       initial_prompt=PROMPTS[a.city], condition_on_previous_text=False)
            for s in segs:
                if s.text.strip():
                    rows.append({"start": round(w0 + s.start, 2), "end": round(w0 + s.end, 2), "text": s.text.strip()})
            del audio
            state["next"] = w0 + WINDOW
            state["seconds"] += time.time() - t1
            part.write_text(json.dumps(state, ensure_ascii=False))
            print(f"{r['id']}: {min(state['next'], dur) / 60:.0f}/{dur / 60:.0f} min "
                  f"({WINDOW / max(time.time() - t1, 1):.2f}x realtime)", flush=True)
        took = state["seconds"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"model": "faster-whisper large-v3-turbo int8 (G710 CPU)", "audio": r["url"],
                                   "duration": dur, "seconds": took, "segments": rows}, ensure_ascii=False, indent=1))
        part.unlink(missing_ok=True)
        print(f"{r['id']}: done, {len(rows)} segments, {dur / 60:.0f} min audio in {took / 60:.0f} min", flush=True)
        subprocess.run(["python3", str(ROOT / "db" / "build.py")], capture_output=True)


if __name__ == "__main__":
    main()
