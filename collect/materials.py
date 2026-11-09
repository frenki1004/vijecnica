"""Session materials (proposal, explanation) for the items behind posts: what the minutes only name.

The minutes say a decision was taken ("Odluka o izmjenama Odluke o lokalnim porezima"); the materials say what it
does (the new rates, the price, the address, who benefits). For each post of the latest sessions this reads the
item's attachments from data/vijecnica.db, picks the most informative two (explanation, proposal; not forms,
cover letters, land-register extracts or maps), downloads them politely (robots.txt, >= 1 s per host, cached in
data/<unit>/raw/materials) and keeps their text: pdftotext for the first pages, OCR when a PDF is a scan,
textutil for Word files.

Output: data/posts/materials.json {post id: [{"name", "url", "pages", "text"}]}.
Usage: python collect/materials.py [--last 2] [--ids id,id]
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "vijecnica.db"
OUT = ROOT / "data" / "posts" / "materials.json"
UA = "vijecnica-research/0.1 (open data hackathon)"
PAGES, OCR_PAGES, KEEP = 12, 4, 12000  # pages read, pages OCRed for a scan, characters kept per document
GOOD = [(r"obrazlo", 6), (r"prijedlog", 4), (r"materijal", 3), (r"odluk|program|plan\b|izvje|pravilnik|proračun", 2)]
BAD = r"kopija plana|\bzk\b|izvadak|izjav|dopis|obrazac|savjetovanj|zapisnik|poziv|glasnik|mišljenje odbora|tablic"
_robots, _last = {}, {}


def score(name):
    n = name.lower()
    return sum(w for p, w in GOOD if re.search(p, n)) - (10 if re.search(BAD, n) else 0)


def get(url, cache):
    """Cached, polite GET: robots.txt per host, >= 1 s between requests to a host; a 403/429 stops that host."""
    f = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + Path(urllib.parse.urlsplit(url).path).suffix.lower()[:6])
    if f.exists():
        return f
    host = urllib.parse.urlsplit(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser(f"https://{host}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp.allow_all = True
        _robots[host] = rp
    if _robots[host] is None or not _robots[host].can_fetch(UA, url):
        raise PermissionError(f"not allowed: {url}")
    time.sleep(max(0.0, 1.0 - (time.time() - _last.get(host, 0))))
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _robots[host] = None  # blocked: leave this host alone
        raise
    finally:
        _last[host] = time.time()
    cache.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def text_of(f):
    """(text, pages) of a downloaded document; scans are OCRed (first pages), Word files via textutil."""
    head = f.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(f)], capture_output=True,
                                                               text=True).stdout or "Pages: 0").group(1))
        t = subprocess.run(["pdftotext", "-l", str(PAGES), "-layout", str(f), "-"], capture_output=True, text=True).stdout
        if len(re.sub(r"\s", "", t)) < 200 * min(pages, 2):  # a scan
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["pdftoppm", "-l", str(OCR_PAGES), "-r", "250", "-gray", "-png", str(f), f"{tmp}/p"],
                               check=True)
                t = "\f".join(subprocess.run(["tesseract", str(p), "-", "-l", "hrv", "--psm", "4"], capture_output=True,
                                             text=True, env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout
                              for p in sorted(Path(tmp).glob("p-*.png")))
        return t, pages
    if head.startswith(b"PK") or head.startswith(b"\xd0\xcf\x11\xe0"):  # docx / doc
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(f)], capture_output=True, text=True)
        return r.stdout, None
    return "", None


def squash(t):
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=2, help="latest N sessions with posts, per unit")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    posts = {p["id"]: p for p in json.loads((ROOT / "data" / "posts" / "posts.json").read_text())}
    for f in sorted((ROOT / "data" / "posts").glob("queue*.json")):  # posts not written yet (new units)
        posts.update({e["id"]: e for e in json.loads(f.read_text()) if e["id"] not in posts})
    posts = list(posts.values())
    if a.ids:
        posts = [p for p in posts if p["id"] in a.ids.split(",")]
    else:
        sessions = {}
        for p in posts:
            sessions.setdefault(p["city"], set()).add(p["session"])
        posts = [p for p in posts if p["kind"] == "item" and p["session"] in sorted(sessions[p["city"]])[-a.last:]]
    db = sqlite3.connect(DB)
    site = dict(db.execute("SELECT id, site FROM cities"))
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    ok = failed = 0
    for p in posts:
        if p["id"] in out:
            continue
        row = db.execute("SELECT attachments FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
                         (p["city"], p["session"], p["no"], p["sub"])).fetchone()
        docs = json.loads(row[0]) if row and row[0] else []
        docs = sorted((d for d in docs if score(d["name"]) > -5), key=lambda d: -score(d["name"]))[:2]
        got = []
        for d in docs:
            local = d["url"].startswith("manual/")  # downloaded by hand from the city's own link (Dubrovnik)
            url = d["url"] if local else urllib.parse.quote(urllib.parse.urljoin(site.get(p["city"], "") + "/", d["url"]),
                                                             safe=":/?=&%$#~+,;@")
            try:
                f = ROOT / "data" / p["city"] / url if local else get(url, ROOT / "data" / p["city"] / "raw" / "materials")
                t, pages = text_of(f)
            except Exception as e:
                print(f"   !! {p['id']}: {d['name'][:60]}: {e}")
                failed += 1
                continue
            if t.strip():
                got.append({"name": d["name"], "url": url, "pages": pages, "text": squash(t)[:KEEP]})
        out[p["id"]] = got
        ok += bool(got)
        print(f"{p['id']}: {len(got)} documents, {sum(len(g['text']) for g in got)} chars", flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{ok} of {len(posts)} posts with materials, {failed} documents failed")


if __name__ == "__main__":
    main()
