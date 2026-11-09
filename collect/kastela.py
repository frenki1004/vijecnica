"""Kaštela city council (Gradsko vijeće Grada Kaštela), 2025-2029 term, from kastela.hr.

The term page (/kategorija-gradskog-vijeca/mandatno-razdoblje-2025-2029/) links one page per session
("N. sjednica Gradskog vijeća"). Each session page lists the call ("Poziv za N. sjednicu", with the agenda and the
date), one PDF per agenda item named "K. <title>.pdf" and a YouTube link ("Video snimka N. sjednice").
The minutes of session N are item 2 of session N+1 ("Zapisnik s N. sjednice"): PDFs, some with a text layer, some
scans (OCR, tesseract hrv, as in collect/krk.py). The newest session has no minutes yet: agenda and materials only.

The minutes repeat the agenda ("Dnevni red"), then one section per item ("K. <title>") ending with the chair's
formula, e.g.
  Predsjednik Vijeća ... utvrđuje da je, bez rasprave, većinom glasova (13 "za", 1 "suzdržan" od 14) donesen ZAKLJUČAK
  ... utvrđuje da je jednoglasno (16 "za" od 16) donesena ODLUKA ...
  Na Zapisnik ... nije bilo primjedbi te je isti usvojen jednoglasno (17 "za" od 17).
Counts come only from the parentheses; a count they do not name is null ("jednoglasno" gives protiv = suzdržano = 0).
Amendment votes ("stavljen je na glasovanje i nije prihvaćen (5 „za“ ...)") are not the chair's formula and are
skipped. A section with several formulas (konstituirajuća: president, vice-presidents) becomes sub-items a), b), …
titled with the act each formula names.

Output: data/kastela/docs/session_NN.json (format of collect/cakovec.py), data/kastela/recordings.json (YouTube).
Cache: data/kastela/raw/web (HTML), raw/pdf, raw/ocr.

Usage: python collect/kastela.py [--fresh]
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
D = ROOT / "data" / "kastela"
HOST = "https://kastela.hr"
TERM = "/kategorija-gradskog-vijeca/mandatno-razdoblje-2025-2029/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
_robots, _last = None, [0.0]


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests)."""
    global _robots
    ext = (Path(urllib.parse.urlparse(url).path).suffix.lower() or ".bin") if binary else ".html"
    f = D / "raw" / ("pdf" if binary else "web") / (hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if f.exists() and not fresh:
        return f if binary else f.read_text()
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


def pdf_text(path):
    """Text layer of a PDF, or OCR (tesseract, hrv; cached) for a scan."""
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


YT = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})")
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
TERM_START = "2025-06-01"
SEATS = 21
QUOTES = str.maketrans({c: '"' for c in "„“”«»″"})
FORMULA = re.compile(r"(?:utvrđuje,?\s+da\s+(?:je|su),?\s+(?:bez\s+rasprave,\s+)?|usvojen\w*\s+|(?m:^)[ \t\f]*|,\s+(?=jedno))"
                     r"([Jj]ednoglasno|[Vv]ećinom\s+glasova(?:\s+svih\s+vijećnika)?)\s*\(([^()]{3,120})\)"
                     r"\s*(?:,?\s*prihvaćen\s+je\s+prijedlog\s+i\s+|prijedlog\s+prihvaćen\s+i\s+)?(nije\s+)?(\w+)?"
                     r"(?:\s+(?:je|su)\b)?")


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm(t):
    return t.replace(",,", '""').translate(QUOTES)  # length-preserving: positions hold in the raw text


def ddate(m):
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS else None


def session_pages(fresh):
    """{session number: page url} from the term page."""
    t = get(HOST + TERM, fresh=fresh)
    out = {}
    for u in re.findall(r'href="(https://kastela\.hr/gradsko-vijece/mandatno-razdoblje-2025-2029/[^"]+)"', t):
        m = re.search(r"/(\d+)-(?:konstituirajuca-)?sjednica", u)
        if m:
            out.setdefault(int(m.group(1)), u)
    return out


