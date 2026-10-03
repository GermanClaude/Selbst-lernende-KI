from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext
from assistant.providers.anthropic_provider import AnthropicProvider

from tests._fakes import AnthroClient, anthro_msg, text_block, tool_use_block


def _provider(tmp_path, scripted):
    cfg = load_config()
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    reg = build_registry()
    ctx = ToolContext(permissions=pm, memory=mem)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient(scripted))
    return prov, mem


def test_plain_text(tmp_path):
    msg = anthro_msg([text_block("Hallo!")])
    prov, mem = _provider(tmp_path, [(msg, [])])
    out = prov.respond("Hi")
    assert "Hallo" in out
    assert prov.client.messages.calls == 1
    assert prov.usage.output_tokens == 50
    mem.close()


def test_tool_use_then_finish(tmp_path):
    turn1 = (anthro_msg([tool_use_block("system_info", "t1", {})], stop_reason="tool_use"), [])
    turn2 = (anthro_msg([text_block("Dein System ist bereit.")]), [])
    prov, mem = _provider(tmp_path, [turn1, turn2])
    out = prov.respond("Systeminfo")
    assert "bereit" in out
    assert prov.client.messages.calls == 2
    # tool_result muss im Verlauf stehen (append-only).
    assert any(
        isinstance(m["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
        for m in prov.messages
    )
    mem.close()


def test_refusal(tmp_path):
    from types import SimpleNamespace

    msg = anthro_msg([text_block("")], stop_reason="refusal",
                     stop_details=SimpleNamespace(category="cyber"))
    prov, mem = _provider(tmp_path, [(msg, [])])
    out = prov.respond("etwas")
    assert "nicht erfuellen" in out.lower() or "leid" in out.lower()
    mem.close()


def test_usage_accumulates(tmp_path):
    from types import SimpleNamespace

    usage = SimpleNamespace(input_tokens=200, output_tokens=80,
                            cache_read_input_tokens=1000, cache_creation_input_tokens=0)
    msg = anthro_msg([text_block("ok")], usage=usage)
    prov, mem = _provider(tmp_path, [(msg, [])])
    prov.respond("hi")
    assert prov.usage.input_full_tokens == 200
    assert prov.usage.cache_hit_tokens == 1000
    mem.close()
