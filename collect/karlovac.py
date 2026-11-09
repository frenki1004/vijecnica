"""Karlovac city council (Gradsko vijeće Grada Karlovca), 2025-2029 term, from www.karlovac.hr.

Sources (all on www.karlovac.hr, a WordPress site):
- The session posts (post type "sjednica_vijeca", listed through the site's REST API /wp-json/wp/v2/sjednica_vijeca)
  link two files: the agenda ("Dnevni red N. sjednica GV.docx") and one ZIP with all materials of the session
  ("N.-sjednica-GV-<date>.zip": a folder per agenda item).
- The city publishes no minutes page. The minutes of a session ("Skraćeni zapisnik", a Word file with the proposed
  conclusion to adopt it) travel inside the materials ZIP of a later session (usually the next one), as the first
  agenda item "Zapisnik s N. sjednice GV". Only that member is read: the ZIP is opened through HTTP range requests
  (central directory + the one member), cached under raw/zip; the materials themselves are not downloaded.

The minutes are clean text. After "TOČKA N." comes the item title and then one fixed vote formula:
  Nakon provedene rasprave, od nazočnih 19 vijećnika u vijećnici, vijeće je sa 11 glasova ZA, 6 glasova PROTIV i
  2 glasa SUZDRŽANA donijelo:
  Budući da nije bilo rasprave od nazočnih 18 vijećnika u vijećnici, vijeće je sa 18 glasova ZA donijelo:
A category the formula does not name stays null (the minutes give no number for it; it is not inferred from the
number present). Items come from the minutes ("TOČKA N." sections); sessions without minutes yet (the latest) get
the agenda Word file's items, without votes. The ceremonial session (svečana) has no agenda items.

Recordings: the city's YouTube channel (linked from the home page) streams every session; its "streams" tab is
listed once with yt-dlp (titles only, nothing is downloaded; cached in raw/web/youtube_streams.tsv). The listing is
newest first; the current term's streams are the ones before the numbering jumps back up (48. of the old term
after 1. of this one). A session streamed twice (a broken stream restarted) gets parts 1, 2 in upload order.

Output: data/karlovac/docs/session_NN.json (format of collect/cakovec.py; extra keys "agenda_url",
"materials_url"). Cache: data/karlovac/raw/web (HTML/JSON), raw/zip (ZIP directory + extracted minutes),
raw/doc (agenda files).

Usage: python collect/karlovac.py [--fresh]
"""
import hashlib
import html
import os
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "karlovac"
HOST = "https://www.karlovac.hr"
API = "/wp-json/wp/v2/sjednica_vijeca?per_page=100&after=2025-05-01T00:00:00"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
SEATS = 21
GEN = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                   "listopada studenoga prosinca").split(), 1)}
GEN["studenog"] = 11
HEAD = re.compile(r"^[ \t]*TOČKA\s+(\d+)\.?[ \t]*$", re.M)
N = r"(\d+)"
VOTE = re.compile(rf"(?:(?:od\s+nazočnih|uz\s+nazočnost)\s+{N}\s+vijećnika[^,]*,\s*)?vijeće\s+je\s+sa?\s+{N}\s+glas\w*"
                  rf"(?:\s+ZA)?(?:(?:,|\s+i)\s+{N}\s+glas\w*\s+PROT\w*)?(?:(?:,|\s+i)\s+{N}\s+glas\w*\s+SUZD\w*)?"
                  rf"\s+(?:(nije\s+)?don\w*|usvoj\w*|prihvati\w*|(glasal\w*))", re.I)
ELECTED = re.compile(rf"(?:uz\s+nazočnost\s+{N}\s+vijećnika,\s*)?(?:izabran\w*|usvojen\w*|donesen\w*)\s+je\s+jednoglasno"
                     rf"\s+sa?\s+{N}\s+glas\w*\s+ZA", re.I)  # "... izabrana je jednoglasno s 21 glasom ZA"
_robots, _last = None, [0.0]


def _open(url, headers=None, method="GET"):
    global _robots
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0.0, 1.1 - (time.time() - _last[0])))
    try:  # a block (403/429) raises and stops the run; it is never retried
        r = urllib.request.urlopen(urllib.request.Request(url, method=method,
                                                          headers={"User-Agent": UA, **(headers or {})}), timeout=120)
        return r.headers if method == "HEAD" else r.read()
    finally:
        _last[0] = time.time()


