"""Ollama in App und Terminal: Endpunkte, Herunterladen mit Fortschritt, Befehle (ohne Netz)."""
import pytest

from assistant import ollama
from assistant.config import load_config
from tests._fakes import FakeOllama, ollama_chunk
from tests.test_app import _events_until, _req


@pytest.fixture
def fake():
    return FakeOllama(
        caps={"qwen3.5:4b": ["completion", "tools", "vision", "thinking"], "gemma3:4b": ["completion", "vision"]},
        pulls={"qwen3:4b": [{"status": "pulling manifest"}, {"status": "pulling a", "total": 10, "completed": 5},
                            {"status": "success"}]})


@pytest.fixture
def server(tmp_path, monkeypatch, fake):
    from assistant.app.controller import AppController
    from assistant.app.server import AppServer

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.deepseek_api_key = None
    srv = AppServer(lambda b: AppController(cfg, b))
    srv.start()
    srv.controller._ollama_http = fake
    srv.events = srv.hub.subscribe()
    yield srv
    srv.controller.shutdown()
    srv.stop()


def _use_fake(ctl, fake):
    ctl.brain.provider.client = ollama.OllamaClient(ctl.config.ollama.adresse, http=fake)


def test_gehirn_wechseln_und_chatten(server, fake):
    ctl = server.controller
    info = _req(server, "/api/setup")[1]
    o = next(p for p in info["providers"] if p["id"] == "ollama")
    assert o["has_key"] and o["needs_key"] is False and "Ollama" in o["name"]
    body = _req(server, "/api/setup", {"provider": "ollama"})[1]
    assert body["ok"] and "kostenlos" in body["message"] and ctl.config.active_provider == "ollama"
    assert ctl.brain.provider.name == "ollama"
    state = _req(server, "/api/state")[1]
    assert state["provider"] == "ollama" and state["kostenlos"] is True and state["api_key_missing"] is False
    assert "Ollama" in state["provider_name"]
    _use_fake(ctl, fake)
    fake.chats = [[ollama_chunk("Hallo vom PC!"), ollama_chunk(done=True, prompt=10, completion=3)]]
    _req(server, "/api/send", {"text": "Hallo"})
    events = _events_until(server, "state")
    while not any(e["type"] == "chunk" for e in events) or _req(server, "/api/state")[1]["busy"]:
        events += _events_until(server, "state")
    assert "Hallo vom PC!" in "".join(e["text"] for e in events if e["type"] == "chunk")
    assert _req(server, "/api/state")[1]["eur"] == 0


def test_gehirn_wechseln_ohne_laufendes_ollama(server):
    server.controller._ollama_http = FakeOllama(offline=True)
    body = _req(server, "/api/setup", {"provider": "ollama"})[1]
    assert body["ok"] is False and body["kind"] in ("ollama_offline", "ollama_missing")
    assert server.controller.config.active_provider != "ollama"
    forced = _req(server, "/api/setup", {"provider": "ollama", "force": True})[1]
    assert forced["ok"] and server.controller.config.active_provider == "ollama"


def test_stand_mit_faehigkeiten(server):
    info = _req(server, "/api/ollama")[1]
    assert info["laeuft"] and info["version"] == "0.30.1" and info["adresse"] == "http://localhost:11434"
    models = {m["name"]: m for m in info["modelle"]}
    assert models["qwen3.5:4b"]["werkzeuge"] and models["qwen3.5:4b"]["sieht_bilder"] and models["qwen3.5:4b"]["aktiv"]
    assert models["gemma3:4b"]["werkzeuge"] is False and models["gemma3:4b"]["sieht_bilder"]
    assert any(e["id"] == "qwen3.5:9b" and not e["installiert"] for e in info["empfohlen"])
    server.controller._ollama_http = FakeOllama(offline=True)
    off = _req(server, "/api/ollama")[1]
    assert off["laeuft"] is False and off["fehler"]


