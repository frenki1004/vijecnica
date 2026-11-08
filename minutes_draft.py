"""Rule-based draft of the minutes (zapisnik) paragraph for one agenda item, and its comparison with the
official minutes. Inputs: agenda item (title, proposer), roll-call vote totals, speaker turns detected in
the recording (speaker_turns) and the chair's spoken result. No LLM: every sentence comes from a template
in the council's own phrasing, so the draft can be checked line by line.

Used by mcp_server.py (tool draft_minutes, web view) and eval_minutes.py (evaluation report).
"""
import difflib
import json
import re
from collections import Counter

DEBATE_KINDS = ("rasprava", "u ime Kluba", "replika", "neslaganje s replikom", "povreda Poslovnika",
                "daje objašnjenje", "ispravak netočnog navoda")
NOTE = {"u ime Kluba": "u ime Kluba", "replika": "replika", "neslaganje s replikom": "neslaganje s replikom",
        "povreda Poslovnika": "povreda Poslovnika", "daje objašnjenje": "daje objašnjenje"}

# "Prijedlog odluke o …" -> what the assembly "donosi"
DOC = [(r"Prijedlog zagrebačke strategije\s+", "ZAGREBAČKU STRATEGIJU"),
       (r"Prijedlog izmjena i dopun[ae]\s+", "IZMJENE I DOPUNU"),
       (r"Prijedlog izmjena\s+", "IZMJENE"),
       (r"Prijedlog (?:odluke|Odluke)\s+", "ODLUKU"),
       (r"Prijedlog (?:zaključka|Zaključka)\s*", "ZAKLJUČAK"),
       (r"Prijedlog (?:rješenja|za imenovanje|za razrješenje)\s*", "RJEŠENJE"),
       (r"Prijedlog (?:programa|Programa)\s+", "PROGRAM"),
       (r"Prijedlog (?:plana|Plana)\s+", "PLAN"),
       (r"Prijedlog (?:polugodišnjeg|godišnjeg)\s+izvještaja\s+", "IZVJEŠTAJ")]
NOMINATIVE = {"ODLUKU": "Odluku", "ZAKLJUČAK": "Zaključak", "RJEŠENJE": "Rješenje", "IZMJENE": "Izmjene",
              "IZMJENE I DOPUNU": "Izmjene i dopunu", "ZAGREBAČKU STRATEGIJU": "Zagrebačku strategiju",
              "PROGRAM": "Program", "PLAN": "Plan", "IZVJEŠTAJ": "Izvještaj"}


def flat(s):
    return re.sub(r"\s+", " ", s or "").strip()


