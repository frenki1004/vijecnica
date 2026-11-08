"""data.gov.hr connector: register of local units, 2025 local election results, the cities' own datasets.

Everything starts at the national open-data portal's CKAN API (https://data.gov.hr/ckan/api/3/action/...):
package_search finds a dataset, package_show gives its publisher, licence, modification time and resource URLs,
and the resource is downloaded from the URL the portal lists. One dataset is not on data.gov.hr: the DIP
dataset "Rezultati lokalnih izbora" there stops at 2021, so the 2025 file is taken from the same DIP archive
(same URL pattern as the 2013/2017 resources of that dataset) and marked as such in the provenance.

Datasets used (see SOURCES; package_show is called for every one):
  popis-javnopravnih-tijela        MPUDT, live JSON API jpt.gov.hr: every JLS with OIB, official JPT code, county
  adresar-tijela-javne-vlasti      official website of each grad/općina (XML)
  statistika-u-nizu-popis-...-2021 DZS census 2021, population per grad/općina (XLSX, sheet "1.")
  rezultati-lokalnih-izbora        DIP (2013-2021 on the portal; 2025 from izbori.hr, see above)
  https-porezna-uprava-...-4009    Porezna uprava: income-tax rates 2025 vs 2026 per unit (council decisions)
  gradska-skupstina-grada-zagreba  Grad Zagreb: seats per party in the assembly today (Zagreb cross-check)
  registar-biraca-broj-biraca      MPUDT: voters per address (80 MB CSV, only with --voters; per-unit totals kept)
  + organisation listings (package_search fq=organization:<org>) for our 19 cities -> datagovhr_datasets

Council seats: Zakon o lokalnoj i područnoj (regionalnoj) samoupravi čl. 28 (NN 144/20) sets the council size
from the 2021 census population (Grad Zagreb: 47, Zakon o Gradu Zagrebu); seats per list = D'Hondt over lists
with at least 5 % of valid votes (Zakon o lokalnim izborima čl. 98). Extra seats for national minorities
(appointed afterwards when a minority is under-represented) are not computed.

Cache: data/datagovhr/raw/<sha1 of url>.<ext> (+ raw/manifest.json: url, download time, sha256). At least 1 s
between requests, same UA as the other collectors. Output: data/datagovhr/*.json, loaded by db/build.py.

Usage: python collect/datagovhr.py [--fresh] [--voters]
       (--fresh re-asks the CKAN API, files stay cached; --voters adds the 80 MB voter register)
"""
import csv
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datagovhr"
RAW = OUT / "raw"
CKAN = "https://data.gov.hr/ckan/api/3/action/"
PORTAL = "https://data.gov.hr/ckan/dataset/"
UA = "vijecnica-research/0.1 (open data hackathon)"
DIP_2025 = "https://www.izbori.hr/arhiva-izbora/data/lokalni/2025/zip/rezultati.zip"
_last = [0.0]
FRESH = [False]  # --fresh: re-ask every CKAN API call

# our key -> (name as in the census, grad|općina); Zagreb is "Grad Zagreb" everywhere
OURS = {
    "zagreb": ("Zagreb", "grad"), "brod": ("Slavonski Brod", "grad"), "rijeka": ("Rijeka", "grad"),
    "krk": ("Krk", "grad"), "osijek": ("Osijek", "grad"), "sibenik": ("Šibenik", "grad"),
    "opatija": ("Opatija", "grad"), "kastav": ("Kastav", "grad"), "senj": ("Senj", "grad"),
    "ogulin": ("Ogulin", "grad"), "viskovo": ("Viškovo", "općina"), "punat": ("Punat", "općina"),
    "kostrena": ("Kostrena", "općina"), "novivinodolski": ("Novi Vinodolski", "grad"),
    "makarska": ("Makarska", "grad"), "ploce": ("Ploče", "grad"), "omisalj": ("Omišalj", "općina"),
    "baska": ("Baška", "općina"), "cavle": ("Čavle", "općina"), "cakovec": ("Čakovec", "grad"),
}
# datasets of our cities that are about the council, sessions, councillors, acts, budget or elections
TOPIC = re.compile(r"vijeć|vijec|sjednic|skupštin|zastupni|vijećni|odluk|akt[ia]? |službeni (glasnik|list|novine)|"
                   r"proračun|proracun|financijsk|izbor|mandat|savjet mladih|javn[ae] savjetovanj|transparent", re.I)


# ---------------------------------------------------------------- HTTP + cache + provenance

