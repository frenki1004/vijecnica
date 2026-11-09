"""Varaždin city council (Gradsko vijeće Grada Varaždina), 2025-2029 term, from varazdin.hr.

Sources (all on varazdin.hr):
- /sjednice-gradskog-vijeca/ lists one page per session ("N. sjednica Gradskog vijeća", "Konstituirajuća ...";
  the ceremonial "Svečana sjednica" is skipped). A session page has the date, the agenda ("Točke N. sjednice":
  items N, sub-items N.k, each with a material PDF) and the YouTube recording of the session (iframe
  "council-video").
- /zapisnici-zakljucci-i-odluke-sa-sjednica-gradskog-vijeca-2025-2029/ links the minutes ("Skraćeni zapisnik",
  a signed scan, PDF) per session. The scans carry a poor OCR layer, so they are OCRed again (tesseract, hrv, 300
  dpi), page by page, as in collect/krk.py.

The minutes have a "DNEVNI RED" (the agenda as adopted, which can differ from the web agenda: items added by
urgent procedure renumber the rest) and then one "Točka N." section per item; sections with sub-items have a
"N.k. <title>" heading per sub-item. Each act ends with a fixed formula:
  Gradsko vijeće Grada Varaždina je, nakon rasprave, većinom glasova (11 glasova „za“, 2 glasa „protiv“ i 3 glasa
  „suzdržana“) donijelo ...
  Gradsko vijeće Grada Varaždina je, bez rasprave, jednoglasno donijelo ...
Items therefore come from the minutes (agenda list of the minutes: one item per point, or per sub-point N.k), each
with the formula in its section; "primilo na znanje" and acts adopted without a count have no vote. Materials are
matched from the session page by number and title. Sessions without minutes yet get the web agenda only.

Output: data/varazdin/docs/session_NN.json (format of collect/cakovec.py), data/varazdin/recordings.json
(YouTube, listed only). Cache: data/varazdin/raw/web (HTML), raw/pdf (PDF), raw/ocr (OCR text per minutes PDF).

Usage: python collect/varazdin.py [--fresh]
"""
import concurrent.futures
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
D = ROOT / "data" / "varazdin"
HOST = "https://varazdin.hr"
INDEX = "/sjednice-gradskog-vijeca/"
MINUTES_INDEX = "/zapisnici-zakljucci-i-odluke-sa-sjednica-gradskog-vijeca-2025-2029/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
SEATS = 21
MONTHS = {m: i for i, m in enumerate(("siječanj veljača ožujak travanj svibanj lipanj srpanj kolovoz rujan "
                                      "listopad studeni prosinac").split(), 1)}
GEN = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                   "listopada studenoga prosinca").split(), 1)}
GEN["studenog"] = 11
QUOTES = str.maketrans({c: '"' for c in "„“”«»'"})
_robots, _last = None, [0.0]


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests); a block (403/429) is never retried."""
    global _robots
    url = urllib.parse.urljoin(HOST, url)
    sub = "pdf" if binary else "web"
    f = D / "raw" / sub / (hashlib.sha1(url.encode()).hexdigest()[:16] + (".pdf" if binary else ".html"))
    if f.exists() and not fresh:
        return f if binary else f.read_text()
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0.0, 1.1 - (time.time() - _last[0])))
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f if binary else data.decode("utf-8", "replace")


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _ocr_page(png):
    return subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"], capture_output=True, text=True,
                          env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout


def pdf_text(path):
    """OCR text of a scanned PDF (pages joined by form feeds), cached in raw/ocr."""
    cache = D / "raw" / "ocr" / (Path(path).name + ".txt")
    if not cache.exists():
        with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            pngs = sorted(Path(tmp).glob("p-*.png"))
            with concurrent.futures.ThreadPoolExecutor(6) as ex:
                pages = list(ex.map(_ocr_page, pngs))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\f".join(pages))
    return cache.read_text()


# ---------------------------------------------------------------- web pages

def sessions(fresh):
    """{session number: session page url} for the current term (konstituirajuća = 1)."""
    page = get(INDEX, fresh=fresh)
    out = {}
    for u, t in re.findall(r"""<a[^>]+href=["'](/sjednice-gradskog-vijeca/[^"']+)["'][^>]*>(.*?)</a>""", page, re.S):
        t = flat(t)
        m = re.match(r"(\d+)\.\s+sjednica Gradskog vijeća", t)
        n = int(m.group(1)) if m else (1 if t.startswith("Konstituirajuća") else None)
        if n:
            out.setdefault(n, urllib.parse.urljoin(HOST, u))
    return out


def minutes_links(fresh):
    """{session number: minutes PDF url} from the term's minutes page."""
    page = get(MINUTES_INDEX, fresh=fresh)
    out = {}
    for u, t in re.findall(r"""<a[^>]+href=["']([^"']+\.pdf)["'][^>]*>(.*?)</a>""", page, re.S | re.I):
        t = flat(t)
        if not t.lower().startswith("zapisnik"):
            continue
        m = re.search(r"(\d+)\.\s+sjednice", t)
        n = int(m.group(1)) if m else (1 if "konstituiraju" in t.lower() else None)
        if n:
            out.setdefault(n, urllib.parse.urljoin(HOST, u))
    return out


