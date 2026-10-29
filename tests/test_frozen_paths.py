"""KI.exe (PyInstaller) muss .env und config/settings.toml neben sich finden.

Frueher wurde der Programmordner aus __file__ abgeleitet - in der .exe zeigt das
in PyInstallers temporaeren Entpack-Ordner, also wurden .env und settings.toml
ignoriert.
"""
import sys

import pytest

from assistant import config as config_mod
from assistant.config import ConfigError, find_app_root, load_config

SETTINGS = '[ki]\nname = "Jarvis"\n\n[provider]\naktiv = "deepseek"\n'


def _frozen(monkeypatch, tmp_path, exe_dir):
    bundle = tmp_path / "_MEI123"
    (bundle / "config").mkdir(parents=True)
    (bundle / "config" / "settings.example.toml").write_text('[ki]\nname = "Vorlage"\n', encoding="utf-8")
    (bundle / "config" / "persona.md").write_text("Persona aus dem Paket", encoding="utf-8")
    (bundle / "config" / "werte.md").write_text("Werte aus dem Paket", encoding="utf-8")
    exe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "KI.exe"))
    # Schluessel aus der echten Umgebung ausblenden (leer = nicht gesetzt).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    return bundle


def test_exe_reads_env_and_settings_next_to_it(monkeypatch, tmp_path):
    exe_dir = tmp_path / "Programme" / "KI"
    _frozen(monkeypatch, tmp_path, exe_dir)
    (exe_dir / "config").mkdir()
    (exe_dir / "config" / "settings.toml").write_text(SETTINGS, encoding="utf-8")
    (exe_dir / ".env").write_text("DEEPSEEK_API_KEY=sk-echt\n", encoding="utf-8")

    root = find_app_root()
    assert root == exe_dir.resolve()
    cfg = load_config(root)
    assert cfg.ki.name == "Jarvis" and cfg.active_provider == "deepseek"
    assert cfg.deepseek_api_key == "sk-echt"
    assert cfg.settings_file == exe_dir.resolve() / "config" / "settings.toml"
    # Persona fehlt neben der .exe -> Vorlage aus dem Paket.
    assert cfg.persona_text == "Persona aus dem Paket"
    # Gedaechtnis und Arbeitsordner neben der .exe, nicht im Temp-Ordner.
    assert cfg.memory.db_path.startswith(str(exe_dir.resolve()))
    assert cfg.workspace_path == exe_dir.resolve() / "workspace"


def test_exe_in_dist_uses_project_folder(monkeypatch, tmp_path):
    project = tmp_path / "Selbst-lernende-KI"
    exe_dir = project / "dist"
    _frozen(monkeypatch, tmp_path, exe_dir)
    (project / "config").mkdir()
    (project / "config" / "settings.toml").write_text(SETTINGS, encoding="utf-8")
    (project / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-echt\n", encoding="utf-8")

    root = find_app_root()
    assert root == project.resolve()
    cfg = load_config(root)
    assert cfg.ki.name == "Jarvis" and cfg.anthropic_api_key == "sk-ant-echt"


def test_leftover_settings_in_dist_do_not_hide_project_env(monkeypatch, tmp_path):
    # Aeltere Versionen legten beim ersten Start dist/config/settings.toml an.
    project = tmp_path / "Selbst-lernende-KI"
    exe_dir = project / "dist"
    _frozen(monkeypatch, tmp_path, exe_dir)
    (exe_dir / "config").mkdir()
    (exe_dir / "config" / "settings.toml").write_text('[ki]\nname = "Alt"\n', encoding="utf-8")
    (project / "config").mkdir()
    (project / "config" / "settings.toml").write_text(SETTINGS, encoding="utf-8")
    (project / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-echt\n", encoding="utf-8")
    assert find_app_root() == project.resolve()


def test_own_env_next_to_exe_wins(monkeypatch, tmp_path):
    project = tmp_path / "Selbst-lernende-KI"
    exe_dir = project / "dist"
    _frozen(monkeypatch, tmp_path, exe_dir)
    (project / "config").mkdir()
    (project / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-projekt\n", encoding="utf-8")
    (exe_dir / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-exe\n", encoding="utf-8")
    assert find_app_root() == exe_dir.resolve()


def test_exe_without_any_config_falls_back_to_bundle(monkeypatch, tmp_path):
    exe_dir = tmp_path / "Desktop"
    _frozen(monkeypatch, tmp_path, exe_dir)
    cfg = load_config(find_app_root())
    assert cfg.ki.name == "Vorlage"


def test_run_ki_creates_files_where_config_reads(monkeypatch, tmp_path):
    exe_dir = tmp_path / "KI"
    bundle = _frozen(monkeypatch, tmp_path, exe_dir)
    (bundle / ".env.example").write_text("ANTHROPIC_API_KEY=sk-ant-...\n", encoding="utf-8")
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", find_app_root())
    monkeypatch.chdir(tmp_path)
    import run_ki

    run_ki._ensure_runtime_dir()
    assert (exe_dir / "config" / "settings.toml").is_file()
    assert (exe_dir / ".env").is_file()
    # Platzhalter aus der Vorlage zaehlt nicht als Schluessel.
    assert load_config(exe_dir).anthropic_api_key in (None, "")


def test_env_with_bom_and_empty_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # leer gesetzt -> .env soll trotzdem greifen
    (tmp_path / ".env").write_bytes("﻿ANTHROPIC_API_KEY=sk-ant-bom\n".encode("utf-8"))
    assert load_config(tmp_path).anthropic_api_key == "sk-ant-bom"


def test_real_environment_variable_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-system")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-datei\n", encoding="utf-8")
    assert load_config(tmp_path).anthropic_api_key == "sk-ant-system"


def test_settings_with_bom_are_read(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_bytes(("﻿" + SETTINGS).encode("utf-8"))
    assert load_config(tmp_path).ki.name == "Jarvis"


def test_broken_settings_give_clear_error(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("[ki\nname = Jarvis\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="settings.toml"):
        load_config(tmp_path)