def test_herunterladen_mit_fortschritt_im_fenster(server):
    body = _req(server, "/api/ollama/laden", {"model": "qwen3:4b"})[1]
    assert body["ok"]
    events = _events_until(server, "ollama_pull")
    pulls = [e for e in events if e["type"] == "ollama_pull"]
    while not pulls[-1].get("fertig"):
        pulls += [e for e in _events_until(server, "ollama_pull") if e["type"] == "ollama_pull"]
    assert pulls[-1]["ok"] and pulls[-1]["model"] == "qwen3:4b"
    assert any(p.get("prozent") == 50.0 for p in pulls)
    assert _req(server, "/api/ollama/laden", {"model": "../boese"})[1]["ok"] is False
    assert _req(server, "/api/ollama/abbrechen", {})[1]["ok"] is False   # laeuft nichts mehr


def test_adresse_aendern_nur_gueltig(server):
    ctl = server.controller
    bad = _req(server, "/api/ollama/adresse", {"adresse": "file:///etc/passwd"})[1]
    assert bad["ok"] is False and ctl.config.ollama.adresse == "http://localhost:11434"
    good = _req(server, "/api/ollama/adresse", {"adresse": "http://127.0.0.1:11435/"})[1]
    assert good["ok"] and ctl.config.ollama.adresse == "http://127.0.0.1:11435"
    assert load_config(ctl.config.project_root).ollama.adresse == "http://127.0.0.1:11435"
    assert _req(server, "/api/ollama/adresse", {"adresse": ""})[1]["ok"]   # leer = Standard
    assert ctl.config.ollama.adresse == "http://localhost:11434"


def test_modell_waehlen_ueber_die_app(server):
    body = _req(server, "/api/modell", {"provider": "ollama", "model": "gemma3:4b"})[1]
    assert body["ok"] and server.controller.config.ollama.model == "gemma3:4b"
    assert _req(server, "/api/modell", {"provider": "ollama", "denken": "gruendlich"})[1]["ok"]
    assert server.controller.config.ollama.denken == "an"


def test_terminal_befehle(server, capsys):
    ctl = server.controller
    ctl._handle_command("/ollama")
    out = capsys.readouterr().out
    assert "laeuft (Version 0.30.1)" in out and "qwen3.5:4b" in out and "Empfohlen" in out
    ctl._handle_command("/gehirn ollama")
    out = capsys.readouterr().out
    assert ctl.config.active_provider == "ollama" and "kostenlos" in out
    ctl._handle_command("/modell ollama qwen3.5:9b")   # laeuft, aber nicht heruntergeladen -> nicht speichern
    out = capsys.readouterr().out
    assert ctl.config.ollama.model == "qwen3.5:4b" and "noch nicht heruntergeladen" in out
    ctl._handle_command("/modell sonnet")                # Claude-Name, waehrend Ollama aktiv ist
    out = capsys.readouterr().out
    assert ctl.config.ollama.model == "qwen3.5:4b" and "Claude" in out and "/gehirn claude" in out
    ctl._handle_command("/ollama adresse ftp://x")
    assert "http://" in capsys.readouterr().out and ctl.config.ollama.adresse == "http://localhost:11434"
    ctl._handle_command("/ollama quatsch")
    assert "/ollama laden" in capsys.readouterr().out


def test_terminal_herunterladen(tmp_path, monkeypatch, fake, capsys):
    from assistant.ui.cli import CLI

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.provider.aktiv = "ollama"
    cfg.ollama.model = "fehlt:1b"
    cli = CLI(cfg)
    cli._ollama_http = fake
    try:
        cli._handle_command("/ollama laden qwen3:4b")
        out = capsys.readouterr().out
        assert "50.0 %" in out and "ist heruntergeladen" in out
        assert cfg.ollama.model == "qwen3:4b"          # eingestelltes fehlte -> das neue genommen
        cli._handle_command("/ollama laden")
        assert "Welches Modell" in capsys.readouterr().out
        cli._print_cost_line()
        assert "kostenlos" in capsys.readouterr().out
        assert "Ollama" in cli._ollama_starthinweis() or cli._ollama_starthinweis() == ""
    finally:
        cli.memory.close()


