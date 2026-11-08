"""Ollama: kostenloses Gehirn auf dem eigenen PC (ohne Netz getestet - unechter Ollama-Server)."""
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from assistant import modelle, ollama, schluessel
from assistant.bilder import Bild
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.ollama_provider import OllamaProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import FakeOllama, ollama_chunk, ollama_http_fehler

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("KI_MODEL", raising=False)
    config = load_config(tmp_path)
    config.anthropic_api_key = config.deepseek_api_key = None
    config.provider.aktiv = "ollama"
    return config


def _provider(tmp_path, cfg, fake):
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, memory=mem)
    client = ollama.OllamaClient(cfg.ollama.adresse, kontext=cfg.ollama.kontext, http=fake)
    return OllamaProvider(cfg, "SYSTEM", build_registry(), ctx, client=client), mem


# ---------------------------------------------------------------------------
# Adresse, Einstellungen, Modelle, Kosten
# ---------------------------------------------------------------------------
def test_adresse_nur_http_und_https():
    assert ollama.pruefe_adresse("") == "http://localhost:11434"
    assert ollama.pruefe_adresse("http://localhost:11434/") == "http://localhost:11434"
    assert ollama.pruefe_adresse("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert ollama.pruefe_adresse("https://ki.local:8443") == "https://ki.local:8443"
    assert ollama.pruefe_adresse("http://localhost:1234/v1") == "http://localhost:1234/v1"
    assert ollama.ist_openai_adresse("http://localhost:1234/v1")
    for bad in ("file:///etc/passwd", "ftp://x", "javascript:alert(1)", "http://user:pw@host",
                "http://host/api/chat", "http://host?x=1", "http://host:99999", "http:// host", "http://"):
        with pytest.raises(ValueError):
            ollama.pruefe_adresse(bad)


def test_ungueltige_adresse_in_den_einstellungen_wird_nie_benutzt(cfg):
    cfg.ollama.adresse = "file:///geheim"
    assert ollama.adresse_aus(cfg) == ollama.STANDARD_ADRESSE


def test_einstellungen_laden_und_kein_automatischer_wechsel_zu_ollama(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text(
        '[provider]\naktiv = "ollama"\n[ollama]\nmodel = "llama3.2:3b"\nkontext = "kaputt"\ndenken = true\n',
        encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.active_provider == "ollama" and cfg.active_model == "llama3.2:3b"
    assert cfg.ollama.kontext == 16384 and cfg.ollama.denken == "an"
    assert cfg.api_key and not cfg.provider_auto_switched   # kein Schluessel noetig
    # Ollama-Wahl bleibt, auch wenn ein DeepSeek-Schluessel da ist
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-1234567890abcdef1234567890ab")
    assert load_config(tmp_path).active_provider == "ollama"
    # ... und ohne Wahl wird Ollama nie von selbst genommen
    (tmp_path / "config" / "settings.toml").write_text('[provider]\naktiv = "claude"\n', encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    again = load_config(tmp_path)
    assert again.active_provider == "claude" and not again.api_key


def test_kosten_sind_immer_null(cfg):
    assert cfg.kostenlos
    assert cfg.cost_estimate(1_000_000, 1_000_000, 1_000_000) == (0.0, 0.0)
    assert modelle.preise("ollama", "irgendwas:7b") == (0.0, 0.0, 0.0)
    assert cfg.prices.for_provider("ollama") == (0.0, 0.0, 0.0)


def test_modell_und_denktiefe_waehlen(cfg, monkeypatch):
    # Ollama laeuft hier nicht (dann wird ohne Pruefung gespeichert)
    monkeypatch.setattr(ollama, "_http_standard", FakeOllama(offline=True))
    r = modelle.waehle(cfg, "ollama", model="qwen3.5:9b")
    assert r["ok"] and cfg.ollama.model == "qwen3.5:9b" and "Qwen 3.5 (9B)" in r["message"]
    assert modelle.waehle(cfg, "ollama", model="hf.co/Nutzer/Modell:Q4_K_M")["ok"]
    assert cfg.ollama.model == "hf.co/Nutzer/Modell:Q4_K_M"            # Schreibweise bleibt
    assert modelle.waehle(cfg, "ollama", model="gemma")["ok"] and cfg.ollama.model == "gemma4:e4b"
    assert not modelle.waehle(cfg, "ollama", model="../../boese")["ok"]
    assert modelle.waehle(cfg, "ollama", denken="gruendlich")["ok"] and cfg.ollama.denken == "an"
    assert modelle.finde_denktiefe("ollama", "schnell") == "aus"
    again = load_config(cfg.project_root)
    assert again.ollama.model == "gemma4:e4b" and again.ollama.denken == "an"
    assert "gr" in modelle.kurzbeschreibung(cfg, "ollama")
    info = modelle.beschreibung(cfg)["ollama"]
    assert info["modelle"] == [] and [d["id"] for d in info["denktiefen"]] == ["aus", "an"]


def test_build_provider_nimmt_ollama(tmp_path, cfg):
    mem = Memory(tmp_path / "m.sqlite3")
    ctx = ToolContext(permissions=PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True),
                      memory=mem)
    prov = build_provider(cfg, "S", build_registry(), ctx)
    assert isinstance(prov, OllamaProvider) and isinstance(prov.client, ollama.OllamaClient)
    cfg.ollama.adresse = "http://localhost:1234/v1"   # LM Studio & Co.: openai-Bibliothek
    prov2 = build_provider(cfg, "S", build_registry(), ctx)
    assert not isinstance(prov2.client, ollama.OllamaClient)
    mem.close()


# ---------------------------------------------------------------------------
# Uebersetzung OpenAI-Format <-> /api/chat
# ---------------------------------------------------------------------------
def test_anfrage_wird_uebersetzt():
    client = ollama.OllamaClient("http://localhost:11434", kontext=16384, http=FakeOllama())
    body = client.anfrage_aus({
        "model": "qwen3.5:4b", "stream": True, "max_tokens": 100, "tool_choice": "auto",
        "tools": [{"type": "function", "function": {"name": "x"}}], "extra_body": {"think": False},
        "messages": [
            {"role": "system", "content": "S"},
            {"role": "user", "content": [{"type": "text", "text": "Was ist das?"},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
                                         {"type": "image_url", "image_url": {"url": "data:image/gif;base64,R0lG"}}]},
            {"role": "assistant", "content": "", "reasoning_content": "hmm",
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "datei_lesen", "arguments": '{"pfad": "a.txt"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Inhalt"},
        ]})
    assert body["options"] == {"num_ctx": 16384, "num_predict": 100} and body["think"] is False
    assert body["tools"] and body["stream"] is True
    user, assistant, tool = body["messages"][1:]
    assert user["images"] == ["QUJD"] and "Was ist das?" in user["content"] and "Bildformat" in user["content"]
    assert assistant["tool_calls"][0]["function"]["arguments"] == {"pfad": "a.txt"}
    assert assistant["thinking"] == "hmm"
    assert tool == {"role": "tool", "content": "Inhalt", "tool_call_id": "c1", "tool_name": "datei_lesen"}
    # tool_choice "none" -> ohne Werkzeuge (Ollama kennt kein tool_choice)
    assert "tools" not in client.anfrage_aus({"model": "m", "messages": [], "tools": [{}], "tool_choice": "none"})


def test_strom_wird_in_openai_teile_uebersetzt():
    fake = FakeOllama(chats=[[
        ollama_chunk(thinking="ueberlege"),
        ollama_chunk("Hal"), ollama_chunk("lo"),
        ollama_chunk(tool_calls=[{"function": {"name": "system_info", "arguments": {}}}]),
        ollama_chunk(done=True, prompt=120, completion=7),
    ]])
    client = ollama.OllamaClient("http://localhost:11434", http=fake)
    teile = list(client.chat.completions.create(model="m", messages=[], stream=True))
    text = "".join(t.choices[0].delta.content or "" for t in teile if t.choices)
    assert text == "Hallo"
    assert any(t.choices and t.choices[0].delta.reasoning_content == "ueberlege" for t in teile)
    calls = [tc for t in teile if t.choices for tc in t.choices[0].delta.tool_calls or []]
    assert calls[0].function.name == "system_info" and calls[0].function.arguments == "{}" and calls[0].id
    assert teile[-1].usage.prompt_tokens == 120 and teile[-1].usage.completion_tokens == 7


def test_fehler_mitten_im_strom():
    fake = FakeOllama(chats=[[ollama_chunk("a"), {"error": "out of memory"}]])
    client = ollama.OllamaClient("http://localhost:11434", http=fake)
    with pytest.raises(ollama.OllamaFehler, match="out of memory"):
        list(client.chat.completions.create(model="m", messages=[], stream=True))


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------
def test_antwort_mit_werkzeug_und_ohne_kosten(tmp_path, cfg):
    fake = FakeOllama(chats=[
        [ollama_chunk(tool_calls=[{"id": "c1", "function": {"name": "merken",
                                                             "arguments": {"inhalt": "Mag Tee"}}}]),
         ollama_chunk(done=True, prompt=5000, completion=20)],
        [ollama_chunk("Gemerkt!"), ollama_chunk(done=True, prompt=5100, completion=3)],
    ])
    prov, mem = _provider(tmp_path, cfg, fake)
    out = prov.respond("Merk dir: ich mag Tee")
    assert "Gemerkt!" in out
    assert any("Mag Tee" in f.content for f in mem.top_facts())
    first, second = fake.chat_requests()
    assert first["tools"] and first["options"]["num_ctx"] == 16384 and first["model"] == "qwen3.5:4b"
    assert first["think"] is False                         # Qwen 3.5 denkt sonst immer
    assert second["messages"][-1]["role"] == "tool" and second["messages"][-1]["tool_name"] == "merken"
    assert prov.usage.total_tokens > 0 and prov.cost() == (0.0, 0.0)
    mem.close()


def test_modell_ohne_werkzeuge_hinweis_nur_einmal(tmp_path, cfg):
    cfg.ollama.model = "gemma3:4b"
    fake = FakeOllama(caps={"gemma3:4b": ["completion", "vision"]},
                      chats=[[ollama_chunk("Antwort 1", done=True)], [ollama_chunk("Antwort 2", done=True)]])
    prov, mem = _provider(tmp_path, cfg, fake)
    seen = []
    prov.respond("Hallo", on_text=seen.append)
    prov.respond("Nochmal", on_text=seen.append)
    assert sum("keine Werkzeuge" in s for s in seen) == 1 and "qwen3.5:4b" in "".join(seen)
    for req in fake.chat_requests():
        assert "tools" not in req and "think" not in req
        assert "KEINE Werkzeuge" in req["messages"][0]["content"]
    assert prov.messages[0]["content"] == "SYSTEM"   # nur beim Senden ergaenzt
    mem.close()


def test_ollama_lehnt_werkzeuge_ab_dann_ohne(tmp_path, cfg):
    fake = FakeOllama(chats=[ollama_http_fehler(400, "registry.ollama.ai/library/x does not support tools"),
                             [ollama_chunk("geht auch so", done=True)]])
    prov, mem = _provider(tmp_path, cfg, fake)
    assert "geht auch so" in prov.respond("Hi")
    first, second = fake.chat_requests()
    assert "tools" in first and "tools" not in second
    mem.close()


def test_bilder_nur_fuer_modelle_mit_augen(tmp_path, cfg):
    bild = Bild("foto.png", "image/png", PNG)
    fake = FakeOllama(chats=[[ollama_chunk("Ein Pixel.", done=True)]])
    prov, mem = _provider(tmp_path, cfg, fake)
    prov.respond("Was ist das?", bilder=[bild])
    req = fake.chat_requests()[0]
    assert req["messages"][-1]["images"] and "Was ist das?" in req["messages"][-1]["content"]
    mem.close()

    cfg.ollama.model = "qwen3:4b"
    fake = FakeOllama(caps={"qwen3:4b": ["completion", "tools", "thinking"]},
                      chats=[[ollama_chunk("Sehe nichts.", done=True)]])
    prov, mem = _provider(tmp_path, cfg, fake)
    prov.respond("Was ist das?", bilder=[bild])
    msg = fake.chat_requests()[0]["messages"][-1]
    assert "images" not in msg and "[Bild: foto.png]" in msg["content"] and ollama.SIEHT_NICHTS in msg["content"]
    assert len(fake.chat_requests()) == 1               # kein (bezahlter) Nebenaufruf
    mem.close()


def test_nachdenken_nur_wenn_gewuenscht_und_moeglich(tmp_path, cfg):
    cfg.ollama.denken = "an"
    fake = FakeOllama(chats=[[ollama_chunk(thinking="lass mal sehen"), ollama_chunk("42", done=True)],
                             [ollama_chunk("43", done=True)]])
    prov, mem = _provider(tmp_path, cfg, fake)
    prov.respond("Frage")
    assert fake.chat_requests()[0]["think"] is True
    assert prov.messages[-1].get("reasoning_content") == "lass mal sehen"
    prov.respond("Noch eine")
    sent = fake.chat_requests()[1]["messages"]
    assert any(m.get("thinking") == "lass mal sehen" for m in sent)   # Denk-Text geht zurueck
    prov.effort_override = "low"   # Sprachmodus: schnell
    prov.respond("Schnell")
    assert fake.chat_requests()[2]["think"] is False
    mem.close()


def test_ollama_laeuft_nicht(tmp_path, cfg):
    prov, mem = _provider(tmp_path, cfg, FakeOllama(offline=True))
    seen = []
    out = prov.respond("Hallo", on_text=seen.append)
    assert "Ollama antwortet nicht" in out and "ollama.com/download" in out and seen
    assert len(prov.messages) == 1                     # Verlauf unberuehrt
    mem.close()


def test_modell_nicht_heruntergeladen(tmp_path, cfg):
    cfg.ollama.model = "qwen3.5:9b"
    prov, mem = _provider(tmp_path, cfg, FakeOllama())
    out = prov.respond("Hallo")
    assert "noch nicht heruntergeladen" in out and "/ollama laden qwen3.5:9b" in out
    mem.close()


def test_verbindung_bricht_beim_chat_ab(tmp_path, cfg):
    fake = FakeOllama(chats=[urllib.error.URLError(ConnectionRefusedError())])
    prov, mem = _provider(tmp_path, cfg, fake)
    seen = []
    prov.respond("Hallo", on_text=seen.append)
    assert any("Ollama antwortet nicht" in s for s in seen)
    mem.close()


def test_zusammenfassung_und_kurzfrage_ohne_werkzeuge_und_ohne_denken(tmp_path, cfg):
    fake = FakeOllama(chats=[[ollama_chunk("a", done=True)], [ollama_chunk("b", done=True)],
                             {"message": {"content": "Zusammenfassung"}, "done": True, "done_reason": "stop"},
                             {"message": {"content": "Kurz"}, "done": True}])
    prov, mem = _provider(tmp_path, cfg, fake)
    prov.respond("eins")
    prov.respond("zwei")
    assert prov.summarize_history() == "Zusammenfassung"
    assert prov.ask_once("Frage?") == "Kurz"
    for req in fake.chat_requests()[2:]:
        assert req["stream"] is False and "tools" not in req and req["think"] is False
    mem.close()


def test_kleiner_kontext_frueher_zusammenfassen_und_beim_senden_kuerzen(tmp_path, cfg):
    prov, mem = _provider(tmp_path, cfg, FakeOllama())
    assert prov.verlauf_grenze() < cfg.conversation.max_verlauf_zeichen
    assert prov.verlauf_grenze() >= 8000
    prov.messages += [{"role": "user", "content": "lies"},
                      {"role": "assistant", "content": "", "tool_calls": [
                          {"id": f"c{i}", "type": "function", "function": {"name": "datei_lesen", "arguments": "{}"}}
                          for i in range(4)]}]
    prov.messages += [{"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 20_000} for i in range(4)]
    sent = prov._request_messages(False)
    tools = [m["content"] for m in sent if m["role"] == "tool"]
    assert len(tools[0]) < 1000 and len(tools[-1]) == 20_000          # aeltere gekuerzt, neueste ganz
    assert all(len(m["content"]) == 20_000 for m in prov.messages if m["role"] == "tool")  # Verlauf bleibt
    mem.close()


# ---------------------------------------------------------------------------
# Stand, Herunterladen
# ---------------------------------------------------------------------------
def test_status(cfg):
    info = ollama.status(cfg, http=FakeOllama(models=["qwen3.5:4b", "llama3.2:latest"]))
    assert info["laeuft"] and info["version"] == "0.30.1" and info["modell_da"]
    assert [m["name"] for m in info["modelle"]] == ["llama3.2:latest", "qwen3.5:4b"]
    assert next(m for m in info["empfohlen"] if m["id"] == "qwen3.5:4b")["installiert"]
    off = ollama.status(cfg, http=FakeOllama(offline=True))
    assert not off["laeuft"] and "Ollama antwortet nicht" in off["fehler"]
    assert ollama.ist_installiert("llama3.2", {"llama3.2:latest"})


def test_fortschritt_lesen():
    ev = ollama.pull_ereignis(b'{"status":"pulling abc","digest":"sha256:abc","total":200,"completed":50}\n')
    assert ev["prozent"] == 25.0 and not ev["fertig"] and ollama.status_text(ev["status"]) == "Lade herunter …"
    assert ollama.pull_ereignis('{"status":"success"}')["fertig"]
    assert ollama.pull_ereignis('{"error":"kaputt"}')["fehler"] == "kaputt"
    assert ollama.pull_ereignis("kein json") is None and ollama.pull_ereignis("") is None


def test_herunterladen_mit_fortschritt():
    fake = FakeOllama(pulls={"qwen3:4b": [{"status": "pulling manifest"},
                                          {"status": "pulling x", "total": 100, "completed": 40},
                                          {"status": "pulling x", "total": 100, "completed": 100},
                                          {"status": "verifying sha256 digest"}, {"status": "success"}]})
    lader, events = ollama.Lader(), []
    ok, _ = lader.starten(ollama.Dienst(http=fake), "qwen3:4b", events.append, hintergrund=False)
    assert ok and events[-1]["fertig"] and events[-1]["ok"] and not lader.laeuft
    assert any(e.get("prozent") == 40.0 for e in events) and fake.requests[-1][2]["stream"] is True


def test_herunterladen_unbekanntes_modell_und_ungueltiger_name():
    lader, events = ollama.Lader(), []
    lader.starten(ollama.Dienst(http=FakeOllama()), "gibtsnicht:1b", events.append, hintergrund=False)
    assert events[-1]["fertig"] and not events[-1]["ok"] and "gibt es bei Ollama nicht" in events[-1]["fehler"]
    ok, message = lader.starten(ollama.Dienst(http=FakeOllama()), "../x", events.append)
    assert not ok and "kein gueltiger" in message


def test_herunterladen_abbrechen():
    gate, weiter = threading.Event(), threading.Event()

    class Langsam:
        closed = False

        def __init__(self):
            self.lines = [b'{"status":"pulling x","total":100,"completed":1}\n'] * 3

        def readline(self):
            if self.closed:
                return b""
            if not self.lines:
                gate.set()
                weiter.wait(5)
                return b"" if self.closed else b'{"status":"pulling x","total":100,"completed":2}\n'
            return self.lines.pop()

        def close(self):
            self.closed = True

    lader, events = ollama.Lader(), []
    lader.starten(ollama.Dienst(http=lambda *a: Langsam()), "qwen3:4b", events.append)
    assert gate.wait(5) and lader.laeuft and lader.zustand()["model"] == "qwen3:4b"
    assert lader.abbrechen()
    weiter.set()
    lader._thread.join(5)
    assert events[-1]["fertig"] and events[-1]["abgebrochen"] and not lader.laeuft
    assert not lader.abbrechen()


def test_einer_zur_zeit():
    lader = ollama.Lader()
    lader.modell = "a:1b"
    ok, message = lader.starten(ollama.Dienst(http=FakeOllama()), "b:1b", lambda e: None)
    assert not ok and "schon" in message


# ---------------------------------------------------------------------------
# Echter (lokaler) HTTP-Weg: Streamen ueber urllib
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        body = json.dumps({"version": "9.9.9"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length))
        if self.path == "/api/show":
            body = json.dumps({"error": f"model '{data['model']}' not found"}).encode()
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for teil in (ollama_chunk("Hallo "), ollama_chunk("lokal"), ollama_chunk(done=True, prompt=3, completion=2)):
            self.wfile.write((json.dumps(teil) + "\n").encode())
            self.wfile.flush()


def test_echter_http_weg():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{server.server_address[1]}"
        dienst = ollama.Dienst(adresse)
        assert dienst.version() == "9.9.9"
        with pytest.raises(ollama.OllamaFehler) as info:
            dienst.faehigkeiten("fehlt:1b")
        assert info.value.art == "modell_fehlt" and info.value.status_code == 404
        client = ollama.OllamaClient(adresse)
        text = "".join(t.choices[0].delta.content or "" for t in
                       client.chat.completions.create(model="m", messages=[], stream=True) if t.choices)
        assert text == "Hallo lokal"
    finally:
        server.shutdown()
        server.server_close()
    with pytest.raises(ollama.OllamaFehler) as info:
        ollama.Dienst(adresse).version()   # Server weg = "laeuft nicht"
    assert info.value.art == "offline"


class _Traege(BaseHTTPRequestHandler):
    """Ollama "rechnet" lange, bevor die erste Antwort kommt (Modell laden, langen Text lesen)."""

    def log_message(self, *a):
        pass

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        import time

        time.sleep(4)
        try:
            self.send_response(200)
            self.end_headers()
        except OSError:
            pass


def test_stopp_auch_waehrend_ollama_noch_rechnet():
    import time

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Traege)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = ollama.OllamaClient(f"http://127.0.0.1:{server.server_address[1]}")
        fehler = []

        def frage():
            try:
                client.chat.completions.create(model="m", messages=[], stream=True)
            except ollama.OllamaFehler as exc:
                fehler.append(exc)

        t = threading.Thread(target=frage)
        start = time.monotonic()
        t.start()
        time.sleep(0.4)
        client.abbrechen()
        t.join(3)
        assert not t.is_alive() and fehler and time.monotonic() - start < 3
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Gehirn einschalten
# ---------------------------------------------------------------------------
def test_ollama_einschalten(cfg):
    cfg.provider.aktiv = "claude"
    off = schluessel.setup(cfg, provider="ollama", http=FakeOllama(offline=True))
    assert not off["ok"] and off["kind"] in ("ollama_offline", "ollama_missing") and cfg.active_provider == "claude"
    forced = schluessel.setup(cfg, provider="ollama", test=False, http=FakeOllama(offline=True))
    assert forced["ok"] and cfg.active_provider == "ollama"
    cfg.provider.aktiv = "claude"
    # eingestelltes Modell fehlt, ein anderes ist da -> das andere nehmen
    r = schluessel.setup(cfg, provider="ollama", http=FakeOllama(caps={"llama3.2:3b": ["completion", "tools"]}))
    assert r["ok"] and r["changed_provider"] and cfg.ollama.model == "llama3.2:3b" and "kostenlos" in r["message"]
    assert load_config(cfg.project_root).active_provider == "ollama"
    leer = schluessel.setup(cfg, provider="ollama", http=FakeOllama(caps={}, models=[]))
    assert leer["ok"] and "/ollama laden" in leer["message"]


def test_beschreibung_fuer_die_app(cfg):
    info = schluessel.describe(cfg)
    o = next(p for p in info["providers"] if p["id"] == "ollama")
    assert o["has_key"] and o["needs_key"] is False and o["model"] == "qwen3.5:4b"
    assert info["providers"][0]["id"] == "deepseek" and info["key_missing"] is False
    kind, message = schluessel.classify(ollama.OllamaFehler("x", "offline"), "ollama")
    assert kind == "ollama_offline"
    assert schluessel.friendly_error(ollama.OllamaFehler("Modell fehlt", "modell_fehlt"), "ollama") == "Modell fehlt"


def test_werkzeug_gehirn_einstellen(cfg, monkeypatch):
    from assistant.tools.gehirn import GehirnEinstellenTool
    from types import SimpleNamespace

    monkeypatch.setattr(ollama, "status", lambda config, http=None: {
        "laeuft": True, "modelle": [{"name": "qwen3.5:4b"}], "fehler": ""})
    ctx = SimpleNamespace(extra={"config": cfg}, permissions=SimpleNamespace(away=False, require=lambda *a: None))
    tool = GehirnEinstellenTool()
    assert "qwen3.5:4b" in tool.run(ctx, "anzeigen")
    assert "noch nicht heruntergeladen" in tool.run(ctx, "setzen", modell="qwen3.5:9b")
    assert cfg.ollama.model == "qwen3.5:4b"
    assert tool.run(ctx, "setzen", denken="gruendlich").startswith("Eingestellt")
    assert "/gehirn ollama" in tool.description


# ---------------------------------------------------------------------------
# Nachbesserungen nach dem Review
# ---------------------------------------------------------------------------
def test_client_passt_immer_zur_adresse(tmp_path, cfg, monkeypatch):
    import sys

    prov, mem = _provider(tmp_path, cfg, FakeOllama())
    alt = prov.client
    cfg.ollama.kontext = 32768
    prov.settings_changed()
    assert prov.client is alt and alt.kontext == 32768            # gleiche Adresse: weiterbenutzen
    cfg.ollama.adresse = "http://127.0.0.1:11435"
    prov.settings_changed()
    assert isinstance(prov.client, ollama.OllamaClient) and prov.client is not alt
    assert prov.client.dienst.adresse == "http://127.0.0.1:11435"
    pytest.importorskip("openai")
    cfg.ollama.adresse = "http://localhost:1234/v1"
    prov.settings_changed()
    assert type(prov.client).__name__ == "OpenAI" and str(prov.client.base_url).rstrip("/") == cfg.ollama.adresse
    cfg.ollama.adresse = "http://localhost:5678/v1"              # /v1 -> anderes /v1
    prov.settings_changed()
    assert str(prov.client.base_url).rstrip("/") == "http://localhost:5678/v1"
    monkeypatch.setitem(sys.modules, "openai", None)            # openai fehlt -> kein Client
    cfg.ollama.adresse = "http://localhost:9999/v1"
    prov.settings_changed()
    assert prov.client is None
    cfg.ollama.adresse = "http://localhost:11434"               # zurueck zu Ollama: wieder ein Client
    prov.settings_changed()
    assert isinstance(prov.client, ollama.OllamaClient) and prov.client.dienst.adresse == "http://localhost:11434"
    # neues Gespraech bekommt den alten Client - mit inzwischen anderer Adresse
    cfg.ollama.adresse = "http://127.0.0.1:2222"
    neu = OllamaProvider(cfg, "S", build_registry(), prov.tool_ctx, client=prov.client)
    assert neu.client is not prov.client and neu.client.dienst.adresse == "http://127.0.0.1:2222"
    mem.close()


def test_kostenlose_token_kosten_nach_dem_wechsel_nichts(tmp_path, cfg):
    from assistant.abwesend import settings_session
    from assistant.brain import Brain
    from tests._fakes import DSClient, ds_text_chunk, ds_usage_chunk

    prov, mem = _provider(tmp_path, cfg, FakeOllama(chats=[[ollama_chunk("hi", done=True, prompt=900_000,
                                                                          completion=100_000)]]))
    brain = Brain(cfg, mem, build_registry(), prov.tool_ctx, provider=prov)
    brain.respond("Hallo")
    assert brain.usage.total_tokens == 1_000_000 and brain.cost() == (0.0, 0.0)
    cfg.deepseek_api_key = "sk-1234567890abcdef1234567890ab"
    cfg.provider.aktiv = "deepseek"
    brain.switch_provider()
    assert brain.provider.name == "deepseek" and brain.usage.total_tokens == 1_000_000
    assert brain.cost() == (0.0, 0.0) and brain.cost_now_eur() == 0.0       # keine Phantom-Kosten
    session = settings_session(cfg.afk, "", None, None, start_eur=brain.cost_now_eur())
    assert session.start_eur == 0.0
    # danach zaehlt DeepSeek ganz normal (nur seine Token)
    brain.provider.client = DSClient([[ds_text_chunk("ok"), ds_usage_chunk(prompt=1_000_000, completion=0)]])
    brain.respond("Weiter")
    usd, _ = brain.cost()
    assert usd > 0 and usd == pytest.approx(brain.usage.usd)
    assert usd < 1_000_000 * 2 * 0.3 / 1_000_000                 # nur DeepSeeks 1 Mio. Token, nicht 2 Mio.
    mem.close()


def test_einschalten_nimmt_nie_ein_embedding_modell(cfg):
    cfg.provider.aktiv = "claude"
    nur_embedding = FakeOllama(caps={"all-minilm:latest": ["embedding"]})
    r = schluessel.setup(cfg, provider="ollama", http=nur_embedding)
    assert r["ok"] and cfg.ollama.model == "qwen3.5:4b" and "noch kein passendes Modell" in r["message"]
    gemischt = FakeOllama(caps={"all-minilm:latest": ["embedding"], "gemma3:4b": ["completion", "vision"],
                                "llama3.2:3b": ["completion", "tools"]})
    schluessel.setup(cfg, provider="ollama", http=gemischt)
    assert cfg.ollama.model == "llama3.2:3b"                     # mit Werkzeugen bevorzugt
    cfg.ollama.model = "fehlt:1b"
    schluessel.setup(cfg, provider="ollama", http=FakeOllama(caps={"all-minilm:latest": ["embedding"],
                                                                   "gemma3:4b": ["completion", "vision"]}))
    assert cfg.ollama.model == "gemma3:4b"                       # notfalls ohne Werkzeuge


def test_claude_und_deepseek_namen_sind_keine_ollama_modelle(cfg):
    for name, gehirn in (("sonnet", "Claude"), ("opus", "Claude"), ("flash", "DeepSeek"),
                         ("deepseek-chat", "DeepSeek")):
        r = modelle.waehle(cfg, "ollama", model=name, http=FakeOllama(offline=True))
        assert not r["ok"] and gehirn in r["message"] and cfg.ollama.model == "qwen3.5:4b"
    r = modelle.waehle(cfg, "ollama", model="qwen3.5:9b", http=FakeOllama())   # laeuft, nicht heruntergeladen
    assert not r["ok"] and "/ollama laden qwen3.5:9b" in r["message"] and cfg.ollama.model == "qwen3.5:4b"
    r = modelle.waehle(cfg, "ollama", model="gemma3:4b",
                       http=FakeOllama(caps={"qwen3.5:4b": ["completion"], "gemma3:4b": ["completion"]}))
    assert r["ok"] and cfg.ollama.model == "gemma3:4b"
    r = modelle.waehle(cfg, "ollama", model="llama3.2:3b", http=FakeOllama(offline=True))  # nicht pruefbar
    assert r["ok"] and cfg.ollama.model == "llama3.2:3b"


def test_meldung_nennt_keine_falsche_adresse():
    kind, message = schluessel.classify(ConnectionRefusedError("connection refused"), "ollama")
    assert kind == "ollama_offline" and "localhost" not in message and "Ollama antwortet nicht" in message
    kind, message = schluessel.classify(ollama.OllamaFehler(
        ollama.NICHT_ERREICHBAR.format(adresse="http://pc2:11434"), "offline"), "ollama")
    assert "http://pc2:11434" in message
