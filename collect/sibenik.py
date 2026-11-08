"""Collect Šibenik City Council (Gradsko vijeće Grada Šibenika) sessions, 2025-2029 term.

sibenik.hr: the term index (/stranice/sjednice-gradskog-vijeca-2025-2029/260.html) links one page per
session (/sjednice/N-sjednica-…/9x.html) with the date, the adopted acts (.docx), the minutes PDF once
published, one YouTube embed, and a link to the announcement (/najavesjednica/…) that holds the
numbered materials ("1.", "4. a.", "3. prilog.", "DOPUNA1." …).
Minutes (zapisnik) are Word PDFs, except the constitutive session (a scan, OCRed with tesseract):
attendance by name, the question hour, the adopted agenda ("DNEVNI RED" + numbered list, sub-items
"a)" / "a." / "5.a."), then sections "Točka N." (sub-items also as bare "5.b." / "b." / "20. a)") with a
summary of every speaker and the vote: „ZA“ je glasovalo 12 vijećnika, 4 je bilo „SUZDRŽANIH“, 0 je bilo
„PROTIV“, pa predsjednik Gradskog vijeća konstatira da je … donesen većinom glasova / jednoglasno /
nije prihvaćen. No per-member votes.

Agenda: from the minutes when published, else from the announcement's materials (DOPUNA k is
numbered after the last regular item, as the council does when it adopts the supplement).
Cache: data/sibenik/raw/web (HTML), raw/pdf, raw/ocr (tesseract text). No video is downloaded.
Output: data/sibenik/docs/session_NN.json, data/sibenik/recordings.json, data/sibenik/members.json.

Usage: python collect/sibenik.py [--fresh]   (--fresh re-fetches the index, session and announcement pages)
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "sibenik"
HOST = "https://www.sibenik.hr"
INDEX = "/stranice/sjednice-gradskog-vijeca-2025-2029/260.html"
MEMBERS = "/stranice/sastav-gradskog-vijeca/42.html"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
UP = "A-ZČĆŠŽĐ"
_last = [0.0]


def get(path, binary=False, fresh=False):
    url = path if path.startswith("http") else HOST + path
    url = urllib.parse.quote(url, safe="/?&=%.-_:~+")
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cache = D / "raw" / ("pdf" if binary else "web") / key
    if not cache.exists() or fresh:
        time.sleep(max(0, 1.0 - (time.time() - _last[0])))
        try:  # a 403 / bot check raises here and stops the run: do not work around it
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
        finally:
            _last[0] = time.time()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return cache if binary else cache.read_text("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def pdf_text(path):
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(text.strip()) > 200:
        return text.replace("\f", "\n")  # a page break would hide the 'Točka N.' at the top of a page
    # scanned minutes (1st session, Konica copier): OCR once, cache the text
    out = D / "raw" / "ocr" / (Path(path).name + ".txt")
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            pages = [subprocess.run(["tesseract", str(p), "stdout", "-l", "hrv", "--psm", "4"],
                                    capture_output=True, text=True).stdout for p in sorted(Path(tmp).glob("p-*.png"))]
        out.write_text("\n".join(pages))
    return out.read_text()


# ---------------------------------------------------------------- pages

def session_list(fresh):
    idx = get(INDEX, fresh=fresh)
    urls = dict.fromkeys(re.findall(r'href="(https://www\.sibenik\.hr/sjednice/(\d+)-[^"]*2025-2029/\d+\.html)"', idx))
    return sorted(((int(n), u) for u, n in urls), key=lambda x: x[0])


def doc_links(page):
    """Numbered document list of a sibenik.hr page: [(numerator, name, url)]."""
    out = []
    for href, num, name in re.findall(
            r'<a\s+data-toggle="modal"[^>]*?href="([^"]+)"[^>]*>\s*<span class="[^"]*numerator[^"]*"\s*>(.*?)</span>'
            r'\s*<div class="numeratorContent2?[^"]*"\s*>(.*?)<br', page, re.S):
        if "officeapps.live.com" in href:  # Word preview wrapper -> the file itself
            href = urllib.parse.unquote_plus(re.search(r"src=([^&]+)", href).group(1))
        out.append((clean(num), re.sub(r"\.(pdf|docx?)$", "", clean(name), flags=re.I), href))
    return out


def session_page(page):
    title = clean(re.search(r"<title>(.*?)</title>", page, re.S).group(1)).split(" - Službene")[0]
    d = re.search(r"Datum održavanja sjednice:\s*(?:&nbsp;|\s)*(\d{1,2})\.(\d{1,2})\.(\d{4})", page)
    najava = re.search(r'href="(https://www\.sibenik\.hr/najavesjednica/[^"]+)"', page)
    docs = doc_links(page)
    minutes = next((u for _, n, u in docs if re.search(r"zapisnik", n, re.I)), None)
    return {"title": title, "date": f"{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}" if d else None,
            "najava": najava.group(1) if najava else None,
            "youtube": list(dict.fromkeys(re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", page))),
            "acts": [(n, u) for _, n, u in docs if not re.search(r"zapisnik", n, re.I)], "minutes": minutes}


def najava_docs(page):
    """Materials of the announcement: [{key: '4.a' | '12' | 'D1', name, url, attachments}].
    Supplements 'DOPUNA k.' keep key Dk; 'prilog' entries go under the document they belong to."""
    out, by_key = [], {}
    for num, name, url in doc_links(page):
        m = re.match(r"(DOPUNA\s*\d+|\d+)\s*\.?\s*(?:([a-z])\s*\.)?\s*(prilog\s*\d*\.?)?", num, re.I)
        if not m:
            continue
        base = m.group(1).upper().replace("DOPUNA", "D").replace(" ", "")
        key = base + (f".{m.group(2)}" if m.group(2) else "")
        prilog = bool(m.group(3)) or re.match(r"(prilog|obrazac)", name, re.I) or key in by_key
        if prilog and key in by_key:
            by_key[key]["attachments"].append({"name": name, "url": url})
        elif not prilog:
            by_key[key] = {"key": key, "name": name, "url": url, "attachments": []}
            out.append(by_key[key])
    return out


def agenda_from_najava(docs):
    regular = [int(d["key"].split(".")[0]) for d in docs if d["key"][0].isdigit()]
    last = max(regular, default=0)
    items = []
    for d in docs:
        k = d["key"]
        no = int(k.split(".")[0]) if k[0].isdigit() else last + int(k[1:].split(".")[0])
        title = re.sub(r"^\d+\s*", "", d["name"]).strip()
        items.append({"no": no, "sub_label": k.split(".")[1] if "." in k else None, "title": title,
                      "attachments": [{"name": d["name"], "url": d["url"]}] + d["attachments"]})
    # announcements list sub-items before their parent ("4. a." … "4."): parent first, then a, b, …
    items.sort(key=lambda it: (it["no"], it["sub_label"] or ""))
    return finish_items(items)


def finish_items(items):
    parents = {it["no"]: it for it in items if not it["sub_label"]}
    for it in items:
        p = parents.get(it["no"])
        if it["sub_label"] and p:
            it["full_title"] = f"{p['title']}: {it['sub_label']}) {it['title']}"
        elif not it["sub_label"]:
            kids = [k for k in items if k["no"] == it["no"] and k["sub_label"]]
            it["full_title"] = it["title"] + "".join(f" ({k['sub_label']}) {k['title']}" for k in kids)
        else:
            it["full_title"] = it["title"]
    return items


# ---------------------------------------------------------------- minutes: agenda, headings, votes

def agenda_block(text):
    """(start, end) of the adopted agenda list in the minutes."""
    first = None
    for m in re.finditer(r"DNEVNI RED\s*\n|dnevni red i\s+to:\s*\n", text):
        first = m  # the last one before the first 'Točka 1.' is the adopted agenda
        t1 = re.search(r"^[ \t]*To[čc]ka\s+1\s*\.|^RASPRAVA I ODLUČIVANJE", text[m.end():], re.M)
        if t1 and not re.search(r"DNEVNI RED\s*\n", text[m.end():m.end() + t1.start()]):
            return m.end(), m.end() + t1.start()
    return (first.end(), len(text)) if first else (0, 0)


def agenda_from_minutes(text):
    s, e = agenda_block(text)
    entries, last_no, cur = [], 0, None
    for line in text[s:e].splitlines():
        if not line.strip() or re.fullmatch(r"\s*\d+\s*", line):  # blank or page number
            continue
        m = re.match(r"\s*(\d{1,2})\s*\.\s*([a-z])\s*[.)]\s*(.*)", line)
        m2 = re.match(r"\s*(\d{1,2})\s*\.\s+(\S.*)", line)
        m3 = re.match(r"\s*([a-z])\s*[.)]\s+(\S.*)", line)
        if m and int(m.group(1)) in (last_no, last_no + 1):
            last_no = int(m.group(1))
            cur = {"no": last_no, "sub_label": m.group(2), "title": m.group(3).strip()}
            entries.append(cur)
        elif m2 and int(m2.group(1)) == last_no + 1:
            last_no = int(m2.group(1))
            cur = {"no": last_no, "sub_label": None, "title": m2.group(2).strip()}
            entries.append(cur)
        elif m3 and cur is not None:
            cur = {"no": last_no, "sub_label": m3.group(1), "title": m3.group(2).strip()}
            entries.append(cur)
        elif re.match(r"\s*[-•<]", line):  # 1st session: unnumbered procedural steps
            cur = None
        elif cur is not None:
            cur["title"] += " " + line.strip()
    items = []
    for en in entries:
        en["title"] = flat(en["title"]).rstrip(",;")
        if not en["sub_label"] and en["title"].endswith(":"):  # "20. Prijedlozi rješenja …:" / "23. … o prihvaćanju:"
            for k in entries:
                if k["no"] == en["no"] and k["sub_label"] and not k["title"].startswith(("Prijedlog", "Izvješć")):
                    k["title"] = en["title"].rstrip(": ") + " " + k["title"]
            continue
        items.append({**en, "attachments": []})
    return items


def stem_set(t):
    return {w[:5] for w in re.findall(r"\w+", t.lower()) if len(w) > 3}


# words in most agenda titles (stem_set form), useless for telling items apart
TITLE_STOP = stem_set("prijedlog odluke zaključka izmjenama dopunama izmjeni dopuni grada gradskog vijeća "
                      "šibenika području godinu prihvaćanju")


def title_score(item, text):
    """Share of the item title's words found in the same length of text."""
    t = stem_set(item["title"]) - TITLE_STOP
    h = stem_set(text[:max(len(item["title"]) + 10, 80)])
    return len(t & h) / (len(t) or 1)


