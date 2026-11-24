"""Eigene/zusaetzliche Modelle: jedes per API-Schluessel erreichbare Modell laesst sich einstellen."""
from assistant import modelle
from assistant.config import load_config


def test_gueltige_modell_id():
    assert modelle._gueltige_modell_id("deepseek-chat")
    assert modelle._gueltige_modell_id("z-ai/glm-5.3-uncensored")
    assert modelle._gueltige_modell_id("meine-feinabstimmung:v2")
    assert not modelle._gueltige_modell_id("")
    assert not modelle._gueltige_modell_id("hat leerzeichen")
    assert not modelle._gueltige_modell_id("@#$%")


def test_eigenes_deepseek_modell_wird_akzeptiert(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="deepseek", model="deepseek-chat-neu-2027")
    assert r["ok"] and cfg.deepseek.model == "deepseek-chat-neu-2027"


def test_eigenes_openai_modell(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="openai", model="gpt-irgendwas-brandneu")
    assert r["ok"] and cfg.openai.model == "gpt-irgendwas-brandneu"


def test_unsinniger_name_wird_abgelehnt(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="deepseek", model="kein gueltiges modell!!")
    assert r["ok"] is False and "gueltiger Modellname" in r["message"]


def test_bekanntes_kuerzel_bleibt_vorrangig(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="openai", model="luna")  # Kuerzel -> echtes Modell
    assert r["ok"] and cfg.openai.model == "gpt-6-luna"
