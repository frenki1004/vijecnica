"""Zadar city council (Gradsko vijeće Grada Zadra), 2025-2029 term, from www.grad-zadar.hr.

The list "Sjednice Gradskog vijeća" (/sjednice-gradskog-vijeca-625/, paged /page-N/) links one page per session
(/sjednica-detaljnije/14-sjednica-gradskog-vijeca-grada-zadra-134.html). A session page has the title and date
("14. sjednica Gradskog vijeća Grada Zadra - 30. listopada 2026."), the YouTube recording ("snimka sjednice"),
the agenda (one paragraph per item, "N. title" or sub-items "N.M. title", each linking its material PDF on
krsevan.grad-zadar.hr) and, as "PRIVITAK", the extract of the minutes of the PREVIOUS session
("Izvadak iz Zapisnika 13. sjednice Gradskog vijeća", a scanned PDF: OCR with tesseract, hrv, as collect/krk.py).

The extract is the official minutes record of the decisions: the quorum, the agenda adopted, then one section per
item headed with the agenda number ("AD/9", OCR also reads "ADI9", "AD!/12", "ADIT"), each with the vote:
  Većinom glasova (16 "za", 5 "protiv" i 1 "suzdržan") su donesene Prve izmjene i dopune Proračuna …
  Jednoglasno (21 "za") donesena je Odluka o grobljima.
A count the formula does not name stays null (the extract lists only the non-zero groups, but we do not infer);
"Jednoglasno" gives protiv 0 and suzdržano 0. Votes before the agenda (agenda changes) are not items.
The newest session has no extract yet (it comes with the next session's page): items without votes.

Output: data/zadar/docs/session_NN.json (format of collect/cakovec.py), data/zadar/recordings.json (YouTube).
HTML cache data/zadar/raw/web, PDFs data/zadar/raw/pdf, OCR text data/zadar/raw/ocr.

Usage: python collect/zadar.py [--fresh]
"""
import difflib
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
D = ROOT / "data" / "zadar"
HOST = "https://www.grad-zadar.hr"
INDEX = HOST + "/sjednice-gradskog-vijeca-625/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
SEATS = 31
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
LISTED = re.compile(r'href="(https://www\.grad-zadar\.hr/sjednica-detaljnije/[^"]+)">\s*<em[^>]*>[^<]*</em>\s*'
                    r'<strong>([^<]+)</strong>\s*<span>([^<]+)</span>')
LINK = re.compile(r"""<a [^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.S)
YT = re.compile(r"""https?://(?:www\.)?(?:youtube\.com/(?:live/|watch\?v=|embed/)|youtu\.be/)([\w-]{11})""")
# section heads of the extract: "AD/9", OCR "ADI9", "AD!/12", "ADJ/1", "ADIT" (7), "AD/14.1"
HEAD = re.compile(r"^[ \t\f]*A[DO][ \t]?[/I!J|liHA\[]{0,3}[ \t]?/?[ \t]?(\d{1,3}|T)(?:\.[ \t]?(\d{1,2}))?\.?"
                  r"(?:[ \t]*[—–-]{1,3}[ \t]*A\S*?(\d{1,3}))?[ \t|'.]*$", re.M)
QUOTES = str.maketrans({c: '"' for c in "„“”«»?"})
_robots, _last = {}, {}


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt per host, >= 1 s between requests to a host)."""
    sub = "pdf" if binary else "web"
    f = D / "raw" / sub / (hashlib.sha1(url.encode()).hexdigest()[:16] + (".pdf" if binary else ".html"))
    if f.exists() and not fresh:
        return f if binary else f.read_text()
    p = urllib.parse.urlsplit(url)
    host = f"{p.scheme}://{p.netloc}"
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser(host + "/robots.txt")
        rp.read()
        _robots[host] = rp
    if not _robots[host].can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0.0, 1.1 - (time.time() - _last.get(host, 0))))
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[host] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f if binary else data.decode("utf-8", "replace")


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ")).strip()


def pdf_text(path):
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) > 200:
        return t
    cache = D / "raw" / "ocr" / (Path(path).name + ".txt")
    if not cache.exists():
        pages = []
        (D / "raw").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            for png in sorted(Path(tmp).glob("p-*.png")):
                pages.append(subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"],
                                            capture_output=True, text=True,
                                            env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\f".join(pages))
    return cache.read_text()


def hr_date(s):
    m = re.search(r"(\d{1,2})\.\s*(\w+)\s+(\d{4})", s)
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS else None


def sessions(fresh):
    """{session number: (url, date)} of this term's numbered sessions, from the paged list."""
    out = {}
    for page in range(0, 6):
        text = get(INDEX + (f"page-{page}/" if page else ""), fresh=fresh)
        older = False
        for url, title, when in LISTED.findall(text):
            date = hr_date(when)
            m = re.match(r"\s*(\d+)\.", title)
            if not m or "Najava" in when:  # the ceremonial session has no number; an announced one is not held yet
                continue
            if date and date < TERM_START:
                older = True
                continue
            out.setdefault(int(m.group(1)), (url, date))
        if older:
            break
    return out



