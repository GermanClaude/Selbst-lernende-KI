"""0.53: Alltags-Helfer (Rechner, Einheiten, Datum, Wetter, Auslastung)."""
import pytest

from assistant.tools import build_registry
from assistant.tools import helfer as H


@pytest.mark.parametrize("ausdruck, erwartet", [
    ("2+3*4", 14), ("(2+3)*4", 20), ("3,5*2", 7.0), ("2^10", 1024), ("sqrt(16)", 4.0),
    ("runden(pi, 2)", 3.14), ("10 // 3", 3), ("max(1, 2, 3)", 3), ("-(4)", -4), ("fak(5)", 120),
])
def test_rechner_rechnet_exakt(ausdruck, erwartet):
    assert H.rechnen(ausdruck) == erwartet


@pytest.mark.parametrize("boese", ["__import__('os').system('echo x')", "9**9**9", "().__class__", "open('x')",
                                   "x" * 600, "1/0", "fak(10000)", "lambda: 1", "[1,2]", "'a'*5"])
def test_rechner_wehrt_code_und_riesenzahlen_ab(boese):
    with pytest.raises(H.RechenFehler):
        H.rechnen(boese)


def test_rechner_werkzeug_mehrere():
    out = H.Rechner().run(None, "1+1; 2*21")
    assert "= 2" in out and "= 42" in out


@pytest.mark.parametrize("wert, von, nach, erwartet", [
    (1, "km", "m", 1000), (100, "c", "f", 212), (0, "c", "k", 273.15), (1, "gib", "mib", 1024),
    (10, "km/h", "m/s", 10 / 3.6), (1, "kwh", "kcal", 3.6e6 / 4184),
])
def test_einheiten(wert, von, nach, erwartet):
    assert H.umrechnen(wert, von, nach) == pytest.approx(erwartet)


def test_einheiten_passen_nicht():
    with pytest.raises(H.RechenFehler):
        H.umrechnen(1, "kg", "m")


def test_datum():
    d = H.DatumRechnen()
    assert d.run(None, "info", "24.12.2026").startswith("Donnerstag, 24.12.2026")
    assert "7 Tage" in d.run(None, "abstand", "01.12.2026", "08.12.2026")
    assert "5 Werktage" in d.run(None, "abstand", "07.12.2026", "14.12.2026")
    assert "31.12.2026" in d.run(None, "plus", "24.12.2026", tage=7)


def test_wetter_mit_attrappe():
    def holen(url):
        if "geocoding" in url:
            return {"results": [{"name": "Berlin", "country": "Deutschland", "latitude": 52.5, "longitude": 13.4}]}
        return {"current": {"temperature_2m": 4.2, "apparent_temperature": 1.0, "weather_code": 3,
                            "wind_speed_10m": 12, "relative_humidity_2m": 80},
                "daily": {"time": ["2026-11-27"], "weather_code": [61], "temperature_2m_max": [6],
                          "temperature_2m_min": [1], "precipitation_probability_max": [70]}}
    out = H.wetter("Berlin", 1, holen=holen)
    assert "Berlin" in out and "bedeckt" in out and "leichter Regen" in out


def test_helfer_sind_registriert():
    reg = build_registry(include_computer=False, include_agents=False)
    for name in ("rechner", "einheiten_umrechnen", "datum_rechnen", "wetter", "pc_auslastung"):
        assert reg.get(name) is not None
