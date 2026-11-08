"""Vijećnica MCP server: ask Croatian city councils what they decided, said and voted, 2025-2029 term.

Cities: 'zagreb' (Gradska skupština Grada Zagreba: YouTube recordings, per-councillor roll-call votes,
question-hour fonograms), 'brod' (Gradsko vijeće Grada Slavonskog Broda: MP3 recordings, near-verbatim
minutes with vote totals), 'krk' (Gradsko vijeće Grada Krka: MP3 recordings, minutes) and 'rijeka'
(Gradsko vijeće Grada Rijeke: YouTube recordings, agenda with proposals and adopted acts). Read-only over data/vijecnica.db. Every transcript hit links to the exact
second of the recording.

Run: .venv/bin/python mcp_server.py            (stdio, for Claude Code / Claude Desktop)
     .venv/bin/python mcp_server.py --http PORT (streamable HTTP + web page)
"""
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BeforeValidator, Field

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "vijecnica.db"

mcp = MCPServer(
    "vijecnica",
    instructions=(
        "City council data for Croatian cities, term 2025-2029. city='zagreb' (Gradska skupština Grada "
        "Zagreba), 'brod' (Slavonski Brod), 'krk' (Grad Krk) or 'rijeka' (Grad Rijeka), each its Gradsko "
        "vijeće; call list_cities first if unsure. "
        "Data: session agendas, votes (Zagreb: per councillor; elsewhere: totals from minutes or city news), attendance, "
        "councillors' questions with official verbatim answers (Zagreb fonogram), official minutes "
        "(zapisnik; Brod's are near-verbatim), and machine transcripts of the session recordings with "
        "timestamps. Answer in the user's language (usually Croatian). Always cite: link the recording "
        "timestamp for transcript quotes and name the session and agenda item for votes. Machine "
        "transcripts can misspell names; official documents win on facts."),
)


CITY_ALIASES = {"slavonski brod": "brod", "slavonski-brod": "brod", "sb": "brod", "grad zagreb": "zagreb", "zg": "zagreb",
                "grad krk": "krk", "grad rijeka": "rijeka", "ri": "rijeka"}


def _norm_city(v):
    if isinstance(v, str):
        v = v.strip().lower()
        return CITY_ALIASES.get(v, v)
    return v


def _norm_status(v):
    if isinstance(v, str):
        v = v.strip().lower()
        return {"expired": "rok_prošao", "rok_prosao": "rok_prošao", "rok prošao": "rok_prošao", "open": "otvoreno",
                "no_deadline": "bez_roka", "bez roka": "bez_roka", "all": ""}.get(v, v)
    return v


City = Annotated[Literal["zagreb", "brod", "krk", "rijeka"], BeforeValidator(_norm_city),
                 Field(description="City: 'zagreb' (Gradska skupština Grada Zagreba), 'brod' (Gradsko vijeće Grada "
                                   "Slavonskog Broda), 'krk' (Gradsko vijeće Grada Krka) or 'rijeka' (Gradsko vijeće "
                                   "Grada Rijeke). Case-insensitive; 'Slavonski Brod' also works.")]
AnyCity = Annotated[Literal["", "zagreb", "brod", "krk", "rijeka"], BeforeValidator(_norm_city),
                    Field(description="'' = every city, or 'zagreb' / 'brod' / 'krk' / 'rijeka'")]
Session = Annotated[int, Field(ge=1, description="Session number (sjednica) of the 2025-2029 term; list_sessions "
                                                 "gives the valid numbers")]
ItemNo = Annotated[int, Field(ge=0, description="Agenda item number (točka dnevnog reda), as in get_session items[].no")]
Sub = Annotated[int, Field(ge=1, description="Which item when several share one number (items[].sub); usually 1")]


def q(sql, *args):
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, args)]
    finally:
        db.close()


def site(city):
    r = q("SELECT site FROM cities WHERE id = ?", city)
    return r[0]["site"] if r else ""


def link(video_id, t):
    """Recording URL at second t: YouTube ?t= or an MP3 media fragment #t=."""
    v = q("SELECT kind, url FROM videos WHERE id = ?", video_id)
    if not v:
        return None
    t = int(t or 0)
    return f"{v[0]['url']}&t={t}s" if v[0]["kind"] == "youtube" else f"{v[0]['url']}#t={t}"


def absolute(city, url):
    return url if not url or url.startswith("http") else site(city) + url


