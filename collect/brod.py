"""Collect Slavonski Brod City Council (Gradsko vijeće Grada Slavonskog Broda) sessions, 2025-2029 term.

slavonski-brod.hr (Joomla): session pages with the agenda as nested <ol> and one PDF per item,
audio recordings (MP3) per session, minutes PDFs (near-verbatim, with attendance by name and vote
totals per decision; no per-member votes). HTML cache data/brod/raw/web, PDFs data/brod/raw/pdf,
MP3s data/brod/audio. Output: data/brod/docs/session_NN.json, data/brod/recordings.json.

Usage: python collect/brod.py [--audio]
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "brod"
HOST = "https://www.slavonski-brod.hr"
GV = "/gradska-uprava/gradsko-vijece"
UA = "vijecnica-research/0.1 (open data hackathon)"
_last = [0.0]


def get(path, binary=False, fresh=False):
    url = path if path.startswith("http") else HOST + urllib.parse.quote(path, safe="/?&=%.-_:")
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cache = D / "raw" / ("pdf" if binary else "web") / key
    if not cache.exists() or fresh:
        time.sleep(max(0, 1.0 - (time.time() - _last[0])))
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300).read()
        _last[0] = time.time()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return cache if binary else cache.read_text("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


class Agenda(HTMLParser):
    """Top-level <li> = item, nested <li> = sub-item (a, b, c …); keeps link text + href."""

    def __init__(self):
        super().__init__()
        self.depth, self.items, self.cur, self.text, self.href = 0, [], None, [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "ol":
            self.depth += 1
        elif tag == "li":
            self._flush()
            self.cur = {"depth": self.depth, "links": []}
        elif tag == "a" and self.cur is not None:
            self.href = a.get("href")

    def handle_endtag(self, tag):
        if tag == "ol":
            self._flush()
            self.depth -= 1
        elif tag == "a" and self.cur is not None and self.href:
            self.cur["links"].append({"name": " ".join("".join(self.text).split()), "url": self.href})
            self.href = None

    def handle_data(self, data):
        if self.cur is not None:
            self.text.append(data)

    def _flush(self):
        if self.cur is not None:
            t = " ".join("".join(self.text).split())
            if t:
                self.cur["title"] = t
                self.items.append(self.cur)
        self.cur, self.text = None, []


def agenda(page):
    m = re.search(r"D\s*N\s*E\s*V\s*N\s*I(?:&nbsp;|\s)*R\s*E\s*D", page, re.I)
    body = page[m.end():] if m else page[page.find("<ol"):]
    body = body[:body.find("Predsjednik Gradskog vijeća")] if "Predsjednik Gradskog vijeća" in body else body
    p = Agenda()
    p.feed(body)
    p._flush()
    items, no = [], 0
    for it in p.items:
        if it["depth"] <= 1:
            no += 1
            items.append({"no": no, "sub": 1, "title": it["title"], "attachments": it["links"], "children": []})
        elif items:
            items[-1]["children"].append({"title": it["title"], "attachments": it["links"]})
    out = []
    for it in items:
        kids = it.pop("children")
        it["full_title"] = it["title"] + ("".join(f" ({chr(97 + k)}) {c['title']}" for k, c in enumerate(kids)))
        it["attachments"] = it["attachments"] + [a for c in kids for a in c["attachments"]]
        out.append(it)
    return out


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


WORDNUM = {"jednim": 1, "jednom": 1, "jedan": 1, "dva": 2, "dvama": 2, "tri": 3, "četiri": 4}


def minutes_parse(text):
    """Attendance + a list of votes (with the text just before each, to match agenda items)."""
    flat = re.sub(r"\s+", " ", text)
    present = re.search(r"Nazočni vijećnici:\s*(.*?)\s*(?:(?:Nisu nazočni|Nije nazoč\w*):\s*(.*?)\s*)?Ostali nazočni", flat)
    # names only: drop page numbers that pdftotext leaves between lines
    names = lambda s: [n for n in (re.sub(r"\b\d+\b", "", x).strip() for x in re.split(r",| i ", s or "")) if n]
    att = ([{"name": n, "present": True} for n in names(present.group(1))] +
           [{"name": n, "present": False} for n in names(present.group(2))]) if present else []
    votes = []
    for m in re.finditer(r"Po provedenom glasovanju[^.]{0,60}?konstatira\w*\s+je,?\s+(?:da|kako)\s+je,?\s+"
                         r"(.{0,400}?)(?:prihvać|usvoj|odbij|nije|donese|izabran|imenovan)", flat):
        s = m.group(1)
        v = {"za": 0, "protiv": 0, "suzdrzano": 0}
        for num, kind in re.findall(r"(\d+|jednim|jednom|dva|tri)\s+glas\w*\s+\"?(za|protiv|suzdržan\w*)", s):
            k = "suzdrzano" if kind.startswith("suzd") else kind
            v[k] = int(num) if num.isdigit() else WORDNUM.get(num, 0)
        pres = re.search(r"od (\d+) nazočnih", s)
        v["present"] = int(pres.group(1)) if pres else None
        v["unanimous"] = "jednoglasno" in s
        tail = flat[m.end():m.end() + 160]
        v["result"] = "Prijedlog odbijen" if re.search(r"(odbij|nije)\w*$", flat[m.start():m.end() + 8]) else "Prijedlog usvojen"
        v["pos"] = m.start()
        v["context"] = flat[max(0, m.start() - 600):m.start()]
        v["after"] = tail
        votes.append(v)
    return att, votes, flat


def stem_set(t):
    return {w[:5] for w in re.findall(r"\w+", t.lower()) if len(w) > 3}


def attach_votes(items, votes, flat):
    """Minutes sections are headed 'TOČKA N.' in agenda order; a vote belongs to the last heading
    before it (votes before TOČKA 1 are on the minutes and the agenda itself)."""
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r"TOČKA (\d+)\.", flat)]
    by_no = {it["no"]: it for it in items}
    for v in votes:
        prev = [h for h in heads if h[0] < v["pos"]]
        best = by_no.get(prev[-1][1]) if prev else None
        if best is not None:
            best.setdefault("votes", []).append(
                {k: v[k] for k in ("za", "protiv", "suzdrzano", "present", "unanimous", "result")})
    for it in items:
        if it.get("votes"):
            last = it["votes"][-1]
            it["vote"] = {"za": last["za"], "protiv": last["protiv"], "suzdrzano": last["suzdrzano"],
                          "result": last["result"], "members": {}}


def members(known):
    """Council roster with parties (members page table); names spelled as in the minutes when close."""
    from difflib import SequenceMatcher
    page = get(f"{GV}/251-clanovi-gradskog-vijeca", fresh=True)
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        tds = [clean(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        tds = [t for t in tds if t]
        if len(tds) < 3 or not re.fullmatch(r"\d+\.", tds[0]):
            continue
        party = tds[-1]
        for cell in tds[1:-1]:
            # a cell holds "Name Role" (e.g. "Tomislav Tekić Član Gradskog vijeća Hrvoje Špicer Zamjenski član")
            for name in re.findall(r"([A-ZČĆŠŽĐ][a-zčćšžđ]+(?:[ -][A-ZČĆŠŽĐ][a-zčćšžđ]+){1,3}?)\s+"
                                   r"(?:Član|Članica|Predsjedni|Potpredsjedni|Zamjensk)", cell):
                best = max(known, key=lambda k: SequenceMatcher(None, k, name.replace("-", " ")).ratio(),
                           default=name)
                if SequenceMatcher(None, best, name.replace("-", " ")).ratio() > 0.85:
                    name = best
                out.append({"name": name, "party": party})
    return out


def main(download_audio=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    idx = get(f"{GV}/289-sjednice-gv", fresh=True)
    sessions = re.findall(r'href="(/gradska-uprava/gradsko-vijece/469-sjednice-gv/sjednice-2025-2029/[^"]+)"', idx)
    sessions = list(dict.fromkeys(sessions))
    mins = {}
    for u in re.findall(r'href="(/images/Zapisnici/Vijece/\d{4}/(\d+)_sjednica\.pdf)"',
                        get(f"{GV}/308-pisani-zapisnici", fresh=True)):
        mins[int(u[1])] = u[0]
    rec_index = get(f"{GV}/290-tonski-zapisi-o-radu-sjednica-gradskog-vijeca", fresh=True)
    rec_pages = list(dict.fromkeys(re.findall(r'href="([^"]*343-tonski[^"]*/snimke/[^"]+)"', rec_index)))
    recordings = []
    for rp in rec_pages:
        page = get(rp)
        n = re.search(r"/2025_2029/(\d+)/", page)
        sess = int(n.group(1)) if n else 1
        date = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})$", rp)
        for k, mp3 in enumerate(dict.fromkeys(re.findall(r'src="([^"]+\.mp3)"', page)), 1):
            recordings.append({"id": f"brod-{sess:02d}-{k}", "session": sess, "part": k,
                               "url": HOST + urllib.parse.quote(mp3),
                               "date": f"{date.group(3)}-{int(date.group(2)):02d}-{int(date.group(1)):02d}" if date else None,
                               "title": clean(re.search(r"<title>(.*?)</title>", page, re.S).group(1))})
    for pos, sp in enumerate(sessions):
        page = get(sp, fresh=True)
        n = len(sessions) - pos  # the index lists the term's sessions newest first
        title = clean(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
        when = re.search(r"(\d{1,2})\.\s*([A-ZČĆŠŽ]+)\s+(\d{4})", clean(page).upper())
        items = agenda(page)
        doc = {"session": n, "title": title, "items": items, "attendance": [], "questions": [],
               "minutes_url": mins.get(n), "url": HOST + sp}
        if doc["minutes_url"]:
            text = pdf_text(get(doc["minutes_url"], binary=True))
            att, votes, flat = minutes_parse(text)
            doc["attendance"] = att
            doc["minutes_text"] = text
            attach_votes(items, votes, flat)
            d = re.search(r"održane (\d{1,2})\. (\w+) (\d{4})", flat)
            doc["votes_in_minutes"] = len(votes)
        for it in items:
            it.setdefault("proposer", "")
            it.setdefault("status", "prihvaćen" if it.get("vote", {}).get("result") == "Prijedlog usvojen" else None)
            it["url"] = doc["url"]
        rec = [r for r in recordings if r["session"] == n]
        doc["date"] = rec[0]["date"] if rec else None
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        print(f"brod session {n}: {len(items)} items, {sum(1 for i in items if i.get('vote'))} with votes "
              f"({doc.get('votes_in_minutes', 0)} votes in minutes), {len(doc['attendance'])} members, "
              f"minutes {'yes' if doc['minutes_url'] else 'no'}, recordings {len(rec)}", flush=True)
    old = {r["id"]: r for r in json.loads((D / "recordings.json").read_text())} if (D / "recordings.json").exists() else {}
    for r in recordings:  # keep durations measured earlier (ffprobe on the downloaded MP3)
        if old.get(r["id"], {}).get("duration"):
            r["duration"] = old[r["id"]]["duration"]
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    known = sorted({a["name"] for f in (D / "docs").glob("session_*.json")
                    for a in json.loads(f.read_text())["attendance"]})
    roster = members(known)
    (D / "members.json").write_text(json.dumps(roster, ensure_ascii=False, indent=1))
    print(f"members: {len(roster)} with parties", flush=True)
    if download_audio:
        (D / "audio").mkdir(exist_ok=True)
        for r in recordings:
            out = D / "audio" / f"{r['id']}.mp3"
            if not out.exists():
                print("download", r["id"], r["url"], flush=True)
                tmp = out.with_suffix(".part")
                urllib.request.urlretrieve(r["url"], tmp)
                tmp.rename(out)


if __name__ == "__main__":
    main("--audio" in sys.argv)
