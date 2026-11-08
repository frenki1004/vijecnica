"""First analysis pass over data/vijecnica.db. Prints markdown: every table is preceded by the SQL behind it.

  .venv/bin/python analysis/analyze.py [path/to/db] > analysis/results.md
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("VIJECNICA_DB", ROOT / "data" / "vijecnica.db"))
db = sqlite3.connect(DB)

Q = {}

Q["1. Stats per city"] = """
SELECT c.id AS city,
  (SELECT count(*) FROM sessions s WHERE s.city=c.id) AS sessions,
  (SELECT count(*) FROM items i WHERE i.city=c.id) AS items,
  (SELECT count(*) FROM items i WHERE i.city=c.id AND i.za IS NOT NULL) AS items_with_totals,
  (SELECT count(*) FROM votes v WHERE v.city=c.id) AS vote_rows,
  (SELECT count(DISTINCT session||'/'||item_no||'/'||sub) FROM votes v WHERE v.city=c.id) AS items_roll_call,
  (SELECT count(*) FROM members m WHERE m.city=c.id) AS members,
  (SELECT count(*) FROM attendance a WHERE a.city=c.id) AS attendance_rows,
  (SELECT count(DISTINCT session) FROM attendance a WHERE a.city=c.id) AS sessions_w_attendance,
  (SELECT count(*) FROM questions q WHERE q.city=c.id) AS questions,
  (SELECT count(*) FROM videos v WHERE v.city=c.id) AS recordings,
  (SELECT count(*) FROM videos v WHERE v.city=c.id AND v.transcribed) AS transcribed,
  (SELECT count(*) FROM segments s WHERE s.city=c.id) AS segments,
  (SELECT count(*) FROM speaker_turns t WHERE t.city=c.id) AS speaker_turns,
  (SELECT count(*) FROM spoken_votes t WHERE t.city=c.id) AS spoken_votes,
  (SELECT count(*) FROM promises p WHERE p.city=c.id) AS promises
FROM cities c"""

Q["1b. Sessions per city: items, totals, attendance, questions, minutes"] = """
SELECT s.city, s.n, s.date,
  (SELECT count(*) FROM items i WHERE i.city=s.city AND i.session=s.n) AS items,
  (SELECT count(*) FROM items i WHERE i.city=s.city AND i.session=s.n AND i.za IS NOT NULL) AS w_totals,
  (SELECT count(*) FROM attendance a WHERE a.city=s.city AND a.session=s.n) AS roster,
  (SELECT sum(present) FROM attendance a WHERE a.city=s.city AND a.session=s.n) AS present,
  (SELECT count(*) FROM questions q WHERE q.city=s.city AND q.session=s.n) AS questions,
  s.minutes_text IS NOT NULL AS minutes
FROM sessions s ORDER BY s.city, s.n"""

Q["2. Unanimity rate (items with published totals)"] = """
SELECT city, count(*) AS voted_items,
  sum(protiv=0 AND suzdrzano=0) AS unanimous,
  round(100.0*sum(protiv=0 AND suzdrzano=0)/count(*),1) AS unanimous_pct,
  sum(protiv=0) AS no_against, round(100.0*sum(protiv=0)/count(*),1) AS no_against_pct,
  sum(result NOT LIKE '%usvojen%' OR za <= protiv) AS not_adopted_or_za_le_protiv
FROM items WHERE za IS NOT NULL AND protiv IS NOT NULL AND suzdrzano IS NOT NULL GROUP BY city"""

Q["3. Closest votes (smallest za - (protiv+suzdrzano))"] = """
SELECT city, session, no, sub, za, protiv, suzdrzano, za-protiv-suzdrzano AS margin, result, substr(title,1,90) AS title
FROM items WHERE za IS NOT NULL AND protiv IS NOT NULL AND (protiv+suzdrzano) > 0
ORDER BY city, za-protiv-suzdrzano, za-protiv LIMIT 30"""

Q["3b. Items not adopted"] = """
SELECT city, session, no, sub, za, protiv, suzdrzano, result, substr(title,1,100) AS title
FROM items WHERE result IS NOT NULL AND result NOT LIKE '%usvojen%' ORDER BY city, session, no"""

Q["4. Party cohesion, Zagreb roll call (share of a party's cast votes that match the party's majority vote)"] = """
WITH cast AS (SELECT v.session, v.item_no, v.sub, m.party, v.vote, count(*) c
              FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
              WHERE v.city='zagreb' AND v.vote IN ('za','protiv','suzdrzan')
              GROUP BY 1,2,3,4,5),
     pi AS (SELECT session, item_no, sub, party, sum(c) n, max(c) top FROM cast GROUP BY 1,2,3,4)
