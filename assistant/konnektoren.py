"""Konnektoren: eine einfache Oberflaeche fuer Novas Plugin-/MCP-System (assistant/plugins.py).

Statt eine JSON-Konfiguration kennen zu muessen, waehlt man einen Konnektor aus einem Katalog beliebter
Dienste (Zeit, Web, Dateien, GitHub ...) und Nova traegt die richtige Konfiguration selbst ein. Darunter
liegt weiter das MCP-System: ein Konnektor ist ein Programm/Dienst auf dem Rechner (Vertrauen + Nachfragen
wie bei Plugins). config/plugins.json bleibt die Ablage (nur der Mensch/diese Oberflaeche aendert sie).
"""
from __future__ import annotations

import copy
import json

from . import plugins

# Kuratierter Katalog. 'config' ist der mcpServers-Eintrag; <...> sind Platzhalter, die der Nutzer fuellt
# (in 'platzhalter' erklaert). 'braucht' nennt die Voraussetzung (Node/Python-Starter bzw. ein Token).
KATALOG: dict[str, dict] = {
    "zeit": {
        "name": "Zeit & Zeitzonen",
        "beschreibung": "Aktuelle Uhrzeit, Zeitzonen und Umrechnungen.",
        "braucht": "uvx (Python-Starter: 'pip install uv')",
        "config": {"command": "uvx", "args": ["mcp-server-time"]},
    },
    "web": {
        "name": "Web abrufen",
        "beschreibung": "Holt den Text einer Webseite/URL zum Weiterverarbeiten.",
        "braucht": "uvx (Python-Starter: 'pip install uv')",
        "config": {"command": "uvx", "args": ["mcp-server-fetch"]},
    },
    "dateien": {
        "name": "Dateien",
        "beschreibung": "Liest und schreibt Dateien in genau EINEM erlaubten Ordner.",
        "braucht": "npx (kommt mit Node.js)",
        "platzhalter": {"<ORDNER>": "Welchen Ordner darf der Konnektor nutzen? (voller Pfad)"},
        "config": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "<ORDNER>"]},
    },
    "gedaechtnis": {
        "name": "Wissensnetz (Memory)",
        "beschreibung": "Ein einfaches Wissens-/Beziehungsnetz, das der Konnektor pflegt.",
        "braucht": "npx (kommt mit Node.js)",
        "config": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
    },
    "github": {
        "name": "GitHub",
        "beschreibung": "Repos, Issues und Pull Requests lesen/anlegen.",
        "braucht": "npx (Node.js) + ein GitHub-Token",
        "platzhalter": {"<TOKEN>": "Dein GitHub-Token (Personal Access Token)"},
        "config": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
                   "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "<TOKEN>"}},
    },
    "brave_suche": {
        "name": "Brave-Websuche",
        "beschreibung": "Websuche ueber die Brave-Such-API.",
        "braucht": "npx (Node.js) + ein Brave-API-Schluessel",
        "platzhalter": {"<TOKEN>": "Dein Brave-Search-API-Schluessel"},
        "config": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                   "env": {"BRAVE_API_KEY": "<TOKEN>"}},
    },
    "sqlite": {
        "name": "SQLite-Datenbank",
        "beschreibung": "Fragt eine SQLite-Datenbankdatei ab.",
        "braucht": "uvx (Python-Starter: 'pip install uv')",
        "platzhalter": {"<DB>": "Pfad zur .db-/.sqlite-Datei"},
        "config": {"command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "<DB>"]},
    },
}


def katalog() -> list[dict]:
    """Der Katalog als Liste (fuer Anzeige). 'eingaben' = noetige Angaben beim Hinzufuegen (Platzhalter)."""
    out = []
    for schluessel, e in KATALOG.items():
        out.append({"schluessel": schluessel, "name": e["name"], "beschreibung": e["beschreibung"],
                    "braucht": e.get("braucht", ""),
                    "eingaben": [{"feld": k, "frage": v} for k, v in (e.get("platzhalter") or {}).items()]})
    return out


def _fuellen(wert, werte: dict):
    """Ersetzt Platzhalter (<...>) in Strings/Listen/Dicts durch die Werte des Nutzers."""
    if isinstance(wert, str):
        for ph, v in werte.items():
            wert = wert.replace(ph, v)
        return wert
    if isinstance(wert, list):
        return [_fuellen(x, werte) for x in wert]
    if isinstance(wert, dict):
        return {k: _fuellen(v, werte) for k, v in wert.items()}
    return wert


def aktive(root) -> list[dict]:
    """Die eingetragenen Konnektoren (aus config/plugins.json), mit An/Aus und Vertrauen."""
    out = []
    for name, e in plugins.laden(root).items():
        out.append({"name": name, "an": not (e.get("disabled") or e.get("aus")),
                    "vertrauen": bool(e.get("vertrauen")),
                    "quelle": str(e.get("command") or e.get("url") or "")})
    return out


def hinzufuegen(root, schluessel: str, werte: dict | None = None, name: str = "") -> str:
    """Einen Konnektor aus dem Katalog eintragen. Fuellt Platzhalter aus 'werte'. Gibt den Namen zurueck."""
    eintrag = KATALOG.get(schluessel)
    if not eintrag:
        raise plugins.PluginFehler(f"Unbekannter Konnektor '{schluessel}'. Verfuegbar: {', '.join(KATALOG)}.")
    werte = {k: str(v) for k, v in (werte or {}).items()}
    noetig = eintrag.get("platzhalter") or {}
    fehlt = [k for k in noetig if not werte.get(k)]
    if fehlt:
        fragen = "; ".join(f"{k}: {noetig[k]}" for k in fehlt)
        raise plugins.PluginFehler(f"Fuer '{eintrag['name']}' fehlt noch: {fragen}")
    config = _fuellen(copy.deepcopy(eintrag["config"]), werte)
    name = (name or schluessel).strip()
    plugins.einfuegen(root, json.dumps({"mcpServers": {name: config}}))
    return name


def entfernen(root, name: str) -> bool:
    alle = plugins.laden(root)
    if name not in alle:
        return False
    alle.pop(name)
    plugins.speichern(root, alle)
    return True


def setzen(root, name: str, *, an: bool | None = None, vertrauen: bool | None = None) -> bool:
    """An/Aus bzw. Vertrauen eines eingetragenen Konnektors aendern."""
    alle = plugins.laden(root)
    e = alle.get(name)
    if e is None:
        return False
    if an is not None:
        if an:
            e.pop("disabled", None)
            e.pop("aus", None)
        else:
            e["disabled"] = True
    if vertrauen is not None:
        if vertrauen:
            e["vertrauen"] = True
        else:
            e.pop("vertrauen", None)
    plugins.speichern(root, alle)
    return True
