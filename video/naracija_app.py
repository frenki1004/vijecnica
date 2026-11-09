"""Narration recorder for the 3:00 demo video, with your own voice (tool by Lovro Blagić, eSidro, adapted).

Scenes and their text come from reports/demo_uzivo.md: every "## m:ss–m:ss" section is a scene; a section whose
steps carry their own length ("1. **…** (10 s)") with a quote each is split into one scene per step. The page
plays deploy/demo_video/demo_clean.mp4 under each scene, shows the text with a pace marker, records the scene,
and exports one naracija.wav aligned with the video.

    python3 video/naracija_app.py                 ->  deploy/demo_video/naracija.html
    cd deploy/demo_video && npx http-server -p 8765 -s   ->  http://localhost:8765/naracija.html
    (the microphone works only on localhost or https; python -m http.server cannot seek the video)
    video/dodaj_naraciju.sh ~/Downloads/naracija.wav      ->  demo_naracija.mp4 (+ _titlovi with subtitles)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "deploy" / "demo_video" / "naracija.html"
TOTAL = 180.0


def quote(lines):
    return re.sub(r"[„”]", "", " ".join(re.sub(r"^\s*> ", "", x).strip() for x in lines)).strip()


def scenes():
    out, sec = [], None
    for line in (ROOT / "reports" / "demo_uzivo.md").read_text().splitlines():
        m = re.match(r"## (\d+):(\d\d)[–-](\d+):(\d\d) (.+?)(?: \(|$)", line)
        if m:
            a, b, c, d, title = m.groups()
            sec = {"start": int(a) * 60 + int(b), "end": int(c) * 60 + int(d), "title": title.strip(), "steps": [], "q": []}
            out.append(sec)
        elif line.startswith("## ") or line.strip() == "---":
            sec = None
        elif sec is not None:
            st = re.match(r"\d+\. \*\*(.+?)\*\* \((\d+) s\)", line)
            if st:
                sec["steps"].append({"title": st.group(1), "dur": int(st.group(2)), "q": []})
            elif re.match(r"\s*> ", line):
                (sec["steps"][-1]["q"] if sec["steps"] else sec["q"]).append(line)
                sec.setdefault("all", []).append(line)
    res = []
    for k, s in enumerate(out):
        if s["steps"] and all(x["q"] for x in s["steps"]):
            t = s["start"]
            for j, x in enumerate(s["steps"]):
                res.append({"id": f"s{k}_{j}", "title": f"{s['title'].split(':')[0]}: {x['title']}", "chapter": s["title"],
                            "start": t, "dur": x["dur"], "text": quote(x["q"])})
                t += x["dur"]
        elif s.get("all"):  # one scene for the section (steps without a quote each)
            res.append({"id": f"s{k}", "title": s["title"].split(",")[0], "chapter": s["title"], "start": s["start"],
                        "dur": s["end"] - s["start"], "text": quote(s["all"])})
    return res


def main():
    data = {"total": TOTAL, "scenes": scenes()}
    tpl = (Path(__file__).parent / "naracija_template.html").read_text()
    OUT.write_text(tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    for s in data["scenes"]:
        print(f"{s['start']:>5} +{s['dur']:<3} {s['title'][:40]:40} {len(s['text'].split())} riječi")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