def session_page(page):
    """(date, agenda items, youtube ids) of a session page."""
    d = re.search(r"Datum i vrijeme održavanja sjednice:\s*(?:<[^>]+>\s*)*\w+,\s*(\d{1,2})\.\s+(\w+)\s+(\d{4})", page)
    date = f"{d.group(3)}-{MONTHS.get(d.group(2).lower(), 0):02d}-{int(d.group(1)):02d}" if d else None
    i = page.find("council-video")
    j = page.find("Podijeli s prijateljima", i)
    body = page[i:j if j > 0 else len(page)]
    yt = re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", body)
    items = []
    for no, desc in re.findall(r'<summary class="council-point-title">\s*(\d+)\.(.*?)</details>', body, re.S):
        no = int(no)
        desc = desc[desc.find(">", desc.find("council-point-desc")) + 1:]
        paras = [p for p in re.split(r"</p>|<br\s*/?>|</li>", desc) if flat(p)]
        head, parent = None, ""
        for p in paras:
            t = flat(p).lstrip("> ").strip()
            t = re.sub(r'^(?:div|class)[^>]*>\s*', "", t).strip()
            links = [{"name": "Materijal", "url": urllib.parse.urljoin(HOST, u)}
                     for u in re.findall(r"""href=["']([^"']+\.pdf)["']""", p, re.I)]
            m = re.match(r"%d\.(\d{1,2})\.?\s*(.*)" % no, t)
            if m:
                k = int(m.group(1))
                title = m.group(2).strip()
                full = f"{parent.rstrip(':').strip()} {title}".strip() if parent else title
                items.append({"no": no, "sub_label": chr(96 + k), "title": full, "attachments": links})
            elif head is None:
                head = {"no": no, "sub_label": None, "title": t, "attachments": links}
                parent = t if t.endswith(":") else ""
            else:  # a further paragraph of the same item (more material)
                head["attachments"] += links
        if head and not (parent and any(x["no"] == no for x in items)):
            items.append(head)
    items.sort(key=lambda x: (x["no"], x["sub_label"] or ""))
    return date, items, yt


# ---------------------------------------------------------------- minutes

HEAD = re.compile(r"^[ \t\f]*(?:Točka|TOČKA|Toćka|Tocka)\s*([\dIl]{1,2})\s*[.,]?[ \t]*$", re.M)  # OCR: "Točka I."


def head_no(m):
    return int(m.group(1).replace("I", "1").replace("l", "1"))
PAGE = re.compile(r"^\s*[-_—=]*\s*\d{1,3}\s*[-_—=]+\s*$")  # page numbers "- 18 -", "_21-"
VOTE = re.compile(
    r"Gradsko\s+vijeće\s+Grada\s+Varaždina\s+je\s*,?\s+(?:nakon|bez)\s+rasprave\s*[,.]?\s+"
    r"(?:većinom\s+glasova\s*\(\s*(\d+)\s*glas\w*[\s,.]*za\w*"
    r"(?:\s*(,\s*i?|\s+[il1|](?=\s)|\s+i(?=\d)|\s)\s*(\d+)\s*glas\w*[\s,.]*protiv\w*)?"  # OCR reads the word "i" as 1, l, |
    r"(?:\s*(,\s*i?|\s+[il1|](?=\s)|\s+i(?=\d)|\s)\s*(\d+)\s*glas\w*[\s,.]*suzdrž\w*)?\s*\)"
    r"|(jednoglasno)(?:\s*,?\s*sa?\s+(\d+)\s+glas\w*[\s,.]*za\w*)?\s*,?)"
    r"\s+(?:prihvatilo\s+prijedlog\s+i\s+)?(nije\s+)?(?:donij|usvoj|prihvat|izabr|imenov|utvrd|dal|razrij|potvrd)\w*",
    re.I)


