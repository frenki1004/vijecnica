"""Čakovec city council (Gradsko vijeće Grada Čakovca), 2025-2029 term, from www.cakovec.hr.

Each session has a report post ("Održana N. sjednica Gradskog vijeća Grada Čakovca", category Gradsko vijeće)
with the agenda ("Akti s N. sjednice": numbered items, sub-items a) b), a "Materijal" PDF each), the minutes
("Zapisnik", PDF with a text layer), an extract of the minutes and the audio recording.

The minutes are verbatim and end every vote with a fixed formula that names the act:
  „Za“ je glasovalo 14 vijećnika, 2 su glasovala „protiv“, 0 je bilo „suzdržanih“ pa je Odluka o … donesena većinom
  glasova.
They number the agenda their own way ("Točka 18.1.", decisions grouped under one point), so the items come from the
minutes: one per "Točka N." section, and when a section has several (non-amendment) votes, one sub-item per vote,
titled with the act its formula names. Amendment votes and votes before "Točka 1." (minutes, agenda) are skipped.
The report post's agenda gives the materials (matched by title) and is the item list while minutes are missing.
Older minutes are scans: OCR (tesseract, hrv) as in collect/krk.py. Sessions before the 2025-2029 term are skipped.

Output: data/cakovec/docs/session_NN.json (format of collect/sibenik.py). Recordings: collect/audio_sites.py.
HTML cache data/cakovec/raw/web, PDFs data/cakovec/raw/pdf.

Usage: python collect/cakovec.py [--fresh]
"""
import hashlib
import os
import tempfile
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
D = ROOT / "data" / "cakovec"
HOST = "https://www.cakovec.hr"
INDEX = "/kategorija/gradsko-vijece/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
POST = re.compile(r"""href=["'](https://www\.cakovec\.hr/odrzana-(\d+)-sjednica-gradskog-vijeca[^"'#]*)["']""")
LINK = re.compile(r"""<a href=["']([^"']+)["'][^>]*>([^<]*)</a>""")
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
HEAD = re.compile(r"^\f?[ \t]*Točka\s+(\d+)\.(?:(\d+)\.?)?[ \t]+(?=\S)", re.M)  # "Točka 4.", "Točka 18.1.", "22.2"
OUTCOME = re.compile(r"\b(nije\s+)?(?:donesen\w*|usvojen\w*|dan[aeo]?|prihvaćen\w*|izabran\w*|imenovan\w*|"
                     r"utvrđen\w*|potvrđen\w*|verificiran\w*)\b")
TERM_START = "2025-06-01"
SEATS = 19
QUOTES = str.maketrans({c: '"' for c in "„“”«»"})


def quotes(t):
    return t.replace(",,", '"').translate(QUOTES)  # OCR: ,,protiv“
N = r"(\d+|O)"  # OCR reads 0 as O
VOTE = re.compile(rf'"Za"\s+je\s+glasoval\w*\s+{N}\s+vijećnik\w*,\s*{N}\s+(?:\w+\s+){{1,2}}glasoval\w*\s+"protiv",'
                  rf'\s*{N}\s+(?:\w+\s+){{1,2}}bi(?:o|l\w*)\s+"suzdržan\w*"\s*(.{{0,700}})', re.S)
