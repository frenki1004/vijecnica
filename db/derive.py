"""Derived tables, built after the raw import and item alignment (called from build.py).

minutes_items  official minutes split per agenda item (Zagreb): proposer, presenter, closing word,
               ordered speaker list with turn kinds, vote numbers and the decision sentence
speaker_turns  who speaks when in the recordings, from the chair's cues (db/speakers.py)
promises       commitments in question-hour answers (Zagreb fonograms): who promised what and by when
"""
import json
import re
import sqlite3

from minutes import others_present, parse_zagreb
from promises import extract as extract_promises
from speakers import Roster, detect

SCHEMA = """
CREATE TABLE minutes_items(city TEXT, session INTEGER, no INTEGER, sub INTEGER, proposer TEXT, presenter TEXT,
                           closing TEXT, speakers TEXT, voted INTEGER, za INTEGER, protiv INTEGER, suzdrzano INTEGER,
                           mode TEXT, verb TEXT, decision TEXT, text TEXT, PRIMARY KEY(city, session, no, sub));
CREATE TABLE speaker_turns(id INTEGER PRIMARY KEY, city TEXT, session INTEGER, video_id TEXT, item_no INTEGER,
                           sub INTEGER, start REAL, end REAL, speaker TEXT, role TEXT, kind TEXT, method TEXT,
                           score REAL, cue TEXT);
CREATE INDEX turns_video ON speaker_turns(video_id, start);
CREATE INDEX turns_item ON speaker_turns(city, session, item_no, sub);
CREATE TABLE promises(id INTEGER PRIMARY KEY, city TEXT, session INTEGER, question_id INTEGER, asked_by TEXT,
                      speaker TEXT, topic TEXT, quote TEXT, deadline TEXT, deadline_date TEXT, cue TEXT);
"""

# who answers "gradonačelnik, izvolite" without a name: per city and term
EXECUTIVE = {
    "zagreb": {"mayor": "Tomislav Tomašević", "deputy_f": "Danijela Dolenec", "deputy_m": "Luka Korlaet"},
    "brod": {"mayor": "Mirko Duspara", "deputy_f": None, "deputy_m": None},
    "krk": {"mayor": "Darijo Vasilić", "deputy_f": None, "deputy_m": None},
    "rijeka": {"mayor": "Iva Rinčić", "deputy_f": None, "deputy_m": None},  # deputies Vivoda, Milaković: named when called
}


def build(db: sqlite3.Connection):
    db.executescript(SCHEMA)
    officials = {}
    for city, session, text in db.execute("SELECT city, n, minutes_text FROM sessions").fetchall():
        officials.setdefault(city, {})[session] = others_present(text) if city == "zagreb" else []
        if city != "zagreb" or not text:
            continue
        items = db.execute("SELECT no, sub, title FROM items WHERE city = ? AND session = ? ORDER BY no, sub",
                           (city, session)).fetchall()
        roster = [r[0] for r in db.execute("SELECT name FROM members WHERE city = ?", (city,))] + officials[city][session]
        for x in parse_zagreb(text, items, roster):
            if x["title"] is None:
                continue  # a minutes section with no matching agenda item in the DB
            db.execute("INSERT OR REPLACE INTO minutes_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (city, session, x["no"], x["sub"], x["proposer"], x["presenter"],
                        json.dumps(x["closing"], ensure_ascii=False), json.dumps(x["speakers"], ensure_ascii=False),
                        x["voted"], x["za"], x["protiv"], x["suzdrzano"], x["mode"], x["verb"], x["decision"], x["text"]))

    # speaker turns
    for city, ex in EXECUTIVE.items():
        members = dict(db.execute("SELECT name, party FROM members WHERE city = ?", (city,)).fetchall())
        all_officials = {o for s in officials.get(city, {}).values() for o in s}
        for vid, session in db.execute("SELECT id, session FROM videos WHERE city = ? AND transcribed", (city,)).fetchall():
            offs = officials.get(city, {}).get(session) or all_officials
            people = {**{o: "dužnosnik" for o in offs}, **{v: "dužnosnik" for v in ex.values() if v}, **members}
            roster = Roster(people)
            segs = db.execute("SELECT start, end, text FROM segments WHERE video_id = ? ORDER BY start", (vid,)).fetchall()
            items = db.execute("""SELECT no, sub, t_start FROM items WHERE video_id = ? AND t_start IS NOT NULL
                                  ORDER BY t_start, no, sub""", (vid,)).fetchall()
            starts = sorted({t for _, _, t in items})
            windows = []
            for no, sub, t in items:
                nxt = min([s for s in starts if s > t] or [1e12])
                windows.append((no, sub, t, nxt))
            if not windows:
                windows = [(None, None, 0, 1e12)]
            for no, sub, lo, hi in windows:
                part = [s for s in segs if lo <= s[0] < hi]
                for tt in detect(part, roster, ex["mayor"], ex["deputy_f"], ex["deputy_m"], city):
                    role = "vijećnik" if tt["speaker"] in members else "dužnosnik"
                    db.execute("""INSERT INTO speaker_turns(city, session, video_id, item_no, sub, start, end, speaker,
                                  role, kind, method, score, cue) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (city, session, vid, no, sub, tt["start"], tt["end"], tt["speaker"], role, tt["kind"],
                                tt["method"], tt["score"], tt["cue"][:300]))

    # promises from question-hour fonograms
    rosters = {}
    for qid, city, session, member, question, fon in db.execute(
            "SELECT id, city, session, member, question, fonogram FROM questions WHERE fonogram IS NOT NULL").fetchall():
        date = (db.execute("SELECT date FROM sessions WHERE city = ? AND n = ?", (city, session)).fetchone() or [None])[0]
        if city not in rosters:
            rosters[city] = Roster({**{o: 1 for s in officials.get(city, {}).values() for o in s},
                                    **{m: 1 for m, in db.execute("SELECT name FROM members WHERE city = ?", (city,))}})
        for p in extract_promises(fon, member, date):
            if db.execute("SELECT 1 FROM promises WHERE city = ? AND session = ? AND quote = ?",
                          (city, session, p["quote"])).fetchone():
                continue  # the same answer can be filed under two questions
            full, sc = rosters[city].match(p["speaker"])
            if full and sc >= 0.9 and full.split()[-1][:4].lower() == p["speaker"].split()[-1][:4].lower():
                p["speaker"] = full  # fonogram spelling -> roster spelling ("Daniela" -> "Danijela")
            db.execute("""INSERT INTO promises(city, session, question_id, asked_by, speaker, topic, quote, deadline,
                          deadline_date, cue) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (city, session, qid, member, p["speaker"], re.sub(r"\s+", " ", question or "")[:200], p["quote"], p["deadline"],
                        p["deadline_date"], p["cue"]))
