"""0.45: Sandbox-Nova (frisch, andere Hardware, Schluessel geerbt) mit Tarif-Limits - ohne echte Fenster."""
import json
import types
from pathlib import Path

import pytest

from assistant import sandbox as S


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=geheim\nNOVA_PREMIUM_TOKEN=github_pat_x", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("x = 1", encoding="utf-8")
    lebendig = set()
    monkeypatch.setattr(S, "_lebt", lambda pid: pid in lebendig)
    c = types.SimpleNamespace(project_root=tmp_path)
    c._lebendig = lebendig
    return c


def _spawn(cfg):
    n = [2000]

    def spawn(ordner, env):
        n[0] += 1
        cfg._lebendig.add(n[0])
        spawn.letztes_env = env
        spawn.letzter_ordner = ordner
        return n[0]
    return spawn


def test_frei_nur_eine(cfg):
    sp = _spawn(cfg)
    info = S.starten(cfg, None, spawn=sp)
    assert info["limit"] == 1 and info["offen"] == 1
    with pytest.raises(RuntimeError, match="Ohne Premium"):
        S.starten(cfg, None, spawn=sp)


def test_premium_mehr(cfg):
    sp = _spawn(cfg)
    for _ in range(10):
        S.starten(cfg, "premium", spawn=sp)
    assert len(S.offene(cfg.project_root)) == 10
    with pytest.raises(RuntimeError):
        S.starten(cfg, "premium", spawn=sp)


def test_max_und_dev_unbegrenzt(cfg):
    assert S.grenze("max") >= 1000 and S.grenze("dev") >= 1000


def test_erbt_schluessel_frisches_gedaechtnis_fake_hardware(cfg):
    sp = _spawn(cfg)
    S.starten(cfg, None, spawn=sp)
    env = sp.letztes_env
    ordner = sp.letzter_ordner
    assert env["NOVA_ROOT_OVERRIDE"] == str(ordner) and env["NOVA_SIM"] == "1"
    assert "NOVA_PREMIUM_TOKEN" not in env and "NOVA_UPDATE_TOKEN" not in env   # Tokens NICHT erben
    assert (ordner / ".env").read_text(encoding="utf-8").startswith("DEEPSEEK_API_KEY")   # Schluessel geerbt
    assert not any((ordner / "data").iterdir())                                 # frisches Gedaechtnis (leer)
    profil = json.loads(env["NOVA_SIM_HW"])
    assert profil["prozessor"] and profil["grafik"] and profil["arbeitsspeicher_gb"]


def test_aktiv_liest_profil(monkeypatch):
    monkeypatch.setenv("NOVA_SIM", "1")
    monkeypatch.setenv("NOVA_SIM_HW", json.dumps({"prozessor": "Test-CPU"}))
    assert S.aktiv()["prozessor"] == "Test-CPU"
    monkeypatch.delenv("NOVA_SIM")
    assert S.aktiv() is None


def test_system_info_tool_in_sandbox(tmp_path, monkeypatch):
    from assistant.tools import build_registry
    from assistant.config import PermissionSettings
    from assistant.permissions import PermissionManager
    from assistant.tools import ToolContext
    monkeypatch.setenv("NOVA_SIM", "1")
    monkeypatch.setenv("NOVA_SIM_HW", json.dumps(S.hardware_profil("abc")))
    pm = PermissionManager(PermissionSettings(), tmp_path)
    out, _ = build_registry().execute(ToolContext(permissions=pm, memory=None, extra={}), "system_info", {})
    assert "Sandbox" in out and "simuliert" in out


def test_sandbox_startet_keine_sandbox(monkeypatch):
    monkeypatch.setenv("NOVA_SIM", "1")
    monkeypatch.setenv("NOVA_SIM_HW", "{}")
    assert S.aktiv() is not None       # in der Sandbox: _sandbox_befehl verweigert eine weitere (siehe cli)


def test_config_root_override(tmp_path, monkeypatch):
    from assistant.config import find_app_root
    monkeypatch.setenv("NOVA_ROOT_OVERRIDE", str(tmp_path / "sim42"))
    assert find_app_root() == (tmp_path / "sim42").resolve()


def test_simulate_auftrag_wird_abgelegt_und_einmal_gelesen(cfg, monkeypatch):
    sp = _spawn(cfg)
    info = S.starten(cfg, None, spawn=sp, auftrag="Schick eine Diagnose an den Entwickler.")
    assert info["auftrag"] is True
    ordner = sp.letzter_ordner
    assert (ordner / "data" / "sim_auftrag.txt").exists()
    # auftrag_lesen nur, wenn DIESE Nova eine Sandbox ist (NOVA_SIM) - einmalig, dann weg
    monkeypatch.setenv("NOVA_SIM", "1")
    monkeypatch.setenv("NOVA_SIM_HW", json.dumps({"prozessor": "x", "grafik": "y", "arbeitsspeicher_gb": 8}))
    assert S.auftrag_lesen(ordner) == "Schick eine Diagnose an den Entwickler."
    assert S.auftrag_lesen(ordner) == ""     # nur einmal


def test_auftrag_lesen_nur_in_sandbox(cfg, monkeypatch):
    monkeypatch.delenv("NOVA_SIM", raising=False)
    sp = _spawn(cfg)
    S.starten(cfg, None, spawn=sp, auftrag="test")
    assert S.auftrag_lesen(sp.letzter_ordner) == ""     # keine Sandbox -> kein Auftrag
