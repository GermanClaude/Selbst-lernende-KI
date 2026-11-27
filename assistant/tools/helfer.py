"""Alltags-Helfer fuer jedes Gehirn: exakt rechnen, Einheiten umrechnen, mit Daten rechnen, Wetter, PC-Auslastung.

Sprachmodelle verrechnen sich gern - diese Werkzeuge liefern exakte Ergebnisse. Alles nur lesend/rechnend
(Risk.SAFE). Der Rechner wertet NUR Zahlen und Rechenzeichen aus (eigener AST-Pruefer, kein eval auf Code)
und begrenzt Potenzen, damit "9**9**9" den PC nicht lahmlegt.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from .base import Tool, ToolContext

# ---------------------------------------------------------------- Rechner
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNKTIONEN = {"sqrt": math.sqrt, "wurzel": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
               "asin": math.asin, "acos": math.acos, "atan": math.atan, "log": math.log10, "ln": math.log,
               "log2": math.log2, "exp": math.exp, "abs": abs, "round": round, "runden": round,
               "min": min, "max": max, "floor": math.floor, "ceil": math.ceil, "fak": math.factorial,
               "factorial": math.factorial, "grad": math.radians, "rad": math.degrees}
_KONSTANTEN = {"pi": math.pi, "e": math.e, "tau": math.tau}


class RechenFehler(ValueError):
    pass


def _auswerten(knoten):
    if isinstance(knoten, ast.Expression):
        return _auswerten(knoten.body)
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, (int, float)) and not isinstance(knoten.value, bool):
        return knoten.value
    if isinstance(knoten, ast.Name) and knoten.id.lower() in _KONSTANTEN:
        return _KONSTANTEN[knoten.id.lower()]
    if isinstance(knoten, ast.UnaryOp) and type(knoten.op) in _OPS:
        return _OPS[type(knoten.op)](_auswerten(knoten.operand))
    if isinstance(knoten, ast.BinOp) and type(knoten.op) in _OPS:
        links, rechts = _auswerten(knoten.left), _auswerten(knoten.right)
        if isinstance(knoten.op, ast.Pow):
            if abs(rechts) > 1000 or (abs(links) > 1e6 and abs(rechts) > 50):
                raise RechenFehler("Die Potenz ist zu gross.")
        if isinstance(knoten.op, ast.Mult) and isinstance(links, int) and isinstance(rechts, int):
            if abs(links).bit_length() + abs(rechts).bit_length() > 4000:
                raise RechenFehler("Die Zahl wird zu gross.")
        return _OPS[type(knoten.op)](links, rechts)
    if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) and knoten.func.id.lower() in _FUNKTIONEN \
            and not knoten.keywords and len(knoten.args) <= 5:
        args = [_auswerten(a) for a in knoten.args]
        if knoten.func.id.lower() in ("fak", "factorial") and (not args or args[0] > 500):
            raise RechenFehler("Fakultaet nur bis 500.")
        return _FUNKTIONEN[knoten.func.id.lower()](*args)
    raise RechenFehler("Nur Zahlen, + - * / // % **, Klammern und Funktionen wie sqrt/sin/log/runden.")


def rechnen(ausdruck: str):
    text = (ausdruck or "").strip().replace("^", "**").replace("×", "*").replace("·", "*").replace("÷", "/")
    text = text.replace("−", "-")
    if len(text) > 500:
        raise RechenFehler("Der Ausdruck ist zu lang.")
    # deutsche Kommazahlen (3,5) -> 3.5, aber nicht Funktions-Argumente wie max(1, 2)
    import re
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    try:
        baum = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise RechenFehler("Den Ausdruck verstehe ich nicht.") from exc
    try:
        return _auswerten(baum)
    except ZeroDivisionError as exc:
        raise RechenFehler("Division durch null.") from exc
    except (OverflowError, ValueError, TypeError) as exc:
        raise RechenFehler(f"Nicht berechenbar ({exc}).") from exc


def _zahl_text(x) -> str:
    if isinstance(x, float):
        if x.is_integer() and abs(x) < 1e15:
            x = int(x)
        else:
            return f"{x:.10g}".replace(".", ",")
    s = str(x)
    return s if len(s) < 60 else s[:25] + "…" + s[-10:] + f" ({len(s)} Stellen)"


class Rechner(Tool):
    name = "rechner"
    description = ("Rechnet EXAKT (nutze es statt Kopfrechnen fuer jede nicht-triviale Rechnung): + - * / // % ** "
                   "bzw. ^, Klammern, Kommazahlen (3,5), sqrt/wurzel, sin/cos/tan (Bogenmass; grad(x) wandelt um), "
                   "log (10er), ln, exp, runden(x, n), min, max, fak, pi, e. Mehrere Rechnungen mit ';' trennen.")
    input_schema = {"type": "object", "properties": {"ausdruck": {"type": "string"}}, "required": ["ausdruck"]}

    def run(self, ctx: ToolContext, ausdruck: str) -> str:
        ergebnisse = []
        for teil in [t for t in (ausdruck or "").split(";") if t.strip()][:20]:
            try:
                ergebnisse.append(f"{teil.strip()} = {_zahl_text(rechnen(teil))}")
            except RechenFehler as exc:
                ergebnisse.append(f"{teil.strip()}: {exc}")
        return "\n".join(ergebnisse) or "Kein Ausdruck."


# ---------------------------------------------------------------- Einheiten
_EINHEITEN = {
    # Laenge (Meter)
    "mm": ("laenge", 0.001), "cm": ("laenge", 0.01), "dm": ("laenge", 0.1), "m": ("laenge", 1.0),
    "km": ("laenge", 1000.0), "zoll": ("laenge", 0.0254), "inch": ("laenge", 0.0254), "in": ("laenge", 0.0254),
    "ft": ("laenge", 0.3048), "fuss": ("laenge", 0.3048), "yd": ("laenge", 0.9144), "meile": ("laenge", 1609.344),
    "mi": ("laenge", 1609.344), "seemeile": ("laenge", 1852.0),
    # Masse (Kilogramm)
    "mg": ("masse", 1e-6), "g": ("masse", 0.001), "kg": ("masse", 1.0), "t": ("masse", 1000.0),
    "lb": ("masse", 0.45359237), "pfund": ("masse", 0.5), "oz": ("masse", 0.028349523125),
    # Volumen (Liter)
    "ml": ("volumen", 0.001), "cl": ("volumen", 0.01), "l": ("volumen", 1.0), "m3": ("volumen", 1000.0),
    "gallone": ("volumen", 3.785411784), "gal": ("volumen", 3.785411784), "tasse": ("volumen", 0.25),
    "el": ("volumen", 0.015), "tl": ("volumen", 0.005),
    # Flaeche (m2)
    "m2": ("flaeche", 1.0), "km2": ("flaeche", 1e6), "ha": ("flaeche", 1e4), "ar": ("flaeche", 100.0),
    "cm2": ("flaeche", 1e-4), "acre": ("flaeche", 4046.8564224),
    # Geschwindigkeit (m/s)
    "m/s": ("tempo", 1.0), "km/h": ("tempo", 1 / 3.6), "kmh": ("tempo", 1 / 3.6), "mph": ("tempo", 0.44704),
    "knoten": ("tempo", 0.514444),
    # Zeit (Sekunden)
    "s": ("zeit", 1.0), "sek": ("zeit", 1.0), "min": ("zeit", 60.0), "h": ("zeit", 3600.0), "std": ("zeit", 3600.0),
    "tag": ("zeit", 86400.0), "tage": ("zeit", 86400.0), "woche": ("zeit", 604800.0), "jahr": ("zeit", 31557600.0),
    # Daten (Byte)
    "b": ("daten", 1.0), "byte": ("daten", 1.0), "kb": ("daten", 1e3), "mb": ("daten", 1e6), "gb": ("daten", 1e9),
    "tb": ("daten", 1e12), "kib": ("daten", 1024.0), "mib": ("daten", 1024.0 ** 2), "gib": ("daten", 1024.0 ** 3),
    "tib": ("daten", 1024.0 ** 4), "bit": ("daten", 0.125), "mbit": ("daten", 125000.0), "gbit": ("daten", 1.25e8),
    # Energie (Joule)
    "j": ("energie", 1.0), "kj": ("energie", 1000.0), "kcal": ("energie", 4184.0), "kwh": ("energie", 3.6e6),
    "wh": ("energie", 3600.0),
}
_TEMPERATUR = {"c": "c", "°c": "c", "celsius": "c", "f": "f", "°f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}


def umrechnen(wert: float, von: str, nach: str) -> float:
    v, n = von.strip().lower().replace(" ", ""), nach.strip().lower().replace(" ", "")
    if v in _TEMPERATUR and n in _TEMPERATUR:
        c = {"c": wert, "f": (wert - 32) * 5 / 9, "k": wert - 273.15}[_TEMPERATUR[v]]
        return {"c": c, "f": c * 9 / 5 + 32, "k": c + 273.15}[_TEMPERATUR[n]]
    if v not in _EINHEITEN or n not in _EINHEITEN:
        raise RechenFehler(f"Einheit unbekannt ({von if v not in _EINHEITEN else nach}).")
    if _EINHEITEN[v][0] != _EINHEITEN[n][0]:
        raise RechenFehler(f"{von} und {nach} passen nicht zusammen ({_EINHEITEN[v][0]} vs. {_EINHEITEN[n][0]}).")
    return wert * _EINHEITEN[v][1] / _EINHEITEN[n][1]


class Einheiten(Tool):
    name = "einheiten_umrechnen"
    description = ("Rechnet Einheiten exakt um: Laenge (mm, cm, m, km, zoll, ft, meile), Masse (g, kg, lb, oz), "
                   "Volumen (ml, l, gallone, tasse, el, tl), Flaeche (m2, ha, acre), Tempo (km/h, mph, m/s, knoten), "
                   "Zeit (s, min, h, tag, woche, jahr), Daten (kb, mb, gb, kib, mib, mbit), Energie (kcal, kwh, j), "
                   "Temperatur (c, f, k).")
    input_schema = {"type": "object", "properties": {
        "wert": {"type": "number"}, "von": {"type": "string"}, "nach": {"type": "string"}},
        "required": ["wert", "von", "nach"]}

    def run(self, ctx: ToolContext, wert: float, von: str, nach: str) -> str:
        try:
            erg = umrechnen(float(wert), von, nach)
        except (RechenFehler, ValueError) as exc:
            return str(exc)
        return f"{_zahl_text(float(wert))} {von} = {_zahl_text(round(erg, 10))} {nach}"


# ---------------------------------------------------------------- Datum
_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _datum(text: str) -> date:
    text = (text or "").strip().lower()
    if text in ("", "heute"):
        return date.today()
    if text == "morgen":
        return date.today() + timedelta(days=1)
    if text == "gestern":
        return date.today() - timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d.%m."):
        try:
            d = datetime.strptime(text, fmt).date()
            return d.replace(year=date.today().year) if fmt == "%d.%m." else d
        except ValueError:
            continue
    raise RechenFehler(f"Datum '{text}' verstehe ich nicht (z.B. 24.12.2026 oder 2026-12-24).")


def _beschreiben(d: date) -> str:
    return f"{_WOCHENTAGE[d.weekday()]}, {d.strftime('%d.%m.%Y')} (KW {d.isocalendar()[1]})"


class DatumRechnen(Tool):
    name = "datum_rechnen"
    description = ("Rechnet exakt mit Daten: aktion 'info' (datum -> Wochentag, Kalenderwoche), 'abstand' (datum, "
                   "bis -> Tage/Wochen dazwischen, Werktage Mo-Fr), 'plus' (datum, tage - auch negativ). Datum als "
                   "24.12.2026, 2026-12-24, 'heute', 'morgen'.")
    input_schema = {"type": "object", "properties": {
        "aktion": {"type": "string", "enum": ["info", "abstand", "plus"]},
        "datum": {"type": "string"}, "bis": {"type": "string"}, "tage": {"type": "integer"}},
        "required": ["aktion"]}

    def run(self, ctx: ToolContext, aktion: str, datum: str = "heute", bis: str = "", tage: int = 0) -> str:
        try:
            d = _datum(datum)
            if aktion == "info":
                return _beschreiben(d)
            if aktion == "plus":
                if abs(int(tage)) > 365 * 200:
                    return "Zu weit."
                return f"{_beschreiben(d)} {'+' if tage >= 0 else '-'} {abs(int(tage))} Tage = {_beschreiben(d + timedelta(days=int(tage)))}"
            if aktion == "abstand":
                z = _datum(bis)
                diff = (z - d).days
                a, b = sorted((d, z))
                werktage = sum(1 for i in range((b - a).days) if (a + timedelta(days=i)).weekday() < 5)
                wochen = f"{diff / 7:.1f}".replace(".", ",")
                return (f"Von {_beschreiben(d)} bis {_beschreiben(z)}: {diff} Tage "
                        f"({wochen} Wochen, {werktage} Werktage Mo-Fr, ohne Feiertage)")
        except RechenFehler as exc:
            return str(exc)
        return "Unbekannte Aktion."


# ---------------------------------------------------------------- Wetter (Open-Meteo, ohne Schluessel)
_WMO = {0: "klar", 1: "ueberwiegend klar", 2: "teils bewoelkt", 3: "bedeckt", 45: "Nebel", 48: "Reifnebel",
        51: "leichter Nieselregen", 53: "Nieselregen", 55: "starker Nieselregen", 61: "leichter Regen", 63: "Regen",
        65: "starker Regen", 66: "gefrierender Regen", 67: "starker gefrierender Regen", 71: "leichter Schneefall",
        73: "Schneefall", 75: "starker Schneefall", 77: "Schneegriesel", 80: "Regenschauer", 81: "Regenschauer",
        82: "heftige Regenschauer", 85: "Schneeschauer", 86: "starke Schneeschauer", 95: "Gewitter",
        96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel"}


def _json_holen(url: str, holen=None) -> dict:
    if holen is not None:
        return holen(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Nova-Assistent"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read(2_000_000).decode("utf-8"))


def wetter(ort: str, tage: int = 3, holen=None) -> str:
    ort = " ".join((ort or "").split())[:80]
    if not ort:
        raise RechenFehler("Fuer welchen Ort?")
    geo = _json_holen("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": ort, "count": 1, "language": "de", "format": "json"}), holen)
    treffer = (geo.get("results") or [None])[0]
    if not treffer:
        raise RechenFehler(f"Den Ort '{ort}' finde ich nicht.")
    tage = max(1, min(int(tage or 3), 7))
    w = _json_holen("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": treffer["latitude"], "longitude": treffer["longitude"], "timezone": "auto", "forecast_days": tage,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}), holen)
    c = w.get("current") or {}
    name = ", ".join(x for x in (treffer.get("name"), treffer.get("admin1"), treffer.get("country")) if x)
    zeilen = [f"Wetter {name}: jetzt {c.get('temperature_2m')} °C (gefuehlt {c.get('apparent_temperature')} °C), "
              f"{_WMO.get(c.get('weather_code'), '?')}, Wind {c.get('wind_speed_10m')} km/h, "
              f"Luftfeuchte {c.get('relative_humidity_2m')} %"]
    d = w.get("daily") or {}
    for i, tag in enumerate((d.get("time") or [])[:tage]):
        try:
            wt = _WOCHENTAGE[date.fromisoformat(tag).weekday()][:2]
            zeilen.append(f"  {wt} {tag[8:10]}.{tag[5:7]}.: {d['temperature_2m_min'][i]}-{d['temperature_2m_max'][i]} °C, "
                          f"{_WMO.get(d['weather_code'][i], '?')}, Regen {d['precipitation_probability_max'][i]} %")
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    zeilen.append("(Quelle: open-meteo.com)")
    return "\n".join(zeilen)


class Wetter(Tool):
    name = "wetter"
    description = ("Aktuelles Wetter und Vorhersage (bis 7 Tage) fuer einen Ort - ohne Schluessel, Quelle "
                   "open-meteo.com. ort (Stadt), tage (1-7).")
    input_schema = {"type": "object", "properties": {"ort": {"type": "string"}, "tage": {"type": "integer"}},
                    "required": ["ort"]}

    def run(self, ctx: ToolContext, ort: str, tage: int = 3) -> str:
        try:
            return wetter(ort, tage)
        except RechenFehler as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 - kein Netz o.ae.
            return f"Wetterdienst gerade nicht erreichbar ({type(exc).__name__})."


# ---------------------------------------------------------------- PC-Auslastung
class Auslastung(Tool):
    name = "pc_auslastung"
    description = ("Live-Auslastung dieses Geraets: Prozessor %, Arbeitsspeicher %, Akku, Zeit seit dem Neustart. "
                   "Nutze es bei 'warum ist mein PC langsam?' (danach ggf. 'prozesse' fuer die groessten Verbraucher).")
    input_schema = {"type": "object", "properties": {}}

    def run(self, ctx: ToolContext) -> str:
        from ..systemstatus import messen

        m = messen()
        teile = [f"Prozessor {m.get('cpu')} % ({m.get('kerne')} Kerne)",
                 f"Arbeitsspeicher {m.get('ram')} % von {m.get('ram_gb')} GB"]
        if m.get("akku") is not None:
            teile.append(f"Akku {m['akku']} %{' (laedt)' if m.get('am_netz') else ''}")
        if m.get("laufzeit_h") is not None:
            teile.append(f"seit Neustart {m['laufzeit_h']} h")
        return " · ".join(teile)


def register(registry) -> None:
    for werkzeug in (Rechner(), Einheiten(), DatumRechnen(), Wetter(), Auslastung()):
        registry.register(werkzeug)
