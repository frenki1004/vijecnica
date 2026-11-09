"""Collect council sessions from NetCom eSjednice public portals, 2025-2029 term (one collector, many units).

Portals live at sjednice.<domain>.hr or <grad|opcina><name>.esjednice.hr. The public page carries a CSRF token
and one link per meeting type (data-route="../../meetingtype/N" + data-token); the page's own XHR calls are:
  POST /meetingtype/N   {token, sysc=showmeetings}            -> {"html"}: the sessions by year, with dates
  GET  /meeting/ID      {token, sysc=showmeeting}             -> {"html"}: tabs "Točke dnevnog reda" (items),
                                                                 "Dokumenti" (invitation, minutes, MP3s ...),
                                                                 "Odluke" (adopted acts)
  POST /dailyagenda/ID  {token, sysc=showdailyagenda, ...}    -> {"html"}: one item's documents
  GET  /dldocoriginal/ID?signature=...                        -> the file
The meeting-type id of the council differs by unit (UNITS below). Kostrena publishes only the "Odluke" tab,
so its items are the adopted acts.

Minutes (zapisnik) are usually attached to a LATER session ("Zapisnik sa 9. sjednice Gradskog vijeća"),
sometimes to the session itself; committee / local-board minutes on the same page are skipped by name, and
the session a minutes file records is read from its name, else its first lines. PDFs go through
`pdftotext -layout`, .docx through zipfile + word/document.xml.

One minutes parser for the national phrasing:
  headings  "AD 1." / "Ad 1.)" / "Ad – 1." / "Točka 1.)" / "TOČKA 1." (title on the same line or not); when a
            minutes file has none of these, bare "1. PRIJEDLOG ..." lines (Senj) that match an item's title.
            Councils take items out of order and add items, so a heading is matched to the agenda by TITLE;
            the number is only the fallback for a heading with no title of its own.
  votes     "S 10 glasova ZA i 2 glasa PROTIV (vijećnica ..., vijećnik ...) je usvojen" (Kastav names
            dissenters: kept in `quote`), "većinom glasova (10 ZA i 4 SUZDRŽANA) donesena", "jednoglasno
            (12 ZA)", "jednoglasno (9 „ZA“)", "s (7 glasova „ZA“) i (2 glasa „PROTIV“)", "s 13 glasova "ZA"
            jednoglasno", "JEDNOGLASNO je usvojen", "1 je bio „PROTIV“", "4 su bila SUZDRŽANA",
            "„ZA“ je glasovalo 12 vijećnika", counts as words ("pet glasova", "jednim glasom"),
            "nije usvojen / nije prihvaćen / odbilo / odbijen".
            A vote belongs to the last heading before it; a section whose title matches no portal item is
            a boundary, and its votes are logged as unmatched (never put on the item before). Under a
            heading with sub-items, the act named with the vote picks the sub-item. Votes on amendments,
            the agenda, motions ("prijedlog da ...", joining debates), committee opinions and votes retold
            in a speech are not item votes; votes before the first heading (agenda, previous minutes) are
            dropped. Several separate votes under one item (candidates, several acts) give no single count:
            za/protiv/suzdrzano null, the votes listed in item["votes"].
  counts    (see vote_record) "jednoglasno" without a number -> za null, protiv = suzdrzano = 0, note
            "Zapisnik navodi da je odluka donesena jednoglasno, bez broja glasova." Never inferred from
            attendance. Only ZA given -> protiv = suzdrzano = 0 + "... nisu navedeni (upisano 0)." Other
            partial counts -> the missing kind null + "Zapisnik ne navodi broj glasova PROTIV." unless the
            counts add up to the members present stated in the minutes, or "nitko protiv".

Cache: data/<unit>/raw/web/<route>_<id>.json (API answers), data/<unit>/raw/pdf/<doc id>.<ext> (files).
Audio/video files are listed in recordings.json, never downloaded.
Output: data/<unit>/docs/session_NN.json, data/<unit>/recordings.json, data/<unit>/members.json ([]).

Usage: python collect/netcom.py [unit ...] [--fresh]
       (no unit = all; --fresh re-fetches session lists and session pages, files stay cached)
"""
import html
import http.cookiejar
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "vijecnica-research/0.1 (open data hackathon)"
TERM_START = "2025-06-01"  # local elections May 2025; constitutive sessions from June
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"

# key: name, body, host, council meeting-type id, genitive of the name (a stop word in titles), tier
UNITS = {
    "opatija": {"name": "Opatija", "body": "Gradsko vijeće", "host": "sjednice.opatija.hr", "mtype": 1,
                "gen": "Opatije", "tier": "A"},
    "kastav": {"name": "Kastav", "body": "Gradsko vijeće", "host": "sjednice.kastav.hr", "mtype": 1,
               "gen": "Kastva", "tier": "A"},
    "senj": {"name": "Senj", "body": "Gradsko vijeće", "host": "gradsenj.esjednice.hr", "mtype": 1,
             "gen": "Senja", "tier": "A"},
    "ogulin": {"name": "Ogulin", "body": "Gradsko vijeće", "host": "gradogulin.esjednice.hr", "mtype": 1,
               "gen": "Ogulina", "tier": "A"},
    "viskovo": {"name": "Viškovo", "body": "Općinsko vijeće", "host": "sjednice.opcina-viskovo.hr", "mtype": 1,
                "gen": "Viškovo", "tier": "A"},
    "punat": {"name": "Punat", "body": "Općinsko vijeće", "host": "sjednice.punat.hr", "mtype": 1,
              "gen": "Punat", "tier": "A"},
    "kostrena": {"name": "Kostrena", "body": "Općinsko vijeće", "host": "sjednice.kostrena.hr", "mtype": 1,
                 "gen": "Kostrena", "tier": "B"},
    "novivinodolski": {"name": "Novi Vinodolski", "body": "Gradsko vijeće", "host": "sjednice.novi-vinodolski.hr",
                       "mtype": 1, "gen": "Novog Vinodolskog", "tier": "B"},
    "makarska": {"name": "Makarska", "body": "Gradsko vijeće", "host": "gradmakarska.esjednice.hr", "mtype": 1,
                 "gen": "Makarske", "tier": "B"},
    "ploce": {"name": "Ploče", "body": "Gradsko vijeće", "host": "gradploce.esjednice.hr", "mtype": 1,
              "gen": "Ploča", "tier": "B"},
    "omisalj": {"name": "Omišalj", "body": "Općinsko vijeće", "host": "opcinaomisalj.esjednice.hr", "mtype": 1,
                "gen": "Omišlja", "tier": "B"},
    "baska": {"name": "Baška", "body": "Općinsko vijeće", "host": "opcinabaska.esjednice.hr", "mtype": 3,
              "gen": "Baška", "tier": "B"},
    "cavle": {"name": "Čavle", "body": "Općinsko vijeće", "host": "opcinacavle.esjednice.hr", "mtype": 1,
              "gen": "Čavle", "tier": "B"},
    # found by collect/discover.py (2026-11-09); other eSjednice portals it found (Rovinj, Crikvenica, Virovitica,
    # Novalja, Malinska-Dubašnica, Matulji, Orahovica, Županja, Pakoštane) are not collected yet; Samobor's portal
    # holds only one session from 2018 (the council publishes on samobor.hr)
    "split": {"name": "Split", "body": "Gradsko vijeće", "host": "sjednice.split.hr", "mtype": 6,
              "gen": "Splita", "tier": "A"},
}


class Refused(Exception):
    """The portal refused (HTTP error, bot check, no CSRF token): the unit is skipped, never worked around."""


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------------------------- portal (HTTP)

