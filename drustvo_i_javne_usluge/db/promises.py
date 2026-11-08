"""Promise tracker: commitments in the question-hour answers (Zagreb fonograms).

A fonogram is the official verbatim record: speaker headers in capitals ("TOMISLAV TOMAŠEVIĆ:") followed
by "- text". Answers are the turns of anyone who is not the asking councillor or the chair. A sentence
is a commitment when it speaks in the future tense / of plans ("ćemo", "bit će", "planiramo",
"očekujemo", "krenut će") and either names a time ("do kraja godine", "iduće godine", "u 2027.",
"na proljeće") or uses a strong commitment verb. The deadline is turned into an approximate date
(end of the named period) so overdue promises can be listed.
"""
import calendar
import re
import unicodedata
from datetime import date

HEADER = re.compile(r"^\s*([A-ZŠĐČĆŽ][A-ZŠĐČĆŽ .\-]{3,60}):\s*$", re.M)
FUTURE = re.compile(r"\b(ćemo|će|ću|planiramo|planira|plan je|očekujemo|očekuje se|namjeravamo|predviđ\w+|"
                    r"krenut\w*|započet\w*|završit\w*|uskoro)\b", re.I)
NEG = re.compile(r"\b(nećemo|neće|nećete|ne ćemo|ne planiramo)\b", re.I)
STRONG = re.compile(r"\b(ćemo\s+(?:\w+\s+){0,2}(?:izgradit|uredit|otvorit|uvest|osigurat|raspisat|pokrenut|"
                    r"donijet|završit|započet|nabavit|postavit|riješit|obnovit|realizirat|uputit|predložit|"
                    r"zaposlit|povećat|smanjit|sanirat|proširit)\w*|bit će (?:gotov|završen|otvoren|izgrađen|uređen|"
                    r"raspisan|riješen|postavljen|realiziran|predstavljen|upućen|donesen)\w*)", re.I)
MONTHS = {"siječ": 1, "veljač": 2, "ožuj": 3, "trav": 4, "svib": 5, "lipan": 6, "lipnj": 6, "srpan": 7, "srpnj": 7,
          "kolovoz": 8, "rujan": 9, "rujn": 9, "listopad": 10, "studen": 11, "prosin": 12}
WHEN = re.compile(r"(do kraja (?:ove |iduće |sljedeće |naredne )?godine|do kraja (?:ovog |idućeg |sljedećeg )?mjeseca|"
                  r"(?:u|do|tijekom|krajem|početkom)\s+(?:idućem|sljedećem|narednom|idućeg|sljedećeg|ovom|ovog)\s+mjesec\w*|"
                  r"(?:iduće|sljedeće|naredne|slijedeće)\s+godine|(?:iduć|sljedeć|naredn)\w+\s+tjed\w+|"
                  r"(?:do|u|tijekom|krajem|početkom|sredinom)\s+20[23]\d\.?(?:\s+godin\w+)?|"
                  r"(?:na|do|tijekom|ovog|ovo|iduće|iduć\w+|sljedeć\w+)\s+(?:proljeć\w+|ljet\w+|jesen\w*|zim\w+)|"
                  r"(?:do|u|krajem|početkom|tijekom|sredinom)\s+(?:(?:kraja|početka|sredine)\s+)?(?:siječnj|veljač|ožujk|travnj|svibnj|lipnj|srpnj|"
                  r"kolovoz|rujn|listopad|studen|prosin)\w*(?:\s+20[23]\d)?|"
                  r"u\s+(?:prvom|drugom|trećem|četvrtom|zadnjem)\s+kvartal\w*(?:\s+(?:iduće|sljedeće)\s+godine)?|"
                  r"do kraja mandata|(?:u\s+)?narednih\s+(?:nekoliko\s+)?(?:\w+\s+)?(?:mjeseci|tjedana|dana)|uskoro|"
                  r"što prije|ove godine|ove jeseni|ovog ljeta|ove zime)", re.I)


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).upper().strip()


def end_of_month(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def deadline_date(phrase, said):
    """Approximate last day of the named period, relative to the session date (YYYY-MM-DD)."""
    if not said:
        return None
    y, m = int(said[:4]), int(said[5:7])
    p = phrase.lower()
    yr = re.search(r"20[23]\d", p)
    year = int(yr.group()) if yr else (y + 1 if re.search(r"iduć|sljedeć|naredn|slijedeć", p) and "godin" in p else y)
    for k, mm in MONTHS.items():
        if k in p:
            yy = int(yr.group()) if yr else (y if mm >= m else y + 1)
            return end_of_month(yy, mm).isoformat()
    if "mjesec" in p:
        if re.search(r"iduć|sljedeć|naredn", p):
            mm, yy = (m % 12) + 1, y + (m == 12)
            return end_of_month(yy, mm).isoformat()
        return end_of_month(y, m).isoformat()
    if "tjed" in p:
        return None
    for k, (mm, dd) in {"proljeć": (6, 20), "ljet": (9, 22), "jesen": (12, 20), "zim": (3, 20)}.items():
        if k in p:
            yy = year if (yr or re.search(r"iduć|sljedeć|naredn", p)) else y
            if k == "zim" and not yr:
                yy = y + 1
            return date(yy if (yy, mm) >= (y, m) else yy + 1, mm, dd).isoformat()
    if "kvartal" in p:
        q = {"prvom": 3, "drugom": 6, "trećem": 9, "četvrtom": 12, "zadnjem": 12}
        mm = next((v for k, v in q.items() if k in p), 12)
        return end_of_month(year, mm).isoformat()
    if "mandata" in p:
        return "2029-06-01"
    if "godin" in p or yr:
        if "početk" in p:  # "početkom 2026." = early in the year, not its end
            return date(year, 3, 31).isoformat()
        if "sredin" in p:
            return date(year, 6, 30).isoformat()
        return date(year, 12, 31).isoformat()
    return None


def turns(fon):
    """[(SPEAKER, text)] from a fonogram."""
    hs = list(HEADER.finditer(fon or ""))
    return [(h.group(1).strip(), fon[h.end():hs[i + 1].start() if i + 1 < len(hs) else len(fon)])
            for i, h in enumerate(hs)]


def sentences(text):
    t = re.sub(r"\s+", " ", re.sub(r"^\s*-\s*", "", text, flags=re.M)).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZŠĐČĆŽ0-9„\"])", t) if s.strip()]


def extract(fon, asked_by, said_date):
    asker = norm(asked_by or "")
    ts = turns(fon)
    if not ts:
        return []
    chair = ts[1][0] if len(ts) > 1 and len(ts[1][1]) < 250 else None
    out = []
    for speaker, text in ts:
        if norm(speaker) == asker or speaker == chair or len(text) < 200:
            continue
        for s in sentences(text):
            if len(s) < 30 or s.endswith("?") or NEG.search(s) or not FUTURE.search(s):
                continue
            w = WHEN.search(s)
            strong = STRONG.search(s)
            if not (w or strong):
                continue
            dd = deadline_date(w.group(0), said_date) if w else None
            if dd and said_date and dd < said_date:
                continue  # "u listopadu 2023" said in 2026: a reference back, not a commitment
            out.append({"speaker": speaker.title(), "quote": s[:600],
                        "deadline": w.group(0) if w else None,
                        "deadline_date": dd,
                        "cue": (strong or FUTURE.search(s)).group(0)})
    return out
