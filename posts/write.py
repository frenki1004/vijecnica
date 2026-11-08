"""Write post drafts from a queue with the Claude API: posts/writer_prompt.md is the system prompt, a batch of
queue elements is the user message, and the answer comes back as JSON in a fixed schema.

Every draft is checked before it is kept (the same rules the prompt states): lengths, allowed topics and
sides, no "usvojeno"/"prihvaćeno" in headlines, the caption ends with the element's source line, and no
number is given for a count that is null. A batch with problems is sent once more with the problems listed;
drafts that still fail are left out and reported. Ids already in any data/posts/drafts_*.json are skipped,
so a run can be repeated after an interruption.

Usage: .venv/bin/python posts/write.py data/posts/queue_osijek.json [--out drafts_osijek.json] [--batch 8]
       [--dry-run]   (print the first request instead of calling the API)
Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts"
PROMPT = ROOT / "posts" / "writer_prompt.md"
MODEL = "claude-opus-5-5"
TOPICS = ["promet", "stanovanje", "komunalno", "otpad", "okolis", "proracun", "porezi-i-naknade", "vrtici-i-skole",
          "mladi", "sport", "kultura", "socijala", "zdravstvo", "gospodarstvo", "prostorno-uredenje", "imenovanja",
          "gradska-uprava"]
SIDES = ["za", "protiv", "suzdrzani", "nepoznato"]
LIMITS = {"headline": 70, "summary": 280, "why_it_matters": 200, "caption": 600}

TEXT = {"type": "string"}
POST = {"type": "object", "additionalProperties": False,
        "required": ["id", "headline", "summary", "why_it_matters", "debate", "bullets", "topics", "caption", "notes"],
        "properties": {"id": TEXT, "headline": TEXT, "summary": TEXT, "why_it_matters": TEXT,
                       "debate": {"type": "array", "items": {
                           "type": "object", "additionalProperties": False, "required": ["side", "who", "point"],
                           "properties": {"side": {"type": "string", "enum": SIDES}, "who": TEXT, "point": TEXT}}},
                       "bullets": {"type": "array", "items": TEXT},
                       "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}},
                       "caption": TEXT, "notes": TEXT}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["posts"],
          "properties": {"posts": {"type": "array", "items": POST}}}
# the JSON schema has no nulls: an empty string stands for null, and item posts leave "bullets" empty
FORMAT_NOTE = ("Odgovor je JSON prema zadanoj shemi. Prazan niz znakova znači null (npr. why_it_matters kad izvor to "
               "ne podupire). Za kind \"item\" polje bullets ostaje prazno, a za kind \"digest\" summary i "
               "why_it_matters ostaju prazni.")


def problems(el, d):
    """Rule violations of one draft against its queue element, as short Croatian sentences."""
    out = []
    if d["id"] != el["id"]:
        out.append(f"id mora biti {el['id']}")
    for field, n in LIMITS.items():
        limit = 400 if field == "caption" and el["kind"] == "digest" else n
        if len(d.get(field) or "") > limit:
            out.append(f"{field} je dulji od {limit} znakova")
    if re.search(r"usvoj|prihvać", d["headline"], re.I):
        out.append("naslov ne smije sadržavati „usvojeno” ni „prihvaćeno”")
    if not d["caption"].rstrip().endswith(el["source"]):
        out.append(f"caption mora završiti retkom: {el['source']}")
    if any(len(e["point"]) > 160 for e in d["debate"]) or any(len(b) > 90 for b in d["bullets"]):
        out.append("debate.point je dulji od 160 ili bullet od 90 znakova")
    text = " ".join([d["headline"], d["summary"], d["why_it_matters"], d["caption"]])
    for key, word in (("protiv", "protiv"), ("suzdrzano", "suzdrž")):
        if el.get(key) is None and el["kind"] == "item" and re.search(rf"\b\d+\s+(?:glas\w*\s+)?{word}", text, re.I):
            out.append(f"broj „{key}” nije poznat, ne smije se navesti")
    if el["kind"] == "item" and el.get("protiv") != 0:  # a digest holds only unanimous decisions
        if re.search(r"nitko (?:nije bio |nije glasovao )?protiv|bez (?:ijednog )?glas\w* protiv", text, re.I):
            out.append("ne smije pisati da nitko nije bio protiv")
    return out


def draft(d, el):
    """The drafts_*.json shape posts/assemble.py reads."""
    out = {k: d[k] for k in ("id", "headline", "topics", "caption", "notes")}
    if el["kind"] == "digest":
        out["bullets"] = d["bullets"]
    else:
        out |= {"summary": d["summary"], "why_it_matters": d["why_it_matters"] or None, "debate": d["debate"]}
    return out


def request(system, batch, fix=None):
    user = json.dumps(batch, ensure_ascii=False, indent=1)
    if fix:
        user += "\n\nPrethodni odgovor imao je ove probleme, ispravi ih:\n" + "\n".join(f"- {f}" for f in fix)
    # refused requests are re-run server-side on a fallback model chosen by refusal category
    return {"model": MODEL, "max_tokens": 64000, "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default",
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": user}]}


def call(client, params):
    with client.beta.messages.stream(**params) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"odbijeno ({msg.stop_details.category if msg.stop_details else '?'})")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("odgovor prekinut (max_tokens), smanji --batch")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))["posts"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queue")
    ap.add_argument("--out")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    queue = json.loads(Path(a.queue).read_text())
    out = POSTS / (a.out or "drafts_" + Path(a.queue).stem.removeprefix("queue_") + ".json")
    done = {d["id"] for f in POSTS.glob("drafts_*.json") for d in json.loads(f.read_text())}
    todo = [el for el in queue if el["id"] not in done]
    system = PROMPT.read_text() + "\n\n" + FORMAT_NOTE
    if a.dry_run:
        print(json.dumps(request(system, todo[:a.batch]), ensure_ascii=False, indent=1)[:4000])
        return
    client = anthropic.Anthropic()
    drafts = json.loads(out.read_text()) if out.exists() else []
    failed = []
    for i in range(0, len(todo), a.batch):
        batch = todo[i:i + a.batch]
        try:
            got = {d["id"]: d for d in call(client, request(system, batch))}
            bad = {el["id"]: problems(el, got[el["id"]]) if el["id"] in got else ["nedostaje"] for el in batch}
            redo = [el for el in batch if bad[el["id"]]]
            if redo:  # one more try for the drafts that broke a rule, with the problems listed
                fix = [f"{el['id']}: {p}" for el in redo for p in bad[el["id"]]]
                got |= {d["id"]: d for d in call(client, request(system, redo, fix))}
                bad = {el["id"]: problems(el, got[el["id"]]) if el["id"] in got else ["nedostaje"] for el in batch}
        except (anthropic.APIError, RuntimeError, json.JSONDecodeError, StopIteration) as e:
            failed += [(el["id"], str(e)) for el in batch]
            continue
        for el in batch:
            if bad[el["id"]]:
                failed.append((el["id"], "; ".join(bad[el["id"]])))
            else:
                drafts.append(draft(got[el["id"]], el))
        out.write_text(json.dumps(drafts, ensure_ascii=False, indent=1))  # after every batch: resumable
        print(f"{min(i + a.batch, len(todo))}/{len(todo)}", file=sys.stderr)
    print(f"{len(drafts)} drafts -> {out}" + (f"; {len(failed)} left out:" if failed else ""), file=sys.stderr)
    for pid, why in failed:
        print(f"  {pid}: {why}", file=sys.stderr)


if __name__ == "__main__":
    main()
