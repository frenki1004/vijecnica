"""Sveti Juraj na Bregu municipal council (Općinsko vijeće Općine Sveti Juraj na Bregu), 2025-2029 term.

Source: www.svetijurajnabregu.hr/dokumenti-sazivi-i-zapisnici/ lists, as "Download" links, the convocations ("Saziv",
.docx/.pdf) and minutes ("Zapisnik", .doc/.docx) of every session; file names carry the date and session number
("2026_08_31-Zapisnik-11-sjednica-OV.doc"). robots.txt only disallows /wordpress/wp-admin/.

The minutes (Word, converted with macOS textutil) open with the agenda ("DNEVNI RED:", one item per line, unnumbered)
and then one "Točka N." section per item. Each vote is one sentence:
  "... dala je na glasovanje Prijedlog Odluke o ..., vijećnici su jednoglasno s 10 glasova „za“, donijeli:"
Items come from the agenda; a vote goes to the item whose title it names (word overlap), else to the "Točka N."
section it is in. "jednoglasno s N glasova za" -> za N, protiv 0, suzdržano 0; "s N glasova za" alone -> protiv and
suzdržano null (never inferred from attendance). Votes before "Točka 1." (agenda adoption) are skipped.
Ceremonial sessions (svečana sjednica) have a convocation only.

Output: data/svetijuraj/docs/session_NN.json (format of collect/cakovec.py). Cache: data/svetijuraj/raw/.
Usage: python collect/svetijuraj.py [--fresh]
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
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "svetijuraj"
HOST = "https://www.svetijurajnabregu.hr"
INDEX = HOST + "/dokumenti-sazivi-i-zapisnici/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
NAME = "Općinskog vijeća Općine Sveti Juraj na Bregu"
DOC = re.compile(r"""href=["']([^"']+/(\d{4})_(\d\d)_(\d\d)-(Zapisnik|Saziv)[^"']*?(\d+)\.?-(?:konstituirajuc\w*-)?sjedn[^"']*\.(?:docx?|pdf))["']""",
                 re.I)
HEAD = re.compile(r"^[ \t]*(?:Točka\s+(\d+)\.?|(\d+)\.\s*TOČKA)[ \t]*$", re.M | re.I)  # "Točka 4.", "5.TOČKA"
QUOTES = str.maketrans({c: '"' for c in "„“”«»"})
VOTE = re.compile(r'(?:na\s+(?:glasovanje|usvajanje)\s+(?P<act>[^\n]{0,400}?),\s*)?vijećnici\s+su\s+(?P<jedn>jednoglasno\s+)?'
                  r'sa?\s+(?P<za>\d+)\s+glas\w*\s+(?:\([^)]{0,80}\)\s+)?"za"(?P<rest>[^\n]{0,120}?)\s*,?\s*(?P<verb>donijeli|usvojili|prihvatili|'
                  r'odbili|izabrali|imenovali|dali|potvrdili|utvrdili)', re.I)
VOTE1 = re.compile(r'Nakon\s+provedenog\s+glasovanja\s+(?P<jedn>jednoglasno\s+)?sa?\s+(?P<za>\d+)\s+glas\w*\s+"za"'
                   r'(?P<rest>[^\n]{0,120}?)\s*,?\s*(?P<verb>prihvaćen|odbijen)\w*\s+je\s+(?P<act>[^,\n]{0,300})', re.I)
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
                                                             headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def doc_text(path):
    if path.suffix == ".pdf":
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    return subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True, text=True).stdout


def listing(fresh):
    """{session: {"minutes": (url, date), "call": (url, date)}} for the current term."""
    page = get(INDEX, fresh=fresh).read_text("utf-8", "replace")
    out = {}
    for url, y, m, d, kind, n in DOC.findall(page):
        date = f"{y}-{m}-{d}"
        out.setdefault(int(n), {}).setdefault("minutes" if kind.lower() == "zapisnik" else "call", (url, date))
    # session numbers restart with the term: keep a number only if one of its documents is from this term
    return {n: v for n, v in out.items() if any(x[1] >= TERM_START for x in v.values())}