class Portal:
    """One eSjednice host: cached API calls, at most one request per second."""

    def __init__(self, key, host, fresh=False):
        self.key, self.host, self.fresh = key, host, fresh
        self.base = "https://" + host
        self.dir = ROOT / "data" / key
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.home, self.csrf, self.last, self.requests = None, None, 0.0, 0

    def _open(self, url, body=None, headers=None, method=None):
        time.sleep(max(0, 1.0 - (time.time() - self.last)))
        try:  # a 403 / 402 / bot check stops this unit: do not work around it
            req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": UA, **(headers or {})})
            raw = self.op.open(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            raise Refused(f"HTTP {e.code} at {url}") from None
        finally:
            self.last = time.time()
            self.requests += 1
        if re.search(rb"captcha|cf-chl|Just a moment", raw[:5000], re.I):
            raise Refused(f"bot check at {url}")
        return raw

    def start(self):
        """The public page: CSRF token and session cookie for the XHR calls (fetched once, only if needed)."""
        if self.home is None:
            self.home = self._open(self.base + "/").decode("utf-8", "replace")
            m = re.search(r'csrf-token" content="([^"]+)', self.home)
            if not m:
                raise Refused(f"no CSRF token on {self.base}/ (not a public eSjednice portal)")
            self.csrf = m.group(1)
        return self.home

    def api(self, route, rid, token, sysc, method, extra=None, fresh=False):
        """JSON from /<route>/<id>, as the page's own XHR asks for it; cached as raw/web/<route>_<id>.json."""
        cache = self.dir / "raw" / "web" / f"{route}_{rid}.json"
        if not cache.exists() or fresh:
            self.start()
            q = urllib.parse.urlencode({"token": token, "sysc": sysc, **(extra or {})})
            url = f"{self.base}/{route}/{rid}"
            hdr = {"X-CSRF-TOKEN": self.csrf, "X-Requested-With": "XMLHttpRequest"}
            raw = self._open(url, q.encode(), hdr, "POST") if method == "POST" else self._open(url + "?" + q, None, hdr)
            try:
                json.loads(raw)
            except ValueError:
                raise Refused(f"not JSON from {url}: {raw[:120]!r}") from None
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
        return json.loads(cache.read_text("utf-8"))

    def file(self, url, ext):
        """A document (/dldocoriginal/<id>), cached as raw/pdf/<id>.<ext>."""
        doc = re.search(r"/dldocoriginal/(\d+)", url).group(1)
        cache = self.dir / "raw" / "pdf" / f"{doc}.{ext or 'bin'}"
        if not cache.exists():
            raw = self._open(url)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
        return cache


def meeting_types(p):
    p.start()
    return [(int(i), t, c, clean(lab)) for r, i, m, t, c, lab in
            re.findall(r'data-route="\.\./\.\./(\w+)/(\d+)"(?: data-sysmethod="(\w+)")? data-token="([^"]+)" '
                       r'data-sysc="(\w+)"[^>]*>(.*?)</a>', p.home, re.S) if r == "meetingtype"]


def session_list(p, mtype):
    """[(meeting id, token, title, date)] of one meeting type, all years."""
    cache = p.dir / "raw" / "web" / f"meetingtype_{mtype}.json"
    if cache.exists() and not p.fresh:
        d = json.loads(cache.read_text("utf-8"))
    else:
        mt = [t for t in meeting_types(p) if t[0] == mtype]
        if not mt:
            raise Refused(f"meeting type {mtype} not on {p.base}/ (types: {meeting_types(p)})")
        d = p.api("meetingtype", mtype, mt[0][1], mt[0][2], "POST", fresh=True)
    out = []
    for mid, tok, body in re.findall(r'data-route="\.\./\.\./meeting/(\d+)" data-sysmethod="GET" data-token="([^"]+)" '
                                     r'data-sysc="showmeeting"[^>]*>(.*?)</a>', d["html"], re.S):
        title = clean(re.search(r'meeting-title">(.*?)</h3>', body, re.S).group(1))
        info = re.search(r'meeting-info[^>]*>(.*?)</span>', body, re.S)
        dm = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", clean(info.group(1)) if info else "")
        date = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}" if dm else None
        out.append((int(mid), tok, title, date))
    return out


DOC = re.compile(r'<a (?:title="[^"]*" )?href="(https://[^"]+/(?:dldocoriginal|pdfviewer)/(\d+)\?[^"]+)"[^>]*>\s*'
                 r'<i class="fa ([\w-]+)"[^>]*></i>\s*(.*?)<span class="text-muted small">\[\s*\.?(\w*)\s*\]</span>', re.S)


def docs_in(fragment, base):
    """[{name, url, ext, kind}] for the document rows of an HTML fragment; url is the download link."""
    out = []
    for url, did, icon, name, ext in DOC.findall(fragment):
        dl = re.search(rf'{re.escape(base)}/dldocoriginal/{did}\?signature=\w+', fragment)
        kind = "audio" if "audio" in icon or ext.lower() in ("mp3", "wav", "m4a") else \
            "video" if "video" in icon or ext.lower() in ("mp4", "avi", "mov") else "doc"
        out.append({"name": clean(name), "url": html.unescape(dl.group(0) if dl else url), "ext": ext.lower(),
                    "kind": kind})
    return out


def meeting(p, mid, tok):
    """Title, items (with the token to expand each) and the documents of the session page's tabs."""
    h = p.api("meeting", mid, tok, "showmeeting", "GET", fresh=p.fresh)["html"]
    starts = sorted((m.start(), m.group(1)) for m in re.finditer(r'<div id="(\w+)" class="tab-pane', h))
    frag = {k: h[s:(starts[i + 1][0] if i + 1 < len(starts) else len(h))] for i, (s, k) in enumerate(starts)}
    items = []
    for daid, sub, tok2, body in re.findall(r'data-route="\.\./\.\./dailyagenda/(\d+)" data-showsubdailyagendas="(\d)" '
                                            r'data-token="([^"]+)" data-sysc="showdailyagenda"[^>]*>(.*?)</a>', h, re.S):
        info = re.search(r'class="dailyagenda-info"[^>]*>(.*?)(?:<br\s*/?>|</p>)', body, re.S)
        izl = re.search(r"Izlagač\w*:\s*(.*?)</small>", body, re.S)
        pad = re.search(r"padding-left:\s*(\d+)px", body)
        items.append({"daid": int(daid), "token": tok2, "sub": sub, "text": clean(info.group(1) if info else body),
                      "presenter": clean(izl.group(1)) if izl else "", "indent": int(pad.group(1)) if pad else 0})
    docs = [d for k, v in frag.items() if k not in ("dailyagendas", "decisions") for d in docs_in(v, p.base)]
    return {"title": clean(re.search(r'showmeeting-title">(.*?)</h3>', h, re.S).group(1)),
            "documents": docs, "decisions": docs_in(frag.get("decisions", ""), p.base), "items": items}


def item_docs(p, it):
    d = p.api("dailyagenda", it["daid"], it["token"], "showdailyagenda", "POST", {"showsubdailyagendas": it["sub"]})
    return docs_in(d.get("html") or "", p.base)


# ---------------------------------------------------------------------------------------------- text of files

def pdf_text(path):
    """pdftotext -layout; a scan without a text layer (Viškovo 1.-9., constitutive sessions) is OCRed once with
    tesseract (hrv), as collect/sibenik.py does, and the text cached in raw/ocr/."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(text.strip()) > 200 or not (shutil.which("tesseract") and shutil.which("pdftoppm")):
        return text
    out = Path(path).parents[1] / "ocr" / (Path(path).name + ".txt")
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            pages = [subprocess.run(["tesseract", str(pg), "stdout", "-l", "hrv", "--psm", "4"],
                                    capture_output=True, text=True).stdout for pg in sorted(Path(tmp).glob("p-*.png"))]
        out.write_text("\n".join(pages))
    return out.read_text()


def docx_text(path):
    """Paragraph text of a .docx (word/document.xml), one paragraph per line."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    lines = []
    for p in re.findall(r"<w:p[ >].*?</w:p>|<w:p/>", xml, re.S):
        parts = re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>|<w:(tab|br|cr)/>", p)
        lines.append("".join(t if t else ("\t" if tag == "tab" else "\n") for t, tag in parts))
    return html.unescape("\n".join(lines))


def doc_text(path, ext):
    if ext == "pdf":
        return pdf_text(path).replace("\f", "\n")  # a form feed before a page's first line hides "AD 12." from ^
    if ext == "docx":
        return docx_text(path)
    if ext == "doc" and shutil.which("textutil"):  # macOS: old binary Word files
        return subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True,
                              text=True).stdout
    return ""


# ---------------------------------------------------------------------------------------------- agenda

def stem_set(t):
    return {w[:5] for w in re.findall(r"\w+", t.lower()) if len(w) > 3}


BASE_STOP = ("prijedlog prijedloga odluke odluka odluku zaključka zaključak izmjenama izmjena dopunama dopuna izmjeni "
             "dopuni grada općine gradskog općinskog vijeća području godinu godini godine donošenju davanju")


def stops(unit):
    return stem_set(BASE_STOP + " " + UNITS[unit]["gen"] + " " + UNITS[unit]["name"])


def overlap(title, text, stop):
    """Share of the title's words anywhere in text."""
    t = stem_set(title) - stop
    return len(t & stem_set(text)) / (len(t) or 1)


def prefix_overlap(title, text):
    """Share of the title's words (6-letter stems) that begin a word of the text: tells "predsjednika" from
    "predstavničke" and "većine" from "manjine", which 5-letter stems do not (Opatija 1., item 3)."""
    stop6 = {w[:6] for w in re.findall(r"\w+", BASE_STOP.lower())} | {"gradsk", "općins", "vijeća"}
    t = {w[:6] for w in re.findall(r"\w+", title.lower()) if len(w) > 3} - stop6
    tw = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 3]
    return sum(any(x.startswith(s) for x in tw) for s in t) / (len(t) or 1)


def title_score(title, text, stop):
    """Share of the title's words found in the same length of text."""
    t = stem_set(title) - stop
    h = stem_set(text[:max(len(title) + 20, 80)])
    return len(t & h) / (len(t) or 1)


def agenda(m, site_url):
    """Items from the session page: "N. title"; an unnumbered or indented row is a sub-item of the last number."""
    items, last = [], 0
    for r in m["items"]:
        num = re.match(r"(\d{1,3})\s*\.\s*\)?\s*(.*)", r["text"])
        letter = re.match(r"([a-z])\s*[.)]\s*(.*)", r["text"])
        if num and not (r["indent"] and last and int(num.group(1)) != last and not re.match(r"\d+\s*\.\s*\d", r["text"])):
            # "5. 1. 1. Prijedlog Rješenja ..." (Opatija): a sub-item of 5, its title without the sub-numbers
            no, title = int(num.group(1)), re.sub(r"^(?:\d{1,2}\s*\.\s*)+", "", num.group(2))
        else:
            no, title = (last or len(items) + 1), (letter.group(2) if letter else r["text"])
        last = no
        title = title.strip() or r["text"]
        items.append({"no": no, "title": title, "full_title": r["text"], "proposer": r["presenter"],
                      "status": None, "url": site_url,
                      "attachments": [{"name": d["name"], "url": d["url"]} for d in r.get("docs", []) if d["kind"] == "doc"]})
    return items


