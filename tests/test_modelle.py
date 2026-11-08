"""Modell-Wahl und Denk-Tiefe: Claude und DeepSeek, App-Schnittstelle, Kosten."""
from datetime import datetime, timezone
from types import SimpleNamespace

from assistant.config import load_config
from assistant.memory import Memory
from assistant.modelle import beschreibung, finde_denktiefe, kurzbeschreibung, preise, waehle
from assistant.permissions import PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.providers.deepseek_provider import DeepSeekProvider
from assistant.tools import ToolContext, build_registry

from tests._fakes import anthro_msg, ds_text_chunk, ds_toolcall_chunk, ds_usage_chunk, text_block


def _settings(tmp_path, text):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "settings.toml").write_text(text, encoding="utf-8")
    return load_config(tmp_path)


def test_old_deepseek_names_become_the_current_models(tmp_path):
    cfg = _settings(tmp_path, '[deepseek]\nmodel = "deepseek-chat"\n')
    assert (cfg.deepseek.model, cfg.deepseek.denken) == ("deepseek-flash", "aus")
    cfg = _settings(tmp_path, '[deepseek]\nmodel = "deepseek-reasoner"\n')
    assert (cfg.deepseek.model, cfg.deepseek.denken) == ("deepseek-flash", "high")
    cfg = _settings(tmp_path, '[deepseek]\nmodel = "deepseek-reasoner"\ndenken = "low"\n')
    assert cfg.deepseek.denken == "low"  # selbst gewaehlt -> bleibt
    cfg = _settings(tmp_path, '[deepseek]\nmodel = "deepseek-v4-pro"\ndenken = "quatsch"\n')
    assert (cfg.deepseek.model, cfg.deepseek.denken) == ("deepseek-v4-pro", "aus")


def test_choose_model_and_depth_is_saved(tmp_path):
    cfg = load_config(tmp_path)
    result = waehle(cfg, "claude", model="sonnet", denken="schnell")
    assert result["ok"] and result["changed"]
    assert (cfg.claude.model, cfg.claude.effort) == ("claude-sonnet-5-5", "low")
    again = load_config(tmp_path)
    assert (again.claude.model, again.claude.effort) == ("claude-sonnet-5-5", "low")
    assert "Sonnet" in kurzbeschreibung(again, "claude") and "schnell" in kurzbeschreibung(again, "claude")

    result = waehle(cfg, "deepseek", model="pro", denken="gruendlich")
    assert result["ok"]
    again = load_config(tmp_path)
    assert (again.deepseek.model, again.deepseek.denken) == ("deepseek-v4-pro", "high")

    bad = waehle(cfg, "claude", model="gpt-9")
    assert not bad["ok"] and "opus" in bad["message"]
    assert not waehle(cfg, "claude", denken="superschnell")["ok"]
    assert cfg.claude.model == "claude-sonnet-5-5"  # nichts kaputt gemacht


def test_depth_words_fit_each_brain():
    assert finde_denktiefe("claude", "schnell") == "low"
    assert finde_denktiefe("claude", "Sehr gründlich") == "xhigh"
    assert finde_denktiefe("claude", "maximal") == "max"
    assert finde_denktiefe("deepseek", "schnell") == "aus"
    assert finde_denktiefe("deepseek", "sehr gruendlich") == "high"  # gibt es bei DeepSeek nicht
    assert finde_denktiefe("deepseek", "medium") == "high"
    assert finde_denktiefe("deepseek", "ausgewogen") == "low"


def test_description_for_the_app_lists_everything(tmp_path):
    cfg = load_config(tmp_path)
    info = beschreibung(cfg)
    ids = [m["id"] for m in info["claude"]["modelle"]]
    assert ids == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]
    assert [m["id"] for m in info["deepseek"]["modelle"]] == ["deepseek-flash", "deepseek-v4-pro"]
    assert [d["id"] for d in info["deepseek"]["denktiefen"]] == ["aus", "low", "high", "max"]
    assert info["claude"]["denken"] == cfg.claude.effort
    cfg.claude.model = "claude-opus-5"  # eigenes Modell aus settings.toml wird mit angezeigt
    assert beschreibung(cfg)["claude"]["modelle"][-1]["id"] == "claude-opus-5"


