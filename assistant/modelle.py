"""Welches Modell denkt - und wie gruendlich? (Auswahl in App und Terminal)

Pro Gehirn gibt es mehrere Modelle (stark/langsam bis schnell/guenstig) und eine
Denk-Tiefe. Mehr Denk-Tiefe = bessere Antworten bei schweren Aufgaben, aber laenger
warten und mehr Kosten. Fuer Alltagsfragen reicht "schnell" oder "ausgewogen".

Gespeichert wird in config/settings.toml:
  [claude]   model = "claude-opus-5-5"   effort = "medium"   (low|medium|high|xhigh|max)
  [deepseek] model = "deepseek-flash"    denken = "aus"      (aus|low|high|max)
  [gemini]   model = "gemini-3.8-flash"  denken = "low"      (low|medium|high)
  [ollama]   model = "qwen3.5:4b"        denken = "aus"      (aus|an)  - jedes Ollama-Modell
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from .config import save_setting, toml_string

# Preise in US-Dollar pro 1 Mio. Token: (Input, Cache-Treffer, Output).
CLAUDE_MODELLE = [
    {"id": "claude-opus-5-5", "name": "Claude Opus 5.5", "kurz": "opus",
     "info": "sehr stark und gruendlich - der Standard", "tempo": "mittel",
     "preis": (4.0, 0.2, 20.0), "sieht_bilder": True},
    {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "kurz": "sonnet",
     "info": "schnell und stark - gut fuer jeden Tag", "tempo": "schnell",
     "preis": (2.0, 0.2, 10.0), "sieht_bilder": True},
    {"id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "kurz": "haiku",
     "info": "blitzschnell und sehr guenstig - fuer einfache Sachen", "tempo": "sehr schnell",
     "preis": (0.1, 0.01, 0.5), "preis_lang": (0.5, 0.05, 2.5), "lang_ab": 100_000,
     "sieht_bilder": True},
    {"id": "claude-fable-5-1", "name": "Claude Fable 5.1", "kurz": "fable",
     "info": "das staerkste Claude - fuer sehr schwere Aufgaben, langsamer und teurer",
     "tempo": "langsam", "preis": (10.0, 0.25, 50.0), "sieht_bilder": True},
]

# DeepSeek: tagsueber (Spitzenzeit) doppelt so teuer wie sonst.
DEEPSEEK_MODELLE = [
    {"id": "deepseek-flash", "name": "DeepSeek Flash", "kurz": "flash",
     "info": "schnell und extrem guenstig - der Standard", "tempo": "schnell",
     "preis": (0.15, 0.003, 0.6), "preis_spitze": (0.3, 0.006, 1.2), "sieht_bilder": True},
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "kurz": "pro",
     "info": "staerker bei schweren Aufgaben, etwas langsamer und teurer", "tempo": "mittel",
     "preis": (0.66, 0.022, 1.98), "preis_spitze": (1.32, 0.044, 3.96), "sieht_bilder": False},
]

# Google Gemini (OpenAI-kompatibel). Alle sehen Bilder. "preis_neu": (ab Datum, neuer Preis) -
# Google hat Preiserhoehungen angekuendigt (Stand 13.11.2026).
GEMINI_MODELLE = [
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "kurz": "flash",
     "info": "schnell und guenstig - der Standard, mit kostenlosem Einstieg", "tempo": "schnell",
     "preis": (0.75, 0.075, 3.75), "preis_neu": ("2027-01-01", (1.5, 0.15, 7.5)), "sieht_bilder": True},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "kurz": "lite",
     "info": "blitzschnell und am guenstigsten - fuer einfache Sachen", "tempo": "sehr schnell",
     "preis": (0.3, 0.03, 2.5), "sieht_bilder": True},
    {"id": "gemini-4-hydrogen", "name": "Gemini 4 Hydrogen", "kurz": "hydrogen",
     "info": "Gemini 4, auf Tempo getrimmt - stark und flott", "tempo": "schnell",
     "preis": (1.5, 0.075, 7.5), "sieht_bilder": True},
    {"id": "gemini-4-argon", "name": "Gemini 4 Argon", "kurz": "argon",
     "info": "sehr stark, schneller als Carbon", "tempo": "mittel",
     "preis": (2.0, 0.1, 10.0), "preis_neu": ("2026-12-01", (4.0, 0.2, 20.0)), "sieht_bilder": True},
    {"id": "gemini-4-carbon", "name": "Gemini 4 Carbon", "kurz": "carbon",
     "info": "das staerkste Gemini - fuer sehr schwere Aufgaben, langsamer und teurer", "tempo": "langsam",
     "preis": (2.0, 0.1, 10.0), "preis_neu": ("2026-12-01", (4.0, 0.2, 20.0)), "sieht_bilder": True},
]

# DeepSeek-Modell, das Bilder ansieht: beschreibt sie fuer Modelle ohne Augen (V4 Pro).
DEEPSEEK_SEHMODELL = "deepseek-flash"

# Ollama: kostenlos auf deinem PC. Hier nur die Empfehlungen - waehlen laesst sich jedes
# heruntergeladene Modell (siehe assistant/ollama.py).
def _ollama_modelle() -> list[dict]:
    from .ollama import EMPFOHLEN

    return [{"id": m["id"], "name": m["name"], "kurz": m["kurz"], "info": m["info"],
             "tempo": "je nach PC", "preis": (0.0, 0.0, 0.0), "sieht_bilder": m["sieht_bilder"],
             "groesse": m["groesse"]} for m in EMPFOHLEN]


OLLAMA_MODELLE = _ollama_modelle()

MODELLE = {"claude": CLAUDE_MODELLE, "deepseek": DEEPSEEK_MODELLE, "gemini": GEMINI_MODELLE,
           "ollama": OLLAMA_MODELLE}

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
    "gemini": [
        ("low", "schnell", "denkt nur ganz kurz nach - fuer Alltagsfragen"),
        ("medium", "ausgewogen", "denkt etwas nach - guter Mittelweg"),
        ("high", "gruendlich", "denkt laenger nach - fuer knifflige Aufgaben"),
    ],
    "ollama": [
        ("aus", "schnell", "antwortet sofort, ohne vorher nachzudenken"),
        ("an", "gruendlich", "denkt vorher nach - nur Modelle, die das koennen; dauert auf dem PC laenger"),
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
# Ollama-Namen duerfen mehr: "qwen3.5:4b", "hf.co/nutzer/modell:Q4_K_M"
_OLLAMA_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:]{0,150}$")


def modell_info(provider: str, model_id: str) -> dict | None:
    return next((m for m in MODELLE.get(provider, []) if m["id"] == model_id), None)


def sieht_bilder(provider: str, model_id: str) -> bool:
    """Kann dieses Modell Bilder ansehen? Unbekannte Claude-Modelle: ja (alle aktuellen
    koennen es), unbekannte DeepSeek-Modelle: nein (dann beschreibt DeepSeek Flash das Bild)."""
    provider = (provider or "").strip().lower()
    wanted = (model_id or "").strip().lower()
    if provider == "deepseek" and wanted in ALTE_DEEPSEEK_NAMEN:
        wanted = ALTE_DEEPSEEK_NAMEN[wanted][0]  # alte Namen laufen auf dem neuen Modell
    info = modell_info(provider, wanted)
    if info is not None:
        return bool(info.get("sieht_bilder", False))
    # Unbekannte Claude- und Gemini-Modelle: ja. Ollama: fragt der Provider Ollama selbst.
    return provider in ("claude", "gemini")


def modell_name(provider: str, model_id: str) -> str:
    info = modell_info(provider, model_id)
    return info["name"] if info else model_id


def denktiefe_name(provider: str, wert: str) -> str:
    return next((name for w, name, _ in DENKTIEFEN.get(provider, []) if w == wert), wert)


def aktuelle_denktiefe(config, provider: str | None = None) -> str:
    provider = provider or config.active_provider
    if provider == "ollama":
        return config.ollama.denken
    if provider == "gemini":
        return config.gemini.denken
    return config.deepseek.denken if provider == "deepseek" else config.claude.effort


def _section(config, provider: str):
    """(Einstellungs-Abschnitt, Name der Denk-Tiefe darin) eines Gehirns."""
    if provider == "deepseek":
        return config.deepseek, "denken"
    if provider == "ollama":
        return config.ollama, "denken"
    if provider == "gemini":
        return config.gemini, "denken"
    return config.claude, "effort"


def kurzbeschreibung(config, provider: str | None = None) -> str:
    """z.B. 'Claude Opus 5.5 - ausgewogen' (fuer Anzeige und Banner)."""
    provider = provider or config.active_provider
    model = _section(config, provider)[0].model
    return f"{modell_name(provider, model)} \u2013 {denktiefe_name(provider, aktuelle_denktiefe(config, provider))}"


def normalisiere_ollama(ollama) -> None:
    """Unsinnige Werte aus [ollama] nicht abstuerzen lassen (Adresse wird beim Benutzen geprueft)."""
    from .config import DEFAULT_OLLAMA_ADRESSE, DEFAULT_OLLAMA_MODEL

    if not isinstance(ollama.model, str) or not _OLLAMA_ID.match(ollama.model.strip()) or ".." in ollama.model:
        ollama.model = DEFAULT_OLLAMA_MODEL
    ollama.model = ollama.model.strip()
    if not isinstance(ollama.adresse, str) or not ollama.adresse.strip():
        ollama.adresse = DEFAULT_OLLAMA_ADRESSE
    ollama.denken = _ollama_stufe(ollama.denken) or "aus"
    for key, default, low, high in (("kontext", 16384, 2048, 262144), ("max_tokens", 8192, 256, 131072)):
        try:
            value = int(getattr(ollama, key))
        except (TypeError, ValueError):
            value = default
        setattr(ollama, key, min(high, max(low, value)))


def _ollama_stufe(wert) -> str | None:
    if wert is True:
        return "an"
    if wert is False:
        return "aus"
    wert = str(wert or "").strip().lower().replace("\u00fc", "ue")
    if wert in ("aus", "off", "none", "nein", "false", "schnell", "low", "disabled"):
        return "aus"
    if wert in ("an", "ein", "on", "ja", "true", "medium", "high", "xhigh", "max", "gruendlich",
                "sehr gruendlich", "maximal", "ausgewogen"):
        return "an"
    return None


def ollama_denken(config, override: str | None = None) -> bool:
    """Soll das Ollama-Modell jetzt nachdenken? Im Live-Modus zaehlt Tempo ('low' = nein)."""
    if override:
        return override not in ("low", "medium") and _ollama_stufe(override) == "an"
    return (_ollama_stufe(config.ollama.denken) or "aus") == "an"


def normalisiere_claude(claude) -> None:
    """Unsinnige Werte aus settings.toml (z.B. Zahl statt Text) nicht abstuerzen lassen."""
    from .config import DEFAULT_MODEL

    if not isinstance(claude.model, str) or not _MODELL_ID.match(claude.model.strip().lower()):
        claude.model = DEFAULT_MODEL
    claude.model = claude.model.strip()
    effort = str(claude.effort or "").strip().lower()
    claude.effort = effort if effort in [w for w, _, _ in DENKTIEFEN["claude"]] else "medium"


def normalisiere_deepseek(deepseek, denken_gesetzt: bool) -> None:
    """Alte, abgeschaltete DeepSeek-Namen auf die aktuellen umstellen (nur im Speicher)."""
    from .config import DEFAULT_DEEPSEEK_MODEL

    if not isinstance(deepseek.model, str) or not _MODELL_ID.match(deepseek.model.strip().lower()):
        deepseek.model = DEFAULT_DEEPSEEK_MODEL
    deepseek.model = deepseek.model.strip()
    if not isinstance(deepseek.denken, str):
        deepseek.denken = "high" if deepseek.denken is True else "aus"
    old = deepseek.model.lower()
    if old in ALTE_DEEPSEEK_NAMEN:
        new, denken = ALTE_DEEPSEEK_NAMEN[old]
        deepseek.model = new
        if denken and not denken_gesetzt:
            deepseek.denken = denken
    deepseek.denken = _deepseek_stufe(deepseek.denken) or "aus"


def normalisiere_gemini(gemini) -> None:
    """Unsinnige Werte aus [gemini] nicht abstuerzen lassen; abgeloeste Modelle umstellen."""
    from .config import DEFAULT_GEMINI_MODEL, GEMINI_BASE_URL

    if not isinstance(gemini.model, str) or not _MODELL_ID.match(gemini.model.strip().lower()):
        gemini.model = DEFAULT_GEMINI_MODEL
    gemini.model = gemini.model.strip()
    if gemini.model.lower() in ALTE_GEMINI_NAMEN:
        gemini.model = ALTE_GEMINI_NAMEN[gemini.model.lower()]
    gemini.denken = _gemini_stufe(gemini.denken) or "low"
    if not isinstance(gemini.base_url, str) or not gemini.base_url.startswith("https://"):
        gemini.base_url = GEMINI_BASE_URL
    try:
        gemini.max_tokens = min(65536, max(2048, int(gemini.max_tokens)))
    except (TypeError, ValueError):
        gemini.max_tokens = 16384


# Abgeloeste Gemini-Modelle (Google leitet sie ab 01.12.2026 um) -> Nachfolger
ALTE_GEMINI_NAMEN = {
    "gemini-2.5-flash": "gemini-3.8-flash",
    "gemini-2.5-pro": "gemini-4-argon",
    "gemini-2.0-flash": "gemini-3.8-flash",
    "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
}


def _gemini_stufe(wert) -> str | None:
    wert = str(wert or "").strip().lower().replace("\u00fc", "ue")
    if wert in ("low", "medium", "high"):
        return wert
    return {"aus": "low", "off": "low", "none": "low", "minimal": "low", "schnell": "low", "an": "medium",
            "ausgewogen": "medium", "mittel": "medium", "gruendlich": "high", "xhigh": "high", "max": "high",
            "maximal": "high", "sehr gruendlich": "high"}.get(wert)


def gemini_denken(config, override: str | None = None) -> str:
    """Denk-Stufe fuer Gemini. Im Live-Modus (override = Claude-Stufe) zaehlt Tempo."""
    if override:
        return {"low": "low", "medium": "low", "high": "medium", "xhigh": "high", "max": "high"}.get(
            override, _gemini_stufe(override) or "low")
    return _gemini_stufe(config.gemini.denken) or "low"


def _deepseek_stufe(wert) -> str | None:
    wert = str(wert or "").strip().lower()
    if wert in ("aus", "low", "high", "max"):
        return wert
    # Claude-Stufen und Synonyme sinnvoll uebersetzen (DeepSeek kennt nur low/high/max)
    return {"off": "aus", "none": "aus", "disabled": "aus", "nein": "aus", "minimal": "low",
            "medium": "high", "xhigh": "high", "ultra": "max", "an": "high", "ein": "high"}.get(wert)


def deepseek_denken(config, override: str | None = None) -> str:
    """Welche Denk-Stufe DeepSeek jetzt nutzt. 'override' kommt vom Live-Modus (Claude-Stufe):
    dort zaehlt Tempo - deshalb bewusst eine Stufe schneller als sonst ('low' = gar nicht
    erst nachdenken, 'medium' = kurz)."""
    if override:
        return {"low": "aus", "medium": "low", "high": "high", "xhigh": "high", "max": "max"}.get(
            override, _deepseek_stufe(override) or config.deepseek.denken)
    return _deepseek_stufe(config.deepseek.denken) or "aus"


def preise(provider: str, model_id: str, now: datetime | None = None,
           prompt_tokens: int = 0) -> tuple[float, float, float] | None:
    """(Input, Cache-Treffer, Output) in USD pro 1 Mio. Token - oder None (unbekanntes Modell).
    prompt_tokens: Groesse EINER Anfrage (Haiku kostet bei sehr langen Anfragen mehr)."""
    if provider == "ollama":
        return (0.0, 0.0, 0.0)  # laeuft auf deinem PC - kostenlos
    info = modell_info(provider, model_id)
    if not info:
        return None
    if provider == "deepseek" and _spitzenzeit(now):
        return info["preis_spitze"]
    if "preis_neu" in info:
        ab, neu = info["preis_neu"]
        heute = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
        if heute >= ab:
            return neu
    if "lang_ab" in info and prompt_tokens > info["lang_ab"]:
        return info["preis_lang"]
    return info["preis"]


def _spitzenzeit(now: datetime | None = None) -> bool:
    """DeepSeek-Spitzenzeit: Mo-Fr 01-04 und 06-10 Uhr UTC (dann doppelter Preis)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.weekday() < 5 and (1 <= now.hour < 4 or 6 <= now.hour < 10)


