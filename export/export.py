"""CKAN-ready open-data export of the DB: data/export/<city>/*.csv + data/export/datapackage.json.

  python3 export/export.py

Frictionless Data Package (CKAN's ckanext-datapackager / data.gov.hr can ingest it): one resource per
table per city, with a column schema. UTF-8 CSV, comma-separated, header row. Nothing is uploaded.
"""
import csv
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# overrides (export/check_rebuild.sh builds into a scratch copy, never the live DB/export)
DB = Path(os.environ["VIJECNICA_DB"]) if os.environ.get("VIJECNICA_DB") else ROOT / "data" / "vijecnica.db"
OUT = Path(os.environ["VIJECNICA_EXPORT_OUT"]) if os.environ.get("VIJECNICA_EXPORT_OUT") else ROOT / "data" / "export"

TABLES = {
    "sessions": ("Sjednice: broj, datum, naziv, poveznica na službeni zapisnik",
                 "SELECT n AS session, date, title, url, minutes_url FROM sessions WHERE city = ? ORDER BY n"),
    "items": ("Točke dnevnog reda: naslov, predlagatelj, status, zbroj glasova, početak rasprave u snimci (s)",
              """SELECT session, no AS item_no, sub, title, proposer, status, za, protiv, suzdrzano, result, url,
                        video_id, round(t_start, 1) AS t_start_s, round(t_vote, 1) AS t_vote_s
                 FROM items WHERE city = ? ORDER BY session, no, sub"""),
    "spoken_votes": ("Rezultati glasovanja izgovoreni u snimci (Slavonski Brod, prije zapisnika): NESLUŽBENO, "
                     "strojno iz riječi predsjedatelja; source='snimka'",
                     """SELECT session, item_no, sub, n, label, za, protiv, suzdrzano, unanimous, outcome, video_id,
                               round(t, 1) AS t_s, source FROM spoken_votes WHERE city = ? ORDER BY session, item_no, n"""),
    "votes": ("Poimenično glasovanje (samo Zagreb): član, glas (za/protiv/suzdrzan/odsutan = nije bio na sjednici/"
              "nije_glasovao = bio na sjednici, nije glasovao). source: oznaka = X u stupcu PDF-a, bez_oznake = redak s "
              "imenom bez ijedne oznake (glas izveden iz popisa nazočnosti)",
              "SELECT session, item_no, sub, member, vote, source FROM votes WHERE city = ? ORDER BY session, item_no, sub, member"),
    "attendance": ("Nazočnost članova po sjednici (1 = nazočan)",
                   "SELECT session, member, present FROM attendance WHERE city = ? ORDER BY session, member"),
    "members": ("Članovi predstavničkog tijela i stranka. Popis uključuje i zamjenike (Zagreb: 56 imena za 47 mjesta); "
                "datumi početka i kraja mandata nisu u izvoru, pa članstvo po sjednici pokazuje attendance.csv",
                "SELECT name, party FROM members WHERE city = ? ORDER BY name"),
    "questions": ("Pitanja u aktualnom satu s fonogramom (službeni doslovni zapis)",
                  """SELECT id, session, member, party, question, to_whom, answered_by, url, fonogram
                     FROM questions WHERE city = ? ORDER BY session, id"""),
    "segments": ("Strojni transkript snimki sjednica (Whisper, hrvatski model), odsječci s vremenom u sekundama",
                 """SELECT s.video_id, s.session, v.part, round(s.start, 2) AS start_s, round(s.end, 2) AS end_s, s.text
                    FROM segments s JOIN videos v ON v.id = s.video_id WHERE s.city = ? ORDER BY s.video_id, s.start"""),
    "speaker_turns": ("Strojno prepoznati istupi govornika (iz poziva predsjedatelja u transkriptu)",
                      """SELECT session, video_id, item_no, sub, round(start, 1) AS start_s, round(end, 1) AS end_s,
                                speaker, role, kind, method FROM speaker_turns WHERE city = ? ORDER BY video_id, start"""),
    "promises": ("Obećanja izvršne vlasti u odgovorima na pitanja (strojno izdvojeno iz fonograma)",
                 """SELECT id, session, question_id, asked_by, speaker, deadline, deadline_date, quote, topic
                    FROM promises WHERE city = ? ORDER BY session, id"""),
}
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collect"))
from netcom import UNITS as NETCOM  # noqa: E402