def test_costs_follow_the_model(tmp_path):
    cfg = load_config(tmp_path)
    opus, _ = cfg.cost_estimate(1_000_000, 0, 0, provider="claude", model="claude-opus-5-5")
    haiku, _ = cfg.cost_estimate(1_000_000, 0, 0, provider="claude", model="claude-haiku-5-5")
    assert opus == 4.0 and haiku == 0.1
    peak = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)      # Montag 8 Uhr UTC
    night = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
    assert preise("deepseek", "deepseek-flash", peak)[2] == 2 * preise("deepseek", "deepseek-flash", night)[2]
    assert preise("claude", "unbekannt") is None
    assert preise("claude", "claude-haiku-5-5", prompt_tokens=150_000) == (0.5, 0.05, 2.5)  # lange Anfrage


def test_odd_settings_never_crash_the_start(tmp_path):
    cfg = _settings(tmp_path, '[claude]\nmodel = 5\neffort = true\n[deepseek]\nmodel = 7\ndenken = true\n')
    assert (cfg.claude.model, cfg.claude.effort) == ("claude-opus-5-5", "medium")
    assert (cfg.deepseek.model, cfg.deepseek.denken) == ("deepseek-flash", "high")


def _ds(tmp_path, streams):
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "deepseek"
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    client = SimpleNamespace(calls=[])
    prov = DeepSeekProvider(cfg, "SYSTEM", build_registry(), ToolContext(permissions=pm, memory=mem),
                            client=_RecordingDS(streams, client.calls))
    return prov, mem, client.calls


class _RecordingDS:
    """Merkt sich jede Anfrage (Kopie der Nachrichten) und spielt Antworten ab."""

    def __init__(self, streams, calls):
        self.streams, self.calls = streams, calls
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        item = self.streams.pop(0)
        if isinstance(item, Exception):
            raise item
        return iter(item)


def _thinking_chunk(text):
    delta = SimpleNamespace(content=None, tool_calls=None, reasoning_content=text)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)


def test_deepseek_fast_mode_sends_no_thinking(tmp_path):
    prov, mem, calls = _ds(tmp_path, [[ds_text_chunk("Hallo"), ds_usage_chunk()]])
    prov.config.deepseek.denken = "aus"
    assert "Hallo" in prov.respond("Hi")
    call = calls[0]
    assert call["model"] == "deepseek-flash"
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "temperature" in call
    assert "reasoning_content" not in prov.messages[-1]
    mem.close()


