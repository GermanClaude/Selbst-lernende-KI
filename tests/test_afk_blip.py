"""Ein Mikrofon-Geraeusch oder eine versehentliche Taste beendet den AFK-Modus NICHT."""
from assistant.abwesend import AfkSession
from assistant.app.controller import _afk_noise
from assistant.config import load_config


def test_afk_noise_erkennt_blips():
    for blip in ("", "   ", ".", "!!", "x", "ä", "äh", "ähm", "hmm", "mhm", "oh", "na", "...?"):
        assert _afk_noise(blip) is True, blip


def test_afk_noise_laesst_echte_rueckmeldung_durch():
    for echt in ("ok", "hi", "da", "stop", "nein", "bin da", "mach weiter", "ich bin zurueck", "hey nova"):
        assert _afk_noise(echt) is False, echt


def test_submit_blip_beendet_afk_nicht(tmp_path):
    from assistant.app.controller import AppController

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test"
    ctl = AppController(cfg, lambda e: None)
    try:
        session = AfkSession(auftrag="recherchiere")
        ctl._afk = session
        # Kurzer Blip: wird ignoriert, AFK laeuft weiter.
        r = ctl.submit("ähm")
        assert r.get("afk_ignored") is True
        assert not session.stop_event.is_set() and not session.ended
        # Echte Nachricht wuerde den AFK beenden (hier nur die Erkennung geprueft).
        assert _afk_noise("ich bin wieder da") is False
    finally:
        ctl.shutdown()
