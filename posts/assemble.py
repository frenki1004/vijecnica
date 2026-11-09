"""Join writer drafts (data/posts/drafts_*.json) with their queue entries into data/posts/posts.json,
the file the /feed page reads. Drafts whose id is not in any queue are dropped and reported.

Usage: .venv/bin/python posts/assemble.py
"""
import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from netcom import UNITS as NETCOM  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts"
CITY_TAG = {"zagreb": "#Zagreb", "brod": "#SlavonskiBrod", "rijeka": "#Rijeka", "krk": "#Krk",
            "osijek": "#Osijek", "sibenik": "#Šibenik", "cakovec": "#Čakovec", "zadar": "#Zadar", "pula": "#Pula", "karlovac": "#Karlovac", "varazdin": "#Varaždin", "dubrovnik": "#Dubrovnik", "sisak": "#Sisak", "kastela": "#Kaštela", "bjelovar": "#Bjelovar", "velika_gorica": "#VelikaGorica", "samobor": "#Samobor", "brckovljani": "#Brckovljani", "gradiste": "#Gradište", "cernik": "#Cernik", "svetijuraj": "#SvetiJurajnaBregu", "marijagorica": "#MarijaGorica",
            **{k: "#" + u["name"].replace(" ", "") for k, u in NETCOM.items()}}
CITY_NAME = {"zagreb": "Zagreb", "brod": "Slavonski Brod", "rijeka": "Rijeka", "krk": "Krk", "osijek": "Osijek",
             "sibenik": "Šibenik", "cakovec": "Čakovec", "zadar": "Zadar", "pula": "Pula", "karlovac": "Karlovac", "varazdin": "Varaždin", "dubrovnik": "Dubrovnik", "sisak": "Sisak", "kastela": "Kaštela", "bjelovar": "Bjelovar", "velika_gorica": "Velika Gorica", "samobor": "Samobor", "brckovljani": "Brckovljani", "gradiste": "Gradište", "cernik": "Cernik", "svetijuraj": "Sveti Juraj na Bregu", "marijagorica": "Marija Gorica", **{k: u["name"] for k, u in NETCOM.items()}}
TOPIC_TAG = {"promet": "#promet", "stanovanje": "#stanovanje", "komunalno": "#komunalno", "otpad": "#otpad",
             "okolis": "#okoliš", "proracun": "#proračun", "porezi-i-naknade": "#poreziinaknade",
             "vrtici-i-skole": "#vrtićiiškole", "mladi": "#mladi", "sport": "#sport", "kultura": "#kultura",
             "socijala": "#socijala", "zdravstvo": "#zdravstvo", "gospodarstvo": "#gospodarstvo",
             "prostorno-uredenje": "#prostornouređenje", "imenovanja": "#imenovanja",
             "gradska-uprava": "#gradskauprava"}
PARTY_SHORT = {"Možemo! - politička platforma": "Možemo!", "Socijaldemokratska partija Hrvatske": "SDP",
               "Hrvatska demokratska zajednica": "HDZ", "Domovinski pokret": "DP",
               "Hrvatska socijalno - liberalna stranka": "HSLS", "Hrvatska stranka umirovljenika": "HSU",
               "Hrvatska narodna stranka - liberalni demokrati": "HNS",
               "Nezavisna lista Tomislava Jonjića - Jedino Hrvatska!": "Lista T. Jonjića",
               "Dina Dogan - Nezavisna lista": "Lista D. Dogan"}


# "Samo bitno": a fixed, published rule on what a decision is about, never on who proposed it or how it went
# politically. Appointments never count (a director of a nature park is still an appointment); internal
# administration only counts when a residents' topic also applies. A proposal that failed always counts.
RESIDENT_TOPICS = {"promet", "stanovanje", "komunalno", "otpad", "okolis", "proracun", "porezi-i-naknade",
                   "vrtici-i-skole", "mladi", "sport", "kultura", "socijala", "zdravstvo", "prostorno-uredenje"}