def _finde_modell(provider: str, wanted: str) -> str | None:
    wanted_raw = wanted
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return None
    if provider == "deepseek" and wanted in ALTE_DEEPSEEK_NAMEN:
        return ALTE_DEEPSEEK_NAMEN[wanted][0]
    if provider == "gemini" and wanted in ALTE_GEMINI_NAMEN:
        return ALTE_GEMINI_NAMEN[wanted]
    if provider == "ollama":
        from .ollama import finde_empfohlen

        found = finde_empfohlen(wanted)
        if found:
            return found
        if fremdes_modell(wanted):
            return None  # "sonnet", "flash" ... sind keine Ollama-Modelle
        # jedes Ollama-Modell ist erlaubt (Gross-/Kleinschreibung wie eingegeben)
        raw = (wanted_raw or "").strip()
        return raw if _OLLAMA_ID.match(raw) and ".." not in raw else None
    for m in MODELLE.get(provider, []):
        names = {m["id"], m["kurz"], m["name"].lower(),
                 m["name"].lower().replace("claude ", "").replace("deepseek ", "").replace("gemini ", "")}
        if wanted in names or wanted.replace(" ", "-") in names:
            return m["id"]
    return None


def fremdes_modell(wanted: str) -> str | None:
    """Gehoert der Name zu Claude, DeepSeek oder Gemini? -> dieses Gehirn (sonst None)."""
    for other in ("claude", "deepseek", "gemini"):
        if _finde_modell(other, wanted):
            return other
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
    if provider == "ollama":
        return _ollama_stufe(raw)
    if provider == "gemini":
        return _gemini_stufe(raw)
    idx = _WORTE.get(raw)
    if idx is None:
        return None
    if provider == "deepseek":  # DeepSeek hat keine Stufe "sehr gruendlich"
        idx = {3: 2}.get(idx, idx)
        idx = min(idx, 3)
    return levels[min(idx, len(levels) - 1)]