def get(url, sub="web", ext=".html", fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests); returns text for web pages, a path otherwise."""
    url = urllib.parse.urljoin(HOST, url)
    f = D / "raw" / sub / (hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if not f.exists() or fresh:
        data = _open(url)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return f.read_text() if sub == "web" else f


class RangeFile(io.RawIOBase):
    """Read-only file over HTTP range requests (blocks of 256 KB, kept in memory) for zipfile."""
    BLOCK = 1 << 18

    def __init__(self, url):
        self.url, self.pos, self.blocks = url, 0, {}
        self.size = int(_open(url, method="HEAD")["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _block(self, b):
        if b not in self.blocks:
            lo = b * self.BLOCK
            hi = min(self.size, lo + self.BLOCK) - 1
            self.blocks[b] = _open(self.url, {"Range": f"bytes={lo}-{hi}"})
        return self.blocks[b]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        out = bytearray()
        while n > 0:
            b, o = divmod(self.pos, self.BLOCK)
            chunk = self._block(b)[o:o + n]
            if not chunk:
                break
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, buf):
        data = self.read(len(buf))
        buf[:len(data)] = data
        return len(data)


def zip_members(url, fresh=False):
    """Member names of a remote ZIP (cached as JSON)."""
    f = D / "raw" / "zip" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")
    if not f.exists() or fresh:
        with zipfile.ZipFile(RangeFile(url)) as z:
            names = [fix_name(i) for i in z.infolist()]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(names, ensure_ascii=False))
    return json.loads(f.read_text())


def fix_name(info):
    """Zip member names written by Windows tools without the UTF-8 flag are cp852/cp1250, not cp437."""
    n = info.filename
    if info.flag_bits & 0x800:
        return n
    raw = n.encode("cp437")
    for enc in ("utf-8", "cp852", "cp1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return n


def zip_member(url, name):
    """Extract one member of a remote ZIP (by its decoded name) into raw/zip; returns the local path."""
    suffix = Path(name).suffix.lower()
    f = D / "raw" / "zip" / (hashlib.sha1((url + "#" + name).encode()).hexdigest()[:16] + suffix)
    if not f.exists():
        with zipfile.ZipFile(RangeFile(url)) as z:
            info = next(i for i in z.infolist() if fix_name(i) == name)
            f.write_bytes(z.read(info))
    return f


def doc_text(path):
    """Text of a Word (textutil) or PDF (pdftotext) file."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    t = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True, text=True).stdout
    return t.replace("\u2028", "\n").replace("\u2029", "\n")  # Word's manual line breaks


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ---------------------------------------------------------------- sources

def sessions(fresh):
    """[(number, title, url, kind)] from the REST API; kind: '', 'svečana', 'izvanredna', 'tematska'."""
    out = []
    for p in json.loads(get(API, ext=".json", fresh=fresh)):
        t = flat(p["title"]["rendered"])
        m = re.match(r"(\d+)\.", t)
        if not m:
            continue
        kind = next((k for k in ("svečana", "izvanredna", "tematska", "konstituirajuća") if k in t.lower()), "")
        out.append((int(m.group(1)), t, p["link"], kind, p["date"][:10]))
    return sorted(out)


def session_files(page):
    """(agenda docx url, materials zip url) of a session post."""
    links = re.findall(r"""href=["'](https?://[^"']+/wp-content/uploads/[^"']+)["']""", page)
    agenda = next((u for u in links if re.search(r"dnevni", u, re.I) and re.search(r"\.docx?$|\.pdf$", u, re.I)), None)
    zp = next((u for u in links if u.lower().endswith(".zip")), None)
    return agenda, zp


def minutes_in_zip(names):
    """{session number: member name} of minutes carried by a materials ZIP."""
    out = {}
    for n in names:
        base = n.rsplit("/", 1)[-1]
        if re.search(r"\.(docx?|pdf)$", base, re.I) and re.search(r"zapisnik", base, re.I) \
                and not re.search(r"odbor|povjerenstv|savjet", n, re.I):
            m = re.search(r"(\d+)\s*\.?\s*(?:\(?\w+\)?\s+)?sjednic", base, re.I)
            if m:
                k = int(m.group(1))
                proper = re.match(r"(?:skraćeni\s+)?zapisnik", base, re.I)  # not "Zaključak - zapisnik ..."
                if k not in out or proper and not re.match(r"(?:skraćeni\s+)?zapisnik", out[k].rsplit("/", 1)[-1], re.I):
                    out[k] = n
    return out