def plain(text):
    """Text with OCR quote marks removed ("„za“", ",,protiv“", "»Za“" -> za)."""
    t = re.sub(r",,|\.,(?=\w)|[„“”\"»«]", "", text)
    return re.sub(r"(?<=\s),(?=(?:protiv|suzdrž|za\b|ZA\b))", "", t)


def agenda_from_minutes(text):
    """[(no, sub or None, title)] from the minutes' "DNEVNI RED" block (before the first "Točka 1.").

    Some scans OCR the agenda table column by column: a run of bare numbers ("11.", "12.", ...) and then the
    titles as paragraphs; those paragraphs take the numbers in order."""
    m = re.search(r"^\s*DNEVNI\s+RED\s*$", text, re.M)
    h = HEAD.search(text, m.end() if m else 0)
    if not m or not h:
        return []
    out, queue, blank = [], 0, False
    for ln in text[m.end():h.start()].split("\n"):
        s = ln.strip()
        if not s or PAGE.match(s):
            blank = blank or not s
            continue
        if re.match(r"(?:utvrđen|Napomena|Jednoglasno|Gradsko vijeće)", s, re.I):
            continue
        last_top = max((o[0] for o in out), default=0)
        a = re.match(r"(\d{1,2})\.\s?(\d{1,2})\.?\s*[^\w\s]*\s*(.+)", s)
        b = re.match(r"(\d{1,2})\s*[.,]?(?:[^\w\s]|\s)*([A-ZČĆŠŽĐ].+)", s)
        bare = re.fullmatch(r"\d{1,3}\s*\.?", s)
        if bare:
            queue += 1
        elif a and out and int(a.group(1)) in (o[0] for o in out) or a and not b:
            out.append([int(a.group(1)), int(a.group(2)), a.group(3).strip()])
        elif b and int(b.group(1)) == last_top + 1:
            out.append([int(b.group(1)), None, b.group(2).strip()])
        elif queue and blank and re.match(r"[A-ZČĆŠŽĐ]", s):
            out.append([last_top + 1, None, s])
            queue -= 1
        elif out:
            out[-1][2] += " " + s
        blank = False
    return [(n, k, re.sub(r"\s+", " ", t).strip().rstrip(",;.")) for n, k, t in out]


