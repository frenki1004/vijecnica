"""The MCP part of the demo video: the same eVijećnica MCP server answering in three AI assistants.

Three chat pages styled after ChatGPT (dark), Claude (warm light) and Gemini (light), no product logos, each with
a corner label saying it is an illustration. The question, the tool calls (name, arguments, time) and every fact
in the answer come from the real calls in deploy/demo_video/mcp_calls.json (web/mcp_demo_calls.py); the answer
text is composed from them here. play() runs the turn: question, tool calls, then the answer streams in word by
word (~11 s in all, web/record_demo.py calls it).
"""
import html
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "deploy" / "demo_video"
LABEL = "Ilustracija · pozivi i podaci: stvarni MCP poslužitelj eVijećnice"


def strip(t):
    return html.escape(re.sub(r"\*\*", "", t).strip(" …"))


def answers(calls):
    """{ui: (question, [tool calls], answer html)} from the recorded calls."""
    by = {c["ui"]: c for c in calls}
    out = {}

    c = by["chatgpt"]
    said = {x["at"]: x for x in c["calls"][0]["result"]["said_in_session"]}
    item = c["calls"][1]["result"]
    out["chatgpt"] = (c["q"], c["calls"], f"""
<p>Kratko: <b>zasad ne.</b> Na 14. sjednici Gradske skupštine (15. 10. 2026.) klub Drito predložio je da Grad od 2027.
sufinancira obvezne liječničke preglede djece sportaša: 30 % cijene za jedno dijete, 40 % za dvoje i 50 % za troje ili više.</p>
<p>Prijedlog <b>nije prošao: {item['za']} za, {item['protiv']} protiv.</b></p>
<ul><li><b>Za:</b> Drito (4), DP (1), HNS (1)</li><li><b>Protiv:</b> Možemo! (16), SDP (7)</li></ul>
<p>Iz rasprave (transkript snimke):</p>
<ul><li>pregled stoji <b>70 do 90 eura</b> po djetetu, a u nekim sportovima mora se obaviti dvaput godišnje <span class="ts">1:35:58</span></li>
<li>u Zagrebu za to postoje samo <b>3 lokacije</b> <span class="ts">1:35:33</span></li></ul>
<p class="src">Izvori: zapisnik i poimenično glasovanje, točka 23 · snimka 14. sjednice</p>""")

    c = by["claude"]
    zg = c["calls"][0]["result"]
    n = len(zg["agenda_items"])
    out["claude"] = (c["q"], c["calls"], f"""
<p>Evo usporedbe iz odluka i rasprava gradskih vijeća:</p>
<h4>Zagreb</h4>
<p>Skupština je 16. 9. 2026. donijela <b>{n} odluka o stipendijama</b> (izvrsnost, deficitarna zanimanja, učenici s
invaliditetom, socioekonomski status, romska manjina), sve s velikom većinom.</p>
<ul><li>stipendija za izvrsnost: <b>380 € mjesečno za učenike, 520 € za studente</b></li>
<li>prijave idu kroz sustav eStipendije, a natječaj za brucoše objavljuje se početkom listopada</li>
<li>broj stipendija za učenike i studente s invaliditetom narastao je s oko 100 na 170 <span class="ts">0:22:53</span></li></ul>
<h4>Rijeka</h4>
<p>Na sjednici 29. 10. 2026. rečeno je da su stipendije <b>udvostručene, na 300 i 400 €</b>, uz besplatan prijevoz za
srednjoškolce <span class="ts">3:24:46</span></p>
<p class="note">Zagreb je za studente izvrsnosti izdašniji. Iznos u Rijeci je iz rasprave, ne iz same odluke, pa ga provjeri u natječaju.</p>
<p class="src">Izvori: zapisnik 13. sjednice Gradske skupštine Zagreba · snimka 13. sjednice Gradskog vijeća Rijeke</p>""")

    c = by["gemini"]
    out["gemini"] = (c["q"], c["calls"], """
<p>Pretražio sam odluke i snimke sjednica u 36 gradova i općina. Novi vrtići otvaraju se ili grade ovdje:</p>
<ul><li><b>Split</b>: dva nova vrtića, <b>Splitsko sunce</b> i <b>Periska</b> (na dnevnom redu sjednice 12. 11. 2026.)</li>
<li><b>Zadar</b>: osnovan novi javni vrtić <b>Osmijeh</b> u Ulici Bartola Kašića (15 za, 6 protiv)</li>
<li><b>Kaštela</b>: osnovan novi vrtić <b>Kaštela 2</b> (17 za, nitko protiv)</li>
<li><b>Pula</b>: novi vrtić <b>Valmade</b></li>
<li><b>Ogulin</b>: kredit do 1,6 milijuna € za završetak nove zgrade vrtića <b>Bistrac</b></li>
<li><b>Slavonski Brod</b>: otvoren vrtić Varažić, nadograđuju se Kosinka i Pčelica <span class="ts">2:00:42</span></li>
<li><b>Velika Gorica</b>: „trenutačno smo na već 9. vrtiću u gradnji” <span class="ts">3:26:21</span></li></ul>
<p class="src">Izvori: zapisnici i dnevni redovi gradskih vijeća · snimke sjednica (Slavonski Brod, Velika Gorica)</p>""")
    return out


