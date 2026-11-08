"""Export data/posts/posts.json as Reddit-ready markdown files for a person to post by hand:
one file per post, one weekly digest per city and ISO week, and a short how-to README.
Writes files only; it never contacts Reddit. The output directory is cleared and rewritten on each run.

Usage: .venv/bin/python posts/export_reddit.py
"""
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts"
OUT = POSTS / "reddit"
TOPIC_NAME = {"promet": "promet", "stanovanje": "stanovanje", "komunalno": "komunalno", "otpad": "otpad",
              "okolis": "okoliš", "proracun": "proračun", "porezi-i-naknade": "porezi i naknade",
              "vrtici-i-skole": "vrtići i škole", "mladi": "mladi", "sport": "sport", "kultura": "kultura",
              "socijala": "socijala", "zdravstvo": "zdravstvo", "gospodarstvo": "gospodarstvo",
              "prostorno-uredenje": "prostorno uređenje", "imenovanja": "imenovanja",
              "gradska-uprava": "gradska uprava"}
SIDE = {"za": "za", "protiv": "protiv", "suzdrzani": "suzdržani", "nepoznato": "", "predlagatelj": ""}
SEAT = [("za", "Za"), ("protiv", "Protiv"), ("suzdrzan", "Suzdržan"), ("nije_glasovao", "Nije glasovao"),
        ("odsutan", "Odsutan")]
DISCLOSURE = ("Objavu je automatski pripremio projekt Vijećnica, a pregledala ju je osoba. "
              "Ispravke uz izvor dobrodošle su u komentarima.")
TITLE_MAX, BODY_MAX = 300, 40000


def esc(s):
    """Escape markdown inline syntax, and block syntax at the start of each line."""
    s = re.sub(r"([\\*_`\[\]~^])", r"\\\1", str(s or ""))
    s = re.sub(r"(?m)^(\s*)([#>+-])", r"\1\\\2", s)
    return re.sub(r"(?m)^(\s*\d+)([.)])", r"\1\\\2", s)


def cell(s):
    """A table cell: escaped, on one line, and never containing a pipe."""
    return esc(str(s).replace("\n", " ")).replace("|", "\\|")


def n(v):
    return "–" if v is None else str(v)


def fmt_date(d):
    return ". ".join(str(int(x)) for x in reversed(d.split("-"))) + "."


def not_on_agenda(p):
    return "nije uvršten" in (p.get("status") or "")


def verdict(p):
    """Same rule as web/feed.html: an explicit result wins, otherwise compare za with protiv."""
    if not_on_agenda(p):
        return "Nije stavljeno na dnevni red"
    r = p.get("result") or ""
    if not r and p.get("protiv") is None:
        return "Rezultat nepoznat"
    passed = False if re.search(r"nije|odbij", r, re.I) else bool(
        re.search(r"usvoj|prihvać", r, re.I)) or (p.get("za") or 0) > (p.get("protiv") or 0)
    return "Usvojeno" if passed else "Nije usvojeno"


def counts(p):
    return f"{n(p.get('za'))} za, {n(p.get('protiv'))} protiv, {n(p.get('suzdrzano'))} suzdržano"


def totals_note(p):
    """Drop the '(upisano 0)' remark when the count is unknown: we print '–', not 0."""
    note = p.get("totals_note") or ""
    if p.get("protiv") is None or p.get("suzdrzano") is None:
        note = re.sub(r"\s*\(upisano 0\)", "", note)
    return note


def title(p):
    tail = f" ({counts(p)})" if p["kind"] == "item" else ""
    head = f"[{p["city_name"]}] {p['headline']}"
    if len(head) + len(tail) > TITLE_MAX:  # shorten the headline, never the vote counts
        head = head[:TITLE_MAX - len(tail) - 1] + "…"
    base = head + tail
    if p["topics"] and len(t := f"{base} [{TOPIC_NAME[p['topics'][0]]}]") <= TITLE_MAX:
        base = t
    return base[:TITLE_MAX]


def front_matter(fields):
    q = lambda v: json.dumps(v, ensure_ascii=False)
    return "---\n" + "".join(f"{k}: {q(v)}\n" for k, v in fields.items()) + "---\n\n"


def footer(source):
    return f"---\n\n*{esc(source)}*\n\n{DISCLOSURE}\n"


