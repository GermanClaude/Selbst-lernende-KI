"""Opt-in Telemetrie + stabile Geraete-ID + signierte Sperre (auch fuer Gratis-Nutzer)."""
import base64
import json
import types

from assistant import feedback, geraet, premium
from assistant import telemetrie as T


def _cfg(root):
    return types.SimpleNamespace(project_root=root)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def test_geraet_id_stabil_und_gespiegelt(tmp_path, monkeypatch):
    monkeypatch.setattr(geraet, "_spiegel_pfade", lambda: [tmp_path / "m1.id", tmp_path / "m2.id"])
    geraet._cache.clear()
    a = geraet.geraet_id(tmp_path)
    assert len(a) == 16 and all(c in "0123456789abcdef" for c in a)
    # App-Datenordner geloescht -> aus dem Spiegel wiederhergestellt (ueberlebt "Neuinstallation")
    (tmp_path / "data" / "geraet.id").unlink()
    geraet._cache.clear()
    assert geraet.geraet_id(tmp_path) == a
    assert (tmp_path / "m1.id").exists()


def test_standard_aus_und_opt_in(tmp_path):
    (tmp_path / "data").mkdir()
    assert T.aktiv(tmp_path) is False            # Standard: AUS
    T.setzen(tmp_path, an=True, name="Max")
    assert T.aktiv(tmp_path) is True
    assert T.status(tmp_path)["name"] == "Max"
    T.setzen(tmp_path, an=False)
    assert T.aktiv(tmp_path) is False            # widerrufbar


def test_ping_nur_mit_zustimmung(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(feedback, "ziel_url", lambda cfg, **k: "https://script.example/exec")
    monkeypatch.setattr(premium, "stufe", lambda root, *a, **k: None)   # gratis
    calls = []
    # Ohne Zustimmung: nichts gesendet
    assert T.ping(tmp_path, _cfg(tmp_path), post=lambda u, b: calls.append((u, b))) is False
    assert not calls
    T.setzen(tmp_path, an=True, name="Max")
    assert T.ping(tmp_path, _cfg(tmp_path), post=lambda u, b: calls.append((u, b))) is True
    payload = json.loads(calls[-1][1])
    assert payload["aktion"] == "telemetrie" and payload["name"] == "Max" and payload["stufe"] == "gratis"
    assert len(payload["geraet"]) == 16 and payload["kennung"]


def test_nachrichten_nur_mit_zustimmung(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(feedback, "ziel_url", lambda cfg, **k: "https://script.example/exec")
    assert T.nachrichten_holen(tmp_path, _cfg(tmp_path), holen=lambda u: b'{"nachrichten":[]}') == []
    T.setzen(tmp_path, an=True)
    roh = b'{"ok":true,"nachrichten":[{"text":"Hallo!","zeit":"2026-11-28","id":"1"}]}'
    msgs = T.nachrichten_holen(tmp_path, _cfg(tmp_path), holen=lambda u: roh)
    assert msgs and msgs[0]["text"] == "Hallo!"


def test_ist_gesperrt_prueft_kennung_und_geraet(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(feedback, "ziel_url", lambda cfg, **k: "https://script.example/exec")
    monkeypatch.setattr(premium, "signatur_ok", lambda daten, sig, n=None: True)  # Unterschrift separat getestet
    geraet._cache.clear()
    monkeypatch.setattr(geraet, "_spiegel_pfade", lambda: [tmp_path / "m.id"])
    meine_geraet = geraet.geraet_id(tmp_path)

    def huelle(ids):
        inner = json.dumps({"geraete": ids, "kennungen": []}).encode()
        return json.dumps({"daten": _b64u(inner), "sig": base64.b64encode(b"x").decode()}).encode()

    # nicht in der Liste -> nicht gesperrt
    assert T.ist_gesperrt(tmp_path, _cfg(tmp_path), holen=lambda u: huelle(["aaaa"])) is False
    # Geraete-ID in der Liste -> gesperrt (auch ohne Premium)
    assert T.ist_gesperrt(tmp_path, _cfg(tmp_path), holen=lambda u: huelle([meine_geraet])) is True


def test_ist_gesperrt_ohne_netz_false(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(feedback, "ziel_url", lambda cfg, **k: "https://script.example/exec")

    def kaputt(_u):
        raise OSError("kein netz")

    assert T.ist_gesperrt(tmp_path, _cfg(tmp_path), holen=kaputt) is False   # fail-open
