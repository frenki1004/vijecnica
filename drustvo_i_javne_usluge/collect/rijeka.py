"""Collect Rijeka City Council (Gradsko vijeće Grada Rijeke) sessions, 2025-2029 term.

rijeka.hr (WordPress): the session list (/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/page/N/)
mixes all terms; a session page (/session/<slug>/) has the agenda as <h3>Točka N.</h3> blocks with the
material PDFs (first document list) and the adopted acts (later lists), an optional status line
("Prijedlog nije prihvaćen", "Izvješće je povučeno" …), committee conclusions, the minutes PDF, one
YouTube embed per sitting and "Povezane novosti" (news about the outcome).
Minutes (zapisnik) are prose: attendance by name, the question hour ("AKTUALNI SAT", question +
oral answer), sections "TOČKA N." with "Rezultat glasovanja: Gradsko vijeće je VEĆINOM GLASOVA
(21 za, 5 protiv i 5 suzdržanih) donijelo …". No per-councillor votes. Sessions without published
minutes get vote totals from the news prose when a sentence can be tied to one agenda item.

The term has three constitutive sittings (the 1st and 2nd failed to elect a council president); they
are stored together as session 1 (items keep their own numbers, `sub` comes from the order in
db/build.py), with every sitting in `sittings` and one recording part per sitting.
Extraordinary sessions keep the term's number ("Izvanredna 6. sjednica" = 6).

Cache: data/rijeka/raw/web (HTML), data/rijeka/raw/pdf, data/rijeka/raw/yt.json (yt-dlp metadata).
Output: data/rijeka/docs/session_NN.json, data/rijeka/recordings.json, data/rijeka/members.json.
No video/audio is downloaded (sessions are ~9 h YouTube streams).

Usage: python collect/rijeka.py [--fresh]   (--fresh re-fetches the list, session and news pages)
"""
import hashlib
import html
import json
import math
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "rijeka"
HOST = "https://www.rijeka.hr"
GV = "/gradska-uprava/gradsko-vijece"
TERM = GV + "/gradsko-vijece-mandatno-razdoblje-2025-2029"
TERM_START = "2025-06-01"
UA = "vijecnica-research/0.1 (open data hackathon)"
YTDLP = [str(Path.home() / ".local/bin/yt-dlp"), "--js-runtimes", "node"]
_last = [0.0]

MONTHS = {"siječnja": 1, "veljače": 2, "ožujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6, "srpnja": 7,
          "kolovoza": 8, "rujna": 9, "listopada": 10, "studenoga": 11, "studenog": 11, "prosinca": 12}
NUMW = {"nula": 0, "jedan": 1, "jednim": 1, "jedna": 1, "jednog": 1, "jedno": 1, "dva": 2, "dvije": 2,
        "dvama": 2, "tri": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9,
        "deset": 10, "jedanaest": 11, "dvanaest": 12, "trinaest": 13, "četrnaest": 14, "petnaest": 15,
        "šesnaest": 16, "sedamnaest": 17, "osamnaest": 18, "devetnaest": 19, "dvadeset": 20}
NUM = r"(\d+|" + "|".join(sorted(NUMW, key=len, reverse=True)) + r")"
UP = "A-ZČĆŠŽĐ"
OFFICIALS = {"Rinči": "Gradonačelnica Iva Rinčić", "Vivoda": "Zamjenik gradonačelnice Vedran Vivoda",
             "Milakovi": "Zamjenik gradonačelnice Aleksandar-Saša Milaković"}
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"