def page_parts(page):
    """(title, date, agenda items, minutes extracts [(session no, url)], YouTube ids) of a session page."""
    a = page.find('<div class="row article-header">')
    body = page[a:page.find('<div class="col-sm-4">', a)]
    h1 = flat(re.search(r"<h1>(.*?)</h1>", body, re.S).group(1))
    title = re.split(r"\s+-\s+(?=\d)", h1)[0]
    items, head, extracts = [], None, []
    for par in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
        ln = flat(par)
        pdf = next((u for u, _ in LINK.findall(par) if u.lower().endswith(".pdf")), None)
        x = re.search(r"Izvadak iz Zapisnika\s+(\d+)\.", ln, re.I)
        if x and pdf:
            extracts.append((int(x.group(1)), pdf))
            continue
        m = re.match(r"(\d{1,2})\s?\.(?:\s*(\d{1,2})\.)?\s*(\S.+)", ln)
        if not m or "dio" in ln[:12] or "youtu" in ln:
            continue
        no, sub, t = int(m.group(1)), m.group(2), m.group(3).strip(" '\"")
        att = [{"name": "Materijal", "url": pdf}] if pdf else []
        if sub:
            if head and head["no"] == no:
                head["_has_sub"] = True
                if not re.match(r"(Prijedlo\w*|Odluk\w*|Zaključ\w*|Izvješ\w*)\b", t):  # "14.1. AdriFLAVOUR …"
                    t = f"{head['title']}: {t}"
            items.append({"no": no, "sub_label": chr(96 + int(sub)), "title": t, "full_title": t,
                          "attachments": att})
            continue
        head = {"no": no, "sub_label": None, "title": t.rstrip(":").strip(), "attachments": att}
        head["full_title"] = head["title"]
        items.append(head)
    for it in items:  # a heading with sub-items is no item of its own; its material goes to the sub-items
        if it.get("_has_sub"):
            for j in items:
                if j["no"] == it["no"] and j["sub_label"] and not j["attachments"]:
                    j["attachments"] = it["attachments"]
    items = [it for it in items if not it.pop("_has_sub", False)]
    yt = list(dict.fromkeys(YT.findall(body)))
    return title, hr_date(h1), items, extracts, yt


def extract_agenda(text):
    """Items of the agenda adopted at the session, as the extract records it ("DNEVNI RED" up to the first "AD/")."""
    h = HEAD.search(text)
    i = text.rfind("DNEVNI RED", 0, h.start() if h else len(text))  # the last one: a reordered agenda is repeated
    if i < 0:
        return []
    part = text[i:h.start() if h else len(text)]
    part = re.split(r"\n[ \t]*[kž\*]{5,}", part.replace("\f", "\n"))[0]
    items, head = [], None
    for m in re.finditer(r"^[ \t]*(?:-[ \t]*)?(\d{1,3})[.,](?:[ \t]?(\d{1,2})\.)?[ \t]*[=—–-]?[ \t]*([A-ZČĆŠŽĐ\u201e\x22].*(?:\n(?![ \t]*\n|[ \t]*-?[ \t]*\d{1,3}\.|[ \t]*-).*)*)",
                         part, re.M):
        no, sub = int(m.group(1)), int(m.group(2)) if m.group(2) else None
        if no > 60 and not (head and str(no).startswith(str(head["no"]))):  # "2028. godine" wrapped
            continue
        if head and not sub and no > head["no"] + 5 and str(no).startswith(str(head["no"])):
            no, sub = head["no"], int(str(no)[len(str(head["no"])):])  # OCR "124." is 12.4.
        if not sub and head and not (head["no"] < no <= head["no"] + 3):
            no = head["no"] + 1  # OCR slip in the agenda number ("4." for "1."): the agenda counts up
        elif not sub and not head and no > 3:
            no = 1
        t = re.sub(r"\s+", " ", m.group(3)).strip(" :")
        if sub:
            if head and head["no"] == no:
                head["_has_sub"] = True
            items.append({"no": no, "sub_label": chr(96 + sub), "title": t, "full_title": t, "attachments": []})
        else:
            head = {"no": no, "sub_label": None, "title": t, "full_title": t, "attachments": []}
            items.append(head)
    return [it for it in items if not it.pop("_has_sub", False)]