def vote_section(p):
    out = ["**Glasovanje**", "", "| Za | Protiv | Suzdržano | Rezultat |", "|---|---|---|---|",
           f"| {n(p.get('za'))} | {n(p.get('protiv'))} | {n(p.get('suzdrzano'))} | {cell(verdict(p))} |"]
    if not_on_agenda(p):
        out += ["", "*Glasovalo se o uvrštavanju u dnevni red, a ne o samom prijedlogu, pa o njemu nije bilo rasprave.*"]
    if note := totals_note(p):
        out += ["", f"*{esc(note)}*"]
    return out


def club_section(clubs):
    out = ["**Kako su glasali klubovi**", "", "| Klub | " + " | ".join(t for _, t in SEAT) + " |",
           "|---|" + "---|" * len(SEAT)]
    out += [f"| {cell(c['party'])} | " + " | ".join(str(c.get(k) or 0) for k, _ in SEAT) + " |" for c in clubs]
    return out + ["", "*Prema službenom poimeničnom glasovanju. „Nije glasovao”: bio na sjednici, ali nije glasovao.*"]


def debate_line(e):
    who = f"**{esc(e['who'])}**"
    if e["side"] == "predlagatelj":
        who += "" if "predlagatelj" in e["who"] else " (predlagatelj)"
    elif e["side"] in SIDE:
        who += f" · {SIDE[e['side']]}" if SIDE[e["side"]] else ""
    else:
        who += f" · {esc(e['side'])}"
    return f"- {who}: {esc(e['point'])}"


def item_body(p):
    out = ["**Što je odlučeno**", "", esc(p["summary"]), ""]
    if p.get("why_it_matters"):
        out += ["**Zašto je važno**", "", esc(p["why_it_matters"]), ""]
    if p.get("debate"):
        out += ["**Tko je što rekao**", ""] + [debate_line(e) for e in p["debate"]] + [""]
    out += vote_section(p) + [""]
    if p.get("clubs"):
        out += club_section(p["clubs"]) + [""]
    if p.get("parts"):
        out += ["**Podtočke**", ""] + [f"- {esc(x)}" for x in p["parts"]] + [""]
    return "\n".join(out) + "\n" + footer(p["source"])


def digest_body(p):
    return "\n".join(f"- {esc(b)}" for b in p["bullets"]) + "\n\n" + footer(p["source"])


def post_file(p):
    meta = {"title": title(p), "flair": p["city_name"], "city": p["city"],
            "topics": p["topics"], "source": p["source"]}
    return front_matter(meta) + (item_body(p) if p["kind"] == "item" else digest_body(p))


BODY = {"zagreb": "Gradska skupština"}  # everywhere else: Gradsko vijeće


def decided(city):
    return "Gradska skupština odlučila" if BODY.get(city) else "gradsko vijeće odlučilo"


def weekly_section(p):
    notes = [n for n in (totals_note(p), "Glasovalo se samo o tome hoće li se točka staviti na dnevni red."
                         if not_on_agenda(p) else "") if n]
    extra = "".join(f"\n*{esc(x)}*\n" for x in notes)
    return f"### {esc(p['headline'])}\n\n**{verdict(p)}** ({counts(p)})\n{extra}\n{esc(p['summary'])}\n"


def weekly_files(city, week, posts):
    """One digest (split into parts if it would pass Reddit's body limit) for a city's ISO week."""
    items = sorted((p for p in posts if p["kind"] == "item"), key=lambda p: (p["date"], p["no"], p.get("sub", 0)))
    digests = sorted((p for p in posts if p["kind"] == "digest"), key=lambda p: p["date"])
    dates = sorted({p["date"] for p in posts})
    sessions = sorted({p["session"] for p in posts})
    when = ", ".join(fmt_date(d) for d in dates)
    intro = (f"Pregled odluka s {', '.join(f'{s}.' for s in sessions)} sjednice ({when}) prema službenom zapisniku. "
             "Odluke s glasovima protiv ili suzdržanima imaju i zasebnu objavu s detaljima.\n")
    blocks = [weekly_section(p) for p in items]
    if bullets := [b for d in digests for b in d["bullets"]]:
        blocks.append("## Jednoglasno (Ukratko)\n\n" + "\n".join(f"- {esc(b)}" for b in bullets) + "\n")
    source = "; ".join(dict.fromkeys(p["source"] for p in items + digests))
    tail = footer(source)
    room = BODY_MAX - len(intro) - len(tail) - 200
    parts, cur = [], []
    for b in blocks:
        if cur and sum(len(x) + 1 for x in cur) + len(b) > room:
            parts.append(cur)
            cur = []
        cur.append(b)
    parts.append(cur)
    out = {}
    for i, blocks_i in enumerate(parts, 1):
        suffix = f" ({i}/{len(parts)})" if len(parts) > 1 else ""
        meta = {"title": f"[{posts[0]["city_name"]}] Što je {decided(city)} ({when}){suffix}"[:TITLE_MAX],
                "flair": posts[0]["city_name"], "city": city,
                "topics": sorted({t for p in posts for t in p["topics"]}), "source": source}
        body = intro + "\n" + "\n".join(blocks_i) + "\n" + tail
        name = f"{city}-{week}" + (f"-part{i}" if len(parts) > 1 else "")
        out[name] = front_matter(meta) + body
    return out