SELECT party, count(*) AS items, sum(n) AS cast_votes,
       round(100.0*sum(top)/sum(n),1) AS cohesion_pct,
       sum(top<n) AS items_with_split
FROM pi GROUP BY party ORDER BY cohesion_pct"""

Q["4b. Party majority line per item: how often each party's majority voted za / protiv / suzdrzan (Zagreb)"] = """
WITH cast AS (SELECT v.session, v.item_no, v.sub, m.party, v.vote, count(*) c
              FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
              WHERE v.city='zagreb' AND v.vote IN ('za','protiv','suzdrzan') GROUP BY 1,2,3,4,5),
     rk AS (SELECT *, row_number() OVER (PARTITION BY session,item_no,sub,party ORDER BY c DESC) r FROM cast)
SELECT party, count(*) items, sum(vote='za') za, sum(vote='protiv') protiv, sum(vote='suzdrzan') suzdrzan,
       round(100.0*sum(vote='za')/count(*),1) za_pct
FROM rk WHERE r=1 GROUP BY party ORDER BY za_pct"""

Q["4c. Councillors most often voting against their own party's majority (Zagreb)"] = """
WITH cast AS (SELECT v.session, v.item_no, v.sub, m.party, v.vote, count(*) c
              FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
              WHERE v.city='zagreb' AND v.vote IN ('za','protiv','suzdrzan') GROUP BY 1,2,3,4,5),
     rk AS (SELECT *, row_number() OVER (PARTITION BY session,item_no,sub,party ORDER BY c DESC) r FROM cast)
SELECT v.member, m.party, count(*) AS against_party
FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
JOIN rk ON rk.session=v.session AND rk.item_no=v.item_no AND rk.sub=v.sub AND rk.party=m.party AND rk.r=1
WHERE v.city='zagreb' AND v.vote IN ('za','protiv','suzdrzan') AND v.vote != rk.vote
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15"""

Q["5. Attendance per councillor: lowest 15 (sessions present / on roster)"] = """
SELECT a.city, a.member, m.party, sum(a.present) AS present, count(*) AS on_roster,
       round(100.0*sum(a.present)/count(*),1) AS pct
FROM attendance a LEFT JOIN members m ON m.city=a.city AND m.name=a.member
GROUP BY 1,2 HAVING count(*) >= 2 ORDER BY pct, on_roster DESC LIMIT 15"""

Q["5b. Attendance rate per city and party"] = """
SELECT a.city, coalesce(m.party,'?') party, count(DISTINCT a.member) members, sum(a.present) present, count(*) rows,
       round(100.0*sum(a.present)/count(*),1) pct
FROM attendance a LEFT JOIN members m ON m.city=a.city AND m.name=a.member GROUP BY 1,2 ORDER BY 1, pct"""

Q["5c. Present but did not vote (Zagreb): share of roll-call rows of present members with no vote, per councillor"] = """
SELECT v.member, m.party, sum(v.vote='nije_glasovao') AS not_voted,
       sum(v.vote!='odsutan') AS rows_present,
       round(100.0*sum(v.vote='nije_glasovao')/sum(v.vote!='odsutan'),1) pct
FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
WHERE v.city='zagreb' GROUP BY 1,2 HAVING rows_present > 20 ORDER BY pct DESC LIMIT 15"""

Q["5d. Not-voting by party (Zagreb)"] = """
SELECT m.party, sum(v.vote='nije_glasovao') not_voted, sum(v.vote!='odsutan') rows_present,
       round(100.0*sum(v.vote='nije_glasovao')/sum(v.vote!='odsutan'),1) pct