def get(path, binary=False, fresh=False, tries=3):
    url = path if path.startswith("http") else HOST + path
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cache = D / "raw" / ("pdf" if binary else "web") / key
    if not cache.exists() or fresh:
        for t in range(tries):
            time.sleep(max(0, 1.0 - (time.time() - _last[0])))
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                              timeout=60).read()
                break
            except Exception as e:  # the site sometimes stalls on a single request
                print("retry", url, e, file=sys.stderr, flush=True)
                if t == tries - 1:
                    raise
                time.sleep(5)
            finally:
                _last[0] = time.time()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return cache if binary else cache.read_text("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def num(w):
    w = w.lower()
    return int(w) if w.isdigit() else NUMW.get(w)


def hr_date(s):
    """'5. studenoga 2026' / '25.09.2025' → ISO date (first one in s)."""
    m = re.search(r"(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")\s+(\d{4})", s)
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


# ---------------------------------------------------------------- session list

def session_list(fresh):
    """Sessions of the current term from the paged list: [{url, title, date, news:[{title,url,date}]}]."""
    out, page = [], 1
    while True:
        p = get(f"{GV}/sjednice-gradskog-vijeca/" + (f"page/{page}/" if page > 1 else ""), fresh=fresh)
        body = p[p.find("component-sessions"):]
        older = False
        for art in re.split(r"<article>\s*<header>", body)[1:]:
            head, _, foot = art.partition("related-news")
            d = re.search(r'meta date">(.*?)<', head)
            a = re.search(r'<h3><a href="([^"]+/session/[^"]+)">(.*?)</a>', head)
            if not a:
                continue
            date = hr_date(d.group(1)) if d else None
            if date and date < TERM_START:
                older = True
                continue
            news = [{"url": u, "title": clean(t), "date": hr_date(dd)} for dd, u, t in
                    re.findall(r'meta date">(.*?)<.*?<h3><a href="([^"]+)">(.*?)</a>', foot, re.S)]
            out.append({"url": a.group(1), "title": clean(a.group(2)), "list_date": date, "news": news})
        if older or f"/page/{page + 1}/" not in p:
            return out
        page += 1


def session_no(title):
    """(session number, constitutive sitting index or None)."""
    if "konstituirajuć" in title.lower():
        m = re.match(r"(\d+)\.", title)
        return 1, int(m.group(1)) if m else 1
    m = re.search(r"(\d+)\.\s*sjednica", title)
    return int(m.group(1)), None


# ---------------------------------------------------------------- session page

def docs_in(block):
    return [{"name": clean(t), "url": u} for u, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)]


