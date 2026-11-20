"""Vollzugriff ("Stuetzraeder: alles"): wirklich ALLES ohne Rueckfrage - aber AFK bleibt sicher."""
from assistant.config import PermissionSettings, load_config
from assistant.permissions import PermissionManager, Risk

from tests.test_erlauben import _cli


def _pm(tmp_path, **perm):
    settings = PermissionSettings(safe_mode=False, auto_confirm=True, allow_full_filesystem=True, **perm)
    asked = []
    pm = PermissionManager(settings, tmp_path, confirm_fn=lambda m, r: asked.append(m) or False)
    return pm, asked


def test_vollzugriff_hebt_die_shell_sperrliste_auf(tmp_path):
    # Ohne Vollzugriff blockt ein gesperrtes Muster, mit Vollzugriff laeuft es durch.
    pm, _ = _pm(tmp_path, shell_denylist=["format "])
    assert not pm.check_shell("format C: /q").allowed
    pm_voll, asked = _pm(tmp_path, shell_denylist=["format "], vollzugriff=True)
    assert pm_voll.check_shell("format C: /q").allowed and asked == []


def test_vollzugriff_fragt_bei_autostart_nicht_mehr(tmp_path):
    # Normal fragt ein Autostart-Befehl immer nach (confirm_fn -> False => blockiert).
    pm, _ = _pm(tmp_path)
    assert not pm.check_shell("schtasks /create /tn x /tr y").allowed
    pm_voll, asked = _pm(tmp_path, vollzugriff=True)
    assert pm_voll.check_shell("schtasks /create /tn x /tr y").allowed and asked == []
    assert pm_voll.confirm_always("Autostart einrichten").allowed


def test_vollzugriff_im_afk_modus_darf_handeln_aber_kein_autostart(tmp_path):
    # Mit Vollzugriff und AFK-Vollmacht (Standard) handelt Nova im AFK wirklich - nur Autostart bleibt tabu.
    pm, _ = _pm(tmp_path, vollzugriff=True)
    pm.begin_away()
    assert pm.afk_handlungsfrei() is True
    assert pm.check_shell("format C: /q").allowed          # Vollzugriff hebt auch die Sperrliste auf
    assert pm.check(Risk.DANGEROUS, "Loeschen").allowed
    assert not pm.confirm_always("Autostart einrichten").allowed  # Autostart im AFK trotzdem gesperrt


def test_vollzugriff_afk_ohne_vollmacht_bleibt_vorsichtig(tmp_path):
    pm, _ = _pm(tmp_path, vollzugriff=True, afk_autonom=False)
    pm.begin_away()
    assert pm.afk_handlungsfrei() is False
    assert not pm.check_shell("format C: /q").allowed
    assert not pm.check(Risk.DANGEROUS, "Loeschen").allowed


def test_stufe_alles_setzt_und_speichert(tmp_path, monkeypatch):
    c = _cli(tmp_path, [], monkeypatch)
    c.set_training_wheels_stufe("alles")
    assert c.training_wheels_state() == "alles"
    p = load_config(tmp_path).permissions
    assert not p.safe_mode and p.auto_confirm and p.allow_full_filesystem and p.vollzugriff
    # Zurueck auf "aus": Vollzugriff faellt weg, der Rest bleibt offen.
    c.set_training_wheels_stufe("aus")
    assert c.training_wheels_state() == "aus"
    assert load_config(tmp_path).permissions.vollzugriff is False


def test_app_toggle_vollzugriff(tmp_path):
    from assistant.app.controller import AppController

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test"
    ctl = AppController(cfg, lambda e: None)
    try:
        assert ctl.state()["vollzugriff"] is False
        ctl.toggle("vollzugriff", True)
        assert ctl.state()["vollzugriff"] is True and ctl.training_wheels_state() == "alles"
        ctl.toggle("vollzugriff", False)
        assert ctl.state()["vollzugriff"] is False and ctl.training_wheels_state() == "aus"
    finally:
        ctl.shutdown()
