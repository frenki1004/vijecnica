"""Bjelovar city council (Gradsko vijeće Grada Bjelovara), 2025-2029 term, from www.bjelovar.hr.

Sources (WordPress "dokumenti" posts):
- materials: tag "Najave sjednica" (/dokumenti-oznaka/najave-sjednica/), one post per session ("Materijali za N.
  sjednicu Gradskog vijeća") with the call ("1.-Saziv-...pdf": agenda with items "N." and sub-items "a)", and the
  date), one PDF per item named "N.-..." / "N.a.-..." and the draft minutes of the previous session ("1.1.-Skraceni-
  zapisnik-N-1...pdf");
- minutes: category "Zapisnici" (/dokumenti-kategorija/zapisnici/), one post per session with the adopted
  "Skraćeni zapisnik" as .docx (text via macOS textutil). Where no .docx is posted yet, the draft minutes PDF from the
  next session's materials is used.
- recordings: YouTube live streams of the city channel (@gradbjelovar5843), listed with yt-dlp; titles
  "N. SJEDNICA GRADSKOG VIJEĆA GRADA BJELOVARA", matched to sessions by number and date (numbers repeat across terms).

The minutes have one "TOČKA N." section per agenda item ("a)", "b)" for sub-items) and the chair's formula:
  Nakon glasovanja utvrđuje da je Gradsko vijeće jednoglasno (sa 16 glasova) donijelo ZAKLJUČAK ...
  ... sa 17 glasova „za“ i 3 glasa „protiv“ (od ukupno 20 vijećnika) donijelo ODLUKU ...
Counts are taken only as stated: "jednoglasno" gives protiv = suzdržano = 0 and za only when the formula says "sa N
glasova/vijećnika"; "(od ukupno N vijećnika)" is the number present, not a vote count, so it is not used; a count
not named (e.g. suzdržani in "17 za i 3 protiv") stays null. Amendment votes are skipped.

Output: data/bjelovar/docs/session_NN.json (format of collect/cakovec.py), data/bjelovar/recordings.json.
Cache: data/bjelovar/raw/web (HTML), raw/pdf (PDF, DOCX), raw/ocr, raw/youtube.json.

Usage: python collect/bjelovar.py [--fresh]
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
D = ROOT / "data" / "bjelovar"
HOST = "https://www.bjelovar.hr"
INDEX = "/dokumenti-kategorija/zapisnici/"
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


MATERIALS = "/dokumenti-oznaka/najave-sjednica/"
CHANNEL = "https://www.youtube.com/@gradbjelovar5843/streams"
YTDLP = [os.path.expanduser("~/.local/bin/yt-dlp"), "--js-runtimes", "node", "--no-warnings"]
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
TERM_START = "2025-06-01"
SEATS = 21
QUOTES = str.maketrans({c: '"' for c in "„“”«»″"})
VOTE = re.compile(r"(?:utvrđuje|konstatira)\s+da\s+(?:je|su)\s+((?:(?!\n\s*\n)[^.])"
                  r"{0,300}?)\b(donijel\w*|odnijel\w*|izabral\w*|usvojil\w*|usvojen\w*|odbijen\w*|prihvatil\w*|"
                  r"imenoval\w*|razriješil\w*|dal[oa]\b|potvrdil\w*)", re.S)
TYPES = r"(?:ODLUK\w*|ZAKLJUČ\w*|RJEŠENJ\w*|PROGRAM\w*|PRAVILNIK\w*|IZVJEŠĆ\w*|IZVJEŠTAJ\w*|PLAN\w*|PRORAČUN\w*|" \
        r"STATUT\w*|POSLOVNIK\w*|IZMJEN\w*|ANALIZ\w*|SMJERNIC\w*|STRATEGIJ\w*|[IV]+\.\s+IZMJEN\w*)"


def norm(t):
    return t.translate(QUOTES)


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ddate(m):
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS else None


def doc_text(path):
    """Text of a minutes file: .docx via textutil, PDF via pdftotext/OCR."""
    if Path(path).suffix in (".docx", ".doc"):
        return subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True,
                              text=True, check=True).stdout
    return pdf_text(path)


def uploads_ok(urls):
    """True when the post's files were uploaded in this term (wp-content/uploads/YYYY/MM >= 2025/06)."""
    ym = [m for u in urls for m in re.findall(r"/uploads/(\d{4})/(\d{2})/", u)]
    return bool(ym) and max(ym) >= ("2025", "06")


