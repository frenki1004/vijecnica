"""Record demo conversations: six Croatian questions answered ONLY through the Vijećnica MCP server.

Every tool call goes over streamable HTTP to http://localhost:8103/mcp (the same endpoint an external agent
uses), and the tool name, arguments, call time and a trimmed copy of the JSON result are written to
demo/demo.json. The answers (answers_hr.json) were written by hand-reading those recorded results;
re-running this script refreshes the results, so check the answers still match before showing it.

Run: .venv/bin/python demo/record.py [--url http://localhost:8103/mcp]
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

HERE = Path(__file__).resolve().parent
URL = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://localhost:8103/mcp"


LONG = {"fonogram_answer": 1500, "draft": 1500, "quote": 600, "text": 520}  # fields the answers quote from


def cut(x, n=320, items=14, depth=0):
    """Generic trim: long strings shortened, long lists cut with a '+N more' marker."""
    if isinstance(x, str):
        return x if len(x) <= n else x[:n].rstrip() + "…"
    if isinstance(x, list):
        out = [cut(v, n, items, depth + 1) for v in x[:items]]
        if len(x) > items:
            out.append(f"… još {len(x) - items}")
        return out
    if isinstance(x, dict):
        return {k: cut(v, LONG.get(k, n), items, depth + 1) for k, v in x.items()}
    return x


def only(*keys):
    return lambda d: {k: d[k] for k in keys if k in d}


def answer_from(header):
    """get_question: keep the official answer part of the fonogram, starting at the answerer's header."""
    def f(d):
        out = {k: d[k] for k in ("id", "session", "member", "party", "question", "answered_by", "url")}
        fon = d.get("fonogram") or ""
        i = fon.find(header)
        out["fonogram_answer"] = " ".join(fon[i:].split())[:1400] if i >= 0 else None
        return out
    return f


def session_item(no):
    def f(d):
        keep = {k: d[k] for k in ("n", "date", "city", "held", "minutes_published", "days_without_minutes",
                                  "present_count", "attendance_note", "minutes_url") if k in d}
        keep["items"] = [i for i in d.get("items", []) if i["no"] == no]
        keep["items_total"] = len(d.get("items", []))
        return keep
    return f


def promise_rows(d):
    rows = d["promises"]
    by = {}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    return {"count": d["count"], "by_status": by,
            "followup_by_status": {s: sum(1 for r in rows if r["followup"]["status"] == s)
                                   for s in {r["followup"]["status"] for r in rows}},
            "promises": [{**{k: r[k] for k in ("id", "session", "said_on", "speaker", "asked_by", "quote", "deadline",
                                               "deadline_date", "status", "status_label")},
                          "followup": r["followup"]["label"], "followup_mentions": r["followup"]["mentions"]}
                         for r in rows]}


def debate(d):
    return {"title": d["title"], "recording": d["recording"], "speakers": d["speakers"],
            "governing": d.get("governing"),
            "blocks": [{k: b[k] for k in ("speaker", "party", "bloc", "kind", "at", "url", "text")} for b in d["blocks"]
                       if b["speaker"] or "Glasovanje je završeno" in b["text"]]}


def item_votes(d):
    out = {k: d[k] for k in ("city", "session", "no", "title", "proposer", "url", "verdict", "za", "protiv", "suzdrzano",
                             "result", "totals_note", "debate_starts", "vote_called", "snimka") if k in d}
    out["clubs"] = [{k: c[k] for k in ("short", "bloc", "size", "za", "protiv", "suzdrzan", "nije_glasovao", "odsutan")}
                    for c in d.get("clubs", [])]
    return out


def draft(d):
    return {"draft": d["draft"], "sources": d.get("sources"), "comparison": d.get("comparison"),
            "official_speakers": [s["name"] + (f" ({s['kind']})" if s["kind"] != "rasprava" else "")
                                  for s in (d.get("official") or {}).get("speakers", [])]}


