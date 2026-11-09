"""Record the live demo (reports/demo_uzivo.md) as a video, to review it before presenting.

Opens with /intro (the numbers, 35 s), then drives the real feed (local server) through the script: start screen → Brckovljani → Zagreb (property tax post,
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
        started = time.monotonic()  # the recording starts with the page
        # one clock for the whole video, in the timing of reports/demo_uzivo.md (3:00 in all)
        t0 = [0.0]
        at = lambda sec: pg.wait_for_timeout(max(0, int((t0[0] + sec - time.monotonic()) * 1000)))
        say = lambda t: pg.evaluate(CAP, t)
        pg.on("load", lambda _: pg.evaluate("location.pathname.match(/feed|demo/) && (document.documentElement.style.zoom = '1.35')"))
        art = "article:has-text('{}')"

        # 0:00 intro (/intro plays by itself, 35.5 s)
        pg.goto(f"{URL}/intro")
        pg.evaluate("document.fonts.ready")
        t0[0] = time.monotonic()
        lead = t0[0] - started
        at(35.5)
        # 0:35 web
        pg.goto(f"{URL}/feed")
        pg.evaluate("localStorage.removeItem('vij.city')")
        pg.goto(f"{URL}/feed")
        pg.wait_for_selector("#start:not([hidden])")
        pg.evaluate("document.getElementById('tchart').scrollIntoView({behavior:'smooth',block:'center'})")
        say("eVijećnica pokriva svih 15 najvećih gradova i pokazuje gdje je izlaznost najniža.")
        at(45)
        pg.evaluate("document.getElementById('towns-low').scrollIntoView({behavior:'smooth',block:'center'})")
        at(47)
        pg.click("#towns-low [data-c=brckovljani]")
        say("Brckovljani: najniža izlaznost u Hrvatskoj, a vijeće nije objavilo nijedan zapisnik.")
        at(57)
        pg.click("header h1")
        pg.wait_for_timeout(500)
        pg.click("#towns-big [data-c=zagreb]")
        sel = art.format("Porez na nekretnine u Zagrebu")
        pg.locator(sel).first.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-140,behavior:'smooth'})")
        say("Zapisnik kaže samo „izmjene lokalnih poreza”. Iz prijedloga odluke: 8,00 eura po m² umjesto 5,00.")
        at(66)
        post = pg.locator(sel).first
        post.locator(".dots button").nth(1).click()
        say("Što je odlučeno i što to znači za tebe, jednostavnim riječima.")
        at(73)
        clubs = post.locator(".slide").evaluate_all("els => els.findIndex(e => e.textContent.includes('Kako su glasali klubovi'))")
        post.locator(".dots button").nth(clubs).click()
        say("Kako su glasali klubovi: iz službenog poimeničnog glasovanja. Ispod svake objave je izvor.")
        at(85)
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        pg.wait_for_timeout(600)
        pg.select_option("#city", "cakovec")
        pg.wait_for_timeout(600)
        sel = art.format("Prijenos sjednica gradskog")
        pg.locator(sel).first.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-140,behavior:'smooth'})")
        say("Vijest je i ono što nije prošlo: u Čakovcu prijedlog da se sjednice prenose uživo.")
        at(100)
        # 1:40 Reddit
        pg.goto((OUT / "reddit.html").as_uri())
        say("Ista objava ide na Reddit, s tablicom glasovanja i izvorom. Objavljuje osoba, ne bot.")
        at(110)
        pg.mouse.wheel(0, 900)
        at(120)
        # 2:00 MCP
        pg.goto((OUT / "mcp.html").as_uri())
        say("Isti podaci dostupni su svakom AI asistentu, preko otvorenog MCP poslužitelja.")
        at(133)
        pg.evaluate("document.querySelectorAll('section')[1].scrollIntoView({behavior:'smooth',block:'start'})")
        say("Što je rečeno na sjednici u Velikoj Gorici o vrtićima: tekst iz snimke, s vremenom.")
        at(147)
        pg.evaluate("document.querySelectorAll('section')[2].scrollIntoView({behavior:'smooth',block:'start'})")
        say("I obećanja s aktualnog sata u Zagrebu: 57, svako s citatom i rokom.")
        at(165)
        # 2:45 close
        pg.goto(f"{URL}/feed")
        pg.evaluate("localStorage.removeItem('vij.city')")
        pg.goto(f"{URL}/feed")
        pg.wait_for_selector("#start:not([hidden])")
        say("Otvoreni podaci, otvoreni kod. eVijećnica: tvoj grad, u minuti. evijecnica.vercel.app")
        at(180.5)
        video = pg.video.path()
        ctx.close()
        b.close()
    # cut the page-load lead-in, so 0:00 is the intro's first frame and the video is exactly 3:00
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{lead:.2f}", "-i", video, "-t", "180", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
                    str(OUT / "demo.mp4")], check=True)
    print(f"-> {OUT / 'demo.mp4'}")


if __name__ == "__main__":
    main()
