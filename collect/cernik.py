"""Cernik municipal council (Općinsko vijeće Općine Cernik), 2025-2029 term, from cernik.hr.

Source: cernik.hr/wp/zapisnici/ lists the minutes as PDFs ("Zapisnik - 10. sjednica Općinskog vijeća - 05.05.2026.").
For this term only sessions 8, 9 and 10 are published (none of 1-7, nothing after May 2026); no agendas, materials
or recordings are on the site. Decisions appear in the Službeni glasnik (cernik.hr/wp/sluzbeni-glasnik/).
robots.txt: none (404 on www.cernik.hr and cernik.hr).

The minutes (text-layer PDFs) are short summaries: one "Točka N. <title>" section per item, and the vote is a bare
"Jednoglasno se donosi" / "jednoglasno se prihvaća" / "jednoglasno je usvojen" with no numbers, so every vote is
za null, protiv 0, suzdržano 0. Items come from the "Točka N." headings (the agenda list above them is
irregular); votes before "Točka 1." (agenda, previous minutes) are skipped.

Output: data/cernik/docs/session_NN.json (format of collect/cakovec.py). Cache: data/cernik/raw/.
Usage: python collect/cernik.py [--fresh]
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "cernik"
HOST = "https://cernik.hr"
INDEX = HOST + "/wp/zapisnici/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES = "Prijedlog usvojen"
TERM_START = "2025-06-01"
LINK = re.compile(r"""<a[^>]+href=["']([^"']+\.pdf)["'][^>]*>(?:\s|<(?!/a)[^>]*>)*Zapisnik\s*-\s*(\d+)\.\s*sjednica"""
                  r"""[^<]*?(\d\d)\.(\d\d)\.(\d{4})""", re.I)  # Elementor list: icon <span>s before the text
HEAD = re.compile(r"^[ \t\f]*Točka\s+(\d+)\.?[ \t]+(\S[^\n]*)", re.M)
UNAN = re.compile(r"jednoglasno\s+(?:se\s+)?(?:je\s+)?(?:donosi|usvaja|uvaja|prihvaća|usvo\w*|donesen\w*|prihvaćen\w*)", re.I)
_robots, _last = None, [0.0]


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests, no retry on 403/429)."""
    global _robots
    f = D / "raw" / ("pdf" if binary else "web") / (hashlib.sha1(url.encode()).hexdigest()[:16] +
                                                     (".pdf" if binary else ".html"))
    if f.exists() and not fresh:
        return f if binary else f.read_text("utf-8", "replace")
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0, 1.1 - (time.time() - _last[0])))
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f if binary else data.decode("utf-8", "replace")


def headings(text, items):
    """[(pos, item)]: each "Točka N." section heading with its item."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def parse(text, url):
    items, seen, last = [], set(), 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        if n in seen or n < last or n > len(items) + 3:  # repeated, or a typo ("Točka 13. Različito" after 1.)
            continue
        seen.add(n)
        last = n
        nxt = text[m.end():].lstrip(" \t").split("\n")[1:2]  # the heading's wrapped second line, if any
        cont = nxt[0].strip() if nxt and re.match(r"[a-zčćšžđ0-9]", nxt[0].strip()) else ""
        title = re.sub(r"\s+", " ", m.group(2) + " " + cont).strip().rstrip(" -")
        title = re.sub(r"(\w)- (\w)", r"\1\2", title)  # hyphenation
        items.append({"no": n, "sub_label": None, "title": title, "full_title": title, "proposer": "",
                      "status": None, "url": url, "attachments": []})
    heads = headings(text, items)
    found = matched = 0
    for k, (pos, it) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(text)
        hits = list(UNAN.finditer(text, pos, end))
        found += len(hits)
        if hits:
            q = re.sub(r"\s+", " ", text[hits[0].start():hits[0].end() + 160]).strip()
            vote = {"za": None, "protiv": 0, "suzdrzano": 0, "result": YES, "members": {}, "unanimous": True,
                    "quote": q[:300]}
            it["vote"], it["votes"], it["status"] = vote, [vote], "prihvaćen"
            matched += len(hits)
    return items, found, matched


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    page = get(INDEX, fresh=fresh)
    for url, n, d, mth, y in LINK.findall(page):
        date, n = f"{y}-{mth}-{d}", int(n)
        if date < TERM_START:
            continue
        text = subprocess.run(["pdftotext", "-layout", str(get(html.unescape(url), binary=True, fresh=fresh)), "-"],
                              capture_output=True, text=True).stdout
        items, found, matched = parse(text, url)
        total = len(UNAN.findall(text))
        doc = {"session": n, "title": f"{n}. sjednica Općinskog vijeća Općine Cernik", "date": date, "url": INDEX,
               "minutes_url": url, "minutes_text": text, "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"cernik session {n} ({date}): {len(items)} items, {nv} with votes ({total} formulas in text, "
              f"{found} in item sections, {matched} matched)", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
