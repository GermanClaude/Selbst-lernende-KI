from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext
from assistant.providers.deepseek_provider import DeepSeekProvider

from tests._fakes import (
    DSClient,
    ds_text_chunk,
    ds_toolcall_chunk,
    ds_usage_chunk,
)


def _provider(tmp_path, scripted_streams):
    cfg = load_config()
    cfg.provider.aktiv = "deepseek"
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    reg = build_registry()
    ctx = ToolContext(permissions=pm, memory=mem)
    prov = DeepSeekProvider(cfg, "SYSTEM", reg, ctx, client=DSClient(scripted_streams))
    return prov, mem


def test_system_prompt_is_first_message(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("hi"), ds_usage_chunk()]])
    assert prov.messages[0]["role"] == "system"
    assert prov.messages[0]["content"] == "SYSTEM"
    mem.close()


def test_plain_text_and_usage(tmp_path):
    stream = [ds_text_chunk("Hallo "), ds_text_chunk("Welt"),
              ds_usage_chunk(prompt=120, completion=40, cache_hit=100)]
    prov, mem = _provider(tmp_path, [stream])
    collected = []
    out = prov.respond("Hi", on_text=collected.append)
    assert "Hallo Welt" in out
    assert "".join(collected).startswith("Hallo Welt")
    # Cache-Treffer korrekt verbucht.
    assert prov.usage.cache_hit_tokens == 100
    assert prov.usage.input_full_tokens == 20  # 120 - 100
    assert prov.usage.output_tokens == 40
    mem.close()


def test_tool_call_accumulation_and_execution(tmp_path):
    # Erste Runde: Werkzeugaufruf in Fragmenten; zweite Runde: Textantwort.
    turn1 = [
        ds_toolcall_chunk(0, tid="call_1", name="system_info", args_fragment="{}"),
        ds_usage_chunk(),
    ]
    turn2 = [ds_text_chunk("System ist bereit."), ds_usage_chunk()]
    prov, mem = _provider(tmp_path, [turn1, turn2])
    out = prov.respond("Systeminfo")
    assert "bereit" in out
    # Es muss eine tool-Rolle im Verlauf geben.
    assert any(m["role"] == "tool" for m in prov.messages)
    # Assistenten-Nachricht mit tool_calls im OpenAI-Format.
    assert any(m["role"] == "assistant" and m.get("tool_calls") for m in prov.messages)
    mem.close()


def test_toolcall_args_in_fragments(tmp_path):
    # Argumente kommen in mehreren Fragmenten an und muessen zusammengesetzt werden.
    turn1 = [
        ds_toolcall_chunk(0, tid="c1", name="merken", args_fragment='{"inha'),
        ds_toolcall_chunk(0, args_fragment='lt": "Testfakt"}'),
        ds_usage_chunk(),
    ]
    turn2 = [ds_text_chunk("Gemerkt."), ds_usage_chunk()]
    prov, mem = _provider(tmp_path, [turn1, turn2])
    prov.respond("merk dir was")
    # Der Fakt muss tatsaechlich im Gedaechtnis gelandet sein.
    assert any("Testfakt" in f.content for f in mem.top_facts())
    mem.close()


def test_missing_client_is_graceful(tmp_path):
    cfg = load_config()
    cfg.provider.aktiv = "deepseek"
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path)
    reg = build_registry()
    ctx = ToolContext(permissions=pm, memory=mem)
    prov = DeepSeekProvider(cfg, "SYSTEM", reg, ctx, client=None)
    # Ohne Schluessel/Bibliothek wird der Client None - freundliche Meldung statt Absturz.
    if prov.client is None:
        out = prov.respond("hallo")
        assert "openai" in out.lower() or "deepseek" in out.lower()
    mem.close()