# ---------------------------------------------------------------- parsing

def minutes_date(text):
    m = re.search(r"(?:sjednice|sjednica)[^\n]{0,80}?održane\s+dana\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})", text)
    return f"{m.group(3)}-{GEN.get(m.group(2).lower(), 0):02d}-{int(m.group(1)):02d}" \
        if m and m.group(2).lower() in GEN else None


def body_start(text):
    """Start of the minutes proper (after the cover conclusion that adopts them)."""
    m = re.search(r"^\s*(?:SKRAĆENI\s+)?Z\s*A\s*P\s*I\s*S\s*N\s*I\s*K\b", text, re.M)
    return m.start() if m else 0


def headings(text, items):
    """[(pos, item)]: each "TOČKA N." heading with its item."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def vote_of(m, title):
    za = int(m.group(2))
    protiv = int(m.group(3)) if m.group(3) else None
    suzd = int(m.group(4)) if m.group(4) else None
    if m.group(6):  # "... glasalo o navedenom prijedlogu" (elections): the formula names no outcome
        result = YES if za * 2 > za + (protiv or 0) + (suzd or 0) else NO
    else:
        result = NO if m.group(5) or (protiv is not None and za <= protiv) else YES
    q = re.sub(r"\s+", " ", m.group(0))
    return {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
            "unanimous": False, "quote": q[:300]}


def minutes_items(text):
    """Items and votes from the minutes: one per "TOČKA N." section, titled by the line after the heading."""
    heads, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        if n < last or any(h[1] == n for h in heads):
            continue
        last = n
        tail = text[m.end():m.end() + 1500].strip().split("\n")
        title = re.sub(r"\s+", " ", tail[0]).strip().rstrip(",;")
        if title.isupper():  # the constituent session's headings are in capitals
            title = title[0] + title[1:].lower().replace("grada karlovca", "Grada Karlovca") \
                .replace("gradskog vijeća", "Gradskog vijeća").replace("gradskoga vijeća", "Gradskoga vijeća")
        heads.append((m.start(), n, title))
    items = []
    for i, (pos, n, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        sec = text[pos:end]
        it = {"no": n, "sub_label": None, "title": title, "full_title": title, "attachments": []}
        votes = []
        for m in VOTE.finditer(sec):
            if re.search(r"amandman", sec[m.end():m.end() + 100], re.I) \
                    or re.search(r"glasovanje\s+(?:\w+\s+){0,2}amandman", sec[max(0, m.start() - 200):m.start()], re.I):
                continue  # an amendment vote ("... glasalo za predloženi amandman"), not the item's
            v = vote_of(m, title)
            if not (1 <= v["za"] + (v["protiv"] or 0) + (v["suzdrzano"] or 0) <= SEATS):
                continue
            votes.append(v)
        for m in ELECTED.finditer(sec):
            votes.append({"za": int(m.group(2)), "protiv": 0, "suzdrzano": 0, "result": YES, "members": {},
                          "unanimous": True, "quote": re.sub(r"\s+", " ", m.group(0))[:300]})
        jm = re.search(r"[^.\n]*\bvijeće\s+je\s+jednoglasno[^.\n]*", sec, re.I)  # not "Odbor je jednoglasno"
        if not votes and jm:
            votes.append({"za": None, "protiv": 0, "suzdrzano": 0, "result": YES, "members": {},
                          "unanimous": True, "quote": re.sub(r"\s+", " ", jm.group(0)).strip()[:300]})
        if votes:
            it["vote"], it["votes"] = votes[-1], votes
        items.append(it)
    return items


def agenda_items(text):
    """Agenda items of a "Dnevni red" Word file (numbered or bulleted lines after "DNEVNI RED")."""
    m = re.search(r"D\s*N\s*E\s*V\s*N\s*I\s+R\s*E\s*D", text)
    body = text[m.end():] if m else text
    items, no = [], 0
    for ln in body.split("\n"):
        mm = re.match(r"^(?:•|\d+\.|-)\s*(.+)", ln.strip())
        if mm and len(mm.group(1)) > 8:
            no += 1
            title = mm.group(1).strip().rstrip(",;")
            items.append({"no": no, "sub_label": None, "title": title, "full_title": title, "attachments": []})
    return items


CHANNEL = "https://www.youtube.com/channel/UCaWDuKZyEEUUouNAkMWIhNA"
YTDLP = [os.path.expanduser("~/.local/bin/yt-dlp"), "--js-runtimes", "node", "--no-warnings"]


def recordings(rows, dates, fresh=False):
    """[{id, session, part, date, url, kind, title}] of this term's session streams on the city's YouTube channel."""
    f = D / "raw" / "web" / "youtube_streams.tsv"
    if not f.exists() or fresh:
        out = subprocess.run(YTDLP + ["--flat-playlist", "--print", "%(id)s\t%(title)s", CHANNEL + "/streams"],
                             capture_output=True, text=True, check=True).stdout
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(out)
    ceremonial = [n for n, t, u, kind, p in rows if kind == "svečana"]  # oldest first
    found, last = [], 10 ** 6
    for line in f.read_text().splitlines():  # newest first
        vid, title = line.split("\t", 1)
        if not re.search(r"sjednic\w*\s+Gradskog\s+vijeća", title, re.I):
            continue
        m = re.match(r"\s*(\d+)\.", title)
        if m:
            n = int(m.group(1))
            if n > last:  # the previous term begins
                break
            last = n
        elif "svečana" in title.lower():
            n = next((c for c in reversed(ceremonial) if c <= last and c not in [x[0] for x in found]), None)
            if n is None:
                continue
        else:
            continue
        found.append((n, vid, title))
    out = []
    for n in sorted({x[0] for x in found}):
        vids = [x for x in found if x[0] == n][::-1]  # upload order
        for p, (_, vid, title) in enumerate(vids, 1):
            out.append({"id": f"karlovac-{n:02d}-{p}", "session": n, "part": p, "date": dates.get(n),
                        "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube", "title": title})
    return out


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    rows = sessions(fresh)
    pages = {}
    for n, title, url, kind, posted in rows:
        page = get(url, fresh=fresh)
        pages[n] = session_files(page)
    minutes = {}
    for n, (agenda, zp) in sorted(pages.items()):
        if not zp:
            continue
        for k, name in minutes_in_zip(zip_members(zp, fresh=fresh)).items():
            if k < n:  # a ZIP carries the minutes of earlier sessions
                minutes.setdefault(k, (zp, name))
    dates = {}
    for n, title, url, kind, posted in rows:
        agenda, zp = pages[n]
        text, murl = None, None
        if n in minutes:
            zurl, name = minutes[n]
            text = doc_text(zip_member(zurl, name))
            text = text[body_start(text):]
            murl = zurl + "#" + name
        if text:
            items = minutes_items(text)
        elif agenda:
            items = agenda_items(doc_text(get(agenda, sub="doc", ext=Path(agenda).suffix.lower())))
        else:
            items = []
        found = len(VOTE.findall(text)) + len(ELECTED.findall(text)) if text else 0
        for it in items:
            v = it.get("vote")
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        date = (text and minutes_date(text)) or zip_date(zp) or posted
        doc = {"session": n, "title": f"{title} Grada Karlovca", "date": date, "url": url, "minutes_url": murl,
               "minutes_text": text, "agenda_url": agenda, "materials_url": zp, "items": items,
               "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        dates[n] = date
        nv = sum(1 for i in items if i.get("vote"))
        print(f"karlovac session {n} ({date}, {kind or 'redovna'}): {len(items)} items, {nv} with votes "
              f"({found} formulas), minutes {'yes' if text else 'no'}", flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}. {it['title'][:90]}", flush=True)
    recs = recordings(rows, dates, fresh)
    (D / "recordings.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"karlovac recordings: {len(recs)} streams for sessions {sorted({r['session'] for r in recs})}")


def zip_date(zp):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\.zip$", zp or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


if __name__ == "__main__":
    main("--fresh" in sys.argv)
