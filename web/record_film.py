"""Record web/film.html (the 3-minute video, reports/video_skripta_v2.md) to MP4, with the narration as subtitles.

Plays /film in Chromium at 1920x1080 (Playwright screen recording), then ffmpeg -> H.264 MP4. The subtitles are
both on screen (burned into the page) and written as an .srt file for YouTube. No audio: the voice-over is
recorded separately and laid under the video in an editor.

Usage: .venv/bin/python mcp_server.py --http 8103 (running), then
       uv run --with playwright python web/record_film.py [--url http://localhost:8103] [--out deploy/film]
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def srt(html, end=178.0):
    """SUBS = [[seconds, "text"], ...] from film.html -> SRT; a line lasts until the next one (or a scene change)."""
    block = re.search(r"const SUBS = (\[.*?\n\]);", html, re.S).group(1)
    subs = json.loads(re.sub(r",\s*\]$", "]", block.replace("\n", " ")))
    cuts = [15, 35, 85, 105, 135, 160, end]
    ts = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round(s % 1 * 1000)):03d}"
    out = []
    for i, (t, text) in enumerate(subs):
        nxt = min([subs[i + 1][0] if i + 1 < len(subs) else end] + [c for c in cuts if c > t])
        out.append(f"{i + 1}\n{ts(t)} --> {ts(nxt - 0.1)}\n{text}\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8103")
    ap.add_argument("--out", default=str(ROOT / "deploy" / "film"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "vijecnica.srt").write_text(srt((ROOT / "web" / "film.html").read_text()))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  record_video_dir=str(out / "raw"), record_video_size={"width": 1920, "height": 1080})
        page = ctx.new_page()
        t0 = time.monotonic()  # the recording starts with the page
        page.on("pageerror", lambda e: print("page error:", e))
        page.goto(f"{a.url}/film")
        page.wait_for_function("document.title === 'playing'", timeout=30_000, polling=20)
        lead = time.monotonic() - t0  # the film's clock starts once its fonts are loaded
        page.wait_for_function("document.title === 'done'", timeout=240_000, polling=1000)
        video = page.video.path()
        ctx.close()
        browser.close()
    # cut the lead-in, so the video's 0:00 is the film's 0:00 and the .srt lines up
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{lead:.2f}", "-i", video, "-t", "180", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(out / "vijecnica.mp4")], check=True)
    print(f"-> {out / 'vijecnica.mp4'}, {out / 'vijecnica.srt'}")


if __name__ == "__main__":
    main()