def _manifest():
    f = RAW / "manifest.json"
    return json.loads(f.read_text()) if f.exists() else {}


MANIFEST = None


def fetch(url, ext="", fresh=False, timeout=600):
    """Path of the cached file for url; downloads it (politely) when missing or fresh."""
    global MANIFEST
    MANIFEST = MANIFEST if MANIFEST is not None else _manifest()
    path = RAW / (hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if not path.exists() or fresh:
        for attempt in (1, 2):  # data.zagreb.hr is slow: one retry
            time.sleep(max(0, 1.0 - (time.time() - _last[0])))
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                              timeout=timeout).read()
                break
            except (TimeoutError, OSError) as e:
                if attempt == 2:
                    raise
                print(f"  retry {url}: {e}")
            finally:
                _last[0] = time.time()
        RAW.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        MANIFEST[path.name] = {"url": url, "downloaded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        (RAW / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1))
    return path


def api(action, fresh=False, **params):
    """CKAN action API call, result part of the answer."""
    url = CKAN + action + ("?" + urllib.parse.urlencode(params) if params else "")
    d = json.loads(fetch(url, ".json", fresh or FRESH[0]).read_text())
    if not d.get("success"):
        raise RuntimeError(f"CKAN {action} {params}: {d.get('error')}")
    return d["result"]


SOURCES = []  # provenance rows: one per (dataset, resource) actually used


def resource(dataset, match, fresh=False, ext="", url=None, note=None):
    """package_show(dataset) -> download the resource whose url/name matches `match` -> cached path.
    `url` overrides the resource URL (DIP 2025: not listed on the portal), recorded with `note`."""
    p = api("package_show", fresh, id=dataset)
    r = next((r for r in p["resources"] if re.search(match, (r.get("url") or "") + " " + (r.get("name") or ""))),
             None)
    if r is None and url is None:
        raise RuntimeError(f"{dataset}: no resource matching {match!r}")
    rurl = url or r["url"]
    path = fetch(rurl, ext, timeout=900)
    m = MANIFEST[path.name]
    SOURCES.append({"dataset_id": p["id"], "dataset": p["name"], "title": p["title"],
                    "publisher": (p.get("organization") or {}).get("title"),
                    "license": p.get("license_title") or p.get("license_id"),
                    "metadata_modified": p["metadata_modified"], "dataset_url": PORTAL + p["name"],
                    "resource_url": rurl, "resource_name": r.get("name") if r else None,
                    "downloaded": m["downloaded"], "sha256": m["sha256"], "note": note})
    return path


# ---------------------------------------------------------------- minimal XLSX reader (zipfile + xml)

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class Xlsx:
    def __init__(self, src):
        self.z = zipfile.ZipFile(src)
        self.ss = []
        if "xl/sharedStrings.xml" in self.z.namelist():
            for _, el in ET.iterparse(self.z.open("xl/sharedStrings.xml")):
                if el.tag == M + "si":
                    self.ss.append("".join(t.text or "" for t in el.iter(M + "t")))
                    el.clear()
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))}
        self.sheets = {s.get("name"): "xl/" + rels[s.get(REL + "id")].lstrip("/").removeprefix("xl/")
                       for s in ET.fromstring(self.z.read("xl/workbook.xml")).iter(M + "sheet")}

    def rows(self, name):
        for _, r in ET.iterparse(self.z.open(self.sheets[name])):
            if r.tag != M + "row":
                continue
            row = {}
            for c in r.findall(M + "c"):
                t, v = c.get("t"), c.find(M + "v")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(M + "t"))
                elif v is None:
                    continue
                else:
                    val = self.ss[int(v.text)] if t == "s" else v.text
                n = 0
                for ch in re.match(r"[A-Z]+", c.get("r")).group():
                    n = n * 26 + ord(ch) - 64
                row[n - 1] = val
            r.clear()
            yield [row.get(j) for j in range(max(row) + 1)] if row else []


# ---------------------------------------------------------------- names

def fold(s):
    """ASCII, upper case, single spaces: 'Primorsko-goranska  ŽUPANIJA' -> 'PRIMORSKO-GORANSKA ZUPANIJA'."""
    s = unicodedata.normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).upper().strip()


def county_key(s):
    return re.sub(r"\s*ZUPANIJA\s*", " ", fold(s)).strip()


def unit_key(name):
    return re.sub(r"[^A-Z0-9]+", " ", fold(name)).strip()


# ---------------------------------------------------------------- 1. register of units