def stems(t):
    return {w[:5] for w in re.findall(r"\w{4,}", t.lower())} - {"prije", "odluk", "općin", "svet", "juraj", "bregu",
                                                                "godin", "zaklj", "vijeć"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def jaccard(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, len(a | b))


def agenda(text):
    """Agenda titles: the lines after "DNEVNI RED:" up to the first empty line."""
    m = re.search(r"D\s*N\s*E\s*V\s*N\s*I\s+R\s*E\s*D:?[ \t]*\n", text)
    if not m:
        return []
    rest = re.split(r"\n\s*(?:Točka\s+1\b|Molim\s+Vas)", text[m.end():], maxsplit=1, flags=re.I)[0]
    if "•" in rest:  # bulleted (convocations, the constituent session): bullet lines only
        return [re.sub(r"^\s*•\s*", "", ln).rstrip(",. ").removesuffix(" i").strip()
                for ln in rest.split("\n") if ln.strip().startswith("•")]
    out = []
    for ln in rest.split("\n"):
        ln = ln.strip()
        if re.match(r"Predsjedni\w*\s", ln):  # "Predsjednik ... dao je Dnevni red na usvajanje"
            break
        if not ln:
            if out:
                break
            continue
        out.append(re.sub(r"^\d+\.\s*", "", ln).rstrip(",. ").removesuffix(" i").strip())
    return out


def headings(text, items):
    """[(pos, item)]: each "Točka N." section heading with its item."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1) or m.group(2))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def parse(text, url):
    t = text.translate(QUOTES)
    items = [{"no": i, "sub_label": None, "title": a, "full_title": a, "proposer": "", "status": None, "url": url,
              "attachments": []} for i, a in enumerate(agenda(t), 1)]
    heads = headings(t, items)
    first = heads[0][0] if heads else len(t)
    found = matched = 0
    for m in sorted([*VOTE.finditer(t), *VOTE1.finditer(t)], key=lambda m: m.start()):  # VOTE1: constituent session
        if m.start() < first:  # agenda adoption
            continue
        found += 1
        act = re.sub(r"\s+", " ", m.group("act") or "").strip()
        if re.match(r"(?:\w+\s+){0,3}amandman", act, re.I):
            continue
        sec = next((it for pos, it in reversed(heads) if pos < m.start()), None)
        best = max(items, key=lambda x: (overlap(x["title"], act), jaccard(x["title"], act)), default=None) \
            if act else None
        # the item the act names, when clearly better than the section's (a missing "Točka N." heading)
        if best is not None and overlap(best["title"], act) >= 0.6 and (
                sec is None or overlap(best["title"], act) >= overlap(sec["title"], act) + 0.25):
            it = best
        else:
            it = sec
        if it is None:
            continue
        za = int(m.group("za"))
        rest = m.group("rest") or ""
        p = re.search(r"(\d+)\s+(?:glas\w*\s+)?\"?protiv", rest)
        s = re.search(r"(\d+)\s+(?:glas\w*\s+)?\"?suzdrž", rest)
        if m.group("jedn"):
            protiv, suzd = 0, 0
        else:
            protiv = int(p.group(1)) if p else None
            suzd = int(s.group(1)) if s else None
        rejected = m.group("verb").lower() in ("odbili", "odbijen") or (protiv is not None and za <= protiv)
        quote = re.sub(r"\s+", " ", t[max(m.start(), m.start("za") - 60):m.end()]).strip()
        vote = {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": NO if rejected else YES, "members": {},
                "unanimous": bool(m.group("jedn")) and not rejected, "quote": quote[:300]}
        it.setdefault("votes", []).append(vote)
        matched += 1
    for it in items:
        if it.get("votes"):
            it["vote"] = it["votes"][-1]
            it["status"] = "prihvaćen" if it["vote"]["result"] == YES else "nije prihvaćen"
    return items, found, matched


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    for n, docs in sorted(listing(fresh).items()):
        murl, mdate = docs.get("minutes", (None, None))
        curl, cdate = docs.get("call", (None, None))
        text, items, found, matched = None, [], 0, 0
        if murl:
            text = doc_text(get(murl, ext=murl.rsplit(".", 1)[1].lower(), fresh=fresh))
            items, found, matched = parse(text, murl)
        elif curl:  # convocation only: its agenda, no votes
            ctext = doc_text(get(curl, ext=curl.rsplit(".", 1)[1].lower(), fresh=fresh))
            items = [{"no": i, "sub_label": None, "title": a, "full_title": a, "proposer": "", "status": None,
                      "url": curl, "attachments": []} for i, a in enumerate(agenda(ctext.translate(QUOTES)), 1)]
        d = re.search(r"ODRŽANE\s+DANA\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})", text or "")
        months = ("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna listopada studenoga "
                  "prosinca").split()
        date = (f"{d.group(3)}-{months.index(d.group(2).lower()) + 1:02d}-{int(d.group(1)):02d}"
                if d and d.group(2).lower() in months else mdate or cdate)
        doc = {"session": n, "title": f"{n}. sjednica {NAME}", "date": date, "url": INDEX,
               "call_url": curl, "minutes_url": murl, "minutes_text": text, "items": items,
               "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"svetijuraj session {n} ({date}): {len(items)} items, {nv} with votes "
              f"({found} formulas, {matched} matched), minutes {'yes' if text else 'no'}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