_robots, _last = None, [0.0]


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests)."""
    global _robots
    sub = "pdf" if binary else "web"
    f = D / "raw" / sub / (hashlib.sha1(url.encode()).hexdigest()[:16] + (".pdf" if binary else ".html"))
    if f.exists() and not fresh:
        return f if binary else f.read_text()
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    for wait in (0, 30, 90):  # the server often times out the TLS handshake: wait and try again, twice
        time.sleep(max(wait, 1.0 - (time.time() - _last[0])))
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
            break
        except (TimeoutError, OSError) as e:
            if wait == 90 or getattr(e, "code", None) in (403, 429):  # a block is not retried
                raise
            print(f"   retry after {e}: {url}", flush=True)
        finally:
            _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f if binary else data.decode("utf-8", "replace")


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def pdf_text(path):
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) > 200:
        return t
    cache = D / "raw" / "ocr" / (Path(path).name + ".txt")
    if not cache.exists():
        pages = []
        with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            for png in sorted(Path(tmp).glob("p-*.png")):
                pages.append(subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"],
                                            capture_output=True, text=True,
                                            env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\f".join(pages))
    return cache.read_text()


def sessions(fresh):
    """{session number: report post url}, newest category page first; older pages until session 1 is found."""
    out = {}
    for page in range(1, 6):
        url = HOST + INDEX + (f"page/{page}/" if page > 1 else "")
        try:
            text = get(url, fresh=fresh)
        except Exception:
            break
        for u, n in POST.findall(text):
            out.setdefault(int(n), u)
        if 1 in out or 2 in out and page > 1:
            break
    return out


def report(page):
    """Agenda items, minutes/extract links and the post date from a report post."""
    i = page.find("Akti s ")
    body = page[i:page.find("Audio zapisnik", i) if "Audio zapisnik" in page[i:] else len(page)]
    docs = [u for u, t in LINK.findall(page) if u.lower().endswith(".pdf") and "zapisnik" in u.lower()]
    minutes = next((u for u in docs if "izvod" not in u.lower()), None)  # gv8_zapisnik.pdf, Zapisnik_2_GV.pdf
    extract = next((u for u in docs if "izvod" in u.lower()), None)
    agenda = body.split("Izvod iz zapisnika")[0]
    items, no, prefix = [], None, ""
    for chunk in re.split(r"<br\s*/?>|</p>", agenda):
        ln = flat(chunk)
        m = re.match(r"(\d+)\.\s+(.+)", ln)
        s = re.match(r"([a-z])[.)]\s+(.+)", ln)  # "a)" or, in older posts, "a."
        if m:
            no, sub, title = int(m.group(1)), None, m.group(2)
        elif s and no is not None:
            sub, title = s.group(1), s.group(2)
        else:
            continue
        title = title.replace("Materijal", "").strip()
        if title.endswith(":"):  # "11. Suglasnost na:" only heads its sub-items a) b)
            prefix = title.rstrip(":").strip()
            continue
        full = f"{prefix} {title[0].lower()}{title[1:]}" if sub and prefix else title
        mat = next((u for u, t in LINK.findall(chunk) if flat(t) == "Materijal"), None)
        items.append({"no": no, "sub_label": sub, "title": full, "full_title": full,
                      "attachments": [{"name": "Materijal", "url": mat}] if mat else []})
        if not sub:
            prefix = ""
    d = re.search(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})\.\s+\|", flat(page))
    date = f"{d.group(3)}-{MONTHS.get(d.group(2), 0):02d}-{int(d.group(1)):02d}" if d else None
    return items, minutes, extract, date


def minutes_date(text):
    m = re.search(r"održane\s+(\d{1,2})\.\s+(\w+)\s+(\d{4})", text[:600])
    return f"{m.group(3)}-{MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS \
        else None


def headings(text, items):
    """[(pos, item)]: each "Točka N." section heading with its item (the first, for an item with sub-items)."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):  # a quoted "Točka 3." is no heading
            out.append((m.start(), it))
            last = n
    return out


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "čakovc"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def formula(m):
    """(za, protiv, suzdržano, act named after "pa je", result) of a vote formula; act None for an amendment."""
    tail = re.sub(r"\s+", " ", m.group(4))
    k = re.search(r"\bpa\s+(?:je\s+)?(?:predsjednik\s+Gradskog\s+vijeća\s+konstatira\w*\s+da\s+(?:je|su)\s+)?", tail)
    tail = tail[k.end():] if k else tail
    o = OUTCOME.search(tail)
    act = tail[:o.start()].strip(" ,") if o else tail[:200]
    result = NO if o and o.group(1) else YES
    za, protiv, suzd = (int(m.group(j).replace("O", "0")) for j in (1, 2, 3))
    return za, protiv, suzd, act, result


