"""Marija Gorica municipal council (Općinsko vijeće Općine Marija Gorica), 2025-2029 term, from www.marija-gorica.hr.

Source: /index.php/hr/dokumenti/sjednice ("Sjednice - Odluke / Izvješća") links one material package per session:
"Materijali za N. sjednicu Općinskog vijeća", either a .zip/.rar archive or an article page with the PDFs. A
package holds the convocation (Poziv) of session N and the minutes (Zapisnik) of the previous session, so the
minutes of session N come from the package of session N+1. Packages for sessions 6 and 7 are not published, so the
minutes of sessions 2, 3, 5 and 6 are missing; the latest session's minutes appear only with the next package.
No recordings of sessions; the YouTube channel has promotional videos. robots.txt: none (404).

The minutes (text-layer PDFs; the constituent session's is a scan, OCR with tesseract hrv) have one
"AD N) <title>" section per item; votes are "Članovi vijeća jednoglasno su usvojili ..." with no numbers, so
za null, protiv 0, suzdržano 0. Votes before "AD 1)" (previous minutes, agenda) are skipped.

Output: data/marijagorica/docs/session_NN.json (format of collect/cakovec.py). Cache: data/marijagorica/raw/.
Usage: python collect/marijagorica.py [--fresh]
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "marijagorica"
HOST = "https://www.marija-gorica.hr"
INDEX = HOST + "/index.php/hr/dokumenti/sjednice"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
PKG = re.compile(r"""<a[^>]+href=["']([^"']+)["'][^>]*>\s*-?\s*Materijali\s+za\s+(\d+)\.\s*sjednicu""", re.I)
HEAD = re.compile(r"^[ \t\f]*AD\s+(\d+)\s*\)[ \t]*(\S[^\n]*)", re.M)
VOTE = re.compile(r"(?:Članovi|vijećnici)\s+(?:Općinskog\s+)?vijeća\s+(?:su\s+)?(?P<how>jednoglasn\w*|većinom\s+glasova)"
                  r"\s+(?:su\s+)?(?P<verb>usvojili|donijeli|prihvatili|odbili|izabrali|imenovali|dali)\s+(?P<act>[^\n]*(?:\n[^\n]+){0,2})",
                  re.I)
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
VOTE2 = re.compile(r"jednoglasno\s+sa?\s+(?P<za>\d+)\s+glas\w*\s+ZA\b(?P<act>[^\n]*)")  # the constituent session (OCR)
_robots, _last = None, [0.0]


def get(url, ext="html", fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests, no retry on 403/429)."""
    global _robots
    f = D / "raw" / ext / (hashlib.sha1(url.encode()).hexdigest()[:16] + "." + ext)
    if f.exists() and not fresh:
        return f
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0, 1.1 - (time.time() - _last[0])))
    try:
        data = urllib.request.urlopen(urllib.request.Request(urllib.parse.quote(url, safe=":/?&=%"),
                                                             headers={"User-Agent": UA}), timeout=300).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def pdf_text(path):
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) > 200:
        return t
    cache = D / "raw" / "ocr" / (hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16] + ".txt")
    if not cache.exists():
        pages = []
        (D / "raw").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            for png in sorted(Path(tmp).glob("p-*.png")):
                pages.append(subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"],
                                            capture_output=True, text=True,
                                            env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\f".join(pages))
    return cache.read_text()


def packages(fresh):
    """[(session, url)] of the current term: the index lists newest first, the previous term starts where the
    session number goes up again (… 3, 2, 30, 29 …)."""
    page = get(INDEX, fresh=fresh).read_text("utf-8", "replace")
    out, prev = [], None
    for url, n in PKG.findall(page):
        n = int(n)
        if prev is not None and n >= prev:
            break
        out.append((n, urllib.parse.urljoin(HOST, html.unescape(url))))
        prev = n
    return out


def minutes_files(n, url, fresh):
    """[(minutes session, file path, source url)] in the package of session n."""
    ext = url.rsplit(".", 1)[-1].lower()
    out = []
    if ext in ("zip", "rar"):
        arch = get(url, ext=ext, fresh=fresh)
        names = subprocess.run(["bsdtar", "-tf", str(arch)], capture_output=True, text=True).stdout.splitlines()
        for name in names:
            if re.search(r"zapisnik", name, re.I) and name.lower().endswith(".pdf"):
                dest = D / "raw" / "x" / f"{n}" / Path(name).name
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
                        subprocess.run(["bsdtar", "-xf", str(arch), "-C", tmp, name], check=True)
                        (Path(tmp) / name).rename(dest)
                m = re.search(r"(\d+)\.?\s*sjednice", Path(name).name)
                k = int(m.group(1)) if m else (1 if "konstituir" in name.lower() else n - 1)
                out.append((k, dest, url))
    else:  # an article page with the PDFs
        page = get(url, fresh=fresh).read_text("utf-8", "replace")
        for href in re.findall(r"""href=["']([^"']*Zapisnik[^"']*\.pdf)["']""", page, re.I):
            u = urllib.parse.urljoin(HOST, html.unescape(href))
            m = re.search(r"(\d+)_?\.?\s*sjednice", Path(u).name)
            out.append((int(m.group(1)) if m else n - 1, get(u, ext="pdf", fresh=fresh), u))
    return out


def headings(text, items):
    """[(pos, item)]: each "AD N)" section heading with its item."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def parse(text, url):
    items, seen = [], set()
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        if n in seen:
            continue
        seen.add(n)
        nxt = text[m.end():].split("\n")[1:2]
        cont = nxt[0].strip() if nxt and nxt[0].strip() and not re.match(r"Predsjedni|Vijećnicima", nxt[0].strip()) \
            else ""
        title = re.sub(r"\s+", " ", m.group(2) + " " + cont).strip()
        items.append({"no": n, "sub_label": None, "title": title, "full_title": title, "proposer": "",
                      "status": None, "url": url, "attachments": []})
    heads = headings(text, items)
    found = matched = 0
    for k, (pos, it) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(text)
        for m in sorted([*VOTE.finditer(text, pos, end), *VOTE2.finditer(text, pos, end)], key=lambda m: m.start()):
            found += 1
            act = re.sub(r"\s+", " ", m.group("act"))
            if re.match(r"(?:\w+\s+){0,3}amandman", act, re.I):
                continue
            za = int(m.group("za")) if "za" in m.groupdict() else None
            unan = za is not None or m.group("how").lower().startswith("jednoglasn")
            rejected = za is None and m.group("verb").lower() == "odbili"
            vote = {"za": za, "protiv": 0 if unan else None, "suzdrzano": 0 if unan else None,
                    "result": NO if rejected else YES, "members": {}, "unanimous": unan and not rejected,
                    "quote": re.sub(r"\s+", " ", m.group(0))[:300]}
            it.setdefault("votes", []).append(vote)
            matched += 1
    # a missing "AD N)" heading puts two items' votes in one section: the extra vote is the missing item
    for k, (pos, it) in enumerate(heads):
        nxt = heads[k + 1][1]["no"] if k + 1 < len(heads) else None
        if nxt is not None and nxt == it["no"] + 2 and len(it.get("votes", [])) == 2:
            v = it["votes"].pop()
            title = re.sub(r"^prijedlog\s+", "", re.split(r"\.\s", v["quote"].split(" usvojili ", 1)[-1])[0],
                           flags=re.I).strip()
            title = title[0].upper() + title[1:]
            items.insert(items.index(it) + 1, {"no": it["no"] + 1, "sub_label": None, "title": title,
                                               "full_title": title, "proposer": "", "status": None, "url": url,
                                               "attachments": [], "votes": [v]})
    for it in items:
        if it.get("votes"):
            it["vote"] = it["votes"][-1]
            it["status"] = "prihvaćen" if it["vote"]["result"] == YES else "nije prihvaćen"
    total = len(VOTE.findall(text)) + len(VOTE2.findall(text))
    return items, total, found, matched


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    pk = packages(fresh)
    print("packages:", ", ".join(f"{n}" for n, _ in pk), flush=True)
    for n, url in pk:
        for k, path, src in minutes_files(n, url, fresh):
            text = pdf_text(path)
            items, total, found, matched = parse(text, src)
            d = re.search(r"održane\s+(?:u\s+\w+,?\s+)?(\d{1,2})\.\s*(\w+)\s+(\d{4})", text[:1500])
            date = f"{d.group(3)}-{MONTHS.get(d.group(2), 0):02d}-{int(d.group(1)):02d}" if d else None
            doc = {"session": k, "title": f"{k}. sjednica Općinskog vijeća Općine Marija Gorica", "date": date,
                   "url": url, "minutes_url": src if src.endswith(".pdf") else f"{src}#{path.name}",
                   "minutes_text": text, "items": items, "attendance": [], "questions": []}
            (D / "docs" / f"session_{k:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
            nv = sum(1 for i in items if i.get("vote"))
            print(f"marijagorica session {k} ({date}): {len(items)} items, {nv} with votes ({total} formulas in "
                  f"text, {found} in item sections, {matched} matched), from package {n}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
