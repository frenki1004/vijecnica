"""Collect Grad Krk City Council (Gradsko vijeće Grada Krka) sessions, 2025-2029 term.

grad-krk.hr (Drupal). Per session there are up to three kinds of pages:
  - the convocation with the proposed agenda and item materials ("sazivi-YYYY/N-sjednica-…", session 7 sits
    under "sjednice-2026/7-sjednica-gradskog-vijeca-grada-krka"),
  - news reports of the outcome (vote counts in prose, removed agenda items),
  - "aktualni sat" reports (councillor questions + mayor's answers in prose).
Minutes (zapisnici) are scanned PDFs without a text layer: pdftotext gives nothing, so they are OCR'd with
tesseract (hrv) and cached in data/krk/raw/ocr. Minutes carry the adopted agenda, attendance by name,
the question hour (question + answer per councillor) and one vote sentence per item ("Ad N.").
Session 1 = the constitutive session (the minutes call it "(1.) konstituirajuća sjednica").
HTML cache data/krk/raw/web, PDFs data/krk/raw/pdf, MP3s data/krk/audio.
Output: data/krk/docs/session_NN.json, data/krk/recordings.json, data/krk/members.json.

Usage: python collect/krk.py [--audio]
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
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "krk"
HOST = "https://www.grad-krk.hr"
GV = "/gradska-uprava/gradsko-vijece"
UA = "vijecnica-research/0.1 (open data hackathon)"
TERM_START = "2025-06-01"
MAYOR = {"name": "Darijo Vasilić", "party": "PGS", "list": "Koalicija PGS-SDP"}
_last = [0.0]


def get(path, binary=False, fresh=False):
    url = path if path.startswith("http") else HOST + urllib.parse.quote(path, safe="/?&=%.-_:")
    url = url.replace("://grad-krk.hr", "://www.grad-krk.hr")
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
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).replace("\xa0", " ").strip()


def body(page):
    """Article body (field-name-body) up to the sidebar."""
    i = page.find("field-name-body")
    if i < 0:
        return ""
    j = page.find("(Su)Djelujem", i)
    return page[i:j if j > 0 else len(page)]


def lines(b):
    """Body HTML -> [(text, [(link text, href)])] per paragraph/line."""
    out = []
    for chunk in re.split(r"<(?:p|br|li|h\d|tr|div)\b[^>]*>", b):
        links = [(clean(t), h) for h, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S)]
        t = clean(chunk)
        if t or links:
            out.append((t, links))
    return out


def pdf_text(path):
    """pdftotext; Krk minutes are scans (no text layer) -> OCR with tesseract (hrv), cached in raw/ocr."""
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) > 200:
        return t
    cache = D / "raw" / "ocr" / (Path(path).name + ".txt")
    if cache.exists():
        return cache.read_text()
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    pages = []
    with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
        for png in sorted(Path(tmp).glob("p-*.png")):
            pages.append(subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"],
                                        capture_output=True, text=True, env=env).stdout)
            png.unlink()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\f".join(pages))
    return cache.read_text()


MONTHS = {"siječnja": 1, "veljače": 2, "ožujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6, "srpnja": 7,
          "kolovoza": 8, "rujna": 9, "listopada": 10, "studenoga": 11, "studenog": 11, "prosinca": 12}


def find_date(text, year=None):
    m = re.search(r"(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")\s*(\d{4})?", text)
    if not m:
        return None
    y = m.group(3) or year
    return f"{y}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if y else None


ORD = [("konstituir", 1), ("prv", 1), ("drug", 2), ("treć", 3), ("četvrt", 4), ("pet", 5), ("šest", 6),
       ("sedm", 7), ("osm", 8), ("devet", 9), ("deset", 10)]


def session_no(title):
    t = title.lower()
    m = re.search(r"(\d+)\.\s*(?:\(?konstituir\w*\)?\s*)?sjednic", t)
    if m:
        return int(m.group(1))
    for stem, n in ORD:
        if re.search(r"\b" + stem + r"\w*\s+(?:sjednic|gradsko vijeće)", t) or (stem == "konstituir" and stem in t):
            return n
    return None


# ---------------------------------------------------------------- numbers in words (news prose)
WORDNUM = {"jedan": 1, "jednim": 1, "jednom": 1, "jedna": 1, "jednog": 1, "dva": 2, "dvama": 2, "dvoje": 2,
           "tri": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10,
           "jedanaest": 11, "dvanaest": 12, "trinaest": 13}
NUM = r"(\d+|" + "|".join(sorted(WORDNUM, key=len, reverse=True)) + r")"


def num(s):
    return int(s) if s.isdigit() else WORDNUM.get(s.lower())


def stems(t):
    """5-letter word stems without the generic agenda words (prijedlog, odluka, izmjena, dopuna, grad, …)."""
    stop = ("prijedl", "odluk", "grada", "krka", "godin", "izmjen", "dopun", "gradsk", "vijeć", "sjednic", "područj")
    return {w[:5] for w in re.findall(r"\w+", t.lower()) if len(w) > 3 and not w.startswith(stop) and not w.isdigit()}


# ---------------------------------------------------------------- agenda (convocation page)
def agenda(page):
    """Numbered lines after 'Dnevni red' = items; 'a)' / '6.1.' lines = sub-items; 'Predlagatelj:' /
    'Podnositelj izvješća:' = proposer; links on 'Materijale preuzmite' lines = attachments."""
    ls = lines(body(page))
    start = next((k for k, (t, _) in enumerate(ls) if re.search(r"dnevni\s+red", t, re.I)), None)
    if start is None:
        return []
    items = []
    for t, links in ls[start + 1:]:
        m = re.match(r"^(\d{1,2})\s*\.\s+(?!\d)(.+)", t)
        sub = re.match(r"^(?:[a-m]\)|\d{1,2}\.\d\.?)\s*(.+)", t)
        prop = re.match(r"^(?:Predlagatelj\w*|Podnositelj\w*(?: izvješća| Izvješća)?)\s*:\s*(.+)", t)
        if m:
            items.append({"no": int(m.group(1)), "title": m.group(2).strip(" .:;"), "subs": [],
                          "proposer": "", "attachments": []})
        elif not items:
            continue
        elif sub:
            items[-1]["subs"].append(re.sub(r"\s*\(?\s*OVDJE\s*\)?\.?$", "", sub.group(1)).strip(" .;:"))
        elif prop:
            items[-1]["proposer"] = prop.group(1).strip(" .")
        elif t.startswith("Klub članova"):
            items[-1]["proposer"] = t.strip(" .")
        for name, href in links:
            if items and re.search(r"\.(pdf|docx?|xlsx?|zip|odt)$", href, re.I):
                fn = urllib.parse.unquote(href.rsplit("/", 1)[-1])
                label = name if len(name) > 3 and name.lower().strip(" .:") not in ("ovdje",) else fn
                items[-1]["attachments"].append({"name": label, "url": urllib.parse.urljoin(HOST, href)})
    for it in items:
        it["title"] = re.sub(r"\s*\(?\s*OVDJE\s*\)?\s*(i to)?:?$", r" \1", it["title"]).strip(" .:")
        subs = it.pop("subs")
        it["full_title"] = it["title"] + "".join(f" ({chr(97 + k)}) {s}" for k, s in enumerate(subs))
        it["n_subs"] = len(subs)
    return items


# ---------------------------------------------------------------- minutes (OCR)
Q = r"[\"'«»„“”,‚`]{0,3}\s*"


def vote_counts(s):
    """'sa 10 (deset) glasova «za», 1 (jedan) «protiv» i 1 (jedan) «suzdržan»'. The number word in
    parentheses wins over the OCR'd digits ("i 2 (dva)" is read as "12 (dva)")."""
    v = {"za": 0, "protiv": 0, "suzdrzano": 0}
    for d, w1, w2, kind in re.findall(r"(?:(\d+)\s*(?:\(\s*([a-zčćšžđ]+)\s*\)?)?|\(\s*([a-zčćšžđ]+)\s*\))\s*"
                                      r"(?:glas\w*\s*)?" + Q + r"(za|protiv|suzdrž\w*)", s):
        w = (w1 or w2).lower()
        n = WORDNUM.get(w, int(d) if d else None)
        if n is not None:
            v["suzdrzano" if kind.startswith("suzd") else kind] = n
    for d, kind in re.findall(r"(\d+)\s*članova vijeća glasovalo je\s*" + Q + r"(za|protiv|suzdrž\w*)", s):
        v["suzdrzano" if kind.startswith("suzd") else kind] = int(d)
    return v


