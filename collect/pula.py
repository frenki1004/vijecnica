"""Pula city council (Gradsko vijeće Grada Pula - Pola), 2025-2029 term, from www.pula.hr.

The list /hr/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/ links one page per session
(.../sjednice/91/12-sjednica-gradskog-vijeca-grada-pula-pola-29072026/) with the convocation and the proposed agenda
(an <ol>, sub-items "2.1." inside an <li>, each linking its material PDF). A later session's agenda adopts the
minutes of earlier ones and links them: "Usvajanje: 3.2. Skraćenog zapisnika sa 12. sjednice …" (PDF, text layer).

The "skraćeni zapisnik" is the official record: the agenda adopted (possibly reordered), then one section per item
("AD – 3.  DONOŠENJE: 3.1. … 3.2. …") with every vote:
  Predsjednik … daje na glasanje točku 3.1. te nakon glasanja utvrđuje da je
         VIJEĆE sa 13 glasova "ZA", 5 glasova "PROTIV" i 2 "SUZDRŽANA" glasa, usvojilo …
"bez glasova „PROTIV“" is 0. Items come from the AD sections when minutes exist (their numbering is the adopted
one), otherwise from the session page; materials from the page by title. Votes on amendments and on the agenda are
not items. The page links no recordings (only the city's YouTube live stream channel), so there is no
recordings.json.

robots.txt asks every bot for Crawl-delay: 10, which get() keeps.

Output: data/pula/docs/session_NN.json (format of collect/cakovec.py). Cache data/pula/raw/web, data/pula/raw/pdf.

Usage: python collect/pula.py [--fresh]
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
D = ROOT / "data" / "pula"
HOST = "https://www.pula.hr"
INDEX = HOST + "/hr/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/"
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
TERM_START = "2025-06-01"
SEATS = 22
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
LISTED = re.compile(r'<a [^>]*href="(/hr/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/sjednice/\d+/[^"]+)"'
                    r'[^>]*>(.*?)</a>', re.S)
LINK = re.compile(r"""<a [^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.S)
HEAD = re.compile(r"^[ \t\f]*AD[ \t]*[–—-]\s*(\d{1,2})\.?[ \t]*([^\W\d].*)$", re.M)  # "AD -" may end a line
QUOTES = str.maketrans({c: '"' for c in "„“”«»"})
VOTE = re.compile(r'VIJEĆE\s+sa?\s+(\d+)\s+glas\w*\s+"ZA"(?=(.{0,400}))', re.S)  # tail: lookahead
_robots, _last = {}, {}
DELAY = 10.0  # robots.txt: Crawl-delay: 10


def get(url, binary=False, fresh=False):
    """Cached, polite GET (robots.txt, its crawl delay between requests)."""
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
    delay = max(1.0, _robots[host].crawl_delay(UA) or DELAY)
    time.sleep(max(0.0, delay - (time.time() - _last.get(host, 0))))
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
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


def hr_date(s):
    m = re.search(r"(\d{1,2})\.\s*(\w+)\s+(\d{4})", s)
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS else None


def sessions(fresh):
    """{session number: (url, title, date)} of this term, from the list page."""
    out = {}
    for path, label in LISTED.findall(get(INDEX, fresh=fresh)):
        label = flat(label)
        date = hr_date(label.rsplit(" - ", 1)[-1]) or hr_date(label)
        m = re.search(r"\((\d+)\.\s*sjednica\)", label) or re.match(r"\s*(\d+)\.?,?\s", label)
        if not m or not date or date < TERM_START:
            continue
        title = re.split(r"\s+-\s+(?=\d{2}\.\s*\w+\s+\d{4}\.?$)", label)[0]
        out.setdefault(int(m.group(1)), (HOST + path, title, date))
    return out


