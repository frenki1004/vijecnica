"""Slavonski Brod: agenda items and vote results from the session recording, weeks before the minutes.

The Brod chair moves between items with "(te) možemo (prijeći) na četvrtu točku …", "na 9. točku",
"možemo još desetu točku", and between sub-items of one item (e.g. 2 = seven city companies) with
"krećemo s točkom 2a …" / "možemo na iduću pod točku <company>". After each vote he reads the result:
"konstatiram da smo sa 12 glasova za, pet protiv i dva suzdržana usvojili …" (or "jednoglasno usvojili").
ASR garbles words ("su zdržana", "osvojili", "to svojili"), so numbers are read from a window that ends
at the "…svojili" word and starts at the chair's call to vote. A correction ("dva suzdržana usvojili,
pardon, tri suzdržana") is handled by taking the last number said for each option.

Output: items.t_start for Brod items (replaces the Zagreb-style anchors) and table spoken_votes with
source='snimka' (unofficial: the official numbers are in the minutes, which come out weeks later).
"""
import re
import sqlite3

ORD = ["prv", "drug", "treć", "četvrt", "pet", "šest", "sedm", "osm", "devet", "deset", "jedanaest", "dvanaest",
       "trinaest", "četrnaest", "petnaest", "šesnaest", "sedamnaest", "osamnaest", "devetnaest", "dvadeset"]
# ASR/speech variants of the ordinals ("četrnesta", "jedanesta") -> number
ORD_N = {o: i + 1 for i, o in enumerate(ORD)}
ORD_N.update({"jedanest": 11, "dvanest": 12, "trinest": 13, "četrnest": 14, "petnest": 15, "šesnest": 16,
              "sedamnest": 17, "osamnest": 18, "devetnest": 19})
ORD_RE = "|".join(sorted(ORD_N, key=len, reverse=True))
ITEM = re.compile(r"(?:\bna|\bjoš|\bs|\bsa)\s+(?:(?:(\d{1,2})\s*\.?\s*(?:u\s+)?|(" + ORD_RE + r")\w*\s+(?:u\s+)?)točk"
                  r"|točk\w*\s+(\d{1,2})\s*[a-h]?\b)"
                  r"|^\W*(?:i\s+)?(?:(\d{1,2})\s*\.|(" + ORD_RE + r")\w*)\s+točka\b", re.I)
SUB = re.compile(r"(?:iduć\w*|ilođ\w*|izuć\w*|sljedeć\w*)\s+po[dt]\s*točk\w*[.,]?\s*(.{0,70})|točk\w*\s+(\d{1,2}\s*[a-h])\b[,.]?\s*(.{0,60})",
                 re.I)
CALL = re.compile(r"dajem\w*\s+na\s+(?:glasovanj|usvajanj)|tko\s+je\s+za\b|koje?\s+(?:je\s+)?za\?|\bko\s+je\s+za\b", re.I)
DONE = re.compile(r"(?:us|os|to\s*s|\bs)vojil|jedno\s?glasn|nije\s+(?:us|os)vojen|odbij", re.I)
WORDS = {"nula": 0, "jedan": 1, "jedna": 1, "jednim": 1, "jednog": 1, "jedno": 1, "dva": 2, "dvije": 2, "dvoje": 2,
         "tri": 3, "troje": 3, "četiri": 4, "pet": 5, "šest": 6, "sedam": 7, "osam": 8, "devet": 9, "deset": 10,
         "jedanaest": 11, "dvanaest": 12, "trinaest": 13, "četrnaest": 14, "petnaest": 15, "šesnaest": 16,
         "sedamnaest": 17, "osamnaest": 18, "devetnaest": 19, "dvadeset": 20, "dvadesetjedan": 21}
