"""Burn demo.srt into a video, for players that ignore subtitle tracks (WhatsApp, e-mail previews).

This ffmpeg has no libass/drawtext, so every subtitle is drawn to a transparent PNG (Pillow) and laid over the
video with `overlay` for its time span.

Usage: uv run --with pillow python web/burn_subtitles.py [video.mp4] [out.mp4]
       default: deploy/demo_video/demo_clean.mp4 -> deploy/demo_video/demo_titlovi.mp4
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "deploy" / "demo_video"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
W, SIZE, PAD, BOTTOM = 1920, 44, 18, 60


def srt(path):
    sec = lambda t: (lambda h, m, s, ms: h * 3600 + m * 60 + s + ms / 1000)(*map(int, re.split(r"[:,]", t)))
    for block in path.read_text().strip().split("\n\n"):
        lines = block.splitlines()
        a, b = lines[1].split(" --> ")
        yield sec(a), sec(b), lines[2:]


def card(lines, out):
    """The subtitle as a dark rounded box with white text, centred, full video width (transparent around it)."""
    font = ImageFont.truetype(FONT, SIZE)
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [d.textlength(t, font=font) for t in lines]
    lh = int(SIZE * 1.3)
    bw, bh = int(max(widths)) + 2 * PAD + 16, lh * len(lines) + 2 * PAD - 6
    img = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (W - bw) // 2
    d.rounded_rectangle((x0, 0, x0 + bw, bh), radius=14, fill=(0, 0, 0, 200))
    for i, (t, w) in enumerate(zip(lines, widths)):
        d.text(((W - w) / 2, PAD - 4 + i * lh), t, font=font, fill="white")
    img.save(out)
    return bh


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DIR / "demo_clean.mp4"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else DIR / "demo_titlovi.mp4"
    subs = list(srt(DIR / "demo.srt"))
    with tempfile.TemporaryDirectory() as tmp:
        args, chain, prev = ["ffmpeg", "-v", "error", "-y", "-i", str(src)], [], "0:v"
        for i, (a, b, lines) in enumerate(subs, 1):
            h = card(lines, f"{tmp}/{i}.png")
            args += ["-i", f"{tmp}/{i}.png"]
            chain.append(f"[{prev}][{i}:v]overlay=0:H-{h}-{BOTTOM}:enable='between(t,{a:.3f},{b:.3f})'[v{i}]")
            prev = f"v{i}"
        args += ["-filter_complex", ";".join(chain), "-map", f"[{prev}]", "-map", "0:a?", "-c:v", "libx264",
                 "-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "copy",
                 str(dst)]
        subprocess.run(args, check=True)
    print(f"{len(subs)} subtitles burned -> {dst}")


if __name__ == "__main__":
    main()