SOURCES = {
    "zagreb": {"title": "Grad Zagreb, Gradska skupština (web.zagreb.hr) i YouTube kanal Gradske skupštine",
               "path": "https://web.zagreb.hr/Sjednice/2025/"},
    "brod": {"title": "Grad Slavonski Brod (slavonski-brod.hr): sjednice, tonski zapisi, zapisnici",
             "path": "https://www.slavonski-brod.hr"},
    "krk": {"title": "Grad Krk (grad-krk.hr): sjednice, zapisnici i tonski zapisi, vijesti sa sjednica",
            "path": "https://www.grad-krk.hr/gradska-uprava/gradsko-vijece"},
    "rijeka": {"title": "Grad Rijeka (rijeka.hr): sjednice s dnevnim redom i aktima, snimke na YouTubeu",
               "path": "https://www.rijeka.hr/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/"},
    "osijek": {"title": "Grad Osijek (osijek.hr): sjednice, dnevni red, zapisnici i snimke",
               "path": "https://www.osijek.hr/prijenos-sjednice/"},
    "sibenik": {"title": "Grad Šibenik (sibenik.hr): sjednice, materijali i zapisnici",
                "path": "https://www.sibenik.hr/stranice/sjednice-gradskog-vijeca-2025-2029/260.html"},
    "cakovec": {"title": "Grad Čakovec (cakovec.hr): sjednice, materijali, zapisnici i audio zapisi",
                "path": "https://www.cakovec.hr/kategorija/gradsko-vijece/"},
    "zadar": {"title": "Grad Zadar (grad-zadar.hr): sjednice, materijali, izvadci iz zapisnika, snimke na YouTubeu", "path": "https://www.grad-zadar.hr/sjednice-gradskog-vijeca-625/"},
    "pula": {"title": "Grad Pula (pula.hr): sjednice, materijali, skraćeni zapisnici", "path": "https://www.pula.hr/hr/gradska-uprava/gradsko-vijece/sjednice-gradskog-vijeca/"},
    "karlovac": {"title": "Grad Karlovac (karlovac.hr): sjednice, dnevni red, materijali i zapisnici (u paketu materijala), snimke na YouTubeu", "path": "https://www.karlovac.hr/"},
    "varazdin": {"title": "Grad Varaždin (varazdin.hr): sjednice, materijali, skraćeni zapisnici, snimke na YouTubeu", "path": "https://varazdin.hr/"},
    "dubrovnik": {"title": "Grad Dubrovnik (dubrovnik.hr): sazivi sjednica s dnevnim redom, snimke na YouTubeu (zapisnici nisu objavljeni)", "path": "https://www.dubrovnik.hr/gradska-uprava/gradsko-vijece"},
    "sisak": {"title": "Grad Sisak (sisak.hr): sjednice, materijali, zapisnici", "path": "https://sisak.hr/zapisnici-sa-sjednica/"},
    "kastela": {"title": "Grad Kaštela (kastela.hr): sjednice, materijali, zapisnici, snimke na YouTubeu", "path": "https://kastela.hr/kategorija-gradskog-vijeca/mandatno-razdoblje-2025-2029/"},
    "bjelovar": {"title": "Grad Bjelovar (bjelovar.hr): najave sjednica s materijalima, zapisnici, snimke na YouTubeu", "path": "https://www.bjelovar.hr/dokumenti-kategorija/zapisnici/"},
    "velika_gorica": {"title": "Grad Velika Gorica (gorica.hr): sjednice, materijali i zapisnici (paketi preuzeti ručno), audio zapisi",
                      "path": "https://gorica.hr/gradsko-vijece-2/sjednice-gradskog-vijeca/"},
    "samobor": {"title": "Grad Samobor (samobor.hr): sjednice, materijali i zapisnici (paketi preuzeti ručno; Grad u robots.txt isključuje AI sustave)",
                "path": "https://www.samobor.hr/grad/sjednice-c229"},
    "brckovljani": {"title": "Općina Brckovljani (www.brckovljani.hr): samo poziv na konstituirajuću sjednicu i službeni glasnik; zapisnici nisu objavljeni", "path": "https://www.brckovljani.hr"},
    "gradiste": {"title": "Općina Gradište (www.gradiste.hr): proračunski akti; zapisnici ovog saziva nisu objavljeni", "path": "https://www.gradiste.hr"},
    "cernik": {"title": "Općina Cernik (cernik.hr): zapisnici (djelomično), službeni glasnik", "path": "https://cernik.hr"},
    "svetijuraj": {"title": "Općina Sveti Juraj na Bregu (www.svetijurajnabregu.hr): sazivi i zapisnici sjednica", "path": "https://www.svetijurajnabregu.hr"},
    "marijagorica": {"title": "Općina Marija Gorica (www.marija-gorica.hr): paketi materijala sa zapisnicima (djelomično), službeni glasnik", "path": "https://www.marija-gorica.hr"},
    # 13 units on NetCom eSjednice public portals (collect/netcom.py)
    **{k: {"title": f"{u['name']} (eSjednice, {u['host']}): sjednice, dnevni red, odluke"
                    + (" i zapisnici" if u["tier"] == "A" else ""), "path": f"https://{u['host']}"}
       for k, u in NETCOM.items()},
}
ATTRIBUTION = ("Izvor: službene stranice predstavničkih tijela (" + ", ".join(s["path"] for s in SOURCES.values())
               + "); strojno izvedeni podaci")