def load_units():
    jpt = json.loads(resource("popis-javnopravnih-tijela", r"PopisOznakaNaDanasnjiDan", ext=".json").read_text())
    units = {}
    for b in jpt:
        kind = b["VrstaJPT"]
        if not kind.startswith("Jedinica lokalne") or kind.endswith("Županija"):
            continue
        typ = "općina" if kind.endswith("Općina") else "grad"
        name = re.sub(r"^(GRAD|OPĆINA)\s+", "", b["Naziv"]) if b["Naziv"] != "GRAD ZAGREB" else "ZAGREB"
        county = "GRAD ZAGREB" if b["Naziv"] == "GRAD ZAGREB" else county_key(b["Zupanija"])
        units[(county, typ, unit_key(name))] = {
            "code": b["Oznaka"], "oib": b["OIB"], "name": b["Naziv"], "short": name, "type": typ,
            "county": re.sub(r"\s+", " ", b["Zupanija"]).strip(), "website": None, "population": None,
            "email": ", ".join(b.get("Email") or []) or None}
    print(f"jpt.gov.hr: {len(units)} gradova i općina")

    # population, DZS census 2021, sheet "1." (ethnicity table; column 5 = total)
    pop = Xlsx(resource("statistika-u-nizu-popis-stanovnistva-kucanstava-i-stanova-2021",
                        r"po_gradovima_opcinama\.xlsx", ext=".xlsx"))
    hit = 0
    for r in pop.rows("1."):
        if len(r) > 5 and r[0] == "Grad Zagreb" and r[1] is None and (r[5] or "").isdigit():
            r = [r[0], "Grad", None, None, "Zagreb", r[5]]  # city-county: its own total row
        if len(r) > 5 and r[1] in ("Grad", "Općina") and r[4] and (r[5] or "").isdigit():
            typ = "grad" if r[1] == "Grad" else "općina"
            county = "GRAD ZAGREB" if fold(r[0]) == "GRAD ZAGREB" else county_key(r[0])
            u = units.get((county, typ, unit_key(r[4])))
            if u:
                u["population"] = int(r[5])
                hit += 1
            else:
                print("  census: no unit for", r[0], r[1], r[4])
    print(f"census 2021: population for {hit} units")

    # websites: Adresar tijela javne vlasti (XML; no county, so only names that are unique per type)
    root = ET.parse(resource("adresar-tijela-javne-vlasti", r"\.xml", ext=".xml")).getroot()
    by_name = {}
    for rec in root.iter("RECORD"):
        inst, web = rec.findtext("Institucija"), rec.findtext("WebSjediste")
        m = re.match(r"(Grad|Općina)\s+(.+)", inst or "")
        if m and web and (rec.findtext("PodrucjeDjelovanja") or "").startswith("Lokalna"):
            by_name.setdefault(("grad" if m.group(1) == "Grad" else "općina", unit_key(m.group(2))), []).append(
                web.strip())
    hit = 0
    for (county, typ, key), u in units.items():
        webs = by_name.get((typ, key), [])
        if len(webs) == 1:
            u["website"] = webs[0]
            hit += 1
    print(f"adresar: website for {hit} units")
    return units


def our_units(units):
    out = {}
    for city, (name, typ) in OURS.items():
        hits = [u for (c, t, k), u in units.items() if t == typ and k == unit_key(name)]
        if len(hits) != 1:
            raise RuntimeError(f"{city}: {len(hits)} units named {name}")
        out[city] = hits[0]
    return out


# ---------------------------------------------------------------- 2. local elections 2025

def council_size(city, population):
    if city == "zagreb":
        return 47  # Zakon o Gradu Zagrebu: Gradska skupština
    for limit, seats in ((1000, 7), (2500, 9), (10000, 13), (20000, 15), (35000, 19), (60000, 21),
                         (100000, 27), (200000, 31), (300000, 41)):
        if population <= limit:
            return seats
    return 47


def dhondt(votes, seats, valid, threshold=0.05):
    """{list: votes} -> {list: seats}; lists under threshold * valid votes get none."""
    ok = {k: v for k, v in votes.items() if v >= threshold * valid}
    quot = sorted(((v / d, v, k) for k, v in ok.items() for d in range(1, seats + 1)), reverse=True)[:seats]
    out = {k: 0 for k in votes}
    for _, _, k in quot:
        out[k] += 1
    return out


