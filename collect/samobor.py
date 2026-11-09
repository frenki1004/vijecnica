"""Samobor city council (Gradsko vijeće Grada Samobora), from session packages downloaded by hand.

samobor.hr's robots.txt excludes AI systems, so this collector never touches the network: it reads only what a person
downloaded from the city's public session pages into data/samobor/manual/<N>/ (the materials package of session N):
  POZIV za N. sjednicu ….pdf                      the call: date and proposed agenda ("DNEVNI RED", items 0., 1., …)
  <k>.-/…                                         materials per agenda item k ("1 - Prijedlog Gradskom vijeću.pdf",
                                                  "2 - Prijedlog odluke.pdf", "Prilog …", "Zaključak gradonačelnice")
  0.- Verifikacija zapisnika M. sjednice …/ZAPISNIK M. sjednice ….pdf   the minutes of the previous session M
  Odbor za statutarno-pravna pitanja/            committee files (ignored)
File and folder names come from a CP852 ZIP unpacked as Mac Roman ("vijeÜa" = "vijeća"): decoded for display only,
attachment urls keep the on-disk path (relative to data/samobor).

All PDFs are scans: OCR (pdftoppm 300 dpi, tesseract hrv, as in collect/cakovec.py), cached in data/samobor/raw/ocr.

The minutes are a summary: per agenda item an "AD<k>.)" heading (OCR: "ADI.)", "ADS.)", "AD7T.)"), then the vote as
  Nakon provedenog glasovanja Gradsko vijeće Grada Samobora je većinom glasova (15 ZA, 1 SUZDRŽAN) donijelo ODLUKU o …
  … je jednoglasno (17 ZA) donijelo …
Counts not named in the parentheses are null ("jednoglasno" without numbers: null/0/0). Votes before AD1 (minutes,
agenda) and amendment votes are skipped. Items of a session with minutes come from the agenda adopted in the minutes
(the last "0. Verifikacija …" list before AD1; session 11 withdrew an item, so its numbering differs from its call),
else from its call; "Ostale informacije" is not an item. Materials come from the package of the same session.

Output: data/samobor/docs/session_NN.json (format of collect/cakovec.py).
Usage: python collect/samobor.py
"""
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "samobor"
MANUAL = D / "manual"
SEATS = 21
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
SOURCE = "ručno preuzeto iz paketa materijala {p}. sjednice (samobor.hr)"
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
AD = re.compile(r"^\f?[ \t]*A[DO][ \t]*([0-9ISlTO]{1,4})[ \t]*[.,]?[ \t]*\)", re.M)  # "AD12.)", "ADI.)", "ADS.)"
VOTE = re.compile(r"Nakon\s+provedenog\s+glasovanja\s+Gradsko\s+vijeće\s+Grada\s+Samobora\s+(?:je\s+)?"
                  r"(?P<how>jednoglasno|većinom\s+glasova)\s*(?:\((?P<counts>[^)]{0,80})\))?\s*(?:je\s+)?"
                  r"(?P<neg>nije\s+)?(?:donijel\w*|usvojil\w*|prihvatil\w*)\s*(?:x\s+)?(?P<act>.{0,400})", re.S)