def heading_item(items, n, sub, heading, explicit):
    """The agenda item a 'Točka N.' / '5.b.' / 'b.' heading belongs to. Matched on the title that
    follows the heading (councils take items out of order and the minutes have typos such as '4.c)'
    under item 3); for an explicit 'Točka N.' heading the number is the fallback."""
    def score(it):  # ties go to the same sub-label, then the nearest number
        return title_score(it, heading), it["sub_label"] == sub, -abs(it["no"] - (n or 0))
    best = max(items, key=score, default=None)
    numbered = explicit and n is not None and best is not None and best["no"] == n
    # a 'Točka N.' whose title fits item N well enough stays there; a different item needs a clear match
    if best is not None and score(best)[0] >= (0.5 if numbered else 0.75 if explicit else 0.6):
        return best
    if explicit and n is not None:
        same = [it for it in items if it["no"] == n and it["sub_label"] == sub] or \
               [it for it in items if it["no"] == n]
        return same[0] if same else None
    return None


HEAD = re.compile(r"^[ \t]*(?:(?P<t>To[čc]ka|TOČKA)\s+(?P<n1>\S{1,3}?)\s*\.\s*(?:(?P<s1>[a-z])\s*[.)])?"
                  rf"|(?P<n2>\d{{1,2}})\s*\.\s*(?:(?P<s2>[a-z])\s*[.)])?|(?P<s3>[a-z])\s*[.)])\s*(?=[{UP}„\"])", re.M)


