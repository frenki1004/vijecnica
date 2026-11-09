"""Synthetic Croatian voice-over for the film (macOS `say`, voice Lana): one clip per subtitle line of web/film.html,
placed at the line's time and sped up (at most 1.6x) only when it would run into the next line or scene.

A stand-in until a person records the narration. Usage (after web/record_film.py):
    ../.venv/bin/python web/voice_film.py   ->  deploy/film/vijecnica_glas.mp4
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILM = ROOT / "deploy" / "film"
CUTS = [15, 35, 85, 105, 135, 160, 180]  # scene starts in web/film.html; a line never runs into the next scene


def main():
    html = (ROOT / "web" / "film.html").read_text()
    subs = json.loads(re.sub(r",\s*\]$", "]", re.search(r"const SUBS = (\[.*?\n\]);", html, re.S).group(1).replace("\n", " ")))
    voice = FILM / "voice"
    voice.mkdir(parents=True, exist_ok=True)
    inputs, filters = [], []
    for i, (t, text) in enumerate(subs):
        end = min([subs[i + 1][0] if i + 1 < len(subs) else 180] + [c for c in CUTS if c > t])
        clip = voice / f"{i:02d}.aiff"
        subprocess.run(["say", "-v", "Lana", "-r", "175", "-o", str(clip), re.sub(r"[„”]", "", text)], check=True)
        length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                       str(clip)], capture_output=True, text=True).stdout)
        tempo = max(1.0, min(1.6, length / (end - t - 0.15)))
        if tempo > 1.15:
            print(f"{t:6} sped up x{tempo:.2f}: {text[:70]}")
        inputs += ["-i", str(clip)]
        filters.append(f"[{i}:a]atempo={tempo:.3f},adelay={int(t * 1000)}|{int(t * 1000)}[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(subs))) + f"amix=inputs={len(subs)}:normalize=0,apad=whole_dur=180[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-t", "180", "-ar", "48000", str(voice / "voice.wav")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(FILM / "vijecnica.mp4"), "-i", str(voice / "voice.wav"),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(FILM / "vijecnica_glas.mp4")], check=True)
    print(f"-> {FILM / 'vijecnica_glas.mp4'}")


if __name__ == "__main__":
    main()