NUM = r"(\d{1,2}|" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")"
ZA = re.compile(NUM + r"\s+(?:glas\w*\s+|dva\s+slavata\s+)?za(?:\b|(?=[uo]svoj))", re.I)
PROTIV = re.compile(NUM + r"\s+(?:glas\w*\s+)?protiv", re.I)
SUZ = re.compile(NUM + r"\s+(?:glas\w*\s+)?(?:su\s*z?\s*drž|sudrž|suzač)", re.I)


def num(s):
    s = s.lower()
    return int(s) if s.isdigit() else WORDS.get(s)


def parse_result(text):
    """Vote numbers in a chair's readout; None if it has no result."""
    t = re.sub(r"\s+", " ", text)
    za, pr, sz = ([num(m.group(1)) for m in R.finditer(t)] for R in (ZA, PROTIV, SUZ))
    if re.search(r"jedno\s?glasn", t, re.I):
        return {"za": za[-1] if za else None, "protiv": 0, "suzdrzano": 0, "unanimous": 1, "outcome": "usvojeno"}
    if not za:
        return None
    outcome = "nije usvojeno" if re.search(r"nije\s+(?:us|os)vojen|odbij", t, re.I) else "usvojeno"
    return {"za": za[-1], "protiv": pr[-1] if pr else 0, "suzdrzano": sz[-1] if sz else 0, "unanimous": 0,
            "outcome": outcome}


def stems(text):
    return {w[:5] for w in re.findall(r"\w+", text.lower()) if len(w) > 3}


def anchors(segs, n_items, titles=None):
    """{item no: (segment index, char pos)} from the chair's "na N. točku" (monotonic: each next anchor has a higher number)."""
    out, last = {}, 0
    for i, (_, _, text) in enumerate(segs):
        for m in ITEM.finditer(text):
            g = m.group(1) or m.group(3) or m.group(4)
            w = (m.group(2) or m.group(5) or "").lower()
            n = int(g) if g else next(v for o, v in sorted(ORD_N.items(), key=lambda x: -len(x[0])) if w.startswith(o))
            if last < n <= n_items and n <= last + 3 and n not in out:
                out[n], last = (i, m.start()), n
    # an item whose announcement ASR garbled: first segment between its neighbours that repeats its title
    for n in range(2, n_items + 1):
        if n in out or not titles or n not in titles:
            continue
        lo = max([a for k, (a, _) in out.items() if k < n] or [None], key=lambda x: -1 if x is None else x)
        hi = min([a for k, (a, _) in out.items() if k > n] or [None], key=lambda x: 10 ** 9 if x is None else x)
        if lo is None or hi is None:
            continue
        want = stems(titles[n][:160])
        for i in range(lo + 1, hi):
            if len(want & stems(" ".join(x[2] for x in segs[i:i + 2]))) / max(len(want), 1) >= 0.5:
                out[n] = (i, 0)
                break
    return out


def votes(segs):
    """[(segment index, text window, parsed result)] for every readout in a recording."""
    out, last_end = [], -1
    for i, (start, _, text) in enumerate(segs):
        done = DONE.search(text)
        if not done or i <= last_end:
            continue
        # the readout starts at the last call to vote within ~60 s before
        j = i
        while j > 0 and start - segs[j - 1][0] < 60 and j > last_end + 1 and not CALL.search(segs[j][2]):
            j -= 1
        k = i
        # numbers can follow the verb in the next short segment ("usvojili …, pardon, tri suzdržana")
        if i + 1 < len(segs) and re.search(r"pardon|ispravak", segs[i + 1][2], re.I):
            k = i + 1
        window = " ".join(s[2] for s in segs[j:k + 1])
        call_pos = [m.end() for m in CALL.finditer(window)]
        res = parse_result(window[call_pos[-1]:] if call_pos and parse_result(window[call_pos[-1]:]) else window)
        if res:
            out.append((i, done.start(), window, res))
            last_end = k
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS spoken_votes(city TEXT, session INTEGER, item_no INTEGER, sub INTEGER, n INTEGER,
    label TEXT, za INTEGER, protiv INTEGER, suzdrzano INTEGER, unanimous INTEGER, outcome TEXT, video_id TEXT,
    t REAL, quote TEXT, source TEXT);