def hms(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


VOWELS = set("aeiou")


def _stem(w):
    """Croatian-ish stem for prefix search: 6+ letters drop 2 (vrtića -> vrti*), 4-5 letters drop a final
    vowel (škola -> škol*, cesta -> cest*) or keep the word as a prefix (vrtić -> vrtić* = vrtića, vrtići)."""
    if len(w) > 5:
        return f'"{w[:-2]}"*'
    if len(w) >= 4:
        return f'"{w[:-1]}"*' if w[-1].lower() in VOWELS else f'"{w}"*'
    return f'"{w}"'


def fts(query):
    """Turn free text into an FTS5 query: words ANDed, each word matched by its stem as a prefix."""
    words = re.findall(r"\w+", query)
    return " ".join(_stem(w) for w in words) or '""'


# Who governs: the mayor's side and the clubs that form the majority (2025-2029 term). Used to tag speakers
# and clubs as vlast/oporba. Seats are counted from the latest attendance list we have.
GOVERNING = {
    "zagreb": {"label": "Možemo! + SDP", "mayor": "Tomislav Tomašević",
               "parties": ["Možemo! - politička platforma", "Socijaldemokratska partija Hrvatske"],
               "note": "Vladajuća koalicija u Gradskoj skupštini (saziv 2025.–2029.) i gradonačelnik Tomislav "
                       "Tomašević (Možemo!)."},
    "brod": {"label": "Nezavisna lista Mirka Duspare", "mayor": "Mirko Duspara",
             "parties": ["Duspara Mirko - Nezavisna lista"],
             "note": "Gradonačelnik Mirko Duspara i vijećnici njegove nezavisne liste."},
    "krk": {"label": "PGS + SDP + Unija Kvarnera", "mayor": "Darijo Vasilić",
            "parties": ["PGS", "SDP", "Unija Kvarnera"],
            "note": "Gradonačelnik Darijo Vasilić (PGS, koalicijska lista PGS-SDP) i klub PGS-SDP-UK u Gradskom vijeću."},
    "rijeka": {"label": "AM-Unija-Centar-HSU-Fokus-Alternativa (manjinska)", "mayor": "Iva Rinčić", "mayor_f": True,
               "parties": ["Akcija mladih (AM)", "Unija Kvarnera - Unija", "CENTAR", "Hrvatska stranka umirovljenika (HSU)",
                           "FOKUS", "ALTERNATIVA 101 - ALTERNATIVA"],
               "note": "Gradonačelnica Iva Rinčić i klub AM-UNIJA-CENTAR-HSU-FOKUS-ALTERNATIVA (11 od 32). Stabilne većine "
                       "nema: proračun i rebalans prošli su sa 17 glasova, a polugodišnji izvještaj gradonačelnice nije "
                       "prošao. Tko je od ostalih glasovao za, iz zbrojeva se ne vidi (Rijeka ne objavljuje poimenično "
                       "glasovanje)."},
    "osijek": {"label": "HDZ-HSLS-HNS-NL Đapić-NL Mišetić", "mayor": "Ivan Radić",
               "parties": ["HDZ, HSLS, HNS, NL ANTE ĐAPIĆA, NL Tomislava Mišetića"],
               "note": "Gradonačelnik Ivan Radić (HDZ), izabran 2025. u prvom krugu, i lista HDZ-HSLS-HNS-NL Ante Đapića-NL "
                       "Tomislava Mišetića (20 od 29 vijećnika prema popisu vijećnika na osijek.hr). Osijek ne objavljuje "
                       "poimenično glasovanje."},
    "sibenik": {"label": "HDZ i partneri", "mayor": "Željko Burić",
                "parties": ["HDZ", "HDZ-HDS-DP", "HDS"],
                "note": "Gradonačelnik Željko Burić (HDZ) i vijećnici HDZ-a i partnera (11 od 21 prema popisu vijećnika na "
                        "sibenik.hr); sporne točke redovito prolaze s 11-12 glasova za. Šibenik ne objavljuje poimenično "
                        "glasovanje."},
}
SHORT = {"Možemo! - politička platforma": "Možemo!", "Socijaldemokratska partija Hrvatske": "SDP",
         "Hrvatska demokratska zajednica": "HDZ", "Domovinski pokret": "DP",
         "Hrvatska narodna stranka - liberalni demokrati": "HNS", "Hrvatska socijalno - liberalna stranka": "HSLS",
         "Hrvatska stranka umirovljenika": "HSU", "Nezavisna lista Tomislava Jonjića - Jedino Hrvatska!": "Jedino Hrvatska!",
         "Dina Dogan - Nezavisna lista": "Lista Dine Dogan", "Duspara Mirko - Nezavisna lista": "Lista M. Duspare",
         "Kandidacijska lista grupe birača": "Lista grupe birača", "Nestranački": "nestranački",
         "Kandidacijska lista grupe birača; nositelj liste: Dinko Jakovljević": "Lista D. Jakovljevića",
         "Kandidacijska lista grupe birača; nositelj liste: Goran Marević": "Lista G. Marevića",
         "Hrvatska demokratska zajednica (HDZ)": "HDZ", "Možemo! - politička platforma - Možemo!": "Možemo!",
         "Socijaldemokratska partija Hrvatske (SDP)": "SDP", "Akcija mladih (AM)": "AM", "Unija Kvarnera - Unija": "Unija",
         "ALTERNATIVA 101 - ALTERNATIVA": "Alternativa", "Hrvatska stranka umirovljenika (HSU)": "HSU",
         "Primorsko goranski savez (PGS)": "PGS", "Lista za Rijeku (RI)": "RI", "Istarski demokratski sabor (IDS)": "IDS",
         "Nezavisan": "nezavisni", "Nezavisna": "nezavisna"}


def short(p):
    return SHORT.get(p or "", p or "bez stranke")


def governing(city):
    g = GOVERNING.get(city)
    if not g:
        return None
    last = q("SELECT max(session) s FROM attendance WHERE city = ?", city)[0]["s"]
    seats = q("""SELECT m.party, count(*) c FROM attendance a LEFT JOIN members m ON m.city = a.city AND m.name = a.member
                 WHERE a.city = ? AND a.session = ? GROUP BY m.party""", city, last) if last else []
    total = sum(r["c"] for r in seats)
    gov = sum(r["c"] for r in seats if r["party"] in g["parties"])
    if not total:  # no attendance (Brod before minutes): use the roster
        seats = q("SELECT party, count(*) c FROM members WHERE city = ? AND party IS NOT NULL GROUP BY party", city)
        total, gov = sum(r["c"] for r in seats), sum(r["c"] for r in seats if r["party"] in g["parties"])
    out = {**g, "parties_short": [short(p) for p in g["parties"]], "seats": gov, "of": total,
           "seats_basis": f"popis nazočnosti {last}. sjednice" if last else "popis vijećnika"}
    if total and gov * 2 <= total:
        out["majority_note"] = (f"{gov} od {total} mjesta: lista sama nema apsolutnu većinu; s kim glasuje "
                                "vidi se po rezultatima glasovanja")
    return out


def bloc(city, party, role=None):
    """'vlast' (mayor's side / governing clubs), 'oporba', or None when unknown."""
    g = GOVERNING.get(city)
    if role == "dužnosnik":
        return "gradska uprava"
    if not g or not party:
        return None
    if party in g["parties"]:
        return "vlast"
    # independents are not a club: no reason to call them opposition
    return "nezavisni" if party.startswith(("Nestran", "Nezavisna vijeć", "Nezavisni vijeć")) else "oporba"


def asr_quality(city):
    """ASR quality measured against near-verbatim minutes (Brod session 9, eval_brod.py)."""
    if city != "brod":
        return None
    f = sorted((ROOT / "reports").glob("asr_eval_brod_*.json"))
    best = None
    for p in f:
        d = json.loads(p.read_text())
        if d.get("partial") or not d.get("asr", {}).get("wer"):
            continue
        best = d
    if not best:
        return None
    a = best["asr"]
    cov = f"na {a['windows_matched']} od {a['windows_total']} odlomaka koje zapisnik prenosi"
    return {"session": best["session"], "wer": a["wer"], "agreement_pct": round(100 * (1 - a["wer"]), 1),
            "coverage": cov, "windows_matched": a["windows_matched"], "windows_total": a["windows_total"],
            "words_compared": a["aligned_ref_words"], "windows": f"{a['windows_matched']}/{a['windows_total']}",
            "median_window_wer": a.get("median_window_wer"), "cer_no_spaces": a.get("cer_no_spaces"),
            "transcript_minutes": best.get("transcript_minutes"),
            "speakers": {k: best["speakers"].get(k) for k in ("recall", "precision", "windows_with_gold")},
            "votes": {k: best["votes"].get(k) for k in ("compared", "exact", "with_number", "exact_of_numbered")},
            "label": f"Strojni transkript: ≈{round(100 * (1 - a['wer']))} % riječi se slaže sa zapisnikom "
                     f"(na {a['windows_matched']}/{a['windows_total']} odlomaka koje zapisnik prenosi; {best['session']}. sjednica)",
            "method": best.get("method"), "report": f"api/asr_eval?city=brod&n={best['session']}"}


@mcp.tool()
def list_cities() -> list[dict]:
    """Cities covered: sessions, agenda items, recordings and how many are transcribed ('coverage'), who governs
    ('governing': mayor's side and majority clubs, for vlast/oporba), and the measured transcript quality
    ('asr_quality', Brod: word agreement with the near-verbatim minutes of one session)."""
    rows = q("""SELECT c.id AS city, c.name, c.body,
                       (SELECT count(*) FROM sessions s WHERE s.city = c.id) AS sessions,
                       (SELECT count(*) FROM items i WHERE i.city = c.id) AS items,
                       (SELECT count(*) FROM videos v WHERE v.city = c.id) AS recordings,
                       (SELECT count(*) FROM videos v WHERE v.city = c.id AND v.transcribed) AS transcribed,
                       (SELECT group_concat(DISTINCT v.session) FROM videos v WHERE v.city = c.id AND v.transcribed)
                         AS transcribed_sessions
                FROM cities c""")
    for r in rows:
        r["coverage"] = (f"transkribirano {r['transcribed']} od {r['recordings']} snimki"
                         + (f" (sjednice {r['transcribed_sessions']})" if r["transcribed_sessions"] else ""))
        r["governing"] = governing(r["city"])
        r["asr_quality"] = asr_quality(r["city"])
    return rows


def _check_session(city, session):
    if not q("SELECT 1 FROM sessions WHERE city = ? AND n = ?", city, session):
        ns = [r["n"] for r in q("SELECT n FROM sessions WHERE city = ? ORDER BY n", city)]
        raise ToolError(f"no session {session} in {city}; valid sessions: {ns[0]}-{ns[-1]}" if ns else
                        f"no sessions for {city}")


@mcp.tool()
def list_sessions(city: City = "zagreb") -> list[dict]:
    """All sessions of the term in a city: number, date, agenda size, accepted items, recordings.
    held = the date is today or earlier (accepted counts mean nothing before that); minutes_published."""
    return q("""SELECT s.n AS session, s.date, count(i.no) AS items, s.date <= date('now', 'localtime') AS held,
                       coalesce(s.minutes_text, '') != '' AS minutes_published,
                       sum(i.result = 'Prijedlog usvojen' OR i.status = 'prihvaćen') AS accepted,
                       (SELECT count(*) FROM videos v WHERE v.city = s.city AND v.session = s.n) AS videos,
                       (SELECT count(*) FROM videos v WHERE v.city = s.city AND v.session = s.n
                                                        AND v.transcribed) AS transcribed
                FROM sessions s LEFT JOIN items i ON i.city = s.city AND i.session = s.n
                WHERE s.city = ? GROUP BY s.n ORDER BY s.n DESC""", city)


@mcp.tool()
def get_session(session: Session, city: City = "zagreb") -> dict:
    """One session: agenda items with status and vote totals, attendance, recordings, minutes link.
    Brod items voted in a transcribed recording but not yet in published minutes carry 'snimka': the vote
    results the chair read out ("12 glasova za, 7 protiv, 1 suzdržan"), source='snimka' = unofficial, with
    a link to that second of the recording."""
    s = q("SELECT n, date, title, url, minutes_url, minutes_text IS NOT NULL AND minutes_text != '' AS minutes_published"
          " FROM sessions WHERE city = ? AND n = ?", city, session)
    if not s:
        _check_session(city, session)
    out = s[0]
    out["city"] = city
    today = date.today()
    out["minutes_published"] = bool(out["minutes_published"])
    out["held"] = bool(out["date"]) and out["date"] <= today.isoformat()
    if out["held"] and not out["minutes_published"]:
        out["days_without_minutes"] = (today - date.fromisoformat(out["date"])).days
    out["items"] = q("""SELECT no, sub, title, proposer, status, za, protiv, suzdrzano, result, totals_note
                        FROM items WHERE city = ? AND session = ? ORDER BY no, sub""", city, session)
    for x in out["items"]:
        x["totals_note"] = json.loads(x["totals_note"]) if x["totals_note"] else None
    spoken = {}
    for v in q("""SELECT item_no, sub, n, label, za, protiv, suzdrzano, unanimous, outcome, video_id, t, quote
                  FROM spoken_votes WHERE city = ? AND session = ? ORDER BY item_no, n""", city, session):
        v["at"], v["url"] = hms(v["t"]), link(v.pop("video_id"), v.pop("t"))
        spoken.setdefault((v.pop("item_no"), v.pop("sub")), []).append(v)
    for it in out["items"]:
        sv = spoken.get((it["no"], it["sub"]))
        if sv:
            last = sv[-1]
            one = len(sv) == 1  # several votes (sub-items, companies): no single headline count, see 'votes'
            it["snimka"] = {"source": "snimka", "label": "iz snimke, neslužbeno",
                            "za": last["za"] if one else None, "protiv": last["protiv"] if one else None,
                            "suzdrzano": last["suzdrzano"] if one else None, "n_votes": len(sv),
                            "unanimous": all(v["unanimous"] for v in sv),
                            "outcome": last["outcome"] if one or len({v["outcome"] for v in sv}) == 1 else "različito",
                            "at": sv[0]["at"], "url": sv[0]["url"], "votes": sv}
    out["absent"] = [r["member"] for r in q(
        "SELECT member FROM attendance WHERE city = ? AND session = ? AND NOT present", city, session)]
    out["present_count"] = q("SELECT count(*) c FROM attendance WHERE city = ? AND session = ? AND present",
                             city, session)[0]["c"]
    if not out["absent"] and not out["present_count"]:
        out["attendance_note"] = ("nazočnost još nije poznata: zapisnik nije objavljen" if out["held"] and not out["minutes_published"]
                                  else "nazočnost nije objavljena" if out["held"] else "sjednica još nije održana")
    out["recordings"] = [{**v, "url": link(v["id"], 0)} for v in q(
        """SELECT id, part, upload_date, duration, transcribed, kind FROM videos
           WHERE city = ? AND session = ? ORDER BY part""", city, session)]
    out["minutes_url"] = absolute(city, out.get("minutes_url"))
    return out


@mcp.tool()
def get_item(session: Session, item_no: ItemNo, sub: Sub = 1, city: City = "zagreb") -> dict:
    """One agenda item (točka dnevnog reda): full title, proposer, documents, vote totals, a plain-language
    'verdict' sentence, and (Zagreb) how each councillor and club voted ('clubs': sorted by size, with
    vlast/oporba). A few numbers hold several items; 'sub' picks one (1, 2, ...). 'session_recordings' links
    the session's recordings even when this item is not transcribed yet."""
    it = q("SELECT * FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?", city, session, item_no, sub)
    if not it:
        _check_session(city, session)
        nos = sorted({(r["no"], r["sub"]) for r in q("SELECT no, sub FROM items WHERE city = ? AND session = ?", city, session)})
        raise ToolError(f"no item {item_no}" + (f" sub {sub}" if sub > 1 else "") + f" in {city} session {session}; "
                        f"items: {', '.join(f'{n}' + (f'.{s}' if s > 1 else '') for n, s in nos)}")
    it = it[0]
    if it.get("committees"):  # the source concatenates committee names without a separator
        it["committees"] = " · ".join(x.strip() for x in re.split(
            r"\s+(?=(?:Odbor|Povjerenstvo|Komisija|Mandatna komisija|Klub|Gradsko vijeće|Savjet)\b)", it["committees"]) if x.strip())
    # roll call vs official totals: "ručno" = votes added by hand ("32+3=35*", raised card), marked X* in the list
    it["totals_note"] = json.loads(it["totals_note"]) if it.get("totals_note") else None
    it["attachments"] = [{"name": a["name"] if a["name"].lower() not in ("downloadfile", "") else
                          f"Dokument {k} (bez naziva u izvoru)", "url": absolute(city, a["url"])}
                         for k, a in enumerate(json.loads(it.pop("attachments") or "[]"), 1)]
    it["url"] = absolute(city, it["url"])
    vid = it.pop("video_id")
    if vid:
        it["debate_starts"] = {"at": hms(it["t_start"]), "url": link(vid, it["t_start"])}
        if it["t_vote"] is not None:
            it["vote_called"] = {"at": hms(it["t_vote"]), "url": link(vid, it["t_vote"])}
    for k in ("t_start", "t_vote"):
        it.pop(k)
    votes = q("""SELECT v.member, m.party, v.vote FROM votes v
                 LEFT JOIN members m ON m.city = v.city AND m.name = v.member
                 WHERE v.city = ? AND v.session = ? AND v.item_no = ? AND v.sub = ? ORDER BY m.party, v.member""",
              city, session, item_no, sub)
    by_party = {}
    for v in votes:
        by_party.setdefault(v["party"], {}).setdefault(v["vote"], []).append(v["member"])
    it["votes_by_party"] = by_party
    clubs = []
    for p, v in by_party.items():
        c = {k: len(v.get(k, [])) for k in ("za", "protiv", "suzdrzan", "nije_glasovao", "odsutan")}
        clubs.append({"party": p, "short": short(p), "bloc": bloc(city, p), "size": sum(c.values()), **c,
                      "members": v})
    clubs.sort(key=lambda c: (-c["size"], c["short"]))
    it["clubs"] = clubs
    sv = q("""SELECT n, label, za, protiv, suzdrzano, unanimous, outcome, video_id, t, quote FROM spoken_votes
              WHERE city = ? AND session = ? AND item_no = ? AND sub = ? ORDER BY n""", city, session, item_no, sub)
    for v in sv:
        v["at"], v["url"] = hms(v["t"]), link(v.pop("video_id"), v.pop("t"))
    if sv:
        it["snimka"] = {"source": "snimka", "label": "iz snimke, neslužbeno", "votes": sv}
    it["verdict"] = verdict(it)
    it["session_recordings"] = [{"part": v["part"], "transcribed": bool(v["transcribed"]), "url": link(v["id"], 0)}
                                for v in q("SELECT id, part, transcribed FROM videos WHERE city = ? AND session = ?"
                                           " ORDER BY part", city, session)]
    return it


VERB = {"prihvaćen": "Prihvaćeno", "odbijen": "Odbijeno", "povučen": "Povučeno", "vraćen na doradu": "Vraćeno na doradu"}


def verdict(it):
    """One plain sentence: outcome + which clubs voted how ("Odbijeno. Protiv: Možemo! (16), SDP (7). Za: …")."""
    st = (it.get("status") or "").strip()
    res = it.get("result") or ""
    head = VERB.get(st) or ("Usvojeno" if "usvojen" in res and "nije" not in res else
                            "Nije usvojeno" if "nije usvojen" in res else "")
    parts = []
    clubs = it.get("clubs") or []
    if clubs:
        for k, lbl in (("za", "Za"), ("protiv", "Protiv"), ("suzdrzan", "Suzdržani")):
            cs = sorted([c for c in clubs if c[k]], key=lambda c: -c[k])
            if cs:
                parts.append(f"{lbl}: " + ", ".join(f"{c['short']} ({c[k]})" for c in cs) + ".")
        nv = sum(c["nije_glasovao"] for c in clubs)
        if nv:
            parts.append(f"U dvorani, a nisu glasovali: {nv}.")
    elif it.get("za") is not None:
        parts.append(f"{it['za']} za, {it['protiv'] or 0} protiv, {it['suzdrzano'] or 0} suzdržano." if it["protiv"] is not None
                     else f"{it['za']} za (protiv i suzdržani nisu navedeni).")
    elif it.get("snimka"):
        v = it["snimka"]["votes"][-1]
        head = head or ("Usvojeno" if "usvoj" in (v.get("outcome") or "") else "")
        parts.append("Prema snimci (neslužbeno): " + ("jednoglasno" if v["unanimous"] and v["za"] is None else
                     f"{v['za']} za, {v['protiv'] or 0} protiv, {v['suzdrzano'] or 0} suzdržano") + ".")
    if not head and not parts:
        return None
    return (head + ". " if head else "") + " ".join(parts)


@mcp.tool()
def search(query: Annotated[str, Field(description="Croatian words; every word must match, endings are ignored "
                                                   "(vrtić finds vrtića, vrtići)")],
           city: AnyCity = "",
           session: Annotated[int | None, Field(description="Only this session (needs city)")] = None,
           limit: Annotated[int, Field(ge=1, le=100, description="Max hits per kind")] = 15) -> dict:
    """Full-text search: what was said in sessions (transcripts, with recording timestamps), agenda
    items, and councillors' questions. Use Croatian words, e.g. 'tramvaj Dubrava', 'stadion Maksimir',
    'Jakuševec', 'Tvrđava Brod'. city='' searches every city; 'session' needs a city. Only part of the
    recordings is transcribed (list_cities → coverage), so 'said_in_session' covers those sessions only."""
    if session and not city:
        raise ToolError("'session' needs 'city' ('zagreb', 'brod', 'krk' or 'rijeka'): session numbers repeat across cities")
    m = fts(query)
    cond, extra = "", []
    if city:
        cond += " AND {t}.city = ?"
        extra.append(city)
        if session:
            cond += " AND {t}.session = ?"
            extra.append(session)
    said = q(f"""SELECT s.video_id, s.city, s.session, s.start, snippet(segments_fts, 0, '**', '**', '…', 40) AS text
                 FROM segments_fts JOIN segments s ON s.id = segments_fts.rowid
                 WHERE segments_fts MATCH ? {cond.format(t='s')} ORDER BY rank LIMIT ?""", m, *extra, limit)
    for r in said:
        r["at"] = hms(r["start"])
        r["url"] = link(r.pop("video_id"), r.pop("start"))
    items = q(f"""SELECT i.city, i.session, i.no, i.sub, i.title, i.status, i.za, i.protiv, i.suzdrzano, i.result
                  FROM items_fts JOIN items i ON i.rowid = items_fts.rowid
                  WHERE items_fts MATCH ? {cond.format(t='i')} ORDER BY rank LIMIT ?""", m, *extra, limit)
    qs = q(f"""SELECT x.id, x.city, x.session, x.member, x.party, x.question
               FROM questions_fts JOIN questions x ON x.id = questions_fts.rowid
               WHERE questions_fts MATCH ? {cond.format(t='x')} ORDER BY rank LIMIT ?""", m, *extra, limit)
    return {"said_in_session": said, "agenda_items": items, "questions": qs}


@mcp.tool()
def get_transcript(session: Session,
                   part: Annotated[int, Field(ge=1, description="Recording part (a session can have several)")] = 1,
                   start: Annotated[str, Field(description="Offset h:mm:ss, mm:ss or seconds")] = "0:00:00",
                   minutes: Annotated[int, Field(ge=1, le=60, description="How many minutes to return")] = 10,
                   city: City = "zagreb") -> dict:
    """Machine transcript of a session recording from a time offset (h:mm:ss), with timestamps and
    links. A session can have several recordings ('part'); 'parts' lists them with their transcribed flag,
    so a call on an untranscribed part says which part has text. Use after search() to read the context."""
    parts = [{"part": r["part"], "transcribed": bool(r["transcribed"]), "duration_s": r["duration"]}
             for r in q("SELECT part, transcribed, duration FROM videos WHERE city = ? AND session = ? ORDER BY part",
                        city, session)]
    if not parts:
        _check_session(city, session)
        raise ToolError(f"{city} session {session} has no recording")
    v = q("SELECT id, transcribed FROM videos WHERE city = ? AND session = ? AND part = ?", city, session, part)
    if not v:
        raise ToolError(f"{city} session {session} has parts {[p['part'] for p in parts]}, not {part}")
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}", start.strip()):
        raise ToolError(f"start must be h:mm:ss, mm:ss or seconds, got {start!r}")
    vid = v[0]["id"]
    h, mi, se = ([0, 0] + [int(x) for x in start.strip().split(":")])[-3:]
    t0 = h * 3600 + mi * 60 + se
    rows = q("SELECT start, text FROM segments WHERE video_id = ? AND start >= ? AND start < ? ORDER BY start",
             vid, t0, t0 + minutes * 60)
    out = {"recording": link(vid, t0), "parts": parts, "transcribed": bool(v[0]["transcribed"]),
           "lines": [f"[{hms(r['start'])}] {r['text']}" for r in rows]}
    if not v[0]["transcribed"]:
        done = [p["part"] for p in parts if p["transcribed"]]
        out["note"] = f"part {part} is not transcribed yet" + (f"; transcribed parts: {done}" if done else "")
    elif not rows:
        out["note"] = "no speech in this window (try another start)"
    return out


