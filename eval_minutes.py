"""Evaluate auto-drafted minutes against the official zapisnik.

  .venv/bin/python eval_minutes.py [--city zagreb] [--session 14]

For every agenda item located in a transcribed recording: draft (minutes_draft.draft) vs official record
(minutes_items) -> speaker precision/recall, turn recall, order agreement, closing word, vote numbers,
outcome, decision type, text similarity. Writes reports/minutes_eval_<city>_<session>.json and .md.
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from minutes_draft import compare, draft, official

ROOT = Path(__file__).resolve().parent


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def evaluate(db, city, session):
    rows = []
    items = db.execute("SELECT no, sub, t_start FROM items WHERE city = ? AND session = ? ORDER BY no, sub",
                       (city, session)).fetchall()
    for no, sub, t in items:
        off = official(db, city, session, no, sub)
        if not off:
            continue
        d = draft(db, city, session, no, sub)
        m = compare(d, off)
        rows.append({"no": no, "sub": sub, "title": d["title"], "in_recording": t is not None, **m,
                     "draft": d["draft"], "official": off["text"],
                     "official_speakers": [f"{s['name']} ({s['kind']})" for s in off["speakers"]],
                     "draft_speakers": [f"{s['name']} ({s['kind']})" for s in d["speakers"]]})
    rec = [r for r in rows if r["in_recording"]]
    s = lambda k, rs=rec: sum(r[k] for r in rs)
    deb = [r for r in rec if r["gold_turns"] or r["pred_turns"]]
    orders = [r["order_agreement"] for r in rec if r["order_agreement"] is not None]
    summary = {
        "city": city, "session": session, "generated": datetime.now().isoformat(timespec="seconds"),
        "items_with_minutes": len(rows), "items_in_recording": len(rec), "items_with_debate": len(deb),
        "speakers_in_minutes": s("gold_speakers"), "speakers_found": s("speakers_matched"),
        "speaker_recall_pct": pct(s("speakers_matched"), s("gold_speakers")),
        "speaker_precision_pct": pct(s("speakers_matched"), s("pred_speakers")),
        "turns_in_minutes": s("gold_turns"), "turns_found": s("turns_matched"),
        "turn_recall_pct": pct(s("turns_matched"), s("gold_turns")),
        "turn_precision_pct": pct(s("turns_matched"), s("pred_turns")),
        "turns_found_with_kind": s("turns_matched_with_kind"),
        "order_agreement_mean": round(sum(orders) / len(orders), 3) if orders else None,
        "closing_word_ok": f"{sum(1 for r in rec if r['closing_ok'])}/{sum(1 for r in rec if r['closing_ok'] is not None)}",
        "vote_exact_pct": pct(sum(r["vote_exact"] for r in rec), len(rec)),
        "outcome_ok_pct": pct(sum(r["outcome_ok"] for r in rec), len(rec)),
        "decision_type_ok": f"{sum(1 for r in rec if r['doc_ok'])}/{sum(1 for r in rec if r['doc_ok'] is not None)}",
        "vote_exact_all_items_pct": pct(sum(r["vote_exact"] for r in rows), len(rows)),
        "text_similarity_mean": round(sum(r["text_similarity"] for r in rec) / len(rec), 3) if rec else None,
        "items_no_debate_correct": sum(1 for r in rec if not r["gold_turns"] and not r["pred_turns"]),
    }
    return summary, rows


def markdown(summary, rows):
    s = summary
    out = [f"# Nacrt zapisnika vs službeni zapisnik: {s['city']} {s['session']}. sjednica", "",
           f"Generirano {s['generated']}. Točke sa službenim zapisnikom: {s['items_with_minutes']}, "
           f"od toga u transkribiranoj snimci: {s['items_in_recording']} (rasprava u {s['items_with_debate']}).", "",
           "| mjera | vrijednost |", "|---|---|",
           f"| govornici iz zapisnika pronađeni (recall) | {s['speakers_found']}/{s['speakers_in_minutes']} = {s['speaker_recall_pct']} % |",
           f"| preciznost govornika | {s['speaker_precision_pct']} % |",
           f"| istupi (s ponavljanjima) pronađeni | {s['turns_found']}/{s['turns_in_minutes']} = {s['turn_recall_pct']} % (preciznost {s['turn_precision_pct']} %) |",
           f"| istupi s točnom vrstom (replika, u ime Kluba…) | {s['turns_found_with_kind']} |",
           f"| slaganje redoslijeda (LCS, prosjek) | {s['order_agreement_mean']} |",
           f"| završna riječ točna | {s['closing_word_ok']} |",
           f"| rezultat glasovanja točan do broja (točke u snimci) | {s['vote_exact_pct']} % |",
           f"| ishod (donosi / nije donijela) | {s['outcome_ok_pct']} % |",
           f"| vrsta akta (ODLUKU, ZAKLJUČAK…) | {s['decision_type_ok']} |",
           f"| rezultat glasovanja, sve točke sjednice | {s['vote_exact_all_items_pct']} % |",
           f"| točke bez rasprave točno prepoznate | {s['items_no_debate_correct']} |",
           f"| sličnost teksta nacrta i službenog odlomka (difflib) | {s['text_similarity_mean']} |", "",
           "## Po točkama", "", "| točka | govornika (služb.) | pronađeno | višak | redoslijed | glasovi | ishod |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        if not r["in_recording"]:
            continue
        out.append(f"| {r['no']}{'.' + str(r['sub']) if r['sub'] > 1 else ''} | {r['gold_speakers']} | "
                   f"{r['speakers_matched']} | {len(r['extra'])} | {r['order_agreement'] if r['order_agreement'] is not None else '–'} | "
                   f"{'da' if r['vote_exact'] else 'NE'} | {'da' if r['outcome_ok'] else 'NE'} |")
    out += ["", "Propušteni govornici po točkama:", ""]
    out += [f"- {r['no']}: {', '.join(r['missed'])}" for r in rows if r["in_recording"] and r["missed"]]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="zagreb")
    ap.add_argument("--session", type=int, default=14)
    a = ap.parse_args()
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'vijecnica.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    summary, rows = evaluate(db, a.city, a.session)
    base = ROOT / "reports" / f"minutes_eval_{a.city}_{a.session}"
    base.with_suffix(".json").write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=1))
    base.with_suffix(".md").write_text(markdown(summary, rows))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
