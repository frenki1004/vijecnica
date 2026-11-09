"""Pick agenda items that become social posts and dump their context for the writer.

Selection rules (fixed and published, so the feed can't be accused of picking sides):
  1. every voted item with at least one vote against or abstention gets its own post, and so does every
     rejected item and every item whose against/abstained counts are not known;
  2. every other voted item of a session goes into one "Ukratko" digest post for that session.
Sub-items of one agenda item with identical votes (one programme per city district) are one post with `parts`.
Unvoted items (reports taken note of, the constitutive session) are skipped.

Context per item: the item's section of the minutes (Zagreb: minutes_items, others: the "TOČKA N." / "Ad N." section)
and, where there is a roll call (Zagreb), how each party's members voted.

Usage: .venv/bin/python posts/build_queue.py [--city brod] [--last N] > data/posts/queue_<city>.json
  --last N   only the city's latest N sessions that have minutes
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from brod import heading_item  # noqa: E402
import importlib  # noqa: E402

import sibenik  # noqa: E402
import netcom  # noqa: E402
from netcom import UNITS as NETCOM  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "vijecnica.db"
EXCERPT = 8000
BODY = {"zagreb": "Gradske skupštine Grada Zagreba",  # everywhere else: Gradsko vijeće
        **{k: "Općinskog vijeća" for k, u in NETCOM.items() if u["body"].startswith("Općin")}}
MARK = re.compile(r"^\W*(?:TOČKA |Točka |Ad ?|AD ?)(\d+)\.?(?=\s|$)", re.M)  # Krk: "Ad 4."; Osijek: title on the same line


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def excerpt(minutes, item, items):
    """The item's section of the minutes: from its "TOČKA N." heading to the next. The heading is
    matched on title, like the votes (collect/brod.py), since N follows the order items were taken in.
    Without headings, best-effort: the text right after the first mention of the item's title."""
    if not minutes:
        return ""
    by_no = {it["no"]: it for it in items}
    marks = [(heading_item(items, by_no, int(m.group(1)), norm(minutes[m.end():m.end() + 600])[:400]), m.start())
             for m in MARK.finditer(minutes)]
    for i, (it, start) in enumerate(marks):
        if it is not None and it["no"] == item["no"]:
            end = marks[i + 1][1] if i + 1 < len(marks) else len(minutes)
            return norm(minutes[start:end])[:EXCERPT]
    title = item["title"]
    flat = norm(minutes)
    for n in (60, 40, 25):
        key = norm(title)[:n]
        i = flat.find(key) if len(key) >= 15 else -1
        if i >= 0:
            return flat[i:i + EXCERPT]
    return ""


def sibenik_sections(n):
    """{(no, sub): minutes section} for a Šibenik session, from the collector's own heading parser: after
    item 18 its minutes head sections with a bare "19. Prijedlog …" instead of "Točka 19.", and sub-items
    ("18.a.") have their own sections. sub counts items sharing a number, as in db/build.py."""
    f = ROOT / "data" / "sibenik" / "docs" / f"session_{n:02d}.json"
    d = json.loads(f.read_text()) if f.exists() else {}
    text, items = d.get("minutes_text"), d.get("items", [])
    if not text:
        return {}
    seen, key = {}, {}
    for it in items:
        seen[it["no"]] = seen.get(it["no"], 0) + 1
        key[id(it)] = (it["no"], seen[it["no"]])
    heads = sibenik.headings(text, list(items))  # may append items it finds only in the minutes; not ours
    out = {}
    for i, (pos, it) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        if id(it) in key:
            out.setdefault(key[id(it)], norm(text[pos:end])[:EXCERPT])
    return out


CUSTOM = ("cakovec", "zadar", "pula", "karlovac", "varazdin", "dubrovnik", "sisak", "kastela", "bjelovar")


def custom_sections(city, n):
    """{(no, sub): minutes section} for a unit whose collector has headings(text, items) -> [(pos, item)]
    (Čakovec and the collectors written after it); sub-items without a heading of their own share their item's."""
    f = ROOT / "data" / city / "docs" / f"session_{n:02d}.json"
    d = json.loads(f.read_text()) if f.exists() else {}
    text, items = d.get("minutes_text"), d.get("items", [])
    if not text:
        return {}
    heads = importlib.import_module(city).headings(text, items)
    out = {}
    for i, (pos, it) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        for sub in range(1, sum(1 for x in items if x["no"] == it["no"]) + 1):
            out[(it["no"], sub)] = norm(text[pos:end])[:EXCERPT]
    return out


def netcom_sections(city, n):
    """{(no, sub): minutes section} for a NetCom unit, from the collector's own heading parser ("AD 3.)",
    "Točka 3.", bare "3. PRIJEDLOG ..." lines in Senj and Ogulin); sub as in db/build.py."""
    f = ROOT / "data" / city / "docs" / f"session_{n:02d}.json"
    d = json.loads(f.read_text()) if f.exists() else {}
    text, items = d.get("minutes_text"), d.get("items", [])
    if not text:
        return {}
    seen, key = {}, {}
    for it in items:
        seen[it["no"]] = seen.get(it["no"], 0) + 1
        key[id(it)] = (it["no"], seen[it["no"]])
    heads = netcom.headings(text, items, netcom.stops(city))  # (pos, heading end, item, label, number)
    out = {}
    for i, (pos, _, it, *_) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)  # a section runs to the next heading
        if it is not None and id(it) in key:
            out.setdefault(key[id(it)], norm(text[pos:end])[:EXCERPT])
    return out