@mcp.tool()
def item_debate(session: Session, item_no: ItemNo, sub: Sub = 1,
                max_lines: Annotated[int, Field(ge=1, le=2000, description="Max transcript lines")] = 400,
                city: City = "zagreb") -> dict:
    """The full recorded debate on one agenda item, from the chair announcing it to the vote, with
    timestamps, links and who speaks (speaker turns detected from the chair's cues; machine-made, may
    miss turns the chair did not announce by name). Every speaker carries 'party' and 'bloc' (vlast = the
    governing clubs, oporba, gradska uprava = mayor/officials); 'governing' names the majority. Use it to
    summarise who argued what on a decision."""
    it = q("SELECT video_id, t_start, t_vote, title FROM items WHERE city = ? AND session = ? AND no = ? AND sub = ?",
           city, session, item_no, sub)
    if not it:
        get_item(session, item_no, sub, city)  # raises with the valid item numbers
    if not it[0]["video_id"]:
        rec = [v for v in q("SELECT id, part, transcribed FROM videos WHERE city = ? AND session = ?", city, session)]
        return {"available": False, "error": "this item is not located in a transcribed recording yet",
                "session_recordings": [{"part": v["part"], "transcribed": bool(v["transcribed"]), "url": link(v["id"], 0)}
                                       for v in rec]}
    it = it[0]
    end = it["t_vote"] + 90 if it["t_vote"] is not None else it["t_start"] + 3600
    rows = q("SELECT start, text FROM segments WHERE video_id = ? AND start >= ? AND start <= ? ORDER BY start",
             it["video_id"], it["t_start"], end)
    turns = q("""SELECT t.start, t.end, t.speaker, t.kind, t.role, m.party FROM speaker_turns t
                 LEFT JOIN members m ON m.city = t.city AND m.name = t.speaker
                 WHERE t.city = ? AND t.session = ? AND t.item_no = ? AND t.sub = ? ORDER BY t.start""",
              city, session, item_no, sub)
    for t in turns:
        t["bloc"] = bloc(city, t["party"], t["role"])

    def who(t):
        cur = None
        for tt in turns:
            if tt["start"] <= t + 0.01:
                cur = tt
        return cur if cur and t < cur["end"] + 1 else None
    blocks = []
    for r in rows[:max_lines]:
        w = who(r["start"])
        key = (w["speaker"], w["start"]) if w else None
        if blocks and blocks[-1]["_key"] == key:
            blocks[-1]["text"] += " " + r["text"]
            continue
        blocks.append({"_key": key, "speaker": w["speaker"] if w else None, "kind": w["kind"] if w else None,
                       "party": short(w["party"]) if w and w["party"] else None, "bloc": w["bloc"] if w else None,
                       "at": hms(r["start"]), "url": link(it["video_id"], r["start"]), "text": r["text"]})
    for b in blocks:
        b.pop("_key")
    return {"title": it["title"], "recording": link(it["video_id"], it["t_start"]),
            "governing": {k: v for k, v in (governing(city) or {}).items() if k in ("label", "mayor", "parties_short")},
            "speakers": [{"speaker": t["speaker"], "kind": t["kind"], "party": short(t["party"]) if t["party"] else None,
                          "bloc": t["bloc"], "at": hms(t["start"]), "url": link(it["video_id"], t["start"])} for t in turns],
            "lines": [f"[{hms(r['start'])}] {r['text']}" for r in rows[:max_lines]],
            "blocks": blocks, "truncated": len(rows) > max_lines}


