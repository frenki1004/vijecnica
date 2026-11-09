"""Subtitles (.srt) for the narrated 3:00 demo video, from the narration in reports/demo_uzivo.md.

Every "## m:ss–m:ss" section's quoted narration (the "> „…”" lines) is cut into subtitles of at most two lines
(~42 characters each) at sentence and clause boundaries, and the section's time is shared among them in
proportion to their length, so the reader keeps pace with a calm speaker. Change the text in demo_uzivo.md and
run this again.

Usage: python web/subtitles.py  ->  deploy/demo_video/demo.srt
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reports" / "demo_uzivo.md"
OUT = ROOT / "deploy" / "demo_video" / "demo.srt"
LINE, GAP = 42, 0.15  # characters per line, seconds between subtitles


def sections():
    """[(start s, end s, narration text)] in the order of the script."""
    out, cur = [], None
    for line in SRC.read_text().splitlines():
        m = re.match(r"## (\d+):(\d\d)[–-](\d+):(\d\d)", line)
        if m:
            a, b, c, d = map(int, m.groups())
            cur = [a * 60 + b, c * 60 + d, []]
            out.append(cur)
        elif line.startswith("## ") or line.strip() == "---":
            cur = None
        elif cur and re.match(r"\s*> ", line):
            cur[2].append(re.sub(r"^\s*> ", "", line).strip())
    return [(a, b, re.sub(r"[„”]", "", " ".join(t))) for a, b, t in out if t]


def split(s):
    """A sentence longer than a subtitle: cut at the comma or colon nearest the middle, else at the middle word."""
    if len(s) <= 2 * LINE + 6:
        return [s]
    ok = [m.end() for m in re.finditer(r"[,:;]\s", s) if max(m.end(), len(s) - m.end()) <= 2 * LINE + 6]
    cuts = ok or [m.end() for m in re.finditer(r"\s", s)]
    k = min(cuts, key=lambda c: abs(c - len(s) / 2))
    return split(s[:k].strip()) + split(s[k:].strip())


def chunks(text):
    """Sentences, long ones cut at clauses; short neighbours joined when they fit on one subtitle."""
    out = []
    for sent in re.split(r"(?<=[.?!])\s+(?=[A-ZČĆŠŽĐ])", text):
        for piece in split(sent):
            whole = re.search(r"[.?!]$", piece) or not re.search(r"[.?!]$", out[-1]) if out else False  # no half sentences
            if out and whole and min(len(out[-1]), len(piece)) < 32 and len(out[-1]) + 1 + len(piece) <= 2 * LINE:
                out[-1] = f"{out[-1]} {piece}"
            else:
                out.append(piece)
    return out


def two_lines(t):
    """Break a subtitle into two balanced lines."""
    if len(t) <= LINE:
        return t
    words, best = t.split(), None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b)) - (10 if re.search(r"[.,:;?!]$", a) else 0)  # break after punctuation
        if len(a) > LINE + 8 or len(b) > LINE + 8:
            score += 100
        if best is None or score < best[0]:
            best = (score, a, b)
    return f"{best[1]}\n{best[2]}"


def ts(s):
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    subs = []
    for a, b, text in sections():
        parts = chunks(text)
        total = sum(len(p) for p in parts)
        t = a + 0.2
        span = b - a - 0.4
        for p in parts:
            d = span * len(p) / total
            subs.append((t, t + d - GAP, two_lines(p)))
            t += d
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(f"{i}\n{ts(s)} --> {ts(e)}\n{t}\n" for i, (s, e, t) in enumerate(subs, 1)))
    print(f"{len(subs)} subtitles -> {OUT}")


if __name__ == "__main__":
    main()