FROM votes v JOIN members m ON m.city=v.city AND m.name=v.member
WHERE v.city='zagreb' GROUP BY 1 ORDER BY pct DESC"""

# keyword topics: first match wins, on the item title (lowercased)
TOPICS = [
    ("proračun / financije", ["proračun", "financijsk", "zaduživ", "kredit", "porez", "naknad"]),
    ("prostorno planiranje / urbanizam", ["prostorn", "urbanist", "detaljn", "generaln", "plan uređenja"]),
    ("komunalno / promet / infrastruktura", ["komunal", "promet", "parkir", "cest", "javne rasvjete", "vodoopskrb",
                                             "odvodnj", "otpad", "tramvaj", "zet", "holding"]),
    ("imovina / nekretnine", ["nekretnin", "zemljišt", "zakup", "kupoprodaj", "darovanj", "stjecanj", "imovin",
                              "poslovnog prostora", "stan"]),
    ("imenovanja / razrješenja / izbori", ["imenovanj", "razrješenj", "izbor ", "izbor ", "izbor i", "verifikacij",
                                           "mandat", "povjerenstv", "odbor"]),
    ("trgovačka društva / ustanove (izvješća)", ["izvješć", "godišnj", "trgovačk", "ustanov", "d.o.o"]),
    ("socijala / zdravstvo / obrazovanje", ["socijal", "zdravst", "vrtić", "škol", "obrazov", "stipendij",
                                            "umirovljen", "djec"]),
    ("kultura / sport / civilno društvo", ["kultur", "sport", "udrug", "manifestacij", "nagrad", "pokrovitelj"]),
    ("statut / poslovnik / opći akti", ["statut", "poslovnik", "pravilnik", "odluke o izmjen"]),
    ("zaštita okoliša / energija", ["okoliš", "energ", "klimat", "zelen"]),
]


def topic(t):
    t = (t or "").lower()
    for name, kws in TOPICS:
        if any(k in t for k in kws):
            return name
    return "ostalo"


db.create_function("topic", 1, topic)

Q["6. Agenda items by topic (keyword classifier on title, first match wins; see TOPICS in analysis/analyze.py)"] = """
SELECT city, topic(coalesce(full_title,title)) topic, count(*) items,
       sum(za IS NOT NULL AND protiv+suzdrzano>0) AS contested,
       sum(protiv) AS protiv_votes_total
FROM items WHERE title NOT LIKE 'Utvrđivanje kvoruma%' GROUP BY 1,2 ORDER BY 1, 3 DESC"""

Q["6b. Most-discussed items, Zagreb (speaker turns listed in the official minutes)"] = """
SELECT mi.session, mi.no, mi.sub, json_array_length(mi.speakers) AS speakers_in_minutes,
       i.za, i.protiv, i.suzdrzano, substr(i.title,1,90) title
FROM minutes_items mi JOIN items i USING(city, session, no, sub)
WHERE mi.city='zagreb' AND mi.speakers IS NOT NULL ORDER BY speakers_in_minutes DESC LIMIT 15"""

Q["6c. Most-contested topics: share of contested items per topic (all cities with totals)"] = """
SELECT topic(coalesce(full_title,title)) topic, count(*) items_w_totals,
       sum(protiv+suzdrzano>0) contested, round(100.0*sum(protiv+suzdrzano>0)/count(*),1) contested_pct
FROM items WHERE za IS NOT NULL AND protiv IS NOT NULL GROUP BY 1 HAVING items_w_totals>=3 ORDER BY contested_pct DESC"""

Q["7. Questions (aktualni sat) per councillor: top 15"] = """
SELECT city, member, party, count(*) questions, count(DISTINCT session) sessions
FROM questions GROUP BY 1,2 ORDER BY 4 DESC LIMIT 15"""

Q["7b. Questions per party, normalised by seats"] = """
SELECT q.city, q.party, count(*) questions,
       (SELECT count(*) FROM members m WHERE m.city=q.city AND m.party=q.party) members_on_list,
       round(1.0*count(*)/(SELECT count(*) FROM members m WHERE m.city=q.city AND m.party=q.party),2) per_member