def page_files(page):
    """[(name, url)] of the PDFs listed on a session page, and the YouTube ids."""
    files = []
    for u, t in re.findall(r'<a [^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', page, re.S):
        name = flat(t) or urllib.parse.unquote(u.rsplit("/", 1)[-1])
        if name and (u, name) not in files and not any(x[0] == u and x[1] for x in files):
            files.append((u, name))
    files = [(u, n) for u, n in files if n]
    seen, out = set(), []
    for u, n in files:
        if u not in seen:
            seen.add(u)
            out.append((n, u))
    yts = []
    for y in YT.findall(page):
        if y not in yts:
            yts.append(y)
    return out, yts


def agenda(text):
    """([(no, title)], end) from the numbered "Dnevni red" list of a call or the minutes; end = where the list stops
    (the minutes go on with "Prelazi se na raspravljanje" or straight with the first item's section, "1. ...")."""
    t = norm(text)
    m = re.search(r"\n\s*D\s*n\s*e\s*v\s*n\s*i\s+r\s*e\s*d\s*\n", t, re.I)
    if not m:
        return [], 0
    stop = re.search(r"Materijali\s+za|\n\s*PREDSJEDNI|\n\s*Predsjedni\w+\s+Gradskog", t[m.end():])
    limit = m.end() + (stop.start() if stop else len(t) - m.end())
    items, cur, expect, pos = [], None, 1, m.end()
    for k in re.finditer(r"[^\n]*\n?", t[m.end():limit]):
        ln, start = k.group(0), m.end() + k.start()
        pos = start
        s = ln.strip()
        num = re.match(r"(\d+)\.\s*(\S.*)", s)
        if num and int(num.group(1)) == expect:
            cur = [expect, num.group(2)]
            items.append(cur)
            expect += 1
        elif num and int(num.group(1)) == 1 and items:  # numbering restarts: the first section
            break
        elif re.match(r"Prelazi\s+se\s+na", s):  # pdftotext may put this line before the list
            cur = None
        elif not s or s.startswith(("-", "*", "•", "—")) or re.fullmatch(r"\d+", s):
            if s.startswith(("-", "—", "*", "•")):
                cur = None  # "- Izvjestitelj: ...", "* svečana prisega" end the title
            continue
        elif cur is not None and len(cur[1]) < 400:
            cur[1] += " " + s
    else:
        pos = limit
    return [(n, re.sub(r"\s*-?\s*Izvjestitelj.*$", "", re.sub(r"\s+", " ", ti)).strip(" ;")) for n, ti in items], pos


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "kaštel"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def sections(text, items):
    """[(pos, no)] of each item's section heading in the minutes (after the agenda), in text order.

    A heading is "K. <title>" at a line start; items may be taken out of agenda order. OCR can misread the number
    ("7." as "1.", "11." as "1i."): then a line-start "<1-3 chars>. <title>" whose words match the title is taken."""
    t = norm(text)
    start = agenda(text)[1]
    out, used = [], set()
    for exact in (True, False):
        for no, title in items:
            if any(n == no for _, n in out):
                continue
            num = rf"{no}" if exact else r"[\dIil|]{1,3}"
            lo = max([p for p, n in out if n < no], default=start)  # a misread heading lies between its neighbours
            hi = min([p for p, n in out if n > no], default=len(t))
            best = None
            for k in re.finditer(rf"(?m)^[ \t\f]*{num}\.[ \t]*(\S[^\n]*(?:\n[^\n]*)?)", t[start:]):
                p = start + k.start()
                score = overlap(k.group(1)[:160], title[:160])
                if score >= (0.5 if exact else 0.75) and p not in used and (exact or lo < p < hi):
                    best = p
                    break
            if best is not None:
                out.append((best, no))
                used.add(best)
    return sorted(out)


