"""Welches Modell denkt - und wie gruendlich? (Auswahl in App und Terminal)

Pro Gehirn gibt es mehrere Modelle (stark/langsam bis schnell/guenstig) und eine
Denk-Tiefe. Mehr Denk-Tiefe = bessere Antworten bei schweren Aufgaben, aber laenger
warten und mehr Kosten. Fuer Alltagsfragen reicht "schnell" oder "ausgewogen".

Gespeichert wird in config/settings.toml:
  [claude]   model = "claude-opus-5-5"   effort = "medium"   (low|medium|high|xhigh|max)
  [deepseek] model = "deepseek-flash"    denken = "aus"      (aus|low|high|max)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .config import save_setting, toml_string

# Preise in US-Dollar pro 1 Mio. Token: (Input, Cache-Treffer, Output).
CLAUDE_MODELLE = [
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "kurz": "opus",
     "info": "sehr stark und gruendlich - der Standard", "tempo": "mittel",
     "preis": (4.0, 0.2, 20.0)},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "kurz": "sonnet",
     "info": "schnell und stark - gut fuer jeden Tag", "tempo": "schnell",
     "preis": (2.0, 0.2, 10.0)},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "kurz": "haiku",
     "info": "blitzschnell und sehr guenstig - fuer einfache Sachen", "tempo": "sehr schnell",
     "preis": (0.1, 0.01, 0.5)},
    {"id": "claude-fable-5-1", "name": "Claude Fable 5.1", "kurz": "fable",
     "info": "das staerkste Claude - fuer sehr schwere Aufgaben, langsamer und teurer",
     "tempo": "langsam", "preis": (10.0, 0.25, 50.0)},
]

# DeepSeek: tagsueber (Spitzenzeit) doppelt so teuer wie sonst.
DEEPSEEK_MODELLE = [
    {"id": "deepseek-flash", "name": "DeepSeek Flash", "kurz": "flash",
     "info": "schnell und extrem guenstig - der Standard", "tempo": "schnell",
     "preis": (0.15, 0.003, 0.6), "preis_spitze": (0.3, 0.006, 1.2)},
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "kurz": "pro",
     "info": "staerker bei schweren Aufgaben, etwas langsamer und teurer", "tempo": "mittel",
     "preis": (0.66, 0.022, 1.98), "preis_spitze": (1.32, 0.044, 3.96)},
]

MODELLE = {"claude": CLAUDE_MODELLE, "deepseek": DEEPSEEK_MODELLE}

# Denk-Tiefen: (Wert in settings.toml, Name fuer Menschen, Erklaerung)
DENKTIEFEN = {
    "claude": [
        ("low", "schnell", "antwortet fast sofort - fuer Alltagsfragen"),
        ("medium", "ausgewogen", "denkt kurz nach - guter Mittelweg"),
        ("high", "gruendlich", "denkt laenger nach - fuer knifflige Aufgaben"),
        ("xhigh", "sehr gruendlich", "nimmt sich viel Zeit - fuer grosse Programmier-Aufgaben"),
        ("max", "maximal", "so gruendlich wie moeglich - dauert lange, kostet am meisten"),
    ],
    "deepseek": [
        ("aus", "schnell", "antwortet sofort, ohne vorher nachzudenken"),
        ("low", "ausgewogen", "denkt kurz nach"),
        ("high", "gruendlich", "denkt laenger nach - fuer knifflige Aufgaben"),
        ("max", "maximal", "so gruendlich wie moeglich - dauert laenger"),
    ],
}

# Fruehere DeepSeek-Namen (am 24.07.2026 abgeschaltet) -> (neues Modell, Denk-Tiefe)
ALTE_DEEPSEEK_NAMEN = {
    "deepseek-chat": ("deepseek-flash", "aus"),
    "deepseek-reasoner": ("deepseek-flash", "high"),
    "deepseek-v4-flash": ("deepseek-flash", None),
    "deepseek-v4-flash-vision-exp": ("deepseek-flash", None),
}

_WORTE = {  # was Menschen tippen/sagen -> Stufe (je Gehirn passend uebersetzt)
    "schnell": 0, "fix": 0, "aus": 0, "kurz": 0,
    "ausgewogen": 1, "normal": 1, "mittel": 1,
    "gruendlich": 2, "grundlich": 2, "genau": 2,
    "sehr gruendlich": 3, "sehrgruendlich": 3, "sehr-gruendlich": 3,
    "maximal": 4, "max": 4, "maximum": 4,
}

_MODELL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,60}$")


def modell_info(provider: str, model_id: str) -> dict | None:
    return next((m for m in MODELLE.get(provider, []) if m["id"] == model_id), None)


def modell_name(provider: str, model_id: str) -> str:
    info = modell_info(provider, model_id)
    return info["name"] if info else model_id


def denktiefe_name(provider: str, wert: str) -> str:
    return next((name for w, name, _ in DENKTIEFEN.get(provider, []) if w == wert), wert)


def aktuelle_denktiefe(config, provider: str | None = None) -> str:
    provider = provider or config.active_provider
    return config.deepseek.denken if provider == "deepseek" else config.claude.effort


def kurzbeschreibung(config, provider: str | None = None) -> str:
    """z.B. 'Claude Opus 5.5 - ausgewogen' (fuer Anzeige und Banner)."""
    provider = provider or config.active_provider
    model = config.deepseek.model if provider == "deepseek" else config.claude.model
    return f"{modell_name(provider, model)} - {denktiefe_name(provider, aktuelle_denktiefe(config, provider))}"


def normalisiere_deepseek(deepseek, denken_gesetzt: bool) -> None:
    """Alte, abgeschaltete DeepSeek-Namen auf die aktuellen umstellen (nur im Speicher)."""
    old = (deepseek.model or "").strip().lower()
    if old in ALTE_DEEPSEEK_NAMEN:
        new, denken = ALTE_DEEPSEEK_NAMEN[old]
        deepseek.model = new
        if denken and not denken_gesetzt:
            deepseek.denken = denken
    deepseek.denken = _deepseek_stufe(deepseek.denken) or "aus"


def _deepseek_stufe(wert: str | None) -> str | None:
    wert = (wert or "").strip().lower()
    if wert in ("aus", "low", "high", "max"):
        return wert
    # Claude-Stufen und Synonyme sinnvoll uebersetzen (DeepSeek kennt nur low/high/max)
    return {"off": "aus", "none": "aus", "disabled": "aus", "nein": "aus", "minimal": "low",
            "medium": "high", "xhigh": "high", "ultra": "max", "an": "high", "ein": "high"}.get(wert)


def deepseek_denken(config, override: str | None = None) -> str:
    """Welche Denk-Stufe DeepSeek jetzt nutzt. 'override' kommt vom Live-Modus (Claude-Stufe):
    dort zaehlt Tempo - 'low' heisst bei DeepSeek: gar nicht erst nachdenken."""
    if override:
        return {"low": "aus", "medium": "low", "high": "high", "xhigh": "high", "max": "max"}.get(
            override, _deepseek_stufe(override) or config.deepseek.denken)
    return _deepseek_stufe(config.deepseek.denken) or "aus"


def preise(provider: str, model_id: str, now: datetime | None = None) -> tuple[float, float, float] | None:
    """(Input, Cache-Treffer, Output) in USD pro 1 Mio. Token - oder None (unbekanntes Modell)."""
    info = modell_info(provider, model_id)
    if not info:
        return None
    if provider == "deepseek" and _spitzenzeit(now):
        return info["preis_spitze"]
    return info["preis"]


def _spitzenzeit(now: datetime | None = None) -> bool:
    """DeepSeek-Spitzenzeit: Mo-Fr 01-04 und 06-10 Uhr UTC (dann doppelter Preis)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.weekday() < 5 and (1 <= now.hour < 4 or 6 <= now.hour < 10)


