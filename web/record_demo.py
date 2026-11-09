"""Record the live demo (reports/demo_uzivo.md) as a video, to review it before presenting.

Opens with /intro?part=a (the numbers and how we got the data, 65 s), then drives the real feed (local server):
start screen → #mjesto (town card) → #tema (topic chip, a hashtag) → one post (carousel, "did not pass", source,
"Zašto ovo vidim?"); then the Reddit text of the same posts (rendered Markdown from data/posts/reddit/), three
questions answered through the MCP server in three assistants (web/mcp_chats.py; real calls in deploy/demo_video/mcp_calls.json), and /intro?part=b. Narration is shown as captions. 1920x1080, H.264.

Usage: mcp_server.py --http 8103 running, then
       uv run --with playwright python web/record_demo.py [--clean]  ->  deploy/demo_video/demo.mp4 (demo_clean.mp4)
"""
import html
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import mcp_chats

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "demo_video"
URL = "http://localhost:8103"
CSS = """body{margin:0;background:#0d1320;color:#eef2f8;font:22px/1.5 'Public Sans',system-ui,sans-serif}
.w{max-width:1100px;margin:0 auto;padding:60px 40px 160px} h1{font:700 52px 'Newsreader',Georgia,serif;margin:0 0 6px}
.k{font:800 18px sans-serif;letter-spacing:.14em;color:#7fa8ec;text-transform:uppercase}"""
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,700'
         '&family=Public+Sans:wght@400;600;800&display=swap">')


def research_page():
    """Why social media: the Croatian figure from the EP Youth Survey 2024 (bars) beside clips of the two papers,
    the key sentence highlighted (positions from pdftotext -bbox, pages shown 640 px wide = 905 px tall).
    Page images: video/research/ (pdftoppm -r 110 of the two PDFs)."""
    rs = (ROOT / "video" / "research").as_uri()
    bars = [("Društvene mreže", 48), ("TV", 40), ("Internetski portali", 32), ("Video platforme (YouTube…)", 18)]
    rows = "".join(f'<div class="bar{" hi" if i == 0 else ""}"><span>{n}</span><div class="tr"><s style="--w:{v * 2}%"></s></div>'
                   f'<b>{v} %</b></div>' for i, (n, v) in enumerate(bars))
    return f"""<!doctype html><meta charset="utf-8">{FONTS}<style>
body{{margin:0;height:100vh;overflow:hidden;background:#0d1320;color:#eef2f8;font:22px/1.4 'Public Sans',system-ui,sans-serif;
  display:grid;grid-template-columns:47% 53%;align-items:center}}
.l{{padding:0 40px 0 110px}} .k{{font:800 18px sans-serif;letter-spacing:.14em;color:#7fa8ec;text-transform:uppercase}}
.big{{font:800 150px/1 'Public Sans',sans-serif;color:#7fa8ec;margin:14px 0 6px}}
h1{{font:700 40px/1.2 Newsreader,Georgia,serif;margin:0 0 34px}}
.bar{{display:grid;grid-template-columns:300px 1fr 80px;gap:16px;align-items:center;margin:12px 0;font-weight:600;color:#98a3b8}}
.bar.hi{{color:#eef2f8}} .tr{{height:26px}} .bar s{{display:block;height:100%;width:0;border-radius:6px;background:#3a4a6b;
  animation:g 1.4s cubic-bezier(.2,.8,.2,1) forwards .6s}} .bar.hi s{{background:#7fa8ec}} .bar b{{text-align:right}}
@keyframes g{{to{{width:var(--w)}}}}
.src{{color:#98a3b8;font-size:16px;margin-top:30px}}
.r{{position:relative;height:100vh}}
.clip{{position:absolute;width:640px;background:#fff;border-radius:6px;box-shadow:0 30px 70px rgba(0,0,0,.55);overflow:hidden;
  opacity:0;transform:translateY(40px) rotate(var(--rot));animation:in .9s forwards var(--d)}}
@keyframes in{{to{{opacity:1;transform:translateY(0) rotate(var(--rot))}}}}
.clip .pg{{position:relative;height:330px;overflow:hidden}} .clip img{{position:absolute;left:0;width:100%}}
.hl{{position:absolute;background:rgba(255,214,0,.45);mix-blend-mode:multiply;border-radius:3px;width:0;animation:h .9s forwards var(--hd)}}
@keyframes h{{to{{width:var(--hw)}}}}
.cap{{background:#151d2d;color:#dfe6f2;font-size:16px;padding:12px 18px;line-height:1.35}} .cap b{{color:#fff}}
</style>
<div class="l"><div class="k">Zašto društvene mreže?</div><div class="big">48 %</div>
<h1>mladih u Hrvatskoj o politici se najčešće informira na društvenim mrežama</h1>{rows}
<div class="src">Europski parlament, Youth Survey 2024 (Flash Eurobarometar FL013EP), dob 16–30, Hrvatska n = 1.003; do tri odgovora</div></div>
<div class="r">
 <div class="clip" style="left:60px;top:90px;--rot:-2deg;--d:.9s">
  <div class="pg"><img src="{rs}/ep_youth_survey_2024_p26.png" style="top:-109px">
   <span class="hl" style="left:10.9%;top:159px;height:16px;--hw:78.2%;--hd:2s"></span>
   <span class="hl" style="left:10.9%;top:175px;height:16px;--hw:78.2%;--hd:2.4s"></span>
   <span class="hl" style="left:10.9%;top:191px;height:16px;--hw:54%;--hd:2.8s"></span></div>
  <div class="cap"><b>Youth Survey 2024</b> · Europski parlament / Eurobarometar, str. 26</div></div>
 <div class="clip" style="left:300px;top:560px;--rot:2.5deg;--d:1.6s">
  <div class="pg" style="height:300px"><img src="{rs}/fes_studija_o_mladima_2024_p6.png" style="top:-525px">
   <span class="hl" style="left:24.2%;top:84px;height:17px;--hw:31%;--hd:3.2s"></span>
   <span class="hl" style="left:25.9%;top:98px;height:17px;--hw:27%;--hd:3.6s"></span></div>
  <div class="cap"><b>Studija o mladima Hrvatska 2024.</b> · FES / Institut za društvena istraživanja, str. 6</div></div>
</div>"""


