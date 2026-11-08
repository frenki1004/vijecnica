"""Who speaks when: speaker turns from the chair's cues in the machine transcript.

The chair hands the floor with fixed formulas: "zastupnica Kekin, izvolite", "imate jednu repliku,
zastupnica Odvorčić, izvolite", "neslaganje s replikom, zastupnik Klisović, izvolite", "zastupnica Medved
želi završno u ime predlagatelja", "želi li zamjenica gradonačelnika …, izvolite", and closes a turn with
"hvala (vam) kolegice Medved". Names arrive in any grammatical case and misspelt by ASR ("Odvorić",
"Diokićova"), so a mention is matched to the roster (councillors + officials present) by surname stem
similarity. A turn runs from its cue to the next cue (or the end of the item's debate).

Turn kinds follow the minutes' vocabulary: rasprava, u ime Kluba, replika, neslaganje s replikom,
povreda Poslovnika, obrazlaže (before "otvaram raspravu"), završna riječ.
"""
import difflib
import re
import unicodedata

TITLE = (r"(?i:zastupni\w*|koleg\w*|gospodin\w*|gospođ\w*|vijećni\w*|vijecni\w*|viječni\w*|"
         r"pročelni\w*|ravnatelj\w*|direktor\w*|predsjedni\w*|potpredsjedni\w*)")
NAME = r"((?:[A-ZŠĐČĆŽ][\w'-]+)(?:\s+[A-ZŠĐČĆŽ][\w'-]+){0,2})"
TITLED = re.compile(TITLE + r"\s+" + NAME, re.U)
WANTS = re.compile(TITLE + r"\s+" + NAME + r"\s+(?:želi|ima|traži)\s+(završn\w*|repliku|riječ|neslaganje)", re.U)
REPLY_FROM = re.compile(r"replik\w*\s+(?:od\s+)?" + TITLE + r"\s+" + NAME, re.U)
THANKS = re.compile(r"^\W{0,3}(?:\w+\W+){0,2}?(?i:hvala(?:\s+vam|\s+lijepo|\s+vama)?),?\s+" + TITLE + r"\s+" + NAME, re.U)
MAYOR = re.compile(r"(gradonačelni(?:k|če)|zamjeni(?:ca|k)\s+gradonačelnika)\s*,?\s*(?:[^.?!,]{0,30},\s*)?izvolite", re.I)
CHAIRISH = re.compile(r"prelazimo|predlagatelj je|razmotri|izvolite|želi li|nema primjedbi|točk\w+ dnevn", re.I)
OPEN = re.compile(r"otvaram\s+raspravu", re.I)
CLOSE = re.compile(r"zaključujem\s+raspravu|stavljam\s+na\s+glasovanje", re.I)
# a recess: no one holds the floor across it ("zatražila stanku", "kratku pauzu"); also any silence > 120 s
BREAK = re.compile(r"\b(?:stank|pauz)\w*", re.I)
MAX_GAP = 120
# Slavonski Brod chair: "Iduće pitanje postavlja gospodin X. Izvolite." / "Dalje po klubovima, gospođa X." /
# a bare "Gospodin X." as its own line. ASR spells the call "izvolite" as zvolite/izvolić/izvrlo/izvodite/zovod.
BROD_ASK = re.compile(r"(?i:postavlja)\w*\s+" + TITLE + r"\s+" + NAME, re.U)
BROD_ADDR = re.compile(r"^\W*(?P<thx>(?:zahvaljujem|hvala)\w*\W+)?(?P<go>(?:i\s+)?(?:dalje|idemo|sada?\s+idemo)\b[^.?!]{0,45}?"
                       r"[.,?]?\s+)?(?:(?:imali|ima\s+li)[^.?!]{0,50}[?.,]\s*)?" + TITLE + r"\s+" + NAME, re.U | re.I)
BROD_CALL = re.compile(r"\b(?:i?zvol|izvr|zvrl|izvod|zovod)\w*", re.I)

ENDINGS = ("ovima", "ićem", "iću", "ića", "ovom", "om", "em", "oj", "u", "a", "e", "i", "o")


