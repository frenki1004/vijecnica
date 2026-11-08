"""Discovery crawler: where does each of Croatia's 556 cities / municipalities publish council sessions, and does
it publish recordings of them?

Input: table `units` in data/vijecnica.db (read-only; data.gov.hr "Adresar tijela javne vlasti", websites may be
stale). Output: data/discover/registry.json, registry.csv, summary.json (+ progress.jsonl for --resume).

Per unit (polite, links only, nothing downloaded beyond HTML / robots / sitemap):
  1. robots.txt (respected, per host), home page, sitemap (from robots "Sitemap:" or /sitemap.xml).
     Redirects are followed by hand so robots.txt of every host on the way is checked.
     A dead site gets the obvious alternatives (www.<name>.hr, <name>.hr, grad-/opcina-<name>.hr), DNS first.
  2. Candidate council pages from home links + sitemap URLs, scored by keywords (gradsko/općinsko vijeće,
     sjednice, zapisnici, tonski zapis, snimke, prijenos ...); the best 3 are fetched, then 1-2 sub-pages.
  3. eSjednice (NetCom) portal: linked, or probed at <grad|opcina><name>.esjednice.hr / sjednice.<domain>;
     if present, the council's meeting list and one recent meeting are read (as the portal's own XHR does)
     to see whether it carries MP3s / minutes.
  4. Detection on every fetched page: audio files, YouTube (embeds/videos vs. a bare channel link),
     sjednicevijeca.com, Facebook video/live, Vimeo, eSjednice, minutes documents, gazette, consultations.
Politeness: same UA as collect/brod.py, >= 1 s between requests to a server (per IP address: shared hosting and all
*.esjednice.hr count as one),
20 s timeout, at most MAIN_REQ (+ PORTAL_REQ for an eSjednice probe) requests per unit, 403 / 429 / bot check stops the unit (recorded, never worked
around).

Usage:
  python collect/discover.py --calib            # the 19 units we already know, prints a comparison
  python collect/discover.py                    # all 556 units (≈ 10-15 min with 16 threads)
  python collect/discover.py --resume           # continue an interrupted full run
  python collect/discover.py --units krk,ogulin # by name substring or code
  python collect/discover.py --report           # rebuild csv/summary from progress.jsonl, no crawling
"""
import argparse
import concurrent.futures as cf
import csv
import html
import http.client
import http.cookiejar
import json
import random
import re
import socket
import sqlite3
import ssl
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "vijecnica.db"
OUT = ROOT / "data" / "discover"
UA = "vijecnica-research/0.1 (open data hackathon)"
TIMEOUT = 20
MAIN_REQ = 8          # cap per unit on the unit's own site(s): robots, home, sitemap, council pages
PORTAL_REQ = 5        # extra cap for the eSjednice probe / portal (robots, root, meeting list, two meetings)
MAX_BYTES = 3_000_000

CALIB = {  # key -> (unit code, what we know)
    "brod": ("2178-1", {"audio"}), "krk": ("2170-9", {"audio"}), "ogulin": ("2133-2", {"audio", "esjednice"}),
    "ploce": ("2117-12", {"audio", "esjednice"}),
    "zagreb": ("251", {"youtube"}), "rijeka": ("2170-1", {"youtube"}), "osijek": ("2158-1", {"youtube"}),
    "sibenik": ("2182-1", {"youtube"}),
    "opatija": ("2170-12", {"esjednice"}), "kastav": ("2170-7", {"esjednice"}), "senj": ("2125-3", {"esjednice"}),
    "viskovo": ("2170-35", {"esjednice"}), "punat": ("2170-31", {"esjednice"}), "kostrena": ("2170-22", {"esjednice"}),
    "novivinodolski": ("2170-11", {"esjednice"}), "makarska": ("2181-6", {"esjednice"}),
    "omisalj": ("2170-30", {"esjednice"}), "baska": ("2170-15", {"esjednice"}), "cavle": ("2170-17", {"esjednice"}),
}


# ---------------------------------------------------------------- text helpers

def fold(s):
    """lower-case ASCII: 'Općinsko Vijeće' -> 'opcinsko vijece'."""
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def slug(name):
    base = re.sub(r"^(GRAD|OPĆINA)\s+", "", name.strip(), flags=re.I).split(" - ")[0]
    return re.sub(r"[^a-z0-9]+", "-", fold(base)).strip("-")


def host_of(url):
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def reg_domain(host):
    parts = host.split(".")
    n = 3 if len(parts) > 2 and parts[-2] in ("com", "gov", "org", "from", "iz") else 2
    return ".".join(parts[-n:])


_ip = {}


def throttle_key(host):
    """Throttle per server, not per hostname: many municipalities share one hosting IP (and all *.esjednice.hr
    are one server), so >= 1 s between requests is kept per IP address."""
    if host.endswith(".esjednice.hr"):
        return "esjednice.hr"
    if host not in _ip:
        try:
            _ip[host] = socket.gethostbyname(host)
        except (OSError, UnicodeError):
            _ip[host] = host
    return _ip[host]