def reddit_page():
    """The Čakovec live-stream post as it would look in a Reddit thread (a mock-up: not published; no Reddit logo)."""
    t = (ROOT / "data" / "posts" / "reddit" / "cakovec-4-25-1.md").read_text()
    head, body = t.split("\n---\n", 1)
    title = next(line.split('"', 1)[1].rsplit('"', 1)[0] for line in head.splitlines() if line.startswith("title:"))
    body = body.rsplit("\n---\n", 1)[0]
    up = '<svg viewBox="0 0 20 20" width="22"><path d="M10 3 3 11h4v6h6v-6h4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'
    return f"""<!doctype html><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<style>
html{{zoom:1.45}} body{{margin:0;background:#dae0e6;font:15px/1.5 -apple-system,"Helvetica Neue",Arial,sans-serif;color:#1c1c1c}}
.top{{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #edeff1;height:56px;display:flex;align-items:center;gap:18px;padding:0 24px}}
.dot{{width:34px;height:34px;border-radius:50%;background:#ff4500;color:#fff;display:grid;place-items:center;font:800 15px sans-serif}}
.search{{flex:1;max-width:620px;margin:0 auto;background:#f6f7f8;border:1px solid #edeff1;border-radius:20px;padding:9px 16px;color:#878a8c}}
.mock{{background:#fff3cd;color:#664d03;font-size:14px;font-weight:600;padding:6px 14px;border-radius:6px}}
.banner{{height:80px;background:linear-gradient(90deg,#0b4f9c,#1a7ec7)}}
.sub{{background:#fff;padding:0 24px 12px}} .sub .in{{max-width:1080px;margin:0 auto;display:flex;align-items:end;gap:14px}}
.sub .av{{width:72px;height:72px;border-radius:50%;border:4px solid #fff;background:#1a7ec7;color:#fff;display:grid;place-items:center;font:800 26px sans-serif;margin-top:-24px}}
.sub h1{{font:700 26px sans-serif;margin:0}} .sub small{{color:#7c7c7c}}
.wrap{{max-width:1080px;margin:20px auto;display:grid;grid-template-columns:1fr 312px;gap:24px}}
.post{{background:#fff;border:1px solid #ccc;border-radius:6px;display:grid;grid-template-columns:44px 1fr}}
.votes{{background:#f8f9fa;border-radius:6px 0 0 6px;display:flex;flex-direction:column;align-items:center;padding:10px 0;color:#878a8c;gap:4px;font-weight:700}}
.votes .dn{{transform:rotate(180deg)}}
.pc{{padding:10px 16px 6px}} .meta{{font-size:13px;color:#787c7e}} .meta b{{color:#1c1c1c}}
.fl{{display:inline-block;background:#0079d3;color:#fff;font-size:12px;font-weight:700;border-radius:12px;padding:1px 9px;margin-left:6px}}
h2{{font:600 21px/1.35 sans-serif;margin:6px 0 10px}}
.b table{{border-collapse:collapse;margin:6px 0}} .b td,.b th{{border:1px solid #ccc;padding:4px 12px}} .b p{{margin:8px 0}}
.b em{{color:#555}}
.acts{{display:flex;gap:18px;color:#878a8c;font-size:13px;font-weight:700;padding:8px 0}}
.cm{{border:1px solid #ccc;border-radius:4px;margin:6px 0 14px;padding:12px;color:#878a8c;min-height:60px}}
.side .box{{background:#fff;border:1px solid #ccc;border-radius:6px;overflow:hidden;margin-bottom:16px}}
.side .box h3{{margin:0;background:#0b4f9c;color:#fff;font-size:14px;padding:10px 12px}} .side .box p{{margin:0;padding:12px;font-size:14px}}
</style>
<div class="top"><div class="dot">r/</div><b>r/croatia</b><div class="search">Pretraži r/croatia</div><span class="mock">Prikaz: kako bi objava izgledala</span></div>
<div class="banner"></div>
<div class="sub"><div class="in"><div class="av">hr</div><div><h1>Croatia</h1><small>r/croatia</small></div></div></div>
<div class="wrap"><div>
 <div class="post"><div class="votes"><span>{up}</span><span>•</span><span class="dn">{up}</span></div>
 <div class="pc"><div class="meta"><b>r/croatia</b> · objavio u/evijecnica (osoba, ne bot) <span class="fl">Čakovec</span></div>
 <h2>{html.escape(title)}</h2><div class="b" data-md="{html.escape(body)}"></div>
 <div class="acts"><span>💬 Komentari</span><span>↗ Podijeli</span><span>☆ Spremi</span></div>
 <div class="cm">Što ti misliš? Dodaj komentar…</div></div></div>
</div><div class="side">
 <div class="box"><h3>O objavi</h3><p>Tjedni pregled odluka gradskog vijeća, iz službenog zapisnika. Objavu priprema eVijećnica,
 a objavljuje osoba, uz dopuštenje moderatora. Izvor je naveden na dnu.</p></div>
 <div class="box"><h3>eVijećnica</h3><p>Ista objava kao karusel za Instagram i kao kartica na evijecnica.vercel.app.</p></div>
</div></div>
<script>document.querySelectorAll('[data-md]').forEach(e=>e.innerHTML=marked.parse(e.dataset.md))</script>"""


