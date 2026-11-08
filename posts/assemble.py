"""Join writer drafts (data/posts/drafts_*.json) with their queue entries into data/posts/posts.json,
the file the /feed page reads. Drafts whose id is not in any queue are dropped and reported.

Usage: .venv/bin/python posts/assemble.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from netcom import UNITS as NETCOM  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts"
CITY_TAG = {"zagreb": "#Zagreb", "brod": "#SlavonskiBrod", "rijeka": "#Rijeka", "krk": "#Krk",
            "osijek": "#Osijek", "sibenik": "#Šibenik",
            **{k: "#" + u["name"].replace(" ", "") for k, u in NETCOM.items()}}
CITY_NAME = {"zagreb": "Zagreb", "brod": "Slavonski Brod", "rijeka": "Rijeka", "krk": "Krk", "osijek": "Osijek",
             "sibenik": "Šibenik", **{k: u["name"] for k, u in NETCOM.items()}}
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


def clubs(club_votes):
    """Roll call per party as rows for the feed's 'Kako su glasali klubovi' slide, biggest party first."""
    rows = [{"party": PARTY_SHORT.get(p, p), **v} for p, v in (club_votes or {}).items()]
    return sorted(rows, key=lambda r: -sum(n for k, n in r.items() if k != "party")) or None


def main():
    queue = {}
    for f in sorted(POSTS.glob("queue*.json")):
        queue.update({p["id"]: p for p in json.loads(f.read_text())})
    out, dropped = [], []
    for f in sorted(POSTS.glob("drafts_*.json")):
        for d in json.loads(f.read_text()):
            q = queue.get(d["id"])
            if not q:
                dropped.append(d["id"])
                continue
            q = {k: v for k, v in q.items() if k not in ("minutes_excerpt", "club_votes")} | {
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
            out.append({**q, **d, "topics": topics, "city_name": CITY_NAME.get(q["city"], q["city"]),
                        "hashtags": [CITY_TAG.get(q["city"], "#" + q["city"])] + [TOPIC_TAG[t] for t in topics]})
    out.sort(key=lambda p: (p.get("date") or "", p["kind"] == "item", p.get("no", 0)), reverse=True)
    (POSTS / "posts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out)} posts -> {POSTS / 'posts.json'}" + (f"; dropped {dropped}" if dropped else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