def club_votes(db, city, it):
    """{party: {vote: count}} from the roll call; vote is za / protiv / suzdrzan / nije_glasovao / odsutan."""
    out = {}
    for r in db.execute("""SELECT m.party, v.vote, count(*) n FROM votes v
                           JOIN members m ON m.city = v.city AND m.name = v.member
                           WHERE v.city = ? AND v.session = ? AND v.item_no = ? AND v.sub = ?
                           GROUP BY 1, 2 ORDER BY 1, 3 DESC""", (city, it["session"], it["no"], it["sub"])):
        out.setdefault(r["party"], {})[r["vote"]] = r["n"]
    return out or None


def source(city, s):
    d = ". ".join(str(int(x)) for x in reversed(s["date"].split("-"))) + "." if s["date"] else ""
    body = BODY.get(city, "Gradskog vijeća")
    if not s["minutes_text"]:  # Krk 7-8, Rijeka 12-13: totals from the city's news item until minutes appear
        return f"Izvor: gradska vijest o {s['n']}. sjednici {body}, {d} (zapisnik još nije objavljen)"
    return f"Izvor: zapisnik {s['n']}. sjednice {body}, {d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="brod")
    ap.add_argument("--last", type=int)
    a = ap.parse_args()
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    sessions = {r["n"]: r for r in db.execute("SELECT * FROM sessions WHERE city = ?", (a.city,))}
    keep = sorted(n for n, s in sessions.items() if s["minutes_text"])[-a.last:] if a.last else sorted(sessions)
    item_minutes = {(r["session"], r["no"], r["sub"]): r["text"] for r in
                    db.execute("SELECT session, no, sub, text FROM minutes_items WHERE city = ?", (a.city,))}
    agenda = {}
    for it in db.execute("SELECT * FROM items WHERE city = ? ORDER BY session, no, sub", (a.city,)):
        agenda.setdefault(it["session"], []).append(it)
    finder = sibenik_sections if a.city == "sibenik" else (lambda n: custom_sections(a.city, n)) \
        if a.city in CUSTOM else \
        (lambda n: netcom_sections(a.city, n)) if a.city in NETCOM else None
    sections = {n: finder(n) for n in keep} if finder else {}
    posts, digests = [], {}
    # a vote is an item with counts or a result: "jednoglasno" without a number has za = null (NetCom units)
    for it in (it for n in keep for it in agenda.get(n, []) if it["za"] is not None or it["result"]):
        s = sessions[it["session"]]
        note = json.loads(it["totals_note"])["text"] if it["totals_note"] else None
        partial = bool(note and "nisu navedeni" in note)  # minutes give only ZA: against/abstained unknown, not 0
        base = {"city": a.city, "session": it["session"], "date": s["date"],
                "no": it["no"], "sub": it["sub"], "title": norm(it["full_title"] or it["title"]),
                "proposer": it["proposer"], "za": it["za"], "protiv": None if partial else it["protiv"],
                "suzdrzano": None if partial else it["suzdrzano"], "result": it["result"], "status": it["status"],
                "totals_note": note, "source": source(a.city, s)}
        rejected = "nije" in (it["result"] or "")
        unknown = it["protiv"] is None or it["suzdrzano"] is None  # not provably unanimous: own post, not "Ukratko"
        if (it["protiv"] or 0) + (it["suzdrzano"] or 0) > 0 or rejected or partial or unknown:
            prev = posts[-1] if posts else None
            if (prev and prev["session"] == it["session"] and prev["no"] == it["no"]
                    and (prev["za"], prev["protiv"], prev["suzdrzano"]) == (it["za"], it["protiv"], it["suzdrzano"])):
                # sub-items voted together (e.g. one programme per city district): one post, listing the parts
                prev.setdefault("parts", [prev["title"]]).append(base["title"])
                first = prev.setdefault("first_sub", prev["sub"])  # an item can hold two such groups (Šibenik 6/5)
                prev["id"] = f"{a.city}-{it['session']}-{it['no']}" + (f"-{first}-{it['sub']}" if first > 1 else "")
                continue
            key = (it["session"], it["no"], it["sub"])
            section = sections.get(it["session"], {}).get((it["no"], it["sub"]))
            text = (norm(item_minutes[key])[:EXCERPT] if key in item_minutes else section
                    or excerpt(s["minutes_text"], it, agenda[it["session"]]))
            posts.append({"id": f"{a.city}-{it['session']}-{it['no']}-{it['sub']}", "kind": "item", **base,
                          "club_votes": club_votes(db, a.city, it), "minutes_excerpt": text})
        else:
            d = digests.setdefault(it["session"], {"id": f"{a.city}-{it['session']}-ukratko", "kind": "digest",
                                                   "city": a.city, "session": it["session"],
                                                   "date": base["date"], "source": base["source"], "items": []})
            d["items"].append({k: base[k] for k in ("no", "sub", "title", "za", "result")})
    out = posts + list(digests.values())
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print(f"{len(posts)} item posts, {len(digests)} digests", file=sys.stderr)


if __name__ == "__main__":
    main()
