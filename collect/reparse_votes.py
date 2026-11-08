"""Re-parse every cached roll-call PDF (data/raw/pdf) into data/docs/session_NN.json without fetching anything,
and record why a roll call does not add up to the official totals.

  python3 collect/reparse_votes.py [N ...]

vote.roll = counts from the per-member table; vote.totals_note (null when they agree):
  "ručno"       the header says e.g. "32+3=35*": N members voted by hand (device failure / raised card) and the
                per-member table does not mark them, so roll + manual = official
  "nepotpuno"   the PDF's member table is missing marks the totals count (left unexplained, source data)
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docs import OUT, RAW, parse_vote  # noqa: E402

KEYS = (("za", "za"), ("protiv", "protiv"), ("suzdrzano", "suzdrzan"))


def glasova(n):
    a, b = n % 10, n % 100
    return (f"{n} glas zabilježen" if a == 1 and b != 11 else
            f"{n} glasa zabilježena" if 2 <= a <= 4 and not 12 <= b <= 14 else f"{n} glasova zabilježeno")


def note(v):
    c = Counter(v.get("members", {}).values())
    roll = {k: c.get(m, 0) for k, m in KEYS}
    v["roll"] = roll
    if all(v.get(k) is None for k, _ in KEYS):
        return None
    diff = {k: (v.get(k) or 0) - roll[k] for k, _ in KEYS}
    manual = {k: v.get(k + "_manual", 0) for k, _ in KEYS}
    if not any(diff.values()):
        if not any(manual.values()):
            return None
        who = ", ".join(v.get("manual_names") or [])
        return {"kind": "ručno", "diff": diff, "manual": manual,
                "text": f"{glasova(sum(manual.values()))} ručno (u PDF-u \"{v['za'] - manual['za']}+"
                        f"{manual['za']}={v['za']}*\"" + (f": {who}" if who else "") + ", npr. dizanjem glasačkog"
                        " kartona); u pojedinačnom popisu označeni s X*, zbroj se slaže"} if manual["za"] else {
            "kind": "ručno", "diff": diff, "manual": manual,
            "text": f"{glasova(sum(manual.values()))} ručno" + (f": {who}" if who else "")
                    + " (npr. dizanjem glasačkog kartona); u pojedinačnom popisu označeni s X*, zbroj se slaže"}
    if all(diff[k] <= manual[k] for k in diff) and any(manual.values()):
        unmarked = sum(manual.values()) - sum(diff.values())
        return {"kind": "ručno", "diff": diff, "manual": manual,
                "text": f"{glasova(sum(manual.values()))} ručno (zbroj u PDF-u npr. \"32+3=35*\"); "
                        + ("pojedinačni popis ih ne označava" if unmarked == 0 else
                           f"{unmarked} od njih označeno je u pojedinačnom popisu")}
    return {"kind": "nepotpuno", "diff": diff, "manual": manual,
            "text": "pojedinačni popis u PDF-u ne zbraja se na službeni rezultat"
                    + (f" (od toga {sum(manual.values())} ručno)" if any(manual.values()) else "")}


def main(ns):
    for f in sorted(OUT.glob("session_*.json")):
        d = json.loads(f.read_text())
        if ns and d["session"] not in ns:
            continue
        roster = [a["name"] for a in d.get("attendance", [])]
        bad = 0
        for it in d["items"]:
            v = it.get("vote")
            if not v or not v.get("file"):
                continue
            pdf = RAW / "pdf" / v["file"]
            if not pdf.exists():
                continue
            nv = parse_vote(pdf, roster)
            nv["totals_note"] = note(nv)
            it["vote"] = nv
            if nv["totals_note"]:
                bad += 1
                print(f"  {d['session']}/{it['no']}: {nv['totals_note']['kind']} official "
                      f"{[nv.get(k) for k, _ in KEYS]} roll {list(nv['roll'].values())} manual "
                      f"{list(nv['totals_note']['manual'].values())} members={len(nv['members'])}")
        if not DRY:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        print(f"session {d['session']}: {sum(1 for i in d['items'] if i.get('vote'))} votes, {bad} with a note")


DRY = "--dry" in sys.argv
if __name__ == "__main__":
    main({int(x) for x in sys.argv[1:] if x != "--dry"})