def post_files(page):
    """[(name, url)] of the uploaded files linked from a document post."""
    out = []
    for u in re.findall(r'href="(https://www\.bjelovar\.hr/wp-content/uploads/[^"]+\.(?:pdf|docx?|xlsx?))"', page):
        if u not in [x[1] for x in out]:
            out.append((urllib.parse.unquote(u.rsplit("/", 1)[-1]), u))
    return out


def listing(path, pattern, fresh, pages=3):
    """{session number: post url} from a tag/category listing (newest first), this term's posts only."""
    out = {}
    for page in range(1, pages + 1):
        try:
            t = get(HOST + path + (f"page/{page}/" if page > 1 else ""), fresh=fresh)
        except Exception:
            break
        new = False
        for u in dict.fromkeys(re.findall(r'href="(https://www\.bjelovar\.hr/dokumenti/[^"]+/)"', t)):
            m = re.search(pattern, u)
            if not m:
                continue
            n = 1 if "konstituir" in u else int(m.group(1))
            if n in out:
                continue
            files = post_files(get(u, fresh=fresh))
            if uploads_ok([f[1] for f in files]):
                out[n] = (u, files)
                new = True
        if not new and page > 1:
            break
    return out


def agenda(call):
    """[(no, sub, title)] from the call's "DNEVNI RED" (items "N." and sub-items "a)"); a heading item ending in
    ":" ("5. Donošenje:") prefixes its sub-items' titles and is kept as (no, None, heading)."""
    t = norm(call)
    m = re.search(r"D\s*N\s*E\s*V\s*N\s*I\s+R\s*E\s*D", t)
    if not m:
        return []
    body = t[m.end():]
    stop = re.search(r"\n\s*(?:Materijali\s+za|Materijal\s+za|Molim|NAPOMENA|PREDSJEDNI|Predsjedni)", body)
    body = body[:stop.start()] if stop else body
    rows, cur, expect = [], None, 1
    for ln in body.splitlines():
        s_ = ln.strip()
        k = re.match(r"(\d+)\.\s+(\S.*)", s_)
        a = re.match(r"([a-z])\)\s*(\S.*)", s_)
        if k and int(k.group(1)) == expect:
            cur = [expect, None, k.group(2)]
            rows.append(cur)
            expect += 1
        elif a and rows:
            cur = [rows[-1][0], a.group(1), a.group(2)]
            rows.append(cur)
        elif s_ and cur is not None and not re.match(r"[-•*]", s_):
            cur[2] += " " + s_
        elif not s_ and cur is not None and rows and len(rows) > 0:
            pass
    out = []
    for no, sub, title in rows:
        out.append((no, sub, re.sub(r"\s+", " ", title).strip(" ;.")))
    return out


def items_from(ag, files, url):
    heads = {no: t for no, sub, t in ag if sub is None}
    items = []
    for no, sub, title in ag:
        has_subs = any(n == no and s_ for n, s_, _ in ag)
        if sub is None and has_subs:
            continue  # its sub-items carry it; restored if the minutes give the heading its own vote
        full = title
        if sub and heads.get(no):
            h = heads[no].rstrip(":").strip()
            low = title[:2] if title[1:2].isupper() or title[1:2] in ".-" else title[0].lower() + title[1:2]
            full = f"{h} {low}{title[2:]}" if h.lower() in ("donošenje", "razmatranje", "davanje") \
                else f"{h}: {title}"
        pref = rf"{no}\.{sub}\.?-" if sub else rf"{no}\.-"
        att = [{"name": n, "url": u} for n, u in files if re.match(pref, n) and not re.search(r"(?i)saziv|zapisnik", n)]
        items.append({"no": no, "sub_label": sub, "title": full, "full_title": full, "proposer": "", "status": None,
                      "url": url, "attachments": att})
    return items


