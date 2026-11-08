"""Parse the official Zagreb minutes (zapisnik) into one record per agenda item.

The body of a Zagreb zapisnik repeats the agenda: "10. Prijedlog …" then fixed sentences:
"Predlagatelj je …", "X, izvjestitelj … obrazlaže Prijedlog.", "U raspravi sudjeluju: A (u ime Kluba …),
B, C (replika) i D (neslaganje s replikom).", "X daje završnu riječ.", "Glasovalo je N gradskih
zastupnika.", "Gradska skupština većinom glasova (24 "za" i 13 "protiv") donosi ODLUKU …".
Items holding several decisions ("01) … 02) …") get one record per sub; votes are matched by order.
Brod minutes are free prose (no speaker lists), so only Zagreb is parsed for now.
"""
import re

HEAD = re.compile(r"\n[ \t]*(\d{1,2})\.[ \t]+(?=[A-ZŠĐČĆŽ0-9\"„])")
KINDS = [("neslaganje", "neslaganje s replikom"), ("replik", "replika"), ("u ime", "u ime Kluba"),
         ("povreda", "povreda Poslovnika"), ("objašnjenje", "daje objašnjenje"), ("ispravak", "ispravak netočnog navoda")]
VOTE = re.compile(r"Glasovalo je (\d+) gradsk\w+ zastupnik\w*\.\s*Gradska skupština\s+(jednoglasno|većinom glasova)\s*"
                  r"\(([^)]*)\)\s*(nije donijela|donosi|prihvaća|odobrava|daje|utvrđuje|bira|imenuje|\w+)", re.S)


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def kind_of(note):
    note = (note or "").lower()
    for k, v in KINDS:
        if k in note:
            return v
    return "rasprava"


def split_people(s):
    """'A (u ime Kluba X), B, C (replika) i D' -> [(name, note)], splitting only outside parentheses."""
    parts, cur, depth = [], "", 0
    i = 0
    while i < len(s):
        c = s[i]
        depth += (c == "(") - (c == ")")
        if depth == 0 and (s.startswith(", ", i) or s.startswith(" i ", i)):
            parts.append(cur)
            cur = ""
            i += 2 if s.startswith(", ", i) else 3
            continue
        cur += c
        i += 1
    parts.append(cur)
    out = []
    for p in parts:
        m = re.match(r"\s*([^()]+?)\s*(?:\((.*)\))?\s*$", p)
        if m and m.group(1):
            out.append((m.group(1).strip(), (m.group(2) or "").strip()))
    return out


def speaker_lists(text):
    """Every 'U raspravi sudjeluje/sudjeluju: …' sentence in order -> [{'name', 'kind', 'note'}]."""
    out = []
    for m in re.finditer(r"U raspravi sudjeluj[eu]:?\s*", text):
        s, depth, j = text[m.end():], 0, 0
        while j < len(s):
            depth += (s[j] == "(") - (s[j] == ")")
            if s[j] == "." and depth == 0 and (j + 1 == len(s) or s[j + 1].isspace()):
                break
            j += 1
        for name, note in split_people(flat(s[:j])):
            out.append({"name": name, "kind": kind_of(note), "note": note})
    return out


def person_before(sentence, verb, roster=()):
    """'Sara Medved, izvjestiteljica u ime … obrazlaže' / 'Zamjenica gradonačelnika … Danijela Dolenec daje završnu riječ'.
    Known names (roster) win; otherwise the last two capitalised words before the verb or the first comma."""
    s = flat(sentence)
    s = s[:s.find(verb)] if verb in s else s
    hits = [(s.rfind(n), n) for n in roster if n in s]
    if hits:
        return max(hits)[1]
    if "," in s:
        s = s.split(",")[0]
    caps = re.findall(r"[A-ZŠĐČĆŽ][\wšđčćž-]+", s)
    return " ".join(caps[-2:]) if len(caps) >= 2 else None