def norm(s):
    s = unicodedata.normalize("NFKD", s.replace("đ", "dj").replace("Đ", "Dj"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def stem(w):
    w = norm(w)
    for e in ENDINGS:
        if len(w) - len(e) >= 4 and w.endswith(e):
            return w[:-len(e)]
    return w


class Roster:
    def __init__(self, people):
        """people = {full name: role} (role 'member', 'official', …)."""
        self.people = people
        self.keys = []  # (surname stem, full name)
        for full in people:
            toks = full.replace("-", " ").split()
            for t in toks[1:] if len(toks) > 1 else toks:
                self.keys.append((stem(t), norm(t), full))
            self.keys.append((stem(toks[0]), norm(toks[0]), full + "\x00first"))
            if len(toks) > 1:  # ASR splits surnames: "Le Majić" for Lemaić
                self.keys.append((stem(toks[-1]), norm(toks[-1]), full))

    def match_among(self, mention, names, threshold=0.65):
        """Best of a few candidate names (e.g. the ones the chair just announced), with a lower threshold."""
        if not names:
            return None, 0.0
        sub = Roster({n: self.people.get(n) for n in names})
        best, score = None, 0.0
        for t in [t for t in re.split(r"[\s-]+", mention) if len(t) >= 3]:
            for ks, kn, full in sub.keys:
                if full.endswith("\x00first"):
                    continue
                r = max(difflib.SequenceMatcher(None, stem(t), ks).ratio(), difflib.SequenceMatcher(None, norm(t), kn).ratio())
                if r > score:
                    best, score = full, r
        return (best, score) if score >= threshold else (None, score)

    def match(self, mention):
        """Best roster name for 'Odvorić' / 'Klisovića' / 'Matko Dujmović' / 'Rimac Bilušić', or None."""
        toks = [t for t in re.split(r"[\s-]+", mention) if t]
        toks += [a + b for a, b in zip(toks, toks[1:])]  # "Le Majić" -> "LeMajić"
        best, score = None, 0.0
        for t in toks:
            st, nt = stem(t), norm(t)
            if len(nt) < 3:
                continue
            for ks, kn, full in self.keys:
                first = full.endswith("\x00first")
                r = max(difflib.SequenceMatcher(None, st, ks).ratio(), difflib.SequenceMatcher(None, nt, kn).ratio())
                if first:
                    r -= 0.15  # first names alone are weak evidence ("Ivana", "Tomislav")
                if r > score:
                    best, score = full.replace("\x00first", ""), r
        # full name mentioned: both tokens agree -> strong
        return (best, score) if score >= 0.78 else (None, score)


def kind_from(text):
    t = text.lower()
    if "neslaganj" in t:
        return "neslaganje s replikom"
    if "replik" in t:
        return "replika"
    if "povred" in t and "poslovnik" in t:
        return "povreda Poslovnika"
    t = OPEN.split(t)[-1]  # only what the chair said after "otvaram raspravu"
    if "završn" in t or "zaključn" in t:
        return "završna riječ"
    if re.search(r"obrazlo\w*\s+(?:prijedlog|izvješ|zaključ)", t):
        return "obrazlaže"
    if re.search(r"u\s+ime\s+klub", t):
        return "u ime Kluba"
    return "rasprava"


def detect(segs, roster, mayor=None, deputy_f=None, deputy_m=None, city="zagreb"):
    """segs = [(start, end, text)] of one item's debate, in time order.
    Returns turns [{start, end, speaker, kind, cue, method, score}] with end filled in."""
    events = []  # (t, kind, name, cue, method, score)

    def pick(mention, t):
        name, sc = roster.match(mention)
        if city == "brod":  # the chair just named X in full: a garbled repeat within 2 min is X too
            alt, asc = roster.match_among(mention, [e[2] for e in events if t - e[0] < 120 and e[5] >= 0.95])
            if alt:
                return alt, asc
        return name, sc
    opened = None
    closed = None
    club_parties = set()
    phase = "rasprava"  # the chair first takes club speakers, then "pojedinačna rasprava"
    for i, (start, end, text) in enumerate(segs):
        if opened is None and OPEN.search(text):
            opened = start
        if CLOSE.search(text):
            closed = start
        prev = segs[i - 1][2][-160:] if i else ""
        marks = sorted([(m.start(), "phase", "rasprava") for m in re.finditer(r"pojedinačn", text, re.I)] +
                       [(m.start(), "phase", "u ime Kluba")
                        for m in re.finditer(r"u\s+ime\s+klubova|javlja\s+u\s+ime\s+klub", text, re.I)] +
                       [(m.start(), "call", None) for m in re.finditer(r"\bizvolite", text)])
        for pos, what, val in marks:
            if what == "phase":
                phase = val
                continue
            # the name is the last "title + Name" in the 90 characters before "izvolite" that is on the roster
            lo = max(0, pos - 90)
            win = text[lo:pos]
            if re.search(r"stank", win, re.I):
                continue  # a club asking for a recess is not a debate turn
            hit = None
            for m in reversed(list(TITLED.finditer(win))):
                name, sc = pick(m.group(1), start)
                if name:
                    hit = (m, name, sc)
                    break
            if not hit:
                continue
            m, name, sc = hit
            ctx = (prev[-100:] if lo + m.start() < 40 else "") + " " + text[max(0, lo + m.start() - 110):pos + 8]
            k = kind_from(ctx)
            if k == "rasprava" and phase == "u ime Kluba":
                party = roster.people.get(name)
                if party and party in club_parties:
                    phase = "rasprava"  # a second speaker of the same club: club round is over
                else:
                    k = phase
                    club_parties.add(party)
            events.append((start, k, name, text[max(0, lo + m.start() - 60):pos + 8], "poziv", sc))
        for m in WANTS.finditer(text):
            name, sc = roster.match(m.group(1))
            if name:
                events.append((start, kind_from(m.group(0)), name, m.group(0), "poziv", sc))
        for m in REPLY_FROM.finditer(text):
            name, sc = roster.match(m.group(1))
            if name:
                events.append((start + 0.5, "replika", name, m.group(0), "poziv", sc))
        for m in MAYOR.finditer(text):
            who = m.group(1).lower()
            name = mayor if who.startswith("gradonačelni") else (deputy_f if "ca" in who.split()[0][-2:] else deputy_m)
            if name:
                ctx = text[max(0, m.start() - 120):m.end()]
                k = kind_from(ctx)
                events.append((start, "završna riječ" if k == "rasprava" and re.search(r"riječ|želi li", ctx, re.I) else k,
                               name,
                               ctx[-120:], "poziv", 1.0))
        if city == "brod":
            for m in BROD_ASK.finditer(text):
                name, sc = pick(m.group(1), start)
                if name:
                    events.append((start, "vijećničko pitanje", name, text[max(0, m.start() - 40):m.end() + 12], "poziv", sc))
            m = BROD_ADDR.match(text)
            # "Zahvaljujem, gospodine X." alone closes X's turn (THANKS below); with "dalje"/"izvolite" it is a call.
            # Without a call word only a bare chair line counts ("Gospodin Delić."), never a vocative/dative
            # inside someone's speech ("gospođo Lemaić, ako…", "gospođi Maduni", "kolegi X je pitala").
            called = bool(BROD_CALL.search(text[m.end():m.end() + 25])) if m else False
            title = m.group(0)[:m.start(m.re.groups) - m.start()].split()[-1].lower() if m else ""
            bare = (m and not m.group("thx") and title in ("gospodin", "gospođa", "gospodina")
                    and len(text.split()) <= 6)
            if m and (called or bare or (m.group("go") and title.startswith("gospo"))):
                name, sc = pick(m.groups()[-1], start)
                if name and len(text.split()) <= 14:
                    k = "u ime Kluba" if re.search(r"klub", text, re.I) else kind_from(text)
                    events.append((start, k, name, text[:120], "poziv", sc))
        m = THANKS.search(text)
        if m:
            name, sc = roster.match(m.group(1))
            if name:
                events.append((start, None, name, m.group(0), "zahvala", sc))
    events.sort(key=lambda e: e[0])
    turns = []
    for t, kind, name, cue, method, sc in events:
        if method == "zahvala":
            # "hvala, kolegice X" closes X's turn: if no open turn by X, X spoke since the previous cue
            if turns and turns[-1]["speaker"] == name:
                continue
            if any(tt["speaker"] == name and t - tt["start"] < 30 for tt in turns[-2:]):
                continue
            if turns:
                begin = turns[-1]["start"] + 5
            else:  # first speaker of the item: skip the chair's announcement of the item
                begin = next((a for a, _, x in segs[1:] if a < t and not CHAIRISH.search(x)), segs[0][0] if segs else t)
            if begin >= t:
                begin = t - 1
            turns.append({"start": begin, "speaker": name, "kind": "rasprava", "cue": cue, "method": "zahvala",
                          "score": round(sc, 2), "end_hint": t})
            continue
        if turns and turns[-1]["speaker"] == name and t - turns[-1]["start"] < 25:
            continue  # same call spotted twice (e.g. "zastupnik Krasić, zastupnik Krasić u ime Kluba…")
        turns.append({"start": t, "speaker": name, "kind": kind, "cue": cue, "method": method, "score": round(sc, 2)})
    turns.sort(key=lambda x: x["start"])
    last = segs[-1][1] if segs else 0
    breaks = sorted([segs[i - 1][1] for i in range(1, len(segs)) if segs[i][0] - segs[i - 1][1] > MAX_GAP] +
                    [a for a, _, x in segs if BREAK.search(x)])
    for i, tt in enumerate(turns):
        nxt = turns[i + 1]["start"] if i + 1 < len(turns) else (closed if closed and closed > tt["start"] else last)
        tt["end"] = min(nxt, tt.pop("end_hint", nxt)) if "end_hint" in tt else nxt
        brk = next((b for b in breaks if b > tt["start"] + 5), None)
        if brk is not None and brk < tt["end"]:
            tt["end"] = brk  # recess or long silence: the turn is over
        if tt["kind"] != "replika" and opened is not None and tt["start"] < opened:
            tt["kind"] = "obrazlaže"
        # someone who already spoke answering right after a replika = "neslaganje s replikom"
        if (tt["kind"] == "rasprava" and i and turns[i - 1]["kind"] == "replika"
                and any(x["speaker"] == tt["speaker"] for x in turns[:i - 1])):
            tt["kind"] = "neslaganje s replikom"
    return turns
