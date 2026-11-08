"""Slavonski Brod: how good are the ASR, the speaker turns and the spoken vote results, measured against the
near-verbatim official minutes of the same session.

  python3 eval_brod.py --session 9      -> reports/asr_eval_brod_9.json

1. WER: transcript and minutes are normalised (lowercase, no diacritics, no punctuation). The transcript is
   cut into 120-word windows; each window is placed in the minutes by shared 4-grams and aligned with difflib.
   Windows whose speech the minutes quote (>= 50 % of words matched) are scored with word-level edit distance
   against the aligned minutes passage. WER = edits / reference words over those windows.
2. Speakers: the minutes name the speaker before each passage ("Vijećnica Slavica Lemaić: …" / "… vijećnik X
   rekao je"). For every matched window the last councillor named in the minutes before the passage is the
   gold speaker; our speaker_turns at that second are the prediction. Recall = gold windows we name correctly,
   precision = windows we name that are correct.
3. Votes: spoken_votes (source='snimka') vs the totals from the minutes, per item.
Until the session has a transcript, it says so and exits 0. `--partial` uses the transcript that is still
being written (`brod-NN-1.partial.json`, segments only, not in the DB): WER + passages on whatever is done, and
speaker turns detected in memory (db/speakers.py, same rules as the build). Output gets "partial": true.
"""
import argparse
import difflib
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "vijecnica.db"
WIN = 120