def headings(text, items):
    """[(pos, item)]: each item's section start in the minutes (the first sub-item for an item with several)."""
    out = []
    for pos, no in sections(text, [(i["no"], i["full_title"]) for i in items if not i["sub_label"] or
                                   i["sub_label"] == "a"]):
        it = next(i for i in items if i["no"] == no)
        out.append((pos, it))
    return out


def act_name(tail):
    """The act a formula names: "ODLUKA / o izboru ..." -> "Odluka o izboru ..."."""
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", tail)]
    paras = [p for p in paras if p and not re.fullmatch(r"\d+", p)]
    if not paras:
        return ""
    head = paras[0]
    if re.fullmatch(r"[A-ZČĆŠŽĐ ]{5,}", head) and len(paras) > 1:
        head = head.replace(" ", "").capitalize() + " " + paras[1]
    elif "\n" not in tail.strip()[:1] and re.fullmatch(r"[A-ZČĆŠŽĐ ]{5,}", head.split(" o ")[0]):
        head = head[0] + head[1:]
    head = re.sub(r"^([A-ZČĆŠŽĐ]{3,})\b", lambda m: m.group(1).capitalize(), head.replace("Z A K LJ U Č A K", "ZAKLJUČAK")
                  .replace("PRAVI LN I K", "PRAVILNIK"))
    head = re.sub(r"^(\w+) 0 ", r"\1 o ", head)  # OCR: "Odluka 0 izboru"
    head = re.split(r"(?<=[a-zčćšžđ.])\s+(?=[A-ZČĆŠŽĐ][a-zčćšžđ]+ [A-ZČĆŠŽĐ][a-zčćšžđ]+ bira se|U \w+ \w+ biraju se|\d+\. )", head)[0]
    return head[:250]


def parse_vote(m):
    kind, inner, neg, word = m.group(1).lower(), re.sub(r"\s+", " ", m.group(2)), m.group(3), m.group(4) or ""
    inner = re.sub(r"(?<![\w])[Il](?=\W{0,3}\s*(?:za|protiv|suzdrž))", "1", inner)  # OCR: I"suzdržan"
    num = r"(\d+)\s*\W{0,3}\s*"
    za = re.search(num + r"za\b", inner)
    pr = re.search(num + r"protiv", inner)
    su = re.search(num + r"suzdrž", inner)
    za = int(za.group(1)) if za else None
    if kind == "jednoglasno":
        pr, su = 0, 0
    else:
        pr = int(pr.group(1)) if pr else None
        su = int(su.group(1)) if su else None
    result = NO if neg or (za is not None and pr is not None and za <= pr) else YES
    return {"za": za, "protiv": pr, "suzdrzano": su, "result": result, "members": {},
            "unanimous": kind == "jednoglasno" and result == YES,
            "quote": re.sub(r"\s+", " ", m.group(0)).strip()[:300]}


def minutes_items(text, items):
    """Votes into the agenda items: the chair's formulas inside each item's section."""
    t = norm(text)
    secs = sections(text, [(i["no"], i["title"]) for i in items])
    out = []
    found = 0
    for k, (pos, no) in enumerate(secs):
        end = secs[k + 1][0] if k + 1 < len(secs) else len(t)
        base = next(i for i in items if i["no"] == no)
        votes = []
        for m in FORMULA.finditer(t, pos, end):
            v = parse_vote(m)
            tot = sum(x for x in (v["za"], v["protiv"], v["suzdrzano"]) if x)
            if v["za"] is None or not (1 <= tot <= SEATS):
                print(f"   implausible/unread count in {no}: {v['quote'][:80]}", flush=True)
                continue
            if m.group(0).startswith(","):  # an award voted one by one: "1. NAME, za ..., jednoglasno (18 „za“ od 18)."
                head = re.split(r"\n\s*\d+\.\s+", t[max(pos, m.start() - 600):m.start()])[-1]
                act = "Javno priznanje: " + re.sub(r"\s+", " ", head).strip()[:200]
            else:
                act = act_name(t[m.end():m.end() + 700])
            votes.append((v, act))
        found += len(votes)
        base["_votes"] = votes
    for it in items:
        votes = it.pop("_votes", [])
        if len(votes) <= 1:
            if votes:
                it["vote"], it["votes"] = votes[0][0], [votes[0][0]]
            out.append(it)
        else:
            for j, (v, act) in enumerate(votes):
                sub = dict(it, sub_label=chr(97 + j), title=act or it["title"], full_title=act or it["title"],
                           vote=v, votes=[v])
                out.append(sub)
    return out, found


