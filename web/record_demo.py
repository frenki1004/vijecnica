"""Record the live demo (reports/demo_uzivo.md) as a video, to review it before presenting.

Drives the real feed (local server) through the script: start screen → Brckovljani → Zagreb (property tax post,
how the clubs voted) → Čakovec (did not pass); then the Reddit text of the same posts (rendered Markdown from
data/posts/reddit/) and three questions answered through the MCP server (real calls, recorded by this script into
deploy/demo_video/mcp_calls.json beforehand), then /demo. Narration is shown as captions. 1920x1080, H.264.

Usage: mcp_server.py --http 8103 running, then
       uv run --with playwright python web/record_demo.py   ->  deploy/demo_video/demo.mp4
"""
import html
import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "demo_video"
URL = "http://localhost:8103"
CSS = """body{margin:0;background:#0d1320;color:#eef2f8;font:22px/1.5 'Public Sans',system-ui,sans-serif}
.w{max-width:1100px;margin:0 auto;padding:60px 40px 160px} h1{font:700 52px 'Newsreader',Georgia,serif;margin:0 0 6px}
.k{font:800 18px sans-serif;letter-spacing:.14em;color:#7fa8ec;text-transform:uppercase}"""
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,700'
         '&family=Public+Sans:wght@400;600;800&display=swap">')


def reddit_page():
    """The Čakovec weekly digest and the live-stream post as Reddit would show the Markdown (no Reddit branding)."""
    docs = []
    for f in ("weekly/cakovec-2025-W51.md", "cakovec-4-25-1.md"):
        t = (ROOT / "data" / "posts" / "reddit" / f).read_text()
        head, body = t.split("\n---\n", 1)[0], t.split("\n---\n", 1)[1]
        title = next(line.split('"', 1)[1].rsplit('"', 1)[0] for line in head.splitlines() if line.startswith("title:"))
        docs.append((title, body))
    cards = "".join(f'<article class="md"><span class="fl">Čakovec</span><h2>{html.escape(t)}</h2>'
                    f'<div class="b" data-md="{html.escape(b)}"></div></article>' for t, b in docs)
    return f"""<!doctype html><meta charset="utf-8">{FONTS}
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<style>{CSS}
.md{{background:#f6f7f9;color:#1a1a1b;border-radius:14px;padding:28px 36px;margin:26px 0;font-size:19px}}
.md h2{{font:700 26px/1.3 sans-serif;margin:8px 0 12px}} .md table{{border-collapse:collapse}} .md td,.md th{{border:1px solid #ccd;padding:4px 12px}}
.fl{{font:700 15px sans-serif;background:#dbe4f3;color:#1d4f9c;border-radius:99px;padding:3px 12px}}</style>
<div class="w"><p class="k">Reddit</p><h1>Ista objava, kao tekst za raspravu</h1>
<p style="color:#98a3b8">Markdown iz posts/export_reddit.py; objavljuje osoba, ne bot.</p>{cards}</div>
<script>document.querySelectorAll('[data-md]').forEach(e=>e.innerHTML=marked.parse(e.dataset.md))</script>"""