class Links(HTMLParser):
    """<a href> with their text, plus src of iframe/audio/video/source/embed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.srcs, self._a, self._t = [], [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._close()
            self._a, self._t = a["href"], [a.get("title") or ""]
        elif tag in ("iframe", "audio", "video", "source", "embed") and (a.get("src") or a.get("data-src")):
            self.srcs.append(a.get("src") or a.get("data-src"))
        elif tag == "img" and self._a is not None:
            self._t.append(a.get("alt") or "")

    def handle_data(self, d):
        if self._a is not None:
            self._t.append(d)

    def handle_endtag(self, tag):
        if tag == "a":
            self._close()

    def _close(self):
        if self._a is not None:
            self.links.append((self._a, re.sub(r"\s+", " ", " ".join(self._t)).strip()))
        self._a, self._t = None, []


def parse_links(base, text):
    p = Links()
    try:
        p.feed(text)
        p.close()
    except Exception:  # broken markup: keep what we got
        pass
    out = []
    for href, t in p.links:
        href = html.unescape(href.strip())
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            out.append((urllib.parse.urljoin(base, href).split("#")[0], t))
        except ValueError:
            continue
    for href in re.findall(r'data-(?:href|url|link)="([^"]+)"', text):
        try:
            out.append((urllib.parse.urljoin(base, html.unescape(href)).split("#")[0], ""))
        except ValueError:
            pass
    srcs = []
    for s in p.srcs:
        try:
            srcs.append(urllib.parse.urljoin(base, html.unescape(s.strip())))
        except ValueError:
            pass
    return out, srcs


# ---------------------------------------------------------------- polite fetching

class Blocked(Exception):
    pass


class Budget(Exception):
    pass


_hosts = defaultdict(lambda: [threading.Lock(), 0.0])
_hosts_lock = threading.Lock()
_robots = {}
_robots_lock = defaultdict(threading.Lock)
BLOCKED_HOSTS = set()  # hosts that answered 403 / 429 / a bot check: never contacted again (also across --resume)
CTX = ssl.create_default_context()
CTX_NOVERIFY = ssl._create_unverified_context()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


BOT = re.compile(r"Just a moment\.\.\.|cf-chl|challenge-platform|Checking your browser|sgcaptcha|captcha-delivery|"
                 r"DDoS protection by|Attention Required! \| Cloudflare|_Incapsula_Resource|/cdn-cgi/challenge", re.I)


class Unit:
    def __init__(self, row):
        self.code, self.oib, self.name, self.type, self.county, self.website = row[:6]
        self.requests = 0
        self.log = []
        self.cap = MAIN_REQ
        self.evidence = []
        self.jar = http.cookiejar.CookieJar()
        self.noverify = set()

    def note(self, s):
        if s not in self.evidence:
            self.evidence.append(s)

    # one HTTP request, throttled per host; returns (status, final_url, text, headers) or raises Blocked
    def request(self, url, data=None, headers=None, method=None, count=True):
        if count and self.requests >= self.cap:
            raise Budget()
        host = host_of(url)
        if host in BLOCKED_HOSTS:
            raise Blocked(f"{host} refused us earlier (not contacted again)")
        with _hosts_lock:
            slot = _hosts[throttle_key(host)]
        with slot[0]:
            time.sleep(max(0.0, 1.0 - (time.time() - slot[1])))
            self.requests += 1
            ctx = CTX_NOVERIFY if host in self.noverify else CTX
            op = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx),
                                             urllib.request.HTTPCookieProcessor(self.jar))
            req = urllib.request.Request(url, data=data, method=method,
                                         headers={"User-Agent": UA, "Accept-Language": "hr,en;q=0.5", **(headers or {})})
            try:
                try:
                    r = op.open(req, timeout=TIMEOUT)
                    status, hdrs, body = r.status, r.headers, r.read(MAX_BYTES)
                except urllib.error.HTTPError as e:
                    status, hdrs = e.code, e.headers
                    try:
                        body = e.read(200_000)
                    except Exception:
                        body = b""
                except urllib.error.URLError as e:
                    if isinstance(e.reason, ssl.SSLCertVerificationError) and host not in self.noverify:
                        self.noverify.add(host)
                        self.note(f"TLS certificate of {host} does not verify; read without verification")
                        slot[1] = time.time()
                        return None  # caller retries (counts as another request)
                    raise
            finally:
                slot[1] = time.time()
        text = decode(body, hdrs)
        if status in (403, 429):
            BLOCKED_HOSTS.add(host)
            raise Blocked(f"HTTP {status} at {url}")
        if status in (202, 503, 200) and len(body) < 60_000 and BOT.search(text[:20000]):
            BLOCKED_HOSTS.add(host)
            raise Blocked(f"bot check at {url} (HTTP {status})")
        return status, hdrs, text

    def get(self, url, data=None, headers=None, method=None, follow=True):
        """GET with manual redirects (robots.txt checked on every host). Returns (status, final_url, text)
        or (None, url, error string) on network failure; raises Blocked."""
        url = iri(url)
        for _ in range(6):
            if not self.allowed(url):
                return "robots", url, ""
            try:
                r = self.request(url, data, headers, method)
                if r is None:
                    r = self.request(url, data, headers, method)
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError,
                    http.client.HTTPException, OSError, ValueError) as e:
                self.log.append(f"ERR {url}"[:160])
                return None, url, f"{type(e).__name__}: {getattr(e, 'reason', e)}"[:200]
            status, hdrs, text = r
            self.log.append(f"{status} {url}"[:160])
            if status in (301, 302, 303, 307, 308) and follow and hdrs.get("Location"):
                url = iri(urllib.parse.urljoin(url, hdrs["Location"]))
                if host_of(url).startswith("consent."):
                    return "consent", url, ""  # a cookie wall (YouTube in the EU): not followed
                if status == 303:
                    data, method = None, None
                continue
            return status, url, text
        return None, url, "too many redirects"

    def allowed(self, url):
        host = urllib.parse.urlsplit(url).netloc.lower()
        if host.endswith(".esjednice.hr") or host == "esjednice.hr":
            key = host
        else:
            key = host
        with _robots_lock[key]:
            if key not in _robots:
                rp = urllib.robotparser.RobotFileParser()
                scheme = urllib.parse.urlsplit(url).scheme or "https"
                try:
                    r = self.request(f"{scheme}://{host}/robots.txt")
                    if r is None:
                        r = self.request(f"{scheme}://{host}/robots.txt")
                    status, _, text = r
                    self.log.append(f"{status} {scheme}://{host}/robots.txt")
                    if status == 200 and "<html" not in text[:500].lower():
                        rp.parse(text.splitlines())
                        rp.sitemaps_ = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", text)
                    elif status in (401,) or (status and status >= 500):
                        rp.disallow_all = True
                        self.note(f"robots.txt of {host}: HTTP {status}, treated as disallow-all")
                    else:
                        rp.allow_all = True
                except Blocked:
                    raise
                except Budget:
                    raise
                except Exception:
                    rp.allow_all = True  # unreachable: the page fetch itself will tell
                    rp.unreachable = True
                _robots[key] = rp
            rp = _robots[key]
        return rp.can_fetch(UA, url)


def decode(body, hdrs):
    cs = None
    ct = (hdrs.get("Content-Type") or "") if hdrs else ""
    m = re.search(r"charset=([\w-]+)", ct, re.I)
    if m:
        cs = m.group(1)
    else:
        m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', body[:4000], re.I)
        cs = m.group(1).decode() if m else "utf-8"
    try:
        return body.decode(cs, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def iri(url):
    """'https://x.hr/uprava/gradsko-vijeće/' -> percent-encoded path, IDNA host (urllib only sends ASCII)."""
    try:
        sp = urllib.parse.urlsplit(url)
        host = sp.hostname.encode("idna").decode() if sp.hostname and not sp.hostname.isascii() else sp.netloc
        if sp.hostname and not sp.hostname.isascii():
            host = host + (f":{sp.port}" if sp.port else "")
        else:
            host = sp.netloc
        q = lambda x, safe: urllib.parse.quote(x, safe=safe)
        return urllib.parse.urlunsplit((sp.scheme, host, q(sp.path, "/%:@!$&'()*+,;=~-._"),
                                        q(sp.query, "=&%/:?@!$'()*+,;~-._"), ""))
    except (ValueError, UnicodeError):
        return url


def resolves(host):
    try:
        socket.getaddrinfo(host, 443)
        return True
    except (socket.gaierror, UnicodeError, OSError):
        return False


# ---------------------------------------------------------------- scoring and detection

# (pattern on folded "link text + url", weight)
KEYS = [
    (r"gradsk\w* skupstin|gradsk\w* vijec|opcinsk\w* vijec|gradsko-vijece|opcinsko-vijece|gradskovijece|opcinskovijece", 6),
    (r"\bvijec[ea]\b|/vijece", 3),
    (r"sjednic|sjednice", 5),
    (r"zapisni", 4),
    (r"tonsk\w* zapis|tonski-zapis|audio ?zapis|snimk|snimci|video ?zapis|prijenos|livestream|uzivo", 5),
    (r"esjednice|e-sjednice", 6),
    (r"akti vijec|odluke vijec|materijal", 2),
    (r"predstavnick|gradska uprava|tijela|ustroj", 1),
]
NEG = [
    (r"vijec\w* mladih|savjet mladih|nacionaln\w* manjin|prevencij|mjesn\w* odbor|roditelj|vijec\w* za|"
     r"gradske cetvrti|mjesn|turisti|skolsk|sportsk", -5),
    (r"radna tijela|radnih tijela|odbor|povjerenstv|potpredsjedni|vijecnic|klub", -3),
    (r"novost|vijest|news|/\d{4}/\d{2}/|clanak|obavijest", -2),
    (r"\.(pdf|docx?|xlsx?|jpe?g|png|zip|mp3|mp4)(\?|$)", -20),
    (r"facebook|instagram|twitter|youtube|linkedin|tiktok|x\.com|google\.", -20),
]


def score_link(url, text, home_host):
    u = fold(urllib.parse.unquote(url))
    t = fold(text)
    s = 0
    for pat, w in KEYS:
        if re.search(pat, t):
            s += w
        elif re.search(pat, u.replace("-", " ").replace("_", " ")) or re.search(pat, u):
            s += w * 0.7
    for pat, w in NEG:
        if re.search(pat, t + " " + u):
            s += w
    h = host_of(url)
    if h and reg_domain(h) != reg_domain(home_host) and "esjednice" not in h and not h.startswith("sjednice."):
        s -= 6  # other sites (county, ministries, partners)
    if s > 0 and len(urllib.parse.urlsplit(url).path) > 120:
        s -= 1
    return s


AUDIO_EXT = re.compile(r"\.(?:mp3|m4a|wav|ogg|oga|wma)(?![\w-])", re.I)
URL_TAIL = re.compile(r"""[^\s"'<>()]{1,300}$""")