def waehle(config, provider: str | None = None, model: str | None = None,
           denken: str | None = None, http=None) -> dict:
    """Modell und/oder Denk-Tiefe einstellen und dauerhaft speichern.

    Ollama: laeuft es, wird vorher nachgesehen, ob das Modell heruntergeladen ist (http: fuer Tests).
    Gibt {"ok", "message", "changed", "provider"} zurueck."""
    provider = (provider or config.active_provider).strip().lower()
    if provider not in MODELLE:
        return {"ok": False, "message": f"Unbekanntes Gehirn '{provider}'.", "changed": False, "provider": provider}
    section, level_key = _section(config, provider)
    new_model, new_level = section.model, getattr(section, level_key)
    if model:
        found = _finde_modell(provider, model) or (model.strip() if model.strip() == section.model else None)
        if not found and provider == "ollama":
            other = fremdes_modell(model)
            hint = (f"'{model}' ist ein Modell von {_GEHIRN_NAME.get(other, other)} - Ollama nutzt "
                    f"eigene Modelle (z.B. qwen3.5:4b). Zu {other} wechseln: /gehirn {other}") if other \
                else f"'{model}' ist kein gueltiger Modellname fuer Ollama (z.B. qwen3.5:4b)."
            return {"ok": False, "changed": False, "provider": provider, "message": hint}
        if not found:
            names = ", ".join(m["kurz"] for m in MODELLE[provider])
            return {"ok": False, "changed": False, "provider": provider,
                    "message": f"Das Modell '{model}' kenne ich nicht. Moeglich: {names}."}
        if provider == "ollama" and found != section.model:
            fehlt = _ollama_fehlt(config, found, http)
            if fehlt:
                return {"ok": False, "changed": False, "provider": provider, "message": fehlt}
        new_model = found
    if denken:
        found = finde_denktiefe(provider, denken)
        if not found:
            names = ", ".join(name for _, name, _ in DENKTIEFEN[provider])
            return {"ok": False, "changed": False, "provider": provider,
                    "message": f"Diese Denk-Tiefe gibt es nicht. Moeglich: {names}."}
        new_level = found
    model_changed = bool(model) and new_model != section.model
    level_changed = bool(denken) and new_level != getattr(section, level_key)
    root = config.project_root
    # Nur speichern, was wirklich gewaehlt wurde (ein per KI_MODEL erzwungenes Modell bleibt draussen).
    if model_changed:
        save_setting(root, provider, "model", toml_string(new_model))
        section.model = new_model
    if level_changed:
        save_setting(root, provider, level_key, toml_string(new_level))
        setattr(section, level_key, new_level)
    changed = model_changed or level_changed
    message = f"{modell_name(provider, new_model)} \u2013 Denk-Tiefe: {denktiefe_name(provider, new_level)}."
    forced = (os.environ.get("KI_MODEL") or "").strip()
    if model_changed and forced and provider == config.active_provider:
        forced_id = _finde_modell(provider, forced) or forced
        if forced_id != new_model:
            message += (f" Hinweis: KI_MODEL (in .env oder den Umgebungsvariablen) legt beim naechsten Start "
                        f"wieder {modell_name(provider, forced_id)} fest.")
    if provider == "claude" and new_model == "claude-fable-5-1" and new_level in ("xhigh", "max"):
        message += " Achtung: Fable denkt so sehr lange und ist teuer."
    return {"ok": True, "message": message, "changed": changed, "provider": provider}