ENDINGS = ("ega", "oga", "ima", "ama", "om", "em", "og", "eg", "ih", "a", "e", "i", "u", "o")


def norm(w):
    """Drop one case ending: "izvještaja" = "izvještaj", "godišnjeg" = "godišnji", but "mrtvozornika" stays
    apart from "mrtvozornice"."""
    for suf in ENDINGS:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def words(t):
    return {norm(w) for w in re.findall(r"\w+", t.lower()) if len(w) > 2}


DECISION_STOP = words("prijedlog prijedloga usvojena usvojeni usvojeno odluka odluke odluku zaključak zaključka "
                      "rješenje rješenja godinu godini godine grada općine području")


def attach_decisions(items, decisions, stop):
    """Adopted acts ("Odluke" tab) go to the item whose title they name, on whole words ("mrtvozornika" is not
    "mrtvozornice", Makarska 7.). A leading "13 " without a dot is the agenda number (Čavle); "1. ODLUKA ..."
    numbers follow the acts, not the agenda (Ogulin's item 1 is the question hour), so they only break ties.
    The best item must beat the runner-up clearly; otherwise the act goes to other_decisions."""
    left = []
    for d in decisions:
        lead = re.match(r"\s*(\d{1,3})(\.)?\s+", d["name"])
        name = d["name"][lead.end():] if lead else d["name"]
        def content(t):  # whole words, without the unit's name ("Novi Vinodolski") or years
            return {w for w in words(t) - DECISION_STOP if not w.isdigit() and w[:5] not in stop}
        dw = content(name)

        def score(it):
            tw = content(it["title"])
            return 2 * len(dw & tw) / ((len(dw) + len(tw)) or 1)
        cands = items
        if lead and not lead.group(2) and any(it["no"] == int(lead.group(1)) for it in items):
            cands = [it for it in items if it["no"] == int(lead.group(1))]
        ranked = sorted(cands, key=lambda it: (score(it) + (0.05 if lead and it["no"] == int(lead.group(1)) else 0)),
                        reverse=True)
        best = ranked[0] if ranked else None
        second = score(ranked[1]) if len(ranked) > 1 else 0
        numbered = cands is not items
        if best is not None and (numbered and (len(ranked) == 1 or score(best) - second >= 0.1 or score(best) >= 0.5)
                                 or score(best) >= 0.5 and score(best) - second >= 0.1):
            if d["url"] not in {a["url"] for a in best["attachments"]}:
                best["attachments"].append({"name": d["name"], "url": d["url"]})
            best["decision"] = True
        else:
            left.append(d)
    return left


# ---------------------------------------------------------------------------------------------- minutes

COUNCIL_MIN = re.compile(r"zapisnik", re.I)
NOT_COUNCIL = re.compile(r"odbor|\bMO\b|\bVMO\b|mjesn|savjet|komisij|povjerenstv|mladih|SMGK|izvad|video|tonsk|poglavarstv|pregled\w* i ocje|natječaj|ponud|"
                         r"audio|kolegij|stožer|skupštin|poziv", re.I)


def minutes_number(name, text):
    """Which council session a minutes file records ("Zapisnik sa 9. sjednice ...", "ZAPISNIK s konstituirajuće ...")."""
    head = flat(text[:2500])
    head = re.sub(r"(?<=\b[A-ZČĆŠŽĐ]) (?=[A-ZČĆŠŽĐ]\b)", "", head)  # "Z A P I S N I K"
    if text and not re.search(r"vijeć|VIJEĆ", head):
        return None  # not council minutes
    for s in (name, head):
        m = re.search(r"(\d{1,3})\s*\.\s*(?:\(?\s*\w+\s*\)?\s+)?(?:\w+\s+)?sjednic", s, re.I)
        if m and (s is name or re.search(r"zapisnik", s[:m.end() + 10][-200:], re.I)):
            return int(m.group(1))
        if re.search(r"konstituiraju", s[:400], re.I):
            return "konst"
    return None


NUMW = {"nula": 0, "nijedan": 0, "jedan": 1, "jednim": 1, "jednog": 1, "jedna": 1, "jednom": 1, "dva": 2, "dvije": 2,
        "dvama": 2, "tri": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10,
        "jedanaest": 11, "dvanaest": 12, "trinaest": 13, "četrnaest": 14, "petnaest": 15, "šesnaest": 16,
        "sedamnaest": 17, "osamnaest": 18, "devetnaest": 19, "dvadeset": 20, "dvadeset jedan": 21}
# digits may follow a letter ("S13 glasova", OCR); number words need a word boundary
NUM = r"(?:(?<!\d)(\d{1,2})|\b(" + "|".join(sorted(NUMW, key=len, reverse=True)) + r")\b)"
Q = r'\s*"{0,2}\s*'  # „ZA“ / "ZA"
COPULA = r"(?:\s+(?:je|su)\s+bi(?:o|la|lo|li|le))?"  # "1 je bio „PROTIV“", "4 su bila SUZDRŽANA"
KIND = {"za": r"(?:ZA|[Zz]a)\b", "protiv": r"(?:PROTIV|[Pp]rotiv)\b", "suzdrzano": r"(?:S?UZDRŽ|[Ss]?uzdrž)\w*"}


UPPER = {"za": r"ZA\b", "protiv": r"PROTIV\b", "suzdrzano": r"S?UZDRŽ\w*"}


def count_res(k):
    """Count patterns for one kind. Upper case may follow OCR's comma-quotes (,ZA" / ,,ZA"); lower case only
    a real quote or nothing, so "13 vijećnika, za koje ..." is not a vote."""
    w, up = KIND[k], UPPER[k]
    up = rf'(?:{up}|,{{1,2}}\s*{up}\s*")'  # OCR's ,ZA" / ,,ZA" (a closing quote, unlike "11 glasova, PROTIV")
    return [
        re.compile(rf"{NUM}\s*\)?\s*\(?{COPULA}\s*(?:glas\w*|vijećni\w*)(?:\s+(?:je|su))?\s*\)?\s*\(?{Q}{up}"),  # 9 glasova "ZA"
        re.compile(rf"{NUM}\s*\)?\s*\(?{COPULA}\s*glas\w*\s*\(?\s*[\"']{{0,2}}\s*{w}"),                    # 13 glasova za
        re.compile(rf"{NUM}\.?{COPULA}\s*\(?\s*(?:\"{{0,2}}\s*{up}|[\"']{{1,2}}\s*{w})"),  # 9 „ZA“, (15. ZA), 1 je bio „PROTIV“
        # 10 ZA / 2 PROTIV / 6 suzdržanih; a lower-case "za" only inside a list ("(9 za, 6 suzdržanih)")
        re.compile(rf"{NUM}{COPULA}\s+ZA\b|{NUM}\s+za(?=\s*[,);]|\s+i\s+\d)" if k == "za" else rf"{NUM}{COPULA}\s+{w}"),
        re.compile(rf"\"?\s*{w}\s*\"?\s*(?:je\s+)?glas(?:ovalo|ovao|ovala|ovali|alo|ao)\s+(?:je\s+)?{NUM}"),  # „ZA“ je glasovalo 12
        re.compile(rf"\b{up}\s*\"?\s*:\s*{NUM}\b"),                                                     # ZA: 12 (not "i to za: 1.")
        # last on purpose (find_votes prefers it): ZA – 11 glasova, ZA -4- glasa, SUZDRŽANO – 0 glasova (Ogulin)
        # (OCR may lose the Z: "A -15- glasova", Ogulin 1.)
        re.compile(rf"(?:\b{UPPER[k]}\w*|(?<![\w-])A)\s*[–—-]+\s*-?{NUM}\s*-?\s*(?i:glas)" if k == "za" else
                   rf"\b{UPPER[k]}\w*\s*[–—-]+\s*-?{NUM}\s*-?\s*(?i:glas)"),
    ]


COUNTS = {k: count_res(k) for k in KIND}
NOBODY = {"protiv": re.compile(r"nitko\s+(?:nije\s+)?(?:bio\s+)?(?:glasova\w*\s+)?\"?\s*protiv", re.I),
          "suzdrzano": re.compile(r"nitko\s+(?:se\s+)?(?:nije\s+)?(?:bio\s+)?\"?\s*s?uzdrža", re.I)}
ANCHOR = re.compile(r"jednoglasn\w*|JEDNOGLASN\w*|Jednoglasn\w*|većinom\s+glasova|VEĆINOM\s+GLASOVA|" +
                    "|".join(r.pattern for r in COUNTS["za"]) + "|" +
                    "|".join(r.pattern for r in COUNTS["protiv"][:3]) + r"|GLASANJE\s*:|GLASOVANJE\s*:")