CAP = """(t) => { let c = document.getElementById('__cap'); if (!c) { c = document.createElement('div'); c.id = '__cap';
  c.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);max-width:1500px;z-index:99999;'
   + 'background:rgba(0,0,0,.78);color:#fff;font:600 30px/1.35 system-ui,sans-serif;padding:12px 26px;border-radius:12px;text-align:center';
  document.body.appendChild(c); } c.textContent = t; c.style.display = t ? 'block' : 'none'; }"""


CAPTIONS = "--clean" not in sys.argv  # --clean: no on-screen captions (for the narrated video with demo.srt)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reddit.html").write_text(reddit_page())
    (OUT / "research.html").write_text(research_page())
    mcp_chats.build()  # mcp_chatgpt.html, mcp_claude.html, mcp_gemini.html from mcp_calls.json
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT / "raw"),
                            record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page()
        started = time.monotonic()  # the recording starts with the page
        # one clock for the whole video, in the timing of reports/demo_uzivo.md (3:00 in all)
        t0 = [0.0]
        at = lambda sec: pg.wait_for_timeout(max(0, int((t0[0] + sec - time.monotonic()) * 1000)))
        say = (lambda t: pg.evaluate(CAP, t)) if CAPTIONS else (lambda t: None)
        pg.on("load", lambda _: pg.evaluate("location.protocol.startsWith('http') && /^\\/(feed|demo)$/.test(location.pathname) && (document.documentElement.style.zoom = '1.35')"))
        art = "article:has-text('{}')"

        # 0:00 problem + how we got the data (/intro?part=a plays by itself, 65 s)
        pg.goto(f"{URL}/intro?part=a")
        pg.evaluate("document.fonts.ready")
        t0[0] = time.monotonic()
        lead = t0[0] - started
        at(65)
        # 1:05 web: the start screen
        pg.goto(f"{URL}/feed")
        pg.evaluate("localStorage.clear()")
        pg.goto(f"{URL}/feed")
        pg.wait_for_selector("#start:not([hidden])")
        say("Evo kako to izgleda. Svih 15 najvećih gradova Hrvatske, i za svaki kolika je bila izlaznost.")
        pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('tchart').scrollIntoView({behavior:'smooth',block:'center'})")
        at(75)
        # 1:15 #mjesto: pick the town, its card
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        pg.wait_for_timeout(500)
        pg.click("#towns-big [data-c=zagreb]")
        say("#mjesto: odabereš svoje mjesto i vidiš samo svoje vijeće: tko u njemu sjedi i što je odlučilo.")
        at(81)
        pg.evaluate("window.scrollBy({top:420,behavior:'smooth'})")
        at(87)
        # 1:27 #tema: a topic chip, then a hashtag in a post (same topic in every town)
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        pg.wait_for_timeout(500)
        pg.click("#filters [data-tag='#proračun']")
        say("#tema: ili kreneš od teme koja te zanima.")
        at(93)
        pg.select_option("#city", "")
        pg.wait_for_timeout(400)
        tag = pg.locator("article .tags a:not([href='#prora%C4%8Dun'])").first
        tag.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-200,behavior:'smooth'})")
        say("Svaki hashtag je poveznica: jednim klikom ista tema u svim gradovima.")
        at(97)
        tag.click()
        pg.wait_for_timeout(400)
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        at(101)
        # 1:41 one post: carousel, the "did not pass" stamp, the source, "Zašto ovo vidim?"
        pg.click("#filters [data-tag='']")
        pg.select_option("#city", "cakovec")
        pg.wait_for_timeout(600)
        pg.evaluate("while (document.querySelector('#feed .sentinel')) more()")  # the feed draws 12 posts at a time
        sel = art.format("Prijenos sjednica gradskog")
        pg.locator(sel).first.scroll_into_view_if_needed()
        pg.evaluate("window.scrollBy({top:-140,behavior:'smooth'})")
        say("Svaka objava stane u minutu. Vijest je i ono što nije prošlo.")
        at(106)
        post = pg.locator(sel).first
        post.locator(".dots button").nth(1).click()
        say("Što je odlučeno, kako se glasalo i što to znači za tebe.")
        at(110)
        post.locator("details.why summary").click()
        post.locator(".srclink").evaluate("e => e.scrollIntoView({behavior:'smooth',block:'center'})")
        say("Ispod svake objave je izvor: zapisnik, materijal ili trenutak u snimci.")
        at(115)
        # 1:55 why social media (research), then the Reddit thread
        pg.goto((OUT / "research.html").as_uri())
        say("Za gotovo polovicu mladih u Hrvatskoj društvene mreže su najčešći izvor informacija o politici.")
        at(122)
        pg.goto((OUT / "reddit.html").as_uri())
        say("Zato je svaka objava spremna i za njih: najvažnije na Instagram, tjedni pregled na Reddit.")
        at(126)
        pg.evaluate("window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})")
        at(130)
        # 2:10 MCP: the same server in three assistants (RAG over minutes and transcripts)
        for k, ui in enumerate(("chatgpt", "claude", "gemini")):
            pg.goto((OUT / f"mcp_{ui}.html").as_uri())
            pg.evaluate("document.documentElement.style.zoom = '1.25'; play(); 0")
            say(["ChatGPT: sport, liječnički pregled i kako se glasalo.", "Claude: stipendije u Zagrebu i Rijeci.",
                 "Gemini: novi vrtići u cijeloj Hrvatskoj."][k])
            at(142 + 12 * k - (1 if k == 2 else 0))
        # 2:45 the closing idea (/intro?part=b, 15 s)
        say("")
        pg.goto(f"{URL}/intro?part=b")
        at(180.5)
        video = pg.video.path()
        ctx.close()
        b.close()
    name = "demo.mp4" if CAPTIONS else "demo_clean.mp4"
    # cut the page-load lead-in, so 0:00 is the intro's first frame and the video is exactly 3:00
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{lead:.2f}", "-i", video, "-t", "180", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
                    str(OUT / name)], check=True)
    print(f"-> {OUT / name}")


if __name__ == "__main__":
    main()
