"""Static demo of the feed for a host without Python (Vercel): deploy/vijecnica/ with index.html (web/feed.html),
posts.json (data/posts/posts.json without the writers' internal notes and without posts held back for review),
film.html with web/film/ (the 3-minute video as a page, /film),
towns.json (data.gov.hr facts per town), otvoreni-podaci.zip (the export/export.py Data Package), favicon.svg and a
vercel.json that serves /api/posts and /api/towns from the JSON files, the paths the feed already uses.

The demo carries a notice: its posts are machine drafts that no person has reviewed yet.

Live: https://evijecnica.vercel.app
Usage: .venv/bin/python web/build_static.py, then: npx vercel deploy deploy/vijecnica --prod
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "vijecnica"
# not for publication until a person has looked at them (misleading cover, or a case about a named councillor)
HOLD = {"zagreb-12-37-2", "zagreb-11-9-1",
        # Varaždin 7: collector paired items 5-13 with the wrong titles; counts that do not add up in the minutes
        *(f"varazdin-7-{n}-1" for n in range(5, 14)), "split-7-39-1", "sibenik-5-11-1",
        "dubrovnik-12-26-1",  # its vote line in the minutes names another item
        "samobor-11-13-1"}  # OCR: "I." or "II." izmjene unclear
NOTICE = ('<p class="demo-note">Demo za Datathon Portala otvorenih podataka: objave su strojni nacrti iz službenih '
          'zapisnika i još ih nije pregledala osoba. Službeni dokumenti imaju prednost. '
          '<a href="podaci">Preuzmi sve podatke</a>: transkripte, glasovanja i objave (CSV i Data Package za CKAN).</p>')
EXPORT = ROOT / "data" / "export"  # export/export.py
NOTICE_CSS = (".demo-note{margin:10px 0 0;padding:8px 12px;border-radius:8px;background:var(--soft);"
              "color:var(--muted);font-size:14px}")
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" '
           'fill="#1d4f9c"/><path d="M6 13 16 6l10 7zM8 14h3v9H8zm6.5 0h3v9h-3zM21 14h3v9h-3zM6 24h20v3H6z" '
           'fill="#fff"/></svg>')
VERCEL = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": None, "buildCommand": "",
          "rewrites": [{"source": "/api/posts", "destination": "/posts.json"}, {"source": "/film", "destination": "/film.html"},
                       {"source": "/demo", "destination": "/demo.html"}, {"source": "/intro", "destination": "/intro.html"}, {"source": "/api/demo", "destination": "/demo.json"},
                       {"source": "/api/towns", "destination": "/towns.json"},
                       {"source": "/api/units", "destination": "/units.json"}, {"source": "/feed", "destination": "/"},
                       {"source": "/podaci", "destination": "/podaci.html"},
                       {"source": "/mcp", "destination": "/api/server"}],
          "functions": {"api/server.py": {"includeFiles": "{mcp_server.py,collect/netcom.py,data/vijecnica.db}", "maxDuration": 30}},
          "headers": [{"source": "/posts.json", "headers": [{"key": "Cache-Control", "value": "public, max-age=300"}]}]}


# not offered for download: Samobor's robots.txt excludes AI systems by name (its posts stay on the web, with sources)
NO_DOWNLOAD = {"samobor"}
LABELS = {"sessions": "sjednice", "items": "točke dnevnog reda", "spoken_votes": "glasovi iz snimke", "votes": "poimenično glasovanje",
          "attendance": "nazočnost", "members": "članovi vijeća", "questions": "pitanja vijećnika", "segments": "transkript",
          "speaker_turns": "govornici", "promises": "obećanja"}


def podaci(posts):
    """deploy/vijecnica/podaci.html + podaci/ (per-town zips, the Data Package, posts, data.gov.hr provenance) and
    otvoreni-podaci.zip with everything, all from the export/export.py package minus NO_DOWNLOAD."""
    import csv
    import zipfile
    d = OUT / "podaci"
    d.mkdir()
    pkg = json.loads((EXPORT / "datapackage.json").read_text())
    pkg["resources"] = [r for r in pkg["resources"] if r["path"].split("/")[0] not in NO_DOWNLOAD]
    (d / "datapackage.json").write_text(json.dumps(pkg, ensure_ascii=False, indent=1))
    names = {p["city"]: p.get("city_name") or p["city"] for p in posts}
    towns = json.loads((ROOT / "data" / "posts" / "towns.json").read_text())
    rows, cities, descriptions = {}, [], {}
    keys = sorted({r["path"].split("/")[0] for r in pkg["resources"] if "/" in r["path"]})
    with zipfile.ZipFile(OUT / "otvoreni-podaci.zip", "w", zipfile.ZIP_DEFLATED) as everything:
        for f in ("datapackage.json",):
            everything.write(d / f, f)
        for f in ("README.txt",):
            if (EXPORT / f).exists():
                everything.write(EXPORT / f, f)
        for key in keys:
            tables = []
            with zipfile.ZipFile(d / f"{key}.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted((EXPORT / key).glob("*.csv")):
                    with f.open(newline="") as fh:
                        n = max(0, sum(1 for _ in csv.reader(fh)) - 1)
                    z.write(f, f"{key}/{f.name}")
                    everything.write(f, f"{key}/{f.name}")
                    tables.append({"name": f.stem, "rows": n})
                    rows[f.stem] = rows.get(f.stem, 0) + n
                z.write(d / "datapackage.json", "datapackage.json")
            t = towns.get(key, {})
            name = names.get(key) or (t.get("unit") or key).replace("OPĆINA ", "").replace("GRAD ", "").title()
            cities.append({"key": key, "name": name, "tables": tables, "size": (d / f"{key}.zip").stat().st_size})
    for r in pkg["resources"]:
        descriptions.setdefault(r["name"].split("-", 1)[-1] if "-" in r["name"] else r["name"], r.get("description", ""))
    descriptions = {k: v for k, v in descriptions.items() if k in LABELS}
    (d / "objave.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1))
    shutil.copy(ROOT / "data" / "datagovhr" / "sources.json", d / "datagovhr-izvori.json")
    data = {"cities": sorted(cities, key=lambda c: c["name"]), "rows": rows, "posts": len(posts),
            "postsSize": (d / "objave.json").stat().st_size, "zip": (OUT / "otvoreni-podaci.zip").stat().st_size,
            "labels": LABELS, "descriptions": descriptions,
            "excluded": [names.get(k, k.title()) for k in sorted(NO_DOWNLOAD)]}
    (OUT / "podaci.html").write_text((ROOT / "web" / "podaci.html").read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))


def mcp_public():
    """The MCP server as a Vercel Python function (/mcp): api/server.py (not mcp.py: that name would hide the mcp package), mcp_server.py, collect/netcom.py and a
    public copy of the database without NO_DOWNLOAD units (rows deleted, full-text indexes rebuilt)."""
    import sqlite3
    (OUT / "api").mkdir()
    shutil.copy(ROOT / "web" / "vercel_mcp" / "server.py", OUT / "api" / "server.py")
    shutil.copy(ROOT / "mcp_server.py", OUT / "mcp_server.py")
    (OUT / "collect").mkdir()
    shutil.copy(ROOT / "collect" / "netcom.py", OUT / "collect" / "netcom.py")
    (OUT / "data").mkdir()
    db_path = OUT / "data" / "vijecnica.db"
    src = sqlite3.connect(f"file:{ROOT / 'data' / 'vijecnica.db'}?mode=ro", uri=True)
    db = sqlite3.connect(db_path)
    src.backup(db)
    src.close()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE '%fts%'")]
    for t in tables:
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
        for c in ("city",) if "city" in cols else ("id",) if t == "cities" else ():
            db.execute(f"DELETE FROM {t} WHERE {c} IN ({','.join('?' * len(NO_DOWNLOAD))})", sorted(NO_DOWNLOAD))
    for fts in ("segments_fts", "items_fts", "questions_fts"):
        db.execute(f"INSERT INTO {fts}({fts}) VALUES ('rebuild')")
    db.commit()
    db.execute("VACUUM")
    db.close()
    (OUT / "requirements.txt").write_text("mcp==2.3.0\nstarlette==1.10.0\npydantic==2.14.3\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.iterdir():  # keep .vercel/ (the link to the Vercel project), replace the rest
        if f.name != ".vercel":
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    html = (ROOT / "web" / "feed.html").read_text()
    for anchor, add in (("</style>", NOTICE_CSS + "\n</style>"), ("</header>", NOTICE + "\n  </header>")):
        assert anchor in html, anchor
        html = html.replace(anchor, add, 1)
    (OUT / "index.html").write_text(html)
    posts = [{k: v for k, v in p.items() if k != "notes"}
             for p in json.loads((ROOT / "data" / "posts" / "posts.json").read_text()) if p["id"] not in HOLD]
    (OUT / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, separators=(",", ":")))
    shutil.copy(ROOT / "data" / "posts" / "towns.json", OUT / "towns.json")
    shutil.copy(ROOT / "data" / "posts" / "units.json", OUT / "units.json")  # "Moj grad nije na popisu"
    podaci(posts)  # /podaci: the open-data package, whole and per town
    mcp_public()  # /mcp: the MCP server for any AI assistant
    (OUT / "film.html").write_text((ROOT / "web" / "film.html").read_text())  # the 3-minute video as a page
    shutil.copytree(ROOT / "web" / "film", OUT / "film")
    # "Kako agent odgovara": six questions answered only through the MCP server (demo/record.py)
    (OUT / "demo.html").write_text((ROOT / "web" / "demo.html").read_text().replace("← natrag na sjednice", "← natrag na objave"))
    shutil.copy(ROOT / "demo" / "demo.json", OUT / "demo.json")
    (OUT / "intro.html").write_text((ROOT / "web" / "intro.html").read_text())  # the live demo's opening
    (OUT / "favicon.svg").write_text(FAVICON)
    (OUT / "vercel.json").write_text(json.dumps(VERCEL, indent=1))
    print(f"{len(posts)} posts -> {OUT}")


if __name__ == "__main__":
    main()