def human(name):
    """Display form of an on-disk name (CP852 bytes read as Mac Roman)."""
    s = unicodedata.normalize("NFC", name)
    try:
        return s.encode("mac_roman").decode("cp852")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def ocr(path, pkg):
    """Text of a (scanned) PDF; OCR cached as raw/ocr/<package>__<stem>.txt."""
    t = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    if len(re.sub(r"\s", "", t)) > 200:
        return t
    cache = D / "raw" / "ocr" / f"{pkg}__{Path(path).stem}.txt"
    if not cache.exists():
        pages = []
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=D / "raw") as tmp:
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True)
            for png in sorted(Path(tmp).glob("p-*.png")):
                pages.append(subprocess.run(["tesseract", str(png), "-", "-l", "hrv", "--psm", "4"],
                                            capture_output=True, text=True,
                                            env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout)
        cache.write_text("\f".join(pages))
    return cache.read_text()


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def date_of(text, word):
    m = re.search(word + r"[^0-9]{0,40}?(\d{1,2})\.\s*(\w+)\s+(\d{4})", text)
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS else None


def agenda(text):
    """[(no, title)] from the last numbered list starting "0. Verifikacij…" in text (items 1.., no "Ostale")."""
    starts = [m.start() for m in re.finditer(r"^\f?[ \t]*0[.,]\s+Verifikacij", text, re.M)]
    if not starts:
        return []
    out, cur, expect = [], None, 1
    for ln in text[starts[-1]:].splitlines()[1:]:
        m = re.match(r"\s*(\d{1,2})[.,]\s+(\S.*)", ln)
        if m and int(m.group(1)) == expect:
            cur = [expect, m.group(2)]
            out.append(cur)
            expect += 1
        elif re.match(r"\s*(Pitam|NAPOMENA|Prije usvajanja|Sada prelazimo)", ln):
            break
        elif cur and ln.strip() and not re.match(r"\s*(DNEVNI RED|Za sjednicu)", ln):
            cur[1] += " " + ln.strip()
    items = [(n, re.sub(r"Priijedlog", "Prijedlog", ws(t).rstrip(" |"))) for n, t in out]
    return [(n, t) for n, t in items if not re.match(r"Ostale informacije", t, re.I)]


def ad_heads(text):
    """[(pos, no)] of the "AD<k>.)" headings, OCR-repaired and kept in increasing order."""
    out, last = [], 0
    for m in AD.finditer(text):
        tok = m.group(1)
        digits = re.sub(r"\D", "", tok)
        if not digits:
            digits = tok.translate(str.maketrans("IlSO", "1150")).rstrip("T") or ""
            digits = re.sub(r"\D", "", digits)
        if not digits:
            continue
        n = int(digits)
        if not last < n <= last + 2:  # "AD7T" etc. fixed above; anything else out of order is no heading
            n = last + 1 if n != last else None
        if n:
            out.append((m.start(), n))
            last = n
    return out


def headings(text, items):
    """[(pos, item)]: each "AD<k>.)" section heading of the minutes with its item."""
    out = []
    for pos, n in ad_heads(text):
        it = next((x for x in items if x["no"] == n), None)
        if it is not None:
            out.append((pos, it))
    return out


def clean(s):
    """A formula as one line: page-number lines and stray marks dropped, OCR "|" between capitals read as "I"."""
    s = re.sub(r"(?m)^[ \t\f]*\d{1,2}[ \t]*$", "", s)
    s = re.sub(r"(?<=[A-ZČĆŠŽĐ]) \| (?=[A-ZČĆŠŽĐ])", " I ", ws(s))
    return re.sub(r"(donijel\w*) [.x] ", r"\1 ", s)


def parse_vote(m):
    c = m.group("counts") or ""
    def num(word):
        k = re.search(r"(\d+)\s*" + word, c, re.I)
        return int(k.group(1)) if k else None
    za, protiv, suzd = num(r"ZA\b"), num(r"PROTIV"), num(r"SUZDR")
    unanimous = m.group("how") == "jednoglasno"
    if unanimous:
        protiv, suzd = 0, 0
    act = re.split(r",?\s*u\s+tekstu\s+kao|\n\s*\n\s*Tekst\s", m.group("act"))[0]
    act = clean(act).lstrip(". ")
    caps = re.match(r"([A-ZČĆŠŽĐ|]{2,}(?:\s+[A-ZČĆŠŽĐ|]+)*)\b", act)  # "IZMJENE I DOPUNE PROGRAMA gospodarenja …"
    if caps:
        act = caps.group(1).replace("|", "I").capitalize() + act[caps.end():]
    neg = bool(m.group("neg")) or (za is not None and protiv is not None and za <= protiv)
    quote = clean(re.split(r",?\s*u\s+tekstu\s+kao|\n\s*\n\s*Tekst\s", m.group(0))[0])[:300]
    return {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": NO if neg else YES, "members": {},
            "unanimous": unanimous and not neg, "quote": quote}, act


def materials(pkg_dir, no):
    """Attachments of agenda item `no` in a package: the "Prijedlog Gradskom vijeću" and "Prijedlog odluke" files."""
    folder = next((f for f in pkg_dir.iterdir() if f.is_dir() and re.match(rf"{no}\.-", f.name)), None)
    if not folder:
        return []
    out = []
    for f in sorted(folder.iterdir(), key=lambda p: p.name):
        h = human(f.stem)
        if f.suffix.lower() != ".pdf" or re.match(r"\s*Prilog", h, re.I):
            continue
        name = re.sub(r"^\s*\d+\s*\.?\s*-?\s*", "", h).strip(" _")
        if re.match(r"Prijedlog\s+(Gradskom\s+vijeću|odluke)", name, re.I):
            out.append({"name": name, "url": str(f.relative_to(D))})
    return out


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "samobo"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def packages():
    """{session: {"dir", "call": text, "minutes": (session M, text, pdf path)}} for every manual/<N>/."""
    out = {}
    for d in sorted((p for p in MANUAL.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda p: int(p.name)):
        n = int(d.name)
        pk = {"dir": d, "call": None, "minutes": None}
        call = next((f for f in d.glob("*.pdf") if human(f.name).upper().startswith("POZIV")), None)
        if call:
            pk["call"] = ocr(call, n)
        for f in d.glob("0.*/*.pdf"):
            m = re.search(r"ZAPISNIK\w*\s+(\d+)\.", human(f.name), re.I)
            if m:
                pk["minutes"] = (int(m.group(1)), ocr(f, n), f)
        out[n] = pk
    return out


def main():
    (D / "docs").mkdir(parents=True, exist_ok=True)
    pk = packages()
    minutes = {m[0]: (m[1], m[2], p) for p, x in pk.items() if (m := x["minutes"])}
    for n in sorted(set(pk) | set(minutes)):
        call = pk.get(n, {}).get("call")
        call_items = []
        if call:
            for no, title in agenda(call):
                call_items.append({"no": no, "title": title,
                                   "attachments": materials(pk[n]["dir"], no)})
        text, mpath, mpkg = minutes.get(n, (None, None, None))
        src = agenda(text[:AD.search(text).start()] if AD.search(text) else text) if text else []
        if not src:
            src = [(i["no"], i["title"]) for i in call_items]
        items = []
        for no, title in src:
            att = next((c["attachments"] for c in call_items if c["no"] == no and overlap(c["title"], title) >= .5),
                       None)
            if att is None:
                best = max(call_items, key=lambda c: overlap(c["title"], title), default=None)
                att = best["attachments"] if best and overlap(best["title"], title) >= .6 else []
            items.append({"no": no, "sub_label": None, "title": title, "full_title": title, "proposer": "",
                          "status": None, "url": None, "attachments": att})
        found = 0
        if text:
            heads = ad_heads(text)
            found = len(VOTE.findall(text, heads[0][0])) if heads else 0
            for k, (pos, no) in enumerate(heads):
                end = heads[k + 1][0] if k + 1 < len(heads) else len(text)
                it = next((x for x in items if x["no"] == no), None)
                if it is None:
                    continue
                for m in VOTE.finditer(text, pos, end):
                    vote, act = parse_vote(m)
                    if re.match(r"(?:\w+\s+){0,3}amandman", act, re.I):
                        continue
                    tot = sum(v for v in (vote["za"], vote["protiv"], vote["suzdrzano"]) if v)
                    if not 1 <= tot <= SEATS:
                        print(f"   implausible count {tot} for item {no}, dropped")
                        continue
                    it["vote"], it["votes"] = vote, [vote]
                    it["status"] = "prihvaćen" if vote["result"] == YES else "nije prihvaćen"
                    break
        present = None
        if text:
            p = re.search(r"nazočno\s+(\d+)\s+vijećnika", text)
            present = int(p.group(1)) if p else None
        doc = {"session": n, "title": f"{n}. sjednica Gradskog vijeća Grada Samobora",
               "date": (text and date_of(text[:1500], r"održane")) or (call and date_of(call, r"dana")),
               "url": None, "minutes_url": None,
               "minutes_source": SOURCE.format(p=mpkg) if text else None,
               "minutes_text": text, "present": present,
               "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"samobor session {n} ({doc['date']}): {len(items)} items, {nv} with votes "
              f"({found} formulas after AD1), minutes {'yes' if text else 'no'}, call {'yes' if call else 'no'}, "
              f"{sum(len(i['attachments']) for i in items)} attachments")
        for it in items:
            if text and not it.get("vote"):
                print(f"   no vote: {it['no']}. {it['title'][:90]}")


if __name__ == "__main__":
    main()
