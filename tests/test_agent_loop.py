"""Werkzeug-Schleife: Schritt-Limit, abgeschnittene Antworten, Kompaktierung.

Hintergrund: Bei Programmieraufgaben las die KI nur Dateien und hoerte dann stumm
auf (25-Schritte-Limit), danach wurde der Verlauf schon wegen der vielen
Werkzeug-Nachrichten zusammengefasst und das Gelesene vergessen - eine Schleife.
"""
from types import SimpleNamespace

from assistant.brain import Brain
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.providers.base import TRUNCATED_TOOL_ERROR
from assistant.providers.deepseek_provider import DeepSeekProvider
from assistant.tools import ToolContext, build_registry

from tests._fakes import (
    AnthroClient,
    DSClient,
    anthro_msg,
    ds_text_chunk,
    ds_toolcall_chunk,
    ds_usage_chunk,
    text_block,
    tool_use_block,
)


def _setup(tmp_path):
    cfg = load_config()
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, memory=mem)
    return cfg, mem, build_registry(), ctx


def _anthropic(tmp_path, scripted):
    cfg, mem, reg, ctx = _setup(tmp_path)
    return AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient(scripted)), mem


def _tool_turn(i, name="system_info", tinput=None, stop_reason="tool_use"):
    return (anthro_msg([tool_use_block(name, f"t{i}", tinput or {})], stop_reason=stop_reason), [])


def _tool_results(prov):
    return [
        b
        for m in prov.messages
        if isinstance(m["content"], list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]


def test_tool_round_limit_tells_the_user(tmp_path):
    prov, mem = _anthropic(tmp_path, [_tool_turn(1)])  # will immer weiter Werkzeuge nutzen
    shown = []
    out = prov.respond("Programmier was", on_text=shown.append, max_tool_rounds=3)
    assert prov.client.messages.calls == 3
    assert "weiter" in out and "Limit" in out
    assert "weiter" in "".join(shown)
    mem.close()


def test_round_limit_comes_from_config(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.conversation.max_werkzeug_runden = 4
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([_tool_turn(1)]))
    prov.respond("los")
    assert prov.client.messages.calls == 4
    mem.close()


def test_max_tokens_truncated_tool_call_is_not_executed(tmp_path):
    target = tmp_path / "gross.py"
    turn1 = (
        anthro_msg(
            [
                tool_use_block("system_info", "t1", {}),
                tool_use_block("datei_schreiben", "t2", {"pfad": str(target), "inhalt": "abgeschn"}),
            ],
            stop_reason="max_tokens",
        ),
        [],
    )
    turn2 = (anthro_msg([text_block("Ok, in Teilen.")]), [])
    prov, mem = _anthropic(tmp_path, [turn1, turn2])
    prov.respond("Schreib eine grosse Datei")
    results = {r["tool_use_id"]: r for r in _tool_results(prov)}
    assert not results["t1"]["is_error"]  # vollstaendiger Aufruf lief
    assert results["t2"]["is_error"] and results["t2"]["content"] == TRUNCATED_TOOL_ERROR
    assert not target.exists()
    mem.close()


def test_max_tokens_text_only_tells_the_user(tmp_path):
    prov, mem = _anthropic(tmp_path, [(anthro_msg([text_block("Hier ist der Anf")], stop_reason="max_tokens"), [])])
    out = prov.respond("Erklaer")
    assert "abgeschnitten" in out
    mem.close()


def test_prompt_caching_enabled(tmp_path):
    prov, mem = _anthropic(tmp_path, [(anthro_msg([text_block("hi")]), [])])
    prov.respond("hi")
    assert prov.client.messages.last_kwargs["extra_body"]["cache_control"] == {"type": "ephemeral"}
    mem.close()


def test_tool_rounds_do_not_trigger_compaction(tmp_path):
    # 15 Werkzeug-Schritte = 32 Nachrichten, aber nur EINE Nachricht vom Menschen.
    turns = [_tool_turn(i) for i in range(15)] + [(anthro_msg([text_block("Fertig gelesen.")]), [])]
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.economy.aktiv = True
    cfg.economy.verlauf_kompakt_nach = 24
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient(turns))
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    brain.respond("Lies das Projekt")
    assert prov.history_length() == 32
    assert prov.user_turns() == 1
    # Verlauf ist noch vollstaendig da (nicht durch eine Zusammenfassung ersetzt).
    assert len(_tool_results(prov)) == 15
    mem.close()


def test_huge_history_still_compacts(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.conversation.max_verlauf_zeichen = 1000
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([(anthro_msg([text_block("x" * 2000)]), [])]))
    brain = Brain(cfg, mem, reg, ctx, provider=prov)
    brain.respond("hi")
    assert prov.history_length() == 2 and "Zusammenfassung" in prov.messages[0]["content"]
    mem.close()


def test_summary_keeps_the_end_of_long_histories(tmp_path):
    from assistant.providers.anthropic_provider import _history_as_text

    msgs = [{"role": "user", "content": "alt " * 30000}, {"role": "user", "content": "NEUESTER STAND"}]
    assert "NEUESTER STAND" in _history_as_text(msgs)[-60000:]


def test_economy_cap_does_not_cut_file_reads(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.economy.aktiv = True
    cfg.economy.max_werkzeug_ausgabe = 100
    (tmp_path / "code.py").write_text("\n".join(f"zeile_{i} = {i}" for i in range(50)), encoding="utf-8")
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=AnthroClient([]))
    out, err = prov._exec_tool("datei_lesen", {"pfad": str(tmp_path / "code.py")})
    assert not err and "zeile_49" in out and "gekuerzt" not in out
    mem.close()