def headings(text, items):
    """[(pos, item)] for the section headings after the agenda; unknown 'Točka N.' (e.g. the 1st
    session's supplementary point, OCRed as 'Točka S.') become new items."""
    _, start = agenda_block(text)
    out = []
    for m in HEAD.finditer(text, start):
        explicit = bool(m.group("t"))
        num = m.group("n1") or m.group("n2")
        n = int(num) if num and num.isdigit() else None
        sub = m.group("s1") or m.group("s2") or m.group("s3")
        head = flat(text[m.end():m.end() + 400])
        it = heading_item(items, n, sub, head, explicit)
        if it is None and explicit:
            title = flat(re.split(r"\n\s*\n", text[m.end():m.end() + 400])[0]).rstrip(".")
            it = {"no": n or (max(i["no"] for i in items) + 1 if items else 1), "sub_label": sub,
                  "title": title, "attachments": [], "added_from_minutes": True}
            items.append(it)
        if it is not None:
            out.append((m.start(), it))
    return out


NUMW = {"nula": 0, "jedan": 1, "jednim": 1, "jedna": 1, "jednog": 1, "dva": 2, "dvije": 2, "dvama": 2,
        "tri": 3, "četiri": 4, "pet": 5}
NUM = r"(\d+|" + "|".join(NUMW) + r")"
QUOTES = str.maketrans({c: '"' for c in "„“”«»‟″"})
OUTCOME = re.compile(r"nije\s+(?:prihvać\w*|donesen\w*|usvojen\w*|prošao|prošla|izabran\w*)|donesen\w*|donijel\w*|"
                     r"prihvaćen\w*|prihvatil\w*|usvojen\w*|izabran\w*|izabral\w*|produžen\w*|dopunjen\w*|prošao")