def readme(posts):
    names = dict(sorted({p["city"]: p["city_name"] for p in posts}.items()))  # flair = the place's name
    flairs = "\n".join(f"| {c} | {name} | Politika |" for c, name in names.items())
    return f"""# Vijećnica na Redditu: upute za objavu

Ove datoteke generira `posts/export_reddit.py`; ne uređuj ih ručno jer se pri svakom pokretanju brišu i pišu iznova.
Svaka `.md` datoteka ima zaglavlje (title, flair, city, topics, source) i tijelo objave ispod drugog `---`.
Naslov kopiraj u polje za naslov, a tijelo (bez zaglavlja) u Markdown editor.

- `<id>.md`: jedna odluka ili sažetak jednoglasnih odluka.
- `weekly/<grad>-<godina>-W<tjedan>.md`: pregled jedne sjednice (ISO tjedan datuma sjednice).
  Ako je pregled predug za Reddit (40.000 znakova), podijeljen je u `-part1`, `-part2` itd.

## Prije objave

1. Provjeri pravila svakog subreddita i prije prve objave pitaj moderatore smiju li se ovakve objave dijeliti.
2. Pročitaj objavu do kraja i usporedi brojeve glasova sa zapisnikom navedenim u izvoru.
3. Nepoznati brojevi glasova prikazani su kao „–”, a ne kao 0. Nemoj ih mijenjati u 0.
4. „Nije stavljeno na dnevni red” nije isto što i „odbijeno”: vijeće je glasovalo samo o tome hoće li se o prijedlogu raspravljati.

## Flairovi

| Grad (`city`) | Flair u našem subredditu | Flair u r/croatia i r/hrvatska |
|---|---|---|
{flairs}

## Prvi komentar (prikvači ga)

> Ovo je neutralan sažetak službenog zapisnika sjednice gradskog vijeća (u Zagrebu Gradske skupštine). Pripremio ga je projekt Vijećnica uz pomoć
> automatskog alata, a prije objave pregledala ga je osoba. Službeni dokumenti uvijek imaju prednost.
> Ako vidiš pogrešku, napiši je u komentar uz izvor (zapisnik, točku dnevnog reda) i ispravit ćemo objavu.
> Ne zastupamo nijednu stranku ni vijećnika.

## Ritam objavljivanja

- Nema masovnog objavljivanja, pogotovo s novog računa: najviše nekoliko objava dnevno.
- U r/croatia i r/hrvatska najviše jedna objava dnevno, i to tjedni pregled, a ne pojedine odluke.
- Između objava u različitim subredditima pričekaj nekoliko sati; istu objavu ne šalji u više subreddita odjednom.
- Odgovaraj na komentare i ispravke; ako je nešto pogrešno, uredi objavu i to napiši u prikvačenom komentaru.
"""


def main():
    posts = json.loads((POSTS / "posts.json").read_text())
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "weekly").mkdir(parents=True)
    for p in posts:
        (OUT / f"{p['id']}.md").write_text(post_file(p))
    weeks = {}
    for p in posts:
        y, w, _ = datetime.date.fromisoformat(p["date"]).isocalendar()
        weeks.setdefault((p["city"], f"{y}-W{w:02d}"), []).append(p)
    n_weekly = 0
    for (city, week), group in sorted(weeks.items()):
        for name, text in weekly_files(city, week, group).items():
            (OUT / "weekly" / f"{name}.md").write_text(text)
            n_weekly += 1
    (OUT / "README.md").write_text(readme(posts))
    print(f"{len(posts)} posts, {n_weekly} weekly digests -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