# ----- DeepSeek ----------------------------------------------------------------
def _ds_finish(reason):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=None), finish_reason=reason)],
        usage=None,
    )


def _deepseek(tmp_path, streams):
    cfg, mem, reg, ctx = _setup(tmp_path)
    cfg.provider.aktiv = "deepseek"
    return DeepSeekProvider(cfg, "SYSTEM", reg, ctx, client=DSClient(streams)), mem


def test_deepseek_truncated_json_is_explained_not_executed(tmp_path):
    target = tmp_path / "x.py"
    args = '{"pfad": "%s", "inhalt": "def f(' % str(target).replace("\\", "/")
    turn1 = [ds_toolcall_chunk(0, tid="c1", name="datei_schreiben", args_fragment=args),
             _ds_finish("length"), ds_usage_chunk()]
    turn2 = [ds_text_chunk("Ich schreibe in Teilen."), ds_usage_chunk()]
    prov, mem = _deepseek(tmp_path, [turn1, turn2])
    prov.respond("Schreib Code")
    tool_msgs = [m for m in prov.messages if m["role"] == "tool"]
    assert tool_msgs[0]["content"] == TRUNCATED_TOOL_ERROR
    assistant = next(m for m in prov.messages if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["function"]["arguments"] == "{}"
    assert not target.exists()
    mem.close()


def test_deepseek_round_limit_tells_the_user(tmp_path):
    turn = [ds_toolcall_chunk(0, tid="c1", name="system_info", args_fragment="{}"), ds_usage_chunk()]
    prov, mem = _deepseek(tmp_path, [turn])
    out = prov.respond("los", max_tool_rounds=2)
    assert prov.client.chat.completions.calls == 2
    assert "weiter" in out
    mem.close()


def test_deepseek_user_turns_ignore_tool_messages(tmp_path):
    turns = [[ds_toolcall_chunk(0, tid=f"c{i}", name="system_info", args_fragment="{}"), ds_usage_chunk()]
             for i in range(5)] + [[ds_text_chunk("fertig"), ds_usage_chunk()]]
    prov, mem = _deepseek(tmp_path, turns)
    prov.respond("los")
    assert prov.user_turns() == 1 and prov.history_length() > 10
    mem.close()


# ----- Befunde der Gegenpruefung ----------------------------------------------
def test_refusal_leaves_a_valid_history(tmp_path):
    from assistant.providers.base import REFUSAL_PLACEHOLDER

    # Ablehnung mitten in einem Werkzeugaufruf: der tool_use darf nicht im Verlauf bleiben.
    refused = (anthro_msg([text_block("Ich"), tool_use_block("system_info", "t9", {})],
                          stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")), [])
    prov, mem = _anthropic(tmp_path, [refused, (anthro_msg([text_block("ok")]), [])])
    prov.respond("Portscanner bauen")
    assert prov.messages[-1] == {"role": "assistant", "content": REFUSAL_PLACEHOLDER}
    prov.respond("Dann etwas anderes")
    assert not any(
        getattr(b, "type", None) == "tool_use" for m in prov.messages if isinstance(m["content"], list)
        for b in m["content"]
    )
    mem.close()


def test_summary_input_keeps_task_and_latest_state():
    from assistant.providers.base import summary_input

    text = "user: AUFGABE: Baue ein Spiel\n" + ("werkzeug-ergebnis: x\n" * 20000) + "user: NEUESTER STAND"
    out = summary_input(text)
    assert len(out) <= 60_100 and "AUFGABE" in out and "NEUESTER STAND" in out


def test_truncated_summary_keeps_history(tmp_path):
    cfg, mem, reg, ctx = _setup(tmp_path)
    client = AnthroClient([(anthro_msg([text_block("x")]), [])])
    client.messages.create = lambda **kw: SimpleNamespace(
        content=[text_block("halbe Zusamm")], stop_reason="max_tokens",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    prov = AnthropicProvider(cfg, "SYSTEM", reg, ctx, client=client)
    prov.respond("hi")
    assert prov.summarize_history() == ""
    mem.close()


def test_deepseek_context_overflow_recovers(tmp_path):
    prov, mem = _deepseek(tmp_path, [[ds_text_chunk("weiter gehts"), ds_usage_chunk()]])
    prov.messages += [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": "datei_lesen", "arguments": "{}"}}]}
        if j == 0 else {"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 30000}
        for i in range(5) for j in range(2)
    ]
    real_create = prov.client.chat.completions.create
    calls = {"n": 0}

    def create(**kw):
        calls["n"] += 1
        if kw.get("stream") and calls["n"] == 1:
            raise RuntimeError("Error code: 400 - This model's maximum context length is 131072 tokens")
        return real_create(**kw)

    prov.client.chat.completions.create = create
    out = prov.respond("weiter")
    assert "weiter gehts" in out
    tool_contents = [m["content"] for m in prov.messages if m["role"] == "tool"]
    assert all(len(c) < 1000 for c in tool_contents[:-2]) and len(tool_contents[-1]) == 30000
    mem.close()


def test_old_max_tokens_defaults_are_upgraded(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text(
        "[claude]\nmax_tokens = 16000\n[deepseek]\nmax_tokens = 2048\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.deepseek.max_tokens == 8192 and cfg.claude.max_tokens == 32000
    (tmp_path / "config" / "settings.toml").write_text("[deepseek]\nmax_tokens = 4000\n", encoding="utf-8")
    assert load_config(tmp_path).deepseek.max_tokens == 4000  # bewusst gewaehlte Werte bleiben
