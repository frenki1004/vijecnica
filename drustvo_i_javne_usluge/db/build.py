"""Build data/vijecnica.db from every city's JSON (recordings, transcripts, session documents).

Cities: zagreb (data/videos.json, data/transcripts, data/docs); brod, krk and rijeka (data/<city>/recordings.json,
data/<city>/transcripts, data/<city>/docs; Rijeka's recordings are YouTube, the others MP3). Rebuilt from scratch each run (a few seconds); the JSON
files are the source of truth.
"""
import json
import os
import re
import sqlite3
from pathlib import Path

from align import align
from brod_audio import build as brod_audio
from derive import build as derive

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = Path(os.environ["VIJECNICA_DB"]) if os.environ.get("VIJECNICA_DB") else DATA / "vijecnica.db"  # override: check_rebuild.sh
TERM_START = "20250601"  # 2025-2029 term; session numbers restart each term

CITIES = {
    "zagreb": {"name": "Zagreb", "body": "Gradska skupština Grada Zagreba", "dir": DATA,
               "site": "https://web.zagreb.hr"},
    "brod": {"name": "Slavonski Brod", "body": "Gradsko vijeće Grada Slavonskog Broda", "dir": DATA / "brod",
             "site": "https://www.slavonski-brod.hr"},
    "krk": {"name": "Krk", "body": "Gradsko vijeće Grada Krka", "dir": DATA / "krk", "site": "https://www.grad-krk.hr"},
    "rijeka": {"name": "Rijeka", "body": "Gradsko vijeće Grada Rijeke", "dir": DATA / "rijeka",
               "site": "https://www.rijeka.hr"},
}
AUDIO_VOTES = ("brod", "krk")  # chair reads vote totals aloud; brod_audio.py finds them in the transcript

SCHEMA = """
CREATE TABLE cities(id TEXT PRIMARY KEY, name TEXT, body TEXT, site TEXT);
CREATE TABLE sessions(city TEXT, n INTEGER, date TEXT, title TEXT, url TEXT, minutes_url TEXT, minutes_text TEXT,
                      PRIMARY KEY(city, n));
CREATE TABLE videos(id TEXT PRIMARY KEY, city TEXT, session INTEGER, upload_date TEXT, title TEXT, duration INTEGER,
                    part INTEGER, transcribed INTEGER, speech_seconds REAL, kind TEXT, url TEXT);
CREATE TABLE segments(id INTEGER PRIMARY KEY, video_id TEXT, city TEXT, session INTEGER, start REAL, end REAL,
                      text TEXT);
CREATE TABLE items(city TEXT, session INTEGER, no INTEGER, sub INTEGER, title TEXT, full_title TEXT, proposer TEXT,
                   status TEXT, committees TEXT, url TEXT, za INTEGER, protiv INTEGER, suzdrzano INTEGER,
                   result TEXT, attachments TEXT, video_id TEXT, t_start REAL, t_vote REAL, spoken_result TEXT,
                   totals_note TEXT,
                   PRIMARY KEY(city, session, no, sub));
CREATE TABLE members(city TEXT, name TEXT, party TEXT, PRIMARY KEY(city, name));
CREATE TABLE attendance(city TEXT, session INTEGER, member TEXT, present INTEGER);
CREATE TABLE votes(city TEXT, session INTEGER, item_no INTEGER, sub INTEGER, member TEXT, vote TEXT,
                   source TEXT DEFAULT 'oznaka');  -- oznaka = X in the PDF column; bez_oznake = name row with no X
CREATE TABLE questions(id INTEGER PRIMARY KEY, city TEXT, session INTEGER, member TEXT, party TEXT, question TEXT,
                       to_whom TEXT, answer TEXT, answered_by TEXT, fonogram TEXT, url TEXT);
CREATE VIRTUAL TABLE segments_fts USING fts5(text, content='segments', content_rowid='id',
                                             tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE items_fts USING fts5(title, full_title, proposer, content='items',
                                          tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE questions_fts USING fts5(question, fonogram, member, content='questions', content_rowid='id',
                                              tokenize='unicode61 remove_diacritics 2');
CREATE INDEX seg_video ON segments(video_id, start);
CREATE INDEX votes_member ON votes(city, member);
"""