OUTCOME = re.compile(r"(?i:ni(?:je|su)\s+(?:\w+\s+){0,2}?(?:usvoj\w*|prihvać\w*|donesen\w*|izabran\w*|imenovan\w*|"
                     r"dobi\w*\s+potrebn\w*|prošao|prošla)|odbij\w*|odbil\w*|odbio|odbačen\w*|"
                     r"usvoj\w*|donesen\w*|donijel\w*|donosi|utvrdil[aoi]\b|odobril\w*|odobren\w*|prihvać\w*|prihvatil\w*|prihvaća|izabran\w*|izabral\w*|"
                     r"imenovan\w*|daje\s+(?:se\s+)?suglasnost|dal[oi]\s+suglasnost|primljen\w*\s+na\s+znanje|"
                     r"prim[ai]\w*\s+(?:se\s+)?na\s+znanje)")
ACT_AFTER = re.compile(r"[\s)\"]{0,6}\s*(?:\d{1,3}\s+)?(?:ODLUK[AU]|RJEŠENJ[EA]|ZAKLJUČAK|PROGRAM|PLAN|PRAVILNIK|"
                       r"POSLOVNIK|STATUT|IZMJENE|GODIŠNJI|POLUGODIŠNJI|PRORAČUN)\b")
PROCEDURAL = re.compile(r"\b(?:dnevn\w*\s+red|objedinj\w*|zajedničk\w*\s+raspr|hitn\w*\s+postup|stank[aeiu]\b|"
                        r"aktualn\w*\s+sat\w*\s+produž|produž\w*\s+aktualn|"
                        # motions: "nije usvojen prijedlog da izvjestitelj mora podnijeti uvodno izlaganje" (Opatija 2.),
                        # "prijedlog vijećnika ... da li su suglasni"
                        r"prijedlo[gz]\w*\s+(?:\w+\s+){0,4}?da\b|da\s+li\s+su\s+suglasni|uvodn\w*\s+izlaganj)", re.I)
QUOTES = str.maketrans({c: '"' for c in "„“”«»‟″"})
PRESENT = re.compile(r"(?:nazočn\w*|prisutn\w*)\s+(?:je\s+|su\s+)?(?:\w+\s+){0,2}?(\d{1,2})\s+(?:od\s+(?:ukupno\s+)?\d+\s+)?"
                     r"(?:vijećni|član)|(\d{1,2})\s+(?:vijećnika|članova)\s+(?:je\s+|su\s+)?(?:nazočn|prisutn)", re.I)


def num(w):
    return int(w) if w.isdigit() else NUMW[w.lower()]


def text_for_parse(text):
    """Quotes unified (same length: positions stay valid); ",," used as an opening quote too."""
    return text.replace(",,", '""').translate(QUOTES)


HEAD_EXPL = re.compile(r"^[ \t•\-]*(?:(?:AD|Ad|ad)\.?|TOČK[AEU]|Točk[aeu]|TOCKA|Tocka)\s*[-–—:.]?\s*(\d{1,2})\s*\.?\s*\)?\s*[.:\-–]?",
                       re.M)
HEAD_BARE = re.compile(r"^[ \t]*(\d{1,2})\s*\.\s*\)?[ \t]*(?=[A-ZČĆŠŽĐ„\"])", re.M)
# what an agenda title starts with (an "AD 6." followed by "Konstatirajući da je ..." has no title of its own)
TITLE_START = re.compile(r"\s*(?:Prijedlog|PRIJEDLOG|Izvješć|IZVJEŠĆ|Izvješt|IZVJEŠT|Izvjest|Odluk|ODLUK|Zaključ|ZAKLJUČ|Izbor|IZBOR|"
                         r"Program|PROGRAM|Plan|PLAN|Informacij|INFORMACIJ|Godišnj|GODIŠNJ|Polugodišnj|POLUGODIŠNJ|Analiz|"
                         r"ANALIZ|Rješenj|RJEŠENJ|Pravilnik|PRAVILNIK|Strategij|STRATEGIJ|Statut|STATUT|Davanj|DAVANJ|"
                         r"Usvajanj|USVAJANJ|Vijećni|VIJEĆNI|Aktualn|AKTUALN|Imenovanj|IMENOVANJ|Razrješenj|RAZRJEŠENJ|"
                         r"Utvrđivanj|UTVRĐIVANJ|Proračun|PRORAČUN|Izmjen|IZMJEN|Donošenj|DONOŠENJ|Prethodn|Suglasnost|"
                         r"[IVX]+\.\s|[A-ZČĆŠŽĐ]{4,}\s+[A-ZČĆŠŽĐ]{2,})")


def headings(text, items, stop):
    """[(pos, end, item or None, label, number)] for the item sections of the minutes, matched by title.
    "AD N." / "Točka N." headings, plus bare "N. PRIJEDLOG ..." lines (Senj, Ogulin). A section whose title
    matches no portal item stays in the list with item None: it is a boundary, so its votes are logged as
    unmatched instead of falling onto the item before it (Senj 11.: "10. ... RASPISIVANJU JAVNOG NATJEČAJA").
    Beside explicit headings a bare line only counts if its number and title agree (lists inside the text,
    "1. Nagrada Grada Opatije ...", must not take the votes that follow)."""
    expl = list(HEAD_EXPL.finditer(text))

    def window(m):
        return flat(text[m.end():m.end() + 500])

    def line(m):
        nl = text.find("\n", m.end())
        return text[m.end():nl if nl >= 0 else len(text)].strip()

    def title_like(s):  # "PRIJEDLOG ZAKLJUČKA O ...": an upper-case section title, not prose or the minutes' title
        letters = re.findall(r"[A-Za-zČĆŠŽĐčćšžđ]", s)
        upper = sum(c.isupper() for c in letters)
        return (len(letters) >= 15 and upper >= 0.8 * len(letters) and TITLE_START.match(s) is not None
                and not re.search(r"SJEDNIC|ZAPISNIK|DNEVNI RED", s))

    bare_all = list(HEAD_BARE.finditer(text))
    best_score = [max((title_score(it["title"], window(m), stop) for it in items), default=0) for m in bare_all]
    bare = [(m, sc) for m, sc in zip(bare_all, best_score) if sc >= 0.6 or title_like(line(m))]
    # bare lines match each item twice (agenda list + section): explicit headings win unless they are only a
    # stray "• Točka 2." in the agenda list (Senj 11.)
    use_expl = len(expl) >= 2 and len(expl) >= 0.5 * sum(sc >= 0.6 for _, sc in bare) / 2
    # bare lines a few lines apart are the agenda list at the top, not sections: a vote after the list's last
    # line (the previous minutes, Ogulin 5.) must not land on that item
    starts = [m.start() for m, _ in bare]
    named = [(max(items, key=lambda it: title_score(it["title"], window(m), stop))["no"] if sc >= 0.6 and items
              else ("?", m.start())) for m, sc in bare]
    keep = []
    for i, (m, sc) in enumerate(bare):
        nxt_close = i + 1 < len(starts) and starts[i + 1] - m.start() < 300
        prev_close = i and m.start() - starts[i - 1] < 300
        if nxt_close or (prev_close and named[i] not in named[:i]):
            continue  # an agenda-list line; the first section right after the list repeats an item: kept
        keep.append((m, sc))
    found = ([(m, True) for m in expl] if use_expl else []) + [(m, False) for m, _ in keep]
    found.sort(key=lambda x: x[0].start())
    out = []
    for m, explicit in found:
        n = int(m.group(1))
        same_line = line(m)
        win = window(m)
        scored = sorted(((title_score(it["title"], win, stop), -abs(it["no"] - n), id(it), it) for it in items),
                        key=lambda x: x[:3], reverse=True)
        best = scored[0] if scored else None
        numbered = [it for it in items if it["no"] == n]
        it = None
        untitled = explicit and numbered and (re.match(r"[A-ZČĆŠŽĐ]{2,}(?:\s+[A-ZČĆŠŽĐ-]{2,}){1,3}\s*,", same_line) or
                                              not TITLE_START.match(same_line) and len(same_line) > 15)
        if untitled:
            it = numbered[0]  # "AD 3. MARINKO HERMAN, predsjednik ...": a speaker, not a title -> the number
        elif best and best[0] >= 0.6:
            it = best[3]
            # the number's own item wins a near tie ("Izvješće o radu ..." items differ in one word)
            if numbered and numbered[0] is not it and title_score(numbered[0]["title"], win, stop) >= best[0] - 0.05:
                it = numbered[0]
        if not explicit:
            if it is not None and use_expl and it["no"] != n:
                continue  # beside explicit headings (Senj 6.) a bare line counts only if number and title agree
            if it is None and use_expl:
                continue
        elif it is None and numbered and (not TITLE_START.match(same_line) or not re.search(r"[A-Za-zČĆŠŽĐčćšžđ]{3}", same_line)
                                          or title_score(numbered[0]["title"], win, stop) >= 0.4):
            it = numbered[0]  # "AD 3." with the title elsewhere ("Ad. 6. Konstatirajući da je ..."): the number
        out.append((m.start(), m.end(), it, flat(f"{m.group(0)} {same_line}")[:120], n))
    return out