"""


def build(db: sqlite3.Connection, city="brod"):
    db.executescript(SCHEMA)
    db.execute("DELETE FROM spoken_votes WHERE city = ?", (city,))
    for (session,) in db.execute("SELECT DISTINCT session FROM segments WHERE city = ?", (city,)).fetchall():
        n_items = db.execute("SELECT max(no) FROM items WHERE city = ? AND session = ?", (city, session)).fetchone()[0]
        if not n_items:
            continue
        db.execute("UPDATE items SET video_id = NULL, t_start = NULL, t_vote = NULL, spoken_result = NULL"
                   " WHERE city = ? AND session = ?", (city, session))
        # one timeline over all parts of the session (part 2 continues where part 1 stopped)
        segs, vids = [], []
        for vid, in db.execute("SELECT id FROM videos WHERE city = ? AND session = ? AND transcribed ORDER BY part",
                               (city, session)).fetchall():
            for s in db.execute("SELECT start, end, text FROM segments WHERE video_id = ? ORDER BY start", (vid,)):
                segs.append(s)
                vids.append(vid)
        if not segs:
            continue
        titles = dict(db.execute("SELECT no, title FROM items WHERE city = ? AND session = ? AND sub = 1",
                                 (city, session)).fetchall())
        anc = anchors(segs, n_items, titles)
        for no, (i, _) in anc.items():
            db.execute("UPDATE items SET video_id = ?, t_start = ? WHERE city = ? AND session = ? AND no = ? AND sub = 1",
                       (vids[i], segs[i][0], city, session, no))
        order = sorted((i, pos, no) for no, (i, pos) in anc.items())

        def item_at(i, pos=10 ** 6):
            cur = None
            for a, apos, no in order:
                if (a, apos) <= (i, pos):
                    cur = no
            return cur
        # sub-item labels ("iduću pod točku Trgovačko društvo Vodovod") inside an item
        subs = []
        for i, (_, _, text) in enumerate(segs):
            m = SUB.search(text)
            if m:
                lab = (m.group(1) or ((m.group(2) or "") + " " + (m.group(3) or ""))).strip(" ,.")
                if len(lab) < 8 and i + 1 < len(segs):  # "možemo na iduću pod točku." + name in the next segment
                    lab = segs[i + 1][2][:70].strip(" ,.")
                subs.append((i, lab))
        # the chair's quorum count ("nazočno je 18 vijećnika"): a unanimous vote without a number = all of them
        quorum = [(i, int(m.group(1))) for i, (_, _, x) in enumerate(segs)
                  for m in re.finditer(r"nazočn\w*\s+je\s+(\d{1,2})\s", x, re.I)]
        count, prev = {}, None
        for i, pos, window, r in votes(segs):
            if r["unanimous"] and r["za"] is None:
                q = [n for a, n in quorum if a <= i]
                if q:
                    r["za"] = q[-1]
            no = item_at(i, pos)
            if no is None:
                continue  # minutes of the previous session, agenda: voted before item 1
            if prev and prev[0] == no and vids[i] == prev[1] and segs[i][0] - prev[2] < 8:
                continue  # "18. Jednoglasno." + "konstatiram da smo jednoglasno usvojili": one vote
            prev = (no, vids[i], segs[i][0])
            lab = next((lab for a, lab in reversed(subs) if a <= i and item_at(a) == no), None)
            count[no] = count.get(no, 0) + 1
            db.execute("INSERT INTO spoken_votes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (city, session, no, 1, count[no], lab, r["za"], r["protiv"], r["suzdrzano"], r["unanimous"],
                        r["outcome"], vids[i], segs[i][0], window[-300:], "snimka"))
            db.execute("UPDATE items SET t_vote = ? WHERE city = ? AND session = ? AND no = ? AND sub = 1 AND"
                       " video_id = ?", (segs[i][0], city, session, no, vids[i]))