def minutes_parse(text, roster):
    flat = re.sub(r"[ \t]+", " ", text.replace("\f", "\n"))
    one = re.sub(r"\s+", " ", flat)
    # attendance
    att = []
    m = re.search(r"(?:Nazočni|NAZOČNI ČLANOVI GRADSKOG VIJEĆA|Prisutni)\s*:\s*(.*?)(?=Odsut\w* član|Nenazočn|Sjednici također)", one)
    if m:
        att += [{"name": n, "present": True, "note": note} for n, note in people(m.group(1))]
    m = re.search(r"(?:Odsut\w*|Nenazočn\w*)(?: član\w*)?(?: vijeća)?\s*:\s*(.*?)(?=Sjednici također|Na temelju|$)", one)
    if m:
        att += [{"name": n, "present": False, "note": note} for n, note in people(m.group(1))]
    for a in att:
        a["name"], a["party"] = match_member(a["name"], roster)
        if not a["note"]:
            a.pop("note")
    # adopted agenda: numbered lines after the last "DNEVNI RED:" before "AKTUALNI SAT"/"Ad1"
    first_ad = re.search(r"(?m)^\s*Ad\s*[l1I\d]", flat)
    end = first_ad.start() if first_ad else len(flat)
    akt = re.search(r"AKTUALNI SAT", flat[:end])
    head = flat[:akt.start() if akt else end]
    dr = [x.end() for x in re.finditer(r"DNEVNI RED\s*:?", head)]
    adopted = []
    if dr:
        for mm in re.finditer(r"(?ms)^\s*(\d{1,2})\s*\.\s*(.+?)(?=^\s*\d{1,2}\s*\.\s|\Z)", head[dr[-1]:]):
            adopted.append((int(mm.group(1)), re.sub(r"\s+", " ", mm.group(2)).strip(" .")))
    # removed items ("točke 12 i 13 … izostave s dnevnog reda")
    removed = []
    for mm in re.finditer(r"točk\w*\s+([\d\s,i]+?)\.?\s+(?:predloženog\s+)?Dnevnog reda.{0,160}?izostav\w*(.{0,250})", one, re.I):
        if re.search(r"nije\s+prihvaćen", mm.group(2)[:200]):
            continue
        removed += [int(x) for x in re.findall(r"\d+", mm.group(1))]
    # question hour
    questions = minutes_questions(flat[akt.start():end] if akt else "", roster)
    # per-item sections "Ad N."
    sections = {}
    heads = [(mm.start(), mm.end(), mm.group(1)) for mm in re.finditer(r"(?m)^\s*Ad\s*([lIiSs\d]{1,3})\s*\.?\s*$", flat)]
    for k, (s, e, n) in enumerate(heads):
        n = re.sub(r"^[Ss](?=\d)", "", n)  # OCR: "Ads5." = Ad 5
        n = int(n.translate(str.maketrans("lIiSs", "11155")))
        sections.setdefault(n, flat[e:heads[k + 1][0] if k + 1 < len(heads) else len(flat)])
    return att, adopted, removed, questions, sections, one