# (1) „ZA“ je glasovalo 12 vijećnika, 4 je bilo „SUZDRŽANIH“, 0 je bio „PROTIV“, pa … konstatira da je … donesen
#     (also "ZA“ je 17 glasovalo vijećnika", "glasovalo 11vijećnika", opening quote often lost)
# (2) Uz 16 glasova „ZA“ 4 glasa „SUZDRŽANA“ prihvaćen je prijedlog … / Vijeće je uz 21 glas „ZA“ donijelo …
#     / Vijeće je jednoglasno, sa 21 glas „ZA“ izabralo … / uz 20 glasova „ZA“ i 1 glas „UZDRŽAN“ … izabran
VOTE = re.compile(r'"*\s*ZA"*\s+je\s+(?:(?P<a>\d+)\s+)?glasovalo\s*(?P<b>\d+)?\s*vijećnika'
                  rf'|(?:[Uu]z|sa)\s+{NUM}\s+glas\w*\s*,?\s*"*\s*ZA\b')
PROTIV = re.compile(rf'{NUM}\s+(?:je\s+bi(?:lo|o)\s+|glas\w*\s+)?"*\s*PROTIV')
SUZD = re.compile(rf'{NUM}\s+(?:je\s+bi(?:lo|o)\s+|glas\w*\s+)?"*\s*S?UZDRŽAN')


def num(w):
    return int(w) if w.isdigit() else NUMW[w]