def audio_urls(text):
    """URLs ending in an audio extension; anchored on the extension (a backwards scan over long minified
    tokens would be quadratic)."""
    for m in AUDIO_EXT.finditer(text):
        head = URL_TAIL.search(text[max(0, m.start() - 300):m.start()])
        if head:
            q = re.match(r"""\?[^\s"'<>]{0,200}""", text[m.end():m.end() + 201])
            yield head.group(0) + m.group(0) + (q.group(0) if q else "")
YT = re.compile(r"(?:https?:)?//(?:www\.|m\.)?(?:youtube(?:-nocookie)?\.com/(?:embed/(?:videoseries\?list=)?[\w-]+|watch\?v=[\w-]+|"
                r"live/[\w-]+|playlist\?list=[\w-]+|channel/[\w-]+|@[\w.%-]+|c/[\w.%-]+|user/[\w.%-]+)|youtu\.be/[\w-]+)", re.I)
YT_VIDEO = re.compile(r"embed/|watch\?v=|live/|playlist\?list=|youtu\.be/", re.I)
SVC = re.compile(r"https?://(?:[\w-]+\.)*sjednicevijeca\.com[^\s\"'<>]*", re.I)
FB = re.compile(r"https?://(?:www\.|m\.|web\.)?(?:facebook\.com/(?:[^\s\"'<>]{0,120}?/videos/[^\s\"'<>]{0,120}|watch[^\s\"'<>]{0,120}|"
                r"plugins/video[^\s\"'<>]{0,300}|[^\s\"'<>/]{1,80}/live[^\s\"'<>]{0,80})|fb\.watch/[^\s\"'<>]{1,40})", re.I)
VIMEO = re.compile(r"https?://(?:player\.)?vimeo\.com/(?:video/)?\d+[^\s\"'<>]*", re.I)
EGRAD = re.compile(r"https?://sjednica\.e-grad\.hr/javno/\d+/?", re.I)
ESJ = re.compile(r"https?://(?:[\w-]+\.esjednice\.hr|sjednice\.[\w.-]+\.hr)[^\s\"'<>]*", re.I)
DOCEXT = re.compile(r"\.(pdf|docx?|odt|rtf)(\?|$)|/download|dldocoriginal|attachment|wpdmdl|/file", re.I)
COUNCIL_WORDS = re.compile(r"sjednic|vijec|prijenos|snimk|tonsk|zapis", re.I)
# an audio file / video counts only next to these words (in its URL or within ~300 characters of page text):
# city sites also carry anthems, songs, radio jingles and promo videos
REC_CONTEXT = re.compile(r"sjednic|svednic|vijec|skupstin|\bov\b|\bgv\b|\bsgv\b|tonsk|zapis|snimk|prijenos|razglas", re.I)
NOT_REC = re.compile(r"mixcloud|soundcloud|himn|pjesm|song|jingle|/videos/|background|spot|reklam|radio", re.I)