def _finde_modell(provider: str, wanted: str) -> str | None:
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return None
    if provider == "deepseek" and wanted in ALTE_DEEPSEEK_NAMEN:
        return ALTE_DEEPSEEK_NAMEN[wanted][0]
    for m in MODELLE.get(provider, []):
        names = {m["id"], m["kurz"], m["name"].lower(), m["name"].lower().replace("claude ", "").replace("deepseek ", "")}
        if wanted in names or wanted.replace(" ", "-") in names:
            return m["id"]
    return None


def finde_denktiefe(provider: str, wanted: str) -> str | None:
    """'gruendlich', 'high', 'schnell', 'aus' ... -> gueltiger Wert fuer dieses Gehirn."""
    raw = (wanted or "").strip().lower().replace("\u00fc", "ue")
    levels = [w for w, _, _ in DENKTIEFEN.get(provider, [])]
    if raw in levels:
        return raw
    for w, name, _ in DENKTIEFEN.get(provider, []):
        if raw == name:
            return w
    if provider == "deepseek":
        stufe = _deepseek_stufe(raw)
        if stufe:
            return stufe
    idx = _WORTE.get(raw)
    if idx is None:
        return None
    if provider == "deepseek":  # DeepSeek hat keine Stufe "sehr gruendlich"
        idx = {3: 2}.get(idx, idx)
        idx = min(idx, 3)
    return levels[min(idx, len(levels) - 1)]