def sum_sheet(rows):
    """DIP sheet (one row per polling station) -> (header totals, {column title: votes})."""
    rows = [r for r in rows if r]
    head = rows[1]
    first = 13  # columns 0-12: county, unit, polling station, voters, turnout, valid, invalid
    tot = {"registered": 0, "voted": 0, "valid": 0, "invalid": 0}
    votes = {h: 0 for h in head[first:]}
    for r in rows[2:]:
        if not (r[4] or "").isdigit():
            continue
        tot["registered"] += int(r[8] or 0)
        tot["voted"] += int(r[9] or 0)
        tot["valid"] += int(r[11] or 0)
        tot["invalid"] += int(r[12] or 0)
        for i, h in enumerate(head[first:], first):
            votes[h] += int(r[i] or 0) if i < len(r) else 0
    return tot, votes


def list_name(h):
    return " + ".join(x.strip() for x in h.split("\n") if x.strip())


def elections(ours):
    path = resource("rezultati-lokalnih-izbora", r"lokalni/2025", ext=".zip", url=DIP_2025,
                    note="2025 not listed on data.gov.hr (dataset has 2013, 2017, 2021); same DIP archive "
                         "URL pattern as the listed resources")
    z = zipfile.ZipFile(path)
    names = z.namelist()
    council, mayor, turnout = [], [], []
    for city, u in ours.items():
        county = None
        files = {}
        for rnd in (1, 2):
            if city == "zagreb":
                f = f"krug-{rnd}/ZUP_21/557_21.xlsx"
            else:  # krug-N/ZUP_cc/557_cc_<NAME>.xlsx; same name in two counties -> the county in the rows decides
                pat = re.compile(rf"krug-{rnd}/ZUP_(\d\d)/557_\1_{unit_key(u['short']).replace(' ', '_')}\.xlsx$")
                cand = [n for n in names if pat.match(n)]
                if len(cand) > 1:
                    cand = [n for n in cand if county_key(list(Xlsx(io.BytesIO(z.read(n))).rows(
                        next(iter(Xlsx(io.BytesIO(z.read(n))).sheets))))[2][1]) == county_key(u["county"])]
                f = cand[0] if len(cand) == 1 else None
            if f in names:
                files[rnd] = f
        if 1 not in files:
            print(f"  {city}: no DIP file")
            continue
        src = f"{DIP_2025}#{files[1]}"
        book = Xlsx(io.BytesIO(z.read(files[1])))
        sheet_c = next(s for s in book.sheets if "vijeće" in s or "skupština" in s)
        tot, votes = sum_sheet(list(book.rows(sheet_c)))
        seats_total = council_size(city, u["population"])
        seats = dhondt(votes, seats_total, tot["valid"])
        turnout.append({"city": city, "body": sheet_c, "seats_total": seats_total, **tot, "source": src})
        for h, v in sorted(votes.items(), key=lambda kv: -kv[1]):
            council.append({"city": city, "list": list_name(h), "votes": v,
                            "pct": round(100 * v / tot["valid"], 2) if tot["valid"] else None,
                            "seats": seats[h], "source": src})
        # mayor: round 1 elects with > 50 % of those who voted, else the round-2 winner
        for rnd, f in files.items():
            b = book if rnd == 1 else Xlsx(io.BytesIO(z.read(f)))
            sh = next(s for s in b.sheets if "načelnik" in s)
            mt, mv = sum_sheet(list(b.rows(sh)))
            top = max(mv, key=mv.get)
            for h, v in sorted(mv.items(), key=lambda kv: -kv[1]):
                elected = h == top and (rnd == 2 or (2 not in files and v > mt["voted"] / 2))
                mayor.append({"city": city, "round": rnd, "candidate": list_name(h), "votes": v,
                              "pct": round(100 * v / mt["valid"], 2) if mt["valid"] else None,
                              "elected": int(elected), "voted": mt["voted"], "valid": mt["valid"],
                              "source": f"{DIP_2025}#{f}"})
    return council, mayor, turnout


# ---------------------------------------------------------------- 3. cities' own datasets on data.gov.hr

