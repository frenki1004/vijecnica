"""List the Zagreb City Assembly's YouTube session streams -> data/videos.json.

Keeps only session recordings ("N. sjednica ..."), adds upload date + duration per video
(cached: only new ids are fetched). Newest first.
"""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "videos.json"
CHANNEL = "https://www.youtube.com/channel/UCRMm4Xt9ruoQ8FG7NpIHCsA"
YTDLP = [os.path.expanduser("~/.local/bin/yt-dlp"), "--js-runtimes", "node", "--no-warnings"]
SESSION_RE = re.compile(r"^\s*(\d+)\.?\s+sjednica|konstituirajuća", re.I)


def ytdlp(*args):
    return subprocess.run(YTDLP + list(args), capture_output=True, text=True, check=True).stdout


def main():
    old = {v["id"]: v for v in json.loads(OUT.read_text())} if OUT.exists() else {}
    rows = []
    for tab in ("streams", "videos"):
        for line in ytdlp("--flat-playlist", "--print", "%(id)s\t%(title)s",
                          f"{CHANNEL}/{tab}").splitlines():
            vid, title = line.split("\t", 1)
            if SESSION_RE.search(title) and vid not in {r["id"] for r in rows}:
                rows.append({"id": vid, "title": " ".join(title.split())})
    out = []
    for r in rows:
        v = old.get(r["id"])
        if not v:
            try:
                meta = ytdlp("--skip-download", "--print",
                             "%(upload_date)s\t%(duration)s\t%(release_timestamp)s",
                             f"https://www.youtube.com/watch?v={r['id']}").split("\t")
            except subprocess.CalledProcessError as e:
                print("skip", r["id"], r["title"], (e.stderr or "").strip()[-120:])
                continue
            m = SESSION_RE.search(r["title"])
            v = {**r, "session": int(m.group(1)) if m.group(1) else 0,
                 "upload_date": meta[0], "duration": int(meta[1]) if meta[1] != "NA" else None,
                 "release_timestamp": None if meta[2].strip() == "NA" else int(meta[2])}
            print("new", v["id"], v["upload_date"], v["title"])
        out.append(v)
        if len(out) % 10 == 0:
            OUT.parent.mkdir(exist_ok=True)
            OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out)} session videos")


if __name__ == "__main__":
    main()