# a new vote starts after an outcome verb, a call to vote or a heading between two count phrases
VOTE_BREAK = re.compile(r"na\s+glas(?:ovanj|anj)\w*|GLASANJE\s*:|GLASOVANJE\s*:|\n\s*(?:AD|Ad|TOČK|Točk)\b", re.I)
SENTENCE_BREAK = re.compile(r"(?<![\s(:]\d)(?<![\s(:]\d\d)\.\s+(?=[A-ZČĆŠŽĐ])|\n[ \t]*\n")  # not after "1." in a list
# the sentence before refers to a procedural motion ("predložio je objedinjavanje ... Vijeće je to jednoglasno
# prihvatilo", Senj 10./11.)
PROC_PREV = re.compile(r"objedin\w*|zajedničk\w*\s+raspr|\bstank[aeiu]\b|uvodn\w*\s+izlaganj|predlož\w*\s+(?:je\s+)?da\s+se|"
                       r"dnevn\w*\s+red", re.I)
PROC_STRONG = re.compile(r"objedin\w*|sljedeć\w*\s+dopun\w*|prihvati\w*\s+prijedlog\s+(?:predsjedni|vijećni|kluba)\w*|zajedničk\w*\s+raspr|\bstank[aeiu]\b|uvodn\w*\s+izlaganj|"
                         r"prijedlo[gz]\w*\s+(?:\w+\s+){0,4}?da\b|da\s+li\s+su\s+(?:vijećnici\s+)?suglasni", re.I)
ANAPHORIC = re.compile(r"navedeni\s+prijedlog|taj\s+prijedlog|\bto\s+(?:je\w*\s+)?jednoglasno|što\s+je\s+(?:Gradsko\s+|Općinsko\s+)?"
                       r"[Vv]ijeće|navedeno\b|prihvatil\w*\s+prijedlog\b(?!\s+\w*\s*(?:odluk|zaključ|program|plan|rješenj))")
# a vote retold in a councillor's speech ("... za koji je vijećnik naveo ..., što je jednoglasno prihvaćeno")
SPEECH = re.compile(r"\b(?:naveo|navela|rekao|rekla|smatra|podsjetio|podsjetila|pojasnio|pojasnila|istaknuo|istaknula|"
                    r"kazao|kazala|tvrdi)\b")


def find_votes(text):
    """Every vote: counts, result, the text quoted, positions (outcome verb and the act named after it)."""
    q = text_for_parse(text)
    anchors = sorted(ANCHOR.finditer(q), key=lambda m: m.start())

    def is_za(a):
        return any(r.match(q, a.start()) and r.match(q, a.start()).end() == a.end() for r in COUNTS["za"])
    groups = []
    for a in anchors:
        if groups:
            gap = q[groups[-1][-1].end():a.start()]
            split = (len(gap) >= 400 or VOTE_BREAK.search(gap) or OUTCOME.search(gap)
                     # a new ZA count or "jednoglasno" after a counted vote ("donesena sljedeća rješenja: (13 ZA ...)
                     # RJEŠENJE ... jednoglasno (14 ZA) RJEŠENJE ...", Opatija 3.); a PROTIV after names is not
                     or (is_za(a) and any(is_za(x) for x in groups[-1]) and len(gap) >= 120)
                     # but "jednoglasno" after an act's name (Opatija 3.), not after "ZA – 11 glasova ... utvrđuje
                     # da je Vijeće jednoglasno prihvatilo" (Ogulin: one vote)
                     or (re.match(r"(?i)jednoglas|većinom", a.group(0)) and any(is_za(x) for x in groups[-1])
                         and re.search(r"\b(?:RJEŠENJ|ODLUK|ZAKLJUČ|PROGRAM|PLAN|PRAVILNIK)\w*\b", gap)))
            if not split:  # "S 9 glasova ZA, 4 glasa SUZDRŽAN (four names) i 2 glasa PROTIV (...)" is one vote
                groups[-1].append(a)
                continue
        groups.append([a])
    votes = []
    for gi, g in enumerate(groups):
        s, e = g[0].start(), g[-1].end()
        lo_lim = groups[gi - 1][-1].end() if gi else 0
        hi_lim = groups[gi + 1][0].start() if gi + 1 < len(groups) else len(q)
        o = None
        for reach in (400, 700):  # Opatija 5.: "(8 ZA 5 PROTIV i 1 SUZDRŽAN – s time da se konstatira ...) donesen"
            for cand in OUTCOME.finditer(q, max(lo_lim, s - 160), min(hi_lim, e + reach)):
                # an outcome after the counts must be in the same clause: not past "...2 PROTIV). 4. Marin Luić
                # (prijedlog je usvojen" (the next candidate's, Opatija 3.)
                if cand.start() >= e and re.search(r"\)\s*[.;]|\n[ \t]*\n\s*\d{1,2}\.\s", q[e:cand.start()]):
                    continue
                if o is None or abs(cand.start() - e) < abs(o.start() - e):
                    if cand.start() >= e or cand.end() <= s:
                        o = cand
            if o is not None:
                break
        if o is None or o.start() - e > 400:
            # "jednoglasno (8 ZA) ODLUKA O ..." with the verb left out: the act named right after is the outcome
            rest = re.match(r"(?:\s+|[\d(),.–-]|\bi\b|PROTIV\b|S?UZDRŽ\w*|[Gg]las\w*|\"|ZA\b)*", q[e:e + 120])
            act = ACT_AFTER.match(q, e + rest.end())  # "(12 ZA i 2 SUZDRŽANA) RJEŠENJE o ..."
            if act and not (o is not None and o.start() - act.end() < 40):
                o = act
        if o is not None and votes and votes[-1]["_o"] == o.start() and o.end() <= s:
            # "Zapisnik je jednoglasno usvojen. ZA - 14 glasova, PROTIV - 0 glasova" (Ogulin): the counts after an
            # outcome that the vote before already used belong to that vote
            span2 = q[e - (e - s):min(hi_lim, e + 90)]
            for k in ("za", "protiv", "suzdrzano"):
                hits = list(COUNTS[k][-1].finditer(span2)) or [m for r in COUNTS[k] for m in r.finditer(span2)]
                if votes[-1][k] is None and hits:
                    votes[-1][k] = num(next(x for x in min(hits, key=lambda m: m.start()).groups() if x))
            votes[-1]["end"] = max(votes[-1]["end"], e)
            continue
        no_outcome = False
        if o is None:
            # "Predsjednik ... utvrđuje da je s 11 glasova ZA i 3 glasa SUZDRŽAN Prijedlog Dopune ..." (Viškovo 8.):
            # an announced count without its verb; kept only with a ZA count and an announcing verb before it
            if (not any(is_za(a) for a in g) or not re.search(r"utvrđuje|konstatira|objavi\w*", q[max(lo_lim, s - 200):s])
                    or not re.match(r"[\s\"),.]*(?:Prijedlog|PRIJEDLOG|Odluk|ODLUK|Program|PROGRAM|Plan\b|PLAN\b|Izvješ|"
                                    r"IZVJEŠ|Zaključ|ZAKLJUČ|Pravilnik|PRAVILNIK)",
                                 re.sub(r"\b(?:i\s+)?\d+\s+glas\w*\s*\"?\s*(?:PROTIV|S?UZDRŽ\w*)\"?", " ", q[e:e + 120]))):
                continue
            o = re.compile(r"").match(q, e)  # zero-width at the end of the counts
            no_outcome = True
        lo, hi = min(s, o.start()), max(e, o.end())
        if o.start() >= e:
            lo = max(lo_lim, s - 40)
        span = q[lo:min(hi_lim, max(hi, e + 90))]
        # cut the count span at the next heading / sentence so "... usvojen. AD 2. ... 3 glasa PROTIV" stays out
        off = (o.end() - lo) if o.start() >= e else (e - lo)
        cut = re.search(r"\n\s*(?:AD|Ad|TOČK|Točk)\b|GLASANJE|\.\s+(?=[A-ZČĆŠŽĐ][a-zčćšžđ]+\s)", span[off:])
        if cut:
            span = span[:off + cut.start()]
        v = {}
        for k in ("za", "protiv", "suzdrzano"):
            # "ZA – 14 glasova" is unambiguous and wins over a page number before it ("3 ZA – 14 glasova")
            hits = list(COUNTS[k][-1].finditer(span)) or [m for r in COUNTS[k] for m in r.finditer(span)]
            v[k] = num(next(x for x in min(hits, key=lambda m: m.start()).groups() if x)) if hits else None
            if v[k] is None and NOBODY.get(k) and NOBODY[k].search(span):
                v[k] = 0
        unanimous = bool(re.search(r"jednoglasn", span, re.I))
        sentence = flat(text[lo:max(hi, o.end()) + 1])
        neg = re.match(r"(?i)ni(?:je|su)|odbij|odbil|odbio|odbač", o.group(0))
        result = NO if neg else YES
        if v["za"] is not None and v["protiv"] is not None and v["protiv"] > v["za"]:
            result = NO
        if no_outcome:
            result = YES if v["za"] > (v["protiv"] or 0) + (v["suzdrzano"] or 0) else NO
        before_outcome = flat(q[lo:o.end()])
        prev_end = votes[-1]["end"] if votes else 0
        lead = flat(q[max(prev_end, lo - 150):o.end()])
        # the sentence the vote is in, and the one before it
        brk = [m.end() for m in SENTENCE_BREAK.finditer(q, max(lo_lim, lo - 600), lo)]
        sent_start = brk[-1] if brk else max(lo_lim, lo - 600)
        prev_brk = [b for b in brk if b < sent_start - 2]
        prev_sent = flat(q[prev_brk[-1] if prev_brk else max(lo_lim, sent_start - 400):sent_start])
        sent = flat(q[sent_start:o.end()])
        after = q[o.end():o.end() + 160]
        nxt = re.search(r"\n\s*\n|\n\s*(?:AD|Ad|TOČK|Točk)\b", after)
        tail = after[:nxt.start()] if nxt else after
        # amendment or the act itself: the paragraph says what was put to the vote ("stavio na glasanje Prijedlog
        # Poslovnika uključivo podnesene amandmane ..." is the act; "1. Amandman broj 3. ... nije usvojen" is not;
        # nor is "... nije usvojen Amandman broj 3")
        blanks = [m.end() for m in re.finditer(r"\n[ \t]*\n", q[max(0, lo - 3000):lo])]
        para_start = max(max(0, lo - 3000) + blanks[-1] if blanks else 0, prev_end if prev_end < lo else 0)
        para = flat(q[para_start:o.end()])
        put = list(re.finditer(r"na\s+glas(?:ovanj|anj)\w*", para, re.I))
        if re.match(r"\s*(?:\w+\s+){0,2}amandman", tail, re.I):
            amendment = True
        elif put:
            ctx = para[max(0, put[-1].start() - 60):put[-1].end() + 40]
            amendment = bool(re.search(r"amandman", ctx, re.I)) and not re.search(
                r"uključiv|(?:s|sa|uz)\s+(?:\w+\s+){0,2}amandman|amandmanima|amandmanom", ctx, re.I)
        else:
            amendment = bool(re.match(r"\s*(?:\d{1,2}\s*[.)]\s*)?amandman", para, re.I)) or (
                bool(re.search(r"amandman", lead, re.I)) and not re.search(
                    r"(?:s|sa|uz)\s+(?:\w+\s+){0,2}amandman|amandmanima|amandmanom|uključiv\w*\s+(?:\w+\s+)?amandman",
                    lead, re.I))
        # a parenthesised aside ("(8 ZA ... – s time da se konstatira da je prije glasanja o točki 9. dnevnog
        # reda ...)", Opatija 5.) is not what was voted on
        procedural = bool(PROCEDURAL.search(re.sub(r"\([^)]{0,600}\)", " ", before_outcome) + " " + tail))
        if PROC_STRONG.search(re.sub(r"\([^)]{0,600}\)", " ", sent) + " " + q[o.start():o.end() + 60]):
            procedural = True  # "Prijedlog o objedinjavanju rasprave prihvaćen je jednoglasno" (Senj 10.)
        if ANAPHORIC.search(sent) and PROC_PREV.search(prev_sent + " " + sent):
            procedural = True  # "predložio je objedinjavanje ... Vijeće je to jednoglasno prihvatilo"
        # a committee's opinion quoted in the minutes ("razmotrili i podržali: 1. Odbor za ... jednoglasno
        # (ZA -4- ...)"): "podrža..." in the sentence with no call to the council's vote after it
        pod = [m.end() for m in re.finditer(r"podrža\w*", sent)]
        committee = bool(pod) and re.search(r"Odbor", sent) is not None and not re.search(
            r"na\s+glas(?:ovanj|anj)", sent[pod[-1]:], re.I)
        speech = bool(SPEECH.search(sent)) and not re.search(r"utvrđuje|konstatira|objavio|objavila|GLASANJE", sent)
        minutes_vote = bool(re.search(r"zapisni[kc]\w*\s+(?:(?:s|sa|od)\s+)?(?:\d{1,2}\s*\.|[IVX]+\.|prethodne|konstitui)",
                                      lead + " " + tail[:120], re.I))
        klasa = re.search(r"KLASA\s*[:;]?\s*([\d/-]+)", q[o.end():min(hi_lim, o.end() + 400)])
        # where the act's name starts: right after the counts when it follows them ("(12 ZA i 2 SUZDRŽANA)
        # RJEŠENJE o razrješenju i imenovanju ..." -- "imenovanju" is no outcome verb here), else after the verb
        rest = re.match(r"(?:\s+|[\d(),.–-]|\bi\b|PROTIV\b|S?UZDRŽ\w*|[Gg]las\w*|\"|ZA\b)*", q[e:e + 120])
        act_here = ACT_AFTER.match(q, e + rest.end())
        act_from = act_here.start() if act_here else max(o.end(), e)
        votes.append({"pos": s, "end": max(hi, o.end()), "o_start": min(o.start(), s), "o_end": act_from, **v,
                      "unanimous": unanimous, "result": result, "amendment": amendment,
                      "procedural": procedural or committee or speech, "kind": "committee" if committee else
                      "speech" if speech else "procedural" if procedural else "vote", "minutes_vote": minutes_vote,
                      "no_outcome": no_outcome, "_o": o.start(), "klasa": klasa.group(1) if klasa else None,
                      "next": hi_lim, "repeat": bool(re.search(r"ponov\w*\s+glas|ponovljen\w*", sent, re.I)),
                      "quote": flat(text[lo:min(len(text), max(hi, o.end()) + 200)])[:400],
                      "sentence": sentence})
    return votes