_GEHIRN_NAME = {"claude": "Claude", "deepseek": "DeepSeek", "gemini": "Gemini", "ollama": "Ollama"}


def _ollama_fehlt(config, modell: str, http=None) -> str:
    """Laeuft Ollama und ist das Modell NICHT heruntergeladen: Hinweis (sonst "" - auch wenn Ollama
    gerade nicht laeuft, dann wird gespeichert und spaeter beim Benutzen gemeldet)."""
    from . import ollama

    adresse = ollama.adresse_aus(config)
    if ollama.ist_openai_adresse(adresse):
        return ""
    try:
        namen = [m["name"] for m in ollama.Dienst(adresse, http).modelle()]
    except Exception:  # noqa: BLE001 - laeuft nicht: nicht pruefbar
        return ""
    if ollama.ist_installiert(modell, namen):
        return ""
    return ollama.MODELL_FEHLT.format(modell=modell)


def beschreibung(config) -> dict:
    """Fuer die Einstellungen in der App: alle Modelle, Denk-Tiefen und was gerade aktiv ist."""
    out = {}
    for provider, models in MODELLE.items():
        current = _section(config, provider)[0].model
        if provider == "ollama":
            # Die Modelle auf dem PC zeigt der eigene Ollama-Bereich (GET /api/ollama).
            out[provider] = {"model": current, "denken": aktuelle_denktiefe(config, provider), "modelle": [],
                             "denktiefen": [{"id": w, "name": name, "info": info}
                                            for w, name, info in DENKTIEFEN[provider]]}
            continue
        rate = float(getattr(config.prices, "usd_zu_eur", 0.92) or 0.92)
        entries = [{"id": m["id"], "name": m["name"], "info": m["info"], "tempo": m["tempo"],
                    "preis": _preis_text(m, rate), "sieht_bilder": bool(m.get("sieht_bilder"))}
                   for m in models]
        if not any(m["id"] == current for m in models) and _MODELL_ID.match(current or ""):
            entries.append({"id": current, "name": current, "info": "eigenes Modell (aus settings.toml)",
                            "tempo": "", "preis": "", "sieht_bilder": sieht_bilder(provider, current)})
        out[provider] = {
            "model": current,
            "denken": aktuelle_denktiefe(config, provider),
            "modelle": entries,
            "denktiefen": [{"id": w, "name": name, "info": info} for w, name, info in DENKTIEFEN[provider]],
        }
    return out


def _preis_text(m: dict, rate: float = 0.92) -> str:
    """In Euro, wie die Kosten-Anzeige: Eingabe / Antwort pro 1 Mio. Token."""
    inp, _hit, out = m["preis"]
    text = f"ca. {_zahl(inp * rate)} \u20ac / {_zahl(out * rate)} \u20ac pro 1 Mio. Token"
    if "preis_spitze" in m:
        text += " (werktags tagsueber doppelt)"
    if "preis_neu" in m:
        ab, neu = m["preis_neu"]
        if datetime.now(timezone.utc).date().isoformat() >= ab:
            text = f"ca. {_zahl(neu[0] * rate)} \u20ac / {_zahl(neu[2] * rate)} \u20ac pro 1 Mio. Token"
        else:
            tag = f"{ab[8:10]}.{ab[5:7]}.{ab[0:4]}"
            text += f" (ab {tag}: {_zahl(neu[0] * rate)} \u20ac / {_zahl(neu[2] * rate)} \u20ac)"
    return text


def _zahl(x: float) -> str:
    return (f"{x:.2f}" if x < 10 else f"{x:.0f}").replace(".", ",")
