"""Record the live demo (reports/demo_uzivo.md) as a video, to review it before presenting.

Opens with /intro?part=a (the numbers and how we got the data, 65 s), then drives the real feed (local server):
start screen → #mjesto (town card) → #tema (topic chip, a hashtag) → one post (carousel, "did not pass", source,
"Zašto ovo vidim?"); then the Reddit text of the same posts (rendered Markdown from data/posts/reddit/), three
questions answered through the MCP server (real calls, deploy/demo_video/mcp_calls.json), and /intro?part=b. Narration is shown as captions. 1920x1080, H.264.

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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "demo_video"
URL = "http://localhost:8103"
CSS = """body{margin:0;background:#0d1320;color:#eef2f8;font:22px/1.5 'Public Sans',system-ui,sans-serif}
.w{max-width:1100px;margin:0 auto;padding:60px 40px 160px} h1{font:700 52px 'Newsreader',Georgia,serif;margin:0 0 6px}
.k{font:800 18px sans-serif;letter-spacing:.14em;color:#7fa8ec;text-transform:uppercase}"""
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,700'
         '&family=Public+Sans:wght@400;600;800&display=swap">')


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


def mcp_page():
    """An AI-assistant chat (any MCP client: Claude, ChatGPT, Gemini…) answering from the real MCP calls in
    mcp_calls.json; window.step(i) shows question i, the tool call, then the answer (driven by main())."""
    calls = json.loads((OUT / "mcp_calls.json").read_text())
    e = html.escape
    turns = []
    for c in calls:
        r, tool = c["result"], c["tool"]
        if tool == "get_item":
            rows = "".join(f"<tr><td>{e(k['short'])}</td><td>{k['za']}</td><td>{k['protiv']}</td><td>{k['nije_glasovao']}</td>"
                           f"<td>{k['odsutan']}</td></tr>" for k in r["clubs"][:6])
            ans = (f"<p>Skupština je <b>usvojila</b> izmjene Odluke o lokalnim porezima: <b>{r['za']} za, {r['protiv']} protiv</b>, "
                   f"{r['suzdrzano']} suzdržanih. Predlagatelj je gradonačelnik.</p><p>Po klubovima:</p>"
                   f"<table><tr><th>klub</th><th>za</th><th>protiv</th><th>nije glasovao</th><th>odsutan</th></tr>{rows}</table>"
                   f"<p class='src'>Izvor: 14. sjednica, točka 9, službeno poimenično glasovanje · <a>web.zagreb.hr</a></p>")
        elif tool == "search":
            items = "".join(f"<li>„{e(x['text'].replace('**', ''))[:230]}”<br><a>▶ {x['at']} u snimci</a></li>"
                            for x in r["said_in_session"][:3])
            ans = (f"<p>Na <b>8. sjednici</b> Gradskog vijeća vrtići su se spominjali nekoliko puta. Iz transkripta snimke:</p>"
                   f"<ul>{items}</ul><p class='src'>Izvor: transkript audio snimke sjednice (gorica.hr), s vremenom u snimci</p>")
        else:
            ps = [p for p in r["promises"] if p["deadline"] and len(p["quote"]) <= 160][:3]
            items = "".join(f"<li><b>{e(p['speaker'])}</b>: „{e(p['quote'])}”<br><small>rok: {e(p['deadline'])} · "
                            f"{e(p['status_label'])}</small></li>" for p in ps)
            ans = (f"<p>Na aktualnom satu zabilježeno je <b>{r['count']} obećanja</b>. Neka s rokom:</p><ul>{items}</ul>"
                   f"<p class='src'>Izvor: transkript 14. sjednice, aktualni sat</p>")
        args = ", ".join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in c["args"].items())
        turns.append(f"<div class='turn'><div class='you'>{e(c['q'])}</div>"
                     f"<div class='bot'><div class='tool'><span class='spin'></span>evijecnica · <b>{tool}</b>"
                     f"<code>{{{e(args)}}}</code><span class='ms'>{c['ms']} ms</span></div>"
                     f"<div class='ans'>{ans}</div></div></div>")
    return f"""<!doctype html><meta charset="utf-8">{FONTS}<style>
body{{margin:0;background:#f7f6f2;color:#1f1e1c;font:19px/1.55 -apple-system,"Public Sans",system-ui,sans-serif;display:grid;grid-template-columns:270px 1fr;height:100vh}}
aside{{background:#efede6;border-right:1px solid #e2dfd6;padding:22px 18px;font-size:16px;color:#5c5a54}}
aside .new{{background:#fff;border:1px solid #e2dfd6;border-radius:10px;padding:10px 14px;color:#1f1e1c;font-weight:600;margin-bottom:22px}}
aside .h{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:18px 0 8px}}
aside .conn{{display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #e2dfd6;border-radius:10px;padding:10px 12px;color:#1f1e1c}}
aside .conn i{{width:9px;height:9px;border-radius:50%;background:#2e9e5b}}
aside .works{{margin-top:12px;line-height:1.7}}
main{{display:flex;flex-direction:column;min-height:0}}
.bar{{padding:14px 32px;border-bottom:1px solid #e2dfd6;display:flex;justify-content:space-between;font-size:16px;color:#5c5a54}}
.bar b{{color:#1f1e1c}}
.chat{{flex:1;overflow:auto;padding:26px 0 40px;scroll-behavior:smooth}}
.turn{{max-width:960px;margin:0 auto 34px;padding:0 32px;display:none}} .turn.on{{display:block}}
.you{{margin-left:auto;width:fit-content;max-width:75%;background:#e9e5da;border-radius:18px;padding:12px 18px;margin-bottom:18px}}
.bot{{display:grid;grid-template-columns:36px 1fr;gap:14px}}
.bot:before{{content:"✳";width:34px;height:34px;border-radius:50%;background:#d97757;color:#fff;display:grid;place-items:center;font-size:18px}}
.tool{{grid-column:2;display:flex;align-items:center;gap:10px;border:1px solid #e2dfd6;background:#fff;border-radius:10px;padding:8px 14px;font-size:15px;color:#5c5a54;width:fit-content;opacity:0;transition:opacity .4s}}
.tool code{{font:14px ui-monospace,Menlo,monospace;color:#8a5a2b}} .tool .ms{{color:#9a978e}}
.spin{{width:12px;height:12px;border-radius:50%;border:2px solid #d97757;border-right-color:transparent;animation:r .8s linear infinite}}
.tool.done .spin{{animation:none;border:0;background:#2e9e5b}}
@keyframes r{{to{{transform:rotate(1turn)}}}}
.ans{{grid-column:2}} .ans>*{{opacity:0;transform:translateY(6px);transition:opacity .45s,transform .45s}} .ans>.on{{opacity:1;transform:none}}
.ans p{{margin:10px 0}} .ans ul{{margin:6px 0;padding-left:22px}} .ans li{{margin:8px 0}} .ans small,.src{{color:#7a776f;font-size:15px}}
.ans a{{color:#b4562f;text-decoration:underline}}
table{{border-collapse:collapse;font-size:16px;margin:4px 0}} td,th{{border:1px solid #e2dfd6;padding:4px 12px;text-align:left;background:#fff}}
.input{{max-width:960px;width:calc(100% - 64px);margin:0 auto 22px;border:1px solid #d6d2c6;background:#fff;border-radius:16px;padding:16px 18px;color:#9a978e;display:flex;justify-content:space-between}}
.input span{{font-size:14px;border:1px solid #e2dfd6;border-radius:8px;padding:2px 10px;color:#5c5a54}}
</style>
<aside><div class="new">+ Novi razgovor</div><div class="h">Povezani MCP poslužitelji</div>
<div class="conn"><i></i><b>evijecnica</b>&nbsp;· 17 alata</div>
<div class="works"><div class="h">Isti poslužitelj radi u</div>Claude<br>ChatGPT<br>Gemini<br>i drugim MCP klijentima</div></aside>
<main><div class="bar"><span><b>AI asistent</b> · pitaj vijeće</span><span>MCP: http…/mcp · streamable HTTP</span></div>
<div class="chat" id="chat">{''.join(turns)}</div>
<div class="input">Pitaj bilo što o svom gradskom vijeću…<span>⚙ evijecnica</span></div></main>
<script>
window.step = i => {{
  const t = document.querySelectorAll('.turn')[i], chat = document.getElementById('chat'), down = () => chat.scrollTop = chat.scrollHeight;
  t.classList.add('on'); down();
  const tool = t.querySelector('.tool'), parts = [...t.querySelectorAll('.ans>*')];
  setTimeout(() => {{ tool.style.opacity = 1; down(); }}, 700);
  setTimeout(() => tool.classList.add('done'), 1700);
  parts.forEach((p, k) => setTimeout(() => {{ p.classList.add('on'); p.scrollIntoView({{behavior:'smooth',block:'end'}}); }}, 1900 + k * 650));
}};
</script>"""


