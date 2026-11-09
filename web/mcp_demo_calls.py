"""Run the demo questions against the live MCP server (streamable HTTP) and keep the real tool calls and results
for the MCP part of the demo video (web/record_demo.py) -> deploy/demo_video/mcp_calls.json.

Usage: mcp_server.py --http 8103 running, then  ../.venv/bin/python web/mcp_demo_calls.py
"""
import asyncio
import json
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

OUT = Path(__file__).resolve().parent.parent / "deploy" / "demo_video" / "mcp_calls.json"
QUESTIONS = [
    ("chatgpt", "Igram nogomet u Zagrebu. Hoće li mi grad platiti liječnički pregled?",
     [("search", {"query": "liječnički pregled sportaša", "city": "zagreb", "limit": 6}),
      ("get_item", {"city": "zagreb", "session": 14, "item_no": 23})]),
    ("claude", "Koliko su stipendije u Zagrebu, a koliko u Rijeci?",
     [("search", {"query": "stipendija", "city": "zagreb", "limit": 6}),
      ("search", {"query": "stipendije", "city": "rijeka", "limit": 6})]),
    ("gemini", "Gdje se u Hrvatskoj grade novi vrtići?",
     [("search", {"query": "vrtić", "city": "", "limit": 40}),
      ("search", {"query": "vrtića gradnji", "city": "velika_gorica", "limit": 4})]),
]


async def main():
    out = []
    async with streamable_http_client("http://localhost:8103/mcp") as (r, w, *_):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for ui, question, calls in QUESTIONS:
                done = []
                for tool, args in calls:
                    t = time.perf_counter()
                    res = await s.call_tool(tool, args)
                    ms = round((time.perf_counter() - t) * 1000)
                    data = res.structured_content or json.loads(res.content[0].text)
                    done.append({"tool": tool, "args": args, "ms": ms, "result": data["result"] if list(data) == ["result"] else data})
                out.append({"ui": ui, "q": question, "calls": done})
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
