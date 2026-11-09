"""Static demo of the feed for a host without Python (Vercel): deploy/vijecnica/ with index.html (web/feed.html),
posts.json (data/posts/posts.json without the writers' internal notes and without posts held back for review),
film.html with web/film/ (the 3-minute video as a page, /film),
towns.json (data.gov.hr facts per town), otvoreni-podaci.zip (the export/export.py Data Package), favicon.svg and a
vercel.json that serves /api/posts and /api/towns from the JSON files, the paths the feed already uses.

The demo carries a notice: its posts are machine drafts that no person has reviewed yet.

Live: https://vijecnica.vercel.app
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
        *(f"varazdin-7-{n}-1" for n in range(5, 14)), "split-7-39-1", "sibenik-5-11-1"}
NOTICE = ('<p class="demo-note">Demo za Datathon Portala otvorenih podataka: objave su strojni nacrti iz službenih '
          'zapisnika i još ih nije pregledala osoba. Službeni dokumenti imaju prednost. '
          '<a href="otvoreni-podaci.zip" download>Preuzmi otvorene podatke</a> (CSV i Frictionless Data Package '
          'spreman za CKAN, 20 gradova i općina; licenca po resursu u datapackage.json).</p>')
EXPORT = ROOT / "data" / "export"  # export/export.py
NOTICE_CSS = (".demo-note{margin:10px 0 0;padding:8px 12px;border-radius:8px;background:var(--soft);"
              "color:var(--muted);font-size:14px}")
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" '
           'fill="#1d4f9c"/><path d="M6 13 16 6l10 7zM8 14h3v9H8zm6.5 0h3v9h-3zM21 14h3v9h-3zM6 24h20v3H6z" '
           'fill="#fff"/></svg>')
VERCEL = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": None, "buildCommand": "",
          "rewrites": [{"source": "/api/posts", "destination": "/posts.json"}, {"source": "/film", "destination": "/film.html"},
                       {"source": "/api/towns", "destination": "/towns.json"}, {"source": "/feed", "destination": "/"}],
          "headers": [{"source": "/posts.json", "headers": [{"key": "Cache-Control", "value": "public, max-age=300"}]}]}


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
    shutil.make_archive(str(OUT / "otvoreni-podaci"), "zip", EXPORT)  # the open-data package, as published
    (OUT / "film.html").write_text((ROOT / "web" / "film.html").read_text())  # the 3-minute video as a page
    shutil.copytree(ROOT / "web" / "film", OUT / "film")
    (OUT / "favicon.svg").write_text(FAVICON)
    (OUT / "vercel.json").write_text(json.dumps(VERCEL, indent=1))
    print(f"{len(posts)} posts -> {OUT}")


if __name__ == "__main__":
    main()
