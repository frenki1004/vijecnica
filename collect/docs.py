"""Collect the Zagreb City Assembly's session documents (2025-2029 term) from web.zagreb.hr.

Per session N: agenda items (title, proposer, status, attachments), roll-call vote PDFs,
councillors' questions + answers (aktualni sat), attendance, minutes PDF.
HTML is cached in data/raw/web/, PDFs in data/raw/pdf/. Output: data/docs/session_NN.json.

Usage: python collect/docs.py [N ...]   (default: every session on the agenda dropdown)
       python collect/docs.py --refresh-latest 2   (only missing sessions + re-fetch the 2 newest)
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "docs"
HOST = "https://web.zagreb.hr"
SJ = "/Sjednice/2025/Sjednice_Skupstine_2025.nsf/"
ZP = "/Sjednice/2025/SkupstinaZapisi_2025.nsf/"
UA = "vijecnica-research/0.1 (open data hackathon; contact via G710 owner)"
STATUS = {"vwicn082": "prihvaćen", "vwicn117": "povučen", "vwicn038": "odbijen",
          "vwicn039": "vraćen na doradu"}
_last = [0.0]
REFRESH = [False]  # re-fetch HTML (not PDFs) for sessions that may still change


def get(path, binary=False, fresh=False):
    """GET with a disk cache and >=1 s between requests."""
    url = path if path.startswith("http") else HOST + urllib.parse.quote(path, safe="/?&=$.,:()-_%")
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cache = RAW / ("pdf" if binary else "web") / key
    if cache.exists() and not fresh and not (REFRESH[0] and not binary):
        data = cache.read_bytes()
    else:
        time.sleep(max(0, 1.0 - (time.time() - _last[0])))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=120).read()
        _last[0] = time.time()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    if binary:
        return cache
    # most pages are ASCII + entities with UTF-8 file names in URLs; some legacy ones are cp1250
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1250", errors="replace")
    return html.unescape(text)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def items_from(page):
    """(onclick url, number div, title div html, right-aligned div) per agenda-item block."""
    out = []
    for m in re.finditer(r"""<div class="agenda-item" onclick="handleItemClick\('([^']+)'\)">(.*?)</div>\s*</div>""",
                         page, re.S):
        url, body = m.group(1), m.group(2) + "</div>"
        divs = re.findall(r"<div[^>]*>(.*?)</div>", body, re.S)
        out.append((url, divs))
    return out


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                          text=True).stdout


def attachments(page):
    return [{"name": clean(n), "url": u} for u, n in
            re.findall(r"""handleItemClick\('([^']*\$FILE/[^']+)'\)[^>]*>(.*?)</""", page, re.S)] or \
           [{"name": Path(u).stem, "url": u} for u in
            dict.fromkeys(re.findall(r"""['"(]([^'"( ]*\$FILE/[^'"]+)['"]""", page))]


def agenda(n):
    page = get(f"{SJ}DRJ_?OpenAgent&{n}.")
    head = re.search(r"(\d+\. sjednica Gradske skup[^<]+)", page)
    items = []
    for url, divs in items_from(page):
        no = re.search(r"(\d+)", clean(divs[0]))
        icon = re.search(r"(vwicn\d+)", divs[1]) if len(divs) > 1 else None
        item = {"no": int(no.group(1)) if no else None,
                "title": clean(divs[1]) if len(divs) > 1 else "",
                "proposer": clean(divs[2]).replace("PREDLAGATELJ:", "").strip() if len(divs) > 2 else "",
                "status": STATUS.get(icon.group(1), icon.group(1)) if icon else None,
                "url": url}
        detail = get(url)
        body = clean(detail)
        m = re.search(r"Matično radno tijelo:(.*?)Nadležna radna tijela:(.*?)PRILOŽENI AKTI", body)
        if m:
            item["committee_lead"], item["committees"] = m.group(1).strip(), m.group(2).strip()
        item["full_title"] = (re.search(r"TOČKA \d+\.\s*(.*?)\s*Predlagatelj:", body) or [None, item["title"]])[1]
        item["attachments"] = attachments(detail)
        items.append(item)
    return (clean(head.group(1)) if head else f"{n}. sjednica"), items


VOTE_COLS = ("ZA", "SUZDRŽANO", "PROTIV", "Odsutan")


def unshift(s):
    """The vote PDFs embed some names in a font whose text layer is shifted by 29 code points."""
    fix = {"þ": "č", "ü": "ć", "ã": "š", "å": "ž", "â": "Š", "ä": "Ž", "ý": "Č", "û": "Ć", "ÿ": "đ"}
    return "".join(fix.get(c) or (chr(ord(c) + 29) if " " < c <= "]" else c) for c in s)


def parse_vote(pdf, roster):
    """Totals + per-member votes from a roll-call PDF; names matched against the attendance roster."""
    text = pdf_text(pdf)
    res = {"file": pdf.name}
    for k, lab in (("za", "ZA"), ("protiv", "PROTIV"), ("suzdrzano", "SUZDRŽANO"), ("glasovalo", "GLASOVALO")):
        # "32+3=35*" = 32 electronic + 3 added by hand (device failure etc.); the member table lists the 32
        m = re.search(rf"^\s*{lab}\s+(\d+)(?:\+(\d+)=(\d+))?\*?\s*$", text, re.M)
        res[k] = int(m.group(3) or m.group(1)) if m else None
        if m and m.group(2):
            res[k + "_manual"] = int(m.group(2))
    # "* gradski zastupnik Srđan Subotić glasovao je dizanjem glasačkog kartona"
    res["manual_names"] = [unshift(x) if not re.search(r"[a-zčćšž]{3}", x) else x for x in
                           re.findall(r"\*\s*gradsk\w+\s+zastupni\w+\s+(.+?)\s+glasoval", text)]
    m = re.search(r"Prijedlog (usvojen|nije usvojen|odbijen)", text)
    res["result"] = m.group(0) if m else None
    # per-member: bbox words, rows by y, X marks by column x
    bbox = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True).stdout
    members = {}
    page_words = re.split(r"<page ", bbox)[1:]
    cols = None
    for pw in page_words:
        words = [(float(a), float(b), float(c), html.unescape(w)) for a, b, c, w in
                 re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="[\d.]+">([^<]*)</word>', pw)]
        # the per-member table header is the row holding SUZDRŽAN(O) + ZA + "Ime" (the party table has "Stranka";
        # session 1 PDFs print SUZDRŽANO, later ones SUZDRŽAN). A page without a header continues the previous
        # page's table (sessions 5, 8: the columns are printed once).
        top = 0
        for sz in [w for w in words if w[3] in ("SUZDRŽAN", "SUZDRŽANO")]:
            line = [w for w in words if abs(w[1] - sz[1]) < 3]
            za = [w for w in line if w[3] == "ZA"]
            if not za or "Stranka" in {w[3] for w in line}:
                continue
            cols = {"za": (za[0][0] + za[0][2]) / 2}
            for w in line:
                c = {"SUZDRŽAN": "suzdrzan", "SUZDRŽANO": "suzdrzan", "PROTIV": "protiv", "Odsutan": "odsutan"}.get(w[3])
                if c:
                    cols[c] = (w[0] + w[2]) / 2
            top = sz[1] + 8
            break
        if not cols:
            continue
        foot = min([w[1] for w in words if w[1] > top and (w[3].startswith("Tiskano") or w[3] == "*")] or [1e9])
        names = [w for w in words if top < w[1] < foot and w[0] < cols["za"] - 40]
        marks = [w for w in words if top < w[1] < foot and w[3].rstrip("*") == "X"]
        lines = {}
        for w in names:
            lines.setdefault(round(w[1]), []).append(w)
        rows = sorted(lines.items())
        for x0, y, x1, _ in marks:
            col = min(cols, key=lambda c: abs(cols[c] - (x0 + x1) / 2))
            # a mark on its name's line wins; else (a wrapped name "Ankica Penava Pejčinović / X / (Možemo)") the
            # name lines within 14 pt above/below
            same = [" ".join(w[3] for w in sorted(ws)) for yy, ws in rows
                    if abs(yy - y) < 4 and not sorted(ws)[0][3].startswith("(")]  # "(Možemo)" = 2nd line of a name
            near = same or [" ".join(w[3] for w in sorted(ws)) for yy, ws in rows if abs(yy - y) < 14]
            raw = " ".join(near)
            name = match_member(raw, roster)
            if name:
                members[name] = col
    res["members"] = members
    return res


def norm(s):
    return re.sub(r"[^a-zčćšžđ ]", "", s.lower())


def match_member(raw, roster):
    from difflib import SequenceMatcher
    best, score = None, 0.0
    # OCR'd PDFs (sessions 1, 4) read a capital I as l: "lva lvšić", "lvka Odvorčić"
    ocr = re.sub(r"\bl(?=[bcdfghjklmnprstvzčćšžđ])", "I", raw)
    for cand in (raw, unshift(raw), ocr):
        c = norm(re.sub(r"\(.*?\)", "", cand))
        for r in roster:
            rn = norm(r)
            s = 1.0 if rn and rn in c else SequenceMatcher(None, c, rn).ratio()
            if s > score:
                best, score = r, s
    return best if score >= 0.6 else None


def attendance(n):
    page = get(f"{ZP}(sjednice_prisutnost)?OpenAgent&{n}.")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        tds = re.split(r"<td[^>]*>", tr)[1:]  # the last cell has no </td>
        if len(tds) >= 4 and re.match(r"\s*\d+\.", clean(tds[0])):
            icon = re.search(r"vwicn(\d+)", tds[3])
            rows.append({"name": clean(tds[1]), "party": clean(tds[2]),
                         "present": icon.group(1) == "114" if icon else None})
    return rows


def questions(n):
    page = get(f"{ZP}web_pitanja_?OpenAgent&{n}.")
    out = []
    for url, divs in items_from(page):
        who = clean(divs[2]) if len(divs) > 2 else ""
        name, _, party = who.partition(", ")
        raw = get(url)
        detail = clean(re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", raw))
        to = re.search(r"Pitanje upućeno:\s*(.*?)\s*ODGOVOR", detail)
        ans = re.search(r"ODGOVOR\s*(.*?)\s*(?:Odgovorio:\s*(.*?)\s*)?(?:PRILOŽENI AKTI|Copyright|$)",
                        detail[to.end() - len("ODGOVOR"):] if to else "")
        q = {"question": clean(divs[1]), "name": name, "party": party,
             "to": to.group(1) if to else "", "answer": ans.group(1).strip() if ans else "",
             "answered_by": (ans.group(2) or "").strip() if ans else "", "url": url,
             "attachments": attachments(raw)}
        # the fonogram is the verbatim transcript of the question and the oral answer
        for a in q["attachments"]:
            q.setdefault("fonogram", pdf_text(get(a["url"], binary=True)))
        out.append(q)
    return out


def minutes():
    page = get(f"{SJ}zapisnik_?OpenAgent", fresh=True)
    return {int(n): u for u, n in re.findall(
        r"handleItemClick\('([^']+)'\)\">\s*<div[^>]*>Zapisnik sa (\d+)\.", page)}


def sessions_available():
    page = get(f"{HOST}/sjednice/2025/sjednice_skupstine_2025.nsf/web_pretraga_autoriziran_font_new__?OpenForm",
               fresh=True)
    sel = re.search(r'name="rb_sjednice".*?</select>', page, re.S)
    return sorted({int(x) for x in re.findall(r"<option[^>]*>\s*(\d+)\.", sel.group(0) if sel else page)})


def main(ns, refresh_latest=None):
    OUT.mkdir(parents=True, exist_ok=True)
    ns = ns or sessions_available()
    mins = minutes()
    for n in ns:
        REFRESH[0] = refresh_latest is not None and n > max(ns) - refresh_latest
        if refresh_latest is not None and not REFRESH[0] and (OUT / f"session_{n:02d}.json").exists():
            continue
        t0 = time.time()
        title, items = agenda(n)
        att = attendance(n)
        roster = [a["name"] for a in att]
        for it in items:
            for a in it["attachments"]:
                if "glasovanja" in a["name"].lower() or "Izvještaj glasovanja" in a["url"]:
                    try:
                        it["vote"] = parse_vote(get(a["url"], binary=True), roster)
                        from reparse_votes import note  # roll call vs official totals ("32+3=35*")
                        it["vote"]["totals_note"] = note(it["vote"])
                    except Exception as e:  # keep going; one broken PDF should not stop a session
                        it["vote_error"] = repr(e)
        doc = {"session": n, "title": title, "items": items, "attendance": att,
               "questions": questions(n), "minutes_url": mins.get(n)}
        if doc["minutes_url"]:
            doc["minutes_text"] = pdf_text(get(doc["minutes_url"], binary=True))
        date = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", title)
        doc["date"] = f"{date.group(3)}-{int(date.group(2)):02d}-{int(date.group(1)):02d}" if date else None
        (OUT / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        votes = sum(1 for i in items if i.get("vote"))
        print(f"session {n}: {len(items)} items, {votes} votes, {len(att)} members, "
              f"{len(doc['questions'])} questions, minutes {'yes' if doc['minutes_url'] else 'no'} "
              f"({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--refresh-latest"]:
        main([], int(sys.argv[2]))
    else:
        main([int(x) for x in sys.argv[1:]])