def waehle(config, provider: str | None = None, model: str | None = None,
           denken: str | None = None) -> dict:
    """Modell und/oder Denk-Tiefe einstellen und dauerhaft speichern.

    Gibt {"ok", "message", "changed", "provider"} zurueck."""
    provider = (provider or config.active_provider).strip().lower()
    if provider not in MODELLE:
        return {"ok": False, "message": f"Unbekanntes Gehirn '{provider}'.", "changed": False, "provider": provider}
    section = config.deepseek if provider == "deepseek" else config.claude
    level_key = "denken" if provider == "deepseek" else "effort"
    new_model, new_level = section.model, getattr(section, level_key)
    if model:
        found = _finde_modell(provider, model)
        if not found:
            names = ", ".join(m["kurz"] for m in MODELLE[provider])
            return {"ok": False, "changed": False, "provider": provider,
                    "message": f"Das Modell '{model}' kenne ich nicht. Moeglich: {names}."}
        new_model = found
    if denken:
        found = finde_denktiefe(provider, denken)
        if not found:
            names = ", ".join(name for _, name, _ in DENKTIEFEN[provider])
            return {"ok": False, "changed": False, "provider": provider,
                    "message": f"Diese Denk-Tiefe gibt es nicht. Moeglich: {names}."}
        new_level = found
    changed = (new_model, new_level) != (section.model, getattr(section, level_key))
    if changed:
        root = config.project_root
        save_setting(root, provider, "model", toml_string(new_model))
        save_setting(root, provider, level_key, toml_string(new_level))
        section.model = new_model
        setattr(section, level_key, new_level)
    message = f"{modell_name(provider, new_model)} - Denk-Tiefe: {denktiefe_name(provider, new_level)}."
    if provider == "claude" and new_model == "claude-fable-5-1" and new_level in ("xhigh", "max"):
        message += " Achtung: Fable denkt so sehr lange und ist teuer."
    return {"ok": True, "message": message, "changed": changed, "provider": provider}


def beschreibung(config) -> dict:
    """Fuer die Einstellungen in der App: alle Modelle, Denk-Tiefen und was gerade aktiv ist."""
    out = {}
    for provider, models in MODELLE.items():
        current = config.deepseek.model if provider == "deepseek" else config.claude.model
        entries = [{"id": m["id"], "name": m["name"], "info": m["info"], "tempo": m["tempo"],
                    "preis": _preis_text(m)} for m in models]
        if not any(m["id"] == current for m in models) and _MODELL_ID.match(current or ""):
            entries.append({"id": current, "name": current, "info": "eigenes Modell (aus settings.toml)",
                            "tempo": "", "preis": ""})
        out[provider] = {
            "model": current,
            "denken": aktuelle_denktiefe(config, provider),
            "modelle": entries,
            "denktiefen": [{"id": w, "name": name, "info": info} for w, name, info in DENKTIEFEN[provider]],
        }
    return out


def _preis_text(m: dict) -> str:
    inp, _hit, out = m["preis"]
    text = f"{_zahl(inp)} $ / {_zahl(out)} $ pro 1 Mio. Token"
    if "preis_spitze" in m:
        text += " (tagsueber doppelt)"
    return text


def _zahl(x: float) -> str:
    return (f"{x:.2f}" if x < 1 else f"{x:g}").replace(".", ",")