# (id, persona, question, [(tool, args, trim)])
QUESTIONS = [
    ("sljeme", "građanka, Zagreb",
     "Kad će napokon proraditi nova sjedežnica na Sljemenu?",
     [("search", {"query": "sjedežnica Sljeme", "city": "zagreb", "limit": 5}, None),
      ("get_question", {"question_id": 156}, answer_from("LUKA KORLAET:")),
      ("promises", {"city": "zagreb", "session": 14, "speaker": "Korlaet"}, promise_rows)]),
    ("pregledi", "novinar",
     "Kako su klubovi glasali o Dritovu prijedlogu da Grad sufinancira zdravstvene preglede djece sportaša, "
     "i čime su protivnici obrazložili odbijanje?",
     [("search", {"query": "zdravstvenih pregleda sportaša", "city": "zagreb", "limit": 5}, None),
      ("get_item", {"session": 14, "item_no": 23, "city": "zagreb"}, item_votes),
      ("item_debate", {"session": 14, "item_no": 23, "city": "zagreb"}, debate),
      ("get_minutes", {"session": 14, "contains": "Sara Medved (u ime Kluba", "city": "zagreb"}, None)]),
    ("tomasevic", "građanin na društvenim mrežama",
     "Je li istina da gradonačelnik Tomašević ne ispunjava obećanja koja daje u Skupštini?",
     [("promises", {"city": "zagreb", "speaker": "Tomašević"}, promise_rows),
      ("promises", {"city": "zagreb", "speaker": "Tomašević", "status": "rok_prošao"}, promise_rows),
      ("promise_followup", {"promise_id": 24, "city": "zagreb"}, None),
      ("promise_followup", {"promise_id": 33, "city": "zagreb"}, None)]),
    ("brod-rebalans", "vijećnica iz Slavonskog Broda",
     "Je li Gradsko vijeće Slavonskog Broda u listopadu izglasalo rebalans proračuna za 2026. i s koliko glasova?",
     [("list_sessions", {"city": "brod"}, lambda d: d[:3]),
      ("get_session", {"session": 10, "city": "brod"}, session_item(7)),
      ("get_item", {"session": 10, "item_no": 7, "city": "brod"}, item_votes),
      ("get_item", {"session": 4, "item_no": 7, "city": "brod"}, item_votes),
      ("transcript_quality", {"city": "brod"}, lambda d: {k: d[k] for k in ("label", "agreement_pct", "wer", "cer_no_spaces",
                                                                           "words_compared", "votes", "votes_detail")})]),
    ("zapisnik", "službenica u stručnoj službi Skupštine",
     "Može li mi sustav napisati nacrt zapisnika za točku 23. sa 14. sjednice, i koliko mu smijem vjerovati?",
     [("draft_minutes", {"session": 14, "item_no": 23, "city": "zagreb"}, draft),
      ("minutes_evaluation", {"session": 14, "city": "zagreb"}, lambda d: {"summary": d["summary"]})]),
    ("ravlic", "novinarka lokalnog portala",
     "Kako je vijećnik Anto Ravlić glasao o rebalansu proračuna Slavonskog Broda u listopadu?",
     [("member_record", {"name": "Ravlić", "city": "brod"}, None),
      ("get_item", {"session": 10, "item_no": 7, "city": "brod"}, item_votes),
      ("speaker_turns", {"session": 10, "item_no": 7, "city": "brod"}, None)]),
]


def payload(res):
    if res.structured_content is not None:
        d = res.structured_content
        return d["result"] if set(d) == {"result"} else d
    text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
    try:
        return json.loads(text)
    except ValueError:
        return text


async def main():
    answers = json.loads((HERE / "answers_hr.json").read_text()) if (HERE / "answers_hr.json").exists() else {}
    out = {"recorded_at": datetime.now().isoformat(timespec="seconds"), "endpoint": URL,
           "transport": "MCP streamable HTTP (mcp Python SDK ClientSession)", "conversations": []}
    async with streamable_http_client(URL) as streams:
        async with ClientSession(streams[0], streams[1]) as s:
            init = await s.initialize()
            out["server"] = {"name": init.server_info.name, "version": init.server_info.version}
            out["tools_available"] = [t.name for t in (await s.list_tools()).tools]
            for qid, persona, question, calls in QUESTIONS:
                rec = []
                for tool, args, trim in calls:
                    t0 = time.perf_counter()
                    res = await s.call_tool(tool, args)
                    ms = round((time.perf_counter() - t0) * 1000)
                    data = payload(res)
                    full = len(json.dumps(data, ensure_ascii=False))
                    data = cut(trim(data) if trim else data)
                    rec.append({"tool": tool, "arguments": args, "ms": ms, "is_error": bool(res.is_error),
                                "result_chars": full, "result": data})
                a = answers.get(qid, {})
                out["conversations"].append({"id": qid, "persona": persona, "question": question, "calls": rec,
                                             "answer": a.get("answer"), "sources": a.get("sources", []),
                                             "limits": a.get("limits")})
    (HERE / "demo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"wrote {HERE / 'demo.json'}: {len(out['conversations'])} conversations, "
          f"{sum(len(c['calls']) for c in out['conversations'])} tool calls")


if __name__ == "__main__":
    asyncio.run(main())