def city_datasets(ours, fresh=False):
    orgs = set(api("organization_list", fresh, limit=2000))
    rows, summary = [], []
    for city, (name, typ) in OURS.items():
        slug = ("grad-" if typ == "grad" else "opcina-") + re.sub(r"[^a-z0-9]+", "-", fold(name).lower()).strip("-")
        if slug not in orgs:
            summary.append({"city": city, "organization": None, "datasets": 0, "relevant": 0})
            continue
        res = api("package_search", fresh, fq=f"organization:{slug}", rows=1000)
        rel = 0
        for p in res["results"]:
            text = " ".join([p["title"], p.get("notes") or "", " ".join(t["name"] for t in p.get("tags", []))])
            if not TOPIC.search(text):
                continue
            rel += 1
            rows.append({"city": city, "organization": slug, "name": p["name"], "title": p["title"].strip(),
                         "url": PORTAL + p["name"],
                         "formats": ",".join(sorted({(r.get("format") or "?").upper() for r in p["resources"]})),
                         "resources": len(p["resources"]), "modified": p["metadata_modified"][:10],
                         "license": p.get("license_title") or p.get("license_id")})
        summary.append({"city": city, "organization": slug, "datasets": res["count"], "relevant": rel})
    return rows, summary


# ---------------------------------------------------------------- 4. extras: tax rates, Zagreb assembly, voters

def tax_rates(ours):
    x = Xlsx(resource("https-porezna-uprava-gov-hr-hr-odluke-jls-4009", r"usporedba-2025-i-2026", ext=".xlsx"))
    want = {unit_key(u["short"]): c for c, u in ours.items()}
    out = []
    for r in x.rows(next(iter(x.sheets))):
        if len(r) >= 6 and r[1] and unit_key(r[1]) in want and re.match(r"[\d.]+$", r[2] or ""):
            city = want[unit_key(r[1])]
            if city == "zagreb" and unit_key(r[1]) != "ZAGREB":
                continue
            out.append({"city": city, "unit": r[1], "lower_2026": float(r[2]), "higher_2026": float(r[3]),
                        "lower_2025": float(r[4]), "higher_2025": float(r[5])})
    return out


def zagreb_assembly():
    p = resource("gradska-skupstina-grada-zagreba", r"raspodjeli-mandata.*\.csv", ext=".csv")
    rows = list(csv.reader(io.StringIO(p.read_bytes().decode("utf-8-sig")), delimiter=";"))
    return [{"party": r[0], "seats": int(r[3])} for r in rows[1:]
            if len(r) > 3 and r[3].isdigit() and not r[0].startswith("Ukupno")]


def voters(ours):
    p = resource("registar-biraca-broj-biraca", r"\.csv", ext=".csv")
    want = {unit_key(u["short"] if c != "zagreb" else "GRAD ZAGREB"): c for c, u in ours.items()}
    tot = {}
    with open(p, encoding="cp1250", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            c = want.get(unit_key(r["GROP_NAZIV"]))
            if c:
                key = (c, county_key(r["ZUPANIJA_NAZIV"]))
                tot[key] = tot.get(key, 0) + int(r["BROJ_BIRACA"] or 0)
    out = []
    for c, u in ours.items():
        n = tot.get((c, "GRAD ZAGREB" if c == "zagreb" else county_key(u["county"])))
        out.append({"city": c, "voters": n, "as_of": "2026-05-13"})
    return out


# ---------------------------------------------------------------- main

def main():
    fresh, with_voters = "--fresh" in sys.argv, "--voters" in sys.argv
    FRESH[0] = fresh
    OUT.mkdir(parents=True, exist_ok=True)
    units = load_units()
    ours = our_units(units)
    council, mayor, turnout = elections(ours)
    datasets, summary = city_datasets(ours, fresh)
    out = {
        "units": [{k: u[k] for k in ("code", "oib", "name", "type", "county", "website", "population", "email")}
                  for u in sorted(units.values(), key=lambda u: (u["county"], u["name"]))],
        "city_units": [{"city": c, "code": u["code"], "oib": u["oib"]} for c, u in ours.items()],
        "council_composition": council, "mayor_results": mayor, "election_turnout": turnout,
        "datagovhr_datasets": datasets, "datagovhr_publishers": summary,
        "tax_rates": tax_rates(ours), "zagreb_assembly_parties": zagreb_assembly(),
    }
    if with_voters or (OUT / "voters.json").exists():  # opted in once: re-read from the cache
        out["voters"] = voters(ours)
    out["sources"] = SOURCES
    for name, rows in out.items():
        (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{name}: {len(rows)}")
    for c in OURS:
        t = next((t for t in turnout if t["city"] == c), None)
        lists = [f"{r['list'][:40]} {r['seats']}" for r in council if r["city"] == c and r["seats"]]
        print(f"{c}: {t and t['seats_total']} seats | " + "; ".join(lists))


if __name__ == "__main__":
    main()