def minutes_votes(text):
    """Every vote sentence after the agenda: totals, result, its act text and position. Votes on
    amendments, the agenda, the previous minutes and extending the question hour are left out."""
    q = text.replace(",,", '""').translate(QUOTES)  # same length as text: positions stay valid
    _, start = agenda_block(text)
    votes = []
    for m in VOTE.finditer(q, start):
        o = OUTCOME.search(q, m.end(), m.end() + 500)
        if not o:
            continue
        window = q[m.start():o.end()]
        around = flat(q[max(0, m.start() - 200):o.end() + 20])
        # "Uz 9 glasova „ZA“ amandman nije prošao" is a vote on an amendment, not on the item (the item's
        # own vote may follow "… sa usvojenim amandmanima", so only the vote sentence itself is checked)
        if re.search(r"amandman|dnevni red|zapisnik|aktualni sat", flat(q[m.start():o.end() + 50]), re.I):
            continue
        za = m.group("a") or m.group("b") or m.group(3)
        if za is None:
            continue
        p, s = PROTIV.search(window), SUZD.search(window)
        # the act voted on: "… konstatira da je <act> donesen…", else "daje na glasovanje <act>" just before
        k = re.search(r"konstatira\s+da\s+(?:je\s+|su\s+)?(.*)", window, re.S)
        before = q[max(0, m.start() - 400):m.start()]
        g = before.rfind("na glasovanje")
        acts = [flat(before[g + 13:]) if g >= 0 else "", flat(k.group(1)) if k else ""]
        votes.append({"pos": m.start(), "za": num(za), "protiv": num(p.group(1)) if p else 0,
                      "suzdrzano": num(s.group(1)) if s else 0, "only_za": not (p or s),
                      "unanimous": "jednoglasno" in around,
                      "result": NO if o.group(0).startswith("nije") else YES,
                      "kind": "konstatira" if m.group("a") or m.group("b") or "konstatira" in window else "uz",
                      "acts": [a for a in acts if a], "quote": flat(text[m.start():o.end() + 40])})
    return votes


def section_status(text, items, heads):
    """Items without a vote: 'primljeno na znanje' (reports: "… se prima na znanje") or withdrawn
    ("povlači se s dnevnog reda", "Gradonačelnik je odustao od prijedloga pod točkom: 14.")."""
    for i, (pos, it) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        tail = flat(text[pos:end])[-700:]
        if re.search(r"prima\w*\s+(?:se\s+)?na\s+znanje", tail):
            it.setdefault("section_status", "primljeno na znanje")
        if re.search(r"povlači\s+se\s+s\s+dnevnog\s+reda|povučen\w*\s+s\s+dnevnog", tail):
            it["section_status"] = "povučeno s dnevnog reda"
    s, _ = agenda_block(text)
    seen = {id(it) for _, it in heads}
    for m in re.finditer(r"odusta\w*\s+od\s+prijedloga\s+pod\s+točkom\s*:?\s*(\d+)", flat(text[:s])):
        for it in items:
            if it["no"] == int(m.group(1)) and id(it) not in seen:
                it["section_status"] = "povučeno s dnevnog reda"


def attach_votes(items, votes, heads):
    """A vote belongs to the last heading before it, unless neither act text it names ('daje na
    glasovanje Prijedlog …', '… konstatira da je Odluka … donesena') fits that heading's item and one
    clearly fits another (a missed heading). The heading wins otherwise: the minutes sometimes copy
    the wrong act name into the 'konstatira' sentence (4th session, 20.g)."""
    def sc(it, v):
        return max((title_score(it, a) for a in v["acts"]), default=0)
    moved = []
    for v in votes:
        prev = [h for h in heads if h[0] < v["pos"]]
        head = prev[-1][1] if prev else None
        alt = max(items, key=lambda it: (sc(it, v), it is head), default=None)
        best = head
        if alt is not None and alt is not head and sc(alt, v) >= 0.9 and (head is None or sc(head, v) < 0.6):
            best = alt
            moved.append((v["quote"][:80], head and head["title"][:60], alt["title"][:60]))
        if best is not None:
            best.setdefault("votes", []).append(v)
    for it in items:
        vs = it.get("votes") or []
        if not vs:
            continue
        konst = [v for v in vs if v["kind"] == "konstatira"]
        same = len({(v["za"], v["protiv"], v["suzdrzano"], v["result"]) for v in vs}) == 1
        v = konst[-1] if konst else vs[-1]
        it["vote"] = {"za": v["za"], "protiv": v["protiv"], "suzdrzano": v["suzdrzano"], "result": v["result"],
                      "members": {}, "unanimous": v["unanimous"], "quote": v["quote"]}
        notes = []
        if v["only_za"] and not v["unanimous"]:
            notes.append("Zapisnik navodi samo broj glasova ZA; protiv i suzdržani nisu navedeni (upisano 0).")
        if len(vs) > 1 and not konst and not same:
            notes.append(f"O točki se glasovalo {len(vs)} puta (pojedinačno); prikazano je zadnje glasovanje.")
        elif len(vs) > 1 and not konst:
            notes.append(f"O točki se glasovalo {len(vs)} puta (pojedinačno), svaki put s istim rezultatom.")
        if notes:
            it["vote"]["totals_note"] = {"kind": "zapisnik", "text": " ".join(notes), "quote": v["quote"]}
        it["votes"] = [{k: x[k] for k in ("za", "protiv", "suzdrzano", "result", "quote")} for x in vs]
    return moved