def page_parts(page):
    """(agenda items, {session no: minutes url}) of a session page."""
    i = page.find("<h1")
    body = page[i:page.find("</main>", i)]
    items, minutes = [], {}
    ol = re.search(r"<ol[^>]*>(.*?)</ol>", body, re.S)
    for no, li in enumerate(re.findall(r"<li[^>]*>(.*?)</li>", ol.group(1), re.S) if ol else [], 1):
        parts = re.split(r"<br\s*/?>", li)
        head = flat(parts[0])
        subs = [p for p in parts[1:] if re.match(r"\s*(?:&nbsp;|\s)*\d+\.\d+\.", flat(p))]
        for x, t in LINK.findall(li):
            z = re.search(r"zapisnika\s+sa?\s+(\d+)\.\s*(?:\w+\s+)?sjednic", flat(t), re.I)
            if z and x.lower().endswith(".pdf"):
                minutes[int(z.group(1))] = urllib.parse.urljoin(HOST, x)
        if subs and re.search(r":\s*$", head):
            prefix = re.sub(r":\s*$", "", head)
            for k, p in enumerate(subs, 1):
                t = re.sub(r"^\d+\.\d+\.\s*", "", flat(p))
                pdf = next((urllib.parse.urljoin(HOST, u) for u, _ in LINK.findall(p) if u.lower().endswith(".pdf")),
                           None)
                full = f"{prefix} {t}"
                items.append({"no": no, "sub_label": chr(96 + k), "title": full, "full_title": full,
                              "attachments": [{"name": "Materijal", "url": pdf}] if pdf else []})
        else:
            pdf = next((urllib.parse.urljoin(HOST, u) for u, _ in LINK.findall(li) if u.lower().endswith(".pdf")),
                       None)
            t = flat(li)
            items.append({"no": no, "sub_label": None, "title": t, "full_title": t,
                          "attachments": [{"name": "Materijal", "url": pdf}] if pdf else []})
    return items, minutes


def sentence_case(t):
    t = re.sub(r"\s+", " ", t).strip(" :")
    if sum(c.isupper() for c in t) > 0.6 * max(1, sum(c.isalpha() for c in t)):
        t = t.lower()
        t = t[0].upper() + t[1:]
        t = re.sub(r"\b(grada? pul\w*|pula|pole?|pule)\b", lambda m: m.group(0).title(), t, flags=re.I)
    return t


def minutes_items(text):
    """[(item, section start, section end)] from the AD sections of the minutes; sub-items "3.1." under a head."""
    heads = list(HEAD.finditer(text))
    out = []
    for i, m in enumerate(heads):
        no = int(m.group(1))
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        # the heading block: up to the first blank-line-separated paragraph that is not the heading's continuation
        block = re.split(r"\n[ \t]*\n[ \t]*\n|\n\s*\n(?=[ \t]*[A-ZČĆŠŽĐ][a-zčćšžđ])", text[m.start():end])[0]
        block = block[m.end(1) - m.start() + 1:]
        subs = list(re.finditer(r"^[ \t]*(\d{1,2})\.(\d{1,2})\.?[ \t]*([^\W\d].*(?:\n(?![ \t]*\d{1,2}\.\d{1,2}\.?).*)*)",
                                block, re.M))
        if subs:
            head = sentence_case(block[:subs[0].start()])
            for k, s in enumerate(subs, 1):
                t = sentence_case(s.group(3))
                full = f"{head} {t[0].lower()}{t[1:]}" if head.endswith(":") or head.lower().startswith("donošenje") \
                    else t
                full = re.sub(r":\s", " ", full, count=1)
                out.append(({"no": no, "sub_label": chr(96 + int(s.group(2))), "title": full, "full_title": full,
                             "attachments": []}, m.start(), end))
        else:
            t = sentence_case(block)
            out.append(({"no": no, "sub_label": None, "title": t, "full_title": t, "attachments": []}, m.start(), end))
    return out


def votes_in(text, start, end):
    """[(point "3.1" or None, vote)] of the formulas in a section, with the point announced before each."""
    t = text.translate(QUOTES)
    out = []
    for m in VOTE.finditer(t, start, end):
        before = t[max(start, m.start() - 400):m.start()]
        pt = re.findall(r"na\s+glasanje\s+(?:prijedlog\s+)?(\w+)\s+(\d{1,2}(?:\.\d{1,2})?)\.?", before, re.I)
        what = pt[-1][0].lower() if pt else ""
        if re.search(r"amandman", before[-250:], re.I) and what != "točku":
            continue  # a vote on an amendment
        point = pt[-1][1] if pt and what == "točku" else None
        tail = m.group(2)
        k = re.search(r"\b(?:NIJE\s+|nije\s+)?(?:donijel|usvojil|prihvatil|odbil|izabral|utvrdil|dal[oa]\b|imenoval|"
                      r"primil|potvrdil|razriješil|verificiral)\w*", tail)
        formula = tail[:k.start()] if k else tail[:200]
        za = int(m.group(1))
        p = re.search(r'(\d+)\s+glas\w*\s+"PROTIV"', formula)
        protiv = int(p.group(1)) if p else (0 if re.search(r'bez\s+glas\w*\s+"PROTIV"', formula) else None)
        z = re.search(r'(\d+)\s+(?:glas\w*\s+)?"SUZDRŽAN', formula)
        suzd = int(z.group(1)) if z else (0 if re.search(r'bez\s+(?:glas\w*\s+)?"SUZDRŽAN', formula) else None)
        neg = (k and re.match(r"nije|odbil", k.group(0), re.I)) or re.search(r"\bnije\s+(?:usvoj|donije|prihvat)", formula, re.I)
        result = NO if neg or za <= (protiv or 0) else YES
        end_q = m.end() + (k.end() if k else 200)
        rest = re.split(r"\n[ \t]*\n[ \t]*\n|\n\s*(?:Predsjednik|PREDSJEDNIK|AD\s*[–—-])", text[end_q:end_q + 400])[0]
        q = re.sub(r"\s+", " ", text[m.start():end_q] + " " + rest).strip()[:300]
        if za is not None and not (1 <= za + (protiv or 0) + (suzd or 0) <= SEATS):
            print(f"   implausible count {(za, protiv, suzd)}, dropped", flush=True)
            continue
        out.append((point, {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
                            "unanimous": result == YES and protiv == 0 and suzd == 0, "quote": q}))
    return out