def mcp_page():
    """The three MCP questions: question, the tool call (name, arguments, time) and what it returned."""
    calls = json.loads((OUT / "mcp_calls.json").read_text())
    blocks = []
    for c in calls:
        r, tool = c["result"], c["tool"]
        if tool == "get_item":
            clubs = "".join(f"<tr><td>{html.escape(k['short'])}</td><td>{k['za']}</td><td>{k['protiv']}</td>"
                            f"<td>{k['nije_glasovao']}</td><td>{k['odsutan']}</td></tr>" for k in r["clubs"][:7])
            res = (f"<p><b>{html.escape(r['title'])}</b>: {r['za']} za, {r['protiv']} protiv, {r['suzdrzano']} suzdržano"
                   f" ({html.escape(r['status'])}).</p><table><tr><th>klub</th><th>za</th><th>protiv</th>"
                   f"<th>nije glasovao</th><th>odsutan</th></tr>{clubs}</table>")
        elif tool == "search":
            res = "".join(f"<p class='q'>„{html.escape(x['text'].replace('**', ''))}”<br><small>{x['session']}. sjednica · "
                          f"{x['at']} u snimci · <a href='{html.escape(x['url'])}'>poslušaj</a></small></p>"
                          for x in r["said_in_session"][:3])
        else:
            res = f"<p>{r['count']} obećanja s rokom. Primjeri:</p>" + "".join(
                f"<p class='q'>„{html.escape(x['quote'])}”<br><small>{html.escape(x['topic'][:110])}… · rok: "
                f"{html.escape(x['deadline'])} · {html.escape(x['status'])}</small></p>" for x in r["promises"][:3])
        args = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
        blocks.append(f"<section><div class='you'>{html.escape(c['q'])}</div>"
                      f"<div class='call'>⚙ {tool}({html.escape(args)}) · {c['ms']} ms</div><div class='ans'>{res}</div></section>")
    return f"""<!doctype html><meta charset="utf-8">{FONTS}<style>{CSS}
section{{margin:34px 0}} .you{{background:#1d4f9c;border-radius:16px;padding:14px 20px;display:inline-block;max-width:900px}}
.call{{font:600 17px ui-monospace,monospace;color:#e2ad48;margin:12px 0}} .ans{{background:#151d2d;border:1px solid #26314a;border-radius:14px;padding:16px 22px}}
table{{border-collapse:collapse;font-size:18px}} td,th{{border:1px solid #26314a;padding:3px 12px;text-align:left}}
.q{{margin:8px 0}} .q small{{color:#98a3b8}} a{{color:#7fa8ec}}</style>
<div class="w"><p class="k">MCP · pitaj vijeće</p><h1>AI asistent odgovara iz istih podataka</h1>
<p style="color:#98a3b8">Stvarni pozivi MCP poslužitelja eVijećnice (streamable HTTP, /mcp); isto dobiva Claude, ChatGPT ili drugi agent.</p>
{''.join(blocks)}</div>"""