def para_before(text, pos):
    """The paragraph text from the last blank line before pos up to pos."""
    starts = [m.end() for m in re.finditer(r"\n\s*\n", text[:pos])]
    return text[(starts[-1] if starts else 0):pos]


def votes(text):
    out = []
    for m in VOTE.finditer(text):
        counts = {k: 0 for k in ("za", "protiv", "suzdrzano")}
        for n, w in re.findall(r"(\d+)\s*\"?\s*(za|protiv|suzdrž\w*)", m.group(3)):
            counts["suzdrzano" if w.startswith("suzdr") else w] = int(n)
        tail = flat(text[m.end(4):m.end(4) + 400])
        tail = re.split(r"u predloženom tekstu|,\s*u predloženim|\.\s+[A-Z]", tail)[0].strip(" ,.")
        out.append({"voted": int(m.group(1)), "mode": m.group(2), **counts, "verb": m.group(4), "decision": tail})
    return out


def parse_zagreb(text, items, roster=()):
    """items = [(no, sub, title)] from the DB -> list of per-item dicts."""
    if not text:
        return []
    heads = [(m.start(), int(m.group(1))) for m in HEAD.finditer(text)]
    # the body is the last run 1, 2, 3, … (the agenda list near the top is an earlier run)
    best = []
    for k, (pos, n) in enumerate(heads):
        if n != 1:
            continue
        chain, want = [(pos, 1)], 2
        for p2, n2 in heads[k + 1:]:
            if n2 == want:
                chain.append((p2, n2))
                want += 1
        if len(chain) >= len(best):
            best = chain
    subs = {}
    for no, sub, title in items:
        subs.setdefault(no, []).append((sub, title))
    out = []
    for i, (pos, n) in enumerate(best):
        end = best[i + 1][0] if i + 1 < len(best) else len(text)
        sec = text[pos:end]
        sec = re.split(r"\n\s*(?:Završeno|Sjednica je završ|Dovršeno)", sec)[0]
        props = [flat(m.group(1)) for m in re.finditer(r"(?:Predlagatelj je|je podni\w+) (.+?)\.\s*\n", sec, re.S)]
        pres = [person_before(para_before(sec, m.start()), "obrazlaže", roster) for m in re.finditer("obrazlaže", sec)]
        clos = [person_before(para_before(sec, m.start()), "daje", roster)
                for m in re.finditer(r"daje\s+završnu\s+riječ", sec)]
        spk = speaker_lists(sec)
        vs = votes(sec)
        mine = subs.get(n, [(1, None)])
        for j, (sub, title) in enumerate(mine):
            v = vs[j] if len(vs) == len(mine) else (vs[0] if vs and len(mine) == 1 else {})
            out.append({"no": n, "sub": sub, "title": title, "text": sec.strip(),
                        "proposer": props[min(j, len(props) - 1)] if props else None,
                        "presenter": pres[0] if pres else None, "closing": clos,
                        "speakers": spk if j == 0 else (spk if len(mine) > 1 and not vs else []),
                        **{k: v.get(k) for k in ("voted", "za", "protiv", "suzdrzano", "mode", "verb", "decision")}})
    return out


def others_present(text):
    """Names from 'Drugi nazočni: A, titula - funkcija; B - …' (officials who may speak)."""
    m = re.search(r"Drugi nazočni:(.+?)\n\s*\n", text or "", re.S)
    if not m:
        return []
    names = []
    for chunk in flat(m.group(1)).split(";"):
        for part in re.split(r"\s+i\s+(?=(?:dr\. sc\.|mr\. sc\.)?\s*[A-ZŠĐČĆŽ])", chunk.split(" - ")[0]):
            part = re.sub(r"\b(dr|mr|sc|techn|izv|prof)\.\s*", "", part).split(",")[0]
            w = re.findall(r"[A-ZŠĐČĆŽ][\wšđčćžŠĐČĆŽ-]+", part)
            if len(w) >= 2:
                names.append(" ".join(w))
    return names