def relevance(p):
    """(relevant, reason) for the feed's "Samo bitno" filter."""
    if p["kind"] != "item":
        return False, "pregled jednoglasnih odluka"
    if "nije" in (p.get("result") or "") or "nije uvršten" in (p.get("status") or ""):
        return True, "prijedlog nije prošao"
    if "imenovanja" in p["topics"]:
        return False, "imenovanja"
    hit = sorted(RESIDENT_TOPICS & set(p["topics"]))
    return (True, "tema: " + ", ".join(hit)) if hit else (False, "imenovanja ili rad uprave")


def short_list(name):
    """'HRVATSKA DEMOKRATSKA ZAJEDNICA - HDZ + MOST' -> 'HDZ + MOST': each party's own short name after its last ' - '."""
    return " + ".join(part.rsplit(" - ", 1)[-1].strip() for part in name.split(" + "))


# the five units with the lowest 2025 turnout (DIP): what each council publishes for the 2025-2029 term (checked 9. 11. 2026.)
LOW_TURNOUT = {
    "brckovljani": "Za ovaj saziv objavljen je samo poziv na konstituirajuću sjednicu; zapisnici i materijali nisu objavljeni, odluke su u službenom glasniku bez rezultata glasovanja.",
    "gradiste": "Za ovaj saziv nisu objavljeni ni pozivi ni zapisnici; zadnja objavljena sjednica je iz lipnja 2023. Objavljeni su proračunski akti.",
    "cernik": "Objavljeni su zapisnici samo 8., 9. i 10. sjednice; ostali zapisnici, materijali i snimke nisu objavljeni.",
    "svetijuraj": "Objavljeni su pozivi i zapisnici gotovo svih sjednica; snimke se ne objavljuju.",
    "marijagorica": "Objavljeni su paketi materijala s pozivima i dijelom zapisnika (sjednice 1, 4, 7 i 8); snimke se ne objavljuju.",
}


def towns(db_path):
    """Per city, the data.gov.hr and DIP facts the feed's town card shows, each with its source.
    Built by collect/datagovhr.py + db/build.py (view city_overview); empty when that has not run."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT * FROM city_overview").fetchall()
    except sqlite3.OperationalError:
        return {}
    dg = ROOT / "data" / "datagovhr"
    every = json.loads((dg / "unit_turnout.json").read_text()) if (dg / "unit_turnout.json").exists() else []
    ranked = sorted(t["turnout_pct"] for t in every)
    big = {u["code"] for u in sorted(json.loads((dg / "units.json").read_text()), key=lambda u: -(u["population"] or 0))[:15]} \
        if (dg / "units.json").exists() else set()
    out = {}
    for r in rows:
        c = r["city"]
        seats = [{"list": short_list(x["list"]), "seats": x["seats"], "pct": x["pct"]} for x in db.execute(
            "SELECT list, seats, pct FROM council_composition WHERE city = ? AND seats > 0 ORDER BY seats DESC", (c,))]
        tax = db.execute("SELECT * FROM tax_rates WHERE city = ?", (c,)).fetchone()
        pub = db.execute("SELECT * FROM datagovhr_publishers WHERE city = ?", (c,)).fetchone()
        el = db.execute("SELECT registered, voted FROM election_turnout WHERE city = ?", (c,)).fetchone()
        out[c] = {"unit": r["unit"], "county": r["county"], "website": r["website"], "oib": r["oib"],
                  "population": r["population"], "voters": r["voters_2026"], "turnout_2025": r["turnout_pct"],
                  "registered_2025": el["registered"] if el else None,
                  "nonvoters_2025": el["registered"] - el["voted"] if el else None,
                  # 1 = lowest turnout of all units with 2025 results (DIP), and how many there are
                  "turnout_rank": sum(1 for x in ranked if x < r["turnout_pct"]) + 1 if r["turnout_pct"] and ranked else None,
                  "turnout_units": len(ranked) or None,
                  "big15": r["code"] in big,  # one of the 15 most populous units in Croatia (DZS 2021.)
                  "low_turnout": LOW_TURNOUT.get(c),  # one of the five lowest-turnout units: what its council publishes
                  "seats_total": r["seats_total"], "seats": seats, "majority": bool(r["single_list_majority"]),
                  "mayor": (r["mayor"] or "").title() or None,
                  "tax": dict(tax) if tax else None,
                  "datagovhr": {"organization": pub["organization"], "datasets": pub["datasets"]} if pub else None,
                  "sources": {"population": "DZS, Popis 2021. (data.gov.hr)", "voters": "Registar birača 2026. (data.gov.hr)",
                              "seats": "DIP, lokalni izbori 2025., preračun D'Hondt", "tax": "Porezna uprava (data.gov.hr)",
                              "unit": "Popis javnopravnih tijela, jpt.gov.hr (data.gov.hr)"}}
    return out


def clubs(club_votes):
    """Roll call per party as rows for the feed's 'Kako su glasali klubovi' slide, biggest party first."""
    rows = [{"party": PARTY_SHORT.get(p, p), **v} for p, v in (club_votes or {}).items()]
    return sorted(rows, key=lambda r: -sum(n for k, n in r.items() if k != "party")) or None


