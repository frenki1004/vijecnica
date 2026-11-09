"""Queue entries with more than the minutes: the item's materials and the debate from the session recording.

For each post with materials (data/posts/materials.json, collect/materials.py) or a transcribed recording, the
queue entry (data/posts/queue*.json, posts/build_queue.py) gets
  materials          [{name, text}]: the proposal and its explanation, each cut to MAT characters
  transcript_excerpt the machine transcript from the item's start in the recording to the next item's start
                     (items.video_id / t_start, aligned by db/build.py), "[h:mm:ss] text" lines, cut to TR characters
and its source line names the materials. Output: data/posts/queue_v3.json (assemble.py lets it win over the
older queue files); the writer (posts/writer_prompt.md) then rewrites these posts.

Usage: python posts/enrich.py [--ids id,id] [--out data/posts/queue_v3.json]
"""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts"
MAT, TR = 5000, 6000


def clock(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def excerpt(db, city, session, no, sub):
    """Transcript of one item: from its start in the recording to the next aligned item's start (same video)."""
    it = db.execute("SELECT video_id, t_start FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
                    (city, session, no, sub)).fetchone()
    if not it or not it[0] or it[1] is None:
        return None
    nxt = db.execute("SELECT min(t_start) FROM items WHERE city = ? AND video_id = ? AND t_start > ?",
                     (city, it[0], it[1])).fetchone()[0]
    rows = db.execute("SELECT start, text FROM segments WHERE video_id = ? AND start >= ? AND start < ? ORDER BY start",
                      (it[0], it[1] - 5, nxt if nxt is not None else it[1] + 1800)).fetchall()
    out, n = [], 0
    for start, text in rows:
        line = f"[{clock(start)}] {text.strip()}"
        if n + len(line) > TR:
            break
        out.append(line)
        n += len(line) + 1
    return "\n".join(out) or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--out", default=str(POSTS / "queue_v3.json"))
    a = ap.parse_args()
    queue = {}
    for f in sorted(POSTS.glob("queue*.json")):
        if f.name.startswith("queue_v3"):
            continue
        queue.update({e["id"]: e for e in json.loads(f.read_text())})
    mats = json.loads((POSTS / "materials.json").read_text()) if (POSTS / "materials.json").exists() else {}
    ids = a.ids.split(",") if a.ids else sorted(mats)
    db = sqlite3.connect(ROOT / "data" / "vijecnica.db")
    out = []
    for i in ids:
        e = queue.get(i)
        if not e:
            continue
        e = dict(e)
        docs = [{"name": d["name"], "text": d["text"][:MAT]} for d in mats.get(i, []) if d["text"].strip()]
        if docs:
            e["materials"] = docs
            e["source"] = e["source"].replace("Izvor: zapisnik", "Izvor: zapisnik i materijali", 1) \
                if e["source"].startswith("Izvor: zapisnik") else e["source"] + "; materijali sjednice"
        tr = excerpt(db, e["city"], e["session"], e["no"], e["sub"])
        if tr:
            e["transcript_excerpt"] = tr
        if docs or tr:
            out.append(e)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out)} queue entries -> {a.out} ({sum('materials' in e for e in out)} with materials, "
          f"{sum('transcript_excerpt' in e for e in out)} with a transcript)")


if __name__ == "__main__":
    main()