def norm_words(text):
    t = unicodedata.normalize("NFKD", text.replace("đ", "dj").replace("Đ", "Dj"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z0-9]+", t)


def edit_distance(ref, hyp):
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def place(window, ref, index):
    """Best start in ref for a transcript window, by votes of shared 4-grams (offset-consistent)."""
    votes = defaultdict(int)
    for i in range(len(window) - 3):
        for p in index.get(tuple(window[i:i + 4]), ())[:50]:
            votes[(p - i) // 20] += 1
    if not votes:
        return None
    b, n = max(votes.items(), key=lambda x: x[1])
    return max(0, b * 20 - 20) if n >= 2 else None


def wer_eval(segs, minutes):
    """segs = [(start, text)]; returns (summary, matched windows [(t, ref_start, ref_end, words)])."""
    ref = norm_words(minutes)
    index = defaultdict(list)
    for i in range(len(ref) - 3):
        index[tuple(ref[i:i + 4])].append(i)
    hyp, times = [], []
    for start, text in segs:
        for w in norm_words(text):
            hyp.append(w)
            times.append(start)
    edits = refw = hypw = cedits = cref = 0
    matched, per = [], []
    for k in range(0, len(hyp) - WIN + 1, WIN):
        win = hyp[k:k + WIN]
        p = place(win, ref, index)
        if p is None:
            continue
        cand = ref[p:p + int(WIN * 1.6) + 40]
        sm = difflib.SequenceMatcher(None, win, cand, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        if not blocks or sum(b.size for b in blocks) / len(win) < 0.5:
            continue
        r0, r1 = blocks[0].b, blocks[-1].b + blocks[-1].size
        h0, h1 = blocks[0].a, blocks[-1].a + blocks[-1].size
        r, h = cand[r0:r1], win[h0:h1]
        e = edit_distance(r, h)
        # CER on the same passage with spaces removed: "na zalost" vs "nazalost" is not an ASR error
        rc, hc = "".join(r), "".join(h)
        cedits += edit_distance(rc, hc)
        cref += len(rc)
        per.append(e / len(r) if r else 1.0)
        edits += e
        refw += len(r)
        hypw += len(h)
        matched.append((times[k + h0], p + r0, p + r1, len(r), h, r))
    per.sort()
    return {"windows_total": len(hyp) // WIN, "windows_matched": len(matched), "aligned_ref_words": refw,
            "aligned_hyp_words": hypw, "edits": edits, "wer": round(edits / refw, 3) if refw else None,
            "median_window_wer": round(per[len(per) // 2], 3) if per else None,
            "cer_no_spaces": round(cedits / cref, 3) if cref else None,
            "windows_wer_below_0_25": sum(x < 0.25 for x in per),
            "unmatched_words": (len(hyp) // WIN - len(matched)) * WIN}, matched, ref


def speaker_eval(db, city, session, minutes, ref, matched, roster, turns_override=None):
    """Gold = last roster surname mentioned in the minutes within 400 words before the passage."""
    surname = {}
    for full in roster:
        for tok in norm_words(full)[1:] or norm_words(full):
            if len(tok) >= 4:
                surname[tok[:-1] if len(tok) > 5 else tok] = full  # stem: Lemaica/Lemaicu
    pos_names = [(i, surname[k]) for i, w in enumerate(ref) for k in surname if w.startswith(k)]
    turns = turns_override if turns_override is not None else db.execute(
        "SELECT start, end, speaker FROM speaker_turns WHERE city = ? AND session = ?", (city, session)).fetchall()
    gold_n = pred_n = correct = 0
    rows = []
    for t, r0, *_ in matched:
        gold = next((n for i, n in reversed(pos_names) if r0 - 400 <= i <= r0), None)
        pred = next((s for a, b, s in turns if a <= t < b), None)
        gold_n += gold is not None
        pred_n += pred is not None
        correct += gold is not None and gold == pred
        rows.append({"t": round(t), "gold": gold, "pred": pred})
    return {"windows_with_gold": gold_n, "windows_with_prediction": pred_n, "correct": correct,
            "recall": round(correct / gold_n, 3) if gold_n else None,
            "precision": round(correct / pred_n, 3) if pred_n else None, "sample": rows[:40]}


def vote_eval(db, city, session):
    """Spoken totals vs the minutes' totals per item (docs JSON keeps every vote of an item)."""
    f = ROOT / "data" / "brod" / "docs" / f"session_{session:02d}.json"
    gold = {}
    if f.exists():
        for it in json.loads(f.read_text())["items"]:
            vs = it.get("votes") or ([it["vote"]] if it.get("vote") else [])
            if vs:
                gold[it["no"]] = [(v.get("za"), v.get("protiv") or 0, v.get("suzdrzano") or 0) for v in vs]
    spoken = defaultdict(list)
    for no, za, pr, sz in db.execute("SELECT item_no, za, protiv, suzdrzano FROM spoken_votes WHERE city = ? AND"
                                     " session = ? ORDER BY item_no, n", (city, session)):
        spoken[no].append((za, pr or 0, sz or 0))
    both = sorted(set(gold) & set(spoken))
    exact = [no for no in both if spoken[no][-1] == gold[no][-1] or set(spoken[no]) & set(gold[no])]
    numbered = [no for no in both if any(v[0] is not None for v in spoken[no])]
    ex_num = [no for no in numbered if no in exact]
    return {"items_with_minutes_vote": len(gold), "items_with_spoken_vote": len(spoken), "compared": len(both),
            "exact": len(exact), "exact_pct": round(100 * len(exact) / len(both), 1) if both else None,
            "with_number": len(numbered), "exact_of_numbered": f"{len(ex_num)}/{len(numbered)}",
            "without_number": [no for no in both if no not in numbered],
            "missing_in_recording": sorted(set(gold) - set(spoken)),
            "mismatches": [{"item": no, "spoken": spoken[no], "minutes": gold[no]} for no in both if no not in exact]}


def passages(matched, k=5):
    """A few aligned passages, side by side, with their own WER (the 'show me' part)."""
    out = []
    step = max(1, len(matched) // k)
    for t, r0, r1, n, h, r in matched[::step][:k]:
        out.append({"t": round(t), "wer": round(edit_distance(r, h) / len(r), 3) if r else None,
                    "transcript": " ".join(h[:40]), "minutes": " ".join(r[:40])})
    return out


def partial_turns(segs, roster_names, db):
    sys.path.insert(0, str(ROOT / "db"))
    from speakers import Roster, detect
    import derive
    ex = derive.EXECUTIVE["brod"]
    people = {**{v: "dužnosnik" for v in ex.values() if v}, **{n: "vijećnik" for n in roster_names}}
    return [(x["start"], x["end"], x["speaker"]) for x in
            detect(segs, Roster(people), ex["mayor"], ex["deputy_f"], ex["deputy_m"], "brod")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=9)
    ap.add_argument("--partial", action="store_true", help="use brod-NN-1.partial.json if no final transcript")
    a = ap.parse_args()
    city, n = "brod", a.session
    tdir = ROOT / "data" / "brod" / "transcripts"
    found = [f for f in list(tdir.glob(f"brod-{n}-*.json")) + list(tdir.glob(f"brod-{n:02d}-*.json"))
             if not f.name.endswith(".partial.json")]
    partial = sorted(tdir.glob(f"brod-{n:02d}-*.partial.json"))
    if not found and not (a.partial and partial):
        print(f"brod {n}: nema transkripta, nema preklapanja" + (" (djelomični postoji: --partial)" if partial else ""))
        return 0
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    minutes = (db.execute("SELECT minutes_text FROM sessions WHERE city = ? AND n = ?", (city, n)).fetchone() or [""])[0]
    turns = None
    if found:
        segs = db.execute("SELECT s.start, s.text FROM segments s JOIN videos v ON v.id = s.video_id WHERE s.city = ? AND"
                          " s.session = ? ORDER BY v.part, s.start", (city, n)).fetchall()
    else:
        raw = json.loads(partial[0].read_text())["segments"]
        segs = [(x["start"], x["text"]) for x in raw]
        names = [r[0] for r in db.execute("SELECT name FROM members WHERE city = ?", (city,))]
        turns = partial_turns([(x["start"], x["end"], x["text"]) for x in raw], names, db)
    if not minutes or not segs:
        print(f"brod {n}: nema transkripta u bazi ili nema zapisnika, nema preklapanja (pokreni db/build.py)")
        return 0
    roster = [r[0] for r in db.execute("SELECT name FROM members WHERE city = ?", (city,))]
    wer, matched, ref = wer_eval(segs, minutes)
    method = ("Transkript i zapisnik normalizirani su (mala slova, bez dijakritika i interpunkcije). Transkript je "
              f"izrezan u odlomke od {WIN} riječi; svaki se smješta u zapisnik po zajedničkim nizovima od 4 riječi i "
              "poravnava (difflib). Odlomci kojima zapisnik prenosi ≥ 50 % riječi ocjenjuju se Levenshteinovom "
              "udaljenošću na razini riječi: WER = (zamjene + umetanja + brisanja) / riječi zapisnika; slaganje = 1 − WER. "
              "Zapisnik je uređen (gramatika, izostavljene poštapalice), pa je ovo gornja granica stvarne pogreške ASR-a. "
              "Odlomke koje zapisnik ne prenosi (predsjedatelj, stanke) mjera ne vidi. Dodatno: CER = ista udaljenost po "
              "slovima bez razmaka (\"na zalost\" = \"nazalost\").")
    out = {"city": city, "session": n, "partial": not found, "method": method,
           "transcript_minutes": round(max(t for t, _ in segs) / 60, 1), "asr": wer,
           "passages": passages(matched),
           "speakers": speaker_eval(db, city, n, minutes, ref, matched, roster, turns),
           "votes": vote_eval(db, city, n)}
    path = ROOT / "reports" / f"asr_eval_brod_{n}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: (v if k != "speakers" else {x: y for x, y in v.items() if x != "sample"}) if k != "passages" else v[:3]
                      for k, v in out.items()}, ensure_ascii=False, indent=1))
    print("->", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