def main():
    queue = {}
    for f in sorted(POSTS.glob("queue*.json")):
        queue.update({p["id"]: p for p in json.loads(f.read_text())})
    out, dropped = {}, []
    # drafts_v3_* (written with materials and transcripts) come last, so they replace older drafts of the same post
    for f in sorted(POSTS.glob("drafts_*.json"), key=lambda f: (f.name.startswith("drafts_v3"), f.name)):
        for d in json.loads(f.read_text()):
            q = queue.get(d["id"])
            if not q:
                dropped.append(d["id"])
                continue
            q = {k: v for k, v in q.items() if k not in ("minutes_excerpt", "club_votes", "materials",
                                                         "transcript_excerpt")} | {
                "clubs": clubs(q.get("club_votes"))}
            topics = [t for t in d.get("topics", []) if t in TOPIC_TAG]
            head, _, last = d.get("caption", "").rpartition("\n")
            if q.get("source") and last.startswith("Izvor:") and last != q["source"]:  # the queue's source line wins
                d["caption"] = f"{head}\n{q['source']}"
            if q.get("totals_note") and q.get("protiv") is None:  # shown as "–", so not "(upisano 0)" either
                q["totals_note"] = re.sub(r"\s*\(upisano 0\)", "", q["totals_note"])
            for e in d.get("debate", []):  # a proposing mayor has no vote in the council
                if e["who"].startswith("Gradonačelni") and "predlagatelj" in e["who"]:
                    e["side"] = "predlagatelj"
            out[d["id"]] = ({**q, **d, "topics": topics, "city_name": CITY_NAME.get(q["city"], q["city"]),
                        "hashtags": [CITY_TAG.get(q["city"], "#" + q["city"])] + [TOPIC_TAG[t] for t in topics]})
    db = sqlite3.connect(ROOT / "data" / "vijecnica.db")
    site = dict(db.execute("SELECT id, site FROM cities"))
    links = {(c, n): m or u for c, n, m, u in db.execute("SELECT city, n, minutes_url, url FROM sessions")}
    links = {k: (v if not v or v.startswith("http") else urllib.parse.urljoin(site.get(k[0]) or "", v))
             for k, v in links.items()}  # Zagreb's and Brod's links are site-relative
    out = list(out.values())
    for p in out:
        p["relevant"], p["relevance"] = relevance(p)
        p["source_url"] = links.get((p["city"], p["session"]))  # the minutes, else the session's page
    out.sort(key=lambda p: (p.get("date") or "", p["kind"] == "item", p.get("no", 0)), reverse=True)
    (POSTS / "posts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    (POSTS / "towns.json").write_text(json.dumps(towns(ROOT / "data" / "vijecnica.db"), ensure_ascii=False, indent=1))
    print(f"{len(out)} posts -> {POSTS / 'posts.json'}" + (f"; dropped {dropped}" if dropped else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