@mcp.tool()
def speaker_turns(session: Session, item_no: Annotated[int | None, Field(description="Only this item; omit = whole session")] = None,
                  sub: Sub = 1, city: City = "zagreb") -> dict:
    """Who spoke when in a session (or one agenda item): speaker, kind of turn (rasprava, u ime Kluba,
    replika, neslaganje s replikom, obrazlaže, završna riječ), start/end time and recording link. Detected
    from the chair's cues in the machine transcript ("zastupnica X, izvolite"); compare with the official
    minutes via draft_minutes. Coverage on Zagreb session 14: see minutes_evaluation."""
    cond, args = "", [city, session]
    if item_no is not None:
        cond, args = " AND item_no = ? AND sub = ?", args + [item_no, sub]
    rows = q(f"""SELECT video_id, item_no, sub, start, end, speaker, role, kind, method FROM speaker_turns
                 WHERE city = ? AND session = ?{cond} ORDER BY video_id, start""", *args)
    for r in rows:
        r["at"], r["minutes"] = hms(r["start"]), round((r["end"] - r["start"]) / 60, 1)
        r["url"] = link(r.pop("video_id"), r.pop("start"))
        r.pop("end")
    if not rows:
        return {"turns": [], "note": "no transcribed recording / no detected turns for this selection"}
    return {"turns": rows}


@mcp.tool()
def draft_minutes(session: Session, item_no: ItemNo, sub: Sub = 1, city: City = "zagreb") -> dict:
    """Auto-drafted minutes (zapisnik) paragraph for one agenda item in the official format ("Predlagatelj
    je …", "U raspravi sudjeluju: …", "Glasovalo je N … donosi …"), built by rules from the agenda, the
    roll-call vote and the speaker turns in the recording. If the official minutes exist, they are returned
    too with a comparison (speakers found/missed, vote exact match, outcome)."""
    import minutes_draft
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        d = minutes_draft.draft(db, city, session, item_no, sub)
        if "error" in d:
            return d
        off = minutes_draft.official(db, city, session, item_no, sub)
        if off:
            d["official"] = {"text": off["text"], "speakers": off["speakers"], "closing": off["closing"],
                             "vote": {k: off[k] for k in ("voted", "za", "protiv", "suzdrzano", "mode", "verb")}}
            d["comparison"] = minutes_draft.compare(d, off)
        else:
            d["official"] = None
        return d
    finally:
        db.close()


@mcp.tool()
def minutes_evaluation(session: Session = 14, city: City = "zagreb") -> dict:
    """How good the auto-drafted minutes are against the official ones for a whole session: speaker
    recall/precision, order agreement, decision type, per item. Vote totals match by construction (the draft
    copies the roll-call totals), so 'vote_exact' checks the format, not a measurement."""
    ck = ("me", session, city, DB.stat().st_mtime)
    if ck not in _ASK_CACHE:
        _ASK_CACHE[ck] = _minutes_evaluation(session, city)
    return _ASK_CACHE[ck]


def _minutes_evaluation(session, city):
    import eval_minutes
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        summary, rows = eval_minutes.evaluate(db, city, session)
    finally:
        db.close()
    keep = ("no", "sub", "title", "in_recording", "gold_speakers", "speakers_matched", "speaker_recall",
            "speaker_precision", "gold_turns", "turns_matched", "order_agreement", "missed", "extra", "closing_ok",
            "vote_exact", "outcome_ok", "doc_ok", "text_similarity", "official_speakers", "draft_speakers")
    return {"summary": summary, "items": [{k: r[k] for k in keep} for r in rows]}


MONTHS = ("siječ", "veljač", "ožuj", "trav", "svib", "lip", "srp", "kolovoz", "rujn", "rujan", "listopad", "studen", "prosin")
STOP = set("""godine godina godinu godini godinama gradonačelnik gradonačelnika gradonačelnice zastupnik zastupnika
zastupnica zastupnice zastupnicu kolega kolege kolegice kolegica pitanje pitanja pitanju odgovor grada gradu gradom
gradske gradski gradska zagreba zagrebu zagreb zagrebački zagrebačke znači dakle naravno također sljedeće sljedeći
mjesec mjeseca mjeseci tjedan tjedna tjedana početkom krajem sredinom sigurno upravo odnosno međutim svakako mislim
imamo možemo trebamo ovdje onda tome kojem kojoj kada nakon prije tijekom uskoro svega svaki svake jednom nekoliko
vezano zanima informacije konkretno kvartala polovine očekujem očekujemo računam nadam planiramo trebali trebala
trebao krenuti krenuli kreće krenut napraviti napravit završiti završetak gotovo gotova realizirati realizacija
odnosi isto ovome tome ovoga napreduje napredovanje predlaže prijedlog uvođenje okvirni realizacije poduzima novosti
mlade mladih potaknuti konkretni konkretne mjerljivi vremenski određeni plana plan projekta projekt projekte
sesvete sesvetama sesveta sesvetski dubrava dubravi donji donjem donja donjeg gornji gornjem gornja gornjeg novog
novom trnje gradske četvrti četvrt naselja naselje ulice ulici ulica nacrta nacionalnog generalnog
detalji informacija informacije zanimaju zatražila izvijesti sjednici""".split())


def _words(text, proper_only=False):
    """Content words (>= 5 letters, not stop words or months). proper_only: capitalised words that do not
    start a sentence (place and project names: Jarunskog, Kašini, Klaićevoj)."""
    out = []
    for mt in re.finditer(r"[^\W\d_]{5,}", text or ""):
        w = mt.group()
        if w.lower() in STOP or w.lower().startswith(MONTHS):
            continue
        if proper_only:
            before = (text[:mt.start()].rstrip() or ".")[-1]
            if not w[0].isupper() or before in ".!?…:\"„“”" or w.isupper():
                continue
        out.append(w)
    return out


