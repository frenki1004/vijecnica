"""Static demo of the feed for a host without Python (Vercel): deploy/vijecnica/ with index.html (web/feed.html),
posts.json (data/posts/posts.json without the writers' internal notes and without posts held back for review),
favicon.svg and a vercel.json that serves /api/posts from posts.json, the path the feed already uses.

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
HOLD = {"zagreb-12-37-2", "zagreb-11-9-1"}
NOTICE = ('<p class="demo-note">Demo za Datathon Portala otvorenih podataka: objave su strojni nacrti iz službenih '
          'zapisnika i još ih nije pregledala osoba. Službeni dokumenti imaju prednost.</p>')
NOTICE_CSS = (".demo-note{margin:10px 0 0;padding:8px 12px;border-radius:8px;background:var(--soft);"
              "color:var(--muted);font-size:14px}")
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" '
           'fill="#1d4f9c"/><path d="M6 13 16 6l10 7zM8 14h3v9H8zm6.5 0h3v9h-3zM21 14h3v9h-3zM6 24h20v3H6z" '
           'fill="#fff"/></svg>')
VERCEL = {"$schema": "https://openapi.vercel.sh/vercel.json", "framework": None, "buildCommand": "",
          "rewrites": [{"source": "/api/posts", "destination": "/posts.json"}, {"source": "/feed", "destination": "/"}],
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
    (OUT / "favicon.svg").write_text(FAVICON)
    (OUT / "vercel.json").write_text(json.dumps(VERCEL, indent=1))
    print(f"{len(posts)} posts -> {OUT}")


if __name__ == "__main__":
    main()