def args_of(c):
    return ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in c["args"].items() if v != "")


STREAM = """
const sleep = ms => new Promise(r => setTimeout(r, ms));
function words(el) {  // wrap every word of the answer in a hidden span, in reading order
  const out = [], walk = n => { for (const c of [...n.childNodes]) {
    if (c.nodeType === 3) { const f = document.createDocumentFragment();
      c.textContent.split(/(\\s+)/).forEach(w => { if (!w) return; if (/^\\s+$/.test(w)) { f.append(w); return; }
        const s = document.createElement('span'); s.className = 'w'; s.textContent = w; f.append(s); out.push(s); });
      c.replaceWith(f); }
    else { if (c.classList?.contains('ts')) { c.classList.add('w'); out.push(c); } else walk(c); } } };
  walk(el); return out; }
async function play() {
  const scroller = document.querySelector('.scroll'), down = () => scroller.scrollTop = scroller.scrollHeight;
  await sleep(300); document.querySelector('.you').classList.add('on'); down();
  for (const t of document.querySelectorAll('.tool')) { await sleep(650); t.classList.add('on'); down(); await sleep(550); t.classList.add('done'); }
  await sleep(300);
  const ans = document.querySelector('.ans'); ans.classList.add('on');
  const ws = words(ans);
  ans.querySelectorAll('li,p,h4').forEach(b => b.classList.add('pending'));
  for (const w of ws) { w.classList.add('on'); w.closest('.pending')?.classList.remove('pending'); down(); await sleep(26); }
}
"""
BASE = """*{box-sizing:border-box} html,body{margin:0;height:100%} body{display:flex;overflow:hidden}
.w{opacity:0;transition:opacity .25s} .w.on{opacity:1} .pending{display:none}
.you,.tool,.ans{display:none} .you.on,.tool.on,.ans.on{display:block} .tool.on{display:flex}
.label{position:fixed;right:18px;bottom:14px;font:500 13px system-ui;padding:5px 10px;border-radius:8px;z-index:9;opacity:.85}
.ts{font:600 .78em ui-monospace,Menlo,monospace;border-radius:6px;padding:1px 6px;margin-left:4px;white-space:nowrap}
.ts:before{content:"▶ "}
.tool>span{white-space:nowrap} .tool code{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
"""


