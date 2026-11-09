"""Sisak city council (Gradsko vijeće Grada Siska), 2025-2029 term, from sisak.hr (WordPress).

Each session has a convocation post in the category "Sjednice" (/kategorija/sjednice/:
"N. sjednica Gradskog vijeća Grada Siska u <dan>, <datum>", plus "Konstituirajuća sjednica …") whose "Dokumenti"
list holds the proposed agenda and one PDF per item, titled "2. a) Prijedlog …" (sometimes "4. a) b) c) …").
Item 1 of each session is "Usvajanje zapisnika s N-1. sjednice": the draft minutes of the previous session.
The adopted minutes are listed on /zapisnici-sa-sjednica/ ("Zapisnik s N. sjednice …"; the file names do not always
match the titles, so the title decides). Minutes are scans: OCR (tesseract, hrv) as in collect/krk.py.

The minutes are a summary: attendance by name, the question hour, the agenda ("DNEVNI RED"), then sections
"TOČKA N." with sub-points "a)", "b)" and one vote sentence each:
  a) Nakon uvodnog usmenog obrazloženja Vesne Štengl, s 13 glasova za, ništa glasova protiv i 2 glasa suzdržana:
     Marka Kričke i Edina Safića, donosi se ODLUKU …
  b) Jednoglasno s 15 glasova za, donosi se …
Counts the sentence does not give stay null ("S 15 glasova za, donosi se": protiv/suzdržano unknown).
The vote names who voted against / abstained; that is kept in the quote, members stay {} (no full roll call).

Session numbering: the constitutive session is session 0 (the city numbers the next one "1. sjednica").
Output: data/sisak/docs/session_NN.json (format of collect/cakovec.py). No recordings are published.
Cache: data/sisak/raw/web (HTML), raw/pdf, raw/ocr.

Usage: python collect/sisak.py [--fresh]
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
D = ROOT / "data" / "sisak"
HOST = "https://sisak.hr"
INDEX = "/kategorija/sjednice/"
MINUTES_PAGE = "/zapisnici-sa-sjednica/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
SEATS = 21
QUORUM = 11  # fewer counted votes than a quorum: not a council vote (committee votes are quoted too)
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
ASCII_MONTHS = {"sijecnja": 1, "veljace": 2, "ozujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6, "srpnja": 7,
                "kolovoza": 8, "rujna": 9, "listopada": 10, "studenog": 11, "studenoga": 11, "prosinca": 12}
POST = re.compile(r"""href=["'](https://sisak\.hr/((\d+)|konstituirajuca)-sjednica-gradskog-vijeca-grada-siska[^"'#]*)["']""")
DOC = re.compile(r"""<a href=["']([^"']+\.(?:pdf|docx?))["'][^>]*title=["']([^"']*)["']""", re.I)
HEAD = re.compile(r"^\f?[ \t]*T[O0][ČCčc]?\S?KA\s+(\d+)\s*\.", re.M)
_robots, _last = None, [0.0]

WORDS = {"jedan": 1, "jednim": 1, "jednog": 1, "jedna": 1, "jednom": 1, "dva": 2, "dvama": 2, "dvoje": 2,
         "tri": 3, "triju": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10,
         "ništa": 0, "nijednim": 0, "niti": 0, "bez": 0}
NUM = r"(\d+|ništa|nijednim|jedn\w*|dv\w*|tri\w*|četiri|pet|šest|sedam|osam|devet|deset)"


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests). A 403/429 is raised, never retried."""
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
    time.sleep(max(0, 1.0 - (time.time() - _last[0])))
    try:
        quoted = urllib.parse.quote(url, safe=":/?&=%#+,;~")
        data = urllib.request.urlopen(urllib.request.Request(quoted, headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f if binary else data.decode("utf-8", "replace")


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def pdf_text(path):
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    # some text layers have a broken font map ("Proraduna", "Ivi6a", "TOdKA"): OCR those too
    if len(re.sub(r"\s", "", t)) > 200 and len(re.findall(r"[čćšžČĆŠŽ]", t)) > len(t) / 400:
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
    """{session number (0 = constitutive): convocation post url} for the current term."""
    out = {}
    for page in range(1, 4):
        url = HOST + INDEX + (f"stranica/{page}/" if page > 1 else "")
        text = get(url, fresh=fresh)
        for u, key, n in POST.findall(text):
            out.setdefault(int(n) if n else 0, u)
        if 0 in out:
            break
    return out


def url_date(url):
    m = re.search(r"-(\d{1,2})-([a-z]+)-(\d{4})/?$", url)
    return f"{m.group(3)}-{ASCII_MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m else None


def documents(page):
    """[(url, title)] of the post's "Dokumenti" list."""
    i = page.find(">Dokumenti<")
    return [(u, flat(t)) for u, t in DOC.findall(page[i:] if i >= 0 else page)]


def agenda(docs):
    """Agenda items from the document titles ("2. a) Prijedlog …", "4. a) b) c) Prijedlozi …")."""
    items = []
    for u, t in docs:
        if re.search(r"\.(?:pdf|docx?)$", t, re.I) or t.count("-") > 3:  # a file name: "12.-aPrijedlog-odluke-….pdf"
            t = re.sub(r"\.(?:pdf|docx?)$", "", t, flags=re.I).replace("-", " ")
            t = re.sub(r"^(\d+)\s*\.\s*((?:[a-z]\s+)*)([a-z])(?=[A-ZČĆŠŽ])", r"\1. \2\3 ", t)
            t = re.sub(r"^(\d+\s*\.\s*)((?:[a-z]\s+)+)", lambda k: k.group(1) + "".join(x + ") " for x in k.group(2).split()), t)
            t = re.sub(r"\s+", " ", t).strip()
        m = re.match(r"(\d+)\s*\.\s*((?:[a-zčćž]\)\s*)*)(.+)", t)
        if not m:
            continue
        no, subs, title = int(m.group(1)), re.findall(r"([a-z])\)", m.group(2)), m.group(3).strip()
        att = {"name": t, "url": u}
        for s in subs or [None]:
            ex = next((x for x in items if x["no"] == no and x["sub_label"] == s), None)
            if ex:
                ex["attachments"].append(att)
                continue
            items.append({"no": no, "sub_label": s, "title": title, "full_title": title, "attachments": [att]})
    return items


def minutes_index(fresh):
    """{session number: adopted minutes url} from /zapisnici-sa-sjednica/ (current term only: the page's own list)."""
    page = get(HOST + MINUTES_PAGE, fresh=fresh)
    out = {}
    for u, t in documents(page):
        if "/wp-content/" not in u:
            continue
        if re.search(r"konstituiraju", t, re.I):
            out.setdefault(0, u)
            continue
        m = re.search(r"Zapisnik\s+sa?\s+(\d+)\s*\.\s*sjednice\s+Gradskog", t, re.I)
        if m:
            out.setdefault(int(m.group(1)), u)
    return out


def minutes_date(text):
    m = re.search(r"održane\s+(\d{1,2})\s*\.\s*(\w+)\s+(\d{4})", text[:1500])
    return f"{m.group(3)}-{MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS \
        else None


def clean(t):
    t = t.replace(",,", "„").replace("€)", "e)")  # OCR: ,,Kristalna"; "e)" read as "€)"
    return t


def headings(text, items):
    """[(pos, item)]: each "TOČKA N." section heading with its item (the first, for an item with sub-items)."""
    out, last = [], 0
    for m in HEAD.finditer(text):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n >= last and not any(x is it for _, x in out):
            out.append((m.start(), it))
            last = n
    return out


def num(w):
    if w is None:
        return None
    w = w.lower()
    if re.fullmatch(r"[\dlio]+", w) and re.search(r"\d", w):  # OCR: "l7", "1O"
        w = w.replace("l", "1").replace("i", "1").replace("o", "0")
    if w.isdigit():
        return int(w)
    for k, v in WORDS.items():
        if w.startswith(k[:4]) and (w == k or k[:4] in ("jedn", "ništ", "nije")):
            return v
    return WORDS.get(w)


# a vote: "[a)] [Nakon …,] [jednoglasno] s 13 glasova za[: names], ništa glasova protiv i 2 glasa suzdržana: …,
# donosi se ODLUKU …" or, verb first, "Zapisnik … usvaja se jednoglasno sa 17 glasova za."
ANCHOR = re.compile(r"\b[sS]a?[\s_]*(?P<za>[\dlIO]*\d[\dlIO]*|jednim|dva|tri)\s+glas\w*\s+(?:„|\")?[zZ][aA]\b")
VERB = re.compile(r"\b(?P<neg>ne\s+|nije\s+)?(?:donos[ie]\s+[sj]e|biraju\s+se|donesen\w*|usvaja\s+se|usvojen\w*|prihvaća\s+se|prihvaćen\w*|"
                  r"daje\s+se|dan[aoe]?\b|izabran\w*|bira\s+se|imenuj\w*\s+se|imenovan\w*|utvrđuje\s+se|utvrđen\w*|"
                  r"razrješ\w*|potvrđuje\s+se|potvrđen\w*|verificira\w*|odbija\s+se|odbijen\w*)", re.I)


# a roll-call style vote: "Za Prijedlog … glasuje 4 vijećnika: …, protiv glasuje 13 vijećnika: … te ništa
# suzdržanih glasova. Utvrđuje se da Prijedlog … nije usvojen …"
ALT = re.compile(r"(?:^|\n|\.\s)Za\s+[^\n]{0,300}?\bglasuj?e\s+(?P<za>\d+)\s+vijećnik\w*(?P<rest>.{0,1500}?)"
                 r"(?:\.\s*\n|\n\s*\n)", re.S)


def find_alt(t, pos, end):
    out = []
    for a in ALT.finditer(t, pos, end):
        rest = re.sub(r"\s+", " ", a.group("rest"))
        p = re.search(rf"protiv\s+glasuj?e\s+{NUM}\b|{NUM}\s+(?:vijećnik\w*|glas\w*)\s+protiv", rest, re.I)
        sz = re.search(rf"{NUM}\s+suzdrž\w*|suzdrž\w*\s+(?:je\s+)?{NUM}\b|suzdržan\w*\s+glasuj?e\s+{NUM}\b", rest, re.I)
        za = int(a.group("za"))
        protiv = num(next(g for g in p.groups() if g)) if p else None
        suzd = num(next(g for g in sz.groups() if g)) if sz else None
        after = t[a.end():min(end, a.end() + 600)]
        neg = re.search(r"nije\s+(?:usvojen|donesen|prihvaćen)", after[:400]) is not None
        result = NO if neg or (protiv is not None and za <= protiv) else YES
        quote = re.sub(r"\s+", " ", a.group(0)).strip()
        out.append((a.start(), (None, {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
                                        "unanimous": False, "quote": quote[:400]})))
    return out


def sentence_start(t, pos, at):
    """Start of the sentence holding position at: after a blank line or a full stop before a capital letter."""
    ends = [m.end() for m in re.finditer(r"\n[ \t]*\n|\.\s+(?=[A-ZČĆŠŽĐ„])", t[pos:at])]
    return pos + ends[-1] if ends else pos


PLAIN = re.compile(r"(?:usvaja\s+se|donosi\s+se|usvojen\w*\s+je)\s+jednoglasno\b(?![^.\n]{0,15}\b(?:s|sa)\s*\d)")


def find_plain(t, pos, end):
    """"Zapisnik … usvaja se jednoglasno bez primjedbi.": unanimous without counts (za null, protiv 0, suzdržano 0)."""
    out = []
    for a in PLAIN.finditer(t, pos, end):
        sstart = sentence_start(t, pos, a.start())
        e = t.find(".", a.end(), end)
        quote = re.sub(r"\s+", " ", t[sstart:(e + 1) if e > 0 else a.end()]).strip()
        out.append((a.start(), (None, {"za": None, "protiv": 0, "suzdrzano": 0, "result": YES, "members": {},
                                        "unanimous": True, "quote": quote[:400]})))
    return out


def find_votes(t, pos, end):
    """[(sub label from the text or None, vote)] in t[pos:end], in text order."""
    alt = find_alt(t, pos, end) + find_plain(t, pos, end)
    return [v for _, v in sorted(find_anchor_votes(t, pos, end) + alt, key=lambda x: x[0])]


def find_anchor_votes(t, pos, end):
    out = []
    anchors = list(ANCHOR.finditer(t, pos, end))
    for i, a in enumerate(anchors):
        nxt = anchors[i + 1].start() if i + 1 < len(anchors) else end
        sstart = sentence_start(t, pos, a.start())
        pre = t[sstart:a.start()]
        tail = t[a.end():min(nxt, a.end() + 1500)]
        vpre = [v for v in VERB.finditer(pre) if not re.match(r"\s+da\b", pre[v.end():])]  # "Utvrđuje se da …"
        vpost = VERB.search(tail)
        if vpre and not re.search(r"Nakon|obrazlo", pre[vpre[-1].end():]):  # verb first: up to the sentence end
            e = re.search(r"\.\s*(?:\n|$)|\n\s*\n", tail)
            rest, verb = tail[:e.start() if e else 300], vpre[-1]
        elif vpost:
            rest, verb = tail[:vpost.start()], vpost
        else:
            continue
        rest1 = re.sub(r"\s+", " ", rest)
        za = num(a.group("za"))
        protiv = suzd = None
        p = re.search(rf"\b{NUM}\s+(?:glas\w*\s+)?(?:„|\")?protiv", rest1, re.I)
        if p:
            protiv = num(p.group(1))
        s = re.search(rf"\b{NUM}\s+(?:glas\w*\s+)?(?:„|\")?suzdrž", rest1, re.I)
        if s:
            suzd = num(s.group(1))
        jedn = bool(re.search(r"jednoglasno", pre + " " + rest1[:40], re.I))
        if jedn:
            protiv = 0 if protiv is None else protiv
            suzd = 0 if suzd is None else suzd
        neg = bool(verb.group("neg")) or verb.group(0).lower().startswith("odbij")
        result = NO if neg or (protiv is not None and za is not None and za <= protiv) else YES
        quote = t[sstart:a.end()] + rest + (verb.group(0) if verb is vpost else "")
        quote = re.sub(r"\s+", " ", quote).strip()
        lab = re.match(r"\s*(?:\d{1,2}[ \t]*\n\s*)?([a-zčćž1])\)", t[sstart:a.start()].lstrip("\n"))
        sub = lab.group(1) if lab and lab.group(1) != "1" else None
        if sum(x or 0 for x in (za, protiv, suzd)) < QUORUM:  # a committee's vote reported in the minutes
            continue
        if za is not None and not (1 <= za <= SEATS):
            print(f"   implausible count {za}: {quote[:80]}, dropped", flush=True)
            continue
        if re.search(r"\b(?:govori|ističe|kaže|smatra|navodi|pita|podsjeća)\b", pre):  # a vote quoted in a speech
            continue
        if re.search(r"amandman", pre, re.I):
            continue
        out.append((a.start(), (sub, {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
                          "unanimous": jedn and result == YES, "quote": quote[:400]})))
    return out


def agenda_from_minutes(t):
    """Agenda items (no, sub_label, title) from the minutes' "DNEVNI RED" list, before "TOČKA 1."."""
    h = HEAD.search(t)
    d = re.search(r"DNEVNI\s+RED|dnevni\s+red", t)
    if not h or not d or d.start() > h.start():
        return []
    block = t[d.end():h.start()]
    items, no, cur = [], None, None
    for ln in block.split("\n"):
        s = ln.strip()
        m = re.match(r"(\d{1,2})\s*\.\s+(\S.*)", s)
        a = re.match(r"([a-z])\)\s*(\S.*)", s)
        if m and (no is None or int(m.group(1)) == no + 1):
            no = int(m.group(1))
            cur = {"no": no, "sub_label": None, "title": m.group(2)}
            items.append(cur)
        elif a and no is not None:
            cur = {"no": no, "sub_label": a.group(1), "title": a.group(2)}
            items.append(cur)
        elif cur is not None and s and not re.match(r"(Dnevni red|Predsjednik|Tomislav Kralj)", s):
            cur["title"] += " " + s
        elif not s:
            cur = None if cur is None or len(cur["title"]) > 20 else cur
    for it in items:
        it["title"] = re.sub(r"\s+", " ", it["title"]).strip()
    # an item with sub-items: its own line is just a heading ("2. Prijedlozi odluka:")
    heads = {it["no"] for it in items if it["sub_label"]}
    return [it for it in items if it["sub_label"] or it["no"] not in heads]


def items_from_sections(t, subs_too=True):
    """Items from the "TOČKA N." headings when the agenda is not listed: the section's first paragraph is the
    title; sub-items "a) …" are the first line with each label in the section. For the constitutive session
    (subs_too False) one item per section holds all its votes (elections of committees, one vote each)."""
    heads, last = [], 0
    for m in HEAD.finditer(t):
        n = int(m.group(1))
        if n < last or any(n == x for _, x in heads):
            continue
        heads.append((m.end(), n))
        last = n
    items = []
    for i, (pos, n) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        sec = t[pos:end]
        subs = {}
        for k in re.finditer(r"^[ \t]*([a-z])\)[ \t]+(\S[^\n]*(?:\n(?![ \t]*\n)[^\n]*){0,2})", sec, re.M):
            subs.setdefault(k.group(1), re.sub(r"\s+", " ", k.group(2)).strip())
        if subs_too and len(subs) > 1:
            for lab, title in sorted(subs.items()):
                items.append({"no": n, "sub_label": lab, "title": title[:300], "full_title": title[:300]})
            continue
        para = re.split(r"\n[ \t]*\n", sec.strip())[0]
        title = re.sub(r"\s+", " ", para).strip()[:300]
        items.append({"no": n, "sub_label": None, "title": title, "full_title": title})
    return items


def minutes_votes(t):
    """({point no: [(sub label or None, vote)]}, formulas found) from the "TOČKA N." sections."""
    heads, last = [], 0
    for m in HEAD.finditer(t):
        n = int(m.group(1))
        if n < last or any(n == x for _, x in heads):
            continue
        heads.append((m.start(), n))
        last = n
    out = {}
    for i, (pos, n) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        out[n] = find_votes(t, pos, end)
    found = len(ANCHOR.findall(t[heads[0][0]:])) + len(ALT.findall(t[heads[0][0]:])) if heads else 0
    return out, found


def assign(items, votes):
    """Votes to items: by order when a point has as many votes as (sub-)items, else by the sub label."""
    unmatched = []
    for n, vs in votes.items():
        subs = [x for x in items if x["no"] == n]
        if not vs:
            continue
        if len(subs) == 1:
            subs[0]["votes"] = [v for _, v in vs]
        elif len(subs) == len(vs) and subs:
            for x, (_, v) in zip(subs, vs):
                x["votes"] = [v]
        else:
            for lab, v in vs:
                x = next((x for x in subs if x["sub_label"] == lab), None)
                if x is None:
                    unmatched.append((n, lab, v))
                else:
                    x.setdefault("votes", []).append(v)
    for x in items:
        if x.get("votes"):
            x["vote"] = x["votes"][-1]
    return unmatched


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    idx = sessions(fresh)
    adopted = minutes_index(fresh)
    pages = {n: get(u, fresh=fresh) for n, u in sorted(idx.items())}
    drafts = {}
    for n, page in pages.items():  # item 1 of session n: draft minutes of session n-1
        for u, t in documents(page):
            m = re.search(r"Usvajanje\s+zapisnika\s+sa?\s+(\d+|konstituiraju\w*)", t, re.I)
            if m:
                k = int(m.group(1)) if m.group(1).isdigit() else 0
                drafts.setdefault(k, u)
    for n, url in sorted(idx.items()):
        date = url_date(url)
        if date and date < TERM_START:
            continue
        docs = documents(pages[n])
        items = agenda(docs)
        murl = adopted.get(n) or drafts.get(n)
        text = clean(pdf_text(get(murl, binary=True))) if murl else None
        votes, found = minutes_votes(text) if text else ({}, 0)
        if text:  # titles and items without material from the minutes' agenda
            listed = agenda_from_minutes(text)
            if n == 0:  # the constitutive minutes' agenda does not follow the "TOČKA N." numbering
                listed = []
            for a in listed or (items_from_sections(text, n != 0) if not items else []):
                ex = next((x for x in items if x["no"] == a["no"] and x["sub_label"] == a["sub_label"]), None)
                if ex is None:
                    items.append({"no": a["no"], "sub_label": a["sub_label"], "title": a["title"],
                                  "full_title": a["title"], "attachments": []})
        items.sort(key=lambda x: (x["no"], x["sub_label"] or ""))
        unmatched = assign(items, votes)
        matched = sum(len(x.get("votes", [])) for x in items)
        for it in items:
            it["proposer"] = ""
            v = it.get("vote")
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        title = "Konstituirajuća sjednica Gradskog vijeća Grada Siska" if n == 0 else \
            f"{n}. sjednica Gradskog vijeća Grada Siska"
        doc = {"session": n, "title": title, "date": (text and minutes_date(text)) or date, "url": url,
               "minutes_url": murl, "minutes_draft": bool(murl) and murl not in adopted.values(),
               "minutes_text": text, "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"sisak session {n} ({doc['date']}): {len(items)} items, {nv} with votes; "
              f"{found} vote formulas in minutes, {sum(len(v) for v in votes.values())} in sections, {matched} matched; "
              f"minutes {'draft' if doc['minutes_draft'] else 'adopted' if murl else 'no'}", flush=True)
        for n_, lab, v in unmatched:
            print(f"   unmatched vote {n_}{lab or ''}: {v['quote'][:100]}", flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
