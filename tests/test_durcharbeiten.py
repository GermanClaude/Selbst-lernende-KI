"""Durcharbeiten (automatisch weiter), Agenten, Strg+C, Zeitlimits."""
from types import SimpleNamespace

import pytest

from assistant.brain import CONTINUE_PROMPT, Brain
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.providers.base import ABORT_NOTE
from assistant.tools import ToolContext, build_registry

from tests._fakes import AnthroClient, anthro_msg, text_block, tool_use_block


def _setup(tmp_path, **conv):
    cfg = load_config()
    for key, value in conv.items():
        setattr(cfg.conversation, key, value)
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    reg = build_registry()
    ctx = ToolContext(permissions=pm, memory=mem)
    return cfg, mem, reg, ctx


def _tool(i, name="system_info", tinput=None):
    return (anthro_msg([tool_use_block(name, f"t{i}", tinput or {})], stop_reason="tool_use"), [])


def _text(t):
    return (anthro_msg([text_block(t)]), [])


def test_keeps_working_past_the_step_limit(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path, max_werkzeug_runden=2, automatisch_weiter=3)
    # 5 Werkzeug-Schritte, dann fertig: braucht 3 Abschnitte a 2 Schritte
    script = [_tool(i) for i in range(5)] + [_text("Alles erledigt.")]
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient(script))
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    shown = []
    out = brain.respond("Bau mir das Projekt", on_text=shown.append)
    assert "Alles erledigt." in out
    assert "Limit" not in out  # kein "schreib weiter", sie hat selbst weitergemacht
    assert sum("arbeite weiter" in s for s in shown) == 2
    assert [m["content"] for m in prov.messages if m["content"] == CONTINUE_PROMPT]
    mem.close()


def test_asks_after_the_automatic_continues(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path, max_werkzeug_runden=1, automatisch_weiter=1)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_tool(1)]))
    out = Brain(cfg, mem, reg, ctx, provider=prov).respond("los")
    assert "Limit" in out and prov.client.messages.calls == 2
    mem.close()


def test_agent_gets_fresh_history_limited_tools_and_counts_cost(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    main_script = [
        (anthro_msg([tool_use_block("agent_beauftragen", "a1",
                                     {"rolle": "recherche", "auftrag": "Finde die Hauptstadt von Peru"})],
                    stop_reason="tool_use"), []),
        _text("Die Hauptstadt ist Lima."),
    ]
    client = AnthroClient(main_script)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=client)
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    agent_calls = []
    real_stream = client.messages.stream

    def stream(**kw):
        if kw["system"] != "SYSTEM":  # Aufruf des Agenten
            agent_calls.append(kw)
            from tests._fakes import AnthroStream
            return AnthroStream(anthro_msg([text_block("Lima (Quelle: Lexikon)")]), [])
        return real_stream(**kw)

    client.messages.stream = stream
    shown = []
    out = brain.respond("Hauptstadt von Peru?", on_text=shown.append)
    assert "Lima" in out
    sent = agent_calls[0]
    assert "RECHERCHE" in sent["system"] and "WERTE" in sent["system"]
    first = sent["messages"][0]  # frischer Verlauf: beginnt mit dem Auftrag, nicht mit dem Gespraech
    assert first["role"] == "user" and first["content"].startswith("Auftrag:") and "Peru" in first["content"]
    tool_names = {t["name"] for t in sent["tools"]}
    assert "shell_befehl" not in tool_names and "agent_beauftragen" not in tool_names
    assert "web_suche" in tool_names
    results = [b for m in prov.messages if isinstance(m["content"], list) for b in m["content"]
               if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert "Lima (Quelle: Lexikon)" in results[0]["content"]
    assert prov.usage.output_tokens == 150  # 2 eigene Antworten + 1 des Agenten
    assert any("Agent 'recherche' startet" in s for s in shown)
    mem.close()


def test_agents_cannot_start_agents(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_text("x")]))
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    brain._agent_running = True
    assert "keine weiteren Agenten" in brain.run_agent("helfer", "irgendwas")
    mem.close()


def test_pruefer_may_run_tests_but_not_write(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    client = AnthroClient([_text("Keine Probleme gefunden")])
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=client)
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    brain.run_agent("pruefer", "Pruefe x.py")
    tools = {t["name"] for t in client.messages.last_kwargs["tools"]}
    assert "shell_befehl" in tools and "datei_schreiben" not in tools and "datei_loeschen" not in tools
    mem.close()


def test_ctrl_c_leaves_a_valid_history(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_tool(1), _text("ok")]))
    prov.respond("Erste Frage")
    snapshot = prov.history_snapshot()

    def interrupted(*a, **kw):
        raise KeyboardInterrupt

    prov.registry.execute = interrupted  # Strg+C waehrend ein Werkzeug laeuft
    prov.client.messages.calls = 0
    with pytest.raises(KeyboardInterrupt):
        prov.respond("Zweite Frage")
    prov.abort_turn(snapshot, "Zweite Frage")
    assert prov.messages[-2] == {"role": "user", "content": "Zweite Frage"}
    assert prov.messages[-1] == {"role": "assistant", "content": ABORT_NOTE}
    # kein Werkzeugaufruf ohne Ergebnis bleibt zurueck
    for m in prov.messages[snapshot:]:
        assert isinstance(m["content"], str)
    mem.close()


def test_model_clients_have_timeouts(monkeypatch):
    import anthropic
    import openai

    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.setdefault("anthropic", kw))
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: seen.setdefault("openai", kw))
    cfg = load_config()
    cfg.anthropic_api_key = "sk-ant-test"
    cfg.deepseek_api_key = "sk-test"
    reg = build_registry()
    ctx = ToolContext(permissions=PermissionManager(cfg.permissions, cfg.workspace_path), memory=None)
    AnthropicProvider(cfg, "S", reg, ctx)
    from assistant.providers.deepseek_provider import DeepSeekProvider

    DeepSeekProvider(cfg, "S", reg, ctx)
    for kw in seen.values():
        assert kw["timeout"].read == 180.0 and kw["timeout"].connect == 15.0 and kw["max_retries"] == 3


def test_waiting_indicator_is_called_before_each_model_request(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_tool(1), _text("ok")]))
    calls = []
    prov.wait_fn = lambda: calls.append(1)
    prov.respond("x")
    assert len(calls) == 2
    mem.close()
