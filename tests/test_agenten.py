"""0.58: dirigierte Agent-Fenster (Premium Max) - der Datei-Briefkasten zwischen Dirigent und Agent,
ohne echte Fenster zu oeffnen."""
import types

import pytest

from assistant import agenten as A
from assistant import sandbox as S


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=geheim", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("x = 1", encoding="utf-8")
    lebendig: set = set()
    monkeypatch.setattr(S, "_lebt", lambda pid: pid in lebendig)

    def stoppen(root, sid=""):
        n = 0
        for d in S.offene(root):
            if sid and d.get("id") != sid:
                continue
            lebendig.discard(int(d.get("pid") or 0))
            n += 1
        S.aufraeumen(root)
        return n

    monkeypatch.setattr(S, "stoppen", stoppen)
    c = types.SimpleNamespace(project_root=tmp_path)
    c._leb = lebendig
    return c


def _spawn(cfg):
    n = [3000]

    def spawn(ordner, env):
        n[0] += 1
        cfg._leb.add(n[0])
        spawn.env = env
        return n[0]
    return spawn


def test_aktiv_liest_env(monkeypatch):
    monkeypatch.delenv("NOVA_AGENT", raising=False)
    assert A.aktiv() is None
    monkeypatch.setenv("NOVA_AGENT", "1")
    monkeypatch.setenv("NOVA_AGENT_NAME", "Logik")
    assert A.aktiv() == "Logik"


def test_start_dirigieren_protokoll_schliessen(cfg):
    sp = _spawn(cfg)
    a = A.starten(cfg, "max", "Grafik", "Zeichne das Menue", spawn=sp)
    assert a["name"] == "Grafik"
    assert sp.env["NOVA_AGENT"] == "1" and sp.env["NOVA_AGENT_NAME"] == "Grafik"
    assert sp.env["NOVA_SIM"] == "1"                 # ein Agent ist eine Sandbox-Nova (frisch, Schluessel geerbt)

    # Dirigent sieht den laufenden Agenten
    laufen = A.liste(cfg.project_root)
    assert len(laufen) == 1 and laufen[0]["name"] == "Grafik"

    # Agent-Seite: der erste Auftrag liegt im Briefkasten
    ordner = a["ordner"]
    neu = A.neue_auftraege(ordner, set())
    assert neu and neu[0]["nr"] == 1 and neu[0]["text"].startswith("Zeichne")

    # Agent meldet ein Ergebnis zurueck
    A.log_anhaengen(ordner, 1, "Menue fertig gezeichnet")
    A.status_setzen(ordner, "frei", 1)
    assert A.log_lesen(ordner)[0]["text"] == "Menue fertig gezeichnet"

    # Dirigent gibt per Name einen weiteren Auftrag
    assert A.auftrag_geben(cfg.project_root, "Grafik", "Mach es bunt")
    neu2 = A.neue_auftraege(ordner, {1})
    assert neu2 and neu2[0]["text"] == "Mach es bunt"

    # Schliessen sammelt das Protokoll ein und beendet das Fenster
    erg = A.schliessen(cfg.project_root, "Grafik")
    assert erg["geschlossen"] == 1
    assert erg["protokolle"][0]["log"][0]["text"] == "Menue fertig gezeichnet"
    assert A.liste(cfg.project_root) == []


def test_auftrag_an_unbekannten_agenten(cfg):
    assert A.auftrag_geben(cfg.project_root, "GibtsNicht", "irgendwas") is False


def test_mehrere_agenten_nebeneinander(cfg):
    sp = _spawn(cfg)
    for name in ("Grafik", "Logik", "Ton"):
        A.starten(cfg, "max", name, f"Teilaufgabe {name}", spawn=sp)
    namen = {a["name"] for a in A.liste(cfg.project_root)}
    assert namen == {"Grafik", "Logik", "Ton"}
    erg = A.schliessen(cfg.project_root)      # alle schliessen
    assert erg["geschlossen"] == 3
    assert A.liste(cfg.project_root) == []