def present_before(text, pos, default):
    """Members present at a point: the last "nazočno N vijećnika" / "prisutno N od ukupno 15" before it."""
    hits = [m for m in PRESENT.finditer(text, 0, pos)]
    if hits:
        return int(hits[-1].group(1) or hits[-1].group(2))
    return default


TITLES = re.compile(r"\b(?:dr\.?\s*sc\.|mr\.?\s*sc\.|dr\.\s*med\.|prof\.|dipl\.\s*\w+\.?|mag\.\s*\w+\.?|univ\.\s*\w+\.?)\s*", re.I)


def person(n):
    n = TITLES.sub("", re.sub(r"\b\d+\b|\(.*?\)", "", n))
    n = re.sub(r"\s+[–—-]\s+.*$", "", flat(n))  # "Marinko Herman – predsjednik Gradskog vijeća"
    n = re.sub(r"^(?:vijećni\w*|gosp\w*|g\.|gđa\.?)\s+", "", n.strip(" ,.;:-–"), flags=re.I)
    return n if re.fullmatch(r"[A-ZČĆŠŽĐ][\w'’-]+(?:\s+[A-ZČĆŠŽĐ][\w'’-]+){1,3}", n) else None


def attendance(text):
    """Present / absent councillors by name, when the minutes list them."""
    f = TITLES.sub("", flat(text[:12000]))
    pres = re.search(r"(?:Prisutni|Nazočni)\s+(?:su\s+)?(?:vijećnici|članovi(?:\s+vijeća)?)\s*:\s*(.*?)(?:\.\s|\s(?:Odsutn|Nisu\s+nazoč|"
                     r"Nije\s+nazoč|Opravdano|Osim\s+vijeć|Ostali|Nazočn\w*\s+(?:dužnos|od|su)|Gradonačelni|Općinsk\w*\s+načeln))", f, re.I) or \
        re.search(r"Sjednici\s+su\s+(?:prisutni|nazočni)\s+vijećnici\s*:?\s*(.*?)\.\s", f)
    absent = re.search(r"(?:Odsutni\s+(?:vijećnici|članovi)|Nisu\s+nazočni(?:\s+vijećnici)?|Sjednici\s+nisu\s+nazočni\s+"
                       r"(?:vijećnici|vijećnice|članovi)?|Opravdano\s+odsutn\w*(?:\s+vijećni\w*)?|Nije\s+nazoč\w*(?:\s+vijećni\w*)?)"
                       r"\s*:?\s*(.*?)(?:\.\s|\s(?:Gradonačelni|Općinsk\w*\s+načeln|Ostali|Osim|Sjednici|Upravni|Nazoč|Prisutn))", f)
    names = lambda s: [p for p in (person(x) for x in re.split(r",|;|\s+i\s+|\s+te\s+", s or "")) if p]
    out = [{"name": n, "present": True} for n in names(pres and pres.group(1))]
    seen = {a["name"] for a in out}
    out += [{"name": n, "present": False} for n in names(absent and absent.group(1)) if n not in seen]
    return out


def council_size(text):
    """Members of the council, only when the minutes state it ("od ukupno 15 vijećnika")."""
    m = [int(x) for x in re.findall(r"od\s+(?:ukupno\s+)?(\d{1,2})\s+(?:vijećnik|član)", text)]
    return max(m) if m else None


MISSING = {"za": "Zapisnik ne navodi broj glasova ZA.", "protiv": "Zapisnik ne navodi broj glasova PROTIV.",
           "suzdrzano": "Zapisnik ne navodi broj SUZDRŽANIH glasova."}


