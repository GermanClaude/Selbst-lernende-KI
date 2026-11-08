"""Bilder sehen (0.7.0): Bilder im Chat und in Werkzeug-Ergebnissen, fuer Claude und DeepSeek.

Wichtig dabei: Claude-Verlauf bleibt append-only (ein Bild-Block wird nie mehr veraendert),
ohne Bilder bleiben alle Anfragen genau wie bisher, und DeepSeek V4 Pro (sieht keine Bilder)
bekommt eine Beschreibung von DeepSeek Flash.
"""
from __future__ import annotations

import json
import struct
import zlib
from types import SimpleNamespace

import pytest

from assistant.bilder import Bild, vorbereiten
from assistant.brain import CONTINUE_PROMPT, Brain
from assistant.config import load_config
from assistant.memory import Memory
from assistant.modelle import DEEPSEEK_SEHMODELL, MODELLE, beschreibung, sieht_bilder
from assistant.permissions import PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.providers.anthropic_provider import _history_as_text as anthro_history_text
from assistant.providers.base import (
    BILD_ABGELEHNT,
    BILD_ZEICHEN,
    LEER_BILDER,
    LEER_EIN_BILD,
    LLMProvider,
    bild_gewicht,
)
from assistant.providers.deepseek_provider import DeepSeekProvider
from assistant.providers.deepseek_provider import _history_as_text as ds_history_text
from assistant.tools import ToolContext, build_registry
from assistant.tools.base import Tool, ToolOutput, ToolRegistry

from tests._fakes import (
    AnthroClient,
    DSClient,
    anthro_msg,
    ds_reply,
    ds_text_chunk,
    ds_toolcall_chunk,
    ds_usage_chunk,
    dump,
    text_block,
    tool_use_block,
)


