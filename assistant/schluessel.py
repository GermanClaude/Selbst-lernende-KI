"""API-Schluessel einrichten - direkt im Chat (App und Terminal).

Fuegt dein Mensch einen Schluessel in den Chat ein ("sk-..." fuer DeepSeek,
"sk-ant-..." fuer Claude), wird er NIE an die KI geschickt, sondern:
  1. erkannt (welches Gehirn?),
  2. kurz ausprobiert (stimmt er? ist Guthaben da?),
  3. in .env gespeichert und das passende Gehirn eingeschaltet.
Ausserdem: verstaendliche Meldungen, wenn ein Schluessel spaeter nicht mehr geht.
Ollama (kostenlos, auf deinem PC) braucht keinen Schluessel - dort wird nur geprueft, ob
Ollama laeuft, bevor es eingeschaltet wird.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .config import save_env_value, save_setting, toml_string

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "env": "DEEPSEEK_API_KEY",
        "info": "sehr guenstig, gut fuer jeden Tag",
        "url": "https://platform.deepseek.com/api_keys",
        "prefix": "sk-",
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "env": "ANTHROPIC_API_KEY",
        "info": "sehr stark, teurer",
        "url": "https://console.anthropic.com/settings/keys",
        "prefix": "sk-ant-",
    },
    "ollama": {
        "name": "Ollama (kostenlos, auf deinem PC)",
        "env": "",
        "info": "kostenlos, laeuft auf deinem PC \u2013 ohne Schluessel, ohne Internet",
        "url": "https://ollama.com/download",
        "prefix": "",
        "ohne_schluessel": True,
    },
}

_KEY = re.compile(r"(?<![A-Za-z0-9_\-])(sk-[A-Za-z0-9_\-]{20,})(?![A-Za-z0-9_\-])")


def find_key(text: str) -> str | None:
    """Steckt in der Nachricht ein API-Schluessel? (Der darf nie an die KI gehen.)"""
    match = _KEY.search(text or "")
    return match.group(1) if match else None


_CF_TOKEN = re.compile(r"(?<![A-Za-z0-9_\-])([A-Za-z0-9_\-]{40})(?![A-Za-z0-9_\-])")
CLOUDFLARE_HINWEIS = ("Das sieht nach einem Cloudflare-Schl\u00fcssel aus \u2013 den schicke ich nicht an die KI. "
                      "Bitte in \u201eGehirn & Schl\u00fcssel\u201c \u2192 \u201eBilder\u201c eintragen.")


def find_cloudflare_token(text: str) -> str | None:
    """Ein Cloudflare-Token (40 Zeichen, ohne festen Anfang) im Chat? Nur erkannt, wenn die
    Nachricht praktisch nur aus dem Token besteht oder Cloudflare erwaehnt - sonst zu viele
    Fehlalarme. Er geht dann NICHT an die KI."""
    text = (text or "").strip()
    match = _CF_TOKEN.search(text)
    if not match:
        return None
    token = match.group(1)
    if not (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)):
        return None
    rest = text.replace(token, "").strip(" \t\r\n:=\"'`.,;")
    if not rest or "cloudflare" in text.lower() or "token" in text.lower():
        return token
    return None


def provider_for_key(key: str) -> str:
    return "claude" if key.startswith("sk-ant-") else "deepseek"


def mask(key: str) -> str:
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "…"


def key_of(config, provider: str) -> str | None:
    if provider == "ollama":
        return None  # kein Schluessel noetig
    return config.deepseek_api_key if provider == "deepseek" else config.anthropic_api_key


def braucht_schluessel(provider: str) -> bool:
    return not PROVIDERS.get(provider, {}).get("ohne_schluessel", False)


def bereit(config, provider: str) -> bool:
    """Kann dieses Gehirn benutzt werden? (Schluessel da - bzw. bei Ollama: immer.)"""
    return not braucht_schluessel(provider) or bool(key_of(config, provider))


def classify(exc: Exception, provider: str) -> tuple[str, str]:
    """Fehler des Anbieters -> (Art, verstaendliche Meldung)."""
    info = PROVIDERS.get(provider, PROVIDERS["deepseek"])
    name = info["name"]
    art = getattr(exc, "art", None)
    if provider == "ollama" or art:
        return _classify_ollama(exc, art)
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).lower()
    kind_name = type(exc).__name__.lower()
    if isinstance(exc, ImportError):
        return "missing", f"Fuer {name} fehlt ein Paket ({exc}). Starte einmal start.bat, das installiert es."
    if status == 401 or "authentication" in kind_name or "invalid api key" in text or "invalid x-api-key" in text:
        return "invalid", (f"Der {name}-Schluessel wurde abgelehnt - er ist falsch, unvollstaendig kopiert oder "
                           f"geloescht. Hol dir unter {info['url']} einen neuen und fuege ihn einfach hier ein.")
    if status == 402 or "insufficient balance" in text or "credit balance" in text:
        where = ("platform.deepseek.com unter \u201eTop up\u201c" if provider == "deepseek"
                 else "console.anthropic.com unter \u201eBilling\u201c")
        return "balance", (f"Der Schluessel stimmt, aber dein {name}-Guthaben ist leer. Lade auf {where} "
                           "etwas auf - dann geht es sofort weiter.")
    if status == 403 or "permission" in kind_name:
        return "forbidden", f"{name} erlaubt diesem Schluessel das nicht (gesperrt oder nicht freigeschaltet)."
    if status == 429 or "ratelimit" in kind_name:
        return "busy", f"{name} ist gerade ausgelastet (zu viele Anfragen). Der Schluessel scheint zu stimmen."
    if status and int(status) >= 500:
        return "server", f"{name} hat gerade eine Stoerung. Versuch es in ein paar Minuten nochmal."
    if "connection" in kind_name or "timeout" in kind_name or "connect" in text:
        return "network", f"Keine Verbindung zu {name} - bist du mit dem Internet verbunden?"
    return "other", f"{name} meldet: {str(exc)[:240]}"


def _classify_ollama(exc: Exception, art: str | None) -> tuple[str, str]:
    from .ollama import NICHT_ERREICHBAR_KURZ

    text = str(exc)
    if art == "offline" or "connection refused" in text.lower() or "connect" in type(exc).__name__.lower():
        # OllamaFehler "offline" nennt schon die eingestellte Adresse; sonst lieber gar keine nennen
        return "ollama_offline", text if art == "offline" else NICHT_ERREICHBAR_KURZ
    if art == "modell_fehlt":
        return "ollama_model", text
    if art in ("keine_werkzeuge", "kein_denken"):
        return "ollama_model", text
    return "other", f"Ollama meldet: {text[:240]}"


def friendly_error(exc: Exception, provider: str) -> str | None:
    """Fuer Fehler waehrend des Chats: verstaendliche Meldung oder None (unbekannt)."""
    kind, message = classify(exc, provider)
    return None if kind == "other" else message


def test_key(config, provider: str, key: str) -> tuple[bool, str, str]:
    """Probiert den Schluessel kurz aus. -> (ok, Art, Meldung)"""
    name = PROVIDERS[provider]["name"]
    try:
        if provider == "deepseek":
            from openai import OpenAI, Timeout

            client = OpenAI(api_key=key, base_url=config.deepseek.base_url,
                            timeout=Timeout(25.0, connect=10.0), max_retries=0)
            # 1 Token Antwort: kostet praktisch nichts, zeigt aber auch leeres Guthaben
            client.chat.completions.create(model=config.deepseek.model, max_tokens=1,
                                           messages=[{"role": "user", "content": "Hi"}],
                                           extra_body={"thinking": {"type": "disabled"}})
        else:
            import anthropic

            client = anthropic.Anthropic(api_key=key, timeout=anthropic.Timeout(25.0, connect=10.0), max_retries=0)
            client.models.list(limit=1)
    except Exception as exc:  # noqa: BLE001
        kind, message = classify(exc, provider)
        return kind == "busy", kind, message
    return True, "ok", f"Der {name}-Schluessel funktioniert."


def save_key(config, provider: str, key: str) -> Path:
    """Schluessel dauerhaft in .env speichern und sofort benutzen."""
    if not braucht_schluessel(provider):
        raise ValueError(f"{PROVIDERS[provider]['name']} braucht keinen Schluessel.")
    env = PROVIDERS[provider]["env"]
    path = save_env_value(config.project_root, env, key)
    os.environ[env] = key
    if provider == "deepseek":
        config.deepseek_api_key = key
    else:
        config.anthropic_api_key = key
    return path


def set_provider(config, provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unbekanntes Gehirn '{provider}'. Moeglich: {', '.join(PROVIDERS)}")
    save_setting(config.project_root, "provider", "aktiv", toml_string(provider))
    config.provider.aktiv = provider


def setup(config, key: str | None = None, provider: str | None = None, test: bool = True,
          tester=None, http=None) -> dict:
    """Ein Schritt fuer alles: Schluessel pruefen, speichern, Gehirn umschalten.

    Gibt {"ok", "kind", "message", "provider", "changed_provider"} zurueck."""
    provider = provider or (provider_for_key(key) if key else config.active_provider)
    if provider not in PROVIDERS:
        return {"ok": False, "kind": "other", "message": f"Unbekanntes Gehirn '{provider}'.", "provider": provider}
    if provider == "ollama":
        return setup_ollama(config, pruefen=test, http=http)
    key = (key or "").strip() or key_of(config, provider)
    name = PROVIDERS[provider]["name"]
    if not key:
        return {"ok": False, "kind": "missing_key", "provider": provider,
                "message": f"Fuer {name} fehlt noch der Schluessel - fuege ihn einfach hier ein "
                           f"(zu bekommen unter {PROVIDERS[provider]['url']})."}
    ok, kind, message = (tester or test_key)(config, provider, key) if test else (True, "ok", "")
    if not ok:
        return {"ok": False, "kind": kind, "message": message, "provider": provider}
    save_key(config, provider, key)
    changed = provider != config.active_provider
    if changed:
        set_provider(config, provider)
    done = f"Gespeichert: {name} ist jetzt mein Gehirn (Schluessel {mask(key)})."
    if message and kind == "busy":
        done += " " + message
    return {"ok": True, "kind": kind, "message": done, "provider": provider, "changed_provider": changed}


def setup_ollama(config, pruefen: bool = True, http=None) -> dict:
    """Ollama einschalten. Erst nachsehen, ob es laeuft (pruefen=False: trotzdem einschalten).
    Ist das eingestellte Modell nicht da, aber ein anderes, wird das andere genommen."""
    from . import ollama
    from .modelle import modell_name

    name = PROVIDERS["ollama"]["name"]
    info = ollama.status(config, http=http)
    if pruefen and not info["laeuft"]:
        kind = "ollama_missing" if info.get("installiert") is False else "ollama_offline"
        message = info["fehler"] or ollama.NICHT_ERREICHBAR.format(adresse=info["adresse"])
        if kind == "ollama_missing":
            message = ("Ollama ist auf diesem PC noch nicht installiert. Lade es kostenlos herunter "
                       f"({ollama.DOWNLOAD_SEITE}), starte es und versuch es dann nochmal.")
        return {"ok": False, "kind": kind, "message": message, "provider": "ollama"}
    hinweis = ""
    namen = [m["name"] for m in info["modelle"]]
    if info["laeuft"] and not info["modell_da"]:
        ersatz = ollama.bestes_modell(ollama.Dienst(info["adresse"], http), namen) if not info["openai"] \
            else (namen[0] if namen else None)
        if ersatz:
            from .config import save_setting, toml_string

            save_setting(config.project_root, "ollama", "model", toml_string(ersatz))
            config.ollama.model = ersatz
            hinweis = f" Ich nutze {modell_name('ollama', ersatz)}, das schon auf deinem PC ist."
        else:
            hinweis = (" Es ist aber noch kein passendes Modell heruntergeladen - lade eins in \u201eGehirn & Schluessel\u201c "
                       f"herunter (empfohlen: {ollama.STANDARD_MODELL}) oder tippe /ollama laden "
                       f"{ollama.STANDARD_MODELL}.")
    elif not info["laeuft"]:
        hinweis = " Ollama laeuft gerade nicht - starte es, bevor du schreibst."
    changed = config.active_provider != "ollama"
    if changed:
        set_provider(config, "ollama")
    return {"ok": True, "kind": "ok", "provider": "ollama", "changed_provider": changed,
            "message": f"Gespeichert: {name} ist jetzt mein Gehirn - kostenlos, ohne Schluessel.{hinweis}"}


def describe(config) -> dict:
    """Fuer die Einstellungen in der App."""
    from .modelle import beschreibung, kurzbeschreibung

    return {
        "modelle": beschreibung(config),
        "aktuell": kurzbeschreibung(config),
        "provider": config.active_provider,
        "providers": [
            {"id": pid, "name": info["name"], "info": info["info"], "url": info["url"],
             "has_key": bereit(config, pid), "needs_key": braucht_schluessel(pid),
             "key_hint": mask(key_of(config, pid) or "") if key_of(config, pid)
             else "", "model": config.model_of(pid),
             "model_name": kurzbeschreibung(config, pid)}
            for pid, info in PROVIDERS.items()
        ],
        "key_missing": not config.api_key,
        "env_path": str(Path(config.project_root) / ".env"),
    }