def vote_record(v, size):
    """The stored vote for one minutes vote, following the conventions:
    - "jednoglasno" without a number: za null, protiv = suzdrzano = 0, a note; never inferred from attendance;
    - only ZA given: protiv = suzdrzano = 0 and the "... nisu navedeni (upisano 0)." note, unless ZA equals the
      members present stated in the minutes (then the zeros are implied and there is no note);
    - other partial counts: a missing kind is null with a note naming it, unless the given counts add up to
      the members present stated in the minutes, or the minutes say "nitko protiv" (0 already);
    - a count above the stated council size ("jednoglasno (43 ZA)" of 15): null, with a note quoting it."""
    za, pr, su = v["za"], v["protiv"], v["suzdrzano"]
    present = v.get("present")
    notes = []
    if v["unanimous"] and za is None and pr is None and su is None:
        pr = su = 0
        notes.append("Zapisnik navodi da je odluka donesena jednoglasno, bez broja glasova.")
    elif v["unanimous"]:
        # "jednoglasno (12 ZA)": the other kinds are 0; "jednoglasno ... (9 glasova PROTIV) odbilo": ZA is 0
        if za is None and v["result"] == NO:
            za = 0
        pr, su = (0 if pr is None else pr), (0 if su is None else su)
        if za is None:
            notes.append(MISSING["za"])
    elif za is not None and pr is None and su is None:
        pr = su = 0
        if present is None or za != present:
            notes.append("Zapisnik navodi samo broj glasova ZA; protiv i suzdržani nisu navedeni (upisano 0).")
    elif za is None and pr is None and su is None:
        notes.append("Zapisnik navodi samo da je prijedlog prihvaćen većinom glasova; broj glasova nije naveden."
                     if v["result"] == YES else "Zapisnik ne navodi broj glasova.")
    else:
        given = sum(x for x in (za, pr, su) if x is not None)
        implied = present is not None and given == present
        vals = {"za": za, "protiv": pr, "suzdrzano": su}
        for k in ("za", "protiv", "suzdrzano"):
            if vals[k] is None:
                if implied and k != "za":
                    vals[k] = 0
                else:
                    notes.append(MISSING[k])
        za, pr, su = vals["za"], vals["protiv"], vals["suzdrzano"]
    if size and za is not None and za > size + 5:
        notes.append(f"Zapisnik navodi „{za} ZA“, više od broja članova vijeća ({size}); broj glasova ZA nije upisan.")
        za = None
    if v.get("no_outcome"):
        notes.append("Zapisnik ne navodi ishod glasovanja; ishod je upisan prema broju glasova.")
    rec = {"za": za, "protiv": pr, "suzdrzano": su, "result": v["result"], "members": {},
           "unanimous": v["unanimous"], "quote": v["quote"]}
    return rec, notes


def parse_minutes(text, items, stop, log=None):
    """Attach the minutes' votes to the items. Returns (attendance, stats)."""
    heads = headings(text, items, stop)
    votes = find_votes(text)
    att = attendance(text)
    size = council_size(text)
    stats = {"votes": len(votes), "item_votes": 0, "before_first_heading": 0, "procedural": 0, "amendment": 0,
             "unmatched_heading": [], "headings": len(heads), "no_outcome": []}
    for v in votes:
        prev = [h for h in heads if h[0] < v["pos"]]
        if v["procedural"]:
            stats["procedural"] += 1
            continue
        if not prev:
            stats["before_first_heading"] += 1
            continue
        if v["amendment"]:
            stats["amendment"] += 1
        it, n = prev[-1][2], prev[-1][4]
        if v["minutes_vote"] and not (it and re.search(r"zapisni", it["title"], re.I)):
            stats["before_first_heading"] += 1  # adopting the previous minutes, after the agenda list
            continue
        group = [x for x in items if x["no"] == it["no"]] if it is not None else []
        if it is None and n is not None:
            # an unmatched section: a "2.2." just before the vote may still name a portal sub-item
            group = [x for x in items if x["no"] == n]
        nxt_head = min([h[0] for h in heads if h[0] > v["pos"]] + [len(text)])
        # the act the vote is about: the words before the outcome verb, and the act named right after it
        # ("... donesena ODLUKA O ..."), never the next sentence or vote
        act_end = min(v["o_end"] + 450, v["next"], nxt_head)
        after_act = flat(text[v["o_end"]:act_end])
        raw = text[v["o_end"]:act_end]
        # skip what is left of the counts and a page number: " i 1 SUZDRŽAN)  17  RJEŠENJE o izboru ..."
        raw = re.sub(r"^(?:\s+|[\d(),.–-]|\bi\b|ZA\b|PROTIV\b|S?UZDRŽ\w*|[Gg]las\w*|[„“\"«»])+", " ", raw)
        lead_ws = len(raw) - len(raw.lstrip())
        cut = re.search(r"\.\s+(?=[A-ZČĆŠŽĐ][a-zčćšžđ]+\s)|\n[ \t]*\n", raw[lead_ws:])
        if cut and not re.match(r"\s*(?:\d{1,3}\s+)?[A-ZČĆŠŽĐ]{3,}", raw):  # "17 RJEŠENJE ...": the act in capitals
            after_act = flat(raw[:lead_ws + cut.start()])
        act_type = re.match(r"\s*(?:\d+\s+)?(ZAKLJUČ|ODLUK|RJEŠENJ|PROGRAM|PLAN|PRAVILNIK|IZVJEŠ)", after_act.upper())
        near = flat(text[max(0, v["pos"] - 80):v["o_start"]]) + " " + after_act
        chosen = it
        if len(group) > 1:
            g = group[0]["no"]
            subno = re.findall(rf"(?<![\d.]){g}\s*\.\s*(\d{{1,2}})\s*\.", flat(text[max(0, v["pos"] - 60):v["pos"] + 15]))
            by_sub = [x for x in group if re.match(rf"{g}\s*\.\s*{subno[-1]}\s*\.(?!\s*\d)", x["full_title"])] if subno else []
            # real sub-items ("3. 2. Izbor potpredsjednika ... većine") before the generic parent ("3. Izbor
            # predsjednika i potpredsjednika"); the act named after the outcome decides, its type breaks ties
            # ("donesen ZAKLJUČAK o davanju prethodne suglasnosti ..." vs the Opći uvjeti themselves, Opatija 2.)
            subs = [x for x in group if re.match(r"\s*\d+\s*\.\s*\d", x["full_title"])]
            pool = [x for x in subs if overlap(x["title"], near, stop) >= 0.6] or group

            def sub_score(x):
                bonus = 0.3 if act_type and act_type.group(1).lower()[:5] in x["title"].lower() else 0
                return (prefix_overlap(x["title"], after_act) + bonus, overlap(x["title"], near, stop), x is it)
            best = max(pool, key=sub_score)
            if by_sub:  # "2.2. jednoglasno (12 ZA) donesena ODLUKA ...": the sub-item numbered 2.2
                chosen = by_sub[0]
            elif overlap(best["title"], near, stop) >= 0.6:
                chosen = best
        if chosen is None:
            stats["unmatched_heading"].append({"heading": prev[-1][3], "quote": v["quote"][:200]})
            continue
        stats["item_votes"] += 1
        if v["no_outcome"]:
            stats["no_outcome"].append(v["quote"][:160])
        v["present"] = present_before(text, v["pos"], None)
        chosen.setdefault("votes", []).append(v)
        # one vote for several sub-items: "JEDNOGLASNO su usvojene 3.1.) Odluka ... 3.2.) Odluka ..." (Kastav),
        # "su jednoglasno (13 ZA) donesene ODLUKA ... i ODLUKA ..." (Opatija)
        if len(group) > 1 and re.search(r"\bsu\b|usvojene|donesene|doneseni|usvojeni|prihvaćene", v["sentence"]):
            after = flat(text[v["pos"]:min(v["end"] + 1500, nxt_head, v["next"])])
            subs = [x for x in group if re.match(r"\s*\d+\s*\.\s*\d", x["full_title"])]
            for x in (subs or group):
                if x is not chosen and overlap(x["title"], after, stop) >= 0.9 and not x.get("votes"):
                    x.setdefault("votes", []).append(v)
    for it in items:
        vs = it.pop("votes", None)
        if not vs:
            continue
        final = [x for x in vs if not x["amendment"]]
        if not final:
            it["amendments_only"] = len(vs)
            continue
        # a restatement right after a vote, with no new call to vote between ("ZA -15- glasova ... Nakon
        # provedenog glasovanja Gradsko vijeće ... jednoglasno je usvojilo", Ogulin 1.), is the same vote
        q = text_for_parse(text)
        merged = []
        for x in sorted(final, key=lambda x: x["pos"]):
            prev = merged[-1] if merged else None
            if (prev and x["pos"] - prev["end"] < 400 and x["result"] == prev["result"]
                    and (prev["za"] is None) != (x["za"] is None)  # one side only restates, without counts
                    and not VOTE_BREAK.search(q[prev["end"]:x["pos"]])):
                keep = prev if prev["za"] is not None or x["za"] is None else x
                other = x if keep is prev else prev
                merged[-1] = {**keep, **{k: keep[k] if keep[k] is not None else other[k]
                                         for k in ("za", "protiv", "suzdrzano")},
                              "unanimous": keep["unanimous"] or other["unanimous"], "end": max(prev["end"], x["end"])}
            else:
                merged.append(x)
        final = merged
        recs = [vote_record(x, size) for x in final]
        # several votes under one item: a repeat of the same act (same KLASA, or "ponovno glasovanje") keeps the
        # last; separate votes (candidates, several acts) give no single count: the votes are listed instead
        klasas = {x["klasa"] for x in final}
        repeat = len(final) > 1 and (any(x["repeat"] for x in final[1:]) or (len(klasas) == 1 and None not in klasas))
        if len(final) == 1 or repeat:
            rec, notes = recs[-1]
            if repeat:
                notes = notes + [f"O točki se glasovalo {len(final)} puta (ponovljeno glasovanje); prikazano je "
                                 f"zadnje glasovanje."]
        else:
            results = {r["result"] for r, _ in recs}
            rec = {"za": None, "protiv": None, "suzdrzano": None,
                   "result": YES if YES in results else NO, "members": {},
                   "unanimous": all(r["unanimous"] for r, _ in recs), "quote": recs[-1][0]["quote"]}
            notes = [f"Zapisnik bilježi {len(final)} zasebna glasovanja pod ovom točkom (npr. po kandidatima ili "
                     f"aktima), bez zbirnog broja glasova; pojedinačna glasovanja su u popisu votes."]
            it["votes"] = [{k: r[k] for k in ("za", "protiv", "suzdrzano", "result", "quote")} |
                           ({"totals_note": " ".join(n)} if n else {}) for r, n in recs]
        it["vote"] = rec
        if notes:
            it["vote"]["totals_note"] = {"kind": "zapisnik", "text": " ".join(notes), "quote": rec["quote"]}
    return att, stats


