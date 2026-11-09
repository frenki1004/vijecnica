"""Dubrovnik city council (Gradsko vijeće Grada Dubrovnika), 2025-2029 term, from www.dubrovnik.hr.

What the city publishes: the council page (/gradska-uprava/gradsko-vijece, paged with ?page=N) lists the posts tagged
"Sjednica Gradskog vijeća". Each session has a convocation post ("N. sjednica Gradskog vijeća Grada Dubrovnika
(PRIJENOS UŽIVO)") with the date, the proposed agenda ("D n e v n i r e d", numbered items), a link to the materials on
cloud.dubrovnik.hr (a Nextcloud share; its robots.txt disallows everything, so it is linked, never fetched), the call
PDF ("Dokumenti uz članak") and one YouTube embed (the live stream, which stays as the recording). Supplements to the
agenda come as separate posts ("Dopuna dnevnog reda N. sjednice …", items as "- Prijedlog …").

No minutes (zapisnik) and no vote results are published on the site (the agenda never has a "usvajanje zapisnika"
item; www.dubrovnik.hr/robots.txt disallows /zapisnik/). So items carry no "vote" key and status None; the collector
gives the agenda, the materials link and the recordings only. Votes would have to come from the recordings.

Numbering: the constitutive session is session 1 (the city calls the next one "2. sjednica"). Supplement items are
numbered after the last regular item, in the order of the supplement post (the order the council adds them in is not
published); their "supplement" key is true.

Output: data/dubrovnik/docs/session_NN.json (format of collect/cakovec.py) and data/dubrovnik/recordings.json.
Cache: data/dubrovnik/raw/web.

Usage: python collect/dubrovnik.py [--fresh]
"""
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "dubrovnik"
HOST = "https://www.dubrovnik.hr"
INDEX = "/gradska-uprava/gradsko-vijece"
UA = "vijecnica-research/0.1 (open data hackathon)"
TERM_START = "2025-06-01"
MONTHS = {m: i for i, m in enumerate(("siječnja veljače ožujka travnja svibnja lipnja srpnja kolovoza rujna "
                                      "listopada studenoga prosinca").split(), 1)}
MONTHS["studenog"] = 11
POST = re.compile(r"""href=["'](/vijesti/((\d+)-sjednica-gradskog-vijeca-grada-dubrovnika|"""
                  r"""konstituirajuca-sjednica-gradskog-vijeca-grada-dubrovnika|"""
                  r"""dopuna[^"']*?(\d+)-sjednice[^"']*|(\d+)-sjednica-gradskog-vijeca-grada-dubrovnika---dopuna[^"']*)"""
                  r"""[^"']*)["']""")
YES, NO = "Prijedlog usvojen", "Prijedlog nije usvojen"
MANUAL = D / "manual"
MINUTES_SOURCE = "ručno preuzeto iz paketa materijala {p}. sjednice (cloud.dubrovnik.hr, javna poveznica Grada)"
AD = re.compile(r"^\f?[ \t]*Ad[ \t]+(\d+)\s*\.?[ \t]*$", re.M)  # section heading per agenda item: "Ad 12."
Q = "„“”\"'"
VOTE = re.compile(r"nakon\s+glasovanja\s*,?\s+utvrdi\w*\s+je\s*,?\s+da\s+(?:je\s+)?"
                  r"(?P<how>jednoglasno|većinom\s+glasova\s*\((?P<counts>[^)]{0,160})\))\s*"
                  r"(?P<what>[^.]{0,80}?)\b(?P<neg>nije\s+)?(?P<verb>donesen\w*|prihvaćen\w*|usvojen\w*|izabran\w*|"
                  r"imenovan\w*|utvrđen\w*|dan[aoe]?\b|odbijen\w*|potvrđen\w*|verificiran\w*)", re.S)
_robots, _last = None, [0.0]


def get(url, fresh=False):
    """Cached, polite GET (robots.txt, >= 1 s between requests). A 403/429 is raised, never retried."""
    global _robots
    f = D / "raw" / "web" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")
    if f.exists() and not fresh:
        return f.read_text()
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser(HOST + "/robots.txt")
        _robots.read()
    if not _robots.can_fetch(UA, url):
        raise PermissionError(f"robots.txt disallows {url}")
    time.sleep(max(0, 1.0 - (time.time() - _last[0])))
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    finally:
        _last[0] = time.time()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return data.decode("utf-8", "replace")


def flat(s):
    s = re.sub(r"<(?:br|/p|/li|/div)[^>]*>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xad", "").replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n"))


