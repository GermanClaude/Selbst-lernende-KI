"""Charakter, Stil, 'Ueber mich', neues Gespraech."""
import json

import pytest

from assistant import profil
from assistant.config import load_config
from assistant.memory import Memory
from assistant.personality import build_system_prompt


def _cfg(tmp_path):
    (tmp_path / "config").mkdir(exist_ok=True)
    return load_config(tmp_path)


def test_choose_character_backs_up_old_persona(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "config" / "persona.md").write_text("Meine eigene Persona", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert profil.active_character(cfg) == "eigen"
    chosen = profil.apply_character(cfg, "butler")
    assert "Butler" in chosen.name and "Jarvis" in (tmp_path / "config" / "persona.md").read_text(encoding="utf-8")
    backups = list((tmp_path / "data" / "persona-sicherungen").iterdir())
    assert backups and backups[0].read_text(encoding="utf-8") == "Meine eigene Persona"
    assert profil.active_character(load_config(tmp_path)) == "butler"
    with pytest.raises(ValueError):
        profil.apply_character(cfg, "gibtsnicht")


def test_style_and_about_go_into_the_system_prompt(tmp_path):
    cfg = _cfg(tmp_path)
    profil.set_style(cfg, "anrede", "sie")
    profil.set_style(cfg, "humor", "viel")
    profil.save_about(cfg, {"name": "Nathanael", "interessen": "SCP, Programmieren", "unbekannt": "x"})
    cfg = load_config(tmp_path)
    assert cfg.style.anrede == "Sie" and cfg.about == {"name": "Nathanael", "interessen": "SCP, Programmieren"}
    mem = Memory(tmp_path / "m.sqlite3")
    prompt = build_system_prompt(cfg, mem)
    assert "mit 'Sie' an" in prompt and "humorvoll" in prompt
    assert "UEBER DEINEN MENSCHEN" in prompt and "Mein Name: Nathanael" in prompt
    mem.close()
    with pytest.raises(ValueError):
        profil.set_style(cfg, "laenge", "riesig")


def test_long_answers_switch_off_the_short_hint(tmp_path):
    cfg = _cfg(tmp_path)
    mem = Memory(tmp_path / "m.sqlite3")
    assert "so knapp wie moeglich" in build_system_prompt(cfg, mem)
    profil.set_style(cfg, "laenge", "ausfuehrlich")
    assert "so knapp wie moeglich" not in build_system_prompt(cfg, mem)
    mem.close()


def test_new_conversation_reloads_character_and_keeps_costs(tmp_path):
    from assistant.brain import Brain
    from assistant.permissions import PermissionManager
    from assistant.providers.anthropic_provider import AnthropicProvider
    from assistant.tools import ToolContext, build_registry
    from tests._fakes import AnthroClient, anthro_msg, text_block

    cfg = _cfg(tmp_path)
    mem = Memory(tmp_path / "m.sqlite3")
    reg = build_registry()
    ctx = ToolContext(permissions=PermissionManager(cfg.permissions, tmp_path), memory=mem)
    client = AnthroClient([(anthro_msg([text_block("ok")]), [])])
    brain = Brain(cfg, mem, reg, ctx, provider=AnthropicProvider(cfg, "ALT", reg, ctx, client=client))
    brain.respond("Hallo")
    used = brain.usage.total_tokens
    profil.apply_character(cfg, "kumpel")
    brain.new_conversation()
    assert "bester Kumpel" in brain.system_prompt and brain.provider.messages == []
    assert brain.usage.total_tokens >= used  # Kosten der Sitzung bleiben
    assert mem.recent_episodes()  # altes Gespraech als Zusammenfassung im Gedaechtnis
    mem.close()
