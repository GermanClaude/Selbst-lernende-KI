"""0.54: Zugangs-Tresor - Logins lokal verschluesselt, Passwoerter nie im Klartext an die KI."""
import pytest

from assistant import tresor as T
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools.base import ToolContext
from assistant.tools.tresor_tool import ZugangTool

HAUPT = "superGeheim123"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data").mkdir()
    yield tmp_path
    T.zusperren(tmp_path)


def test_einrichten_oeffnen_und_speichern(root):
    T.einrichten(root, HAUPT)
    T.eintrag(root, "Instagram", benutzer="nova", passwort="ig-pw", url="https://instagram.com")
    T.zusperren(root)
    assert not T.ist_offen(root)
    T.oeffnen(root, HAUPT)
    assert [e["dienst"] for e in T.liste(root)] == ["Instagram"]


def test_falsches_hauptpasswort(root):
    T.einrichten(root, HAUPT)
    T.zusperren(root)
    with pytest.raises(T.TresorFehler, match="Falsches Haupt-Passwort"):
        T.oeffnen(root, "falschfalsch")


def test_datei_ist_verschluesselt(root):
    T.einrichten(root, HAUPT)
    T.eintrag(root, "Mail", benutzer="ich@example.com", passwort="GANZ_GEHEIM_42")
    roh = (root / "data" / "tresor.bin").read_bytes()
    assert b"GANZ_GEHEIM_42" not in roh and b"ich@example.com" not in roh and b"Mail" not in roh


def test_liste_zeigt_nie_das_passwort(root):
    T.einrichten(root, HAUPT)
    T.eintrag(root, "Bank", benutzer="kunde", passwort="PIN9999")
    for e in T.liste(root):
        assert "passwort" not in e and "PIN9999" not in str(e)


def test_werkzeug_gibt_passwort_nie_heraus(root):
    T.einrichten(root, HAUPT)
    T.eintrag(root, "Insta", benutzer="nova", passwort="streng_geheim")
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), root / "ws", app_root=root,
                           confirm_fn=lambda m, r: True)
    getippt = {}
    ctx = ToolContext(permissions=pm, extra={"app_root": str(root),
                                             "tresor_filler": lambda d: getippt.update(d) or True})
    tool = ZugangTool()
    assert "streng_geheim" not in tool.run(ctx, "liste")
    erg = tool.run(ctx, "einloggen", dienst="Insta")
    assert "streng_geheim" not in erg and "eingetippt" not in erg.lower() or "getippt" in erg.lower()
    assert getippt.get("passwort") == "streng_geheim"     # nur die Ausfuell-Schicht sieht es


def test_werkzeug_merken_setzt_kein_passwort(root):
    T.einrichten(root, HAUPT)
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), root / "ws", app_root=root,
                           confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, extra={"app_root": str(root)})
    ZugangTool().run(ctx, "merken", dienst="X", benutzer="user")
    assert T.liste(root)[0]["hat_passwort"] is False


def test_tresor_datei_ist_fuer_werkzeuge_gesperrt(root):
    pm = PermissionManager(PermissionSettings(safe_mode=False, allow_full_filesystem=True, vollzugriff=True),
                           root / "ws", app_root=root, confirm_fn=lambda m, r: True)
    from assistant.permissions import PermissionError_
    with pytest.raises(PermissionError_):
        pm.resolve_path(str(root / "data" / "tresor.bin"))


def test_auto_zu_nach_ablauf(root, monkeypatch):
    import time as _t
    echt = _t.time()
    T.einrichten(root, HAUPT)
    monkeypatch.setattr(_t, "time", lambda: echt + T.AUTO_ZU + 60)   # 31 Min. spaeter
    assert not T.ist_offen(root)
