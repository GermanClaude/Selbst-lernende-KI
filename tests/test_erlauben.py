"""Einmal 'immer erlauben' = dauerhaft keine Rueckfragen mehr."""
from pathlib import Path

from assistant.config import PermissionSettings, load_config, save_setting
from assistant.permissions import PermissionManager, Risk
from assistant.selbststart import starts_the_ki
from assistant.ui import cli as cli_mod


def test_save_setting_keeps_comments_and_is_loaded(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.toml").write_text(
        "# meine Einstellungen\n[ki]\nname = \"Aria\"\n\n[permissions]\n# frag mich\nsafe_mode = false\n"
        "auto_confirm = false\n", encoding="utf-8")
    save_setting(tmp_path, "permissions", "auto_confirm", "true")
    text = (cfg_dir / "settings.toml").read_text(encoding="utf-8")
    assert "# meine Einstellungen" in text and "# frag mich" in text and "auto_confirm = true" in text
    assert load_config(tmp_path).permissions.auto_confirm is True


def test_save_setting_adds_missing_section_and_file(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.example.toml").write_text("[ki]\nname = \"Aria\"\n", encoding="utf-8")
    save_setting(tmp_path, "permissions", "auto_confirm", "true")  # Datei fehlt -> aus Vorlage
    cfg = load_config(tmp_path)
    assert cfg.permissions.auto_confirm is True and cfg.ki.name == "Nova"  # alter Standardname "Aria"


def _cli(tmp_path, answers, monkeypatch):
    (tmp_path / "config").mkdir(exist_ok=True)
    c = cli_mod.CLI.__new__(cli_mod.CLI)
    c.config = load_config(tmp_path)
    c.permissions = PermissionManager(PermissionSettings(safe_mode=False), tmp_path, confirm_fn=c._confirm)
    c.thinking = cli_mod._Thinking(False)
    monkeypatch.setattr("builtins.input", lambda prompt="": answers.pop(0))
    return c


def test_answer_a_allows_everything_permanently(tmp_path, monkeypatch):
    c = _cli(tmp_path, ["a"], monkeypatch)
    assert c.permissions.check(Risk.MODERATE, "Datei schreiben").allowed
    assert c.permissions.settings.auto_confirm is True
    assert c.permissions.check(Risk.DANGEROUS, "Shell").allowed  # keine weitere Frage (input waere leer)
    assert load_config(tmp_path).permissions.auto_confirm is True  # auch nach Neustart


def test_autostart_question_has_no_always(tmp_path, monkeypatch):
    c = _cli(tmp_path, ["a"], monkeypatch)
    assert not c._confirm("Aufgabe einrichten", Risk.AUTOSTART)
    assert c.permissions.settings.auto_confirm is False


def test_erlauben_command(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    c._allow_command(["alles"])
    assert load_config(tmp_path).permissions.auto_confirm is True
    c._allow_command(["fragen"])
    assert load_config(tmp_path).permissions.auto_confirm is False


def test_game_start_bat_is_not_the_ki(tmp_path):
    ki = tmp_path / "KI"
    game = ki / "workspace" / "scp-spiel"
    game.mkdir(parents=True)
    assert not starts_the_ki(f'start "" "{game}/start.bat"', ki)
    assert not starts_the_ki("start.bat", ki, cwd=game)          # im Spielordner
    assert starts_the_ki("start.bat", ki, cwd=ki)                # im KI-Ordner
    assert starts_the_ki(f'cmd /c "{ki}/start.bat"', ki)
    assert starts_the_ki("python -m assistant", ki)


def test_autostart_question_can_be_switched_off(tmp_path):
    asked = []
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True, autostart_immer_fragen=False),
                           tmp_path, confirm_fn=lambda m, r: asked.append(m) or False)
    assert pm.check_shell("schtasks /create /tn x /tr y").allowed and asked == []


def test_new_name_nova_and_old_default_migrates(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.ki.name == "Nova" and cfg.ki.bedeutung == "Neugierige, Offene, Vernetzte Assistenz"
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "settings.toml").write_text('[ki]\nname = "Aria"\n', encoding="utf-8")
    assert load_config(tmp_path).ki.name == "Nova"          # alter Standard -> neuer Name
    (tmp_path / "config" / "settings.toml").write_text('[ki]\nname = "Max"\n', encoding="utf-8")
    assert load_config(tmp_path).ki.name == "Max"           # selbst gewaehlter Name bleibt


def test_name_command_saves_name_and_meaning(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    c._name_command("JONA = Jederzeit Online, Nachdenkend, Aufmerksam")
    cfg = load_config(tmp_path)
    assert cfg.ki.name == "JONA" and cfg.ki.bedeutung.startswith("Jederzeit")


def test_system_prompt_knows_name_and_meaning(tmp_path):
    from assistant.memory import Memory
    from assistant.personality import build_system_prompt

    mem = Memory(tmp_path / "m.sqlite3")
    prompt = build_system_prompt(load_config(tmp_path), mem)
    assert "Du bist Nova (Neugierige, Offene, Vernetzte Assistenz)" in prompt
    mem.close()
