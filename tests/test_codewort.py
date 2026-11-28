"""0.66: Codewort-Schutz - ein vom Nutzer gesetztes Wort sichert sensible Aktionen ab.
Nur ein Hash wird gespeichert; gesperrte Aktionen (senden/anrufen/anmelden/Passwort) geben einen Hinweis."""
import time

from assistant import codewort as C
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


def test_setzen_pruefen(tmp_path):
    assert C.frei(tmp_path) is True          # ohne Codewort ist alles frei
    C.setzen(tmp_path, "mein geheim")
    assert C.gesetzt(tmp_path)
    assert C.pruefen(tmp_path, "mein geheim") and not C.pruefen(tmp_path, "falsch")
    # Nur der Hash liegt in der Datei, nie das Wort:
    roh = (tmp_path / "data" / "codewort.json").read_text(encoding="utf-8")
    assert "mein geheim" not in roh and "hash" in roh


def test_zu_kurz(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        C.setzen(tmp_path, "ab")


def test_entsperren_sperren_ablauf(tmp_path, monkeypatch):
    C.setzen(tmp_path, "oeffne dich")
    C.sperren(tmp_path)
    assert C.frei(tmp_path) is False
    assert C.entsperren(tmp_path, "oeffne dich") is True and C.frei(tmp_path) is True
    assert C.entsperren(tmp_path, "falsch") is False
    # Ablauf: Fenster vorbei -> wieder gesperrt
    C._frei[str(tmp_path)] = time.time() - 1
    assert C.frei(tmp_path) is False


def test_entfernen_braucht_codewort(tmp_path):
    C.setzen(tmp_path, "weg damit")
    assert C.entfernen(tmp_path, "falsch") is False and C.gesetzt(tmp_path)
    assert C.entfernen(tmp_path, "weg damit") is True and not C.gesetzt(tmp_path)
    assert C.frei(tmp_path) is True          # ohne Codewort wieder alles frei


def test_befehl_flow(tmp_path):
    assert "KEIN Codewort" in C.befehl(tmp_path, [])
    assert "gesetzt" in C.befehl(tmp_path, ["setzen", "sei", "offen"]).lower()
    C.sperren(tmp_path)
    assert "stimmt nicht" in C.befehl(tmp_path, ["daneben"])
    assert "frei" in C.befehl(tmp_path, ["sei", "offen"]).lower()
    assert C.frei(tmp_path) is True


# -- Gate: eine sensible Aktion (Dialer) ist bei gesetztem+gesperrtem Codewort blockiert ----------
def _ctx(tmp_path):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), tmp_path)
    return ToolContext(permissions=pm, memory=None,
                       extra={"app_root": tmp_path, "dialer_oeffnen": lambda nummer, wer="": "AUF"})


def test_dialer_ist_mit_codewort_gesperrt(tmp_path):
    C.setzen(tmp_path, "tor auf")
    C.sperren(tmp_path)
    out, _ = build_registry().execute(_ctx(tmp_path), "telefon_waehlen", {"nummer": "0171 1234567"})
    assert out == C.SPERR_HINWEIS                       # gesperrt -> Hinweis, kein Waehlen
    assert C.entsperren(tmp_path, "tor auf")
    out2, _ = build_registry().execute(_ctx(tmp_path), "telefon_waehlen", {"nummer": "0171 1234567"})
    assert "AUF" in out2 or "Dialer" in out2            # entsperrt -> laeuft
