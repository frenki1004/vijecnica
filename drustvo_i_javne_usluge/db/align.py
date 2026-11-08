"""Find where each agenda item starts and is voted on in the session recordings.

The chair follows a fixed script: "Prelazimo na 11. točku <title>…", then "stavljam na glasovanje
<title>…", then "Glasovanje je završeno, glasalo je 25 zastupnika, … 23 glasalo za, 2 suzdržana …".
Anchors from "prelazimo na N. točku" come first; items without one (e.g. the first item of a
continuation day, announced by title only) are placed by title-word overlap between their neighbours.
"""
import re
import sqlite3

START = re.compile(r"(?:prelazimo|prijelazimo|idemo|nastavljamo)\s+(?:na|s|sa)\s+"
                   r"(?:(\d{1,2})\.?\s*točk|točk\w*\s+(?:broj\s+)?(\d{1,2}))", re.I)
VOTE = re.compile(r"stavljam\s+na\s+glasovanje", re.I)
RESULT = re.compile(r"glasovanje\s+je\s+završeno", re.I)


def stem_set(text):
    return {w[:5] for w in re.findall(r"\w+", text.lower()) if len(w) > 3}


def align(db: sqlite3.Connection):
    for city, session in db.execute("SELECT DISTINCT city, session FROM items").fetchall():
        segs = db.execute("""SELECT s.video_id, v.part, s.start, s.text FROM segments s
                             JOIN videos v ON v.id = s.video_id
                             WHERE s.city = ? AND s.session = ? ORDER BY v.part, s.start""",
                          (city, session)).fetchall()
        if not segs:
            continue
        items = db.execute("SELECT no, sub, title FROM items WHERE city = ? AND session = ? ORDER BY no, sub",
                           (city, session)).fetchall()
        # 1. explicit "prelazimo na N. točku" anchors (index into segs)
        anchor = {}
        for i, (_, _, _, text) in enumerate(segs):
            for m in START.finditer(text):
                n = int(m.group(1) or m.group(2))
                if n not in anchor:
                    anchor[n] = i
        # 2. title overlap for the rest, searched between the neighbouring anchors
        pos = {}
        for no, sub, title in items:
            if sub == 1 and no in anchor:
                pos[(no, sub)] = anchor[no]
        for no, sub, title in items:
            if (no, sub) in pos:
                continue
            lo = max([p for (n, _), p in pos.items() if n < no] or [0])
            hi = min([p for (n, _), p in pos.items() if n > no] or [len(segs)])
            want = stem_set(title[:200])
            best, score = None, 0.0
            for i in range(lo, hi):
                got = stem_set(segs[i][3])
                s = len(want & got) / max(len(want), 1)
                if s > score:
                    best, score = i, s
            if best is not None and score >= 0.5:
                pos[(no, sub)] = best
        # 3. vote call + result after the start, before the next item's start
        starts = sorted(pos.values())
        for (no, sub), i in pos.items():
            nxt = min([p for p in starts if p > i] or [len(segs)])
            vote = next((j for j in range(i, nxt) if VOTE.search(segs[j][3])), None)
            res = next((j for j in range(vote or i, nxt) if RESULT.search(segs[j][3])), None)
            spoken = None
            if res is not None:
                m = re.search(r"glasalo\s+je\s+(\d+)\s+zastupnik.*?(\d+)\s+zastupnika\s+glasalo\s+za",
                              " ".join(t for *_, t in segs[res:res + 2]), re.I)
                spoken = f"{m.group(2)}/{m.group(1)}" if m else None
            db.execute("""UPDATE items SET video_id = ?, t_start = ?, t_vote = ?, spoken_result = ?
                          WHERE city = ? AND session = ? AND no = ? AND sub = ?""",
                       (segs[i][0], segs[i][2],
                        segs[vote][2] if vote is not None and segs[vote][0] == segs[i][0] else None,
                        spoken, city, session, no, sub))