def headings(text, items):
    """[(pos, item)]: each "Točka N." section heading with its (first) item."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = head_no(m)
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def vote_of(m, present):
    """Vote dict of a formula match, or None for a count that cannot be right (OCR)."""
    q = re.sub(r"\s+", " ", m.group(0))
    if m.group(6):  # jednoglasno [s N glasova za]
        za = int(m.group(7)) if m.group(7) else None
        return {"za": za, "protiv": 0, "suzdrzano": 0, "result": NO if m.group(8) else YES, "members": {},
                "unanimous": True, "quote": q[:300]}
    za = int(m.group(1))
    groups = [(m.group(2), m.group(3)), (m.group(4), m.group(5))]
    counts = []
    for sep, n in groups:
        if n is None:
            counts.append(None)
            continue
        if sep.strip() == "" and len(n) == 2 and n[0] == "1":  # "„za“ 12 glasa": OCR merged the "i" into the number
            n = n[1]
        counts.append(int(n))
    protiv, suzd = counts
    # the minutes name only the categories that got votes: a category not named is not a number the minutes give
    total = za + (protiv or 0) + (suzd or 0)
    if total > SEATS or (present and total > present):
        return None
    result = NO if m.group(8) or (protiv is not None and za <= protiv) else YES
    return {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {}, "unanimous": False,
            "quote": q[:300]}


def present_at(text, pos):
    """Members present at a position: the last "Napomena: Sjednici je nazočno N" (or the opening quorum) before it."""
    best = None
    for m in re.finditer(r"(?:nazočno|nazočna|prisutno)\s+(\d{1,2})\s+(?:član|vijećni)", text[:pos]):
        best = int(m.group(1))
    return best


def minutes_items(text, web):
    """Items with votes from the minutes; web: agenda items of the session page (for materials)."""
    t = plain(text)
    agenda = agenda_from_minutes(t)
    heads, last = [], 0
    for m in HEAD.finditer(t):
        n = head_no(m)
        if n <= last:
            continue
        heads.append((m.start(), m.end(), n))
        last = n
    items = []
    for i, (pos, hend, n) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        sec = t[hend:end]
        top = next((a for a in agenda if a[0] == n and a[1] is None), None)
        subs = [a for a in agenda if a[0] == n and a[1] is not None]
        if top:
            title = top[2]
        else:  # heading block in capitals: the lines after "Točka N."
            block = re.split(r"\n\s*\n", sec.strip(), 1)[0]
            title = re.sub(r"\s+", " ", block).strip()
            title = title[0] + title[1:].lower() if title.isupper() else title
        parts = []
        if subs:
            for k, (_, sk, stitle) in enumerate(subs):
                starts = [mm.start() for mm in re.finditer(r"^\s*%d\.\s?%d\.?\s" % (n, sk), sec, re.M)]
                parts.append((sk, f"{title.rstrip(':').strip()}: {stitle}", starts[-1] if starts else None))
            ok = [p for p in parts if p[2] is not None]
            bounds = sorted(p[2] for p in ok)
        else:
            parts = [(None, title, 0)]
            bounds = [0]
        for sk, stitle, start in parts:
            it = {"no": n, "sub_label": chr(96 + sk) if sk else None, "title": stitle, "full_title": stitle,
                  "attachments": []}
            if start is not None:
                nxt = next((b for b in bounds if b > start), len(sec))
                seg = sec[start:nxt]
                votes = []
                for vm in VOTE.finditer(seg):
                    v = vote_of(vm, present_at(t, hend + start + vm.start()))
                    if v is None:
                        print(f"   implausible count in {n}{it['sub_label'] or ''}: {vm.group(0)[:120]!r}", flush=True)
                    else:
                        votes.append(v)
                if votes:
                    it["vote"], it["votes"] = votes[-1], votes
            items.append(it)
    match_materials(items, web)
    return items


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "varažd"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def match_materials(items, web):
    """Materials from the session page: same number and sub-item first, else the best title match."""
    for it in items:
        same = [w for w in web if w["no"] == it["no"] and w["sub_label"] == it["sub_label"] and w["attachments"]]
        cand = same if same and overlap(same[0]["title"], it["title"]) >= 0.3 else \
            [w for w in web if w["attachments"] and overlap(w["title"], it["title"]) >= 0.6]
        if cand:
            best = max(cand, key=lambda w: overlap(w["title"], it["title"]))
            it["attachments"] = best["attachments"]


def minutes_date(text):
    m = re.search(r"održane\s+dana\s*(\d{1,2})\.\s*(\w+)\s+(\d{4})", text[:1500])
    return f"{m.group(3)}-{GEN.get(m.group(2).lower(), 0):02d}-{int(m.group(1)):02d}" \
        if m and m.group(2).lower() in GEN else None


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    mins = minutes_links(fresh)
    recordings = []
    for n, url in sorted(sessions(fresh).items()):
        date, web, yt = session_page(get(url, fresh=fresh))
        if date and date < TERM_START:
            continue
        murl = mins.get(n)
        text = pdf_text(get(murl, binary=True, fresh=fresh)) if murl else None
        items = minutes_items(text, web) if text else [
            {**{k: v for k, v in w.items() if k != "parent"}, "full_title": w["title"]} for w in web]
        found = len(VOTE.findall(plain(text))) if text else 0
        for it in items:
            v = it.get("vote")
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        title = "Konstituirajuća sjednica Gradskog vijeća Grada Varaždina" if n == 1 else \
            f"{n}. sjednica Gradskog vijeća Grada Varaždina"
        doc = {"session": n, "title": title, "date": (text and minutes_date(text)) or date, "url": url,
               "minutes_url": murl, "minutes_text": text, "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        for p, vid in enumerate(yt, 1):
            recordings.append({"id": f"varazdin-{n:02d}-{p}", "session": n, "part": p, "date": doc["date"],
                               "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube",
                               "title": f"{title} (snimka)"})
        nv = sum(1 for i in items if i.get("vote"))
        print(f"varazdin session {n} ({doc['date']}): {len(items)} items, {nv} with votes ({found} formulas), "
              f"minutes {'yes' if text else 'no'}, recordings {len(yt)}", flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main("--fresh" in sys.argv)
