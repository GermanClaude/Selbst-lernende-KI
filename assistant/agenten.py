"""Dirigierte Agent-Fenster (Premium Max): die Haupt-Nova ("Dirigent") startet mehrere sichtbare
Sandbox-Novas als Agenten, gibt jedem eigene Teilauftraege, liest mit, was sie tun, und schliesst die
Fenster am Ende wieder. Jeder Agent ist eine eigenstaendige Sandbox-Nova (eigenes Fenster, frisches
Gedaechtnis, aber die Schluessel geerbt) - man kann ihr nicht hineinreden, nur der Dirigent gibt Auftraege.

Verstaendigung laeuft ueber Dateien im Ordner des Agenten (dessen data/), damit kein Netz noetig ist:
  agent.json           - wer der Agent ist (Name), vom Dirigenten geschrieben
  agent_auftrag.jsonl  - Dirigent -> Agent: je Zeile ein Auftrag {"nr":N,"text":...}
  agent_log.jsonl      - Agent -> Dirigent: je Zeile ein fertiges Ergebnis {"nr":N,"zeit":ts,"text":...}
  agent_status.json    - Agent -> Dirigent: {"name":..,"zustand":"arbeitet|frei","nr":N,"zeit":ts}

Sicherheit/Kosten: ein Agent startet nie selbst weitere Agenten (NOVA_AGENT=1 schaltet das Werkzeug ab),
und er wird nur taetig, wenn der Dirigent ihm einen Auftrag gibt - er laeuft also nicht von selbst im Kreis.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

HOECHSTENS = 8          # so viele Agent-Fenster gleichzeitig (Chaos-Bremse, unabhaengig vom Sandbox-Limit)
_POLL = 3.0             # Sekunden zwischen zwei Blicken des Agenten in seinen Auftrags-Briefkasten


# ---------------------------------------------------------------- bin ICH ein Agent?
def aktiv() -> str | None:
    """Laeuft DIESE Nova als dirigierter Agent? Dann ihr Name, sonst None."""
    if os.environ.get("NOVA_AGENT") != "1":
        return None
    return (os.environ.get("NOVA_AGENT_NAME") or "Agent").strip()[:40] or "Agent"


# ---------------------------------------------------------------- Dateipfade im Agent-Ordner
def _auftrag_pfad(root) -> Path:
    return Path(root) / "data" / "agent_auftrag.jsonl"


def _log_pfad(root) -> Path:
    return Path(root) / "data" / "agent_log.jsonl"


def _status_pfad(root) -> Path:
    return Path(root) / "data" / "agent_status.json"


def _agent_json(ordner: Path) -> Path:
    return ordner / "data" / "agent.json"


def _lies_jsonl(pfad: Path) -> list[dict]:
    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    aus = []
    for z in zeilen:
        z = z.strip()
        if not z:
            continue
        try:
            d = json.loads(z)
            if isinstance(d, dict):
                aus.append(d)
        except ValueError:
            continue
    return aus


def _haenge_an(pfad: Path, d: dict) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- Dirigent-Seite (Haupt-Nova)
def _sandbox_ordner(root, sid: str) -> Path:
    return Path(root) / "data" / "simulationen" / sid


def starten(config, stufe: str | None, name: str, auftrag: str, spawn=None) -> dict:
    """Einen neuen Agenten (Sandbox-Nova-Fenster) mit Namen und erstem Auftrag starten."""
    from . import sandbox

    name = " ".join(str(name or "Agent").split())[:40] or "Agent"

    def setze(env: dict) -> None:
        env["NOVA_AGENT"] = "1"
        env["NOVA_AGENT_NAME"] = name

    d = sandbox.starten(config, stufe, spawn=spawn, env_setzen=setze, auftrag="")
    ordner = Path(d["ordner"])
    try:
        _agent_json(ordner).write_text(json.dumps({"name": name, "gestartet": time.time()}), encoding="utf-8")
    except OSError:
        pass
    if auftrag and auftrag.strip():
        _haenge_an(_auftrag_pfad(ordner), {"nr": 1, "text": auftrag.strip()[:8000], "zeit": time.time()})
    return {"id": d["id"], "name": name, "pid": d["pid"], "ordner": str(ordner)}


def liste(root) -> list[dict]:
    """Laufende Agenten (offene Sandboxen mit agent.json)."""
    from . import sandbox

    aus = []
    for d in sandbox.offene(root):
        ordner = _sandbox_ordner(root, str(d.get("id")))
        try:
            info = json.loads(_agent_json(ordner).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        aus.append({"id": d.get("id"), "name": info.get("name", "Agent"), "pid": d.get("pid"),
                    "ordner": str(ordner), "status": status_lesen(ordner)})
    return aus


def _finde(root, id_oder_name: str) -> dict | None:
    kennung = str(id_oder_name or "").strip().lower()
    treffer = [a for a in liste(root) if a["id"].lower() == kennung or a["name"].lower() == kennung]
    return treffer[0] if treffer else None


def auftrag_geben(root, id_oder_name: str, text: str) -> bool:
    """Dem Agenten einen (weiteren) Auftrag in den Briefkasten legen."""
    a = _finde(root, id_oder_name)
    if not a:
        return False
    pfad = _auftrag_pfad(Path(a["ordner"]))
    nr = len(_lies_jsonl(pfad)) + 1
    _haenge_an(pfad, {"nr": nr, "text": str(text or "").strip()[:8000], "zeit": time.time()})
    return True


def log_lesen(ordner) -> list[dict]:
    return _lies_jsonl(_log_pfad(Path(ordner)))


def status_lesen(ordner) -> dict:
    try:
        d = json.loads(_status_pfad(Path(ordner)).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def schliessen(root, id_oder_name: str = "") -> dict:
    """Einen Agenten (oder alle) schliessen. Das Protokoll (was er geschrieben hat) wird vorher gelesen
    und zurueckgegeben, damit die Haupt-Nova es behalten kann."""
    from . import sandbox

    ziel = liste(root) if not id_oder_name else [a for a in liste(root)
                                                 if a["id"] == id_oder_name or a["name"] == id_oder_name
                                                 or (_finde(root, id_oder_name) or {}).get("id") == a["id"]]
    protokolle = []
    for a in ziel:
        protokolle.append({"name": a["name"], "id": a["id"], "log": log_lesen(a["ordner"])})
        sandbox.stoppen(root, a["id"])
    return {"geschlossen": len(ziel), "protokolle": protokolle}


# ---------------------------------------------------------------- Agent-Seite (die Sandbox-Nova)
def neue_auftraege(root, schon: set) -> list[dict]:
    """Auftraege, die der Agent noch nicht erledigt hat (nr nicht in 'schon')."""
    return [a for a in _lies_jsonl(_auftrag_pfad(root))
            if isinstance(a.get("nr"), int) and a["nr"] not in schon and str(a.get("text") or "").strip()]


def log_anhaengen(root, nr: int, text: str) -> None:
    _haenge_an(_log_pfad(root), {"nr": nr, "zeit": time.time(), "text": str(text or "")[:20000]})


def status_setzen(root, zustand: str, nr: int = 0) -> None:
    try:
        p = _status_pfad(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"name": aktiv() or "Agent", "zustand": zustand, "nr": nr,
                                 "zeit": time.time()}), encoding="utf-8")
    except OSError:
        pass