class Findings:
    def __init__(self):
        self.audio, self.yt_video, self.yt_channel, self.svc, self.fb, self.vimeo = {}, {}, {}, {}, {}, {}
        self.esj, self.minutes, self.gazette, self.consult = {}, {}, {}, {}
        self.minutes_pages, self.hints, self.egrad, self.yt_titles = {}, {}, {}, {}

    @staticmethod
    def add(d, url, where):
        if url not in d and len(d) < 50:
            d[url] = where


def near(text, pos, width=300):
    return fold(clean(text[max(0, pos - width):pos + width]))


def detect(f, page_url, text, links, srcs, kind):
    """kind: 'home' or 'council'. Fills f with url -> 'kind:page_url'."""
    where = f"{kind}:{page_url}"
    title = re.search(r"<title[^>]*>(.*?)</title>", text[:20000], re.S | re.I)
    # a page about sessions / recordings: everything audio / video on it is taken as council material
    page_ctx = kind == "council" and bool(re.search(r"sjednic|svednic|snimk|prijenos|video ?zapis|videozapis|tonsk|audio",
                                                    fold(urllib.parse.unquote(page_url) + " " + (clean(title.group(1)) if title else "")).replace("-", " ")))
    for raw in audio_urls(text):
        u = html.unescape(raw).lstrip("'\"=")
        if not (u.startswith(("http", "/", "./", "../")) or "/" in u):
            continue
        uf = fold(urllib.parse.unquote(u)).replace("_", " ").replace("-", " ")
        if NOT_REC.search(uf):
            continue
        pos = text.find(raw)
        if page_ctx or REC_CONTEXT.search(uf) or REC_CONTEXT.search(near(text, pos, 300)):
            f.add(f.audio, urllib.parse.urljoin(page_url, u), where)
    link_text = {u: t for u, t in links}
    for m in YT.finditer(text):
        u = m.group(0)
        u = ("https:" + u) if u.startswith("//") else u
        if YT_VIDEO.search(u):
            ctx = near(text, m.start(), 400)
            if page_ctx or REC_CONTEXT.search(ctx):
                f.add(f.yt_video, u, where + (" (near council words)" if kind == "home" else ""))
            else:
                f.add(f.yt_channel, u, where + " (video, no council context)")
        else:
            t = fold(link_text.get(u, ""))
            f.add(f.yt_channel, u, where + (f" text='{t[:40]}'" if t else ""))
    for m in SVC.finditer(text):
        f.add(f.svc, m.group(0), where)
    for m in FB.finditer(text):
        if kind == "council" or COUNCIL_WORDS.search(near(text, m.start())):
            f.add(f.fb, m.group(0), where)
    for m in VIMEO.finditer(text):
        if kind == "council" or COUNCIL_WORDS.search(near(text, m.start())):
            f.add(f.vimeo, m.group(0), where)
    for m in EGRAD.finditer(text):
        f.add(f.egrad, m.group(0), where)
    for m in ESJ.finditer(text):
        h = host_of(m.group(0))
        f.add(f.esj, f"https://{h}/", where)
    for u, t in links:
        ft, fu = fold(t), fold(urllib.parse.unquote(u))
        if ("zapisni" in ft or "zapisni" in fu) and not re.search(
                r"kabinet|kolegij|mjesn\w* odbor|povjerenstv|savjet\w* mladih|vijec\w* mladih|manjin|udrug|"
                r"skolsk|vatrogas|turisti|lag\b|nadzorn", ft + " " + fu.replace("-", " ")) and (
                kind == "council" or re.search(r"sjednic|vijec|skupstin", ft + " " + fu)):
            if DOCEXT.search(u) or re.search(r"\.(pdf|docx?)\b", ft):
                f.add(f.minutes, u, where)
            else:
                f.add(f.minutes_pages, u, where)
        if re.search(r"sluzben\w* (glasnik|novine|vjesnik)|sluzbeni-glasnik|sluzbeni-vjesnik|sluzbene-novine|"
                     r"glasnik (grada|opcine)|\bglasnik\b", ft + " " + fu.replace("-", " ")) \
                and not re.search(r"\.(pdf|docx?)(\?|$)", fu):
            f.add(f.gazette, u, where)
        if re.search(r"savjetovanj|esavjetovanja", ft + " " + fu):
            f.add(f.consult, u, where)


# ---------------------------------------------------------------- eSjednice portal

ESJ_DOC = re.compile(r'href="(https://[^"]+/(?:dldocoriginal|pdfviewer)/\d+\?[^"]+)"[^>]*>\s*<i class="fa ([\w-]+)"[^>]*>'
                     r'</i>\s*(.*?)<span class="text-muted small">\[\s*\.?(\w*)\s*\]</span>', re.S)


