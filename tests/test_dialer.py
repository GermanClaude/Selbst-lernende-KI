"""0.60: Sicherer Dialer (telefon_waehlen) - oeffnet den Dialer mit einer beliebigen Nummer,
waehlt aber NIE selbst. Nova kann so beim Anrufen Dritter helfen, ohne je von sich aus zu telefonieren."""
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry
from assistant.tools.anruf import dialer_nummer


def _ctx(tmp_path, confirm=lambda m, r: True, away=False, geoeffnet=None):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path, confirm_fn=confirm)
    pm.away = away
    extra = {"app_root": tmp_path, "ki_name": lambda: "Nova"}
    if geoeffnet is not None:
        extra["dialer_oeffnen"] = lambda nummer, wer="": (geoeffnet.append((nummer, wer)) or "📞 Dialer geoeffnet")
    return ToolContext(permissions=pm, memory=None, extra=extra)


def test_nummer_wird_aufbereitet():
    assert dialer_nummer("0171 1234567") == "+491711234567"
    assert dialer_nummer("+49 (30) 12-34") == "+49301234"
    assert dialer_nummer("*101#") == "*101#"          # Kurz-/Sondernummern bleiben erhalten
    assert dialer_nummer("hallo") is None and dialer_nummer("12") is None


def test_werkzeug_kann_jede_nummer():
    # Anders als 'anrufen' (nur eigene Nummer) hat der Dialer ein Nummernfeld fuer Dritte.
    tool = build_registry().get("telefon_waehlen")
    assert tool is not None and "nummer" in tool.input_schema["properties"]


def test_oeffnet_dialer_und_fragt_am_pc(tmp_path):
    geoeffnet, gefragt = [], []
    out, _ = build_registry().execute(
        _ctx(tmp_path, confirm=lambda m, r: gefragt.append(m) or True, geoeffnet=geoeffnet),
        "telefon_waehlen", {"nummer": "0171 1234567", "wer": "Dr. Meier"})
    assert geoeffnet == [("+491711234567", "Dr. Meier")]     # normalisiert an den Dialer gegeben
    assert gefragt and "+491711234567" in gefragt[0] and "selbst" in gefragt[0].lower()
    assert "Dialer" in out


def test_am_pc_abgelehnt_oeffnet_nicht(tmp_path):
    geoeffnet = []
    build_registry().execute(_ctx(tmp_path, confirm=lambda m, r: False, geoeffnet=geoeffnet),
                             "telefon_waehlen", {"nummer": "0171 1234567"})
    assert geoeffnet == []                                    # abgelehnt -> kein Dialer


def test_im_afk_ohne_nachfrage(tmp_path):
    geoeffnet = []
    build_registry().execute(
        _ctx(tmp_path, confirm=lambda m, r: (_ for _ in ()).throw(AssertionError("im AFK nicht fragen")),
             away=True, geoeffnet=geoeffnet),
        "telefon_waehlen", {"nummer": "+49 30 1234567"})
    assert geoeffnet == [("+49301234567", "")]


def test_unsinnige_nummer_oeffnet_nichts(tmp_path):
    geoeffnet = []
    out, _ = build_registry().execute(_ctx(tmp_path, geoeffnet=geoeffnet),
                                      "telefon_waehlen", {"nummer": "ruf mal an"})
    assert geoeffnet == [] and "Rufnummer" in out


def test_ohne_frontend_nennt_die_nummer(tmp_path):
    # Kein dialer_oeffnen im Kontext (z.B. seltener Sonderfall): Nova nennt wenigstens die Nummer.
    out, _ = build_registry().execute(_ctx(tmp_path), "telefon_waehlen", {"nummer": "0171 1234567"})
    assert "+491711234567" in out