def chatgpt(q, calls, ans):
    tools = "".join(f"<div class='tool'><span class='dot'></span><span>Pozvan alat <b>evijecnica</b> › {c['tool']}</span>"
                    f"<code>{html.escape(args_of(c))}</code><span class='ms'>{c['ms']} ms</span></div>" for c in calls)
    return f"""<!doctype html><meta charset="utf-8"><style>{BASE}
body{{background:#212121;color:#ececec;font:17px/1.65 ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}}
nav{{width:260px;background:#181818;padding:12px 10px;font-size:14.5px;color:#cfcfcf;flex:none}}
nav .row{{padding:8px 10px;border-radius:10px;display:flex;gap:10px;align-items:center}} nav .row.on{{background:#2a2a2a;color:#fff}}
nav .h{{color:#8f8f8f;font-size:13px;padding:18px 10px 6px}}
main{{flex:1;display:flex;flex-direction:column;min-width:0}}
header{{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 18px}}
header .m{{font-size:18px;font-weight:600;color:#ececec}} header .m span{{color:#9b9b9b;font-weight:400}}
header .sh{{border:1px solid #424242;border-radius:999px;padding:6px 14px;font-size:14px}}
.scroll{{flex:1;overflow:auto}} .col{{max-width:820px;margin:0 auto;padding:26px 24px 30px}}
.you.on{{margin-left:auto;width:fit-content;max-width:70%;background:#303030;border-radius:24px;padding:11px 20px;margin-bottom:26px}}
.tool{{gap:10px;align-items:center;color:#afafaf;font-size:15px;margin:4px 0}} .tool code{{color:#8f8f8f;font:13.5px ui-monospace,Menlo,monospace}}
.tool .ms{{color:#6f6f6f;font-size:13px}} .dot{{width:9px;height:9px;border-radius:50%;background:#afafaf;animation:p 1s infinite}}
.tool.done .dot{{animation:none;background:#10a37f}} @keyframes p{{50%{{opacity:.2}}}}
.ans{{margin-top:14px}} .ans p{{margin:0 0 14px}} .ans ul{{margin:0 0 14px;padding-left:24px}} .ans li{{margin:5px 0}}
.ans b{{color:#fff}} .src{{color:#9b9b9b;font-size:14.5px}} .ts{{background:#2f2f2f;color:#c9c9c9}}
.composer{{max-width:772px;width:calc(100% - 48px);margin:0 auto 10px;background:#303030;border-radius:28px;padding:16px 22px;color:#9b9b9b;display:flex;justify-content:space-between;align-items:center}}
.composer .t{{font-size:13.5px;border:1px solid #4a4a4a;border-radius:999px;padding:3px 12px;color:#cfcfcf}}
.foot{{text-align:center;color:#8f8f8f;font-size:12.5px;padding-bottom:12px}}
.label{{background:#303030;color:#cfcfcf}}</style>
<nav><div class="row on">✎ Novi razgovor</div><div class="row">⌕ Pretraži razgovore</div><div class="row">⚙ Konektori · evijecnica</div>
<div class="h">Razgovori</div><div class="row on">Liječnički pregled za sportaše</div><div class="row">Ideje za maturalac</div><div class="row">Zadatak iz fizike</div></nav>
<main><header><div class="m">ChatGPT <span>⌄</span></div><div class="sh">⇪ Podijeli</div></header>
<div class="scroll"><div class="col"><div class="you">{html.escape(q)}</div>{tools}<div class="ans">{ans}</div></div></div>
<div class="composer">Pitaj bilo što<span class="t">⚙ evijecnica</span></div><div class="foot">AI može pogriješiti. Provjeri važne informacije.</div></main>
<div class="label">{LABEL}</div><script>{STREAM}</script>"""