TITLES = re.compile(r"\b(?:dr\.?\s*sc\.|mr\.?\s*sc\.|dr\.\s*med\.|prof\.)\s*", re.I)


def person(n):
    return flat(TITLES.sub("", re.sub(r"\b\d+\b", "", n))).strip(" ,.;")


def attendance(text):
    f = flat(text)
    pres = re.search(r"nazoč\w*\s+\d+\s+vijećni\w*\s+i\s+to:\s*(.*?)\s+te\s+(?:da|je)\b", f)
    absent = re.search(r"Sjednici\s+(?:uz\s+ispriku\s+)?(?:nisu\s+nazočni|nije\s+nazoč\w*)\s*:?\s*(.*?)\.\s", f)
    names = lambda s: [person(x) for x in re.split(r",|\s+i\s+", s or "") if person(x)]
    return ([{"name": n, "present": True} for n in names(pres and pres.group(1))] +
            [{"name": n, "present": False} for n in names(absent and absent.group(1))])


# ---------------------------------------------------------------- materials, members

def attach_docs(items, docs, threshold=0.6):
    """Announcement materials / adopted acts -> agenda items, by title."""
    def score(name, title):  # both directions: file names are often shortened, titles too
        a, b = stem_set(name) - TITLE_STOP, stem_set(title) - TITLE_STOP
        return (len(a & b) / (len(a) or 1) + len(a & b) / (len(b) or 1)) / 2
    lost = []
    for d in docs:
        name = re.sub(r"^\d+\s*", "", d["name"])
        best = max(items, key=lambda it: score(name, it["title"]), default=None)
        sc = score(name, best["title"]) if best else 0
        if best is not None and sc >= threshold:
            for a in [{"name": d["name"], "url": d["url"]}] + d.get("attachments", []):
                if a["url"] not in {x["url"] for x in best["attachments"]}:
                    best["attachments"].append(a)
        else:
            lost.append(d["name"])
    return lost


def canon(name, known):
    best = max(known, key=lambda k: SequenceMatcher(None, k, name).ratio(), default=name)
    return best if SequenceMatcher(None, best, name).ratio() > 0.85 else name


def members(fresh, known):
    """Current council (members page: 'Ime Prezime (STRANKA)'), plus anyone on an attendance list who
    has left since (party from the constitutive session's mandate report, status 'bivši član')."""
    page = clean(get(MEMBERS, fresh=fresh))
    body = page[page.find("Predsjednik:"):page.find("PREGLED DOKUMENATA")]
    out = [{"name": person(n), "party": p.strip()} for n, p in re.findall(rf"([{UP}][^()]*?)\s*\(([^)]+)\)", body)]
    out = [{"name": re.sub(r"^(?:Predsjednik|Potpredsjednici|Članovi vijeća):\s*", "", m["name"]), "party": m["party"]}
           for m in out]
    have = {m["name"] for m in out}
    lists = election_lists()
    for n in sorted(set(known) - have):
        party = lists.get(canon(n, list(lists)), "")  # OCR spelling: "TOMAMASINI"
        out.append({"name": n, "party": party, "status": "bivši član ili zamjenik (nije u aktualnom sastavu)"})
    return out