def same_title(a, b):
    """Whether two titles are the same text up to OCR slips: every word of 4+ letters of each has a close match
    (difflib ratio >= 0.75) in the other. "održavanja" vs "građenja" or "u kulturi" vs "u tehničkoj kulturi" differ."""
    wa, wb = (re.findall(r"[^\W\d_]{4,}", t.lower()) for t in (a, b))
    close = lambda w, ws: any(difflib.SequenceMatcher(None, w, x).ratio() >= 0.75 for x in ws)
    return bool(wa and wb) and all(close(w, wb) for w in wa) and all(close(w, wa) for w in wb)


def merge(adopted, page):
    """The adopted agenda's items, titled and with materials from the page's agenda where the title is the same:
    the page item with the same number, else the single page item with that title (the agenda may be reordered)."""
    for it in adopted:
        same = next((p for p in page if (p["no"], p["sub_label"]) == (it["no"], it["sub_label"])), None)
        if not (same and same_title(same["title"], it["title"])):
            cands = [p for p in page if same_title(p["title"], it["title"])]
            same = cands[0] if len(cands) == 1 else None
        if same:
            it["title"], it["full_title"], it["attachments"] = same["title"], same["full_title"], same["attachments"]
    return adopted


def heads(text):
    """[(match, no, sub, range end)] of the "AD/N" section heads, OCR digit slips mended by the sequence."""
    out, prev = [], 0
    for m in HEAD.finditer(text):
        d = m.group(1)
        no = 7 if d == "T" else int(d)  # OCR: "ADIT" is AD/7
        if d != "T" and len(d) > 1 and d[0] == "1" and not (prev <= no <= prev + 4) and prev <= int(d[1:]) <= prev + 4:
            no = int(d[1:])  # "AD129.3": the slash read as 1
        if no < prev or no > prev + 15:  # not a head in sequence (a quoted number, a misread)
            continue
        sub = int(m.group(2)) if m.group(2) else None
        upto = int(m.group(3)) if m.group(3) else None
        out.append((m, no, sub, upto))
        prev = upto if upto and upto > no else no
    return out


def counts(par):
    """za, protiv, suzdržano from a formula; a group it does not name is None."""
    za = re.search(r"(\d+)\s*(?:glas\w*\s*)?\W{0,3}\s*za\b", par, re.I)
    pr = re.search(r"(\d+)\s*(?:glas\w*\s*)?\W{0,3}\s*protiv", par, re.I)
    su = re.search(r"(\d+)\s*(?:glas\w*\s*)?\W{0,4}\s*[sg]uzdr", par, re.I)
    return tuple(int(m.group(1)) if m else None for m in (za, pr, su))


FORMULA = re.compile(r"(Jedn\w{0,3}glasno|Većinom\s+glasova|S\s+\d+\s+glasova)\s*(\([^)]{0,90}\)?)?|"
                     r"\b(jedn\w{0,3}glasno)\s+(?:je\s+|su\s+)?(?:usvoj\w+|izabran\w*|donesen\w*|utvrđen\w*|prihvać\w+)", re.S)