def claude(q, calls, ans):
    tools = "".join(f"<div class='tool'><span class='ic'>⚒</span><span><b>{c['tool']}</b> <span class='srv'>evijecnica</span></span>"
                    f"<code>{html.escape(args_of(c))}</code><span class='ms'>{c['ms']} ms ›</span></div>" for c in calls)
    return f"""<!doctype html><meta charset="utf-8"><style>{BASE}
body{{background:#faf9f5;color:#3d3929;font:17.5px/1.65 Georgia,"Times New Roman",serif}}
nav{{width:280px;background:#f5f4ee;border-right:1px solid #e8e6dc;padding:16px 12px;font:14.5px/1.4 -apple-system,system-ui,sans-serif;color:#3d3929;flex:none}}
nav .brand{{font:600 21px Georgia,serif;padding:4px 10px 18px}} nav .row{{padding:8px 10px;border-radius:8px}} nav .row.on{{background:#ebe9e0}}
nav .new{{color:#c96442;font-weight:600}} nav .h{{color:#83827d;font-size:12.5px;padding:18px 10px 6px}}
main{{flex:1;display:flex;flex-direction:column;min-width:0}}
header{{height:54px;display:flex;align-items:center;justify-content:center;font:500 15px -apple-system,system-ui,sans-serif;color:#3d3929;border-bottom:1px solid #efede5}}
.scroll{{flex:1;overflow:auto}} .col{{max-width:780px;margin:0 auto;padding:28px 24px 30px}}
.you.on{{display:flex;gap:12px;align-items:flex-start;width:fit-content;max-width:85%;background:#f0eee6;border-radius:14px;padding:12px 18px 12px 12px;margin-bottom:24px;font:16.5px/1.5 -apple-system,system-ui,sans-serif}}
.you:before{{content:"F";flex:none;width:28px;height:28px;border-radius:50%;background:#3d3929;color:#faf9f5;display:grid;place-items:center;font-size:13px;font-weight:700}}
.tool{{gap:10px;align-items:center;border:1px solid #e3e1d7;background:#fff;border-radius:10px;padding:9px 14px;margin:6px 0;font:14.5px -apple-system,system-ui,sans-serif;width:fit-content;max-width:100%}}
.tool .ic{{color:#c96442}} .tool .srv{{color:#83827d}} .tool code{{font:13px ui-monospace,Menlo,monospace;color:#6b5e45;background:#f5f4ee;padding:2px 6px;border-radius:5px}}
.tool .ms{{color:#a3a196;font-size:13px}} .tool:not(.done) .ic{{animation:p 1s infinite}} @keyframes p{{50%{{opacity:.2}}}}
.ans{{margin-top:16px}} .ans p{{margin:0 0 14px}} .ans ul{{margin:0 0 14px;padding-left:24px}} .ans li{{margin:5px 0}}
.ans h4{{font:600 17px -apple-system,system-ui,sans-serif;margin:16px 0 6px}} .note{{background:#f0eee6;border-radius:10px;padding:10px 14px;font-size:16px}}
.src{{color:#83827d;font:14.5px -apple-system,system-ui,sans-serif}} .ts{{background:#f0eee6;color:#6b5e45}}
.spark{{color:#d97757;font-size:26px;margin:10px 0 0}}
.composer{{max-width:732px;width:calc(100% - 48px);margin:0 auto 18px;background:#fff;border:1px solid #e3e1d7;border-radius:18px;padding:16px 18px 12px;color:#a3a196;font:16px -apple-system,system-ui,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,.04)}}
.composer .r{{display:flex;justify-content:space-between;margin-top:14px;font-size:13.5px;color:#83827d}} .composer .go{{background:#c96442;color:#fff;border-radius:9px;padding:3px 10px}}
.label{{background:#ebe9e0;color:#3d3929}}</style>
<nav><div class="brand">Claude</div><div class="row new">⊕ Novi razgovor</div><div class="row">⌕ Pretraži</div><div class="row">⚙ Konektori · evijecnica</div>
<div class="h">Nedavno</div><div class="row on">Stipendije Zagreb i Rijeka</div><div class="row">Esej o Krleži</div><div class="row">Plan učenja za maturu</div></nav>
<main><header>Stipendije Zagreb i Rijeka ⌄</header>
<div class="scroll"><div class="col"><div class="you">{html.escape(q)}</div>{tools}<div class="ans">{ans}</div><div class="spark">✳</div></div></div>
<div class="composer">Odgovori…<div class="r"><span>＋ &nbsp;⚙ evijecnica</span><span class="go">↑</span></div></div></main>
<div class="label">{LABEL}</div><script>{STREAM}</script>"""


