"""Skills-Reiter in der App: GET/POST /api/skills (anlegen, an/aus, loeschen, fuer alle oder ein Gehirn)."""
import json
import urllib.request

import pytest

from assistant import skills as skills_mod
from assistant.app.controller import AppController
from assistant.app.server import AppServer
from assistant.config import load_config


@pytest.fixture
def ctl(tmp_path):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    c = AppController(cfg, lambda e: None)
    yield c
    c.shutdown()


def _namen(info):
    return [s["name"] for s in info["skills"]]


def test_info_hat_skills_und_gehirne(ctl):
    info = ctl.skills_info()
    assert info["skills"] == []
    ids = {g["id"] for g in info["gehirne"]}
    assert {"claude", "deepseek", "gemini"} <= ids          # Auswahl "nur fuer ..." kennt die Gehirne
    assert info["aktiv"] == ctl.config.active_provider
    assert info["max"] == skills_mod.MAX_SKILLS


def test_anlegen_fuer_alle_und_fuer_ein_gehirn(ctl):
    r = ctl.skills_action({"action": "add", "name": "Kurz", "anweisung": "Antworte knapp."})
    assert r["ok"] and _namen(r) == ["Kurz"]
    r = ctl.skills_action({"action": "add", "name": "Nur DS", "anweisung": "Sei sparsam.", "provider": "DeepSeek"})
    assert r["ok"]
    nur = [s for s in r["skills"] if s["name"] == "Nur DS"][0]
    assert nur["provider"] == "deepseek" and nur["an"] is True
    # wirkt im System-Prompt nur fuer das passende Gehirn
    root = ctl.config.project_root
    assert "Sei sparsam." in skills_mod.prompt_block(root, "deepseek")
    assert "Sei sparsam." not in skills_mod.prompt_block(root, "claude")
    assert "Antworte knapp." in skills_mod.prompt_block(root, "claude")


def test_umschalten_und_loeschen(ctl):
    ctl.skills_action({"action": "add", "name": "Kurz", "anweisung": "Antworte knapp."})
    r = ctl.skills_action({"action": "toggle", "name": "Kurz", "an": False})
    assert r["ok"] and r["skills"][0]["an"] is False
    assert skills_mod.prompt_block(ctl.config.project_root, "claude") == ""   # aus = nicht im Prompt
    r = ctl.skills_action({"action": "remove", "name": "kurz"})               # Gross/klein egal
    assert r["ok"] and r["skills"] == []


def test_gleicher_name_ersetzt(ctl):
    ctl.skills_action({"action": "add", "name": "Kurz", "anweisung": "alt"})
    r = ctl.skills_action({"action": "add", "name": "kurz", "anweisung": "neu"})
    assert r["ok"] and len(r["skills"]) == 1 and r["skills"][0]["anweisung"] == "neu"


def test_fehlerfaelle(ctl):
    r = ctl.skills_action({"action": "add", "name": "", "anweisung": "x"})
    assert not r["ok"] and r["message"]                                       # Name fehlt
    r = ctl.skills_action({"action": "add", "name": "X", "anweisung": "y", "provider": "gibtsnicht"})
    assert not r["ok"] and "gibtsnicht" in r["error"]                         # nur echte Gehirne
    r = ctl.skills_action({"action": "toggle", "name": "fehlt", "an": True})
    assert not r["ok"]
    r = ctl.skills_action({"action": "remove", "name": "fehlt"})
    assert not r["ok"]
    r = ctl.skills_action({"action": "quatsch"})
    assert not r["ok"] and "skills" in r                                      # Liste kommt trotzdem


def test_http_route_lesen_und_schreiben(tmp_path):
    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    server = AppServer(lambda broadcast: AppController(cfg, broadcast))
    server.start()
    try:
        def req(body=None):
            data = json.dumps(body).encode() if body is not None else None
            r = urllib.request.Request(f"http://127.0.0.1:{server.port}/api/skills", data=data,
                                       headers={"Content-Type": "application/json", "X-KI-Token": server.token},
                                       method="POST" if body is not None else "GET")
            with urllib.request.urlopen(r, timeout=10) as resp:
                return json.loads(resp.read())

        assert req()["skills"] == []
        r = req({"action": "add", "name": "Caveman", "anweisung": "Rede wie Hoehlenmensch."})
        assert r["ok"] and _namen(r) == ["Caveman"]
        assert _namen(req()) == ["Caveman"]                                    # wirklich gespeichert
    finally:
        server.controller.shutdown()
        server.stop()
