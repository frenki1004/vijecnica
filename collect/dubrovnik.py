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


def main(fresh=False):
    (D / "docs").mkdir(parents=True, exist_ok=True)
    main_posts, extra = posts(fresh)
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
        for it in items:
            it["proposer"] = ""
            it["status"] = None
            it["url"] = url
        title = "Konstituirajuća sjednica Gradskog vijeća Grada Dubrovnika" if n == 1 else \
            f"{n}. sjednica Gradskog vijeća Grada Dubrovnika"
        doc = {"session": n, "title": title, "date": date, "url": url, "supplement_urls": supp_urls,
               "minutes_url": None, "minutes_text": None, "items": items, "attendance": [], "questions": []}
        (D / "docs" / f"session_{n:02d}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        for p, vid in enumerate(yt, 1):
            recordings.append({"id": f"dubrovnik-{n:02d}-{p}", "session": n, "part": p, "date": date,
                               "url": f"https://www.youtube.com/watch?v={vid}", "kind": "youtube",
                               "title": f"{title} ({date})" + (f", dio {p}" if len(yt) > 1 else "")})
        print(f"dubrovnik session {n} ({date}): {len(items)} items "
              f"({sum(1 for i in items if i.get('supplement'))} from supplements), 0 with votes (no minutes), "
              f"{len(yt)} video, materials {'yes' if cloud else 'no'}", flush=True)
    (D / "recordings.json").write_text(json.dumps(recordings, ensure_ascii=False, indent=1))
    print(f"dubrovnik: {len(recordings)} recordings", flush=True)


def headings(text, items):
    """[(pos, item)]: no minutes are published, so there are no sections to cut ([] for any text)."""
    return []


if __name__ == "__main__":
    main("--fresh" in sys.argv)