def test_deepseek_thinking_keeps_and_returns_its_reasoning(tmp_path):
    turn1 = [_thinking_chunk("Ich pruefe zuerst das System."),
             ds_toolcall_chunk(0, tid="c1", name="system_info", args_fragment="{}"), ds_usage_chunk()]
    turn2 = [_thinking_chunk("Fertig."), ds_text_chunk("Alles bereit."), ds_usage_chunk()]
    prov, mem, calls = _ds(tmp_path, [[ds_text_chunk("Hi"), ds_usage_chunk()], turn1, turn2])
    prov.config.deepseek.denken = "aus"
    prov.respond("Hallo")  # erste Antwort noch ohne Nachdenken
    prov.config.deepseek.denken = "high"
    assert "bereit" in prov.respond("Systeminfo bitte")
    first, second = calls[1], calls[2]
    assert first["extra_body"] == {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    assert first["max_tokens"] >= 32768 and "temperature" not in first
    # alte Antwort ohne Denk-Text bekommt einen leeren, damit DeepSeek nicht ablehnt
    old_answer = [m for m in first["messages"] if m["role"] == "assistant"][0]
    assert old_answer["reasoning_content"] == ""
    # der Denk-Text des Werkzeug-Schritts geht beim naechsten Schritt mit
    tool_step = [m for m in second["messages"] if m["role"] == "assistant" and m.get("tool_calls")][0]
    assert tool_step["reasoning_content"] == "Ich pruefe zuerst das System."
    assert prov.messages[-1]["reasoning_content"] == "Fertig."
    mem.close()


def test_deepseek_refused_thinking_falls_back_without(tmp_path):
    error = Exception("400 Bad Request: missing reasoning_content in assistant message")
    error.status_code = 400
    prov, mem, calls = _ds(tmp_path, [error, [ds_text_chunk("Ok"), ds_usage_chunk()],
                                      [ds_text_chunk("Wieder"), ds_usage_chunk()]])
    prov.config.deepseek.denken = "high"
    assert "Ok" in prov.respond("Hi")
    assert calls[1]["extra_body"] == {"thinking": {"type": "disabled"}}
    prov.settings_changed()  # neue Wahl -> wieder mit Nachdenken probieren
    prov.respond("Nochmal")
    assert calls[2]["extra_body"]["thinking"]["type"] == "enabled"
    mem.close()


def test_live_mode_makes_deepseek_answer_without_thinking(tmp_path):
    prov, mem, calls = _ds(tmp_path, [[ds_text_chunk("Ja"), ds_usage_chunk()]])
    prov.config.deepseek.denken = "high"
    prov.effort_override = "low"  # Jarvis-Modus
    prov.respond("Hi")
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    mem.close()


class _RecordingClaude:
    def __init__(self, usage):
        self.calls, self.usage = [], usage
        self.messages = SimpleNamespace(stream=self._stream)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        from tests._fakes import AnthroStream

        return AnthroStream(anthro_msg([text_block("ok")], usage=self.usage), [])


def test_claude_uses_chosen_model_and_depth_and_cost(tmp_path):
    cfg = load_config(tmp_path)
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    usage = SimpleNamespace(input_tokens=50_000, output_tokens=0, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0)
    client = _RecordingClaude(usage)
    prov = AnthropicProvider(cfg, "SYS", build_registry(), ToolContext(permissions=pm, memory=mem), client=client)
    waehle(cfg, "claude", model="haiku", denken="schnell")
    cfg.claude.server_side_fallback = True
    prov.respond("eins")
    waehle(cfg, "claude", model="opus")
    prov.respond("zwei")
    first, second = client.calls
    assert first["model"] == "claude-haiku-5-5" and first["output_config"] == {"effort": "low"}
    assert "fallbacks" not in first  # Haiku kennt keinen Ersatz bei Ablehnungen
    assert second["model"] == "claude-opus-5-5" and second.get("fallbacks") == "default"
    usd, _ = prov.cost()
    assert round(usd, 4) == 0.205  # 50.000 Token Haiku (0,005 $) + 50.000 Token Opus (0,20 $)
    mem.close()


def test_nova_can_switch_on_request(tmp_path):
    from assistant.tools import build_registry

    cfg = load_config(tmp_path)
    asked = []
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: asked.append(m) or True)
    changed = []
    ctx = ToolContext(permissions=pm, extra={"config": cfg, "on_model": lambda: changed.append(1)})
    tool = build_registry().get("gehirn_einstellen")
    assert "Opus" in tool.run(ctx, aktion="anzeigen")
    out = tool.run(ctx, aktion="setzen", denken="schnell")
    assert out.startswith("Eingestellt") and cfg.claude.effort == "low" and changed
    assert not asked  # schneller/guenstiger: ohne Rueckfrage
    tool.run(ctx, aktion="setzen", modell="fable")
    assert cfg.claude.model == "claude-fable-5-1"
    assert asked or pm.settings.auto_confirm  # teurer: fragt (ausser alles erlaubt)
    assert tool.run(ctx, aktion="setzen", modell="gpt").startswith("Nicht geaendert")