def recordings(city, base):
    """[(recording dict, session, part, kind, url)] for a city, newest term only."""
    if city == "zagreb":
        videos = [v for v in json.loads((base / "videos.json").read_text()) if v["upload_date"] >= TERM_START]
        # part = order of the session's videos by upload date (a session spans 2-4 streams)
        by_session = {}
        for v in sorted(videos, key=lambda v: (v["upload_date"], v.get("release_timestamp") or 0)):
            by_session.setdefault(v["session"], []).append(v)
        return [(v, s, i, "youtube", f"https://www.youtube.com/watch?v={v['id']}")
                for s, vs in by_session.items() for i, v in enumerate(vs, 1)]
    f = base / "recordings.json"
    rows = json.loads(f.read_text()) if f.exists() else []
    return [({**r, "upload_date": (r["date"] or "").replace("-", ""), "duration": r.get("duration")},
             r["session"], r["part"], r.get("kind", "audio"), r["url"]) for r in rows]


def main():
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    for city, c in CITIES.items():
        base = c["dir"]
        if not (base / "docs").exists():  # collector not run yet
            continue
        db.execute("INSERT INTO cities VALUES(?,?,?,?)", (city, c["name"], c["body"], c["site"]))
        for v, s, part, kind, url in recordings(city, base):
            t = base / "transcripts" / f"{v['id']}.json"
            tr = json.loads(t.read_text()) if t.exists() else None
            db.execute("INSERT INTO videos VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (v["id"], city, s, v["upload_date"], v["title"],
                        v.get("duration") or (tr and int(tr.get("duration") or 0)) or None, part, bool(tr),
                        tr and tr.get("speech_seconds"), kind, url))
            for seg in (tr or {}).get("segments", []):
                text = re.sub(r"…\s*", "", seg["text"]).strip()
                if text:
                    db.execute("INSERT INTO segments(video_id, city, session, start, end, text) VALUES(?,?,?,?,?,?)",
                               (v["id"], city, s, seg["start"], seg["end"], text))

        for f in sorted((base / "docs").glob("session_*.json")):
            d = json.loads(f.read_text())
            n = d["session"]
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                       (city, n, d.get("date"), d["title"], d.get("url"), d.get("minutes_url"), d.get("minutes_text")))
            seen = {}
            for it in d["items"]:
                v = it.get("vote") or {}
                if v.get("source") == "vijest" and not v.get("totals_note"):  # Krk: minutes not out yet
                    v["totals_note"] = {"kind": "vijest", "text": "Zbroj iz gradske vijesti o sjednici, zapisnik još nije "
                                        "objavljen" + (f" ({v['note']})" if v.get("note") else "")
                                        + ("; protiv i suzdržani nisu navedeni" if v.get("protiv") is None else "") + ".",
                                        "quote": v.get("quote")}
                # several items can share a number (e.g. 28 = three sponsorship decisions): sub = 1, 2, 3
                sub = seen[it["no"]] = seen.get(it["no"], 0) + 1
                db.execute("INSERT INTO items(city, session, no, sub, title, full_title, proposer, status, committees,"
                           " url, za, protiv, suzdrzano, result, attachments, totals_note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (city, n, it["no"], sub, it["title"], it.get("full_title"), it.get("proposer", ""),
                            it.get("status"), it.get("committees"), it.get("url"), v.get("za"), v.get("protiv"),
                            v.get("suzdrzano"), v.get("result"), json.dumps(it["attachments"], ensure_ascii=False),
                            json.dumps(v["totals_note"], ensure_ascii=False) if v.get("totals_note") else None))
                for m, vote in v.get("members", {}).items():
                    db.execute("INSERT INTO votes(city, session, item_no, sub, member, vote) VALUES(?,?,?,?,?,?)",
                               (city, n, it["no"], sub, m, vote))
            for a in d["attendance"]:
                db.execute("INSERT OR IGNORE INTO members VALUES(?,?,?)", (city, a["name"], a.get("party")))
                if a.get("party"):
                    db.execute("UPDATE members SET party = ? WHERE city = ? AND name = ?", (a["party"], city, a["name"]))
                db.execute("INSERT INTO attendance VALUES(?,?,?,?)", (city, n, a["name"], a["present"]))
            for q in d["questions"]:
                db.execute("INSERT INTO questions(city, session, member, party, question, to_whom, answer, answered_by,"
                           " fonogram, url) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (city, n, q["name"], q["party"], q["question"], q.get("to"), q.get("answer"),
                            q.get("answered_by"), q.get("fonogram"), q["url"]))
        parties = base / "members.json"  # optional city roster with parties
        if parties.exists():
            for m in json.loads(parties.read_text()):
                if m.get("status") and not db.execute("SELECT 1 FROM members WHERE city = ? AND name = ?",
                                                      (city, m["name"])).fetchone():
                    continue  # Rijeka: mandate paused/ended and never on an attendance list -> not a councillor here
                db.execute("INSERT OR IGNORE INTO members VALUES(?,?,?)", (city, m["name"], m.get("party")))
                db.execute("UPDATE members SET party = ? WHERE city = ? AND name = ?", (m.get("party"), city, m["name"]))

    # The roll-call PDF prints "Odsutan" for everyone without a vote, including members who were in the
    # session that day but did not vote. Those are "nije_glasovao", not absent (attendance list decides).
    db.execute("""UPDATE votes SET vote = 'nije_glasovao' WHERE vote = 'odsutan' AND EXISTS (
                    SELECT 1 FROM attendance a WHERE a.city = votes.city AND a.session = votes.session
                    AND a.member = votes.member AND a.present = 1)""")
    # The PDF also has name rows with NO mark in any column (e.g. Zagreb 14/6: Ante Deur, Dragana Turkalj, …,
    # present that day). The parser keeps only marked rows, so those members had no vote row at all (3,592
    # rows of present members, round-4 judge). Every item with a roll call gets one row per member on that
    # session's attendance list: no row -> nije_glasovao if present, odsutan if not; source = 'bez_oznake'.
    db.execute("""INSERT INTO votes(city, session, item_no, sub, member, vote, source)
                  SELECT i.city, i.session, i.no, i.sub, a.member,
                         CASE WHEN a.present THEN 'nije_glasovao' ELSE 'odsutan' END, 'bez_oznake'
                  FROM items i JOIN attendance a ON a.city = i.city AND a.session = i.session
                  WHERE EXISTS (SELECT 1 FROM votes v WHERE v.city = i.city AND v.session = i.session
                                AND v.item_no = i.no AND v.sub = i.sub)
                    AND NOT EXISTS (SELECT 1 FROM votes v WHERE v.city = i.city AND v.session = i.session
                                    AND v.item_no = i.no AND v.sub = i.sub AND v.member = a.member)""")
    # check: roll size = attendance roster size for every item with a roll call
    bad = db.execute("""SELECT i.city, i.session, i.no, i.sub,
                               (SELECT count(*) FROM votes v WHERE v.city = i.city AND v.session = i.session
                                AND v.item_no = i.no AND v.sub = i.sub) AS roll,
                               (SELECT count(*) FROM attendance a WHERE a.city = i.city AND a.session = i.session) AS roster
                        FROM items i WHERE EXISTS (SELECT 1 FROM votes v WHERE v.city = i.city AND v.session = i.session
                                                   AND v.item_no = i.no AND v.sub = i.sub)""").fetchall()
    bad = [b for b in bad if b[4] != b[5]]
    print("roll == roster for every item with a roll call" if not bad else f"roll != roster: {bad[:10]}")
    align(db)
    for city in AUDIO_VOTES:  # item starts + spoken vote results (source='snimka') from the chair's words
        brod_audio(db, city)
    derive(db)
    for t in ("segments_fts", "items_fts", "questions_fts"):
        db.execute(f"INSERT INTO {t}({t}) VALUES('rebuild')")
    db.commit()
    for city in CITIES:
        stats = {t: db.execute(f"SELECT count(*) FROM {t} WHERE city = ?", (city,)).fetchone()[0]
                 for t in ("sessions", "videos", "segments", "items", "votes", "questions", "minutes_items",
                           "speaker_turns", "promises", "spoken_votes")}
        stats["items_in_video"] = db.execute("SELECT count(*) FROM items WHERE city = ? AND t_start IS NOT NULL",
                                             (city,)).fetchone()[0]
        stats["transcribed"] = db.execute("SELECT count(*) FROM videos WHERE city = ? AND transcribed",
                                          (city,)).fetchone()[0]
        print(city, stats)
    db.close()
    tmp.replace(DB)


if __name__ == "__main__":
    main()