# ---------------------------------------------------------------------------
# Oberflaeche: Vertrag mit dem Server, reine Hilfen (Node)
# ---------------------------------------------------------------------------
def test_oberflaeche_kennt_ollama():
    from tests.test_oberflaeche import APP_JS, CSS, HTML

    for pfad in ("/api/ollama", "/api/ollama/laden", "/api/ollama/abbrechen", "/api/ollama/adresse",
                 "/api/ollama/starten"):
        assert f"'{pfad}'" in APP_JS
    assert "case 'ollama_pull':" in APP_JS and "soOnPull(ev)" in APP_JS
    assert 'role="radiogroup"' in HTML[HTML.index('id="so-models"') - 120:HTML.index('id="so-models"') + 120]
    assert "role', 'progressbar'" in APP_JS and "aria-valuenow" in APP_JS
    assert ".su-prov.sp-ollama" in CSS and "grid-column: 1 / -1" in CSS
    for text in ("Ollama auf deinem PC", "Modelle auf deinem PC", "Empfohlen zum Herunterladen", "Neu prüfen"):
        assert text in HTML
    for text in ("kein Schlüssel nötig", "Ollama herunterladen", "Ollama starten", "Herunterladen", "kostenlos"):
        assert text in APP_JS
    # nie ein Installer automatisch: nur ein Link auf die offizielle Seite
    assert "https://ollama.com/download" in (APP_JS + HTML + open(
        __import__("tests.test_oberflaeche", fromlist=["STATIC"]).STATIC / "helfer.js", encoding="utf-8").read())


_JS = r"""
const assert = require('assert');
const H = require(process.argv[2]);
const eq = (a, b) => assert.deepStrictEqual(a, b);
const d = H.normOllama({ laeuft: true, version: '0.30.1', installiert: true, adresse: 'http://localhost:11434',
  modelle: [{ name: 'qwen3.5:4b', anzeige: 'Qwen 3.5 (4B)', groesse: 3400000000, werkzeuge: true, sieht_bilder: true, aktiv: true },
            { name: '../boese' }, { name: 'qwen3.5:4b' }, { name: 'gemma3:4b', werkzeuge: false }],
  empfohlen: [{ id: 'qwen3.5:9b', name: 'Qwen 3.5 (9B)', groesse: '6,6 GB', installiert: false }, { id: 'x y' }],
  laden: { model: 'qwen3.5:9b', prozent: 150, erledigt: 5, gesamt: 10 } });
eq(d.modelle.map((m) => m.name), ['qwen3.5:4b', 'gemma3:4b']);
eq(d.modelle[0].groesse, '3,4 GB'); eq(d.modelle[1].werkzeuge, false); eq(d.modelle[1].bilder, null);
eq(d.empfohlen.length, 1); eq(d.laden.prozent, 100); eq(d.laeuft, true);
eq(H.normOllama({ adresse: 'javascript:alert(1)' }).adresse, '');
eq(H.normOllama(null), null); eq(H.normOllama([]), null);
eq(H.normPull({ model: '' }), null);
const p = H.normPull({ model: 'qwen3:4b', text: 'Lade herunter …', prozent: 45.7, erledigt: 1500000000, gesamt: 3400000000 });
eq(H.pullText(p), 'Lade herunter … 45 % (1,5 GB von 3,4 GB)');
eq(H.pullText(H.normPull({ model: 'a', text: 'Bereite vor …' })), 'Bereite vor …');
eq(H.ollamaGroesse(0), ''); eq(H.ollamaGroesse(523000000), '523 MB');
eq(H.ollamaName('hf.co/nutzer/modell:Q4_K_M'), 'hf.co/nutzer/modell:Q4_K_M'); eq(H.ollamaName('a..b'), '');
console.log('OK');
"""


def test_ollama_hilfen_in_node(tmp_path):
    import shutil
    import subprocess

    from tests.test_oberflaeche import STATIC

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js fehlt")
    script = tmp_path / "ollama_test.js"
    script.write_text(_JS, encoding="utf-8")
    r = subprocess.run([node, str(script), str(STATIC / "helfer.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip().endswith("OK"), r.stdout + r.stderr