def esjednice(unit, base, f):
    """Look at an eSjednice portal: is the council on it, and does a recent meeting carry MP3 / minutes."""
    st, final, page = unit.get(base)
    if st != 200 or "esjednice" not in page.lower():
        return None
    info = {"url": final, "council_type": None, "meetings": 0, "audio": [], "minutes": [], "last_meeting": None}
    csrf = re.search(r'csrf-token" content="([^"]+)', page)
    types = re.findall(r'data-route="\.\./\.\./meetingtype/(\d+)"(?: data-sysmethod="\w+")? data-token="([^"]+)" '
                       r'data-sysc="(\w+)"[^>]*>(.*?)</a>', page, re.S)
    council = [t for t in types if re.search(r"vijec", fold(clean(t[3]))) and not re.search(
        r"mladih|manjin|mjesn|odbor", fold(clean(t[3])))]
    if not council:
        info["types"] = [clean(t[3]) for t in types]
        return info
    mt, tok, sysc, lab = council[0]
    info["council_type"] = clean(lab)
    if not csrf:
        return info
    hdr = {"X-CSRF-TOKEN": csrf.group(1), "X-Requested-With": "XMLHttpRequest"}
    try:
        st, _, body = unit.get(f"{final.rstrip('/')}/meetingtype/{mt}",
                               urllib.parse.urlencode({"token": tok, "sysc": sysc}).encode(), hdr, "POST")
        d = json.loads(body).get("html", "") if st == 200 else ""
    except (ValueError, AttributeError):
        d = ""
    ms = []
    for mid, mtok, mbody in re.findall(r'data-route="\.\./\.\./meeting/(\d+)" data-sysmethod="GET" data-token="([^"]+)" '
                                       r'data-sysc="showmeeting"[^>]*>(.*?)</a>', d, re.S):
        dm = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", clean(mbody))
        date = f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}" if dm else ""
        title = clean(re.search(r'meeting-title">(.*?)</h3>', mbody, re.S).group(1)) if 'meeting-title' in mbody else ""
        ms.append((date, int(mid), mtok, title))
    info["meetings"] = len(ms)
    if not ms:
        return info
    ms.sort(reverse=True)
    today = time.strftime("%Y-%m-%d")
    past = [m for m in ms if m[0] and m[0] < today] or ms
    # the 2nd- and 4th-latest past meetings: minutes / MP3s are often attached to a later session
    picks = [past[i] for i in (1, 3) if i < len(past)] or past[:1]
    info["last_meeting"] = "; ".join(f"{p[3]} ({p[0]})" for p in picks)
    h = ""
    for pick in picks:
        try:
            q = urllib.parse.urlencode({"token": pick[2], "sysc": "showmeeting"})
            st, _, body = unit.get(f"{final.rstrip('/')}/meeting/{pick[1]}?{q}", headers=hdr)
            h += json.loads(body).get("html", "") if st == 200 else ""
        except (ValueError, AttributeError, Budget):
            pass
    for url, icon, name, ext in ESJ_DOC.findall(h):
        name = clean(name)
        if "audio" in icon or ext.lower() in ("mp3", "wav", "m4a", "ogg"):
            info["audio"].append(name)
        elif "zapisni" in fold(name):
            info["minutes"].append(name)
    if re.search(r"youtube\.com|youtu\.be", h):
        info["youtube_in_meeting"] = True
        for m in YT.finditer(h):
            f.add(f.yt_video, m.group(0), f"esjednice {final}")
    return info


# ---------------------------------------------------------------- YouTube titles

YT_ID = re.compile(r"(?:embed/|watch\?v=|live/|youtu\.be/)([\w-]{11})")
YT_SESSION = re.compile(r"sjednic|svednic|vijec|skupstin|\bov\b|\bgv\b|konstituir", re.I)


def verify_youtube(unit, f, n=3):
    """Title of up to n candidate videos via YouTube oEmbed (allowed by youtube.com/robots.txt, no cookie wall):
    a video counts as a council recording only if its title says so."""
    cands = list(f.yt_video) + [u for u, w in f.yt_channel.items() if "no council context" in w and w.startswith("council:")]
    for u in cands[:n]:
        m = YT_ID.search(u)
        if not m or m.group(1) == "live_stream":
            continue
        try:
            st, _, body = unit.get("https://www.youtube.com/oembed?format=json&url="
                                   + urllib.parse.quote(f"https://www.youtube.com/watch?v={m.group(1)}", safe=""))
            f.yt_titles[u] = json.loads(body).get("title", "") if st == 200 else None
        except (ValueError, Budget):
            break
        except Blocked as e:
            unit.note(f"YouTube oEmbed refused: {e}")
            break


# ---------------------------------------------------------------- per unit

def candidates_from_sitemap(unit, home_url, f_notes):
    host = urllib.parse.urlsplit(home_url).netloc
    rp = _robots.get(host.lower())
    maps = list(getattr(rp, "sitemaps_", []) or []) or [f"{urllib.parse.urlsplit(home_url).scheme}://{host}/sitemap.xml"]
    st, url, text = unit.get(maps[0])
    if st != 200 or "<" not in text[:200]:
        return []
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
    unit.note(f"sitemap {url}: {len(locs)} locs")
    if "<sitemapindex" in text[:1000].lower():
        subs = [l for l in locs if re.search(r"page|stranic|categor|menu", l, re.I)] or locs[:1]
        if subs and unit.requests <= 4:
            st, url2, t2 = unit.get(html.unescape(subs[0]))
            if st == 200:
                locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", t2)
                unit.note(f"sitemap {url2}: {len(locs)} locs")
            else:
                locs = []
        else:
            locs = []
    return [(html.unescape(l), "") for l in locs[:5000]]


SESSION = re.compile(r"\b\d{1,2}\s*\.?\s*(?:\(?\w+\)?\s*)?(?:redovn\w* |izvanredn\w* |konstituirajuc\w* |tematsk\w* )?sjednic|"
                     r"konstituirajuc\w* sjednic|/session/|sjednica-\d|\d+-sjednica|\d+-izvanredna", re.I)
REC_HINT = re.compile(r"tonsk\w* zapis|audio ?zapis|audio ?snimk|video ?snimk|snimk\w* sjednic|snimci sjednic|"
                      r"video ?zapis|prijenos\w* sjednic|uzivo|live ?stream|izravn\w* prijenos|prijenos uzivo|"
                      r"tonski-zapis|snimke-sjednic|prijenos-sjednic|video-prijenos", re.I)


def page_score(u, t, home_host):
    sc = score_link(u, t, home_host)
    ft = fold(t + " " + urllib.parse.unquote(u)).replace("-", " ")
    if SESSION.search(ft) and re.search(r"vijec|skupstin|sjednic", ft):
        sc += 3
    if REC_HINT.search(ft):
        sc += 4
    return sc