CAP = """(t) => { let c = document.getElementById('__cap'); if (!c) { c = document.createElement('div'); c.id = '__cap';
  c.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);max-width:1500px;z-index:99999;'
   + 'background:rgba(0,0,0,.78);color:#fff;font:600 30px/1.35 system-ui,sans-serif;padding:12px 26px;border-radius:12px;text-align:center';
  document.body.appendChild(c); } c.textContent = t; c.style.display = t ? 'block' : 'none'; }"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reddit.html").write_text(reddit_page())
    (OUT / "mcp.html").write_text(mcp_page())
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT / "raw"),
                            record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page()
        cap = lambda t, wait=0: (pg.evaluate(CAP, t), pg.wait_for_timeout(int(wait * 1300)))  # ~live pace
        center = lambda sel: pg.evaluate("s => document.querySelector(s).scrollIntoView({behavior:'smooth',block:'center'})", sel)
        art = "article:has-text('{}')"

        zoom = lambda: pg.evaluate("document.documentElement.style.zoom = '1.35'")  # fill the 1920 frame
        pg.on("load", lambda _: zoom())
        # 1. start screen
        pg.goto(f"{URL}/feed")
        pg.wait_for_selector("#start:not([hidden])")
        pg.evaluate("document.fonts.ready")
        cap("Gradsko vijeće odlučuje o tvom porezu, vrtiću i autobusu. To piše u zapisniku od 60 stranica.", 5)
        cap("Na lokalnim izborima 2025. u 20 najvećih gradova nije glasovalo 957.627 ljudi.", 4)
        pg.evaluate("document.getElementById('towns-big').scrollIntoView({behavior:'smooth',block:'start'})")
        cap("eVijećnica pokriva svih 15 najvećih gradova. Uz svaki: izlaznost i mjesto među 555 jedinica.", 5)
        pg.evaluate("document.getElementById('towns-low').scrollIntoView({behavior:'smooth',block:'center'})")
        cap("I pet općina s najnižom izlaznošću u Hrvatskoj.", 3.5)
        pg.click("#towns-low [data-c=brckovljani]")
        cap("Brckovljani: glasovao je svaki peti birač, a vijeće za ovaj saziv nije objavilo nijedan zapisnik.", 6)
        # 2. Zagreb
        pg.click("header h1")
        pg.wait_for_timeout(600)
        pg.click("#towns-big [data-c=zagreb]")
        cap("Zagreb: kartica grada iz otvorenih podataka (data.gov.hr) i rezultata izbora.", 4.5)
        sel = art.format("Porez na nekretnine u Zagrebu")
        pg.locator(sel).first.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-140,behavior:'smooth'})")
        cap("Zapisnik kaže samo „izmjene lokalnih poreza”. Iz prijedloga odluke: 8,00 eura po m² umjesto 5,00.", 6)
        post = pg.locator(sel).first
        post.locator(".dots button").nth(1).click()  # what was decided
        cap("Što je odlučeno i što to znači za tebe, jednostavnim riječima.", 5)
        clubs = post.locator(".slide").evaluate_all(
            "els => els.findIndex(e => e.textContent.includes('Kako su glasali klubovi'))")
        post.locator(".dots button").nth(clubs).click()
        cap("Kako su glasali klubovi, iz službenog poimeničnog glasovanja.", 6)
        post.locator(".srclink").scroll_into_view_if_needed()
        post.locator(".srclink").hover()
        cap("Ispod svake objave: službeni izvor.", 3.5)
        # 3. Čakovec
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        pg.wait_for_timeout(800)
        pg.select_option("#city", "cakovec")
        pg.wait_for_timeout(800)
        sel = art.format("Prijenos sjednica gradskog")
        pg.locator(sel).first.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-140,behavior:'smooth'})")
        cap("Vijest je i ono što nije prošlo: u Čakovcu prijedlog da se sjednice prenose uživo.", 6)
        # 4. Reddit
        pg.goto((OUT / "reddit.html").as_uri())
        pg.wait_for_timeout(800)
        cap("Ista objava ide na Reddit, gdje se raspravlja, s tablicom glasovanja i izvorom.", 5)
        pg.mouse.wheel(0, 900)
        cap("Objavljuje osoba, ne bot: sustav priprema tekst, urednik pregleda i objavi.", 5)
        # 5. MCP
        pg.goto((OUT / "mcp.html").as_uri())
        pg.wait_for_timeout(800)
        cap("Iste podatke može pitati i AI asistent, preko otvorenog MCP poslužitelja.", 6)
        cap("Kako su glasali klubovi o porezu u Zagrebu: poimenično, iz službenog glasovanja.", 6)
        pg.evaluate("document.querySelectorAll('section')[1].scrollIntoView({behavior:'smooth',block:'start'})")
        pg.wait_for_timeout(900)
        cap("Što je rečeno na sjednici u Velikoj Gorici o vrtićima: tekst iz snimke, s vremenom.", 7)
        pg.evaluate("document.querySelectorAll('section')[2].scrollIntoView({behavior:'smooth',block:'start'})")
        pg.wait_for_timeout(900)
        cap("I obećanja s aktualnog sata u Zagrebu: 57, svako s citatom i rokom.", 7)
        pg.goto(f"{URL}/demo")
        pg.wait_for_timeout(1200)
        cap("Na stranici /demo: šest snimljenih razgovora, poziv po poziv.", 4.5)
        pg.mouse.wheel(0, 900)
        pg.wait_for_timeout(2500)
        # 6. close
        pg.goto(f"{URL}/feed")
        pg.evaluate("localStorage.removeItem('vij.city')")
        pg.goto(f"{URL}/feed")
        pg.wait_for_selector("#start:not([hidden])")
        cap("eVijećnica: tvoj grad, u minuti. vijecnica.vercel.app", 5)
        video = pg.video.path()
        ctx.close()
        b.close()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(OUT / "demo.mp4")], check=True)
    print(f"-> {OUT / 'demo.mp4'}")


if __name__ == "__main__":
    main()
