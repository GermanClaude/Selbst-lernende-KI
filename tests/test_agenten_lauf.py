"""0.58: Agent-Fenster von Ende zu Ende - der echte Agent-Loop im Controller (ohne GUI, ohne Modell)
und die Dirigent-API (ohne echte Fenster zu oeffnen)."""
import time

import pytest

from assistant import agenten as A
from assistant import sandbox as S
from assistant.config import load_config


def _ctl(tmp_path):
    from assistant.app.controller import AppController

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test"
    return AppController(cfg, lambda e: None)


def test_agent_loop_erledigt_auftrag_und_protokolliert(tmp_path, monkeypatch):
    """Diese Nova laeuft als Agent: ein Auftrag im Briefkasten -> sie arbeitet ihn ab (hier gestubbt)
    und schreibt das Ergebnis ins Protokoll, das der Dirigent lesen kann."""
    monkeypatch.setenv("NOVA_AGENT", "1")
    monkeypatch.setenv("NOVA_AGENT_NAME", "Tester")
    monkeypatch.setattr(A, "_POLL", 0.05)
    ctl = _ctl(tmp_path)
    try:
        # Statt das echte Modell laufen zu lassen: der "Turn" liefert einfach ein Ergebnis zurueck.
        def fake_answer(text, model_text=None, **kw):
            ctl._last_answer = "ERLEDIGT:" + (model_text or text)
        monkeypatch.setattr(ctl, "_answer", fake_answer)

        A._haenge_an(A._auftrag_pfad(tmp_path), {"nr": 1, "text": "Zeichne das Menue", "zeit": time.time()})
        ctl._agent_schleife_starten()

        ende = time.monotonic() + 5
        while time.monotonic() < ende and not A.log_lesen(tmp_path):
            time.sleep(0.05)
        log = A.log_lesen(tmp_path)
        assert log and log[0]["nr"] == 1
        assert "ERLEDIGT:" in log[0]["text"] and "Zeichne das Menue" in log[0]["text"]
        assert A.status_lesen(tmp_path).get("zustand") == "frei"
    finally:
        ctl._stop_watch.set()
        ctl.shutdown()


def test_dirigent_api_startet_listet_schliesst(tmp_path, monkeypatch):
    """Die Haupt-Nova (Premium Max) startet einen Agenten, sieht ihn in der Liste und schliesst ihn wieder -
    ohne dass ein echtes Fenster aufgeht."""
    from assistant import premium as PM

    monkeypatch.delenv("NOVA_AGENT", raising=False)
    monkeypatch.setattr(PM, "stufe", lambda root, *a, **k: "max")
    lebendig: set = set()
    monkeypatch.setattr(S, "_lebt", lambda pid: pid in lebendig)

    n = [4000]

    def fake_spawn(ordner, env):
        n[0] += 1
        lebendig.add(n[0])
        fake_spawn.env = env
        return n[0]
    monkeypatch.setattr(S, "_spawn_app", fake_spawn)

    def fake_stoppen(root, sid=""):
        anzahl = 0
        for d in S.offene(root):
            if sid and d.get("id") != sid:
                continue
            lebendig.discard(int(d.get("pid") or 0))
            anzahl += 1
        S.aufraeumen(root)
        return anzahl
    monkeypatch.setattr(S, "stoppen", fake_stoppen)

    ctl = _ctl(tmp_path)
    try:
        api = ctl._agenten_api()
        assert api["erlaubt"]() is True
        r = api["starten"]("Grafik", "Zeichne das Menue")
        assert r["ok"] and r["agent"]["name"] == "Grafik"
        assert fake_spawn.env["NOVA_AGENT"] == "1"
        laufen = api["liste"]()
        assert len(laufen) == 1 and laufen[0]["name"] == "Grafik"
        # weiterer Auftrag landet im Briefkasten
        assert api["auftrag"]("Grafik", "Mach es bunt") is True
        erg = api["schliessen"]("")
        assert erg["geschlossen"] == 1
        assert api["liste"]() == []
    finally:
        ctl._stop_watch.set()
        ctl.shutdown()


def test_agent_darf_keine_agenten_starten(tmp_path, monkeypatch):
    """Aus einem Agenten heraus ist die Dirigent-API gesperrt (kein Agent startet weitere Agenten)."""
    from assistant import premium as PM

    monkeypatch.setenv("NOVA_AGENT", "1")
    monkeypatch.setattr(PM, "stufe", lambda root, *a, **k: "max")
    ctl = _ctl(tmp_path)
    try:
        api = ctl._agenten_api()
        assert api["erlaubt"]() is False
        assert api["starten"]("X", "tu was")["ok"] is False
    finally:
        ctl._stop_watch.set()
        ctl.shutdown()