def sections(text):
    """[(pos, no)] of the "TOČKA N." headings in the minutes, in order."""
    out, last = [], 0
    for m in re.finditer(r"(?m)^[ \t\f]*TOČKA\s+(\d+)\s*\.", text):
        n = int(m.group(1))
        if n > last:
            out.append((m.start(), n))
            last = n
    return out


def headings(text, items):
    """[(pos, item)]: each "TOČKA N." section start with its item (the first sub-item for an item with several)."""
    out = []
    for pos, n in sections(text):
        it = next((i for i in items if i["no"] == n), None)
        if it is not None:
            out.append((pos, it))
    return out


def act_after(t, m):
    """Name of the act a formula decided: "ZAKLJUČAK / o prihvaćanju ..." or "izabralo X za potpredsjednika"."""
    tail = t[m.end():m.end() + 600]
    if m.group(2).startswith("izabral"):
        return re.sub(r"\s+te\s+donijel\w*.*$", "", tail.split("\n")[0]).strip(" .")
    lines = [l.strip() for l in tail.split("\n")]
    out = []
    for l in lines:
        if not l and out:
            if len(out) > 1:
                break
            continue
        if l.startswith("(") or re.match(r"Zaključ\w*\s+Klasa|Klasa:", l):
            break
        if l:
            out.append(l)
    name = re.sub(r"^\d+\s+", "", re.sub(r"\s+", " ", " ".join(out)).strip())  # a page number before the act
    k = re.match(TYPES + r"\s*", name)
    if k:
        name = k.group(0).strip().capitalize() + " " + name[k.end():]
    return name[:250]


def parse_vote(t, m):
    clause = re.sub(r"\s+", " ", m.group(1))
    za = re.search(r"(\d+)\s+glas\w*\s+\"?\s*za\b", clause)
    pr = re.search(r"(\d+)\s+(?:glas\w*\s+)?\"?\s*protiv", clause)
    su = re.search(r"(\d+)\s+(?:glas\w*\s+)?\"?\s*suzdrž", clause)
    unan = "jednoglasno" in clause
    if unan:
        k = re.search(r"\(\s*(?:sa\s+)?(\d+)\s+(?:glas|vijećnik)", clause)
        za, pr, su = (int(k.group(1)) if k else None), 0, 0
    else:
        za, pr, su = (int(x.group(1)) if x else None for x in (za, pr, su))
    neg = m.group(2).startswith("odbij") or re.search(r"\bnije\s+(?:donij|usvoj|prihvat|izabr)", clause)
    result = NO if neg or (za is not None and pr is not None and za <= pr) else YES
    return {"za": za, "protiv": pr, "suzdrzano": su, "result": result, "members": {},
            "unanimous": bool(unan) and result == YES,
            "quote": re.sub(r"\s+", " ", t[m.start():m.end() + 120]).strip()[:300]}


def votes_in(t, a, b):
    """[(vote, act)] of the chair's formulas in t[a:b] (amendments and non-votes skipped)."""
    out = []
    for m in VOTE.finditer(t, a, b):
        clause = m.group(1)
        if not re.search(r"jednoglasno|\d+\s+glas", clause):
            continue
        if re.search(r"amandman", t[max(a, m.start() - 250):m.end()], re.I):
            continue
        v = parse_vote(t, m)
        tot = sum(x for x in (v["za"], v["protiv"], v["suzdrzano"]) if x)
        if tot > SEATS:
            print(f"   implausible count, dropped: {v['quote'][:90]}", flush=True)
            continue
        out.append((v, act_after(t, m), m.start(), m.end()))
    return out


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "donoše", "odluke", "odluka", "grada",
                                                                 "bjelov", "godinu", "godini", "izmjen", "dopune",
                                                                 "dopuna", "programa", "progra"}


def similarity(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, len(a | b))