def materials(files, no):
    """Agenda item no's PDFs on the session page ("K. title.pdf", "K_title.pdf")."""
    out = []
    for name, u in files:
        fn = urllib.parse.unquote(u.rsplit("/", 1)[-1])
        if re.match(rf"{no}(?:[._\s-]|\.-)", name) or re.match(rf"{no}[._]", fn):
            if "zapisnik" in fn.lower() and no != 2:
                continue
            out.append({"name": name, "url": u})
    return out


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    pages = session_pages(fresh)
    info = {}
    for n, url in sorted(pages.items()):
        files, yts = page_files(get(url, fresh=fresh))
        info[n] = (url, files, yts)
    recordings = []
    for n, (url, files, yts) in sorted(info.items()):
        call = next((u for name, u in files if "poziv" in u.lower() or "saziv" in u.lower()), None)
        call_text = pdf_text(get(call, binary=True)) if call else ""
        nxt = info.get(n + 1)
        minutes = None
        if nxt:
            minutes = next((u for name, u in nxt[1] if re.search(rf"zapisnik\w*-s\w?-{n}\.", u.lower())
                            or re.search(rf"zapisnik\w*-s\w?-(?:konstituirajuce|{n}\.)", u.lower())
                            and (n == 1) == ("konstituir" in u.lower())), None)
        text = pdf_text(get(minutes, binary=True)) if minutes else None
        ag = agenda(text)[0] if text else []
        if not ag:
            ag = agenda(call_text)[0]
        date = ddate(re.search(r"održane\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})", norm(text or "")[:1500])) or \
            ddate(re.search(r"za\s+dan\s+(\d{1,2})\.\s*(\w+)\s*(?:\(\w+\)\s*)?(\d{4})", norm(call_text)))
        if date and date < TERM_START:
            continue
        items = [{"no": no, "sub_label": None, "title": ti, "full_title": ti, "proposer": "", "status": None,
                  "url": url, "attachments": materials(files, no)} for no, ti in ag]
        found = 0
        if text:
            items, found = minutes_items(text, items)
        for it in items:
            v = it.get("vote")
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
        doc = {"session": n, "title": f"{n}. sjednica Gradskog vijeća Grada Kaštela", "date": date, "url": url,
               "minutes_url": minutes, "minutes_text": text, "call_url": call, "items": items, "attendance": [],
               "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        formulas = len(FORMULA.findall(norm(text))) if text else 0
        nv = sum(1 for i in items if i.get("vote"))
        print(f"kastela session {n} ({date}): {len(items)} items, {nv} with votes, formulas in minutes {formulas} "
              f"(matched {found}), minutes {'yes' if text else 'no'}", flush=True)
        if text:
            for it in items:
                if not it.get("vote"):
                    print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)
        for p, y in enumerate(yts, 1):
            recordings.append({"id": f"kastela-{n:02d}-{p}", "session": n, "part": p, "date": date,
                               "url": f"https://www.youtube.com/watch?v={y}", "kind": "youtube",
                               "title": f"{n}. sjednica Gradskog vijeća (Kaštela)"})
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    print(f"kastela: {len(recordings)} recordings", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