def section_votes(sec):
    """Vote sentences in an Ad section, in order:
    'Gradsko vijeće … sa N glasova «za» … donijelo je / izvršilo izbor' (decision; 'odbilo' after it = rejected),
    '… nije dobio propisanu većinu glasova (… 7 članova vijeća glasovalo je «protiv», 2 «za» …)' (rejected),
    '… jednoglasno izabrana, sa 13 glasova «za»' (elections, verb before the count)."""
    s = re.sub(r"\s+", " ", sec).replace("_", "")
    s = re.sub(r"\bi(\d)", r"i \1", s)
    found = []
    for m in re.finditer(r"(?:Gradsko vijeće|utvrđuje da je)(?:(?!Gradsko vijeće).){0,300}?(jednoglasno)?.{0,40}?\b(?:sa|s)\s+(\d+)\s*"
                         r"(?:\(\s*\w+\s*\)?\s*)?glas\w*(.{0,160}?)\b(nije\s+)?(donijel\w*|donosi|usvoj\w*|prihvat\w*|"
                         r"izvršil\w*|izabral\w*|imenoval\w*|odbil\w*|primil\w*)", s):
        v = vote_counts(m.group(0))
        after = s[m.end():m.end() + 400]
        rejected = m.group(4) or m.group(5).startswith("odbil") or re.search(r"\bodbil[oa]\b|ne prihvaća se", after)
        v["result"] = "Prijedlog nije usvojen" if rejected else "Prijedlog usvojen"
        v["unanimous"] = bool(m.group(1))
        found.append((m.start(), m.end(), v))
    for m in re.finditer(r"(nije\s+)?dobi\w*\s+propisanu\s+većinu\s+glasova[\s\w]*\(?(.{0,260}?)(?:\)\s*\.|$)", s):
        if any(a <= m.start() < b for a, b, _ in found):
            continue
        v = vote_counts(m.group(2))
        v["result"] = "Prijedlog nije usvojen" if m.group(1) else "Prijedlog usvojen"
        v["unanimous"] = False
        found.append((m.start(), m.end(), v))
    for m in re.finditer(r"(jednoglasno,?\s+)?(?:izabran|izrabran|prihvaćen|usvojen|izglasan)\w*,?\s*(jednoglasno,?\s*)?"
                         r"(?:sa|s)\s+\d+\s*(?:\(\s*\w+\s*\)\s*)?glas\w*.{0,80}", s):
        if any(a <= m.start() < b or m.start() <= a < m.end() for a, b, _ in found):
            continue
        v = vote_counts(m.group(0))
        v["result"] = "Prijedlog usvojen"
        v["unanimous"] = bool(m.group(1) or m.group(2))
        found.append((m.start(), m.end(), v))
    return [v for _, _, v in sorted(found, key=lambda x: x[0])]