def minutes_items(text, items, url, heads):
    """Votes from the minutes into the agenda items, per "TOČKA N." section. Within a section with sub-items each
    vote goes to the unused sub-item (or the heading item itself) whose title best matches what was put to the vote
    ("daje na glasovanje Prijedlog ...") and adopted (the act after the formula); the "a)" markers of the minutes are
    not reliable enough to use."""
    t = norm(text)
    secs = sections(t)
    by_no, matched = {}, 0
    for it in items:
        by_no.setdefault(it["no"], []).append(it)
    for k, (pos, no) in enumerate(secs):
        end = secs[k + 1][0] if k + 1 < len(secs) else len(t)
        vs, prev = [], pos
        for v, act, m0, m1 in votes_in(t, pos, end):
            put = re.findall(r"na\s+(?:glasovanje|usvajanje)\s+(.{0,300}?)(?:\.(?=\s+[A-ZČĆŠŽĐ]|\s*$)|\.?\n\s*\n)", t[prev:m0], re.S)
            put = re.sub(r"\s+", " ", put[-1]).strip() if put else ""
            vs.append((v, act, put + " " + act, put))
            prev = m1
        group = by_no.get(no)
        if not group:  # an item added to the agenda at the session ("dopuna dnevnog reda"): titled by its act
            if not vs:
                continue
            group = by_no[no] = [{"no": no, "sub_label": None, "title": vs[0][1] or f"Točka {no}.",
                                  "full_title": vs[0][1] or f"Točka {no}.", "proposer": "", "status": None,
                                  "url": url, "attachments": []}]
        vs = [x[:3] + (x[3],) for x in vs]
        subs = [i for i in group if i["sub_label"]]
        if subs:
            cands = list(subs) + ([None] if heads.get(no) else [])
            for v, act, ctx, _ in vs:
                free = [c for c in cands if c is None or "vote" not in c] or [None]
                score = lambda c: similarity(ctx, heads[no] if c is None else c["title"])
                best = max(free, key=lambda c: (score(c), -cands.index(c)))
                if best is None:
                    if not heads.get(no) or any(i["sub_label"] is None for i in group):
                        print(f"   TOČKA {no}: vote not placed: {act[:70]}", flush=True)
                        continue
                    best = {"no": no, "sub_label": None, "title": act or heads[no], "full_title": act or heads[no],
                            "proposer": "", "status": None, "url": url, "attachments": []}
                    group.insert(0, best)
                    cands.remove(None)
                best["vote"], best["votes"] = v, [v]
                matched += 1
        elif len(vs) == 1 and len(group) == 1:
            group[0]["vote"], group[0]["votes"] = vs[0][0], [vs[0][0]]
            matched += 1
        elif len(vs) > 1 and len(group) == 1:
            base = group.pop()
            for j, (v, act, _, put) in enumerate(vs):
                name = put if len(put) > 20 else act or base["title"]  # "Prijedlog odluke o dodjeli ... OPG-u Perec"
                name = name[0].upper() + name[1:]
                group.append(dict(base, sub_label=chr(97 + j), title=name, full_title=name, vote=v, votes=[v]))
            matched += len(vs)
    out = []
    for no in sorted(by_no):
        out.extend(by_no[no])
    return out, matched