def headings(text, items):
    """[(pos, item)]: each "AD – N." section of the minutes with its item (the first, for sub-items)."""
    out = []
    for m in HEAD.finditer(text):
        it = next((x for x in items if x["no"] == int(m.group(1))), None)
        if it is not None and not any(x is it for _, x in out):
            out.append((m.start(), it))
    return out


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "donoše",
                                                                "godinu", "pula", "pola"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    k = len(a & b)
    return (k / max(1, min(len(a), len(b))) + k / max(1, len(a), len(b))) / 2


def attendance(text):
    m = re.search(r"prisutno\s+(\d+)\s+vijećnik", text[:6000])
    return int(m.group(1)) if m else None


def minutes_date(text):
    m = re.search(r"održane\s+\w+,?\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", text[:3000])
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    found = sessions(fresh)
    pages = {n: page_parts(get(u, fresh=fresh)) for n, (u, _, _) in sorted(found.items())}
    minutes = {k: u for _, mins in pages.values() for k, u in mins.items()}
    for n, (url, title, date) in sorted(found.items()):
        agenda = pages[n][0]
        murl = minutes.get(n)
        text = pdf_text(get(murl, binary=True)) if murl else None
        found_f = len(VOTE.findall(text.translate(QUOTES))) if text else 0
        if text and HEAD.search(text):
            secs = minutes_items(text)
            items = [it for it, _, _ in secs]
            for it in items:  # materials (and the cleaner title) from the page agenda
                sc = sorted(((overlap(a["title"], it["title"]), k) for k, a in enumerate(agenda)), reverse=True)
                best = agenda[sc[0][1]] if sc and sc[0][0] >= 0.6 and (len(sc) < 2 or sc[0][0] > sc[1][0] + 0.03) \
                    else None  # only a clearly best page item (sub-item titles share a template)
                if best:
                    it["attachments"] = best["attachments"]
                    it["title"] = it["full_title"] = best["title"]
            by_sec = {}
            for it, s, e in secs:
                by_sec.setdefault((s, e), []).append(it)
            for (s, e), its in by_sec.items():
                for point, vote in votes_in(text, s, e):
                    it = None
                    if point:  # "daje na glasanje točku 3.2": that item, wherever its section (joint debates)
                        no, _, sub = point.partition(".")
                        subl = chr(96 + int(sub)) if sub else None
                        it = next((x for x in items if x["no"] == int(no) and x["sub_label"] == subl), None)
                        if it is None and not sub:
                            it = next((x for x in items if x["no"] == int(no) and x["sub_label"] is None), None)
                    elif len(its) == 1:
                        it = its[0]
                    if it is None:
                        it = next((x for x in its if not x.get("vote")), None) if len(its) == 1 else None
                    if it is None:
                        print(f"   vote {point} in AD {its[0]['no']} has no item: {vote['quote'][:80]}", flush=True)
                        continue
                    if it.get("vote"):
                        it["votes"].append(vote)
                    else:
                        it["vote"], it["votes"] = vote, [vote]
        else:
            items = agenda
        for it in items:
            v = it.get("vote")
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        doc = {"session": n, "title": title, "date": (text and minutes_date(text)) or date, "url": url,
               "minutes_url": murl, "minutes_text": text, "present": text and attendance(text), "items": items,
               "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"pula session {n} ({doc['date']}): {len(items)} items, {nv} with votes "
              f"({sum(len(i.get('votes', [])) for i in items)} votes, {found_f} formulas), "
              f"minutes {'yes' if text else 'no'}", flush=True)
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:90]}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