def debate(sec):
    s = re.sub(r"\s+", " ", sec)
    m = re.search(r"U raspravi (?:su|je) sudjelova\w* (?:vijećni\w*)?\s*:?\s*(.*?)\.", s)
    return split_names(m.group(1)) if m else []


def people(s):
    """'A, B (note), C i D.' -> [(name, note)]; notes in parentheses stay with the name before them."""
    out = []
    for m in re.finditer(r"([^,()]+?)\s*(?:\((.*?)\))?\s*(?:,+|\bi\b|\.\s*$|$)", s.strip()):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
        if re.fullmatch(r"[A-ZČĆŠŽĐ][\w-]+(?:\s+[A-ZČĆŠŽĐ][\w-]+){1,2}", name):
            note = re.sub(r"\s+", " ", m.group(2) or "").strip() or None
            out.append((name, note))
        elif out and m.group(2) and not name:
            out[-1] = (out[-1][0], m.group(2).strip())
    return out


def split_names(s):
    s = re.sub(r"\s+", " ", s or "")
    return [n.strip(" .,;") for n in re.split(r",|\bi\b", s) if re.search(r"[A-ZČĆŠŽĐ]\w+\s+[A-ZČĆŠŽĐ]", n.strip())]


def norm(n):
    return re.sub(r"[\s-]+", " ", n.lower()).replace("danijel", "daniel").strip()


def match_member(name, roster):
    if name and roster:
        rev = " ".join(name.split()[::-1])
        if any(norm(r["name"]) == norm(rev) for r in roster):
            name = rev
    best = max(roster, key=lambda r: SequenceMatcher(None, norm(r["name"]), norm(name)).ratio())
    if SequenceMatcher(None, norm(best["name"]), norm(name)).ratio() > 0.8:
        return best["name"], best["party"]
    return name.title() if name.isupper() else name, None


def minutes_questions(block, roster):
    """'> Član(ica) vijeća NAME:' question block, then '> Gradonačelnik NAME odgovorio je sljedeće:' answer
    block; numbered sub-questions are paired with numbered answers."""
    out = []
    pat = re.compile(r"(?m)^\W{0,3}\s*(Član\w* vijeća|Gradonačelni\w*|Zamjeni\w* gradonačelni\w*|Pročelni\w*)"
                     r"\s+([A-ZČĆŠŽĐ][\w-]+(?:\s+[A-ZČĆŠŽĐ][\w-]+){1,2})?[^\n:]{0,60}:\s*$")
    marks = list(pat.finditer(block))
    for k, m in enumerate(marks):
        if not m.group(1).startswith("Član"):
            continue
        q = block[m.end():marks[k + 1].start() if k + 1 < len(marks) else len(block)]
        ans, by = "", None
        if k + 1 < len(marks) and not marks[k + 1].group(1).startswith("Član"):
            nxt = marks[k + 1]
            ans = block[nxt.end():marks[k + 2].start() if k + 2 < len(marks) else len(block)]
            by = nxt.group(2) or (MAYOR["name"] if nxt.group(1).startswith("Gradonač") else nxt.group(1))
            if nxt.group(1).startswith("Gradonač") and not nxt.group(2):
                by = MAYOR["name"]
        name, party = match_member(m.group(2) or "", roster)
        qs, ans_parts = numbered(q), numbered(ans)
        if len(qs) > 1 and len(qs) == len(ans_parts):
            pairs = list(zip(qs, ans_parts))
        else:
            pairs = [(squash(q), squash(ans))]
        for qq, aa in pairs:
            out.append({"name": name, "party": party, "question": qq, "to": "Gradonačelnik" if by else None,
                        "answer": aa or None, "answered_by": by, "fonogram": None, "url": None})
    return out


def numbered(t):
    parts = re.split(r"(?m)^\s*\d\s*\.\s*(?=\S)", t)
    parts = [squash(p) for p in parts if squash(p)]
    return parts


