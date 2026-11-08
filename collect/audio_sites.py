"""Session recordings from councils that post plain audio files on their own site (found by collect/discover.py).

Per unit: read its recordings page (robots.txt respected), take every audio link (mp3/m4a/wma), read the session
number from the file name, download the newest sessions to data/<unit>/audio/<id>.mp3 and list them in
data/<unit>/recordings.json, the format asr/transcribe_mlx_local.py reads (same as Brod/Krk). Nothing else is parsed:
these units have no agenda/minutes collector yet, so the transcript is the only source for now.

The date is the file's Last-Modified (when it was put online, not necessarily the day of the session).

Usage: python collect/audio_sites.py [--units cakovec,velika_gorica] [--last 3]
"""
import argparse
import email.utils
import html
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "vijecnica-research/0.1 (open data hackathon)"  # as collect/brod.py
AUDIO = re.compile(r"""(?:href|src)=["']([^"']+\.(?:mp3|m4a|wma))(?:\?[^"']*)?["']""", re.I)
POST = re.compile(r"""href=["'](https://www\.cakovec\.hr/odrzana-\d+-sjednica-gradskog-vijeca[^"'#]*)["']""")
UNITS = {  # key: (name, recordings page, session number from the file path)
    # one news post per session ("Održana N. sjednica"), the audio is linked there: POST finds them on the page
    "cakovec": ("Čakovec", "https://www.cakovec.hr/kategorija/gradsko-vijece/", r"/gv(\d+)/"),
    "velika_gorica": ("Velika Gorica", "https://gorica.hr/gradsko-vijece-2/sjednice-gradskog-vijeca/",
                      r"gv-audio-(\d+)-\d{4}"),
    "petrinja": ("Petrinja", "https://petrinja.hr/snimke-sjednica-gradskog-vijeca/",
                 r"(\d+)\D{0,3}sjednic|sjednic\w*\D{0,3}(\d+)"),
}
_last = {}
_robots = {}


def fetch(url, method="GET"):
    """Polite GET/HEAD: robots.txt per host, >= 1 s between requests to a host. Returns (headers, body)."""
    p = urllib.parse.urlsplit(url)
    if p.netloc not in _robots:
        rp = urllib.robotparser.RobotFileParser(f"{p.scheme}://{p.netloc}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp.allow_all = True  # no robots.txt reachable: nothing disallowed
        _robots[p.netloc] = rp
    if not _robots[p.netloc].can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0.0, 1.0 - (time.time() - _last.get(p.netloc, 0))))
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, method=method, headers={"User-Agent": UA}),
                                   timeout=600)
        return r.headers, r.read()
    finally:
        _last[p.netloc] = time.time()


def links(key):
    name, page, pat = UNITS[key]
    text = fetch(page)[1].decode("utf-8", "replace")
    for post in list(dict.fromkeys(POST.findall(text)))[:6]:  # newest first on the page
        text += fetch(post)[1].decode("utf-8", "replace")
    seen, out = set(), []
    for m in AUDIO.finditer(text):
        url = urllib.parse.urljoin(page, html.unescape(m.group(1))).replace("http://", "https://", 1)
        if url in seen:
            continue
        seen.add(url)
        s = re.search(pat, urllib.parse.unquote(url), re.I)
        if s:
            out.append((int(next(g for g in s.groups() if g)), url))
    return out


def collect(key, last):
    base = ROOT / "data" / key
    (base / "audio").mkdir(parents=True, exist_ok=True)
    found = links(key)
    sessions = sorted({s for s, _ in found}, reverse=True)[:last]
    path = base / "recordings.json"
    recs = {r["id"]: r for r in json.loads(path.read_text())} if path.exists() else {}
    for s in sessions:
        for part, url in enumerate((u for n, u in found if n == s), 1):
            rid = f"{key}-{s:02d}-{part}"
            mp3 = base / "audio" / f"{rid}.mp3"  # ffmpeg reads m4a/wma by content, whatever the extension
            if rid in recs and mp3.exists():
                continue
            headers, data = fetch(url)
            mp3.write_bytes(data)
            mod = headers.get("Last-Modified")
            date = email.utils.parsedate_to_datetime(mod).date().isoformat() if mod else None
            recs[rid] = {"id": rid, "session": s, "part": part, "url": url, "date": date,
                         "title": f"{s}. sjednica Gradskog vijeća ({UNITS[key][0]})"}
            print(f"{rid} {date} {len(data) / 1e6:.0f} MB {url}")
    path.write_text(json.dumps(sorted(recs.values(), key=lambda r: (-r["session"], r["part"])),
                               ensure_ascii=False, indent=1))
    print(f"{key}: {len(found)} audio links, sessions {sessions}, {len(recs)} recordings listed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", default=",".join(UNITS))
    ap.add_argument("--last", type=int, default=3, help="newest N sessions per unit")
    a = ap.parse_args()
    for key in a.units.split(","):
        try:
            collect(key, a.last)
        except Exception as e:  # one site down must not stop the others
            print(f"!! {key}: {e}")


if __name__ == "__main__":
    main()
