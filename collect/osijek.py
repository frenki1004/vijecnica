"""Collect Osijek City Council (Gradsko vijeće Grada Osijeka) sessions, 2025-2029 term.

osijek.hr (WordPress): /prijenos-sjednice/ has a <select> of every session (all terms); the theme's
prijenos-sjednice-connection.php (POST sjednica_id=<option value>) returns that session's panel: the
audio ZIP link, a YouTube embed and the agenda as <div class="row dnevni-red"><h6>N. x) title</h6>
with the item's PDFs (uredsko.zio.hr/JavniDokumenti/...). Sub-items ("5. a)", "5. b)" ...) are kept as
separate items that share a number (db/build.py gives them sub = 1, 2, 3 ...), because the council votes
on each one. There is no per-session URL, so every session links to the archive page.

Minutes (zapisnik) are text PDFs attached to a later session's "Usvajanje zapisnika" item; the session
they belong to is read from the PDF itself ("ZAPISNIK sa 8. sjednice ..."). They have attendance by name,
sections "TOČKA N. <TITLE IN CAPITALS>" (numbered as the session ran: items get added and renumbered,
so a heading is matched to an agenda item by title) and votes such as "Nakon provedenog glasovanja
utvrdio je da je Odluka ... donesena većinom glasova ... i to s 19 “za” i 3 “suzdržana”" or
"... jednoglasno i to s 22 glasa „za“". No per-councillor votes. Procedural votes (joint debate,
agenda) are skipped.

Cache: data/osijek/raw/web (HTML), data/osijek/raw/pdf. Audio ZIPs and videos are not downloaded.
Output: data/osijek/docs/session_NN.json, data/osijek/recordings.json, data/osijek/members.json.

Usage: python collect/osijek.py [--fresh]   (--fresh re-fetches the session list and session panels)
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "osijek"
HOST = "https://www.osijek.hr"
ARCHIVE = HOST + "/prijenos-sjednice/"
PANEL = HOST + "/wp-content/themes/osijek/prijenos-sjednice-connection.php"
MEMBERS = HOST + "/gradska-uprava/gradsko-vijece/vijecnici/"
TERM_START = "2025-06-03"  # constitutive session of the 2025-2029 term
UA = "vijecnica-research/0.1 (open data hackathon)"
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
_last = [0.0]

MONTHS = {"siječnja": 1, "veljače": 2, "ožujka": 3, "travnja": 4, "svibnja": 5, "lipnja": 6, "srpnja": 7,
          "kolovoza": 8, "rujna": 9, "listopada": 10, "studenoga": 11, "studenog": 11, "prosinca": 12}
WORDNUM = {"jednim": 1, "jednom": 1, "jedan": 1, "jedna": 1, "dva": 2, "dvama": 2, "dvije": 2, "tri": 3,
           "četiri": 4, "pet": 5}


def get(url, binary=False, fresh=False, data=None):
    """Cached GET (or POST when data is given), at most one request per second."""
    body = urllib.parse.urlencode(data).encode() if data else None
    key = hashlib.sha1((url + ("?" + body.decode() if body else "")).encode()).hexdigest()[:16]
    cache = D / "raw" / ("pdf" if binary else "web") / key
    if not cache.exists() or fresh:
        time.sleep(max(0, 1.0 - (time.time() - _last[0])))
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.URLError as e:
            # uredsko.zio.hr chains to Sectigo's R46 root, missing from Python's CA file but in the macOS
            # keychain that curl uses: retry with curl, which still verifies the certificate
            if "CERTIFICATE_VERIFY_FAILED" not in str(e):
                raise
            cmd = ["curl", "-sSf", "--max-time", "120", "-A", UA, url] + (["--data", body.decode()] if body else [])
            raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        finally:
            _last[0] = time.time()
        if not binary and re.search(rb"captcha|cf-chl|Just a moment", raw[:5000], re.I):
            sys.exit(f"bot check at {url}; stopping")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    return cache if binary else cache.read_text("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def hr_date(s):
    m = re.search(r"(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")\s+(\d{4})", s)
    return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}" if m else None


def session_list(fresh):
    """[(option id, session number, title, date)] of the current term, oldest first."""
    page = get(ARCHIVE, fresh=fresh)
    sel = re.search(r'<select name="gr_vijece".*?</select>', page, re.S)
    out = []
    for oid, label in re.findall(r'<option value="(\d+)">([^<]+)', sel.group(0) if sel else page):
        label = clean(label)
        date = hr_date(label)
        n = re.match(r"(\d+)\.", label)
        if date and n and date >= TERM_START:
            out.append((oid, int(n.group(1)), label, date))
    return sorted(out, key=lambda s: s[1])


def agenda(panel):
    """Items from the panel: one per <h6> row; a link's name is the <h6> inside it."""
    items = []
    for row in re.split(r'<div class="row dnevni-red">', panel)[1:]:
        h = re.search(r"<h6>(.*?)</h6>", row, re.S)
        head = clean(h.group(1)) if h else ""
        m = re.match(r"(\d+)\s*\.\s*([a-z0]?)\s*\)?\s*(.*)", head)  # "5. a) ...", "3. ) ...", "19. 0) ..."
        if not m:
            continue
        title = m.group(3).strip()
        status = None
        dropped = re.search(r"\s*-\s*TOČKA SKINUTA S DNEVNOG REDA\s*$", title)
        if dropped:
            title, status = title[:dropped.start()], "skinuto s dnevnog reda"
        title = re.sub(r"\s*-\s*(?:PRIJEDLOG ZA )?DOPUNA? DNEVNOG REDA\s*$", "", title, flags=re.I)
        links = [{"name": clean(name), "url": html.unescape(u)}
                 for u, name in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', row[h.end():], re.S)]
        items.append({"no": int(m.group(1)), "letter": m.group(2).strip("0"), "title": title, "status": status,
                      "attachments": links})
    # a sub-item's full title names its group when the site gives one ("17. Godišnja izvješća ...:")
    for it in items:
        it["full_title"] = (f"{it['no']}. {it['letter']}) " if it["letter"] else f"{it['no']}. ") + it["title"]
    return items


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


def person(s):
    """'Leko Ćurčić, Mira' / 'Surla-Lusch Nataša' -> 'Mira Leko Ćurčić' / 'Nataša Surla-Lusch'."""
    s = re.sub(r"-\s+", "-", re.sub(r"\s+", " ", s)).strip(" .,")  # "Surla- Lusch": hyphen at a line break
    if "," in s:
        last, first = (x.strip() for x in s.split(",", 1))
    else:
        *last, first = s.split(" ")
        last = " ".join(last)
    return f"{first} {last}".strip()


QUOTE = "\"“”„‟'’‘«»"
COUNT = re.compile(r"(\d+|" + "|".join(WORDNUM) + r")\s+(?:glas\w*\s+)?[" + QUOTE + r"]?\s*(za|protiv|suzdrž\w*)\b")
PROCEDURAL = re.compile(r"zajedničk\w* raspra|dnevn\w* red|hitn\w* postup", re.I)


def minutes_parse(text):
    """Attendance, the session the minutes are for, and the votes (with the text that names the act)."""
    flat = re.sub(r"\s+", " ", text)
    sess = re.search(r"ZAPISNIK\s*(?:sa|s)\s+(\d+)\.\s+(?:\w+\s+)?sjednic", re.sub(r"(?<=[A-Z]) (?=[A-Z])", "", flat[:600]), re.I)
    att = []
    pres = re.search(r"Nazočni vijećnici:\s*(.*?)\s*(?:Nisu nazočni|Nije nazoč\w*|Odsutn\w*)\s*:?\s*(.*?)\s*Ostali nazočni", flat)
    if not pres:
        pres = re.search(r"Nazočni vijećnici:\s*(.*?)\s*()Ostali nazočni", flat)
    if pres:
        for n in re.split(r"\s*\d+\.\s+", " " + pres.group(1)):
            if n.strip() and re.search(r"[A-Za-zČĆŠŽĐčćšžđ]", n):
                att.append({"name": person(n), "present": True})
        absent = re.sub(r"\.\s*$", "", pres.group(2))
        for n in re.split(r",\s*|\s+i\s+", absent):
            n = re.sub(r"\b\d+\b", "", n).strip()
            if n and re.search(r"[A-Za-zČĆŠŽĐčćšžđ]", n):
                att.append({"name": person(n), "present": False})
    votes = []
    # "Nakon (elektronički) provedenog glasovanja utvrdio je da ..." / "Nakon obrazloženja i provedenog
    # glasovanja predsjednik je konstatirao da ..."
    for m in re.finditer(r"(?:Nakon|Po) [^.]{0,40}?provedenog (?:elektroničkog )?glasovanja,?\s+(?:\w+\s+)?"
                         r"(?:je\s+)?(?:utvrdi\w*|konstatira\w*)\s+(?:je,?\s+)?(?:da|kako)\s+", flat):
        s = flat[m.end():m.end() + 600]
        cut = re.search(r"\s(?:te je|te su)\s|\.\s(?=Predsjednik|Pozvao|Nakon|TOČKA|[A-ZČĆŠŽĐ]{4,})", s)
        s = s[:cut.start()] if cut else s
        v = {"za": 0, "protiv": 0, "suzdrzano": 0, "procedural": bool(PROCEDURAL.search(s))}
        tail = s[re.search(r"\bi to sa?\b|jednoglasno|većinom", s).start():] if re.search(
            r"\bi to sa?\b|jednoglasno|većinom", s) else s
        for num, kind in COUNT.findall(tail):
            k = "suzdrzano" if kind.startswith("suzd") else kind
            v[k] = int(num) if num.isdigit() else WORDNUM.get(num, 0)
        v["unanimous"] = "jednoglasno" in s
        v["result"] = NO if re.search(r"\bnije\s+(?:\w+\s+){0,3}(?:donesen|prihvać|usvoj|primljen|izabran|imenovan)|odbijen",
                                      s) else YES
        prev_end = votes[-1]["end"] if votes else 0
        call = flat.rfind("glasovanju o", prev_end, m.start())
        v["subject"] = flat[call if call >= 0 else max(prev_end, m.start() - 400):m.start()] + " " + s
        v["sentence"] = s
        v["pos"], v["end"] = m.start(), m.end() + len(s)
        votes.append(v)
    return (int(sess.group(1)) if sess else None), att, votes, flat


def stem_set(t):
    return {w[:5] for w in re.findall(r"\w+", t.lower()) if len(w) > 3}


TITLE_STOP = stem_set("prijedlog odluke zaključka rješenja izmjenama dopunama izmjeni dopuni grada gradskog "
                      "gradskoga vijeća osijeka području godinu godini")


HEAD = re.compile(r"TOČK[AU] (\d+)\.:?")


def heading_text(flat, end):
    """The capitalised title after 'TOČKA N.' (ends at the first lower-case word)."""
    s = flat[end:end + 800]
    low = re.search(r"\b[A-ZČĆŠŽĐ]?[a-zčćšžđ]{3,}", s)
    s = s[:low.start()] if low else s[:400]
    return s if len(s) > 8 else flat[end:end + 400]


def heading_item(items, n, heading):
    """The agenda item a 'TOČKA N.' heading belongs to, by title: the minutes number items in the order
    the session took them (8th session added a mandate report as item 1, so every heading is one ahead
    of the published agenda). Best F1 of "title words in the heading" and "heading words in the title" wins
    (porotnici 'Općinskog suda' vs 'za mladež Općinskog suda'; a short title such as 'Izbor predsjednika'
    must not take a long heading that merely contains it), then the closest number. None unless 60 % of
    the title is in the heading, or of a short heading in the title ('IZVJEŠĆE MANDATNOG POVJERENSTVA')."""
    h = stem_set(heading) - TITLE_STOP

    def score(it):
        t = stem_set(it["title"]) - TITLE_STOP
        cover, back = len(t & h) / (len(t) or 1), len(t & h) / (len(h) or 1)
        f1 = 2 * cover * back / ((cover + back) or 1)
        return f1, -abs(it["no"] - n), cover, back if len(h) >= 2 else 0
    cands = [it for it in items if it.get("status") != "skinuto s dnevnog reda"]
    best = max(cands, key=score, default=None)
    return best if best is not None and max(score(best)[2:]) >= 0.6 else None


def attach_votes(items, votes, flat):
    """A vote belongs to the last 'TOČKA N.' heading before it; when that heading's item has sub-items
    (5. a), 5. b) ...), to the sub-item whose title best matches the act named in the vote. Returns the
    votes that could not be placed (with the heading they fell under)."""
    heads = []
    for m in re.finditer(HEAD, flat):
        ht = heading_text(flat, m.end())
        heads.append((m.start(), int(m.group(1)), ht, heading_item(items, int(m.group(1)), ht)))
    lost = []
    for v in votes:
        prev = [h for h in heads if h[0] < v["pos"]]
        if v["procedural"]:
            # a rejected proposal to add an item (session 4: Možemo!'s "Preporuka ... obaloutvrde") is the
            # only vote that item ever gets; accepted additions get their own TOČKA and vote
            if not prev and v["result"] == NO and "dopun" in v["sentence"]:
                subj = stem_set(v["subject"])
                for it in items:
                    t = stem_set(it["title"]) - TITLE_STOP
                    if t and len(t & subj) / len(t) >= 0.8 and not it.get("votes"):
                        it["votes"] = [{**{k: v[k] for k in ("za", "protiv", "suzdrzano", "unanimous", "result",
                                                             "sentence")}, "agenda": True}]
                        it["status"] = "nije uvršten u dnevni red"
            continue
        if not prev:
            continue  # before TOČKA 1 and not procedural: should not happen
        hpos, n, ht, best = prev[-1]
        if best is None:
            lost.append({"heading": f"TOČKA {n}. {ht.strip()}", **{k: v[k] for k in ("za", "protiv", "suzdrzano")}})
            continue
        group = [it for it in items if it["no"] == best["no"] and it.get("status") != "skinuto s dnevnog reda"]
        if len(group) > 1:
            # the minutes put "A) TITLE" before each sub-item's vote: that letter counts for half; the rest is
            # the act named in the vote (the site's titles have typos: "Izješće ... infrstrukture")
            subs = re.findall(r"(?:^|\s)([A-Z])\)\s+[A-ZČĆŠŽĐ]{3,}", flat[hpos + len(ht) + 10:v["pos"]])
            letter = subs[-1].lower() if subs else None
            subj = stem_set(v["subject"]) - TITLE_STOP

            def sc(it):
                t = stem_set(it["title"]) - TITLE_STOP
                return (len(t & subj) / (len(t) or 1) + 0.5 * (it["letter"] == letter),
                        len(t & subj) / (len(t | subj) or 1), -len(it.get("votes", [])))
            best = max(group, key=sc)
        best.setdefault("votes", []).append({k: v[k] for k in ("za", "protiv", "suzdrzano", "unanimous", "result",
                                                               "sentence")})
    for it in items:
        if it.get("votes"):
            # the last vote on the act itself, not on an amendment (session 4, item 23: nine amendments,
            # then the programme); "Usvajanje zapisnika sa 6. i 7. sjednice": two votes, both the same
            final = [x for x in it["votes"] if not re.match(r"(?:\d+\.\s*)?Amandman", x["sentence"])]
            last = (final or it["votes"])[-1]
            it["vote"] = {"za": last["za"], "protiv": last["protiv"], "suzdrzano": last["suzdrzano"],
                          "result": last["result"], "members": {}}
    return lost


def proposer_of(flat, items):
    """'Gradonačelnik je utvrdio navedeni prijedlog ...' right after an item's heading."""
    for m in re.finditer(HEAD, flat):
        ht = heading_text(flat, m.end())
        it = heading_item(items, int(m.group(1)), ht)
        body = flat[m.end() + len(ht):m.end() + len(ht) + 300]
        p = re.match(r"\s*([A-ZČĆŠŽĐ][\w ,-]{3,80}?) (?:je|su) (?:utvrdi\w*|razmotri\w*|podni\w*|predloži\w*|"
                     r"uputi\w*|dostavi\w*)", body)
        if it is not None and p:
            for sib in items:
                if sib["no"] == it["no"] and not sib.get("proposer"):
                    sib["proposer"] = p.group(1)


def members(known, fresh):
    """Roster with parties: the elected members by list, and the sitting councillors (with substitutes,
    who take the list of the member they replace). Elected members not sitting get a status."""
    from difflib import SequenceMatcher
    page = get(MEMBERS, fresh=fresh)
    body = page[page.find("Mandat 2025."):]
    elected = {}
    for block in re.findall(r"<p>(.*?)</p>", body[:body.find("VIJEĆNICI")], re.S):
        lists = [clean(x) for x in re.findall(r"<strong>(.*?)</strong>", block, re.S)]
        names = [clean(x) for x in re.findall(r"\d+\.\s*([^<]+)", block)]
        if lists:
            short = [re.split(r"\s+[–-]\s+", l)[-1] if re.search(r"\s[–-]\s", l) else l for l in lists]
            party = ", ".join(short)
            cur = party
        for n in names:
            elected[n.title()] = cur
    sitting = re.search(r"VIJEĆNICI.*?<ol>(.*?)</ol>", body, re.S)
    out, seen = [], set()

    def canon(name):
        best = max(known, key=lambda k: SequenceMatcher(None, k, name).ratio(), default=name)
        return best if SequenceMatcher(None, best, name).ratio() > 0.85 else name

    def elected_party(name):
        best = max(elected, key=lambda k: SequenceMatcher(None, k.lower(), name.lower()).ratio())
        return elected[best] if SequenceMatcher(None, best.lower(), name.lower()).ratio() > 0.8 else None
    for li in re.findall(r"<li>(.*?)</li>", sitting.group(1) if sitting else "", re.S):
        li = clean(li)
        name = canon(person(re.split(r"\s+[–-]\s+|\s*\(", li)[0]))
        sub = re.search(r"zamjen\w* (?:za )?vijećnik\w* (\w+) (\w+)", li)
        party = elected_party(name)
        if sub and not party:  # 'Igora Pandžića' / 'Borisa Piližotu' / 'Milana Opačka': match on stems
            f, l = sub.group(1)[:3].lower(), sub.group(2)[:4].lower()
            hit = [p for k, p in elected.items() if k.split()[0][:3].lower() == f and k.split()[-1][:4].lower() == l]
            party = hit[0] if hit else None
        out.append({"name": name, "party": party, **({"note": li.split(name.split()[0])[-1].strip(" –-,()")}
                                                      if sub else {})})
        seen.add(name.lower())
    for n, party in elected.items():
        name = canon(n.replace("-", " ") if n.replace("-", " ") in known else n)
        if name.lower() not in seen and not any(SequenceMatcher(None, name.lower(), s).ratio() > 0.85 for s in seen):
            out.append({"name": name, "party": party, "status": "nije u sastavu vijeća (mandat miruje ili prestao)"})
    return out


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    sessions = session_list(fresh)
    panels = {n: get(PANEL, fresh=fresh, data={"sjednica_id": oid}) for oid, n, _, _ in sessions}
    for n, p in panels.items():
        if "dnevni-red" not in p:
            sys.exit(f"session {n}: no agenda in the panel response; stopping")
    agendas = {n: agenda(panels[n]) for n in panels}
    # minutes: every PDF on a "zapisnik" item; the PDF says which session it records
    minutes = {}
    for n, items in agendas.items():
        for it in items:
            if "zapisnik" in it["title"].lower():
                for a in it["attachments"]:
                    if a["url"].lower().endswith(".pdf") and "zapisnik" in a["name"].lower():
                        text = pdf_text(get(a["url"], binary=True))
                        s = minutes_parse(text)[0]
                        named = re.search(r"(\d+)\.", a["name"])
                        s = s or (int(named.group(1)) if named else None)
                        if s:
                            minutes[s] = (a["url"], text)
    recordings, lost_all = [], {}
    for oid, n, label, date in sessions:
        panel, items = panels[n], agendas[n]
        doc = {"session": n, "title": label, "date": date, "url": ARCHIVE, "minutes_url": None, "minutes_text": None,
               "items": items, "attendance": [], "questions": []}
        if n in minutes:
            doc["minutes_url"], doc["minutes_text"] = minutes[n]
            _, att, votes, flat = minutes_parse(doc["minutes_text"])
            doc["attendance"] = att
            lost_all[n] = attach_votes(items, votes, flat)
            proposer_of(flat, items)
            doc["votes_in_minutes"] = len(votes)
        for it in items:
            it.pop("letter", None)
            it.pop("votes", None)
            it.setdefault("proposer", "")
            if it["status"] is None and it.get("vote"):
                it["status"] = "prihvaćen" if it["vote"]["result"] == YES else "nije prihvaćen"
            docs = [a for a in it["attachments"] if a["url"].lower().endswith(".pdf")]
            it["url"] = docs[0]["url"] if docs else ARCHIVE
        for k, vid in enumerate(dict.fromkeys(re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", panel)), 1):
            recordings.append({"id": f"osijek-{n:02d}-{k}", "session": n, "part": k, "date": date, "title": label,
                               "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube"})
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        rec = [r for r in recordings if r["session"] == n]
        print(f"osijek session {n} ({date}): {len(items)} items, {sum(1 for i in items if i.get('vote'))} with votes "
              f"({doc.get('votes_in_minutes', 0)} votes in minutes, {len(lost_all.get(n, []))} unplaced), "
              f"{len(doc['attendance'])} members, minutes {'yes' if doc['minutes_url'] else 'no'}, "
              f"recordings {len(rec)}", flush=True)
        for lv in lost_all.get(n, []):
            print(f"   unplaced vote: {lv}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    known = sorted({a["name"] for f in (D / "docs").glob("session_*.json")
                    for a in json.loads(f.read_text())["attendance"]})
    roster = members(known, fresh)
    (D / "members.json").write_text(json.dumps(roster, ensure_ascii=False, indent=1))
    # minutes typos ("Mato Jurčević" for Mate): attendance takes the roster spelling when nearly equal
    from difflib import SequenceMatcher
    for f in sorted((D / "docs").glob("session_*.json")):
        doc = json.loads(f.read_text())
        for a in doc["attendance"]:
            best = max(roster, key=lambda m: SequenceMatcher(None, m["name"], a["name"]).ratio())["name"]
            if best != a["name"] and SequenceMatcher(None, best, a["name"]).ratio() >= 0.9:
                print(f"   session {doc['session']}: attendance '{a['name']}' -> '{best}'", flush=True)
                a["name"] = best
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    print(f"members: {len(roster)} ({sum(1 for m in roster if m['party'])} with parties); "
          f"latest minutes: session {max(minutes) if minutes else None}", flush=True)


if __name__ == "__main__":
    main("--fresh" in sys.argv)
