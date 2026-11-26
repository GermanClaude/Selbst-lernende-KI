"""Winziger MCP-Server fuer die Tests (stdio, eine JSON-Nachricht pro Zeile) - wie ein echtes Plugin."""
import json
import os
import sys

WERKZEUGE = [
    {"name": "addieren", "description": "Zaehlt zwei Zahlen zusammen.",
     "inputSchema": {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
                     "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
    {"name": "umgebung", "description": "Verraet, welche Schluessel das Plugin sieht.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def senden(n):
    sys.stdout.write(json.dumps(n) + "\n")
    sys.stdout.flush()


print("ich bin eine Log-Zeile, kein JSON", flush=True)   # schlampige Plugins machen das
for zeile in sys.stdin:
    try:
        n = json.loads(zeile)
    except ValueError:
        continue
    m, nid = n.get("method"), n.get("id")
    if nid is None:
        continue                                           # Mitteilungen
    if m == "initialize":
        senden({"jsonrpc": "2.0", "id": nid, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                                                        "serverInfo": {"name": "testserver", "version": "1"}}})
    elif m == "tools/list":
        if not (n.get("params") or {}).get("cursor"):
            senden({"jsonrpc": "2.0", "id": nid, "result": {"tools": WERKZEUGE[:1], "nextCursor": "seite2"}})
        else:
            senden({"jsonrpc": "2.0", "id": nid, "result": {"tools": WERKZEUGE[1:]}})
    elif m == "tools/call":
        p = n.get("params") or {}
        if p.get("name") == "addieren":
            a = p.get("arguments") or {}
            text = str(a.get("a", 0) + a.get("b", 0))
        else:
            text = "sichtbar: " + ",".join(sorted(k for k in os.environ if "KEY" in k or "TOKEN" in k)) + \
                   " eigenes=" + os.environ.get("PLUGIN_EIGEN", "")
        senden({"jsonrpc": "2.0", "id": nid, "result": {"content": [{"type": "text", "text": text}]}})
    else:
        senden({"jsonrpc": "2.0", "id": nid, "error": {"code": -32601, "message": "unbekannt"}})