def extract_votes(text):
    """[(no, sub, range end, vote or None, act named, position, parent)] from a minutes extract. The first formula of
    a section belongs to its "AD/N"; further formulas (a head OCR missed) get no number and are matched by act."""
    t = text.translate(QUOTES)
    hs = heads(t)
    out = []
    for i, (m, no, sub, upto) in enumerate(hs):
        end = hs[i + 1][0].start() if i + 1 < len(hs) else len(t)
        sec = t[m.end():end]
        fs = []
        for f in FORMULA.finditer(sec):
            sentence = re.split(r"\.\s", sec[max(0, f.start() - 300):f.start()])[-1]
            if re.search(r"održan\w*\s+\d|na\s+prvoj\s+konstitu", sentence):  # recalls an earlier session's vote
                continue
            fs.append(f)
        if not fs:
            out.append((no, sub, upto, None, "", m.start(), None))
        for k, f in enumerate(fs):
            vote, act = formula(text[m.end():end], sec, f)
            line = sec[sec.rfind("\n", 0, f.start()) + 1:f.start()]
            inline = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.?\s*$", line)  # "3.1. Jednoglasno je donesena …"
            if inline and int(inline.group(1)) == no:
                out.append((no, int(inline.group(2)), None, vote, act, m.end() + f.start(), None))
            elif k == 0:
                out.append((no, sub, upto, vote, act, m.start(), None))
            else:  # a second vote in the section: another item (a head OCR missed) or a further vote on this one
                out.append((None, None, None, vote, act, m.end() + f.start(), (no, sub)))
    return out


def formula(raw, sec, f):
    """(vote or None, act named) of one formula match f in section sec (raw: the same text, quotes untouched)."""
    unanimous = bool(f.group(3)) or f.group(1).startswith("Jedn")
    za, protiv, suzd = counts(f.group(2) or "") if f.group(1) else (None, None, None)
    if f.group(1) and f.group(1).startswith("S "):  # "S 11 glasova "za" i 15 glasova "protiv" nije se …"
        za, protiv, suzd = counts(re.split(r"\s(?:nije|je)\s", sec[f.start():f.start() + 160])[0])
    if unanimous:
        protiv, suzd = 0 if protiv is None else protiv, 0 if suzd is None else suzd
    after = re.sub(r"\s+", " ", sec[f.end():f.end() + 400])
    neg = re.match(r"\W*(?:(?:je|su|se)\s+)?(?:nije|nisu)\b", after)
    result = NO if neg or (za is not None and protiv is not None and za <= protiv) else YES
    if f.group(1):
        act = re.sub(r"^\W*(?:(?:je|su|se)\s+)?(?:nije\s+|nisu\s+)?(?:se\s+)?\w+\s+(?:je\s+|su\s+|se\s+)?", "", after)
        q = re.sub(r"\s+", " ", raw[f.start():f.end() + 400]).strip()
        q = re.split(r"(?<=[a-zčćšžđ\d\)\"“])\.\s+(?=[A-ZČĆŠŽĐ])|\s\d{1,2}\.\d{1,2}\.\s", q)[0]
    else:  # "… je jednoglasno usvojen": the sentence that ends with it
        q = re.split(r"(?<=[a-zčćšžđ\d\)\"“])\.\s+(?=[A-ZČĆŠŽĐ])", re.sub(r"\s+", " ", raw[:f.end()]))[-1]
        act = q
    act = re.split(r"(?<=[a-zčćšžđ\d\)\"])\.\s+(?=[A-ZČĆŠŽĐ])|\.$", act)[0].strip()
    if za is not None and not (1 <= za + (protiv or 0) + (suzd or 0) <= SEATS):
        print(f"   implausible count {(za, protiv, suzd)}, dropped: {q[:80]}", flush=True)
        return None, act
    return {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
            "unanimous": unanimous or (result == YES and protiv == 0 and suzd == 0), "quote": q[:300]}, act


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "zadra",
                                                                "godinu", "izmjen", "dopune", "zaklju"}


def overlap(a, b):
    """Shared word stems, the mean of the share in the shorter and in the longer title (a subset title scores
    below an equal one: "u kulturi" vs "u tehničkoj kulturi")."""
    a, b = stems(a), stems(b)
    k = len(a & b)
    return (k / max(1, min(len(a), len(b))) + k / max(1, len(a), len(b))) / 2