def youtube(sessions_dates, fresh):
    """Session streams on the city channel: [(session, id, title)] matched by number and date (cached)."""
    cache = D / "raw" / "youtube.json"
    known = json.loads(cache.read_text()) if cache.exists() and not fresh else {}
    try:
        lines = subprocess.run(YTDLP + ["--flat-playlist", "--print", "%(id)s\t%(title)s", CHANNEL],
                               capture_output=True, text=True, check=True, timeout=300).stdout.splitlines()
    except Exception as e:
        print(f"   yt-dlp listing failed: {e}", flush=True)
        lines = [f"{k}\t{v['title']}" for k, v in known.items()]
    out = []
    for ln in lines:
        vid, title = ln.split("\t", 1)
        m = re.match(r"\s*(\d+)\.\s*sjednica\s+gradskog\s+vije", title, re.I) or \
            re.match(r"\s*(konstituirajuća)\s+sjednica", title, re.I)
        if not m:
            continue
        n = 1 if not m.group(1).isdigit() else int(m.group(1))
        if n not in sessions_dates:
            continue
        if vid not in known:
            time.sleep(1)
            try:
                d = subprocess.run(YTDLP + ["--skip-download", "--print", "%(release_date)s\t%(upload_date)s",
                                            f"https://www.youtube.com/watch?v={vid}"], capture_output=True,
                                   text=True, timeout=120).stdout.strip()
            except Exception:
                d = ""
            known[vid] = {"title": title, "date": d}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(known, ensure_ascii=False, indent=1))
        d = known[vid]["date"].split("\t")
        day = next((x for x in d if re.fullmatch(r"\d{8}", x)), None)
        if not day:  # unavailable (private) video
            continue
        day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        sd = sessions_dates[n]
        if day >= TERM_START and (not sd or abs((time.mktime(time.strptime(day, "%Y-%m-%d")) -
                                                 time.mktime(time.strptime(sd, "%Y-%m-%d"))) / 86400) <= 3):
            out.append((n, vid, title, day))
    return out


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    mats = listing(MATERIALS, r"materijali-za-(\d+)-sjednicu|saziv-konstituir", fresh)
    mins = listing(INDEX, r"zapisnik-(?:sa-)?(\d+)-(?:konstituirajuce-)?sjednice", fresh)
    dates = {}
    for n in sorted(set(mats) | set(mins)):
        url, files = mats.get(n, (None, []))
        call = next((u for name, u in files if re.search(r"(?i)saziv", name)), None)
        call_text = pdf_text(get(call, binary=True)) if call else ""
        minutes = next((u for name, u in mins.get(n, (None, []))[1] if re.search(r"(?i)zapisnik", name)), None)
        if not minutes and n + 1 in mats:  # draft minutes in the next session's materials
            minutes = next((u for name, u in mats[n + 1][1]
                            if re.search(rf"(?i)zapisnik\w*-{n}\.", name.replace("-sa-", "-"))), None)
        text = doc_text(get(minutes, binary=True)) if minutes else None
        d_min = ddate(re.search(r"održane\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})", norm(text or "")[:1500]))
        d_call = ddate(re.search(r"za\s+(\d{1,2})\.\s*(\w+)\s*(?:\(\w+\)\s*)?(\d{4})", norm(call_text)))
        # the minutes' date wins, unless it falls before the term (session 6: "održane 30. siječnja 2025.", a typo
        # for 2026; its call is for 30. 1. 2026)
        date = d_min if d_min and (d_min >= TERM_START or not d_call) else d_call or d_min
        if date and date < TERM_START:
            continue
        dates[n] = date
        ag = agenda(call_text) if call_text else []
        items = items_from(ag, files, url or mins.get(n, (None,))[0])
        found = matched = 0
        if text:
            if not items:  # no call: one item per "TOČKA N." section
                items = [{"no": no, "sub_label": None, "title": f"Točka {no}.", "full_title": f"Točka {no}.",
                          "proposer": "", "status": None, "url": mins[n][0], "attachments": []}
                         for _, no in sections(norm(text))]
            heads = {no: t_ for no, sub, t_ in ag if sub is None and any(n == no and s_ for n, s_, _ in ag)}
            items, matched = minutes_items(text, items, url, heads)
            secs = sections(norm(text))
            found = len(votes_in(norm(text), secs[0][0], len(text))) if secs else 0
        for it in items:
            v = it.get("vote")
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
        doc = {"session": n, "title": f"{n}. sjednica Gradskog vijeća Grada Bjelovara" +
               (" (konstituirajuća)" if n == 1 else ""), "date": date, "url": url or mins[n][0],
               "minutes_url": minutes, "minutes_text": text, "call_url": call, "items": items, "attendance": [],
               "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"bjelovar session {n} ({date}): {len(items)} items, {nv} with votes, formulas in minutes {found} "
              f"(matched {matched}), minutes {'yes' if text else 'no'}", flush=True)
        if text:
            for it in items:
                if not it.get("vote"):
                    print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)
    recs, parts = [], {}
    for n, vid, title, day in sorted(youtube(dates, fresh), key=lambda x: (x[0], x[3])):
        parts[n] = parts.get(n, 0) + 1
        recs.append({"id": f"bjelovar-{n:02d}-{parts[n]}", "session": n, "part": parts[n], "date": day,
                     "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube", "title": title})
    (D / "recordings.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"bjelovar: {len(recs)} recordings", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