def squash(t):
    t = re.sub(r"(?m)^\s*\d{1,2}\s*$", "", t)  # page numbers
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- news prose
def news_votes(text, items):
    """Sentences with a vote count tied to one agenda item: an explicit 'N.' / 'točka N' or the best title
    match (≥ 3 shared word stems and clearly better than the runner-up)."""
    found = {}
    text = re.sub(r"\bi(?=(?:jedn\w+|dva|tri|dvije)\b)", "i ", text)
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-ZČĆŠŽĐ0-9\"„])", text):
        low = sent.lower()
        has_count = re.search(NUM + r"\s+(?:glas\w*\s+)?[\"„“]?(za|protiv|suzdrž\w*)", low)
        unan = "jednoglasno" in low or "konsenzual" in low
        majority = "većinom glasova" in low and not re.search(r"amandman|prigovor", low)
        if not (has_count or unan or majority):
            continue
        if "amandman" in low.split("prihvać")[0] if "prihvać" in low else "amandman" in low[:60]:
            continue
        v = {"za": None, "protiv": None, "suzdrzano": None}
        for n, kind in re.findall(NUM + r"\s+(?:glas\w*\s+)?[\"„“]?(za|protiv|suzdrž\w*)", low):
            v["suzdrzano" if kind.startswith("suzd") else kind] = num(n)
        for n, kind in re.findall(NUM + r"\s+(protiv|suzdrž\w*)", low):
            v["suzdrzano" if kind.startswith("suzd") else kind] = num(n)
        if re.search(r"\bs\s+" + NUM + r"\s+glas\w*\s+vijećnika", low) and v["za"] is None:
            v["za"] = num(re.search(r"\bs\s+" + NUM + r"\s+glas", low).group(1))
        if unan:
            v = {"za": None, "protiv": 0, "suzdrzano": 0, **{k: x for k, x in v.items() if x is not None}}
        elif v["za"] is not None:
            v = {k: (0 if x is None and (v["protiv"] is not None or v["suzdrzano"] is not None) else x) for k, x in v.items()}
        v["result"] = "Prijedlog nije usvojen" if re.search(r"odbijen|nije (prihvać|usvoj|izglas)", low) else "Prijedlog usvojen"
        v["unanimous"] = unan
        target = None
        m = re.match(r"^\s*(\d{1,2})\.\s", sent) or re.search(r"točk\w* (" + NUM[1:-1] + r"|\d+)\.? dnevnog reda", low)
        if m:
            target = num(m.group(1))
        else:
            scored = sorted(((overlap(sent, it["title"]), len(stems(sent) & stems(it["title"])), it["no"])
                             for it in items), reverse=True)
            if scored and scored[0][0] >= 0.6 and scored[0][1] >= 2 and (len(scored) == 1 or scored[0][0] >= scored[1][0] + 0.15):
                target = scored[0][2]
        if not (has_count or unan):  # "većinom glasova": outcome only, no numbers
            v = {"za": None, "protiv": None, "suzdrzano": None, "result": v["result"], "unanimous": False,
                 "majority_only": True}
        if target is not None and target not in found:
            found[target] = {**v, "sentence": sent.strip()}
    return found


def news_removed(text, items):
    """'… uklonjene/skinute su (dvije) točke: A te B' -> agenda numbers by title match."""
    out = []
    m = re.search(r"(?:uklonjen\w*|skinut\w*|izostav\w*)[^:]{0,80}točk\w*\s*:\s*(.{0,500})", text)
    if not m:
        return out
    for part in re.split(r"\s+te\s+|;\s*", m.group(1))[:4]:
        part = re.split(r"\.\s+(?=[A-ZČĆŠŽĐ])", part)[0][:200]
        scored = sorted(((overlap(part, it["title"]), it["no"]) for it in items), reverse=True)
        if scored and scored[0][0] >= 0.6:
            out.append(scored[0][1])
    return out


def news_questions(page, roster):
    """aktualni-sat pages: a paragraph naming a councillor + a question verb opens a question; the following
    paragraphs (until the next question) are the answer."""
    paras = [t for t, _ in lines(body(page)) if t]
    paras = [p for p in paras if not re.match(r"^(Dnevni red|Izvješće s|Tekst|Tonski zapis|Aktualni sat)", p)]
    qverbs = r"zanima|upita|pita\w*|otvori|skrenu|aktualizira|predlož|postavi|interesira|upozori|tražio|tražila"
    out = []
    for p in paras:
        who = None
        if re.search(qverbs, p[:300].lower()) and not re.match(r"^\W*Gradonačelnik", p):
            hits = []
            for r in roster:  # full name first, else surname stem (any case ending: Čabraje, Dijanić)
                sur = r["name"].split()[-1]
                m = re.search(re.escape(r["name"]), p[:250]) or re.search(r"\b" + re.escape(sur[:max(4, len(sur) - 2)]) + r"\w*", p[:250])
                if m:
                    hits.append((m.start(), r))
            if hits:
                who = min(hits, key=lambda h: h[0])[1]
        if who and re.search(r"(vijećni\w*|Vijećni\w*)", p[:250]):
            out.append({"name": who["name"], "party": who["party"], "question": p, "to": "Gradonačelnik",
                        "answer": "", "answered_by": None, "fonogram": None, "url": None})
        elif out:
            out[-1]["answer"] = (out[-1]["answer"] + " " + p).strip()
    for q in out:
        if re.search(r"gradonačelni|Vasilić", q["answer"]):
            q["answered_by"] = MAYOR["name"]
        else:
            m = re.search(r"(?:Voditelj\w*|Pročelni\w*|direktor\w*)[^.]{0,80}?([A-ZČĆŠŽĐ]\w+ [A-ZČĆŠŽĐ]\w+)", q["answer"])
            q["answered_by"] = m.group(1) if m else None
        q["answer"] = q["answer"] or None
        if not q["answer"]:
            q["to"] = None
    return out


