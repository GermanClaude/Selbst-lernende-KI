"""API-Schluessel einrichten - direkt im Chat (App und Terminal).

Fuegt dein Mensch einen Schluessel in den Chat ein ("sk-..." fuer DeepSeek,
"sk-ant-..." fuer Claude), wird er NIE an die KI geschickt, sondern:
  1. erkannt (welches Gehirn?),
  2. kurz ausprobiert (stimmt er? ist Guthaben da?),
  3. in .env gespeichert und das passende Gehirn eingeschaltet.
Ausserdem: verstaendliche Meldungen, wenn ein Schluessel spaeter nicht mehr geht.
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
}

_KEY = re.compile(r"(?<![A-Za-z0-9_\-])(sk-[A-Za-z0-9_\-]{20,})(?![A-Za-z0-9_\-])")


def find_key(text: str) -> str | None:
    """Steckt in der Nachricht ein API-Schluessel? (Der darf nie an die KI gehen.)"""
    match = _KEY.search(text or "")
    return match.group(1) if match else None


def provider_for_key(key: str) -> str:
    return "claude" if key.startswith("sk-ant-") else "deepseek"


def mask(key: str) -> str:
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "…"


def key_of(config, provider: str) -> str | None:
    return config.deepseek_api_key if provider == "deepseek" else config.anthropic_api_key


def classify(exc: Exception, provider: str) -> tuple[str, str]:
    """Fehler des Anbieters -> (Art, verstaendliche Meldung)."""
    info = PROVIDERS.get(provider, PROVIDERS["deepseek"])
    name = info["name"]
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = str(exc).lower()
    kind_name = type(exc).__name__.lower()
    if isinstance(exc, ImportError):
        return "missing", f"Fuer {name} fehlt ein Paket ({exc}). Starte einmal start.bat, das installiert es."
    if status == 401 or "authentication" in kind_name or "invalid api key" in text or "invalid x-api-key" in text:
        return "invalid", (f"Der {name}-Schluessel wurde abgelehnt - er ist falsch, unvollstaendig kopiert oder "
                           f"geloescht. Hol dir unter {info['url']} einen neuen und fuege ihn einfach hier ein.")
    if status == 402 or "insufficient balance" in text or "credit balance" in text:
        where = ("platform.deepseek.com -> \"Top up\"" if provider == "deepseek"
                 else "console.anthropic.com -> \"Billing\"")
        return "balance", (f"Der Schluessel stimmt, aber dein {name}-Guthaben ist leer. Lade unter {where} "
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
                                           messages=[{"role": "user", "content": "Hi"}])
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
          tester=None) -> dict:
    """Ein Schritt fuer alles: Schluessel pruefen, speichern, Gehirn umschalten.

    Gibt {"ok", "kind", "message", "provider", "changed_provider"} zurueck."""
    provider = provider or (provider_for_key(key) if key else config.active_provider)
    if provider not in PROVIDERS:
        return {"ok": False, "kind": "other", "message": f"Unbekanntes Gehirn '{provider}'.", "provider": provider}
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


def describe(config) -> dict:
    """Fuer die Einstellungen in der App."""
    return {
        "provider": config.active_provider,
        "providers": [
            {"id": pid, "name": info["name"], "info": info["info"], "url": info["url"],
             "has_key": bool(key_of(config, pid)), "key_hint": mask(key_of(config, pid) or "") if key_of(config, pid)
             else "", "model": config.deepseek.model if pid == "deepseek" else config.claude.model}
            for pid, info in PROVIDERS.items()
        ],
        "key_missing": not config.api_key,
        "env_path": str(Path(config.project_root) / ".env"),
    }