def posts(fresh):
    """({session: post url}, {session: [supplement post urls]}) from the council page, newest first."""
    main, extra = {}, {}
    for page in range(0, 12):
        text = get(HOST + INDEX + (f"?page={page}" if page else ""), fresh=fresh)
        for u, _, n1, n2, n3 in POST.findall(text):
            u = HOST + u
            if "dopuna" in u:
                n = int(re.search(r"(\d+)-sjednic", u).group(1))
                if u not in extra.setdefault(n, []):
                    extra[n].append(u)
            elif "konstituirajuca" in u:
                main.setdefault(1, u)
            else:
                main.setdefault(int(n1), u)
        if 1 in main:
            break
    return main, extra


def body(page):
    i = page.find('header-post-image')
    j = page.find('<script type="application/ld+json"', i)
    return page[i:j if j > 0 else len(page)]


def session_date(text):
    m = re.search(r"održat\s+će\s+se\s+(?:u\s+|za\s+)?\w+,?\s+(\d{1,2})\s*\.\s*(\w+)\s+(\d{4})", text)
    if not m:
        m = re.search(r"za\s+\w+,\s+(\d{1,2})\s*\.\s*(\w+)\s+(\d{4})", text)
    return f"{m.group(3)}-{MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS \
        else None


def agenda(text):
    """Numbered agenda items after "D n e v n i r e d" (numbers must run 1, 2, 3 … to count as items)."""
    m = re.search(r"D\s?n\s?e\s?v\s?n\s?i\s+r\s?e\s?d", text)
    if not m:
        return []
    t = text[m.end():]
    end = re.search(r"\n\s*(?:Materijali\s+za|Pročelni|Predsjednik\s+Gradskog|PREDSJEDNIK|S\s+poštovanjem|"
                    r"Dokumenti\s+uz\s+članak|Napomena)", t)
    t = t[:end.start()] if end else t
    t = re.sub(r"\s+", " ", t)
    items, pos, want = [], [], 1
    for k in re.finditer(r"(?:^|\s)(\d{1,2})\s*\.\s+(?=[A-ZČĆŠŽĐ„\"])", t):
        if int(k.group(1)) == want:
            pos.append((k.start(), k.end(), want))
            want += 1
    for i, (s, e, n) in enumerate(pos):
        title = t[e:pos[i + 1][0] if i + 1 < len(pos) else len(t)].strip()
        title = re.sub(r"\s*―\s*", "; ", title).strip(" ;")
        if i + 1 == len(pos):  # notes after the last item ("Vijećnička pitanja. U privitku Vam …")
            title = re.split(r"(?<=\.)\s+(?=U\s+privitku|Prijedlo\w*\s+(?:akta|za)\b|O\s+\d+\.\s+točki|Materijal|"
                             r"Molim|Pozivam|Također)", title)[0]
        items.append({"no": n, "sub_label": None, "title": title, "full_title": title})
    return items


def supplement(text):
    """Items of a supplement post: the "- Prijedlog …" lines."""
    out = []
    flat1 = re.sub(r"\s+", " ", text)
    m = re.search(r"točk\w*:?\s*1\.\s+(.+?)(?:\s(?:Također|S\s+poštovanjem|Prijedlozi\s+akata|Materijal)|$)", flat1)
    if m:  # numbered: "točkama: 1. Prijedlog … 2. Prijedlog …"
        return [x.strip(" ,;") for x in re.split(r"\s\d{1,2}\.\s+(?=[A-ZČĆŠŽĐ])", " " + m.group(1)) if x.strip(" ,;")]
    for ln in text.split("\n"):
        m = re.match(r"\s*[-–]\s*(Prijedlog\b.+)", ln)
        if m:
            out.append(re.sub(r"\s+", " ", m.group(1)).strip())
    if not out:  # all on one line
        m = re.search(r"točk\w*:\s*(.+?)(?:Također|S\s+poštovanjem|Prijedlozi\s+akata|$)", re.sub(r"\s+", " ", text))
        if m:
            out = [x.strip(" .") for x in re.split(r"\s[-–]\s", " " + m.group(1)) if x.strip(" .-–")]
    return out


def links(page):
    b = body(page)
    yt = list(dict.fromkeys(re.findall(r"youtube(?:-nocookie)?\.com/embed/([\w-]{11})", b)))
    cloud = list(dict.fromkeys(re.findall(r"https?://cloud\.dubrovnik\.hr/(?:index\.php/)?s/\w+", b)))
    i = b.find("Dokumenti uz članak")
    docs = []
    if i >= 0:
        for u, t in re.findall(r"""<a[^>]+href=["']([^"']+)["'][^>]*>.*?<div class="title">([^<]*)</div>""", b[i:], re.S):
            docs.append({"name": html.unescape(t).strip(), "url": u})
    return yt, cloud, docs


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


def manual_packages():
    """{package session P: [pdf paths]} from data/dubrovnik/manual/<P>/** (unpacked by hand; zips are ignored)."""
    out = {}
    if MANUAL.exists():
        for d in sorted(MANUAL.iterdir()):
            if d.is_dir() and d.name.isdigit():
                out[int(d.name)] = sorted(d.rglob("*.pdf"))
    return out


