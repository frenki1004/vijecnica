"""Links to the item's own documents (proposal, explanation, report) on each post: posts.json gets "docs".

For every agenda-item post: first the documents the writer actually read (data/posts/materials.json), then the
best-scored other attachments (collect/materials.py score), at most 2, each {"name", "url"} with an absolute public
URL. Files we hold only as a manual download (manual/...) are replaced by the city's public link to the session
materials when the item lists one (Dubrovnik: cloud.dubrovnik.hr). Idempotent; posts/assemble.py calls add_docs().

Usage: python posts/docs.py   (rewrites data/posts/posts.json in place)
"""
import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collect"))
from materials import score  # noqa: E402


def label(name):
    n = re.sub(r"\.(pdf|docx?|xlsx?|odt|zip)$", "", name.strip(), flags=re.I).rstrip(". ")
    n = re.sub(r"^\d+[.)]?\s*", "", n)  # "33.Prijedlog …" -> "Prijedlog …"
    return n[:1].upper() + n[1:] if n else "Dokument"


def add_docs(posts):
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'vijecnica.db'}?mode=ro", uri=True)
    site = dict(db.execute("SELECT id, site FROM cities"))
    mats = json.loads((ROOT / "data" / "posts" / "materials.json").read_text())
    n = 0
    for p in posts:
        p.pop("docs", None)
        if p.get("kind") != "item":
            continue
        row = db.execute("SELECT attachments FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
                         (p["city"], p["session"], p["no"], p["sub"])).fetchone()
        att = json.loads(row[0]) if row and row[0] else []
        used = [d["name"] for d in mats.get(p["id"]) or []]
        ranked = sorted(att, key=lambda d: (d["name"] not in used, -score(d["name"])))
        public = next((d for d in att if d["url"].startswith("http") and "materijali" in d["name"].lower()), None)
        docs, seen = [], set()
        for d in ranked:
            if score(d["name"]) <= -5 and d["name"] not in used:
                continue
            if d["url"].startswith("manual/"):
                if not public:
                    continue
                d = {"name": public["name"], "url": public["url"]}
            url = urllib.parse.quote(urllib.parse.urljoin(site.get(p["city"], "") + "/", d["url"]), safe=":/?=&%$#~+,;@")
            if url in seen or not url.startswith("http"):
                continue
            seen.add(url)
            docs.append({"name": label(d["name"]), "url": url})
            if len(docs) == 2:
                break
        if docs:
            p["docs"] = docs
            n += 1
    return n


if __name__ == "__main__":
    f = ROOT / "data" / "posts" / "posts.json"
    posts = json.loads(f.read_text())
    n = add_docs(posts)
    f.write_text(json.dumps(posts, ensure_ascii=False, indent=1))
    print(f"{n} of {len(posts)} posts have document links")