# ---------------------------------------------------------------- agenda as adopted
def overlap(ref, title):
    b = stems(title)
    return len(stems(ref) & b) / max(1, len(b))


def merge_with_minutes(items, sections, adopted):
    """Minutes sections 'Ad N.' follow the agenda as adopted (renumbered after removals, plus additions).
    Each section is matched to a convocation item by title overlap (adopted-list title + the section's
    first lines); unmatched convocation items were taken off the agenda."""
    merged, used = [], set()
    for no in sorted(sections):
        head = squash(sections[no][:600])
        ref = adopted.get(no, "") + " " + head
        scored = sorted(((overlap(ref, it["title"]) + (0.1 if it["no"] == no else 0), it["no"]) for it in items
                         if it["no"] not in used), reverse=True)
        src = next((it for it in items if scored and it["no"] == scored[0][1]), None)
        if src and scored[0][0] >= 0.45:
            used.add(src["no"])
            row = {**src, "no": no}
            if src["no"] != no:
                row["proposed_no"] = src["no"]
        else:  # added to the agenda at the session (dopuna) or unmatched: title from the minutes
            t = adopted.get(no) or re.split(r",\s*(?:obrazlož|oblazlož|iznijel|podnio|podnijel)|\.\s", head)[0]
            row = {"no": no, "title": t[:300], "full_title": t, "proposer": "", "attachments": [],
                   "added_at_session": True}
        merged.append(row)
    nxt = max([m["no"] for m in merged] + [0]) + 1
    for it in items:
        if it["no"] not in used:
            merged.append({**it, "no": nxt, "proposed_no": it["no"], "_removed": True})
            nxt += 1
    return merged


def renumber(items, gone):
    """No minutes: items named as removed in the news go to the end (status povučen), the rest are
    renumbered in order, as the Krk minutes do (session 4: proposed 27 became Ad 25)."""
    out, k = [], 0
    for it in items:
        if it["no"] not in gone:
            k += 1
            out.append({**it, "no": k, **({"proposed_no": it["no"]} if it["no"] != k else {})})
    for it in items:
        if it["no"] in gone:
            k += 1
            out.append({**it, "no": k, "proposed_no": it["no"], "_removed": True})
    return out


# ---------------------------------------------------------------- roster
def members():
    page = get(GV, fresh=True)
    t = clean(body(page))
    part = t[t.find("Članovi:"):] if "Članovi:" in t else t
    out = []
    for name, party in re.findall(r"([A-ZČĆŠŽĐ][\w-]+(?: [A-ZČĆŠŽĐ][\w-]+){1,2}) \(([^)]+)\)", part):
        if name not in [o["name"] for o in out]:
            out.append({"name": name, "party": party.strip()})
    return out


def discover():
    """session no -> {'agenda': url, 'news': [urls], 'aktualni': [urls]} for the current term."""
    S = {}
    pages = []
    for y in (2025, 2026):
        for kind in ("sazivi", "sjednice"):
            for href, title in re.findall(r'<h2><a href="([^"]+)">(.*?)</a>', get(f"/kategorije/{kind}-{y}", fresh=True)):
                pages.append((kind, href, clean(title)))
    for kind, href, title in pages:
        n = session_no(title) or session_no(href.replace("-", " "))
        if n is None:
            continue
        page = get(href)
        b = clean(body(page))
        d = find_date(b, year=re.search(r"-(20\d\d)/", href).group(1) if re.search(r"-(20\d\d)/", href) else None)
        if d and d < TERM_START:
            continue
        s = S.setdefault(n, {"agenda": None, "agenda_items": 0, "news": [], "aktualni": []})
        if "aktualni sat" in title.lower():
            s["aktualni"].append(href)
        elif re.search(r"dnevni\s+red", b, re.I) and re.search(r"sazva|saziva", b) and "Materijale" in b:
            k = len(agenda(page))
            if k > s["agenda_items"]:
                s["agenda"], s["agenda_items"] = href, k
        elif kind == "sjednice":
            s["news"].append(href)
    return S


def minutes_index():
    mins = {}
    for y in (2025, 2026):
        page = get(f"{GV}/zapisnici-i-tonski-zapisnici/zapisnici-{y}", fresh=True)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            a = re.search(r'href="([^"]+\.pdf)"', tr)
            if not a or not tds:
                continue
            label = clean(tds[0])
            if label.lower().startswith("zaključ") or not (label.lower().startswith("zapisnik")
                                                           or "zapisnik" in clean(tr).lower()):
                continue
            n = session_no(label) or (1 if "konst" in a.group(1) else None)
            if n is None:
                m = re.search(r"zapisnik_(\d+)\.", a.group(1))
                n = int(m.group(1)) if m else None
            if n is not None:
                mins.setdefault((y, n), a.group(1))
    return mins