CAP = """(t) => { let c = document.getElementById('__cap'); if (!c) { c = document.createElement('div'); c.id = '__cap';
  c.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);max-width:1500px;z-index:99999;'
   + 'background:rgba(0,0,0,.78);color:#fff;font:600 30px/1.35 system-ui,sans-serif;padding:12px 26px;border-radius:12px;text-align:center';
  document.body.appendChild(c); } c.textContent = t; c.style.display = t ? 'block' : 'none'; }"""


CAPTIONS = "--clean" not in sys.argv  # --clean: no on-screen captions (for the narrated video with demo.srt)


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
        say = (lambda t: pg.evaluate(CAP, t)) if CAPTIONS else (lambda t: None)
        pg.on("load", lambda _: pg.evaluate("location.pathname.match(/feed|demo/) && (document.documentElement.style.zoom = '1.35')"))
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
        # 1:55 Reddit
        pg.goto((OUT / "reddit.html").as_uri())
        say("Spremno za društvene mreže: najvažnije objave tjedna na Instagram, tjedni pregled grada na Reddit.")
        at(121)
        pg.evaluate("window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})")
        at(130)
        # 2:10 MCP: RAG over minutes and transcripts, in an AI-assistant chat
        pg.goto((OUT / "mcp.html").as_uri())
        say("MCP: AI asistent prvo pretraži našu bazu zapisnika i transkripata, pa odgovori. To je RAG.")
        pg.evaluate("step(0)")
        at(142)
        pg.evaluate("step(1)")
        say("Što su vijećnici u Velikoj Gorici rekli o vrtićima: iz transkripta, s vremenom u snimci.")
        at(154)
        pg.evaluate("step(2)")
        say("Obećanja s aktualnog sata u Zagrebu, svako s citatom i rokom. Odgovor uvijek ima izvor.")
        at(165)
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