def crawl_council(unit, f, home_url, home_host, links, max_pages=5):
    """Best-first over council candidates: index pages first, and at least one individual session page
    (recordings / minutes usually sit there), within the unit's request cap."""
    seen = {home_url.rstrip("/")}
    frontier = {}

    def push(lst, bonus=0.0):
        for u, t in lst:
            if urllib.parse.urlsplit(u).scheme not in ("http", "https") or u.rstrip("/") in seen:
                continue
            sc = page_score(u, t, home_host) + bonus
            ft = fold(t + " " + urllib.parse.unquote(u))
            if REC_HINT.search(ft.replace("-", " ")) and sc > 0:
                f.add(f.hints, u, f"link '{t[:60]}'")
            if sc >= 4 and sc > frontier.get(u, (-99,))[0]:
                frontier[u] = (sc, t)
    push(links)
    pages, got_session = [], False
    while frontier and len(pages) < max_pages and unit.requests < unit.cap:
        items = sorted(frontier.items(), key=lambda x: -x[1][0])
        if len(pages) >= max_pages - 1 and not got_session:  # last slot: an individual session page if any
            sess = [x for x in items if SESSION.search(fold(x[1][1] + " " + urllib.parse.unquote(x[0])).replace("-", " "))]
            if sess:
                items = sess
        u, (sc, t) = items[0]
        del frontier[u]
        if u.rstrip("/") in seen:
            continue
        seen.add(u.rstrip("/"))
        h = host_of(u)
        if h.endswith(".esjednice.hr") or (h.startswith("sjednice.") and h != home_host):
            f.add(f.esj, f"https://{h}/", f"linked from site '{t[:40]}'")
            continue
        try:
            st, fu, text = unit.get(u)
        except Budget:
            break
        if st != 200:
            unit.note(f"council candidate {u}: {st}")
            continue
        seen.add(fu.rstrip("/"))
        is_session = bool(SESSION.search(fold(t + " " + urllib.parse.unquote(u)).replace("-", " ")))
        got_session |= is_session
        pl, ps = parse_links(fu, text)
        detect(f, fu, text, pl, ps, "council")
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        if REC_HINT.search(fold(clean(title.group(1)) if title else "")):
            f.add(f.hints, fu, "page title")
        pages.append({"url": fu, "score": round(sc, 1), "text": t[:80], "session_page": is_session})
        push(pl, bonus=1.0)  # links found on council pages are more likely council pages themselves
    return pages


def fetch_home(unit):
    """Try the registry website, then the obvious alternatives if (and only if) it fails."""
    tried = []
    urls = []
    if unit.website:
        w = unit.website.strip()
        w = re.sub(r"^(https?://)?", "", w, flags=re.I)
        urls += [f"https://{w}", f"http://{w}"]  # https first saves the usual http->https redirect
    s = slug(unit.name)
    pre = "grad" if unit.type == "grad" else "opcina"
    s2 = s.replace("-", "")
    alts = list(dict.fromkeys([f"https://www.{s}.hr/", f"https://{s}.hr/", f"https://www.{s2}.hr/", f"https://{s2}.hr/",
                               f"https://www.{pre}-{s}.hr/", f"https://{pre}-{s}.hr/", f"https://www.{pre}{s2}.hr/"]))
    skip_http = False
    for i, u in enumerate(urls + alts):
        if i >= len(urls):
            if u in tried or not resolves(host_of(u)):
                continue
            if unit.requests >= 5:
                break
        elif i == 1 and skip_http:
            continue
        tried.append(u)
        st, final, text = unit.get(u)
        if i == 0 and st is not None and st != 200:
            skip_http = True  # https answered (just not 200): plain http would land in the same place
        if st == "robots":
            return "robots_disallowed", final, "", tried
        if st == 200 and len(text) > 300:
            if i >= len(urls):
                unit.note(f"registry website {'missing' if not urls else 'failed'}; using alternative {final}")
            return "ok", final, text, tried
        unit.note(f"{u}: {st if st is not None else text}")
    return "dead", None, "", tried


def run_unit(row):
    unit = Unit(row)
    f = Findings()
    rec = {"code": unit.code, "name": unit.name, "type": unit.type, "county": unit.county,
           "website_registry": unit.website or None}
    status, final, council_page, pages, esj_info = None, None, None, [], []
    try:
        status, final, home, tried = fetch_home(unit)
        rec["website_checked"] = tried
        if status == "ok":
            home_host = host_of(final)
            links, srcs = parse_links(final, home)
            detect(f, final, home, links, srcs, "home")
            try:
                links += candidates_from_sitemap(unit, final, f)
            except Budget:
                pass
            pages = crawl_council(unit, f, final, home_host, links)
            if pages:
                idx = [p for p in pages if not p["session_page"]] or pages
                council_page = max(idx, key=lambda p: (p["score"], -len(p["url"])))["url"]
        unit.cap = unit.requests + PORTAL_REQ
        # eSjednice: linked portals, then the usual hostnames
        s = slug(unit.name).replace("-", "")
        pre = "grad" if unit.type == "grad" else "opcina"
        probes = list(f.esj)
        if final:
            probes.append(f"https://sjednice.{reg_domain(host_of(final))}/")
        probes.append(f"https://{pre}{s}.esjednice.hr/")
        done = set()
        for p in probes:
            h = host_of(p)
            if h in done or not resolves(h):
                continue
            done.add(h)
            if unit.requests >= unit.cap - 1:
                unit.note(f"request budget used before probing {h}")
                break
            try:
                info = esjednice(unit, p, f)
            except Budget:
                break
            except Blocked as e:  # the portal host refused: the unit's own site results stand
                unit.note(f"eSjednice probe refused: {e}")
                continue
            if info:
                esj_info.append(info)
                f.add(f.esj, info["url"], f.esj.get(p, "probe"))
                break
            elif p in f.esj:
                f.esj.pop(p, None)
        unit.cap = unit.requests + 3
        if f.yt_video or f.yt_channel:
            verify_youtube(unit, f)
        if status == "ok" and not pages:
            status = "no_council_page"
        if status == "dead" and esj_info:
            status = "ok"
    except Blocked as e:
        status = "blocked"
        unit.note(str(e))
    except Budget:
        unit.note("request budget exhausted")
        status = status or "dead"
    return finish(unit, rec, status, final, council_page, pages, f, esj_info)


