"""Pitch number for the clerk: how long the machine draft of a whole session's minutes takes, against how
many days after the session the official minutes PDF appeared (its PDF CreationDate).

  python3 clerk_time.py [--session 14]   -> reports/clerk_time_zagreb_<N>.json
"""
import argparse
import json
import re
import sqlite3
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from minutes_draft import draft

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "vijecnica.db"


def pdf_created(session_text_head):
    """CreationDate of the cached minutes PDF whose first page matches (data/raw/pdf)."""
    for f in sorted((ROOT / "data" / "raw" / "pdf").glob("*")):
        t = subprocess.run(["pdftotext", "-l", "1", str(f), "-"], capture_output=True, text=True).stdout[:300]
        if "ZAPISNIK" in t and session_text_head in t:
            info = subprocess.run(["pdfinfo", str(f)], capture_output=True, text=True).stdout
            m = re.search(r"CreationDate:\s+(.+)", info)
            if m:
                return datetime.strptime(" ".join(m.group(1).split()[:5]), "%a %b %d %H:%M:%S %Y").date(), f.name
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=14)
    a = ap.parse_args()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    s = db.execute("SELECT date, minutes_text FROM sessions WHERE city = 'zagreb' AND n = ?", (a.session,)).fetchone()
    items = db.execute("SELECT no, sub FROM items WHERE city = 'zagreb' AND session = ? ORDER BY no, sub",
                       (a.session,)).fetchall()
    t0 = time.perf_counter()
    drafts = [draft(db, "zagreb", a.session, r["no"], r["sub"]) for r in items]
    secs = time.perf_counter() - t0
    ok = sum(1 for d in drafts if "error" not in d)
    # the session can last two days ("15. i 16. listopada"): count from the last day
    head = re.search(r"\d+\.\s+sjednice[^\n]*\n[^\n]*", s["minutes_text"] or "")
    created, pdf = pdf_created(f"{a.session}. sjednice")
    days = re.findall(r"(\d{1,2})\.", head.group(0).split("\n")[1]) if head else []
    start = date.fromisoformat(s["date"])
    last_day = start.replace(day=int(days[-2])) if len(days) >= 2 and int(days[-2]) > start.day else start
    out = {"session": a.session, "session_dates": head.group(0).split("\n")[1].strip() if head else s["date"],
           "items": len(items), "drafted": ok, "draft_seconds": round(secs, 2),
           "minutes_pdf": pdf, "minutes_pdf_created": created.isoformat() if created else None,
           "days_after_last_session_day": (created - last_day).days if created else None,
           "note": "Draft = rules over agenda, roll-call PDFs and speaker turns (no LLM). Includes items not in a "
                   "transcribed recording (agenda + vote only). Excludes the one-off ASR time."}
    (ROOT / "reports" / f"clerk_time_zagreb_{a.session}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