def election_lists():
    """Name -> list abbreviations from the 1st session's mandate report (OCR text)."""
    f = D / "docs" / "session_01.json"
    if not f.exists():
        return {}
    text = json.loads(f.read_text()).get("minutes_text") or ""
    out = {}
    for blk in re.split(r"\n[a-f]\)\s+", text[text.find("izabrani kako slijedi"):text.find("Željko Burić, dr. med. izabran")]):
        abbr = "-".join(re.findall(r"-\s*([A-ZČĆŠŽ!]{2,})\s*$", blk.split("dobila")[0], re.M))
        for name in re.findall(r"\d+\.\s+(?:dr\.sc\.|mr\.sc\.)?\s*([A-ZČĆŠŽĐ][A-ZČĆŠŽĐ ]+?)(?:,|\n)", blk):
            out[person(name.title())] = abbr.replace("!", "")
    return out


# ---------------------------------------------------------------- main

def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    recordings, report = [], []
    for n, url in session_list(fresh):
        sp = session_page(get(url, fresh=fresh))
        docs = najava_docs(get(sp["najava"], fresh=fresh)) if sp["najava"] else []
        doc = {"session": n, "title": sp["title"], "date": sp["date"], "url": url, "minutes_url": sp["minutes"],
               "minutes_text": None, "items": [], "attendance": [], "questions": []}
        moved, lost = [], []
        if sp["minutes"]:
            text = pdf_text(get(sp["minutes"], binary=True))
            doc["minutes_text"] = text
            items = agenda_from_minutes(text)
            heads = headings(text, items)
            items.sort(key=lambda it: (it["no"], it["sub_label"] or ""))
            items = finish_items(items)
            votes = minutes_votes(text)
            moved = attach_votes(items, votes, heads)
            section_status(text, items, heads)
            doc["attendance"] = attendance(text)
            doc["votes_in_minutes"] = len(votes)
            lost = attach_docs(items, docs)
        else:
            items = agenda_from_najava(docs)
        attach_docs(items, [{"name": nm, "url": u} for nm, u in sp["acts"]])  # adopted acts (.docx)
        for it in items:
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if it["vote"]["result"] == YES else "nije prihvaćen") if it.get("vote") \
                else it.get("section_status")
            it["url"] = url
        doc["items"] = [{k: it[k] for k in ("no", "sub_label", "title", "full_title", "proposer", "status", "url",
                                            "attachments", "vote", "votes", "added_from_minutes") if k in it}
                        for it in items]
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        for k, yt in enumerate(sp["youtube"], 1):
            recordings.append({"id": f"sibenik-{n:02d}-{k}", "session": n, "part": k, "date": sp["date"],
                               "title": sp["title"], "url": f"https://www.youtube.com/watch?v={yt}", "kind": "youtube"})
        nv = sum(1 for i in items if i.get("vote"))
        report.append((n, len(items), nv, bool(sp["minutes"])))
        print(f"sibenik session {n} ({sp['date']}): {len(items)} items, {nv} with votes "
              f"({doc.get('votes_in_minutes', 0)} item votes in minutes), {len(doc['attendance'])} attendance, "
              f"minutes {'yes' if sp['minutes'] else 'no'}, recordings {len(sp['youtube'])}", flush=True)
        for q, a, b in moved:
            print(f"   vote moved by act title: {a!r} -> {b!r}  [{q}]", flush=True)
        for it in items:
            if sp["minutes"] and not it.get("vote"):
                print(f"   no vote ({it['status']}): {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)
        for nm in lost:
            print(f"   material not matched to an item: {nm[:100]}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    # one spelling per person: attendance names are snapped to the members page (minutes have typos)
    roster = members(fresh, [])
    names = [m["name"] for m in roster]
    known = set()
    for f in sorted((D / "docs").glob("session_*.json")):
        d = json.loads(f.read_text())
        for a in d["attendance"]:
            a["name"] = canon(a["name"], names)
            known.add(a["name"])
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    roster = members(False, sorted(known))
    (D / "members.json").write_text(json.dumps(roster, ensure_ascii=False, indent=1))
    print(f"members: {len(roster)} ({sum(1 for m in roster if not m.get('status'))} current), "
          f"recordings: {len(recordings)}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