def finish(unit, rec, status, final, council_page, pages, f, esj_info):
    esj = esj_info[0] if esj_info else None
    if esj and not esj.get("council_type") and esj.get("meetings", 0) == 0:
        unit.note(f"eSjednice portal {esj['url']} has no council meeting type ({esj.get('types')})")
    esj_audio = bool(esj and esj["audio"])
    esj_ok = bool(esj and esj.get("council_type"))
    if status == "no_council_page" and esj_ok:
        status = "ok"
    if not council_page and esj_ok:
        council_page = esj["url"]
    egrad = next(iter(f.egrad), None)
    if egrad:
        if status == "no_council_page":
            status = "ok"
        council_page = council_page or egrad
    yt_strong = dict(f.yt_video)
    for u, title in f.yt_titles.items():  # titles override the page-context guess
        if title and YT_SESSION.search(fold(title)):
            yt_strong[u] = f"title '{title[:70]}'"
        elif title is not None:
            yt_strong.pop(u, None)
            unit.note(f"YouTube {u} is not a session ('{(title or '')[:60]}')")
    checked = [t for t in f.yt_titles.values() if t is not None]
    if checked and not any(YT_SESSION.search(fold(t)) for t in checked):
        yt_strong = {}  # every video we could check is something else (promo, events): drop the rest too
    # a channel link found on a council page but not on the home page (footer links appear everywhere)
    home_channels = {u for u, w in f.yt_channel.items() if w.startswith("home:")}
    for u, w in f.yt_channel.items():
        if w.startswith("council:") and u not in home_channels and "no council context" not in w:
            yt_strong[u] = w + " (channel linked from council page)"
    if f.audio or esj_audio:
        rtype = "audio"
    elif yt_strong:
        rtype = "youtube"
    elif f.svc or f.fb or f.vimeo:
        rtype = "stream_service"
    elif status in ("dead", "blocked", "robots_disallowed"):
        rtype = "unknown"
    elif f.yt_channel or esj_ok or egrad:
        rtype = "unknown"  # a YouTube channel exists / eSjednice without MP3 in the meeting we looked at
    elif council_page:
        rtype = "none"
    else:
        rtype = "unknown"
    minutes = list(f.minutes)
    if esj and esj["minutes"]:
        minutes.append(f"{esj['url']} :: {esj['minutes'][0]}")
    ev = []
    for label, d in (("audio", f.audio), ("youtube video", f.yt_video), ("youtube channel", f.yt_channel),
                     ("sjednicevijeca", f.svc), ("facebook video", f.fb), ("vimeo", f.vimeo),
                     ("minutes doc", f.minutes), ("minutes page", f.minutes_pages), ("recording hint", f.hints)):
        if d:
            u, w = next(iter(d.items()))
            ev.append(f"{label} x{len(d)}: {u} [{w}]")
    if esj:
        ev.append(f"eSjednice {esj['url']}: council type={esj.get('council_type')}, meetings={esj['meetings']}, "
                  f"checked {esj.get('last_meeting')}: audio={len(esj['audio'])}, minutes={len(esj['minutes'])}")
    for p in pages:
        ev.append(f"council candidate {p['url']} (score {p['score']}, '{p['text']}')")
    has_rec = rtype in ("audio", "youtube", "stream_service")
    if status in ("dead", "blocked", "robots_disallowed", "no_council_page") or not rec.get("website_registry"):
        conf = "low"  # (no registry website: the site was guessed from the name, possibly another unit's)
    elif (has_rec or minutes or esj_ok or egrad) and council_page:
        conf = "high" if (f.audio or yt_strong or f.svc or esj_ok or egrad or (minutes and pages)) else "medium"
    else:
        conf = "medium" if council_page else "low"
    rec.update({
        "final_url": final, "status": status, "council_page": council_page,
        "recordings": {
            "audio_links_sample": list(f.audio)[:5] + ([f"{esj['url']} :: {a}" for a in esj["audio"][:3]] if esj else []),
            "youtube": list(yt_strong)[:5], "youtube_channel": [u for u in f.yt_channel if u not in yt_strong][:3],
            "sjednicevijeca": list(f.svc)[:3], "facebook": list(f.fb)[:3], "vimeo": list(f.vimeo)[:3],
            "esjednice": esj["url"] if esj_ok else None,
            "e_grad": egrad,
        },
        "recording_type": rtype,
        "minutes_found": bool(minutes), "minutes_sample": minutes[0] if minutes else None,
        "minutes_page": next(iter(f.minutes_pages), None),
        "recording_hints": list(f.hints)[:3],
        "gazette": next(iter(f.gazette), None), "consultations": next(iter(f.consult), None),
        "confidence": conf, "requests": unit.requests, "fetched": unit.log,
        "evidence": (ev + unit.evidence)[:25],
    })
    return rec


# ---------------------------------------------------------------- output