def match(items, no, sub, act):
    """The agenda item of an "AD/N" section: by number, unless the act it names fits another item clearly better
    (the council may renumber the agenda at the start of the session). Many titles share a template ("Izvješće o
    radu … TD X"), so only a clear margin moves a vote off its number."""
    subl = chr(96 + sub) if sub else None
    by_no = [it for it in items if it["no"] == no and it["sub_label"] == subl] if no is not None else []
    if not by_no and no is not None and sub is None:
        by_no = [it for it in items if it["no"] == no and it["sub_label"] in (None, "a")][:1]
    if not act:
        return by_no[0] if by_no else None
    scored = sorted(((overlap(it["title"], act), k) for k, it in enumerate(items)), reverse=True)
    best, bs = (items[scored[0][1]], scored[0][0]) if scored else (None, 0)
    unique = len(scored) < 2 or scored[0][0] > scored[1][0] + 0.05
    if no is None:
        return best if bs >= 0.6 and unique else None
    ns = overlap(by_no[0]["title"], act) if by_no else 0
    if by_no and (ns >= 0.85 or not (bs >= ns + 0.1 and bs >= 0.6 and unique)):
        return by_no[0]
    if bs >= 0.6 and unique:
        return best
    return by_no[0] if by_no else None


def headings(text, items):
    """[(pos, item)]: each "AD/N" section of the minutes extract with its item."""
    out = []
    for no, sub, _, _, act, pos, _ in extract_votes(text):
        it = match(items, no, sub, act)
        if it is not None and not any(x is it for _, x in out):
            out.append((pos, it))
    return sorted(out, key=lambda p: p[0])


def attendance(text):
    m = re.search(r"nazočno\s+(\d+)\s+vijećnik", text[:3000])
    return int(m.group(1)) if m else None


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    found = sessions(fresh)
    pages = {n: page_parts(get(u, fresh=fresh)) for n, (u, _) in sorted(found.items())}
    extracts = {k: u for p in pages.values() for k, u in p[3]}
    # the announced next session's page carries the extract of the newest held one
    for url in dict.fromkeys(re.findall(r'href="(https://www\.grad-zadar\.hr/sjednica-detaljnije/[^"]+)"',
                                        get(INDEX, fresh=fresh))):
        n = re.search(r"/(\d+)-", url)
        if n and int(n.group(1)) == max(found) + 1:
            extracts.update(dict(page_parts(get(url, fresh=fresh))[3]))
    recs = []
    for n, (title, date, items, _, yt) in pages.items():
        url, list_date = found[n]
        date = date or list_date
        minutes = extracts.get(n)
        text = pdf_text(get(minutes, binary=True)) if minutes else None
        adopted = extract_agenda(text) if text else []
        if adopted:
            items = merge(adopted, items)
        votes = extract_votes(text) if text else []
        nf = len(FORMULA.findall(text.translate(QUOTES))) if text else 0
        for no, sub, upto, vote, act, _, parent in votes:
            if not vote:
                continue
            it = match(items, no, sub, act)
            if parent and (it is None or it.get("vote")):  # a further vote under the same "AD/N"
                it = match(items, parent[0], parent[1], "")
                if it is not None and it.get("vote"):
                    it["votes"].append(vote)
                    continue
            if it is None:
                print(f"   vote AD/{no}{'.' + str(sub) if sub else ''} has no agenda item: {vote['quote'][:100]}", flush=True)
                continue
            if it.get("vote"):
                print(f"   AD/{no} matched {it['no']}{it['sub_label'] or ''} again, skipped: {vote['quote'][:80]}", flush=True)
                continue
            it["vote"], it["votes"] = vote, [vote]
        for it in items:
            v = it.get("vote")
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        doc = {"session": n, "title": title, "date": date, "url": url, "minutes_url": minutes,
               "minutes_text": text, "present": text and attendance(text), "items": items,
               "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"zadar session {n} ({date}): {len(items)} items, {nv} with votes ({nf} formulas, "
              f"{sum(1 for v in votes if v[3])} sections with a vote), minutes {'yes' if text else 'no'}",
              flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)
        for k, vid in enumerate(yt, 1):
            recs.append({"id": f"zadar-{n:02d}-{k}", "session": n, "part": k, "date": date,
                         "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube",
                         "title": f"{title} ({k}. dio)" if len(yt) > 1 else title})
    (D / "recordings.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"zadar: {len(pages)} sessions, {len(recs)} recordings", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