def minutes_items(text, agenda):
    """Items and their votes from the minutes ("Točka N." sections, one sub-item per decision voted in a section)."""
    t = quotes(text)
    heads, seen, last = [], set(), 0
    for m in HEAD.finditer(t):
        key = (int(m.group(1)), int(m.group(2) or 0))
        if key in seen or key[0] < last:  # repeated or quoted inside a speech
            continue
        seen.add(key)
        last = key[0]
        title = re.sub(r"\s+", " ", re.split(r"\n\s*\n|\nJosip Varga|\n[A-ZČĆŠŽĐ][a-zčćšžđ]+ [A-ZČĆŠŽĐ][a-zčćšžđ]+\n",
                                         t[m.end():m.end() + 500])[0]).strip()
        heads.append((m.start(), key, title))
    items = []
    for i, (pos, (no, part), title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        votes = [formula(m) for m in VOTE.finditer(t, pos, end)]
        votes = [v for v in votes if not re.match(r"(?:\w+\s+){0,3}amandman", v[3], re.I)]
        if part:  # "Točka 18.1.": the minutes' own sub-point
            votes = votes[-1:]
        if len(votes) <= 1:
            groups = [(title, votes[0] if votes else None)]
        else:
            groups = [(v[3] or title, v) for v in votes]
        for k, (name, v) in enumerate(groups):
            it = {"no": no, "sub_label": (chr(96 + part) if part else (chr(97 + k) if len(groups) > 1 else None)),
                  "title": name[0].upper() + name[1:] if name else title, "attachments": []}
            it["full_title"] = it["title"]
            if v and not (10 <= v[0] + v[1] + v[2] <= SEATS):  # a misread count (OCR): no vote rather than a wrong one
                print(f"   implausible count {v[:3]} for {no}{it['sub_label'] or ''}, dropped", flush=True)
                v = None
            if v:
                vote = {"za": v[0], "protiv": v[1], "suzdrzano": v[2], "result": v[4], "members": {},
                        "unanimous": v[4] == YES and v[1] == 0 and v[2] == 0,
                        "quote": f'„Za“ je glasovalo {v[0]} vijećnika, {v[1]} „protiv“, {v[2]} „suzdržanih“ '
                                 f'pa je {v[3]}'[:300]}
                it["vote"], it["votes"] = vote, [vote]
            items.append(it)
    for it in items:  # materials from the report post, by title
        best = max(agenda, key=lambda a: overlap(a["title"], it["title"]), default=None)
        if best and best["attachments"] and overlap(best["title"], it["title"]) >= 0.5:
            it["attachments"] = best["attachments"]
    return items


def attendance(text):
    """Present count from the chair's quorum line ("u vijećnici prisutno 16 vijećnika"); names are not listed."""
    m = re.search(r"prisutno\s+(\d+)\s+vijećnika", text[:3000])
    return int(m.group(1)) if m else None


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    for n, url in sorted(sessions(fresh).items()):
        agenda, minutes, extract, post_date = report(get(url, fresh=fresh))
        if post_date and post_date < TERM_START:  # previous term: its session numbers repeat in this one
            continue
        text = pdf_text(get(minutes, binary=True)) if minutes else None
        items = minutes_items(text, agenda) if text else agenda
        found = len(VOTE.findall(quotes(text))) if text else 0
        for it in items:
            v = it.get("vote")
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        doc = {"session": n, "title": f"{n}. sjednica Gradskog vijeća Grada Čakovca",
               "date": (text and minutes_date(text)) or post_date, "url": url, "minutes_url": minutes,
               "minutes_extract_url": extract, "minutes_text": text, "present": text and attendance(text),
               "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"cakovec session {n} ({doc['date']}): {len(items)} items, {nv} with votes ({found} formulas), "
              f"minutes {'yes' if text else 'no'}", flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