def write_outputs(recs):
    OUT.mkdir(parents=True, exist_ok=True)
    recs = sorted(recs, key=lambda r: (r["county"] or "", r["name"]))
    (OUT / "registry.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")
    cols = ["code", "name", "type", "county", "website_registry", "final_url", "status", "council_page",
            "recording_type", "audio", "youtube", "youtube_channel", "sjednicevijeca", "facebook", "vimeo", "esjednice", "e_grad",
            "minutes_found", "minutes_sample", "minutes_page", "recording_hints", "gazette", "consultations", "confidence", "requests",
            "evidence"]
    with open(OUT / "registry.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in recs:
            rc = r["recordings"]
            w.writerow([r["code"], r["name"], r["type"], r["county"], r["website_registry"], r["final_url"], r["status"],
                        r["council_page"], r["recording_type"], " ".join(rc["audio_links_sample"][:2]),
                        " ".join(rc["youtube"][:2]), " ".join(rc["youtube_channel"][:1]), " ".join(rc["sjednicevijeca"][:1]),
                        " ".join(rc["facebook"][:1]), " ".join(rc["vimeo"][:1]), rc["esjednice"] or "", rc.get("e_grad") or "",
                        r["minutes_found"], r["minutes_sample"], r["minutes_page"], " ".join(r.get("recording_hints") or []), r["gazette"], r["consultations"],
                        r["confidence"], r["requests"], " | ".join(r["evidence"])])

    def counts(rs):
        return {
            "units": len(rs),
            "status": dict(Counter(r["status"] for r in rs)),
            "recording_type": dict(Counter(r["recording_type"] for r in rs)),
            "council_page": sum(bool(r["council_page"]) for r in rs),
            "minutes": sum(r["minutes_found"] for r in rs),
            "audio": sum(bool(r["recordings"]["audio_links_sample"]) for r in rs),
            "youtube": sum(bool(r["recordings"]["youtube"]) for r in rs),
            "youtube_channel_only": sum(bool(r["recordings"]["youtube_channel"]) and not r["recordings"]["youtube"]
                                        for r in rs),
            "sjednicevijeca": sum(bool(r["recordings"]["sjednicevijeca"]) for r in rs),
            "facebook_video": sum(bool(r["recordings"]["facebook"]) for r in rs),
            "esjednice": sum(bool(r["recordings"]["esjednice"]) for r in rs),
            "e_grad_portal": sum(bool(r["recordings"].get("e_grad")) for r in rs),
            "recording_hint_only": sum(bool(r.get("recording_hints")) and r["recording_type"] not in
                                       ("audio", "youtube", "stream_service") for r in rs),
            "gazette": sum(bool(r["gazette"]) for r in rs),
            "consultations": sum(bool(r["consultations"]) for r in rs),
            "confidence": dict(Counter(r["confidence"] for r in rs)),
        }
    by_county = defaultdict(list)
    for r in recs:
        by_county[r["county"]].append(r)
    summary = {"generated": time.strftime("%Y-%m-%d %H:%M"), "total": counts(recs),
               "by_type": {t: counts([r for r in recs if r["type"] == t]) for t in ("grad", "općina")},
               "by_county": {c: counts(rs) for c, rs in sorted(by_county.items())},
               "mean_requests_per_unit": round(sum(r["requests"] for r in recs) / max(1, len(recs)), 2),
               "max_requests_per_unit": max((r["requests"] for r in recs), default=0)}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    return summary


def calib_report(recs):
    by_code = {r["code"]: r for r in recs}
    hit = tot = 0
    for key, (code, known) in CALIB.items():
        r = by_code.get(code)
        if not r:
            continue
        got = set()
        if r["recordings"]["audio_links_sample"]:
            got.add("audio")
        if r["recordings"]["youtube"]:
            got.add("youtube")
        if r["recordings"]["esjednice"]:
            got.add("esjednice")
        ok = known <= got
        hit += sum(k in got for k in known)
        tot += len(known)
        print(f"{'OK ' if ok else 'MISS'} {key:15} known={sorted(known)} got={sorted(got)} type={r['recording_type']} "
              f"status={r['status']} minutes={r['minutes_found']} req={r['requests']} council={r['council_page']}")
    print(f"calibration: {hit}/{tot} known facts found")


def load_units(sel=None):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("SELECT code, oib, name, type, county, website FROM units ORDER BY code").fetchall()
    con.close()
    if sel:
        keys = [s.strip() for s in sel.split(",") if s.strip()]
        rows = [r for r in rows if any(k == r[0] or fold(k) in fold(r[2]).replace(" ", "") or fold(k) in fold(r[2])
                                       for k in keys)]
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--calib", action="store_true")
    ap.add_argument("--units")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.calib:
        codes = {c for c, _ in CALIB.values()}
        rows = [r for r in load_units() if r[0] in codes]
        progress = OUT / "calib.jsonl"
    else:
        rows = load_units(a.units)
        progress = OUT / ("progress.jsonl" if not a.units else "partial.jsonl")
    for pf in OUT.glob("*.jsonl"):  # remember every host that refused us in any earlier run
        for line in pf.read_text("utf-8").splitlines():
            for h in re.findall(r"(?:HTTP 40[3]|HTTP 429|bot check) at https?://([^/\s:]+)", line):
                BLOCKED_HOSTS.add(h.lower())
    done = {}
    if (a.resume or a.report) and progress.exists():
        for line in progress.read_text("utf-8").splitlines():
            r = json.loads(line)
            old = done.get(r["code"])
            if old and r["status"] == "dead" and old["status"] != "dead":
                # a later re-crawl hit a network failure (e.g. TLS handshake timeouts): keep the earlier result
                old["evidence"] = old["evidence"] + [f"re-crawl later failed ({r['evidence'][-1][:80] if r['evidence'] else 'dead'}); "
                                                     "earlier result kept"]
                continue
            done[r["code"]] = r
    if not a.report:
        todo = [r for r in rows if r[0] not in done]
        if not (a.resume and progress.exists()):
            progress.write_text("", "utf-8")
        t0 = time.time()
        lock = threading.Lock()
        random.seed(1)
        random.shuffle(todo)  # spread hosts sharing a provider
        with cf.ThreadPoolExecutor(a.threads) as ex, open(progress, "a", encoding="utf-8") as fh:
            futs = {ex.submit(run_unit, r): r for r in todo}
            for i, fu in enumerate(cf.as_completed(futs), 1):
                r = futs[fu]
                try:
                    rec = fu.result()
                except Exception as e:  # a bug for one unit must not kill the run
                    rec = finish(Unit(r), {"code": r[0], "name": r[2], "type": r[3], "county": r[4],
                                           "website_registry": r[5], "website_checked": []},
                                 "dead", None, None, [], Findings(), [])
                    rec["evidence"].append(f"crawler error: {type(e).__name__}: {e}")
                    import traceback; traceback.print_exc()
                done[rec["code"]] = rec
                with lock:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                print(f"[{i}/{len(todo)} {time.time() - t0:5.0f}s] {rec['name'][:32]:32} {rec['status']:17} "
                      f"{rec['recording_type']:14} min={int(rec['minutes_found'])} esj={int(bool(rec['recordings']['esjednice']))} "
                      f"req={rec['requests']}", flush=True)
        print(f"crawled {len(todo)} units in {time.time() - t0:.0f}s")
    recs = [done[r[0]] for r in rows if r[0] in done]
    if a.calib:
        calib_report(recs)
        return
    if a.units:
        return
    s = write_outputs(recs)
    print(json.dumps(s["total"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    import http.client  # noqa: F401  (used in the except clause of Unit.get)
    main()
