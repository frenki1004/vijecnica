"""run_queue.py without ssh: when this machine is the Apple-silicon Mac, run transcribe.py here.

Needs .venv-mlx (mlx-whisper, silero-vad, torch) and mlx_models/hr-parla (convert_hf.py). For each recording
without data/[<city>/]transcripts/<id>.json (newest first, or only the ids/sessions given), transcribe its
audio (Zagreb/Rijeka: downloaded via run_queue.download; Brod/Krk: data/<city>/audio/<id>.mp3) and add the
"video" record like run_queue.transcribe().

Usage: python asr/transcribe_mlx_local.py [--city brod] [--sessions 9,8] [ids...]
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

from run_queue import DATA, ROOT, download, log  # asr/ is on sys.path when run as a script

PY = next((p for p in (ROOT / ".venv-mlx" / "bin" / "python", ROOT.parent / ".venv-mlx" / "bin" / "python")
           if p.exists()), ROOT / ".venv-mlx" / "bin" / "python")  # in the repo, or shared one level up
MODEL = ROOT / "mlx_models" / "hr-parla"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--sessions", default="")
    ap.add_argument("--city", default="zagreb", choices=["zagreb", "brod", "krk", "rijeka", "cakovec", "velika_gorica", "petrinja"])
    a = ap.parse_args()
    base = DATA if a.city == "zagreb" else DATA / a.city
    (base / "transcripts").mkdir(parents=True, exist_ok=True)
    if a.city == "zagreb":
        videos = json.loads((base / "videos.json").read_text())
    else:
        videos = [{**r, "upload_date": (r["date"] or "").replace("-", "")}
                  for r in json.loads((base / "recordings.json").read_text())]
    sessions = {int(s) for s in a.sessions.split(",") if s}
    todo = [v for v in videos if not (base / "transcripts" / f"{v['id']}.json").exists()
            and (not a.ids or v["id"] in a.ids) and (not sessions or v["session"] in sessions)]
    todo.sort(key=lambda v: v["upload_date"], reverse=True)
    failed = 0
    for v in todo:
        out = base / "transcripts" / f"{v['id']}.json"
        tmp = out.with_suffix(".json.tmp")  # never matches *.json, so build.py/eval never see a half-written file
        if a.city in ("zagreb", "rijeka"):
            (base / "audio").mkdir(parents=True, exist_ok=True)
            audio = download(v, base)
        else:
            audio = base / "audio" / f"{v['id']}.mp3"
        if not audio.exists():
            log("no audio", audio)
            failed += 1
            continue
        log("transcribe", v["id"], v["upload_date"], v["title"])
        t0 = time.time()
        r = subprocess.run([str(PY), str(ROOT / "asr" / "transcribe.py"), str(audio), str(tmp), str(MODEL), a.city],
                           capture_output=True, text=True)
        if r.returncode:
            log("FAILED", v["id"], r.stderr[-1500:])
            tmp.unlink(missing_ok=True)
            failed += 1
            continue
        d = json.loads(tmp.read_text())
        d.update(model="mlx_models/hr-parla", audio=audio.name, video=v)
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        tmp.rename(out)
        log(r.stdout.strip().splitlines()[-1], f"(wall {(time.time() - t0) / 60:.1f} min)")
    log(f"done {len(todo) - failed}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