def manual_minutes(packages):
    """{session N: (text, package P)} for each "ZAPISNIK sa N. sjednic*.pdf" in a package."""
    out = {}
    for pkg, files in packages.items():
        for f in files:
            m = re.match(r"zapisnik\s+sa?\s+(\d+)\s*\.\s*sjednic", f.name, re.I)
            if m:
                out[int(m.group(1))] = (pdf_text(f), pkg)
    return out


def stems(t):
    return {w[:6] for w in re.findall(r"\w{4,}", t.lower())} - {"prijed", "odluke", "odluka", "grada", "dubrov",
                                                                "zaklju", "godinu"}


def overlap(a, b):
    a, b = stems(a), stems(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def materials(files, items):
    """Per-item PDFs of a package ("7.Prijedlog zaključka ….pdf") onto items: the same number when the titles agree,
    else the item with the most similar title. Returns the package's other PDFs (call), minutes excluded."""
    common = []
    for f in files:
        rel = f.relative_to(D).as_posix()
        att = {"name": f.name, "url": rel}
        if re.match(r"zapisnik", f.name, re.I):
            continue
        m = re.match(r"(\d+)\s*\.\s*(.*)\.pdf$", f.name, re.I)
        if not m:
            common.append(att)
            continue
        no, title = int(m.group(1)), m.group(2)
        it = next((x for x in items if x["no"] == no and overlap(x["title"], title) >= 0.5), None)
        if it is None:
            best = max(items, key=lambda x: overlap(x["title"], title), default=None)
            it = best if best and overlap(best["title"], title) >= 0.6 else None
        if it is None:
            print(f"   material not matched: {rel}", flush=True)
            common.append(att)
        else:
            it.setdefault("attachments", []).insert(0, att)
    return common


def minutes_agenda(t):
    """The adopted agenda: the numbered list after "Dnevni red" (after the agenda vote), before "Ad 1."."""
    a1 = AD.search(t)
    heads = [m for m in re.finditer(r"^\s*Dnevni\s+red\s*$", t[:a1.start() if a1 else len(t)], re.M)]
    if not heads or not a1:
        return []
    block = t[heads[-1].end():a1.start()]
    items, want = [], 1
    for ln in block.split("\n"):
        s_ = ln.strip()
        if not s_ or re.fullmatch(r"\d{1,3}|-\s*\d+\s*-", s_):
            continue
        m = re.match(r"(\d{1,2})\s*\.\s+(\S.*)", s_)
        if m and int(m.group(1)) == want:
            items.append({"no": want, "sub_label": None, "title": m.group(2)})
            want += 1
        elif items:
            items[-1]["title"] += " " + s_
    for it in items:
        it["title"] = it["full_title"] = re.sub(r"\s+", " ", it["title"].rstrip("= ")).strip()
    return items


def num_of(word, counts):
    m = re.search(rf"(\d+)\s*[{Q}]*\s*{word}", counts, re.I)
    return int(m.group(1)) if m else None


def minutes_votes(t):
    """({item no: [vote]}, formulas found, skipped) from the "Ad N." sections; amendment votes are skipped."""
    heads, last = [], 0
    for m in AD.finditer(t):
        n = int(m.group(1))
        if n <= last:
            continue
        heads.append((m.start(), n))
        last = n
    out, skipped = {}, 0
    found = len(VOTE.findall(t))
    for i, (pos, n) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        for v in VOTE.finditer(t, pos, end):
            k = t.rfind("stavio je", pos, v.start())
            k = t.rfind("Predsjedni", pos, k) if k > 0 else -1
            start = k if k >= 0 and v.start() - k < 1500 else max(pos, v.start() - 300)
            subject = t[start:v.start()] + v.group("what")
            if re.search(r"amandman", subject, re.I):
                skipped += 1
                continue
            if v.group("how") == "jednoglasno":
                za, protiv, suzd = None, 0, 0
            else:
                c = v.group("counts")
                za, protiv, suzd = num_of("za", c), num_of("protiv", c), num_of("suzdrž", c)
            neg = bool(v.group("neg")) or v.group("verb").startswith("odbij")
            result = NO if neg or (za is not None and protiv is not None and za <= protiv) else YES
            quote = re.sub(r"\s+", " ", t[start:v.end()]).strip()
            act = re.match(r"\s*([A-ZČĆŠŽĐ][A-ZČĆŠŽĐ \n]{2,40})\b", t[v.end():v.end() + 60])  # "ODLUKA", "ZAK LJ U ČAK"
            if act:
                quote += " " + re.sub(r"\s+", " ", act.group(1)).strip()
            vote = {"za": za, "protiv": protiv, "suzdrzano": suzd, "result": result, "members": {},
                    "unanimous": v.group("how") == "jednoglasno" and result == YES, "quote": quote[-400:]}
            out.setdefault(n, []).append(vote)
    return out, found, skipped


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    main_posts, extra = posts(fresh)
    packages = manual_packages()
    minutes = manual_minutes(packages)
    recordings = []
    for n, url in sorted(main_posts.items()):
        page = get(url, fresh=fresh)
        text = flat(body(page))
        date = session_date(text)
        if date and date < TERM_START:
            continue
        yt, cloud, docs = links(page)
        common = [{"name": "Materijali za sjednicu (cloud.dubrovnik.hr)", "url": u} for u in cloud] + \
            [d for d in docs if not re.match(r"\d+\s*\.", d["name"])]
        items = agenda(text)
        for it in items:  # "7. Prijedlog zaključka ….pdf": the material of item 7
            own = [d for d in docs if re.match(rf"{it['no']}\s*\.(?!\d)", d["name"])]
            it["attachments"] = own + common
        supp_urls = []
        for su in extra.get(n, []):
            sp = get(su, fresh=fresh)
            s_yt, s_cloud, s_docs = links(sp)
            s_att = [{"name": "Dopuna materijala (cloud.dubrovnik.hr)", "url": u} for u in s_cloud] + s_docs
            supp_urls.append(su)
            for title in supplement(flat(body(sp))):
                if any(re.sub(r"\W", "", x["title"].lower()) == re.sub(r"\W", "", title.lower()) for x in items):
                    continue
                items.append({"no": len(items) + 1, "sub_label": None, "title": title, "full_title": title,
                              "attachments": s_att, "supplement": True})
            for v in s_yt:
                if v not in yt:
                    yt.append(v)
        text_m, pkg = minutes.get(n, (None, None))
        found = skipped = 0
        if text_m:  # the adopted agenda in the minutes replaces the proposed one (items are renumbered)
            m_items = minutes_agenda(text_m)
            if m_items:
                for it in m_items:
                    it["attachments"] = list(common)
                items = m_items
            votes, found, skipped = minutes_votes(text_m)
            for it in items:
                vs = votes.get(it["no"])
                if vs:
                    it["votes"], it["vote"] = vs, vs[-1]
            unknown = [k for k in votes if not any(x["no"] == k for x in items)]
            for k in unknown:
                print(f"   votes for Ad {k} without an agenda item", flush=True)
        package_common = materials(packages.get(n, []), items)
        for it in items:
            it["attachments"] = it.get("attachments", []) + package_common
            it["proposer"] = ""
            v = it.get("vote")
            it["status"] = ("prihvaćen" if v["result"] == YES else "nije prihvaćen") if v else None
            it["url"] = url
        title = "Konstituirajuća sjednica Gradskog vijeća Grada Dubrovnika" if n == 1 else \
            f"{n}. sjednica Gradskog vijeća Grada Dubrovnika"
        doc = {"session": n, "title": title, "date": date, "url": url, "supplement_urls": supp_urls,
               "minutes_url": None, "minutes_text": text_m,
               "minutes_source": MINUTES_SOURCE.format(p=pkg) if text_m else None,
               "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        for p, vid in enumerate(yt, 1):
            recordings.append({"id": f"dubrovnik-{n:02d}-{p}", "session": n, "part": p, "date": date,
                               "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube",
                               "title": f"{title} ({date})" + (f", dio {p}" if len(yt) > 1 else "")})
        nv = sum(1 for i in items if i.get("vote"))
        nm = sum(len(i.get("votes", [])) for i in items)
        print(f"dubrovnik session {n} ({date}): {len(items)} items "
              f"({sum(1 for i in items if i.get('supplement'))} from supplements), {nv} with votes; "
              + (f"minutes (package {pkg}): {found} vote formulas, {skipped} amendment votes skipped, {nm} matched; "
                 if text_m else "no minutes; ")
              + f"{len(yt)} video, materials link {'yes' if cloud else 'no'}, "
              f"{sum(1 for i in items for a in i['attachments'] if a['url'].startswith('manual/'))} local PDFs",
              flush=True)
        if text_m:
            for it in items:
                if not it.get("vote"):
                    print(f"   no vote: {it['no']}. {it['title'][:90]}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    print(f"dubrovnik: {len(recordings)} recordings", flush=True)


def headings(text, items):
    """[(pos, item)]: each "Ad N." section heading of the (hand-downloaded) minutes with its item."""
    out, last = [], 0
    for m in AD.finditer(text or ""):
        n = int(m.group(1))
        it = next((x for x in items if x["no"] == n), None)
        if it is not None and n > last:
            out.append((m.start(), it))
            last = n
    return out


if __name__ == "__main__":
    main("--fresh" in sys.argv)