# ---------------------------------------------------------------------------------------------- one unit

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman(r):
    vals = [ROMAN[c] for c in r]
    return sum(-v if i + 1 < len(vals) and v < vals[i + 1] else v for i, v in enumerate(vals))


def session_number(title):
    """'11. sjednica ...', 'Poziv za 8. sjednicu ...' (Baška), 'IX. sjednica ...' (Čavle); None for the
    constitutive session without a number (numbered by the caller)."""
    m = re.search(r"(\d{1,3})\s*\.\s*(?:\w+\s+)?sjednic", title, re.I) or re.match(r"\s*(\d{1,3})\s*\.", title)
    if m:
        return int(m.group(1))
    m = re.match(r"\s*([IVXLC]+)\s*\.\s", title)
    if m:
        return roman(m.group(1))
    return None


def collect(key, log):
    u = UNITS[key]
    p = Portal(key, u["host"], "--fresh" in sys.argv)
    stop = stops(key)
    sessions = []
    for mid, tok, title, date in session_list(p, u["mtype"]):
        if not date or date < TERM_START:
            continue
        m = meeting(p, mid, tok)
        for it in m["items"]:
            it["docs"] = item_docs(p, it)
        sessions.append((mid, title, date, m))
    sessions.sort(key=lambda s: (s[2], s[0]))
    # session numbers: from the title; the constitutive session without one is 1, or 0 when the next session
    # is numbered 1 (Omišalj); anything else without a usable number gets the next free one
    nums = [session_number(t) for _, t, _, _ in sessions]
    used, numbered = set(), []
    for (mid, title, date, m), n in zip(sessions, nums):
        if n is None and re.search(r"konstituiraju", title, re.I):
            n = 0 if 1 in nums else 1
        if n is None or n in used:
            n = max(used | {0}) + 1
            log(f"{key}: '{title}' ({date}) has no usable number; stored as session {n}")
        used.add(n)
        numbered.append((n, mid, title, date, m))
    konst = min((n for n, _, t, _, _ in numbered if re.search(r"konstituiraju", t, re.I)), default=None)
    # every council minutes file on any session page or item; the file says which session it records
    minutes, mins_seen = {}, set()
    for n, mid, title, date, m in (numbered if u["tier"] == "A" else []):
        cands = m["documents"] + [d for it in m["items"] for d in it["docs"]]
        for d in cands:
            if d["kind"] != "doc" or not COUNCIL_MIN.search(d["name"]) or NOT_COUNCIL.search(d["name"]):
                continue
            if d["url"] in mins_seen:
                continue
            mins_seen.add(d["url"])
            path = p.file(d["url"], d["ext"])
            text = doc_text(path, d["ext"])
            rec = minutes_number(d["name"], text)
            if rec == "konst":
                rec = konst
            if rec is None:
                log(f"{key}: minutes '{d['name']}' on session {n}: cannot tell which session it records; skipped")
                continue
            if len(flat(text)) < 200:
                log(f"{key}: minutes '{d['name']}' ({d['ext']}) has no text layer; skipped")
                continue
            # a verified copy wins over a draft on the same page (Punat 6.: "Zapisnik 6. sjednice-verificirani")
            rank = (bool(re.search(r"verific|ovjeren|usvojen", d["name"], re.I)), n)
            if rec in minutes and minutes[rec][3] >= rank:
                continue
            minutes[rec] = (d["url"], text, n, rank)
    (p.dir / "docs").mkdir(parents=True, exist_ok=True)
    for f in (p.dir / "docs").glob("session_*.json"):
        f.unlink()
    recordings, summary = [], []
    for n, mid, title, date, m in numbered:
        url = f"{p.base}/#{u['mtype']}/{mid}"
        items = agenda(m, url)
        left = m["decisions"]
        if not items:  # Kostrena: the adopted acts are all there is
            items = [{"no": k, "title": re.sub(r"^\s*\d+\s*[.)]\s*", "", d["name"]), "full_title": d["name"],
                      "proposer": "", "status": "doneseno", "url": url, "from_decisions": True,
                      "attachments": [{"name": d["name"], "url": d["url"]}]} for k, d in enumerate(m["decisions"], 1)]
            left = []
        else:
            left = attach_decisions(items, m["decisions"], stop)
        doc = {"session": n, "title": title, "date": date, "url": url, "minutes_url": None, "minutes_text": None,
               "items": items, "attendance": [], "questions": []}
        stats = None
        if n in minutes and u["tier"] == "A":
            doc["minutes_url"], doc["minutes_text"] = minutes[n][0], minutes[n][1]
            doc["attendance"], stats = parse_minutes(doc["minutes_text"], items, stop)
            for x in stats["no_outcome"]:
                log(f"   no outcome verb, attached by count: {x[:140]}")
            doc["votes_in_minutes"] = stats["votes"]
        for it in items:
            if it.get("vote"):
                it["status"] = "prihvaćen" if it["vote"]["result"] == YES else "nije prihvaćen"
            elif it.pop("decision", False) and not it["status"]:
                it["status"] = "doneseno"  # an adopted act is published for it, no vote count known
            it.pop("decision", None)
        if left:
            doc["other_decisions"] = [{"name": d["name"], "url": d["url"]} for d in left]
        doc["documents"] = [{"name": d["name"], "url": d["url"]} for d in m["documents"] if d["kind"] == "doc"]
        k = 0
        for d in m["documents"] + [d for it in m["items"] for d in it["docs"]]:
            if d["kind"] in ("audio", "video"):
                k += 1
                recordings.append({"id": f"{key}-{n:02d}-{k}", "session": n, "part": k, "date": date, "title": d["name"],
                                   "url": d["url"], "kind": d["kind"]})
        (p.dir / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        summary.append((n, date, len(items), sum(1 for i in items if i.get("vote")), bool(doc["minutes_url"]), stats))
        log(f"{key} session {n} ({date}): {len(items)} items, {sum(1 for i in items if i.get('vote'))} with votes"
            + (f" ({stats['votes']} vote sentences: {stats['item_votes']} on items, {stats['before_first_heading']} "
               f"before the first heading, {stats['procedural']} procedural, {stats['amendment']} amendments, "
               f"{len(stats['unmatched_heading'])} under an unmatched heading; {stats['headings']} headings)"
               if stats else "") + f", minutes {'yes' if doc['minutes_url'] else 'no'}, attendance "
            f"{len(doc['attendance'])}, recordings {k}")
        for x in (stats or {}).get("unmatched_heading", []):
            log(f"   unattached: {x['heading']!r}: {x['quote'][:140]}")
    (p.dir / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    if not (p.dir / "members.json").exists():
        (p.dir / "members.json").write_text("[]")
    latest = max((s for s in summary if s[4]), key=lambda s: s[0], default=None)
    return {"unit": key, "sessions": len(summary), "items": sum(s[2] for s in summary),
            "with_votes": sum(s[3] for s in summary), "minutes": sum(s[4] for s in summary),
            "latest_minutes": latest and f"session {latest[0]} ({latest[1]})", "requests": p.requests}


def main():
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or list(UNITS)
    bad = [k for k in keys if k not in UNITS]
    if bad:
        sys.exit(f"unknown unit(s) {bad}; known: {', '.join(UNITS)}")
    lock, results = threading.Lock(), {}

    def log(msg):
        with lock:
            print(msg, flush=True)

    def run(k):  # one thread per host: the 1 s spacing is per host
        try:
            results[k] = collect(k, log)
        except (Refused, urllib.error.URLError, OSError) as e:
            results[k] = {"unit": k, "skipped": f"{type(e).__name__}: {e}"}
            log(f"{k}: SKIPPED ({type(e).__name__}: {e})")
    threads = [threading.Thread(target=run, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"\n{'unit':16} {'sessions':>8} {'items':>6} {'votes':>6} {'minutes':>7}  latest minutes")
    for k in keys:
        r = results.get(k, {})
        if "skipped" in r:
            print(f"{k:16} skipped: {r['skipped']}")
        else:
            print(f"{k:16} {r['sessions']:>8} {r['items']:>6} {r['with_votes']:>6} {r['minutes']:>7}  {r['latest_minutes']}")


if __name__ == "__main__":
    main()