def parse_page(p):
    note = re.search(r'<p class="note">(.*?)</p>', p, re.S)
    note = clean(note.group(1)) if note else ""
    agenda = p[p.find("component-session\""):]
    summary_at = agenda.find("component-session-summary")
    summary = agenda[summary_at:agenda.find("</aside>", summary_at)] if summary_at >= 0 else ""
    agenda = agenda[:summary_at] if summary_at >= 0 else agenda
    items = []
    parts = re.split(r"<h3>\s*Točka\s+(\d+)\.\s*</h3>", agenda)
    for k in range(1, len(parts), 2):
        chunk = parts[k + 1]
        desc = re.search(r'item-description">(.*?)</div>', chunk, re.S)
        blocks = re.findall(r'item-documents">(.*?)</div>', chunk, re.S)
        items.append({"no": int(parts[k]), "description": clean(desc.group(1)) if desc else "",
                      "materials": docs_in(blocks[0]) if blocks else [],
                      "acts": [d for b in blocks[1:] for d in docs_in(b)]})
    links = docs_in(summary)
    minutes = [d for d in links if re.match(r"Zapisnik\b.*sjednic", d["name"])]
    gazette = [d for d in links if "sn.rijeka.hr" in d["url"]]
    committees = [d for d in links if d["name"].startswith("Zaključ") and "Odbor" in d["name"]]
    side = p[p.find("component-video"):]
    yt = list(dict.fromkeys(re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", side)))
    return {"note": note, "items": items, "minutes": minutes[0]["url"] if minutes else None,
            "gazette": gazette[0]["url"] if gazette else None, "committee_conclusions": committees,
            "youtube": yt}


def status_from_text(s):
    s = s.lower()
    if re.search(r"povuč|povuc", s):
        return "povučen"
    if re.search(r"nis?u?\w* prihvać|nije prihvać|nije usvoj|nisu usvoj|odbijen", s):
        return "odbijen"
    if re.search(r"prihvać|usvoj|primljen\w* na znanje|primilo na znanje", s):
        return "prihvaćen"
    return None


# ---------------------------------------------------------------- minutes

def flat(s):
    return re.sub(r"\s+", " ", re.sub(r"(\w)-\s*\n\s*(\w)", r"\1-\2", s)).strip()


def attendance(text):
    t = flat(text)
    names = lambda s: [n.strip(" .") for n in re.split(r",\s*|\s+i\s+", s) if n.strip(" .")]
    out = []
    m = re.search(r"Sjednici su bili nazočni članovi Gradskog vijeća:\s*(.*?)\.\s", t)
    if m:
        out += [{"name": n, "present": True} for n in names(m.group(1))]
    m = re.search(r"Sjednici (?:nisu bili nazočni|nije bi\w+ nazočn\w+) član\w* Gradskog vijeća:\s*(.*?)\.\s", t)
    if m:
        out += [{"name": n, "present": False} for n in names(m.group(1))]
    return out


def sections(text):
    """'TOČKA N.' sections after the adopted agenda: {N: (heading, body)}."""
    out = {}
    ms = list(re.finditer(r"(?m)^\s*TOČKA\s+(\d+)\s*\.\s*$", text))
    for i, m in enumerate(ms):
        body = text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        head = []
        for line in body.lstrip("\n").split("\n"):
            if not line.strip():
                break
            head.append(line.strip())
        out[int(m.group(1))] = (" ".join(head), body)
    return out


VOTE_PAREN = re.compile(r"\(([^()]*?\d+\s*(?:glas\w*\s+)?(?:za|protiv|suzdrž)[^()]*)\)", re.I)


def counts(s):
    v = {"za": 0, "protiv": 0, "suzdrzano": 0}
    for n, kind in re.findall(r"(\d+)\s*(?:glas\w*\s+)?(za|protiv|suzdrž)", s, re.I):
        v["suzdrzano" if kind.lower().startswith("suzd") else kind.lower()] = int(n)
    return v


def minutes_votes(body):
    """Every vote parenthesis in a minutes section, with its sentence, result and amendment flag."""
    t = flat(body)
    out = []
    for m in VOTE_PAREN.finditer(t):
        if not re.search(r"\b(za|protiv|suzdrž)", m.group(1), re.I):
            continue
        before = t[max(0, m.start() - 400):m.start()]
        cut = [x.end() for x in re.finditer(r"(?:\.\s+(?=[" + UP + r"0-9])|Rezultat\w* glasovanja:)", before)]
        start = before[cut[-1]:] if cut else before
        after = t[m.end():m.end() + 300]
        end = re.search(r"\.\s+(?=[" + UP + r"0-9])|\s(?:TOČKA|Rezultat)", after)
        after = after[:end.start()] if end else after
        sent = (start + "(" + m.group(1) + ")" + after).strip()
        v = counts(m.group(1))
        neg = re.search(r"\bnije\s+(?:prihvati|donije|usvoji|izabra|primi|da)\w*|\bNIJE PRIHVATILO", sent, re.I)
        v.update({"result": NO if neg else YES, "amendment": "amandman" in start.lower(),
                  "unanimous": "jednoglasno" in sent.lower(), "text": sent[:400]})
        out.append(v)
    return out


def proposer(body):
    t = flat(body)
    m = re.search(r"predlagatelj\w*\s+(?:ove\s+točke\s+dnevnog\s+reda\s+)?(?:je\s+)?([" + UP + r"][^.,;]{3,90}?)"
                  r"(?:\s+te\b|\s+i\s+da\b|[.,;])", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"([" + UP + r"][\w\-]+(?:\s+[\w\-]+){0,5}?)\s+se\s+kao\s+predlagatelj", t)
    return m.group(1).strip() if m else ""


def questions(text, minutes_url, party):
    t = text
    i = t.find("AKTUALNI SAT")
    if i < 0:
        return []
    j = t.find("DNEVNI RED", i)
    sec = t[i + len("AKTUALNI SAT"):j if j > 0 else len(t)]
    name_re = r"[" + UP + r"][" + UP + r"\-]+(?:\s+[" + UP + r"][" + UP + r"\-]+){1,3}"
    starts = list(re.finditer(r"(?m)^\s*(\d+)\.\s+(" + name_re + r")\s*:?\s+(?=je\b|ga\b|ju\b|\w)", sec))
    out = []
    ans_re = re.compile(r"(?m)^\s*((?:Gradonač\w+|Zamjeni\w+|Pročelni\w+|Direktor\w*|Predsjedni\w+)"
                        r"[^\n]{0,110}?)\s+(?:je\s+)?(?:u ime \w+ )?(?:se\s+)?(?:odgovori|iznije|izni|izvijesti|"
                        r"pojasni|rekl|reka|navel|naveo|zahvali|osvrnu)\w*\b")
    for k, m in enumerate(starts):
        block = sec[m.end():starts[k + 1].start() if k + 1 < len(starts) else len(sec)]
        name = " ".join(w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-"))
                        for w in m.group(2).split())
        # the answerer is "<role> <Name>" (or a bare role); skip sentences that merely start with a role word
        a = next((x for x in ans_re.finditer(block)
                  if re.search(r"(?:^|\s)[" + UP + r"][\w.\-]*$",
                               re.split(r"\s+(?:je|se)\s", re.sub(r"\s+", " ", x.group(1)).strip())[0])), None)
        qtext = flat(block[:a.start()] if a else block)
        qtext = re.sub(r"^:?\s*", "", qtext)
        answer, by = None, None
        if a:
            rest = block[a.start():]
            reply = re.search(r"(?m)^\s*" + re.escape(m.group(2).split()[0]) + r"\b[^\n]{0,60}u mišljenju", rest)
            answer = flat(rest[:reply.start()] if reply else rest)
            by = re.sub(r"\s+", " ", a.group(1)).strip()
            by = re.split(r"\s+(?:je|se)\s", by)[0]
            for key, full in OFFICIALS.items():  # minutes misspell them ("Rinčič", "Gradonačlenica")
                if key in by:
                    by = full
        written = bool(re.search(r"pisan\w* odgovor", qtext + (answer or ""), re.I))
        out.append({"name": name, "party": party(name), "question": f"{name} {qtext}",
                    "to": "Gradonačelnici" if re.search(r"gradonačelnic", qtext, re.I) else None,
                    "answer": answer, "answered_by": by, "written_answer_requested": written,
                    "fonogram": None, "url": minutes_url, "no": int(m.group(1))})
    return out


# ---------------------------------------------------------------- news

STOP = {"prijedlog", "prijed", "odluke", "odluka", "odluk", "grada", "rijeke", "rijek", "godinu", "godin",
        "godine", "izvješ", "izvje", "izvjes", "izvještaj", "davanj", "prethodne", "prethodn", "sugla",
        "sugl", "izmje", "izmjen", "dopun", "dopune", "statuta", "statu", "područ", "podru", "gradsk",
        "vijeć", "vijec", "gradskog", "zaklj", "zaključ", "zakl", "poslo", "posl", "prihva", "glasov", "proti",
        "protiv", "suzdrž", "nije", "usvoje", "usvoj", "donese", "godini"}
def stems(s):
    low = s.lower()
    out = set()
    for x in re.findall(r"\w+", low):
        if len(x) >= 4 and not x.isdigit():
            st = x[:6] if len(x) > 6 else x[:5]
            if st not in STOP and st[:5] not in STOP:
                out.add(st)
    if re.search(r"izmjen\w* i dopun\w* proračun", low):  # news say "rebalans" for a budget amendment
        out.add("rebala")
    return out


def news_votes(article_text):
    """Vote sentences in news prose: [{za, protiv, suzdrzano, result, sentence, context}]."""
    sents = re.split(r"(?<=[.!?])\s+(?=[" + UP + r"„\"#])", article_text)
    out = []
    for i, s in enumerate(sents):
        low = s.lower()
        kinds = sum(bool(re.search(p, low)) for p in (r"\bza\b", r"protiv", r"suzdrž"))
        if kinds < 2 or not re.search(NUM + r"\s+(?:glas|vijeć|za\b|protiv|suzdrž)|protiv\s+" + NUM, low):
            continue
        v = {"za": None, "protiv": 0, "suzdrzano": 0}
        m = re.search(NUM + r"\s+glas\w*\s+za\b", low) or re.search(r"\bza\b[^.,]{0,40}?glasoval\w*\s+" + NUM, low)
        if m:
            v["za"] = num(m.group(1))
        m = re.search(NUM + r"\s+(?:glas\w*\s+)?protiv", low) or re.search(r"protiv\s+(?:je\s+bilo\s+|je\s+glasovalo\s+)?" + NUM, low)
        if m:
            v["protiv"] = num(m.group(1))
        m = (re.search(NUM + r"\s+(?:glas\w*\s+|vijećni\w*\s+)?(?:\w+\s+){0,2}?suzdrž", low)
             or re.search(r"suzdrž\w*\s+(?:je\s+bilo\s+|su\s+bila\s+)?" + NUM, low))
        if m:
            v["suzdrzano"] = num(m.group(1))
        if v["za"] is None:
            continue
        neg = re.search(r"nije\s+(?:prihvać|usvoj|dobi|izglas|donese)|odbijen|nisu\s+(?:prihvać|usvoj)", low)
        heads = [x for x in sents[:i] if x.startswith("##")]
        v.update({"result": NO if neg else YES, "sentence": s.strip(),
                  "heading": heads[-1].strip("# .") if heads else "",
                  "context": " ".join(sents[max(0, i - 2):i])})
        out.append(v)
    return out


def article_text(p):
    i = p.find("<h1")
    j = p.find("Povezane", i)
    s = p[i:j if j > 0 else i + 60000]
    s = re.sub(r"<(script|style|figure|figcaption)\b.*?</\1>", " ", s, flags=re.S)
    s = re.sub(r"<h[2-4][^>]*>", " ## ", s)  # headings start a "## …" sentence (topic of the next paragraphs)
    s = re.sub(r"</(h\d|p|li)>", ". ", s)
    return clean(s)


def match_item(texts, items):
    """Item whose title words match the text best (idf-weighted); None unless clearly better."""
    sets = {id(it): stems(it["title"] + " " + it.get("full_title", "")) for it in items}
    df = {}
    for st in sets.values():
        for w in st:
            df[w] = df.get(w, 0) + 1
    n = len(items)
    for t in texts:  # sentence first, then sentence + context
        ws = stems(t)
        scored = sorted(((sum(math.log((n + 1) / df[w]) for w in ws & sets[id(it)]), it) for it in items),
                        key=lambda x: -x[0])
        if scored and scored[0][0] >= 1.5 and (len(scored) == 1 or scored[0][0] > 1.3 * scored[1][0]):
            return scored[0][1]
    return None


# ---------------------------------------------------------------- members

def members():
    p = get(f"{GV}/gradski-vijecnici/", fresh=True)
    roster = []
    body = p[p.find("component-councillors"):]
    body = body[:body.find("<footer")]
    for li in re.findall(r"<li>(.*?)</li>", body, re.S):
        h3 = re.search(r"<h3>(.*?)</h3>", li, re.S)
        if not h3:
            continue
        name = clean(h3.group(1))
        party = re.search(r'political-party">(.*?)</p>', li, re.S)
        pos = re.search(r'council-position">(.*?)</p>', li, re.S)
        m = {"name": name, "party": clean(party.group(1)) if party else None}
        if pos:
            m["role"] = clean(pos.group(1))
        roster.append(m)
    clubs = get(f"{TERM}/klubovi-clanova-gradskog-vijeca-mandatno-razdoblje-2025-2029/", fresh=True)
    club_of, cur = {}, None
    for tag, txt in re.findall(r"<(p|li)\b[^>]*>(.*?)</\1>", clubs[clubs.find("main-content"):], re.S):
        txt = clean(txt)
        if tag == "p" and re.match(r"[IVX]+\.\s", txt):
            short = re.search(r"\((Klub[^)]*)\)\s*$", txt)
            cur = short.group(1) if short else re.sub(r"^[IVX]+\.\s*", "", txt)
        elif tag == "li" and cur and "Share" not in txt and "mandatno razdoblje" not in txt:
            club_of[re.split(r"\s*[-–]\s*", txt)[0].strip()] = cur
    for m in roster:
        if m["name"] in club_of:
            m["club"] = club_of[m["name"]]
    # members whose mandate is paused (mayor, deputies, personal reasons) or ended
    paused = get(f"{TERM}/clanovi-gradskog-vijeca-kojima-mandat-miruje/", fresh=True)
    for txt in re.findall(r"<p>(.*?)</p>", paused[paused.find("main-content"):], re.S):
        txt = clean(txt)
        m = re.match(r"(.+?)\s+\1\b", txt) or re.match(r"(.+?)\s+Izabran", txt)
        sub = re.search(r"obnaša zamjen\w+ (.+?)\s*\.?$", txt)
        lst = re.search(r"kandidacijske liste:?\s*(.*?)\s+Mandat", txt)
        if m:
            rep = sub.group(1).strip(" .") if sub else None
            # the substitute comes from the same list; the mayor and deputies have no list text on the page
            # (no list text: the substitute's club is a hint, not their party)
            prt = clean(lst.group(1)) if lst else None
            hint = next((x.get("club") for x in roster if x["name"] == rep), None)
            roster.append({"name": m.group(1).strip(), "party": prt, "status": "mandat miruje",
                           "replaced_by": rep, "substitute_club": hint, "note": "gradonačelnica / zamjenik" if "izabran" in txt[:200].lower()
                           and "gradonačel" in txt.lower()[:300] else "osobni razlozi"})
    ended = get(f"{TERM}/clanovi-gradskog-vijeca-kojima-je-mandat-prestao-mandatno-razdoblje-2025-2029/", fresh=True)
    body = ended[ended.find("main-content"):]
    for m in re.finditer(r"<p>\s*(.*?)\s+Pripadnost političkoj stranci:\s*(.*?)\s+Izabran", body, re.S):
        why = re.search(r"Mandat\s+člana?\w*\s+Gradskog vijeća prestao je\s+(.*?)</p>", body[m.end():], re.S)
        roster.append({"name": clean(m.group(1)), "party": clean(m.group(2)), "status": "mandat prestao",
                       "note": clean(why.group(1)) if why else None})
    return roster


# ---------------------------------------------------------------- recordings

def yt_meta(ids):
    cache_f = D / "raw" / "yt.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    missing = [i for i in ids if i not in cache]
    if missing:
        r = subprocess.run(YTDLP + ["--skip-download", "--no-warnings", "--sleep-requests", "1",
                                    "--print", "%(id)s\t%(duration)s\t%(upload_date)s\t%(title)s"]
                           + [f"https://www.youtube.com/watch?v={i}" for i in missing],
                           capture_output=True, text=True, timeout=900)
        for line in r.stdout.splitlines():
            vid, dur, up, title = (line.split("\t") + ["", "", ""])[:4]
            cache[vid] = {"duration": int(dur) if dur.isdigit() else None,
                          "upload_date": f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else None, "title": title}
        if r.returncode:
            print("yt-dlp:", r.stderr[-500:], file=sys.stderr)
        cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return cache


# ---------------------------------------------------------------- main

def build_items(page, sec, session_url):
    items = []
    for it in page["items"]:
        mats, acts = it["materials"], it["acts"]
        main = next((d for d in mats if d["name"].lower().startswith("prijedlog")), mats[0] if mats else None)
        desc_title = re.split(r"\s+-\s+", it["description"])[0] if it["description"] else ""
        head, body = sec.get(it["no"], ("", ""))
        title = (main["name"] if main else "") or head or desc_title or f"Točka {it['no']}."
        full = head or desc_title or title
        if main and main["name"] != full and main["name"] not in full:
            full = full + " | " + main["name"] if head else title
        row = {"no": it["no"], "title": title, "full_title": full, "proposer": proposer(body) if body else "",
               "status": None, "url": session_url, "attachments": mats + acts,
               "adopted_acts": acts}
        if it["description"]:
            row["outcome_note"] = it["description"]
        if body:
            vs = minutes_votes(body)
            if vs:
                row["votes"] = [{k: v[k] for k in ("za", "protiv", "suzdrzano", "result", "amendment", "unanimous",
                                                   "text")} for v in vs]
                mains = [v for v in vs if not v["amendment"]] or vs
                # several decisions under one item (president + vice-presidents, 12 awards): the one whose
                # sentence shares most words with the item title; ties → the last one
                tw = stems(title)
                last = max(reversed(mains), key=lambda v: len(stems(v["text"]) & tw))
                row["vote"] = {"za": last["za"], "protiv": last["protiv"], "suzdrzano": last["suzdrzano"],
                               "result": last["result"], "source": "zapisnik", "members": {}}
        items.append(row)
    return items


def set_status(it):
    v = it.get("vote")
    if v:
        it["status"] = "prihvaćen" if v["result"] == YES else "odbijen"
        return
    st = status_from_text(it.get("outcome_note", ""))
    if st:
        it["status"] = st
    elif it["adopted_acts"]:
        it["status"] = "prihvaćen"


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    roster = members()
    by_name = {m["name"]: m for m in roster}

    def party(name):
        m = by_name.get(name)
        if not m:  # minutes spell some names differently (Aleksandar-Saša, Rinčič)
            from difflib import get_close_matches
            c = get_close_matches(name, list(by_name), n=1, cutoff=0.85)
            m = by_name[c[0]] if c else None
        return m.get("party") if m else None

    listing = session_list(fresh)
    groups = {}
    for s in listing:
        n, sitting = session_no(s["title"])
        groups.setdefault(n, []).append((sitting or 0, s))
    recordings = []
    all_yt = []
    pages = {}
    for n, ss in groups.items():
        for _, s in ss:
            pages[s["url"]] = parse_page(get(s["url"], fresh=fresh))
            all_yt += pages[s["url"]]["youtube"]
    meta = yt_meta(list(dict.fromkeys(all_yt)))
    summary = []
    for n in sorted(groups):
        ss = [s for _, s in sorted(groups[n], key=lambda x: (x[0], x[1]["list_date"] or ""))]
        doc = {"session": n, "title": ss[-1]["title"], "date": None, "url": ss[-1]["url"], "minutes_url": None,
               "items": [], "attendance": [], "questions": [], "sittings": [], "news": [],
               "committee_conclusions": [], "gazette_url": None}
        minutes_texts = []
        part = 0
        for s in ss:
            pg = pages[s["url"]]
            dates = [hr_date(x) for x in re.split(r"(?=Nastavak)", pg["note"]) if hr_date(x)]
            sitting_date = dates[0] if dates else s["list_date"]
            doc["sittings"].append({"title": s["title"], "url": s["url"], "date": sitting_date,
                                    "continued": dates[1:], "minutes_url": pg["minutes"], "note": pg["note"]})
            sec, text = {}, ""
            if pg["minutes"]:
                text = pdf_text(get(pg["minutes"], binary=True))
                sec = sections(text)
                minutes_texts.append(text)
                doc["attendance"] = attendance(text) or doc["attendance"]
                doc["questions"] += questions(text, pg["minutes"], party)
            items = build_items(pg, sec, s["url"])
            if len(ss) > 1:  # constitutive sittings: say which one
                for it in items:
                    it["sitting"] = s["title"]
                    it["full_title"] = f"{it['full_title']} ({s['title']}, {sitting_date})"
            doc["items"] += items
            doc["news"] += s["news"]
            doc["committee_conclusions"] += pg["committee_conclusions"]
            doc["gazette_url"] = pg["gazette"] or doc["gazette_url"]
            doc["minutes_url"] = pg["minutes"] or doc["minutes_url"]
            for vid in pg["youtube"]:
                part += 1
                m = meta.get(vid, {})
                recordings.append({"id": vid, "session": n, "part": part,
                                   "url": f"https://www.youtube.com/watch?v={vid}", "date": sitting_date,
                                   "title": m.get("title") or s["title"], "duration": m.get("duration"),
                                   "kind": "youtube", "upload_date": m.get("upload_date")})
        doc["date"] = doc["sittings"][-1]["date"] if len(ss) > 1 else doc["sittings"][0]["date"]
        if len(ss) > 1:
            doc["title"] = f"Konstituirajuća sjednica Gradskog vijeća Grada Rijeke ({len(ss)} sjednice: " + \
                ", ".join(x["date"] for x in doc["sittings"]) + ")"
        if minutes_texts:
            doc["minutes_text"] = "\n\f".join(minutes_texts)
        for a in doc["attendance"]:
            a["party"] = party(a["name"])
        # news: vote totals for items the minutes do not cover
        nv = 0
        for art in doc["news"]:
            txt = article_text(get(art["url"], fresh=fresh))
            for v in news_votes(txt):
                todo = [it for it in doc["items"] if not it.get("vote")]
                it = match_item([v["sentence"], v["heading"].split(":")[0] + " " + v["sentence"],
                                 v["heading"] + " " + v["sentence"],
                                 v["context"] + " " + v["sentence"]], todo) if todo else None
                if it is None:
                    continue
                it["vote"] = {"za": v["za"], "protiv": v["protiv"], "suzdrzano": v["suzdrzano"],
                              "result": v["result"], "source": "vijest", "members": {}, "news_url": art["url"],
                              "quote": v["sentence"][:400]}
                nv += 1
        for it in doc["items"]:
            set_status(it)
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        withv = [it for it in doc["items"] if it.get("vote")]
        summary.append((n, len(doc["items"]), len(withv), nv))
        print(f"rijeka session {n} ({doc['date']}): {len(doc['items'])} items, {len(withv)} with votes "
              f"({nv} from news), attendance {len(doc['attendance'])}, questions {len(doc['questions'])}, "
              f"minutes {'yes' if doc['minutes_url'] else 'no'}, recordings "
              f"{sum(1 for r in recordings if r['session'] == n)}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    (D / "members.json").write_text(json.dumps(roster, ensure_ascii=False, indent=1))
    hours = sum(r["duration"] or 0 for r in recordings) / 3600
    print(f"recordings: {len(recordings)} ({hours:.1f} h); members: {len(roster)}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