def gemini(q, calls, ans):
    tools = "".join(f"<div class='tool'><span class='ic'></span><span>Korištenje alata <b>evijecnica.{c['tool']}</b></span>"
                    f"<code>{html.escape(args_of(c))}</code><span class='ms'>{c['ms']} ms</span></div>" for c in calls)
    star = ("<svg class='star' viewBox='0 0 24 24'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0' stop-color='#4c8df6'/><stop offset='.6' stop-color='#9b72cb'/><stop offset='1' stop-color='#d96570'/>"
            "</linearGradient></defs><path d='M12 1c.6 5.6 5.4 10.4 11 11-5.6.6-10.4 5.4-11 11-.6-5.6-5.4-10.4-11-11 5.6-.6 10.4-5.4 11-11z' fill='url(#g)'/></svg>")
    return f"""<!doctype html><meta charset="utf-8"><style>{BASE}
body{{background:#fff;color:#1f1f1f;font:17px/1.7 "Google Sans","Product Sans",-apple-system,system-ui,"Segoe UI",Roboto,sans-serif}}
nav{{width:72px;background:#f0f4f9;flex:none;display:flex;flex-direction:column;align-items:center;gap:22px;padding-top:22px;color:#444746;font-size:20px}}
main{{flex:1;display:flex;flex-direction:column;min-width:0}}
header{{height:62px;display:flex;align-items:center;justify-content:space-between;padding:0 22px}}
header .m{{font-size:21px;color:#1f1f1f}} header .m span{{font-size:14px;color:#444746;background:#f0f4f9;border-radius:999px;padding:3px 10px;margin-left:8px}}
header .av{{width:34px;height:34px;border-radius:50%;background:#1a73e8;color:#fff;display:grid;place-items:center;font-size:15px}}
.scroll{{flex:1;overflow:auto}} .col{{max-width:800px;margin:0 auto;padding:20px 24px 30px}}
.you.on{{margin-left:auto;width:fit-content;max-width:70%;background:#e9eef6;border-radius:22px 4px 22px 22px;padding:12px 20px;margin-bottom:26px}}
.row{{display:grid;grid-template-columns:40px 1fr;gap:12px}} .star{{width:30px;height:30px;margin-top:4px}}
.tool{{gap:10px;align-items:center;background:#f0f4f9;border-radius:999px;padding:7px 16px;margin:4px 0;font-size:14.5px;color:#444746;width:fit-content;max-width:100%}}
.tool code{{font:13px "Roboto Mono",ui-monospace,Menlo,monospace;color:#5f6368}} .tool .ms{{color:#80868b;font-size:13px}}
.tool .ic{{width:14px;height:14px;border-radius:50%;border:2px solid #4c8df6;border-right-color:transparent;animation:r .8s linear infinite}}
.tool.done .ic{{animation:none;border:0;background:#34a853}} @keyframes r{{to{{transform:rotate(1turn)}}}}
.ans{{margin-top:14px}} .ans p{{margin:0 0 14px}} .ans ul{{margin:0 0 14px;padding-left:24px}} .ans li{{margin:6px 0}}
.src{{color:#5f6368;font-size:14.5px}} .ts{{background:#e9eef6;color:#0b57d0}}
.composer{{max-width:752px;width:calc(100% - 48px);margin:0 auto 10px;background:#f0f4f9;border-radius:32px;padding:18px 24px;color:#5f6368;display:flex;justify-content:space-between}}
.composer .t{{font-size:14px;background:#fff;border-radius:999px;padding:2px 12px;color:#444746}}
.foot{{text-align:center;color:#5f6368;font-size:12.5px;padding-bottom:12px}}
.label{{background:#f0f4f9;color:#444746}}</style>
<nav><span>☰</span><span>✎</span><span>⚙</span></nav>
<main><header><div class="m">Gemini <span>⌄</span></div><div class="av">F</div></header>
<div class="scroll"><div class="col"><div class="you">{html.escape(q)}</div>
<div class="row">{star}<div>{tools}<div class="ans">{ans}</div></div></div></div></div>
<div class="composer">Pitaj Gemini<span class="t">⚙ evijecnica</span></div><div class="foot">AI može pogriješiti, pa provjeri odgovore.</div></main>
<div class="label">{LABEL}</div><script>{STREAM}</script>"""


def build():
    a = answers(json.loads((OUT / "mcp_calls.json").read_text()))
    for ui, fn in (("chatgpt", chatgpt), ("claude", claude), ("gemini", gemini)):
        (OUT / f"mcp_{ui}.html").write_text(fn(*a[ui]))
    return [OUT / f"mcp_{ui}.html" for ui in ("chatgpt", "claude", "gemini")]


if __name__ == "__main__":
    print(build())