def _followups(city):
    """For every promise: later sessions' agenda items, questions and transcripts that mention its subject.
    Subject terms = words of the question topic and the quote that are rare in the question corpus (df <= 12 %);
    a later document must contain two of them (or the single rarest one, df <= 4). Only sessions already held
    count (a scheduled session's agenda is not a "later mention"). Cached per DB version and day."""
    ck = ("fu", city, DB.stat().st_mtime, __import__("datetime").date.today())
    if ck in _ASK_CACHE:
        return _ASK_CACHE[ck]
    nq = q("SELECT count(*) c FROM questions WHERE city = ?", city)[0]["c"] or 1
    last_held = q("SELECT max(n) n FROM sessions WHERE city = ? AND date <= date('now', 'localtime')", city)[0]["n"] or 0
    df_cache, out = {}, {}

    def df(w):
        if w not in df_cache:
            df_cache[w] = q("SELECT count(*) c FROM questions_fts JOIN questions x ON x.id = questions_fts.rowid "
                            "WHERE questions_fts MATCH ? AND x.city = ?", _stem(w), city)[0]["c"]
        return df_cache[w]
    for p in q("SELECT id, session, topic, quote FROM promises WHERE city = ?", city):
        # subject terms: names (strong) from the quote and the question, then words of the question summary
        # (medium). General words of the quote ("obično", "rastegne") are not used: they matched unrelated text.
        seen, terms = set(), []
        for strength, ws in ((0, _words(p["quote"], True) + _words(p["topic"], True)), (1, _words(p["topic"]))):
            for w in ws:
                k = _stem(w.lower())
                if k in seen:
                    continue
                seen.add(k)
                d = df(w)
                if 1 <= d <= max(3, 0.12 * nq):
                    terms.append((strength, d, w))
        terms.sort()
        strong = [w for s, _, w in terms if s == 0][:3]
        terms = [w for _, _, w in terms[:5]]
        res = {"terms": terms, "mentions": []}
        if p["session"] >= last_held:
            res["status"], res["label"] = "nema_kasnijih_sjednica", "nema kasnijih sjednica za provjeru"
            out[p["id"]] = res
            continue
        # two subject terms, at least one of them a name; or one long, rare name on its own
        queries = [f"{_stem(a)} {_stem(b)}" for i, a in enumerate(terms) for b in terms[i + 1:]
                   if a in strong or b in strong]
        queries += [_stem(w) for w in strong if len(w) >= 7 and df(w) <= max(2, 0.04 * nq)]
        hits, keys = [], set()
        for m in queries:
            for r in q("""SELECT i.session, i.no, i.sub, i.title FROM items_fts JOIN items i ON i.rowid = items_fts.rowid
                          WHERE items_fts MATCH ? AND i.city = ? AND i.session > ? AND i.session <= ?
                          ORDER BY i.session LIMIT 5""", m, city, p["session"], last_held):
                if ("t", r["session"], r["no"], r["sub"]) not in keys:
                    keys.add(("t", r["session"], r["no"], r["sub"]))
                    hits.append({"kind": "točka dnevnog reda", "session": r["session"], "text": r["title"][:200],
                                 "href": f"#{city}/tocka-{r['session']}-{r['no']}-{r['sub']}", "matched": m})
            for r in q("""SELECT x.id, x.session, x.member, x.question FROM questions_fts JOIN questions x
                          ON x.id = questions_fts.rowid WHERE questions_fts MATCH ? AND x.city = ? AND x.session > ?
                          AND x.session <= ? ORDER BY x.session LIMIT 5""", m, city, p["session"], last_held):
                if ("q", r["id"]) not in keys:
                    keys.add(("q", r["id"]))
                    hits.append({"kind": "pitanje u aktualnom satu", "session": r["session"],
                                 "text": f"{r['member']}: {r['question'][:180]}", "href": f"#{city}/pitanje-{r['id']}",
                                 "matched": m})
            for r in q("""SELECT s.video_id, s.session, s.start, s.text FROM segments_fts JOIN segments s
                          ON s.id = segments_fts.rowid WHERE segments_fts MATCH ? AND s.city = ? AND s.session > ?
                          AND s.session <= ? ORDER BY s.session, s.start LIMIT 3""", m, city, p["session"], last_held):
                if ("s", r["video_id"], int(r["start"]) // 60) not in keys:
                    keys.add(("s", r["video_id"], int(r["start"]) // 60))
                    hits.append({"kind": "snimka sjednice", "session": r["session"], "text": r["text"][:200],
                                 "href": link(r["video_id"], r["start"]), "at": hms(r["start"]), "matched": m})
        hits.sort(key=lambda h: (h["session"], h["kind"]))
        res["mentions"] = hits[:8]
        res["status"], res["label"] = (("spominje_se_kasnije", "spominje se kasnije (ispunjenje neprovjereno)") if hits
                                       else ("nije_pronađeno", "kasnije se ne spominje u dostupnim podacima"))
        out[p["id"]] = res
    _ASK_CACHE[ck] = out
    return out


PromiseStatus = Annotated[Literal["", "rok_prošao", "otvoreno", "bez_roka"], BeforeValidator(_norm_status),
                          Field(description="'' all; 'rok_prošao' deadline passed; 'otvoreno' future deadline; "
                                            "'bez_roka' no date. 'expired'/'open' also accepted")]


@mcp.tool()
def promises(city: City = "zagreb",
             speaker: Annotated[str, Field(description="Part of the speaker's name, e.g. 'Tomašević'")] = "",
             session: Annotated[int | None, Field(description="Only promises made at this session")] = None,
             status: PromiseStatus = "") -> dict:
    """Promise tracker: commitments the mayor and city officials made when answering councillors'
    questions (aktualni sat, from the official fonogram): who, what (quote), by when (deadline phrase and
    approximate date). status='rok_prošao' lists those whose deadline has passed: 'status_label' says
    "rok prošao, ispunjenje neprovjereno"; 'otvoreno' future deadlines, 'bez_roka' no explicit date.
    'followup' = the "provjeri ispunjenje" helper: whether the subject comes up again in a LATER session
    (agenda item, question, transcript) with links; 'spominje se kasnije' is NOT a claim that it was delivered.
    Details: promise_followup(id). Machine-extracted with rules: verify the quote. Only Zagreb has fonograms."""
    rows = q(f"""SELECT p.id, p.session, s.date AS said_on, p.speaker, p.asked_by, p.topic, p.quote, p.deadline,
                        p.deadline_date, p.question_id
                 FROM promises p JOIN sessions s ON s.city = p.city AND s.n = p.session
                 WHERE p.city = ? {"AND p.speaker LIKE ?" if speaker else ""} {"AND p.session = ?" if session else ""}
                 ORDER BY p.session DESC, p.id""",
             city, *([f"%{speaker}%"] if speaker else []), *([session] if session else []))
    from datetime import date
    today = date.today().isoformat()
    for r in rows:
        r["status"] = "bez_roka" if not r["deadline_date"] else ("rok_prošao" if r["deadline_date"] < today else "otvoreno")
        r["status_label"] = {"rok_prošao": "rok prošao, ispunjenje neprovjereno", "otvoreno": "rok u budućnosti",
                             "bez_roka": "bez roka"}[r["status"]]
    fu = _followups(city)
    for r in rows:
        f = fu.get(r["id"]) or {}
        r["followup"] = {"status": f.get("status"), "label": f.get("label"), "mentions": len(f.get("mentions", [])),
                         "first": f["mentions"][0] if f.get("mentions") else None}
    if status:
        rows = [r for r in rows if r["status"] == status]
    out = {"count": len(rows), "promises": rows}
    if not rows and city != "zagreb":
        out["note"] = f"{city}: no question-hour fonograms, so no promises are extracted"
    return out


@mcp.tool()
def promise_followup(promise_id: Annotated[int, Field(description="Promise id from promises()")],
                     city: City = "zagreb") -> dict:
    """'Provjeri ispunjenje': for one promise, every later mention of its subject (agenda items of later
    sessions, later councillors' questions and their official answers, transcripts) with links, plus the
    subject terms used. A mention means the topic came up again, NOT that the promise was kept: read it."""
    p = q("SELECT id, session, speaker, topic, quote, deadline, deadline_date, question_id FROM promises "
          "WHERE city = ? AND id = ?", city, promise_id)
    if not p:
        raise ToolError(f"no promise {promise_id} in {city}; ids come from promises()")
    return {"promise": p[0], **_followups(city).get(promise_id, {}),
            "caveat": "Spominjanje teme nije dokaz ispunjenja: pročitajte poveznice."}


@mcp.tool()
def member_record(name: Annotated[str, Field(description="Full name or part of it, e.g. 'Selak Raspudić'")],
                  city: City = "zagreb") -> dict:
    """A councillor's record: party, attendance, how often they voted za/protiv/suzdrzan, how often they
    were absent ('odsutan': not at the session) versus present but not voting ('nije_glasovao'), votes
    against their own party's majority (Zagreb), and the questions they asked. Cities without a published
    roll call (Brod) return votes=null, votes_available=false and votes_note (unknown, not zero). If the name matches
    several councillors (e.g. a shared surname), returns 'ambiguous' with the candidates instead."""
    m = q("SELECT name, party FROM members WHERE city = ? AND name LIKE ?", city, f"%{name.strip()}%") if name.strip() else []
    if not m:
        raise ToolError(f"no councillor matching {name!r} in {city}; names: "
                        + ", ".join(r["name"] for r in q("SELECT name FROM members WHERE city = ? ORDER BY name", city)))
    exact = [r for r in m if r["name"].lower() == name.strip().lower()]
    if len(m) > 1 and not exact:
        return {"ambiguous": True, "error": f"{len(m)} councillors match {name!r}; call again with the full name",
                "candidates": m}
    m = (exact or m)[0]
    n = m["name"]
    att = q("SELECT count(*) total, sum(present) present FROM attendance WHERE city = ? AND member = ?", city, n)[0]
    votes = q("SELECT vote, count(*) c FROM votes WHERE city = ? AND member = ? GROUP BY vote", city, n)
    rebel = q("""WITH pm AS (SELECT v.session, v.item_no, v.sub, v.vote, count(*) c,
                                    row_number() OVER (PARTITION BY v.session, v.item_no, v.sub
                                                       ORDER BY count(*) DESC) rk
                             FROM votes v JOIN members mm ON mm.city = v.city AND mm.name = v.member
                             WHERE v.city = ? AND mm.party = ? AND v.vote NOT IN ('odsutan', 'nije_glasovao')
                             GROUP BY v.session, v.item_no, v.sub, v.vote)
                 SELECT v.session, v.item_no, v.sub, i.title, v.vote AS own_vote, pm.vote AS party_majority
                 FROM votes v JOIN pm ON pm.session = v.session AND pm.item_no = v.item_no AND pm.sub = v.sub
                                     AND pm.rk = 1
                 JOIN items i ON i.city = v.city AND i.session = v.session AND i.no = v.item_no AND i.sub = v.sub
                 WHERE v.city = ? AND v.member = ? AND v.vote NOT IN ('odsutan', 'nije_glasovao') AND v.vote != pm.vote""",
              city, m["party"], city, n)
    asked = q("SELECT session, question, answered_by FROM questions WHERE city = ? AND member = ? ORDER BY session DESC",
              city, n)
    per_member = q("SELECT 1 FROM votes WHERE city = ? LIMIT 1", city)
    if not per_member:  # e.g. Brod: minutes give totals only, no roll call -> unknown, not zero
        return {**m, "city": city, "attendance": f"{att['present'] or 0}/{att['total']} sjednica",
                "votes": None, "votes_available": False,
                "votes_note": f"{city}: poimenično glasovanje se ne objavljuje (samo zbrojevi po točki), "
                              "pa se glas pojedinog vijećnika iz ovih podataka ne može znati",
                "against_party_majority": None, "questions": asked}
    return {**m, "city": city, "attendance": f"{att['present'] or 0}/{att['total']} sjednica",
            "votes_available": True,
            "votes": {"za": 0, "protiv": 0, "suzdrzan": 0, "odsutan": 0, "nije_glasovao": 0,
                      **{r["vote"]: r["c"] for r in votes}},
            "vote_legend": {"odsutan": "nije bio na sjednici",
                            "nije_glasovao": "bio na sjednici, nije glasovao (u PDF-u 'Odsutan' ili redak bez oznake)"},
            "bloc": bloc(city, m["party"]), "against_party_majority": rebel, "questions": asked}


@mcp.tool()
def get_question(question_id: Annotated[int, Field(description="Question id from search() or member_record()")]) -> dict:
    """A councillor's question (aktualni sat) with the official verbatim transcript (fonogram) of the
    question and the oral answer (ids come from search or member_record). 'answerer_role' is the role of who
    answered ("zamjenik gradonačelnika"), from the source's 'odgovor' field."""
    r = q("SELECT * FROM questions WHERE id = ?", question_id)
    if not r:
        raise ToolError(f"no question {question_id}; ids come from search() or member_record()")
    r = r[0]
    r["url"] = absolute(r["city"], r["url"])
    role = re.sub(r"\s*\b(usmeno|pismeno)\b\.?", "", r.get("answered_by") or "")
    role = re.sub(r"\s+Grada\s+[Zz]agreba\.?", "", role).strip(" .")
    r["answerer_role"] = role[:1].lower() + role[1:] if role else None
    r["answer_mode"] = "usmeno" if "usmeno" in (r.get("answered_by") or "") else "pismeno" if "pismeno" in (r.get("answered_by") or "") else None
    return r


@mcp.tool()
def get_minutes(session: Session, contains: Annotated[str, Field(description="Only paragraphs with this word")] = "",
                city: City = "zagreb") -> dict:
    """Official minutes (zapisnik) of a session as text. With 'contains', returns only the paragraphs
    mentioning that word (the full minutes are long; Brod's are near-verbatim)."""
    _check_session(city, session)
    r = q("SELECT minutes_url, minutes_text, date FROM sessions WHERE city = ? AND n = ?", city, session)
    if not r[0]["minutes_text"]:
        held = r[0]["date"] and r[0]["date"] <= date.today().isoformat()
        return {"published": False, "error": (f"minutes of {city} session {session} ({r[0]['date']}) not published yet"
                                              if held else f"{city} session {session} is scheduled for {r[0]['date']}, not held yet")}
    text = r[0]["minutes_text"]
    if contains:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if contains.lower() in p.lower()]
        text = "\n\n".join(paras[:20]) or "(no paragraph mentions it)"
    return {"url": absolute(city, r[0]["minutes_url"]), "text": text[:30000]}


# "Pitaj Vijećnicu": six example questions, each mapped to the tool that answers it (no LLM). The web landing
# panel shows them as buttons; an MCP client gets the same answers from the tools named in "tool".
ASK = [
    ("obecanja", "Koja su obećanja gradske uprave prošla rok i spominju li se kasnije?", "zagreb"),
    ("vrtici", "Što je Skupština odlučivala o vrtićima?", "zagreb"),
    ("protiv-kluba", "Tko najčešće glasa protiv većine vlastitog kluba?", "zagreb"),
    ("nije-glasovao", "Tko je najčešće na sjednici, a ne glasuje?", "zagreb"),
    ("tramvaj", "Što se na Skupštini govorilo o tramvaju?", "zagreb"),
    ("zapisnik", "Koliko stroj ubrza pisanje zapisnika?", "zagreb"),
    ("brod-zadnja", "Što je vijeće odlučilo na zadnjoj sjednici?", "brod"),
    ("brod-snimka", "Kako se glasalo prije objave zapisnika?", "brod"),
    ("brod-vrtici", "Što se govorilo o vrtićima i školama?", "brod"),
    ("brod-pitanja", "Tko je postavio vijećnička pitanja?", "brod"),
    ("brod-vlast", "Tko čini vlast u Gradskom vijeću?", "brod"),
    ("brod-tocnost", "Koliko je točan strojni zapis snimke?", "brod"),
    ("krk-zadnja", "Što je vijeće odlučilo na zadnjoj sjednici?", "krk"),
    ("krk-odbijeno", "Koji prijedlozi nisu prošli ili su skinuti s dnevnog reda?", "krk"),
    ("krk-pitanja", "Što su vijećnici pitali gradonačelnika?", "krk"),
    ("krk-vrtici", "Što se govorilo o vrtićima?", "krk"),
    ("krk-vlast", "Tko čini vlast u Gradskom vijeću?", "krk"),
    ("rijeka-zadnja", "Što je vijeće odlučilo na zadnjoj sjednici?", "rijeka"),
    ("rijeka-odbijeno", "Što vijeće nije prihvatilo?", "rijeka"),
    ("rijeka-pitanja", "Što su vijećnici pitali gradonačelnicu?", "rijeka"),
    ("rijeka-autotrolej", "Što je vijeće odlučivalo o Autotroleju i autobusima?", "rijeka"),
    ("rijeka-vlast", "Tko čini vlast u Gradskom vijeću?", "rijeka"),
]


def fmt_date(d):
    return ".".join(reversed(d.split("-"))) + "." if d else ""


def hr_plural(n, one, few, many):
    a, b = n % 10, n % 100
    return f"{n} {one if a == 1 and b != 11 else few if 2 <= a <= 4 and not 12 <= b <= 14 else many}"


_ASK_CACHE = {}
VL = {"za": "za", "protiv": "protiv", "suzdrzan": "suzdržan", "nije_glasovao": "nije glasovao", "odsutan": "odsutan"}


def ask(key: str) -> dict:
    """Cached per DB version (the rebel scan calls member_record for every councillor, ~3 s)."""
    ck = (key, DB.stat().st_mtime)
    if ck not in _ASK_CACHE:
        _ASK_CACHE.clear() if len(_ASK_CACHE) > 50 else None
        _ASK_CACHE[ck] = _ask(key)
    return _ASK_CACHE[ck]


def _ask(key: str) -> dict:
    """Answer one of the example questions (keys in ASK) with real data; returns a card:
    {question, tool, headline, rows: [{text, sub, href}], more: {label, href}}."""
    k = {a[0]: a for a in ASK}.get(key)
    if not k:
        raise ToolError(f"unknown question {key!r}; keys: {', '.join(a[0] for a in ASK)}")
    _, question, city = k
    out = {"key": key, "question": question, "city": city}
    if key == "protiv-kluba":
        names = [r["name"] for r in q("SELECT name FROM members WHERE city = 'zagreb'")]
        recs = [member_record(n, "zagreb") for n in names]
        # independents ("Nestranački") are not a club: no majority to vote against
        recs = [r for r in recs if "against_party_majority" in r and not (r["party"] or "").startswith("Nestran")]
        recs.sort(key=lambda r: -len(r["against_party_majority"]))
        top = recs[:5]
        out["tool"] = "member_record(name) za svakog zastupnika → against_party_majority"
        out["headline"] = (f"Najviše glasova drukčijih od većine vlastitog kluba: {top[0]['name']} ({short(top[0]['party'])}),"
                           f" {len(top[0]['against_party_majority'])} puta (poimenična glasovanja, sve sjednice saziva).")
        out["rows"] = [{"text": f"{r['name']}: {len(r['against_party_majority'])}×",
                        "sub": short(r["party"]) + (f" · npr. {r['against_party_majority'][0]['session']}. sjednica, točka "
                                             f"{r['against_party_majority'][0]['item_no']}: "
                                             f"{VL.get(r['against_party_majority'][0]['own_vote'])} (klub: "
                                             f"{VL.get(r['against_party_majority'][0]['party_majority'])})"
                                             if r["against_party_majority"] else ""),
                        "href": f"#zagreb/zastupnik-{r['name']}"} for r in top]
        out["more"] = {"label": "Svi zastupnici", "href": "#zagreb/zastupnici"}
    elif key == "obecanja":
        p = promises("zagreb", status="rok_prošao")
        allp = promises("zagreb")
        later = sum(1 for x in p["promises"] if x["followup"]["status"] == "spominje_se_kasnije")
        out["tool"] = "promises(status='rok_prošao') → followup (promise_followup)"
        out["headline"] = (f"{p['count']} od {allp['count']} obećanja iz aktualnog sata imaju rok koji je prošao. "
                           f"Za {later} od njih tema se spominje na kasnijim sjednicama (poveznice niže); "
                           "je li obećanje ispunjeno, to spominjanje ne dokazuje.")
        ordered = sorted(p["promises"], key=lambda x: x["followup"]["status"] != "spominje_se_kasnije")
        out["rows"] = [{"text": f"„{x['quote'][:160]}”", "sub": f"{x['speaker']} · {x['session']}. sjednica ({fmt_date(x['said_on'])})"
                        f" · rok: {x['deadline']} (≈ {fmt_date(x['deadline_date'])}) · {x['followup']['label']}",
                        "href": f"#zagreb/pitanje-{x['question_id']}~p{x['id']}"} for x in ordered[:4]]
        out["more"] = {"label": "Sva obećanja s prošlim rokom", "href": "#zagreb/obecanja-rok_prošao"}
    elif key == "vrtici" or key.endswith(("-vrtici", "-autotrolej")):
        term, what = ("Autotrolej", "Autotrolej spominje") if key.endswith("-autotrolej") else ("vrtić", "Vrtiće spominje")
        r = search(term, city, limit=50)
        out["tool"] = f"search(query='{term}', city='{city}')"
        out["headline"] = (f"{what} {hr_plural(len(r['agenda_items']), 'točka', 'točke', 'točaka')} dnevnog reda"
                           + (f" i {hr_plural(len(r['questions']), 'pitanje', 'pitanja', 'pitanja')} vijećnika" if r["questions"] else "")
                           + f"; u transkribiranim snimkama {hr_plural(len(r['said_in_session']), 'mjesto', 'mjesta', 'mjesta')}.")
        rows = [{"text": i["title"][:150], "sub": f"{i['session']}. sjednica, točka {i['no']}" + (f" · {i['status']}" if i["status"] else "")
                 + (f" · {i['za']} za / {i['protiv']} protiv / {i['suzdrzano']} suzdr." if i["za"] is not None else ""),
                 "href": f"#{city}/tocka-{i['session']}-{i['no']}-{i['sub']}"} for i in r["agenda_items"][:3]]
        rows += [{"text": re.sub(r"\*\*", "", h["text"])[:180], "sub": f"▶ {h['session']}. sjednica, {h['at']} (snimka)",
                  "href": h["url"]} for h in r["said_in_session"][:2]]
        out["rows"] = rows
        out["more"] = {"label": "Svi pogoci", "href": f"#{city}/trazi-{term}"}
    elif key.endswith("-zadnja"):
        sess = q("""SELECT max(s.n) n FROM sessions s WHERE s.city = ? AND s.date <= date('now', 'localtime')
                    AND EXISTS (SELECT 1 FROM items i WHERE i.city = ? AND i.session = s.n)""", city, city)[0]["n"]
        s = get_session(sess, city)
        out["tool"] = f"get_session(session={sess}, city='{city}')"
        voted = [i for i in s["items"] if i["za"] is not None or i.get("snimka")]
        news = any((i.get("totals_note") or {}).get("kind") == "vijest" for i in s["items"])
        src = ("službenog zapisnika" if s["minutes_published"] else
               "gradske vijesti o sjednici (zapisnik još nije objavljen)" if news else
               "snimke (zapisnik još nije objavljen, neslužbeno)")
        out["headline"] = (f"{sess}. sjednica ({fmt_date(s['date'])}): {hr_plural(len(s['items']), 'točka', 'točke', 'točaka')}"
                           f" dnevnog reda; za {hr_plural(len(voted), 'točku', 'točke', 'točaka')} rezultat glasovanja je iz {src}.")
        rows = []
        for i in s["items"]:
            if i["za"] is not None:
                res = (f"{i['za']} za · {i['protiv']} protiv · {i['suzdrzano'] or 0} suzdr." if i["protiv"] is not None
                       else f"{i['za']} za (ostalo nije navedeno)")
            elif i.get("snimka"):
                sn = i["snimka"]
                res = ("iz snimke: " + (f"{sn['n_votes']} glasovanja" if sn["n_votes"] > 1 else
                       "jednoglasno" if sn["unanimous"] and sn["za"] is None else
                       f"{sn['za']} za · {sn['protiv'] or 0} protiv · {sn['suzdrzano'] or 0} suzdr.") + f", {sn['outcome']}")
            else:
                continue
            rows.append({"text": i["title"][:140], "sub": f"točka {i['no']} · {res}", "href": f"#{city}/tocka-{sess}-{i['no']}-{i['sub']}"})
        out["rows"] = rows[:5]
        out["more"] = {"label": f"Cijela {sess}. sjednica", "href": f"#{city}/sjednica-{sess}"}
    elif key.endswith("-odbijeno"):
        rows = q("""SELECT session, no, sub, title, status, za, protiv, suzdrzano FROM items
                    WHERE city = ? AND status IN ('odbijen', 'povučen') ORDER BY session DESC, no""", city)
        out["tool"] = f"get_session(session, city='{city}') → items[].status (odbijen / povučen)"
        nb = sum(r["status"] == "odbijen" for r in rows)
        out["headline"] = (f"Odbijeno na glasovanju: {hr_plural(nb, 'prijedlog', 'prijedloga', 'prijedloga')}; "
                           f"skinuto s dnevnog reda ili povučeno: {len(rows) - nb}. Neki se prijedlozi vraćaju više puta.")
        out["rows"] = [{"text": r["title"][:150],
                        "sub": f"{r['session']}. sjednica, točka {r['no']} · " + (
                            f"odbijeno {r['za']} za / {r['protiv']} protiv / {r['suzdrzano'] or 0} suzdr."
                            if r["status"] == "odbijen" and r["za"] is not None else
                            "odbijeno" if r["status"] == "odbijen" else "skinuto s dnevnog reda"),
                        "href": f"#{city}/tocka-{r['session']}-{r['no']}-{r['sub']}"} for r in rows[:6]]
        out["more"] = {"label": "Sve sjednice", "href": f"#{city}/sjednice"}
    elif key.endswith("-pitanja") and q("SELECT 1 FROM questions WHERE city = ? LIMIT 1", city):
        rows = q("""SELECT id, session, member, party, question, answered_by FROM questions WHERE city = ?
                    ORDER BY session DESC, id""", city)
        out["tool"] = f"search(query, city='{city}') → questions; get_question(id)"
        out["headline"] = (f"{hr_plural(len(rows), 'pitanje', 'pitanja', 'pitanja')} vijećnika u aktualnom satu "
                           f"({hr_plural(len({r['member'] for r in rows}), 'vijećnik', 'vijećnika', 'vijećnika')}), s odgovorima "
                           "iz zapisnika ili gradske vijesti.")
        out["rows"] = [{"text": r["question"][:160], "sub": f"{r['member']} ({short(r['party'])}) · {r['session']}. sjednica"
                        + (f" · odgovara {r['answered_by']}" if r["answered_by"] else ""),
                        "href": f"#{city}/pitanje-{r['id']}"} for r in rows[:6]]
        out["more"] = {"label": "Vijećnici", "href": f"#{city}/zastupnici"}
    elif key.endswith("-pitanja"):
        t = q("""SELECT t.speaker, t.session, t.video_id, t.start, m.party FROM speaker_turns t
                 LEFT JOIN members m ON m.city = t.city AND m.name = t.speaker
                 WHERE t.city = ? AND t.kind = 'vijećničko pitanje' ORDER BY t.session DESC, t.start""", city)
        sessions = sorted({r["session"] for r in t})
        out["tool"] = f"speaker_turns(session, city='{city}') → kind='vijećničko pitanje'"
        out["headline"] = (f"U transkribiranim snimkama ({', '.join(f'{x}.' for x in sessions)} sjednica) predsjedatelj je "
                           f"prozvao {hr_plural(len({r['speaker'] for r in t}), 'vijećnika', 'vijećnika', 'vijećnika')} "
                           "na vijećničko pitanje. Strojno prepoznato iz poziva predsjedatelja.")
        out["rows"] = [{"text": f"{r['speaker']}", "sub": f"{short(r['party'])} · {bloc(city, r['party']) or ''} · "
                        f"{r['session']}. sjednica, ▶ {hms(r['start'])}", "href": link(r["video_id"], r["start"])} for r in t[:6]]
        out["more"] = {"label": "Vijećnici", "href": f"#{city}/zastupnici"}
    elif key.endswith("-vlast"):
        g = governing(city)
        seats = q("""SELECT party, count(*) c FROM members WHERE city = ? AND party IS NOT NULL
                     GROUP BY party ORDER BY c DESC""", city)
        out["tool"] = "list_cities() → governing"
        out["headline"] = ((f"Gradonačelnica je {g['mayor']}; njezin klub ima " if g.get("mayor_f") else f"Gradonačelnik je {g['mayor']}; njegova lista ima ")
                           + f"{g['seats']} od {g['of']} vijećnika "
                           f"(prema: {g['seats_basis']})." + (f" {g['majority_note']}." if g.get("majority_note") else ""))
        out["rows"] = [{"text": f"{short(r['party'])}: {r['c']}", "sub": "vlast" if r["party"] in g["parties"] else "oporba / ostali",
                        "href": f"#{city}/zastupnici"} for r in seats]
        out["more"] = {"label": "Svi vijećnici", "href": f"#{city}/zastupnici"}
    elif key == "brod-tocnost":
        a = asr_quality("brod")
        out["tool"] = "list_cities() → asr_quality (eval_brod.py)"
        if not a:
            out["headline"], out["rows"] = "Mjerenje još nije gotovo.", []
        else:
            v = a["votes"]
            out["headline"] = (f"Na {a['session']}. sjednici {str(a['agreement_pct']).replace('.', ',')} % riječi strojnog zapisa "
                               f"slaže se s gotovo doslovnim službenim zapisnikom ({a['coverage']}, {a['words_compared']} riječi uspoređeno). "
                               "Zapisnik je uređen tekst (bez poštapalica, ispravljena gramatika), pa je dio razlike u "
                               "zapisniku, a ne u transkriptu; ovo je donja granica točnosti.")
            out["rows"] = [{"text": f"Glasovi iz snimke: {v['exact_of_numbered']}", "sub": "točaka gdje je izgovoren broj, točno do glasa"
                            f" (još {v['compared'] - v['with_number']} „jednoglasno” bez broja)",
                            "href": "#brod/kvaliteta"},
                           {"text": f"Govornici: odziv {round(100 * a['speakers']['recall'])} %, preciznost "
                                    f"{round(100 * a['speakers']['precision'])} %", "sub": "tko govori, prema zapisniku",
                            "href": "#brod/kvaliteta"}]
        out["more"] = {"label": "Metoda i usporedba odlomaka", "href": "#brod/kvaliteta"}
    elif key == "tramvaj":
        r = search("tramvaj", "zagreb", limit=50)
        out["tool"] = "search(query='tramvaj', city='zagreb')"
        out["headline"] = (f"Tramvaj spominju {hr_plural(len(r['agenda_items']), 'točka', 'točke', 'točaka')} dnevnog reda, "
                           f"{hr_plural(len(r['said_in_session']), 'mjesto', 'mjesta', 'mjesta')} u transkriptima "
                           f"snimki i {hr_plural(len(r['questions']), 'pitanje', 'pitanja', 'pitanja')} zastupnika.")
        rows = [{"text": re.sub(r"\*\*", "", h["text"])[:180], "sub": f"▶ {h['session']}. sjednica, {h['at']} (snimka)",
                 "href": h["url"]} for h in r["said_in_session"][:2]]
        rows += [{"text": i["title"][:150], "sub": f"{i['session']}. sjednica, točka {i['no']} · {i['status'] or ''}"
                  + (f" · {i['za']} za / {i['protiv']} protiv / {i['suzdrzano']} suzdr." if i["za"] is not None else ""),
                  "href": f"#zagreb/tocka-{i['session']}-{i['no']}-{i['sub']}"} for i in r["agenda_items"][:3]]
        out["rows"] = rows
        out["more"] = {"label": "Svi pogoci", "href": "#zagreb/trazi-tramvaj"}
    elif key == "nije-glasovao":
        rows = q("""SELECT m.name, m.party, sum(v.vote = 'nije_glasovao') nije, count(*) n
                    FROM votes v JOIN members m ON m.city = v.city AND m.name = v.member
                    WHERE v.city = 'zagreb' AND v.vote != 'odsutan' GROUP BY m.name ORDER BY nije DESC LIMIT 5""")
        total = q("SELECT count(*) c FROM votes WHERE city = 'zagreb' AND vote = 'nije_glasovao'")[0]["c"]
        out["tool"] = "member_record(name) → votes.nije_glasovao (bio na sjednici, nije glasovao)"
        out["headline"] = (f"Najčešće prisutan, a bez glasa: {rows[0]['name']} ({short(rows[0]['party'])}), u {rows[0]['nije']} od "
                           f"{rows[0]['n']} glasovanja. Ukupno {total} takvih glasova: u PDF-u stoji „Odsutan” ili redak "
                           "bez ikakve oznake, a tek popis nazočnosti pokazuje da je zastupnik bio na sjednici.")
        out["rows"] = [{"text": f"{r['name']}: {r['nije']} / {r['n']}", "sub": short(r["party"]),
                        "href": f"#zagreb/zastupnik-{r['name']}"} for r in rows]
        out["more"] = {"label": "Tablica zastupnika", "href": "#zagreb/zastupnici"}
    elif key == "zapisnik":
        ev = minutes_evaluation(14, "zagreb")["summary"]
        clerk = json.loads((ROOT / "reports" / "clerk_time_zagreb_14.json").read_text())
        out["tool"] = "minutes_evaluation(session=14) + draft_minutes(session, item_no)"
        out["headline"] = (f"Nacrt zapisnika za {hr_plural(clerk['drafted'], 'točku', 'točke', 'točaka')} 14. sjednice "
                           f"nastaje za {str(clerk['draft_seconds']).replace('.', ',')} s; PDF službenog zapisnika izrađen je "
                           f"{clerk['days_after_last_session_day']} dana nakon sjednice (datum izrade PDF-a, ne objave).")
        out["rows"] = [
            {"text": f"Govornici: {ev['speakers_found']}/{ev['speakers_in_minutes']} iz zapisnika pronađeno u snimci",
             "sub": "jedina stvarno izmjerena stavka; brojke glasova prepisuju se iz poimeničnog glasovanja", "href": "#zagreb/zapisnik"},
            {"text": f"Preciznost govornika {ev['speaker_precision_pct']:g} %", "sub": "nijedan prepoznati govornik nije pogrešan",
             "href": "#zagreb/zapisnik"},
            {"text": f"Završna riječ predlagatelja: {ev['closing_word_ok']}, vrsta odluke {ev['decision_type_ok']}",
             "sub": "usporedba sa službenim zapisnikom", "href": "#zagreb/zapisnik"}]
        out["more"] = {"label": "Nacrt vs službeni zapisnik", "href": "#zagreb/zapisnik"}
    elif key == "brod-snimka":
        sess = q("SELECT max(session) s FROM spoken_votes WHERE city = 'brod'")[0]["s"]
        sv = q("""SELECT item_no, n, label, za, protiv, suzdrzano, unanimous, outcome, video_id, t FROM spoken_votes
                  WHERE city = 'brod' AND session = ? ORDER BY item_no, n""", sess)
        items = q("SELECT count(*) c FROM items WHERE city = 'brod' AND session = ?", sess)[0]["c"]
        got = len({v["item_no"] for v in sv})
        voting = q("""SELECT count(*) c FROM items WHERE city = 'brod' AND session = ? AND title NOT LIKE 'Aktualni sat%'""", sess)[0]["c"]
        numbered = len({v["item_no"] for v in sv if v["za"] is not None})
        aq = asr_quality("brod")
        out["tool"] = f"get_session(session={sess}, city='brod') → items[].snimka"
        out["headline"] = (f"Za {got} od {voting} točaka {sess}. sjednice o kojima se glasuje (bez aktualnog sata; ukupno {items}) "
                           f"rezultat je izvučen iz riječi predsjedatelja u tonskom zapisu, prije službenog zapisnika "
                           f"(neslužbeno); za {numbered} je izgovoren i broj glasova."
                           + (f" Provjera na {aq['session']}. sjednici: {aq['votes']['exact_of_numbered']} takvih točaka "
                              "točno do glasa prema zapisniku." if aq and aq["votes"].get("exact_of_numbered") else ""))
        rows, seen = [], set()
        per = {}
        for v in sv:
            per[v["item_no"]] = per.get(v["item_no"], 0) + 1
        for v in sv:
            if v["item_no"] in seen:
                continue
            seen.add(v["item_no"])
            if per[v["item_no"]] > 1:
                rows.append({"text": f"Točka {v['item_no']}: {per[v['item_no']]} zasebnih glasovanja (npr. "
                             f"{(v['label'] or '').strip()[:50]}: {v['za']} za · {v['protiv'] or 0} protiv · "
                             f"{v['suzdrzano'] or 0} suzdr.)", "sub": f"▶ {hms(v['t'])} u snimci",
                             "href": f"#brod/tocka-{sess}-{v['item_no']}-1"})
                continue
            res = ("jednoglasno" + (f" ({v['za']} za)" if v["za"] else "") if v["unanimous"]
                   else f"{v['za']} za · {v['protiv'] or 0} protiv · {v['suzdrzano'] or 0} suzdr.")
            rows.append({"text": f"Točka {v['item_no']}: {res}, {v['outcome']}", "sub": f"▶ {hms(v['t'])} u snimci",
                         "href": f"#brod/tocka-{sess}-{v['item_no']}-1"})
        out["rows"] = rows[:5]
        out["more"] = {"label": f"{sess}. sjednica Slavonskog Broda", "href": f"#brod/sjednica-{sess}"}
    return out


@mcp.tool()
def example_questions(key: Annotated[str, Field(description="Question key; '' lists the questions")] = "",
                      city: AnyCity = "") -> dict:
    """'Pitaj Vijećnicu': six example questions per city answered from the data with a fixed tool mapping
    (the same ones the web page shows as buttons). key='' lists them (city='' = all); key='obecanja' etc.
    returns the answer card with the tool call that produced it. Unknown key = error with the valid keys."""
    if key:
        return ask(key)
    return {"questions": [{"key": a[0], "question": a[1], "city": a[2]} for a in ASK if not city or a[2] == city]}


@mcp.tool()
def transcript_quality(city: City = "brod") -> dict:
    """How accurate the machine transcript is, measured against near-verbatim official minutes (Brod session 9):
    word agreement (1 - WER over aligned passages), method, five passages side by side, speaker and vote checks.
    Zagreb has no verbatim minutes for debates, so there is no measurement there (returns measured=false)."""
    f = sorted((ROOT / "reports").glob(f"asr_eval_{city}_*.json"))
    full = [json.loads(p.read_text()) for p in f]
    full = [d for d in full if not d.get("partial")]
    if not full:
        return {"measured": False, "note": f"{city}: no verbatim reference to measure against yet"}
    d = full[-1]
    return {"measured": True, **asr_quality(city), "passages": d["passages"],
            "speaker_sample": d["speakers"].get("sample", [])[:10], "votes_detail": d["votes"]}


@mcp.prompt()
def sazetak_sjednice(session: int, city: str = "zagreb") -> str:
    """Plain-language summary of a session for citizens."""
    return (f"Napiši sažetak {session}. sjednice gradskog vijeća/skupštine (city='{city}') za građane, "
            "jednostavnim jezikom. Koristi get_session, get_item za važne točke, item_debate, search i "
            "get_transcript za raspravu. Za svaku važnu odluku: što je odlučeno, kako se glasalo, jedna "
            "rečenica iz rasprave s poveznicom na trenutak snimke. Na kraju: tko je bio odsutan.")


@mcp.prompt()
def nacrt_zapisnika(session: int, part: int = 1, city: str = "zagreb") -> str:
    """Draft minutes (zapisnik) from the recording, in the council's own format."""
    return (f"Izradi nacrt zapisnika {session}. sjednice (city='{city}', snimka {part}) u formatu službenih "
            "zapisnika tog grada (pogledaj get_minutes jedne ranije sjednice kao uzor): otvaranje, kvorum, "
            "dnevni red, za svaku točku tko je govorio i ukratko što, rezultat glasovanja (get_item). "
            "Čitaj transkript s item_debate ili get_transcript u blokovima po 20 minuta. Ako postoji "
            "službeni zapisnik (get_minutes), na kraju usporedi nacrt sa službenim i navedi razlike.")


# --- web page + JSON API for people without an MCP client (same process, HTTP mode only) ---
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, Response  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"


def _int(req, key, default=None):
    v = req.query_params.get(key)
    return int(v) if v and v.isdigit() else default


def _city(req):
    c = _norm_city(req.query_params.get("city", "zagreb"))
    return c if c in GOVERNING else "zagreb"


def jr(fn, *args, **kw):
    """Call a tool for the web API: ToolError (bad input / not found) -> HTTP 404 with {"error": …}."""
    try:
        return JSONResponse(fn(*args, **kw))
    except ToolError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@mcp.custom_route("/", methods=["GET"])
async def page(req: Request):
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@mcp.custom_route("/demo", methods=["GET"])
async def demo_page(req: Request):
    """'Kako agent odgovara': recorded demo conversations (demo/record.py → demo/demo.json)."""
    return FileResponse(WEB / "demo.html", headers={"Cache-Control": "no-cache"})


@mcp.custom_route("/feed", methods=["GET"])
async def feed_page(req: Request):
    """Social feed for young readers: one carousel post per contested item (posts/ → data/posts/posts.json)."""
    return FileResponse(WEB / "feed.html", headers={"Cache-Control": "no-cache"})


@mcp.custom_route("/api/posts", methods=["GET"])
async def api_posts(req: Request):
    f = ROOT / "data" / "posts" / "posts.json"
    if not f.exists():
        return JSONResponse({"error": "no posts yet: run posts/assemble.py"}, status_code=404)
    return Response(f.read_bytes(), media_type="application/json", headers={"Cache-Control": "no-cache"})


@mcp.custom_route("/api/demo", methods=["GET"])
async def api_demo(req: Request):
    f = ROOT / "demo" / "demo.json"
    if not f.exists():
        return JSONResponse({"error": "demo not recorded yet: run demo/record.py"}, status_code=404)
    return Response(f.read_bytes(), media_type="application/json", headers={"Cache-Control": "no-cache"})


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" '
           'fill="#1d4f9c"/><path d="M6 13 16 6l10 7zM8 14h3v9H8zm6.5 0h3v9h-3zM21 14h3v9h-3zM6 24h20v3H6z" '
           'fill="#fff"/></svg>')


@mcp.custom_route("/favicon.ico", methods=["GET"])
@mcp.custom_route("/favicon.svg", methods=["GET"])
async def favicon(req: Request):
    return Response(FAVICON, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


@mcp.custom_route("/api/cities", methods=["GET"])
async def api_cities(req: Request):
    return JSONResponse(list_cities())


@mcp.custom_route("/api/sessions", methods=["GET"])
async def api_sessions(req: Request):
    return JSONResponse(list_sessions(_city(req)))


@mcp.custom_route("/api/session", methods=["GET"])
async def api_session(req: Request):
    return jr(get_session, _int(req, "n", 0), _city(req))


@mcp.custom_route("/api/item", methods=["GET"])
async def api_item(req: Request):
    return jr(get_item, _int(req, "n", 0), _int(req, "no", 0), _int(req, "sub", 1), _city(req))


@mcp.custom_route("/api/search", methods=["GET"])
async def api_search(req: Request):
    city = _norm_city(req.query_params.get("city", ""))
    city = city if city in GOVERNING else ""
    return jr(search, req.query_params.get("q", ""), city, _int(req, "n") if city else None, _int(req, "limit", 20))


@mcp.custom_route("/api/members", methods=["GET"])
async def api_members(req: Request):
    return JSONResponse(q("""
        SELECT m.name, m.party,
               (SELECT sum(present) FROM attendance a WHERE a.city = m.city AND a.member = m.name) AS present,
               (SELECT count(*) FROM attendance a WHERE a.city = m.city AND a.member = m.name) AS sessions,
               (SELECT count(*) FROM votes v WHERE v.city = m.city AND v.member = m.name AND v.vote = 'za') AS za,
               (SELECT count(*) FROM votes v WHERE v.city = m.city AND v.member = m.name AND v.vote = 'protiv') AS protiv,
               (SELECT count(*) FROM votes v WHERE v.city = m.city AND v.member = m.name AND v.vote = 'suzdrzan') AS suzdrzan,
               (SELECT count(*) FROM votes v WHERE v.city = m.city AND v.member = m.name AND v.vote = 'odsutan') AS odsutan,
               (SELECT count(*) FROM votes v WHERE v.city = m.city AND v.member = m.name AND v.vote = 'nije_glasovao') AS nije_glasovao,
               (SELECT count(*) FROM questions x WHERE x.city = m.city AND x.member = m.name) AS questions
        FROM members m WHERE m.city = ? ORDER BY m.party, m.name""", _city(req)))


@mcp.custom_route("/api/member", methods=["GET"])
async def api_member(req: Request):
    return jr(member_record, req.query_params.get("name", ""), _city(req))


@mcp.custom_route("/api/question", methods=["GET"])
async def api_question(req: Request):
    return jr(get_question, _int(req, "id", 0))


@mcp.custom_route("/api/debate", methods=["GET"])
async def api_debate(req: Request):
    return jr(item_debate, _int(req, "n", 0), _int(req, "no", 0), _int(req, "sub", 1), city=_city(req))


@mcp.custom_route("/api/transcript", methods=["GET"])
async def api_transcript(req: Request):
    return jr(get_transcript, _int(req, "n", 0), _int(req, "part", 1), req.query_params.get("start", "0:00:00"),
              _int(req, "minutes", 10), _city(req))


@mcp.custom_route("/api/turns", methods=["GET"])
async def api_turns(req: Request):
    return jr(speaker_turns, _int(req, "n", 0), _int(req, "no"), _int(req, "sub", 1), _city(req))


@mcp.custom_route("/api/draft", methods=["GET"])
async def api_draft(req: Request):
    return jr(draft_minutes, _int(req, "n", 0), _int(req, "no", 0), _int(req, "sub", 1), _city(req))


@mcp.custom_route("/api/minutes_eval", methods=["GET"])
async def api_minutes_eval(req: Request):
    return jr(minutes_evaluation, _int(req, "n", 14), _city(req))


@mcp.custom_route("/api/ask", methods=["GET"])
async def api_ask(req: Request):
    """?k=<key> answer card (unknown key -> 404); no k -> the questions of ?city= (all cities if absent)."""
    c = _norm_city(req.query_params.get("city", ""))
    return jr(example_questions, req.query_params.get("k", ""), c if c in GOVERNING else "")


@mcp.custom_route("/api/promises", methods=["GET"])
async def api_promises(req: Request):
    return jr(promises, _city(req), req.query_params.get("speaker", ""), _int(req, "n"),
              _norm_status(req.query_params.get("status", "")))


@mcp.custom_route("/api/followup", methods=["GET"])
async def api_followup(req: Request):
    return jr(promise_followup, _int(req, "id", 0), _city(req))


@mcp.custom_route("/api/asr_eval", methods=["GET"])
async def api_asr_eval(req: Request):
    return jr(transcript_quality, _city(req))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--http":
        import threading  # warm the slow "Pitaj Vijećnicu" answer (~2.5 s) so the first click is instant
        threading.Thread(target=lambda: (ask("protiv-kluba"), ask("obecanja"), minutes_evaluation(14, "zagreb")),
                         daemon=True).start()
        from mcp.server.transport_security import TransportSecuritySettings
        try:
            from config_local import EXTRA_HOSTS  # machine-specific, not in git
        except ImportError:
            EXTRA_HOSTS = []
        hosts = ["localhost", "127.0.0.1", *EXTRA_HOSTS]
        mcp.run("streamable-http", host="0.0.0.0", port=int(sys.argv[2]),
                transport_security=TransportSecuritySettings(
                    allowed_hosts=[f"{h}:{p}" for h in hosts for p in (sys.argv[2], "*")] + hosts,
                    allowed_origins=[f"http://{h}:{sys.argv[2]}" for h in hosts]))
    else:
        mcp.run()