FROM questions q GROUP BY 1,2 ORDER BY 1,3 DESC"""

Q["7c. Who answers questions"] = """
SELECT city, coalesce(answered_by, to_whom, '?') who, count(*) n FROM questions GROUP BY 1,2 ORDER BY 1,3 DESC LIMIT 15"""

Q["7d. Question topics (same keyword classifier on question text)"] = """
SELECT city, topic(question) topic, count(*) n FROM questions GROUP BY 1,2 ORDER BY 1,3 DESC"""

Q["7e. Councillors (on attendance lists) who never asked a question, Zagreb"] = """
SELECT m.name, m.party FROM members m WHERE m.city='zagreb'
  AND EXISTS (SELECT 1 FROM attendance a WHERE a.city=m.city AND a.member=m.name AND a.present)
  AND NOT EXISTS (SELECT 1 FROM questions q WHERE q.city=m.city AND q.member=m.name) ORDER BY m.party, m.name"""

Q["8. Speaking time per speaker (transcribed recordings only; speaker_turns end-start, machine-detected)"] = """
SELECT city, speaker, role, count(*) turns, round(sum(end-start)/60.0,1) minutes,
       round(avg(end-start)/60.0,1) avg_min
FROM speaker_turns WHERE end > start GROUP BY 1,2,3 ORDER BY 1, minutes DESC"""

Q["8b. Speaking time by role and bloc"] = """
SELECT t.city, t.role, coalesce(m.party,'(dužnosnik)') party, count(*) turns, round(sum(t.end-t.start)/60.0,1) minutes
FROM speaker_turns t LEFT JOIN members m ON m.city=t.city AND m.name=t.speaker
WHERE t.end > t.start GROUP BY 1,2,3 ORDER BY 1, minutes DESC"""

Q["8c. Transcribed recordings: coverage and identified speech"] = """
SELECT v.city, v.session, v.part, round(v.duration/60.0) dur_min, round(v.speech_seconds/60.0) speech_min,
       (SELECT count(*) FROM segments s WHERE s.video_id=v.id) segments,
       (SELECT round(sum(end-start)/60.0) FROM speaker_turns t WHERE t.video_id=v.id) attributed_min,
       (SELECT count(*) FROM items i WHERE i.video_id=v.id AND i.t_start IS NOT NULL) items_located
FROM videos v WHERE v.transcribed ORDER BY 1,2,3"""

Q["8d. Spoken (unofficial) vote results from recordings vs. published totals"] = """
SELECT sv.city, sv.session, sv.item_no, sv.za, sv.protiv, sv.suzdrzano, sv.unanimous, sv.outcome,
       i.za AS off_za, i.protiv AS off_protiv, i.suzdrzano AS off_suzdrzano
FROM spoken_votes sv LEFT JOIN items i ON i.city=sv.city AND i.session=sv.session AND i.no=sv.item_no AND i.sub=sv.sub
ORDER BY 1,2,3"""

Q["8e. Promises in question-hour answers: by speaker and deadline status"] = """
SELECT city, speaker, count(*) promises, sum(deadline_date IS NOT NULL) with_deadline,
       sum(deadline_date < date('now')) deadline_passed
FROM promises GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15"""


def table(rows, cols):
    if not rows:
        return "_(no rows)_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("" if x is None else str(x).replace("|", "/").replace("\n", " ") for x in r) + " |")
    return "\n".join(out) + "\n"


print(f"# Vijećnica: analysis query results\n\nDB: `{DB.relative_to(ROOT) if DB.is_relative_to(ROOT) else DB}`\n")
for title, sql in Q.items():
    print(f"## {title}\n\n```sql{sql}\n```\n")
    try:
        cur = db.execute(sql)
        print(table(cur.fetchall(), [d[0] for d in cur.description]))
    except sqlite3.Error as e:
        print(f"_error: {e}_\n")