# Exact source pages per table (URL patterns). Official texts are re-used under the Zakon o pravu na pristup
# informacijama (ponovna uporaba informacija) and the source's terms; CC BY 4.0 applies only to what this
# project derives (parsing, columns, transcripts' timing, speaker turns, promises), not to the official text.
URLS = {
    "zagreb": {
        "sessions": ["https://web.zagreb.hr/Sjednice/2025/Sjednice_Skupstine_2025.nsf/DRJ_?OpenAgent&<n>.",
                     "https://web.zagreb.hr/Sjednice/2025/Sjednice_Skupstine_2025.nsf/zapisnik_?OpenAgent"],
        "items": ["https://web.zagreb.hr/Sjednice/2025/Sjednice_Skupstine_2025.nsf/PW_NEW_?OpenForm&ParentUNID=<unid>"],
        "votes": ["roll-call PDF 'Izvještaj glasovanja za točku dnevnog reda' attached to each item page"],
        "attendance": ["https://web.zagreb.hr/Sjednice/2025/SkupstinaZapisi_2025.nsf/(sjednice_prisutnost)?OpenAgent&<n>."],
        "members": ["https://web.zagreb.hr/Sjednice/2025/SkupstinaZapisi_2025.nsf/(sjednice_prisutnost)?OpenAgent&<n>."],
        "questions": ["https://web.zagreb.hr/Sjednice/2025/SkupstinaZapisi_2025.nsf/web_pitanja_?OpenAgent&<n>.",
                      "fonogram PDF attached to each question"],
        "segments": ["https://www.youtube.com/channel/UCRMm4Xt9ruoQ8FG7NpIHCsA (session recordings)"],
        "speaker_turns": ["derived from segments"], "promises": ["derived from questions.fonogram"],
    },
    "brod": {
        "sessions": ["https://www.slavonski-brod.hr/gradska-uprava/gradsko-vijece/469-sjednice-gv/sjednice-2025-2029/<id>",
                     "https://www.slavonski-brod.hr/images/Zapisnici/Vijece/<year>/<n>_sjednica.pdf (pisani zapisnici)"],
        "items": ["https://www.slavonski-brod.hr/gradska-uprava/gradsko-vijece/469-sjednice-gv/sjednice-2025-2029/<id>",
                  "vote totals: text of the minutes PDF"],
        "attendance": ["minutes PDF: 'Nazočni vijećnici: … Nisu nazočni: …'"],
        "members": ["https://www.slavonski-brod.hr (popis vijećnika i klubova)"],
        "segments": ["https://www.slavonski-brod.hr/images/Zapisnici/Vijece/Tonski/2025_2029/<n>/<part>_dio.mp3"],
        "spoken_votes": ["derived from segments (chair's words); unofficial"],
        "speaker_turns": ["derived from segments"],
    },
    "krk": {
        "sessions": ["https://www.grad-krk.hr/gradska-uprava/gradsko-vijece/sjednice/sjednice-<year>/<slug>",
                     "https://www.grad-krk.hr/gradska-uprava/gradsko-vijece/zapisnici-i-tonski-zapisnici/zapisnici-<year>"],
        "items": ["https://www.grad-krk.hr/gradska-uprava/gradsko-vijece/sjednice/sjednice-<year>/<slug>",
                  "vote totals: minutes PDF, else the city's news report of the session"],
        "segments": ["https://www.grad-krk.hr/sites/default/files/audiofiles/<file>.mp3 (službeni tonski zapis)"],
        "spoken_votes": ["derived from segments (chair's words); unofficial"],
        "speaker_turns": ["derived from segments"],
    },
    "rijeka": {
        "sessions": ["https://www.rijeka.hr/session/<slug>/"],
        "items": ["https://www.rijeka.hr/session/<slug>/ (Točka N: prijedlog, doneseni akt, amandmani, zaključci odbora)"],
        "segments": ["https://www.youtube.com/watch?v=<id> (snimka sjednice, embedded on the session page)"],
        "speaker_turns": ["derived from segments"],
    },
}
OFFICIAL_TEXT = {"sessions", "items", "questions", "members", "attendance", "votes"}
DERIVED = {"segments", "speaker_turns", "promises", "spoken_votes"}
REUSE = {"name": "ZPPI-ponovna-uporaba", "title": "Službeni tekst: ponovna uporaba informacija prema Zakonu o pravu na "
         "pristup informacijama (NN 25/13, 85/15, 69/22) i uvjetima izvora; navesti izvor", "path":
         "https://www.zakon.hr/z/126/Zakon-o-pravu-na-pristup-informacijama"}
