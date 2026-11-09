"""Velika Gorica city council (Gradsko vijeće Grada Velike Gorice), from packages downloaded by hand.

Nothing is fetched: gorica.hr publishes the session materials as a OneDrive package per session, which a person
downloads and unpacks into data/velika_gorica/manual/<N>/ (N = the session the package is for). A package holds
  - the call "poziv za N. sjednicu GV.docx" (date and the proposed agenda, an auto-numbered list),
  - one folder per agenda item, "<k>. <short title>/" with "1. Obrazloženje.pdf", "2. Prijedlog….doc(x)", extracts,
    valuations, maps … (sometimes one level deeper; a lone item can also be a file "<k>. ….pdf"),
  - the minutes of the previous session, "zapisnik sa M. sjednice GV.docx" (verbatim, session M).

The minutes list the adopted agenda after "Dnevni red je prihvaćen … i glasi:" (numbered "1.", sub-items "a.)",
bullets "•") and have one section per item ("Točka N."). Vote formulas are free sentences:
  „Gradsko vijeće je većinom glasova (20 za i 4 protiv) donijelo Odluku …“, „Gradsko vijeće je jednoglasno donijelo …“,
  „Gradsko vijeća se 4 glasa za, 20 protiv i 1 suzdržan nije prihvatilo …“, „… većinom glasalo, 21 za i četiri protiv“.
Votes before "Točka 1." (minutes, urgency, agenda) and amendment votes are skipped. A section with several decision
votes whose agenda item has as many sub-items gets one sub-item per vote (item 16 of session 6: eight school statutes);
a single vote on an item with sub-items (the budget report with its programmes) stays one item, the sub-items in
full_title. Elections of individual candidates (Savjet mladih) and reports taken note of carry no vote.
"jednoglasno" without numbers: za None, protiv 0, suzdržano 0.

Items: from the minutes' adopted agenda when the minutes of the session exist, else from the call. Materials: per item
only the explanation and the proposal ("1. Obrazloženje…", "2. Prijedlog…"), by folder number checked against the title.

Output: data/velika_gorica/docs/session_NN.json (format of collect/cakovec.py). Recordings: collect/audio_sites.py.

Usage: python collect/velika_gorica.py
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "velika_gorica"
MANUAL = D / "manual"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
MINUTES_SOURCE = "ručno preuzeto iz paketa materijala {p}. sjednice (gorica.hr)"
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
WORDS = {w: i for i, w in enumerate("nula jedan dva tri četiri pet šest sedam osam devet deset jedanaest dvanaest "
                                    "trinaest četrnaest petnaest šesnaest sedamnaest osamnaest devetnaest dvadeset"
                                    .split())}
WORDS.update({"jedna": 1, "jednog": 1, "jedne": 1, "dvije": 2})
HEAD = re.compile(r"^[ \t]*Točka\s*(\d+)\s*\.", re.M)  # "Točka 1.", "Točka11."
FORMULA = re.compile(r"^[ \t]*(?:Gradsko\s+vijeć\w*|Zapisnik\s+je|Dnevni\s+red\s+je)\b[^\n]*?"
                     r"\b(?:jednoglasno|većinom|\d+\s+(?:\w+\s+)?(?:za|protiv|suzdrž\w*)\b)[^\n]*", re.M)
NUM = r"(\d+|" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")"
COUNT = re.compile(r"\b" + NUM + r"\s+(?:g\w*\s+)?(za|protiv|suzdrž\w*)\b", re.I)
VERB = re.compile(r"\b(nije\s+)?(?:donijel\w*|prihvatil\w*|usvojil\w*|prihvaćen\w*|odbil\w*|izabral\w*)\b")
SKIP = re.compile(r"amandman|žurnost|dnevn\w+\s+red|zapisnik|prijedlog\s+gospodina|prijedlog\s+vijećni", re.I)
KEEP = re.compile(r"^\s*(?:1\s*\.\s*Obrazlo|2\s*\.\s*Prijedlog)", re.I)


def doc_text(path):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
    return subprocess.run(["textutil", "-convert", "txt", "-stdout", str(p)], capture_output=True, text=True).stdout


def clean(s):
    s = re.sub(r"\s+", " ", s).strip().rstrip(":").strip()
    s = re.sub(r"(?<=\D)\.$", "", s).strip()  # "… Vukovina." but keep "2025."
    h = len(s) // 2
    if len(s) % 2 == 0 and s[:h] == s[h:]:  # the call repeats one item's text twice in the same paragraph
        s = s[:h]
    return s


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "velike",
                                                                "gorice", "zaklju", "godinu", "izvješ", "izvješć"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def num(s):
    return int(s) if s.isdigit() else WORDS[s.lower()]


def date_of(text):
    m = re.search(r"održane\s+(\d{1,2})\.\s+(\w+)\s+(\d{4})", text[:1500])
    if m and m.group(2) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"sjednicu[^\n]{0,80}?\bza\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"sjednicu[^\n]{0,80}?\bza\s+(\d{1,2})\.\s+(\w+)\s+(\d{4})", text)
    return f"{m.group(3)}-{MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m else None


def packages():
    """{package session P: {"call": path, "minutes": {M: path}, "dir": path}}."""
    out = {}
    if not MANUAL.exists():
        return out
    for d in sorted(MANUAL.iterdir(), key=lambda p: (len(p.name), p.name)):
        if not (d.is_dir() and d.name.isdigit()):
            continue
        pkg = {"dir": d, "call": None, "minutes": {}}
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() in (".doc", ".docx", ".pdf"):
                if re.match(r"poziv\b", f.name, re.I):
                    pkg["call"] = f
                m = re.match(r"zapisnik\s+sa?\s+(\d+)\s*\.\s*sjednic", f.name, re.I)
                if m:
                    pkg["minutes"][int(m.group(1))] = f
        out[int(d.name)] = pkg
    return out


def call_agenda(text):
    """Items of the proposed agenda (after "DNEVNI RED", list paragraphs, numbered in order)."""
    i = re.search(r"D\s*N\s*E\s*V\s*N\s*I\s+R\s*E\s*D", text)
    if not i:
        return []
    items = []
    for ln in text[i.end():].split("\n"):
        s = ln.strip()
        if re.match(r"PREDSJEDNI", s):
            break
        m = re.match(r"(?:•|\d+\s*\.)\s*(\S.*)", s)
        if m:
            t = clean(m.group(1))
            items.append({"no": len(items) + 1, "sub_label": None, "title": t, "full_title": t, "subs": []})
    return items


def minutes_agenda(text):
    """The adopted agenda: the numbered list after "Dnevni red je prihvaćen … glasi:"; sub-items "a.)" or "•"."""
    m = re.search(r"Dnevni\s+red\s+je\s+[^\n]*?glasi\s*:", text)
    if not m:
        return []
    items = []
    for ln in text[m.end():].split("\n"):
        s = ln.strip()
        if not s:
            continue
        n = re.match(r"(\d{1,2})\s*\.\s+(\S.*)", s)
        sub = re.match(r"(?:([a-z])\s*\.?\s*\)|•)\s*(\S.*)", s)
        if n and int(n.group(1)) == len(items) + 1:
            t = clean(n.group(2))
            items.append({"no": len(items) + 1, "sub_label": None, "title": t, "full_title": t, "subs": []})
        elif sub and items:
            items[-1]["subs"].append(clean(sub.group(2)))
        else:
            break
    return items


def parse_vote(line):
    """Vote dict of a formula line, or None for a line that is no decision on an item."""
    q = re.sub(r"\s+", " ", line).strip()
    v = VERB.search(q)
    counts = {}
    for c in COUNT.finditer(q[:v.start()] if v else q):
        counts.setdefault(c.group(2).lower()[:5], num(c.group(1)))
    unan = bool(re.search(r"\bjednoglasno\b", q))
    za, protiv, suzd = counts.get("za"), counts.get("proti"), counts.get("suzdr")
    if unan and not counts:
        za, protiv, suzd = None, 0, 0
    elif unan:  # "jednoglasno (21 za)": nobody against or abstaining
        protiv, suzd = 0, 0
    # otherwise a count the minutes do not name stays None (unknown), as in every other collector
    neg = bool(v and v.group(1)) or bool(v and v.group(0).startswith("odbil"))
    result = NO if neg or (za is not None and protiv is not None and za <= protiv) else YES
    return {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
            "unanimous": unan and result == YES, "quote": q[:400]}


def headings(text, items):
    """[(pos, item)]: each "Točka N." section heading of the minutes with its item (the first, for sub-items)."""
    out, last = [], 0
    for m in HEAD.finditer(text or ""):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n > last:
            out.append((m.start(), it))
            last = n
    return out


def minutes_items(text, agenda):
    """Items with votes from the "Točka N." sections. Returns (items, formulas found, votes matched)."""
    found = len(FORMULA.findall(text))
    heads = headings(text, agenda)
    out, matched = [], 0
    for i, (pos, it) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        sec = text[pos:end]
        votes = []
        for f in FORMULA.finditer(sec):
            if SKIP.search(f.group(0)):
                continue
            votes.append(parse_vote(f.group(0)))
        base = {k: it[k] for k in ("no", "sub_label", "title", "full_title")}
        status_free = ("primljeno na znanje" if re.search(r"primil\w*\s+na\s+znanje|primljen\w*\s+na\s+znanje",
                                                           sec, re.I) else None)
        if len(votes) > 1 and len(votes) == len(it["subs"]):
            for k, (sub, v) in enumerate(zip(it["subs"], votes)):
                t = f"{it['title']}: {sub}"
                out.append(dict(base, sub_label=chr(97 + k), title=t, full_title=t, vote=v, votes=[v]))
                matched += 1
            continue
        if it["subs"]:
            base["full_title"] = f"{it['title']}, s točkama: " + "; ".join(it["subs"])
        if votes:
            base["vote"], base["votes"] = votes[-1], votes
            matched += len(votes)
            if len(votes) > 1:
                print(f"   {len(votes)} votes in Točka {it['no']} ({len(it['subs'])} sub-items): last one kept as vote")
        else:
            base["_status"] = status_free
        out.append(base)
    done = {x["no"] for _, x in heads}
    for it in agenda:  # items without a section in the minutes
        if it["no"] not in done:
            out.append({k: it[k] for k in ("no", "sub_label", "title", "full_title")})
    out.sort(key=lambda x: (x["no"], x["sub_label"] or ""))
    return out, found, matched


def item_files(path):
    """Explanation and proposal of one agenda item folder (or the item's single file)."""
    if path.is_file():
        return [path]
    d = path
    while True:
        files = [f for f in d.iterdir() if f.is_file() and not f.name.startswith(".") and f.name != "Thumbs.db"]
        dirs = [f for f in d.iterdir() if f.is_dir()]
        if files or len(dirs) != 1:
            break
        d = dirs[0]  # "5. …/Prijedlog Odluke …/1. Obrazloženje.pdf"
    keep = sorted(f for f in files if KEEP.match(f.name))
    if not keep:  # "20. MRTVOZORNICI/": no numbered files, take the documents themselves
        keep = sorted(f for f in files if f.suffix.lower() in (".pdf", ".doc", ".docx"))[:3]
    return keep


def materials(pkg_dir, items):
    """Attach each "<k>. …" folder of the package to item k (title checked), else to the most similar item."""
    for f in sorted(pkg_dir.iterdir()):
        m = re.match(r"(\d+)\s*\.\s*(.*)", f.name)
        if not m:
            continue
        k, name = int(m.group(1)), re.sub(r"\.pdf$", "", m.group(2), flags=re.I)
        cands = [x for x in items if x["no"] == k]
        tgt = cands if cands and max(overlap(x["full_title"], name) for x in cands) >= 0.3 else []
        if not tgt:
            best = max(items, key=lambda x: overlap(x["full_title"], name), default=None)
            if best and overlap(best["full_title"], name) >= 0.5:
                tgt = [x for x in items if x["no"] == best["no"]]
            else:
                print(f"   material not matched: {f.name}")
                continue
        atts = [{"name": a.name, "url": a.relative_to(D).as_posix()} for a in item_files(f)]
        for x in tgt:
            x.setdefault("attachments", []).extend(atts)


def main():
    (D / "docs").mkdir(parents=True, exist_ok=True)
    pk = packages()
    minutes = {m: (path, p) for p, v in pk.items() for m, path in v["minutes"].items()}
    for n in sorted(set(pk) | set(minutes)):
        pkg = pk.get(n)
        call = doc_text(pkg["call"]) if pkg and pkg["call"] else None
        mpath, mpkg = minutes.get(n, (None, None))
        text = doc_text(mpath) if mpath else None
        agenda = (minutes_agenda(text) if text else []) or (call_agenda(call) if call else [])
        found = matched = 0
        if text:
            items, found, matched = minutes_items(text, agenda)
        else:
            items = [{k: it[k] for k in ("no", "sub_label", "title", "full_title")} for it in agenda]
        if pkg:
            materials(pkg["dir"], items)
        for it in items:
            v = it.get("vote")
            st = it.pop("_status", None)
            it["proposer"] = ""
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else st
            it["url"] = None
            it.setdefault("attachments", [])
            order = ["no", "sub_label", "title", "full_title", "proposer", "status", "url", "attachments"]
            for k in order + ["vote", "votes"]:
                if k in it:
                    it[k] = it.pop(k)
        doc = {"session": n, "title": f"{n}. sjednica Gradskog vijeća Grada Velike Gorice",
               "date": (text and date_of(text)) or (call and date_of(call)), "url": None, "minutes_url": None,
               "minutes_source": MINUTES_SOURCE.format(p=mpkg) if text else None, "minutes_text": text,
               "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        nv = sum(1 for i in items if i.get("vote"))
        print(f"velika_gorica session {n} ({doc['date']}): {len(items)} items, {nv} with votes"
              + (f"; minutes (package {mpkg}): {found} formulas, {matched} matched" if text else "; no minutes")
              + f"; {sum(len(i['attachments']) for i in items)} attachments")
        if text:
            for it in items:
                if not it.get("vote"):
                    print(f"   no vote: {it['no']}{it['sub_label'] or ''}. {it['title'][:80]} [{it['status']}]")


if __name__ == "__main__":
    main()