# ----- Hilfen -------------------------------------------------------------------
def _png(breite: int = 4, hoehe: int = 3, farbe=(200, 30, 30)) -> bytes:
    """Gueltiges PNG ohne Pillow (damit die Tests auch ohne Pillow laufen)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    zeile = b"\x00" + bytes(farbe) * breite
    roh = zlib.compress(zeile * hoehe)
    ihdr = struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", roh) + chunk(b"IEND", b"")


def _bild(name: str = "foto.png", farbe=(200, 30, 30)) -> Bild:
    return vorbereiten(_png(farbe=farbe), name)


def _setup(tmp_path):
    cfg = load_config()
    cfg.economy.aktiv = False
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    reg = build_registry()
    ctx = ToolContext(permissions=pm, memory=mem, extra={"config": cfg})
    return cfg, mem, reg, ctx


def _anthropic(tmp_path, scripted):
    cfg, mem, reg, ctx = _setup(tmp_path)
    return AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient(scripted)), mem


def _deepseek(tmp_path, streams, model="deepseek-flash", non_stream=None):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.provider.aktiv = "deepseek"
    cfg.deepseek.model = model
    cfg.deepseek.denken = "aus"
    return DeepSeekProvider(cfg, "SYSTEM", reg, ctx, client=DSClient(streams, non_stream)), mem


def _ok(text="ok"):
    return (anthro_msg([text_block(text)]), [])


def _ds_ok(text="ok"):
    return [ds_text_chunk(text), ds_usage_chunk()]


class BildWerkzeug(Tool):
    """Werkzeug, das ein Bild mitliefert (wie bildschirmfoto)."""

    name = "zz_bild_test"
    description = "Test: liefert ein Bild."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, text="Hier das Bild.", farbe=(10, 200, 10)):
        self.text, self.farbe = text, farbe

    def run(self, ctx):
        return ToolOutput(self.text, [_bild("werkzeug.png", self.farbe)])


def _image_parts(content):
    return [p for p in content if isinstance(p, dict) and p.get("type") in ("image", "image_url")]


# ----- Modelle ------------------------------------------------------------------
def test_which_models_see_images():
    for m in MODELLE["claude"]:
        assert sieht_bilder("claude", m["id"]) is True
    assert sieht_bilder("deepseek", "deepseek-flash") is True
    assert sieht_bilder("deepseek", "deepseek-v4-pro") is False
    assert sieht_bilder("claude", "claude-opus-9-9") is True      # unbekanntes Claude: ja
    assert sieht_bilder("deepseek", "deepseek-v9-ultra") is False  # unbekanntes DeepSeek: nein
    assert sieht_bilder("deepseek", "deepseek-v4-flash-vision-exp") is True  # laeuft auf Flash
    assert sieht_bilder("deepseek", "") is False
    assert DEEPSEEK_SEHMODELL == "deepseek-flash" and sieht_bilder("deepseek", DEEPSEEK_SEHMODELL)


def test_model_description_shows_who_sees_images(tmp_path):
    cfg = load_config(tmp_path)
    info = beschreibung(cfg)
    flags = {m["id"]: m["sieht_bilder"] for m in info["deepseek"]["modelle"]}
    assert flags == {"deepseek-flash": True, "deepseek-v4-pro": False}
    assert all(m["sieht_bilder"] for m in info["claude"]["modelle"])


# ----- ToolOutput / Registry ----------------------------------------------------
def test_registry_passes_tool_output_through(tmp_path):
    _cfg, mem, _reg, ctx = _setup(tmp_path)
    reg = ToolRegistry()
    reg.register(BildWerkzeug())
    out, err = reg.execute(ctx, "zz_bild_test", {})
    assert not err and isinstance(out, ToolOutput) and len(out.bilder) == 1
    assert str(out) == "Hier das Bild. [Bild: werkzeug.png]"
    out, err = build_registry().execute(ctx, "system_info", {})
    assert isinstance(out, str) and not err  # Text-Werkzeuge wie bisher
    mem.close()


def test_economy_cut_never_touches_image_data(tmp_path):
    prov, mem = _anthropic(tmp_path, [])
    prov.config.economy.aktiv = True
    prov.config.economy.max_werkzeug_ausgabe = 20
    prov.registry.register(BildWerkzeug(text="x" * 500))
    out, err = prov._exec_tool("zz_bild_test", {})
    assert isinstance(out, ToolOutput) and not err
    assert out.text.startswith("x" * 20) and "gekuerzt" in out.text and len(out.text) < 100
    assert out.bilder[0].data == _bild("werkzeug.png", (10, 200, 10)).data
    mem.close()


def test_tool_output_without_images_is_plain_text(tmp_path):
    prov, mem = _anthropic(tmp_path, [])

    class Leer(Tool):
        name = "zz_leer"
        input_schema = {"type": "object", "properties": {}, "required": []}

        def run(self, ctx):
            return ToolOutput("nur Text")

    prov.registry.register(Leer())
    assert prov._exec_tool("zz_leer", {}) == ("nur Text", False)
    mem.close()


# ----- Claude: Nachricht mit Bildern -------------------------------------------
def test_claude_payload_one_image_before_text(tmp_path):
    prov, mem = _anthropic(tmp_path, [_ok("Ein rotes Bild.")])
    bild = _bild()
    assert "rot" in prov.respond("Was siehst du?", bilder=[bild])
    content = prov.client.messages.last_kwargs["messages"][0]["content"]
    assert content == [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": bild.b64()}},
        {"type": "text", "text": "Was siehst du?"},
    ]
    assert prov.user_turns() == 1
    mem.close()


def test_claude_payload_several_images_and_empty_text(tmp_path):
    prov, mem = _anthropic(tmp_path, [_ok(), _ok()])
    a, b = _bild("a.png"), _bild("b.png", (0, 0, 255))
    prov.respond("", bilder=[a, b])
    content = prov.client.messages.last_kwargs["messages"][0]["content"]
    assert [p["type"] for p in content] == ["text", "image", "text", "image", "text"]
    assert content[0]["text"] == "Bild 1:" and content[2]["text"] == "Bild 2:"
    assert content[1]["source"]["data"] == a.b64() and content[3]["source"]["data"] == b.b64()
    assert content[-1]["text"] == LEER_BILDER
    prov.respond("  ", bilder=[a])
    assert prov.messages[-2]["content"][-1] == {"type": "text", "text": LEER_EIN_BILD}
    mem.close()


def test_claude_without_images_request_is_unchanged(tmp_path):
    prov, mem = _anthropic(tmp_path, [_ok("Hallo!")])
    prov.respond("Hi")
    assert prov.client.messages.requests[0] == json.dumps([{"role": "user", "content": "Hi"}], ensure_ascii=False)
    assert prov.messages[0] == {"role": "user", "content": "Hi"}
    mem.close()


def test_claude_history_is_append_only_with_images(tmp_path):
    turns = [_ok("Erstes."), (anthro_msg([tool_use_block("system_info", "t1", {})], stop_reason="tool_use"), []),
             _ok("Zweites."), _ok("Drittes.")]
    prov, mem = _anthropic(tmp_path, turns)
    prov.respond("Schau mal", bilder=[_bild()])
    first = prov.client.messages.requests[0]
    first_turn = json.loads(first)[0]
    prov.respond("Und jetzt?")
    prov.respond("Noch was", bilder=[_bild("zwei.png", (1, 2, 3))])
    requests = prov.client.messages.requests
    assert len(requests) == 4
    for later in requests[1:]:
        # Der erste Bild-Turn wird bei jeder weiteren Anfrage byte-gleich mitgeschickt ...
        assert later.startswith(first[:-1])
        assert json.loads(later)[0] == first_turn
    # ... und jede Anfrage beginnt mit der vorigen (nur angehaengt, nichts veraendert).
    for before, after in zip(requests, requests[1:]):
        assert after.startswith(before[:-1])
    mem.close()


def test_claude_counts_image_turns_and_their_size(tmp_path):
    turns = [(anthro_msg([tool_use_block("system_info", "t1", {})], stop_reason="tool_use"), []), _ok()]
    prov, mem = _anthropic(tmp_path, turns)
    prov.respond("a", bilder=[_bild(), _bild("b.png")])
    assert prov.user_turns() == 1  # das Werkzeug-Ergebnis zaehlt nicht
    assert prov.history_chars() >= 2 * BILD_ZEICHEN
    assert prov.history_chars() < 2 * BILD_ZEICHEN + 2000  # Base64 zaehlt nicht als Text
    assert bild_gewicht(10) == BILD_ZEICHEN and bild_gewicht(64 * 50_000) == 50_000
    mem.close()


def test_claude_images_trigger_compaction(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.conversation.max_verlauf_zeichen = 3 * BILD_ZEICHEN
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_ok()]))
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    brain.respond("zwei Bilder", bilder=[_bild(), _bild("b.png")])
    assert prov.history_length() == 2  # noch unter der Grenze
    brain.respond("noch zwei", bilder=[_bild("c.png"), _bild("d.png")])
    assert prov.history_length() == 2 and "Zusammenfassung" in prov.messages[0]["content"]
    assert len(mem.recent_episodes()) >= 1
    mem.close()


def test_claude_summary_text_has_placeholders_not_base64(tmp_path):
    prov, mem = _anthropic(tmp_path, [(anthro_msg([tool_use_block("zz_bild_test", "t1", {})],
                                                  stop_reason="tool_use"), []), _ok("fertig")])
    prov.registry.register(BildWerkzeug())
    bild = _bild("urlaub.png")
    prov.respond("Was ist das?", bilder=[bild])
    text = anthro_history_text(prov.messages)
    assert "[Bild: urlaub.png]" in text and "Was ist das?" in text
    assert "werkzeug-ergebnis: Hier das Bild. [Bild: werkzeug.png]" in text
    assert bild.b64() not in text and "base64" not in text
    mem.close()


def test_claude_drop_and_abort_with_image_turn(tmp_path):
    prov, mem = _anthropic(tmp_path, [_ok(), _ok()])
    prov.respond("erst")
    snapshot = prov.history_snapshot()
    prov.respond("Wie wird das?", bilder=[_bild()])
    assert prov.drop_turn(snapshot, "Wie wird das?") is True
    assert len(prov.messages) == 2 and prov.messages[-1]["role"] == "assistant"

    snapshot = prov.history_snapshot()
    prov.messages.append({"role": "user", "content": prov._user_content("abgebrochen", [_bild()])})
    block = dict(prov.messages[-1]["content"][0])
    prov.abort_turn(snapshot, "abgebrochen")
    assert prov.messages[-1]["role"] == "assistant"
    assert prov.messages[-2]["content"][0] == block  # Bild-Block unveraendert
    assert prov.drop_turn(0, "anderer Text") is False
    mem.close()


def test_claude_rejected_image_turn_is_taken_back(tmp_path):
    import anthropic

    class Abgelehnt(anthropic.APIStatusError):
        def __init__(self):  # ohne echte HTTP-Antwort
            Exception.__init__(self, "Could not process image")
            self.status_code = 400
            self.message = "Could not process image"

    prov, mem = _anthropic(tmp_path, [_ok("erste"), Abgelehnt(), _ok("weiter")])
    prov.respond("Hallo")
    shown = []
    assert prov.respond("Bild!", on_text=shown.append, bilder=[_bild()]) == BILD_ABGELEHNT
    assert "Could not process image" in "".join(shown)
    assert len(prov.messages) == 2  # die abgelehnte Nachricht ist wieder heraus
    prov.respond("Nochmal ohne")
    assert "image" not in prov.client.messages.requests[-1]
    assert prov.client.messages.requests[-1].startswith(prov.client.messages.requests[0][:-1])
    mem.close()


def test_claude_other_errors_keep_the_image_turn(tmp_path):
    class Weg(Exception):
        pass

    prov, mem = _anthropic(tmp_path, [Weg("Verbindung weg")])
    out = prov.respond("Bild!", bilder=[_bild()])
    assert "Problem" in out and len(prov.messages) == 1  # wie bisher: Nachricht bleibt
    mem.close()


# ----- Claude: Werkzeug mit Bild -----------------------------------------------
def test_claude_tool_result_with_image(tmp_path):
    turns = [(anthro_msg([tool_use_block("zz_bild_test", "t1", {})], stop_reason="tool_use"), []),
             _ok("Gruen."), _ok("weiter")]
    prov, mem = _anthropic(tmp_path, turns)
    prov.registry.register(BildWerkzeug())
    prov.respond("Was zeigt das Werkzeug?")
    result = prov.messages[2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1" and result["is_error"] is False
    bild = _bild("werkzeug.png", (10, 200, 10))
    assert result["content"] == [
        {"type": "text", "text": "Hier das Bild."},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": bild.b64()}},
    ]
    assert prov.user_turns() == 1
    before = prov.client.messages.requests[-1]
    prov.respond("Und?")
    assert prov.client.messages.requests[-1].startswith(before[:-1])
    mem.close()


# ----- Brain --------------------------------------------------------------------
class RecordingProvider(LLMProvider):
    name = "fake"

    def __init__(self, cfg, mem, hit=True):
        reg = build_registry()
        ctx = ToolContext(permissions=PermissionManager(cfg.permissions, cfg.workspace_path), memory=mem)
        super().__init__(cfg, "SYSTEM", reg, ctx)
        self.calls = []
        self.hit = hit

    def respond(self, user_text, on_text=None, max_tool_rounds=25, announce_limit=True, **kwargs):
        self.calls.append((user_text, kwargs))
        self.hit_limit = self.hit and len(self.calls) == 1
        return "Teil"

    def history_length(self):
        return 0

    def summarize_history(self):
        return ""

    def reset_to_summary(self, summary):
        pass


def test_brain_sends_images_only_with_the_first_part(tmp_path):
    cfg = load_config()
    cfg.conversation.automatisch_weiter = 2
    mem = Memory(tmp_path / "m.sqlite3")
    prov = RecordingProvider(cfg, mem)
    brain = Brain(cfg, mem, prov.registry, prov.tool_ctx, provider=prov)
    bild = _bild()
    brain.respond("Mach was mit dem Bild", bilder=[bild])
    assert prov.calls[0] == ("Mach was mit dem Bild", {"bilder": [bild]})
    assert prov.calls[1] == (CONTINUE_PROMPT, {})

    prov.calls.clear()
    prov.hit = False
    brain.respond("ohne Bild")
    brain.respond("leer", bilder=[])
    assert prov.calls == [("ohne Bild", {}), ("leer", {})]  # genau der Aufruf wie bisher
    mem.close()


# ----- DeepSeek Flash: sieht Bilder ---------------------------------------------
def test_deepseek_flash_payload(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok("Rot."), _ds_ok()])
    a, b = _bild("a.png"), _bild("b.png", (0, 0, 255))
    prov.respond("Was ist das?", bilder=[a])
    sent = prov.client.chat.completions.last_kwargs["messages"]
    assert sent[1] == {"role": "user", "content": [
        {"type": "text", "text": "Was ist das?"},
        {"type": "image_url", "image_url": {"url": a.data_url()}},
    ]}
    assert a.data_url().startswith("data:image/png;base64,")
    prov.respond("", bilder=[a, b])
    content = prov.client.chat.completions.last_kwargs["messages"][3]["content"]
    assert [p["type"] for p in content] == ["text", "text", "image_url", "text", "image_url"]
    assert content[0]["text"] == LEER_BILDER and content[1]["text"] == "Bild 1:" and content[3]["text"] == "Bild 2:"
    assert not prov.client.chat.completions.non_stream_calls  # kein Nebenaufruf noetig
    assert prov.user_turns() == 2
    mem.close()


def test_deepseek_without_images_request_is_unchanged(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok()])
    prov.respond("Hi")
    sent = prov.client.chat.completions.last_kwargs["messages"]
    assert sent == [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "Hi"}]
    assert all(a is b for a, b in zip(sent, prov.messages))  # unveraendert durchgereicht
    mem.close()


def test_deepseek_history_is_append_only_with_images(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok("eins"), _ds_ok("zwei")])
    prov.respond("Schau", bilder=[_bild()])
    prov.respond("Und?")
    first, second = prov.client.chat.completions.requests
    assert second[: len(first)] == first
    assert dump(second[1]) == dump(first[1])
    mem.close()


def test_deepseek_tool_image_comes_after_all_tool_answers(tmp_path):
    turn1 = [ds_toolcall_chunk(0, tid="c1", name="zz_bild_test", args_fragment="{}"),
             ds_toolcall_chunk(1, tid="c2", name="system_info", args_fragment="{}"), ds_usage_chunk()]
    prov, mem = _deepseek(tmp_path, [turn1, _ds_ok("Gruen.")])
    prov.registry.register(BildWerkzeug())
    prov.respond("Werkzeug!")
    roles = [m["role"] for m in prov.messages]
    assert roles == ["system", "user", "assistant", "tool", "tool", "user", "assistant"]
    assert prov.messages[3]["content"] == "Hier das Bild." and isinstance(prov.messages[4]["content"], str)
    images_msg = prov.messages[5]["content"]
    assert images_msg[0] == {"type": "text", "text": "Bild vom Werkzeug zz_bild_test:"}
    assert images_msg[1]["image_url"]["url"] == _bild("werkzeug.png", (10, 200, 10)).data_url()
    assert prov.client.chat.completions.last_kwargs["messages"][5] == {"role": "user", "content": images_msg}
    assert prov.user_turns() == 1  # die Werkzeug-Bilder zaehlen nicht als Nachricht
    assert "werkzeug-ergebnis: Hier das Bild." in ds_history_text(prov.messages)
    assert "[Bild: werkzeug.png]" in ds_history_text(prov.messages)
    mem.close()


def test_deepseek_economy_never_cuts_image_data(tmp_path):
    turn1 = [ds_toolcall_chunk(0, tid="c1", name="zz_bild_test", args_fragment="{}"), ds_usage_chunk()]
    prov, mem = _deepseek(tmp_path, [turn1, _ds_ok()])
    prov.config.economy.aktiv = True
    prov.config.economy.max_werkzeug_ausgabe = 10
    prov.registry.register(BildWerkzeug(text="y" * 300))
    prov.respond("los")
    assert "gekuerzt" in prov.messages[3]["content"]
    url = prov.messages[4]["content"][1]["image_url"]["url"]
    assert url == _bild("werkzeug.png", (10, 200, 10)).data_url()
    mem.close()


def test_deepseek_history_size_and_summary_with_images(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok("Antwort")])
    bild = _bild("katze.png")
    prov.respond("Wie heisst die Katze?", bilder=[bild])
    chars = prov.history_chars()
    assert BILD_ZEICHEN <= chars < BILD_ZEICHEN + 200
    text = ds_history_text(prov.messages)
    assert "user: Wie heisst die Katze?" in text and "[Bild: katze.png]" in text
    assert bild.b64() not in text
    # Kuerzen alter Werkzeug-Ausgaben stolpert nicht ueber Listen-Inhalt.
    prov.messages.append({"role": "tool", "tool_call_id": "x", "content": ["kein Text"]})
    assert prov._shrink_old_tool_outputs(keep_last=0) is False
    mem.close()


def test_deepseek_thinking_error_with_image_falls_back(tmp_path):
    class DenkFehler(Exception):
        status_code = 400

    prov, mem = _deepseek(tmp_path, [DenkFehler("thinking mode does not support image input"), _ds_ok("Ohne Denken.")])
    prov.config.deepseek.denken = "high"
    out = prov.respond("Bild?", bilder=[_bild()])
    assert out == "Ohne Denken." and prov._thinking_off
    assert _image_parts(prov.client.chat.completions.last_kwargs["messages"][1]["content"])
    assert prov.client.chat.completions.last_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    mem.close()


def test_deepseek_rejected_image_turn_is_taken_back(tmp_path):
    class Abgelehnt(Exception):
        status_code = 400

    prov, mem = _deepseek(tmp_path, [_ds_ok("hallo"), Abgelehnt("unsupported image"), _ds_ok("weiter")])
    prov.respond("Hi")
    assert prov.respond("Bild", bilder=[_bild()]) == BILD_ABGELEHNT
    assert len(prov.messages) == 3
    prov.respond("ohne")
    assert "image_url" not in json.dumps(prov.client.chat.completions.last_kwargs["messages"])
    mem.close()


# ----- DeepSeek V4 Pro: sieht keine Bilder -> Beschreibung von Flash ------------
def test_deepseek_pro_gets_a_description_from_flash(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok("Eine rote Flaeche.")], model="deepseek-v4-pro",
                          non_stream=lambda **kw: ds_reply("Eine rote Flaeche mit dem Text HALLO.",
                                                           prompt=1000, completion=100))
    bild = _bild()
    usd_before = prov.usage.usd
    prov.respond("Was steht da?", bilder=[bild])
    side = prov.client.chat.completions.non_stream_calls
    assert len(side) == 1
    call = side[0]
    assert call["model"] == DEEPSEEK_SEHMODELL and call["stream"] is False
    assert call["extra_body"] == {"thinking": {"type": "disabled"}} and "tools" not in call
    assert call["timeout"] and call["messages"][0]["content"][1] == {
        "type": "image_url", "image_url": {"url": bild.data_url()}}
    assert "Deutsch" in call["messages"][0]["content"][0]["text"]
    sent = prov.client.chat.completions.last_kwargs
    assert sent["model"] == "deepseek-v4-pro"
    user = sent["messages"][1]["content"]
    assert user == "[Bild 1 – Beschreibung: Eine rote Flaeche mit dem Text HALLO.]\n\nWas steht da?"
    assert "image_url" not in json.dumps(sent["messages"])
    # Kosten der Beschreibung zaehlen mit - zum Flash-Preis.
    flash_usd, _ = prov.config.cost_estimate(1000, 0, 100, provider="deepseek", model="deepseek-flash",
                                             per_request=True)
    pro_usd, _ = prov.config.cost_estimate(100, 0, 50, provider="deepseek", per_request=True)
    assert prov.usage.usd - usd_before == pytest.approx(flash_usd + pro_usd)
    assert prov.user_turns() == 1
    # drop_turn erkennt die Nachricht trotz der Beschreibung davor.
    assert prov.drop_turn(1, "Was steht da?") is True and len(prov.messages) == 1
    mem.close()


def test_deepseek_pro_description_failure_is_explained(tmp_path):
    def kaputt(**kw):
        raise RuntimeError("Error code: 400")

    prov, mem = _deepseek(tmp_path, [_ds_ok("Tut mir leid.")], model="deepseek-v4-pro", non_stream=kaputt)
    out = prov.respond("", bilder=[_bild("scan.png")])
    assert out == "Tut mir leid."
    user = prov.client.chat.completions.last_kwargs["messages"][1]["content"]
    assert user.startswith("[Bild 1: [Bild: scan.png] – Bild konnte nicht angesehen werden")
    assert user.endswith(LEER_EIN_BILD)
    mem.close()


def test_deepseek_pro_tool_image_is_described(tmp_path):
    turn1 = [ds_toolcall_chunk(0, tid="c1", name="zz_bild_test", args_fragment="{}"), ds_usage_chunk()]
    prov, mem = _deepseek(tmp_path, [turn1, _ds_ok("Gruen.")], model="deepseek-v4-pro",
                          non_stream=lambda **kw: ds_reply("Eine gruene Flaeche."))
    prov.registry.register(BildWerkzeug())
    prov.respond("Werkzeug!")
    assert [m["role"] for m in prov.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert prov.messages[3]["content"] == "Hier das Bild.\n\n[Bild 1 – Beschreibung: Eine gruene Flaeche.]"
    mem.close()


def test_deepseek_model_switch_turns_old_images_into_text(tmp_path):
    prov, mem = _deepseek(tmp_path, [_ds_ok("Rot."), _ds_ok("Weiss ich noch.")])
    prov.respond("Merk dir das Bild", bilder=[_bild("merken.png")])
    stored = prov.messages[1]
    stored_dump = dump(stored)
    prov.config.deepseek.model = "deepseek-v4-pro"  # z.B. per /modell pro
    prov.respond("Was war auf dem Bild?")
    sent = prov.client.chat.completions.last_kwargs["messages"]
    assert sent[1] == {"role": "user", "content": "Merk dir das Bild\n[Bild: merken.png]"}
    assert "image_url" not in json.dumps(sent)
    assert prov.messages[1] is stored and dump(stored) == stored_dump  # Verlauf bleibt gleich
    # Zurueck auf Flash: das Bild ist wieder echt dabei.
    prov.config.deepseek.model = "deepseek-flash"
    assert prov._request_messages(False)[1] is stored
    mem.close()


# ----- bildschirmfoto -----------------------------------------------------------
class FakePyAutoGui:
    def __init__(self, breite, hoehe, bildschirm=None):
        self.breite, self.hoehe = breite, hoehe
        self.bildschirm = bildschirm or (breite, hoehe)

    def screenshot(self, pfad):
        with open(pfad, "wb") as f:
            f.write(_png(self.breite, self.hoehe, (40, 40, 40)))
        return SimpleNamespace(size=(self.breite, self.hoehe))

    def size(self):
        return self.bildschirm


def _screenshot(tmp_path, monkeypatch, fake):
    from assistant.tools import computer

    monkeypatch.setattr(computer, "_load_pyautogui", lambda: (fake, None))
    _cfg, mem, reg, ctx = _setup(tmp_path)
    out, err = reg.execute(ctx, "bildschirmfoto", {})
    return out, err, mem


def test_screenshot_returns_the_image(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    out, err, mem = _screenshot(tmp_path, monkeypatch, FakePyAutoGui(2000, 1000))
    assert not err and isinstance(out, ToolOutput) and len(out.bilder) == 1
    bild = out.bilder[0]
    assert (bild.breite, bild.hoehe) == (1568, 784)  # einmal verkleinert
    assert (tmp_path / "bildschirmfoto.png").is_file()
    assert "Bildschirmfoto gespeichert" in out.text and "mal 1.276" in out.text
    mem.close()


def test_screenshot_stays_within_claudes_many_image_limit(tmp_path, monkeypatch):
    pytest.importorskip("PIL")
    from assistant.tools import computer

    monkeypatch.setattr(computer, "_load_pyautogui", lambda: (FakePyAutoGui(3840, 2160), None))
    _cfg, mem, reg, ctx = _setup(tmp_path)
    ctx.extra["config"].bilder.max_kantenlaenge = 3000
    out, _err = reg.execute(ctx, "bildschirmfoto", {})
    assert max(out.bilder[0].breite, out.bilder[0].hoehe) == 2000
    mem.close()


def test_screenshot_small_screen_keeps_coordinates(tmp_path, monkeypatch):
    out, err, mem = _screenshot(tmp_path, monkeypatch, FakePyAutoGui(800, 600))
    assert isinstance(out, ToolOutput) and out.bilder[0].mime == "image/png"
    try:
        import PIL  # noqa: F401
    except ImportError:
        assert "Bildgroesse unbekannt" in out.text
    else:
        assert "passen direkt" in out.text
    mem.close()


def test_screenshot_reaches_claude_as_image(tmp_path, monkeypatch):
    from assistant.tools import computer

    monkeypatch.setattr(computer, "_load_pyautogui", lambda: (FakePyAutoGui(640, 480), None))
    turns = [(anthro_msg([tool_use_block("bildschirmfoto", "t1", {})], stop_reason="tool_use"), []),
             _ok("Ich sehe ein graues Fenster.")]
    prov, mem = _anthropic(tmp_path, turns)
    prov.respond("Was ist auf meinem Bildschirm?")
    content = prov.messages[2]["content"][0]["content"]
    assert content[0]["type"] == "text" and "Bildschirmfoto gespeichert" in content[0]["text"]
    assert content[1]["type"] == "image" and content[1]["source"]["media_type"] == "image/png"
    mem.close()


def test_screenshot_without_pyautogui_is_friendly(tmp_path, monkeypatch):
    from assistant.tools import computer

    monkeypatch.setattr(computer, "_load_pyautogui", lambda: (None, "PC-Steuerung nicht verfuegbar."))
    _cfg, mem, reg, ctx = _setup(tmp_path)
    assert reg.execute(ctx, "bildschirmfoto", {}) == ("PC-Steuerung nicht verfuegbar.", False)
    mem.close()
