"""Vercel Python function: the eVijećnica MCP server, public at https://evijecnica.vercel.app/mcp.

web/build_static.py copies this to deploy/vijecnica/api/server.py (/mcp is rewritten to it) next to mcp_server.py, collect/netcom.py and a
public copy of the database (data/vijecnica.db without units that exclude AI systems, see NO_DOWNLOAD there).
Stateless streamable HTTP with JSON responses, so every request stands alone (serverless). Read-only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from mcp_server import mcp  # noqa: E402

_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                               transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


async def app(scope, receive, send):
    """/mcp is rewritten to this function; accept the request under either path."""
    if scope["type"] == "http" and scope.get("path", "").rstrip("/") in ("/api/server", "/mcp", "/api/server.py", "/api/mcp"):
        scope = dict(scope, path="/mcp", raw_path=b"/mcp")
    await _app(scope, receive, send)