def recordings_index():
    recs = []
    for y in (2025, 2026):
        page = get(f"{GV}/zapisnici-i-tonski-zapisnici/zapisnici-{y}")
        for src, desc in re.findall(r'<audio src="([^"]+\.mp3)"[^>]*>\s*</audio>\s*<div class="description">(.*?)</div>', page, re.S):
            desc = clean(desc)
            n = session_no(desc)
            part = re.search(r"(\d+)\.\s*dio", desc)
            recs.append({"session": n, "part": int(part.group(1)) if part else 1, "url": src, "title": desc})
    return recs


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()))
    except ValueError:
        return None


# ---------------------------------------------------------------- main
def main(download_audio=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    roster = members()
    # Goran Marević sat in the constitutive session; from session 3 his mandate is dormant and
    # Dubravka Dijanić (first on his list) holds the seat. Kept so session-1 attendance has a party.
    roster_all = roster + [{"name": "Goran Marević", "party": "Kandidacijska lista grupe birača; nositelj liste: Goran Marević",
                            "note": "mandat u mirovanju od 3. sjednice (30. 9. 2025.); mjesto preuzela Dubravka Dijanić"}]
    S = discover()
    mins = minutes_index()
    recs = recordings_index()
    for n in sorted(S):
        s = S[n]
        apage = get(s["agenda"]) if s["agenda"] else ""
        items = agenda(apage) if apage else []
        date = find_date(clean(body(apage)).split("Dnevni red")[0], year=None) if apage else None
        title = f"{n}. sjednica Gradskog vijeća Grada Krka" + (" (konstituirajuća)" if n == 1 else "")
        murl = next((u for (y, k), u in sorted(mins.items()) if k == n), None)
        doc = {"session": n, "title": title, "date": date, "url": urllib.parse.urljoin(HOST, s["agenda"] or ""),
               "minutes_url": murl, "items": [], "attendance": [], "questions": [],
               "news_urls": [urllib.parse.urljoin(HOST, u) for u in s["news"]],
               "aktualni_sat_urls": [urllib.parse.urljoin(HOST, u) for u in s["aktualni"]]}
        removed, adopted, sections = [], [], {}
        if murl:
            text = pdf_text(get(murl, binary=True))
            att, adopted, removed, qs, sections, one = minutes_parse(text, roster_all)
            doc["attendance"], doc["questions"], doc["minutes_text"] = att, qs, text
            md = re.search(r"održane\s+(\d{1,2}\.\s*\w+\s*\d{4})", one)
            if md and find_date(md.group(1)):
                doc["date"] = find_date(md.group(1))
        # Material-only lines of the convocation are not agenda items
        items = [it for it in items if not re.fullmatch(r"(Poziv|Dopuna dnevnog reda|Prigovor na dnevni red)\W*", it["title"], re.I)]
        for it in items:
            it["title"] = re.sub(r"^Dopuna dnevnog reda\s*[-–]\s*", "", it["title"])
            it["full_title"] = re.sub(r"^Dopuna dnevnog reda\s*[-–]\s*", "", it["full_title"])
        news_text = " ".join(clean(body(get(u))) for u in s["news"])
        if sections:
            items = merge_with_minutes(items, sections, dict(adopted))
        else:
            gone = set(news_removed(news_text, items)) if news_text else set()
            items = renumber(items, gone)
        nv = news_votes(news_text, items) if news_text else {}
        if not doc["date"] and news_text:
            doc["date"] = find_date(news_text, year=None)
        m_all = re.search(r"(?:dnevnom redu našl\w* se|preostalih)\s+" + NUM + r"\s+točaka,?\s+(?:koje su|koje)\s+(?:su\s+)?(?:uglavnom\s+)?prihvaćene", news_text)
        all_ok = bool(m_all and "uglavnom" not in m_all.group(0) and num(m_all.group(1)) == sum(1 for it in items if not it.get("_removed")))
        for it in items:
            it["url"] = doc["url"]
            if it.pop("_removed", False):
                it["status"] = "povučen"
                it["status_note"] = "skinuto s dnevnog reda na početku sjednice (prihvaćen prigovor na dnevni red)"
            sec = sections.get(it["no"]) if it.get("status") != "povučen" else None
            if sec is not None:
                vs = section_votes(sec)
                if vs:
                    it["votes"] = [{k: v[k] for k in ("za", "protiv", "suzdrzano", "result", "unanimous")} for v in vs]
                    distinct = {(v["za"], v["protiv"], v["suzdrzano"], v["result"]) for v in vs}
                    if len(distinct) == 1:
                        v = vs[0]
                        it["vote"] = {"za": v["za"], "protiv": v["protiv"], "suzdrzano": v["suzdrzano"],
                                      "result": v["result"], "source": "zapisnik"}
                spk = debate(sec)
                if spk:
                    it["debate"] = [match_member(x, roster_all)[0] for x in spk]
            if "vote" not in it and "votes" not in it and it["no"] in nv and it.get("status") != "povučen":
                v = nv[it["no"]]
                if v.get("majority_only"):
                    it["status"] = {"Prijedlog usvojen": "prihvaćen", "Prijedlog nije usvojen": "odbijen"}[v["result"]]
                    it["status_source"] = "vijest (većinom glasova, bez brojeva)"
                za = None if v.get("majority_only") else v["za"]
                if v["unanimous"] and za is None:
                    za = present_count(news_text)
                    if za is None:
                        it["status"] = "prihvaćen"
                        it["status_source"] = "vijest (jednoglasno, broj nazočnih nepoznat)"
                if za is not None:
                    it["vote"] = {"za": za, "protiv": v["protiv"], "suzdrzano": v["suzdrzano"], "result": v["result"],
                                  "source": "vijest", "quote": v["sentence"][:400]}
                    if v["unanimous"] and v["za"] is None:
                        it["vote"]["note"] = "jednoglasno; broj 'za' = broj nazočnih vijećnika iz vijesti"
            if "status" not in it and all_ok and not it.get("vote") and not it.get("votes"):
                it["status"] = "prihvaćen"
                it["status_source"] = "vijest (sve točke prihvaćene većinom glasova)"
            if "status" not in it:
                res = (it.get("vote") or {}).get("result") or ((it.get("votes") or [{}])[-1]).get("result")
                it["status"] = {"Prijedlog usvojen": "prihvaćen", "Prijedlog nije usvojen": "odbijen"}.get(res)
            it.pop("_conv_no", None)
            it.pop("n_subs", None)
        doc["items"] = items
        if not doc["questions"]:
            for u in s["aktualni"]:
                qs = news_questions(get(u), roster_all)
                for q in qs:
                    q["url"] = urllib.parse.urljoin(HOST, u)
                doc["questions"] += qs
        else:
            for q in doc["questions"]:
                q["url"] = murl
        doc["present_count_news"] = present_count(news_text)
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nvote = sum(1 for i in items if i.get("vote"))
        print(f"krk session {n} ({doc['date']}): {len(items)} items "
              f"({sum(1 for i in items if i.get('status') == 'povučen')} removed), {nvote} with votes "
              f"[{', '.join(sorted({i['vote']['source'] for i in items if i.get('vote')}))}], "
              f"{len(doc['attendance'])} attendance, {len(doc['questions'])} questions, "
              f"minutes {'yes' if murl else 'no'}", flush=True)
    # recordings
    old = {r["id"]: r for r in json.loads((D / "recordings.json").read_text())} if (D / "recordings.json").exists() else {}
    recordings = []
    for r in sorted(recs, key=lambda r: (r["session"] or 0, r["part"])):
        rid = f"krk-{r['session']:02d}-{r['part']}"
        doc = D / "docs" / f"session_{r['session']:02d}.json"
        date = json.loads(doc.read_text())["date"] if doc.exists() else None
        recordings.append({"id": rid, "session": r["session"], "part": r["part"], "url": r["url"], "date": date,
                           "title": r["title"], "duration": old.get(rid, {}).get("duration")})
    if download_audio:
        (D / "audio").mkdir(exist_ok=True)
        for r in recordings:
            out = D / "audio" / f"{r['id']}.mp3"
            if not out.exists():
                print("download", r["id"], r["url"], flush=True)
                tmp = out.with_suffix(".part")
                req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as f:
                    while chunk := resp.read(1 << 20):
                        f.write(chunk)
                tmp.rename(out)
                time.sleep(1)
    for r in recordings:
        out = D / "audio" / f"{r['id']}.mp3"
        if out.exists():
            r["duration"] = ffprobe(out)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    print(f"recordings: {len(recordings)}, " + ", ".join(f"{r['id']} {r['duration']}s" for r in recordings), flush=True)
    (D / "members.json").write_text(json.dumps(roster_all, ensure_ascii=False, indent=1))
    (D / "mayor.json").write_text(json.dumps(MAYOR, ensure_ascii=False, indent=1))
    print(f"members: {len(roster)} current + Goran Marević (dormant mandate), mayor {MAYOR['name']}", flush=True)


def present_count(text):
    m = re.search(r"(?:nazočnost|nazočil\w*)\D{0,40}?" + NUM + r"\s+od\s+(?:ukupno\s+)?13", text or "")
    if m:
        return num(m.group(1))
    if re.search(r"nazočnost\s+svih\s+13|svi\s+\w*\s*vijećnici,?\s+njih\s+13", text or ""):
        return 13
    return None


if __name__ == "__main__":
    main("--audio" in sys.argv)