def join_hr(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " i " + xs[-1] if xs else ""


def doc_of(title):
    t = re.sub(r"^(?:[a-z]|\d{1,2})\)\s*", "", flat(title))  # "a) Prijedlog …", "01) Prijedlog …"
    t = re.split(r"(?<=[a-zčćžšđ0-9.])(?=[a-z]\)\s)", t)[0]  # Brod: several sub-titles glued together
    for pat, doc in DOC:
        m = re.match(pat, t)
        if m:
            rest = t[m.end():].strip()
            if rest.startswith("("):
                rest = rest  # "(o sufinanciranju …)" stays in parentheses
            return doc, rest
    return "ZAKLJUČAK", f"({t})"


def counts_text(za, protiv, sz):
    parts = [f'{za} "za"'] + ([f'{protiv} "protiv"'] if protiv else []) + ([f'{sz} "suzdržanih"'] if sz else [])
    return join_hr(parts)


def vote_sentences(it, assembly="Gradska skupština", members="gradskih zastupnika"):
    za, protiv, sz = it["za"], it["protiv"], it["suzdrzano"]
    if za is None:
        return [], None
    voted = za + protiv + sz
    mode = "jednoglasno" if not protiv and not sz else "većinom glasova"
    doc, rest = doc_of(it["title"])
    accepted = (it.get("result") or "").lower().find("nije") < 0 and (it.get("status") or "") != "odbijen"
    if accepted:
        verb = "donosi"
        line = f"{assembly} {mode} ({counts_text(za, protiv, sz)}) donosi\n\n{doc}\n{rest},\n\nu predloženom tekstu."
    else:
        verb = "nije donijela"
        line = f"{assembly} {mode} ({counts_text(za, protiv, sz)}) nije donijela {NOMINATIVE.get(doc, doc.title())} {rest}."
    return [f"Glasovalo je {voted} {members}.", line], {"voted": voted, "za": za, "protiv": protiv, "suzdrzano": sz,
                                                       "mode": mode, "verb": verb, "doc": doc}


def proposer_sentence(p):
    if not p:
        return None
    p = flat(p)
    if re.match(r"Gradonačelni", p):
        p = p[0].lower() + p[1:]
    return f"Predlagatelj je {p}."


def person(name, kind):
    note = NOTE.get(kind)
    return f"{name} ({note})" if note else name


def draft(db, city, session, no, sub=1):
    """Draft paragraph + the structured facts it was built from. db = sqlite3 connection (row_factory=Row)."""
    it = db.execute("SELECT * FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
                    (city, session, no, sub)).fetchone()
    if not it:
        return {"error": "no such item"}
    it = dict(it)
    turns = [dict(r) for r in db.execute("""SELECT start, end, speaker, role, kind, method, score, cue FROM speaker_turns
                                             WHERE city = ? AND session = ? AND item_no = ? AND sub = ? ORDER BY start""",
                                          (city, session, no, sub))]
    presenter = [t for t in turns if t["kind"] == "obrazlaže"]
    debate = [t for t in turns if t["kind"] in DEBATE_KINDS]
    closing = [t for t in turns if t["kind"] == "završna riječ"]
    lines = [f"{no}. {flat(it['title'])}", proposer_sentence(it["proposer"])]
    if presenter:
        lines.append(f"{presenter[0]['speaker']} obrazlaže Prijedlog.")
    # in time order: runs of debate turns become one "U raspravi sudjeluju" sentence, closing words in between
    run = []

    def flush():
        if run:
            ps = [person(t["speaker"], t["kind"]) for t in run]
            lines.append(("U raspravi sudjeluju: " if len(ps) > 1 else "U raspravi sudjeluje ") + join_hr(ps) + ".")
            run.clear()
    for t in turns:
        if t["kind"] in DEBATE_KINDS:
            run.append(t)
        elif t["kind"] == "završna riječ":
            flush()
            lines.append(f"{t['speaker']} daje završnu riječ.")
    flush()
    members = "gradskih zastupnika" if city == "zagreb" else "vijećnika"
    assembly = "Gradska skupština" if city == "zagreb" else "Gradsko vijeće"
    vs, vote = vote_sentences(it, assembly, members)
    lines += vs
    text = "\n\n".join(l for l in lines if l)
    return {"city": city, "session": session, "no": no, "sub": sub, "title": it["title"], "draft": text,
            "in_recording": it["t_start"] is not None, "spoken_result": it.get("spoken_result"),
            "presenter": presenter[0]["speaker"] if presenter else None,
            "speakers": [{"name": t["speaker"], "kind": t["kind"], "at": round(t["start"]), "method": t["method"]}
                         for t in debate],
            "closing": [t["speaker"] for t in closing], "vote": vote,
            "sources": "naslov i predlagatelj: dnevni red; glasovi: poimenični izvještaj glasovanja; "
                       "govornici: strojni transkript snimke (pozivi predsjedatelja)"}


def lcs(a, b):
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            m[i + 1][j + 1] = m[i][j] + 1 if a[i] == b[j] else max(m[i][j + 1], m[i + 1][j])
    return m[-1][-1]


def official(db, city, session, no, sub=1):
    r = db.execute("SELECT * FROM minutes_items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
                   (city, session, no, sub)).fetchone()
    if not r:
        return None
    r = dict(r)
    r["speakers"] = json.loads(r["speakers"] or "[]")
    r["closing"] = json.loads(r["closing"] or "[]")
    return r


def compare(d, off):
    """Metrics of one draft against the official minutes record."""
    gold = [s["name"] for s in off["speakers"]]
    pred = [s["name"] for s in d["speakers"]]
    g, p = Counter(gold), Counter(pred)
    tp_turns = sum((g & p).values())
    gk = Counter((s["name"], s["kind"]) for s in off["speakers"])
    pk = Counter((s["name"], s["kind"]) for s in d["speakers"])
    gs, ps = set(gold), set(pred)
    v, ov = d["vote"] or {}, off
    vote_fields = ("voted", "za", "protiv", "suzdrzano")
    vote_ok = bool(v) and all(v.get(k) == ov.get(k) for k in vote_fields)
    outcome_ok = bool(v) and ov.get("verb") is not None and (
        (v["verb"] == "nije donijela") == (ov["verb"] == "nije donijela"))
    off_doc = (re.match(r"[A-ZŠĐČĆŽ]{2,}(?:\s+(?:I|[A-ZŠĐČĆŽ]{2,}))*", ov.get("decision") or "") or [None])[0]
    common = [x for x in pred if x in gs]
    gold_common = [x for x in gold if x in ps]
    return {
        "gold_turns": len(gold), "pred_turns": len(pred), "turns_matched": tp_turns,
        "turns_matched_with_kind": sum((gk & pk).values()),
        "gold_speakers": len(gs), "pred_speakers": len(ps), "speakers_matched": len(gs & ps),
        "speaker_precision": round(len(gs & ps) / len(ps), 3) if ps else None,
        "speaker_recall": round(len(gs & ps) / len(gs), 3) if gs else None,
        "order_agreement": round(lcs(common, gold_common) / min(len(common), len(gold_common)), 3)
        if common and gold_common else None,
        "missed": sorted(gs - ps), "extra": sorted(ps - gs),
        "closing_ok": (set(d["closing"]) == set(off["closing"])) if (d["closing"] or off["closing"]) else None,
        "vote_exact": vote_ok, "outcome_ok": outcome_ok,
        "doc_ok": (off_doc or "").strip() == (v.get("doc") or "") if v and off_doc else None,
        "text_similarity": round(difflib.SequenceMatcher(None, flat(d["draft"]).lower(),
                                                         flat(off["text"]).lower()).ratio(), 3),
    }