CCBY = {"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/",
        "title": "Creative Commons Attribution 4.0 (samo izvedeni stupci i strojno izvedeni podaci)"}
PERSONAL = ("Osobni podaci: imena i izjave izabranih dužnosnika i službenika u obavljanju javne funkcije, iz javno "
            "objavljenih izvora. Transkripti mogu sadržavati imena građana spomenutih na sjednici; na zahtjev se uklanjaju.")


def raw_manifest():
    """sha256 + size + file mtime (= when it was fetched; the collectors do not record it separately) for data/raw."""
    out = []
    for base in (ROOT / "data" / "raw", *(ROOT / "data" / c / "raw" for c in ("brod", "krk", "rijeka"))):
        for f in sorted(base.rglob("*")):
            if f.is_file():
                h = hashlib.sha256()
                with f.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                st = f.stat()
                out.append({"path": str(f.relative_to(ROOT)), "bytes": st.st_size, "sha256": h.hexdigest(),
                            "fetched_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return out
TYPES = {int: "integer", float: "number", str: "string"}


def main():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    resources = []
    for city, cname in db.execute("SELECT id, name FROM cities ORDER BY id").fetchall():
        (OUT / city).mkdir(parents=True, exist_ok=True)
        for name, (desc, sql) in TABLES.items():
            cur = db.execute(sql, (city,))
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            if not rows:
                (OUT / city / f"{name}.csv").unlink(missing_ok=True)
                continue
            path = OUT / city / f"{name}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            types = {}
            for i, c in enumerate(cols):
                seen = {type(r[i]) for r in rows if r[i] is not None}
                types[c] = "number" if seen == {int, float} else TYPES.get(next(iter(seen)), "string") if len(seen) == 1 else "string"
            resources.append({"name": f"{city}-{name}".replace("_", "-"), "path": f"{city}/{name}.csv",
                              "title": f"{cname}: {name}", "description": desc, "format": "csv", "mediatype": "text/csv",
                              "encoding": "utf-8", "rows": len(rows), "bytes": path.stat().st_size,
                              "schema": {"fields": [{"name": c, "type": types[c]} for c in cols]},
                              "sources": [{**SOURCES[city], "url_patterns": URLS.get(city, {}).get(name, [])}],
                              "licenses": ([REUSE, CCBY] if name in OFFICIAL_TEXT else [CCBY]),
                              "license_note": ("službeni tekst (naslovi, pitanja, fonogrami, zapisnici, glasovi) prenesen je "
                                               "doslovno: vrijede uvjeti izvora i ZPPI; CC BY 4.0 vrijedi za strukturu i "
                                               "izvedene stupce" if name in OFFICIAL_TEXT else
                                               "strojno izvedeno iz snimki/službenog teksta; CC BY 4.0; snimke ostaju "
                                               "vlasništvo izvora")})
            print(f"{city}/{name}.csv {len(rows)} rows")
    pkg = {
        "name": "vijecnica-gradska-vijeca-2025-2029",
        "title": f"eVijećnica: sjednice predstavničkih tijela ({len(SOURCES)} gradova i općina), saziv 2025.-2029.",
        "description": ("Strojno čitljivi podaci o radu predstavničkih tijela: dnevni red, poimenično glasovanje, "
                        "nazočnost, pitanja s fonogramima, strojni transkripti snimki sjednica, prepoznati govornici "
                        "i obećanja izvršne vlasti. Pripremljeno za objavu na data.gov.hr (CKAN)."),
        "version": date.today().isoformat(), "created": date.today().isoformat(), "language": "hr",
        "keywords": ["gradsko vijeće", "gradska skupština", "glasovanje", "transparentnost", "Zagreb", "Slavonski Brod"],
        "licenses": [CCBY, REUSE],
        "license_note": "Licenca je navedena po resursu: CC BY 4.0 samo za izvedene podatke, službeni tekst prema ZPPI i uvjetima izvora.",
        "attribution": ATTRIBUTION,
        "personal_data": PERSONAL,
        "raw_manifest": "raw_manifest.json (sha256, veličina i vrijeme dohvata svake preuzete datoteke)",
        "sources": list(SOURCES.values()),
        "resources": resources,
    }
    (OUT / "datapackage.json").write_text(json.dumps(pkg, ensure_ascii=False, indent=1))
    man = raw_manifest()
    (OUT / "raw_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=0))
    print("raw_manifest.json:", len(man), "files")
    # export hashes: lets someone check an offline rebuild against this one (export/check_rebuild.sh)
    (OUT / "export_sha256.txt").write_text("".join(
        f"{hashlib.sha256((OUT / r['path']).read_bytes()).hexdigest()}  {r['path']}\n" for r in resources))
    (OUT / "README.txt").write_text(
        "eVijećnica open-data export (CKAN / Frictionless Data Package).\n"
        f"{ATTRIBUTION}.\nLicenca izvedenih podataka: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).\n"
        "Službeni tekst (naslovi točaka, pitanja, fonogrami, zapisnici) prenesen je doslovno: za njega vrijede uvjeti izvora i\n"
        "ponovna uporaba prema Zakonu o pravu na pristup informacijama, ne CC BY. Licenca po datoteci: datapackage.json.\n"
        f"{PERSONAL}\n"
        "Regenerate: python3 export/export.py\n"
        "Opis stupaca: datapackage.json. Transkripti, govornici i obećanja su strojno izvedeni.\n")
    print("datapackage.json:", len(resources), "resources")


if __name__ == "__main__":
    main()
