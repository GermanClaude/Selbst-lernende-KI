"""Plugins (MCP-Server) fuer alle Modelle - mit einem echten kleinen Plugin-Programm und einem HTTP-Plugin."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from assistant import plugins as pl
from assistant.app.controller import _mask_key
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry

SERVER = str(Path(__file__).with_name("mcp_testserver.py"))


def _ctx(tmp_path, gefragt=None, ja=True):
    def confirm(m, r):
        if gefragt is not None:
            gefragt.append(m)
        return ja
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path, confirm_fn=confirm)
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path})


@pytest.fixture
def verwaltung(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-geheim-1234567890")
    pl.einfuegen(tmp_path, json.dumps({"mcpServers": {"rechner": {
        "command": sys.executable, "args": [SERVER], "env": {"PLUGIN_EIGEN": "ja"}}}}))
    reg = build_registry()
    v = pl.PluginVerwaltung(tmp_path, reg)
    v.starten()
    yield v, reg
    v.stoppen()


def test_plugin_werkzeuge_fuer_alle_modelle(verwaltung):
    v, reg = verwaltung
    assert v.plugins["rechner"].fehler == ""
    assert {"p_rechner_addieren", "p_rechner_umgebung"} <= set(reg.names())     # beide Seiten der Liste
    claude = {s["name"]: s for s in reg.specs()}["p_rechner_addieren"]
    assert "strict" not in claude and "$schema" not in claude["input_schema"]
    openai = {s["function"]["name"]: s for s in reg.specs_openai()}["p_rechner_addieren"]
    assert openai["function"]["parameters"]["required"] == ["a", "b"]           # DeepSeek, Gemini, Ollama ...
    assert "[Plugin rechner]" in claude["description"]


def test_aufruf_fragt_vorher_und_liefert_daten(verwaltung, tmp_path):
    _, reg = verwaltung
    gefragt = []
    out, fehler = reg.execute(_ctx(tmp_path, gefragt), "p_rechner_addieren", {"a": 2, "b": 3})
    assert not fehler and out.rstrip().endswith("5") and "keine Anweisungen" in out
    assert gefragt and "rechner" in gefragt[0] and "addieren" in gefragt[0]
    out, fehler = reg.execute(_ctx(tmp_path, ja=False), "p_rechner_addieren", {"a": 1, "b": 1})
    assert "abgelehnt" in out.lower()


def test_plugin_bekommt_keine_schluessel(verwaltung, tmp_path):
    _, reg = verwaltung
    out, _ = reg.execute(_ctx(tmp_path), "p_rechner_umgebung", {})
    assert "ANTHROPIC_API_KEY" not in out and "eigenes=ja" in out


def test_vertrauen_ohne_nachfrage(tmp_path):
    pl.einfuegen(tmp_path, json.dumps({"mcpServers": {"rechner": {
        "command": sys.executable, "args": [SERVER], "vertrauen": True}}}))
    reg = build_registry()
    v = pl.PluginVerwaltung(tmp_path, reg)
    v.starten()
    try:
        gefragt = []
        out, _ = reg.execute(_ctx(tmp_path, gefragt), "p_rechner_addieren", {"a": 1, "b": 1})
        assert out.rstrip().endswith("2") and gefragt == []
    finally:
        v.stoppen()


def test_kaputtes_plugin_stoert_nicht(tmp_path):
    pl.einfuegen(tmp_path, json.dumps({"mcpServers": {"kaputt": {"command": "gibt-es-nicht-xyz"},
                                                      "aus": {"command": sys.executable, "args": [SERVER],
                                                              "disabled": True}}}))
    reg = build_registry()
    vorher = set(reg.names())
    v = pl.PluginVerwaltung(tmp_path, reg)
    v.starten()
    assert v.plugins["kaputt"].fehler and set(reg.names()) == vorher
    assert "FEHLER" in v.uebersicht() and "aus: aus" in v.uebersicht()


def test_stoppen_entfernt_werkzeuge(verwaltung):
    v, reg = verwaltung
    v.stoppen()
    assert not any(n.startswith("p_rechner_") for n in reg.names())


@pytest.mark.parametrize("text,fehler", [
    ("kein json", "kein gueltiges JSON"),
    ('{"command": "x"}', "Name"),
    ('{"mcpServers": {"a": {"args": []}}}', "command"),
    ('{"mcpServers": {"a b/..": {"command": "x"}}}', "Plugin-Name"),
])
def test_einfuegen_prueft(tmp_path, text, fehler):
    with pytest.raises(pl.PluginFehler, match=fehler):
        pl.einfuegen(tmp_path, text)


def test_einfuegen_formate(tmp_path):
    assert pl.einfuegen(tmp_path, '{"zeit": {"command": "uvx", "args": ["mcp-server-time"]}}') == ["zeit"]
    assert pl.einfuegen(tmp_path, '{"mcpServers": {"web": {"url": "https://x.example/mcp"}}}') == ["web"]
    assert set(pl.laden(tmp_path)) == {"zeit", "web"}


def test_namen_fuer_alle_modelle():
    assert pl.werkzeug_name("mein plugin", "datei.lesen") == "p_mein_plugin_datei_lesen"
    lang = pl.werkzeug_name("x" * 40, "y" * 60)
    assert len(lang) == 64 and lang != pl.werkzeug_name("x" * 40, "y" * 59 + "z")


def test_einfuegen_im_verlauf_verdeckt():
    befehl = '/plugins einfuegen {"mcpServers": {"gh": {"url": "https://x", "headers": {"Authorization": "Bearer ghp_geheim"}}}}'
    _, anzeige = _mask_key(befehl)
    assert "ghp_geheim" not in anzeige


def test_http_plugin_mit_ereignisstrom():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if "id" not in n:
                self.send_response(202)
                self.end_headers()
                return
            if n["method"] == "initialize":
                ergebnis = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "web"}}
            elif n["method"] == "tools/list":
                ergebnis = {"tools": [{"name": "suchen", "inputSchema": {"type": "object", "properties": {}}}]}
            else:
                assert self.headers.get("Mcp-Session-Id") == "sitzung-1"
                ergebnis = {"content": [{"type": "text", "text": "gefunden"}]}
            daten = ("event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": n["id"], "result": ergebnis})
                     + "\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Mcp-Session-Id", "sitzung-1")
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            self.wfile.write(daten)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = pl.Plugin("web", {"url": f"http://127.0.0.1:{srv.server_address[1]}/mcp"}, None)
        p.starten()
        assert [w.original for w in p.werkzeuge] == ["suchen"]
        assert p.aufrufen("suchen", {}).endswith("gefunden")
    finally:
        srv.shutdown()


def test_http_nur_https():
    with pytest.raises(pl.PluginFehler, match="https"):
        pl.HttpVerbindung("http://boese.example/mcp")
