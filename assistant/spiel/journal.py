"""Spiel-Tagebuch: Plan, Fortschritt und Probleme einer Spielsitzung (ohne Bilder).

Liegt als data/spiele/journal_<id>.json. Daraus baut Nova ein frisches Gespraech, wenn das alte zu
lang wird (Ziel + Tagebuch statt hunderter Bildschirmfotos) - so uebersteht eine Nacht-Sitzung
viele Stunden, und das Gespraech wird nie nachtraeglich veraendert (Claude-sicher).
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

ARTEN = ("plan", "fortschritt", "problem", "system")
MAX_EINTRAEGE = 400
MAX_TEXT = 600


class Journal:
    def __init__(self, ordner: Path, spiel: str, ziel: str, modus: str, kennung: str | None = None):
        self.kennung = kennung or f"{time.strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(3)}"
        self.pfad = Path(ordner) / f"journal_{self.kennung}.json"
        self.daten: dict = {"version": 1, "id": self.kennung, "spiel": spiel, "ziel": str(ziel or "")[:2000],
                            "modus": modus, "begonnen": time.strftime("%Y-%m-%d %H:%M:%S"), "eintraege": [],
                            "zusammenfassungen": [], "zuege": 0, "ende": ""}

    @classmethod
    def laden(cls, pfad: Path) -> "Journal":
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
        journal = cls(Path(pfad).parent, daten.get("spiel", ""), daten.get("ziel", ""), daten.get("modus", ""),
                      kennung=str(daten.get("id") or Path(pfad).stem.removeprefix("journal_")))
        journal.daten.update(daten)
        return journal

    @property
    def eintraege(self) -> list[dict]:
        return self.daten["eintraege"]

    def notiz(self, art: str, text: str, zug: int | None = None) -> None:
        art = art if art in ARTEN else "fortschritt"
        text = " ".join(str(text or "").split())[:MAX_TEXT]
        if not text:
            return
        self.eintraege.append({"zeit": time.strftime("%H:%M"), "art": art, "text": text,
                               **({"zug": int(zug)} if zug is not None else {})})
        if len(self.eintraege) > MAX_EINTRAEGE:
            # aeltere Fortschritte zuerst verwerfen, Plan und Probleme bleiben laenger
            for i, eintrag in enumerate(self.eintraege):
                if eintrag["art"] in ("fortschritt", "system"):
                    del self.eintraege[i]
                    break
            else:
                del self.eintraege[0]

    def zusammenfassung(self, text: str) -> None:
        text = str(text or "").strip()[:4000]
        if text:
            self.daten["zusammenfassungen"] = (self.daten.get("zusammenfassungen") or [])[-4:] + [text]

    def speichern(self) -> None:
        try:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.pfad.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.daten, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.pfad)
        except OSError:
            pass  # das Spiel geht vor - das Tagebuch ist nur eine Hilfe

    def von(self, art: str) -> list[str]:
        return [e["text"] for e in self.eintraege if e.get("art") == art]

    def text_fuer_ki(self, max_zeichen: int = 5000) -> str:
        """Ziel, letzte Zusammenfassung, aktueller Plan und die juengsten Eintraege."""
        teile = []
        zusammen = self.daten.get("zusammenfassungen") or []
        if zusammen:
            teile.append("Zusammenfassung bisher:\n" + zusammen[-1])
        plaene = self.von("plan")
        if plaene:
            teile.append("Aktueller Plan:\n" + plaene[-1])
        juengste = [e for e in self.eintraege if e.get("art") != "plan"][-25:]
        if juengste:
            teile.append("Letzte Eintraege:\n" + "\n".join(f"- [{e['zeit']}] {e['art']}: {e['text']}"
                                                            for e in juengste))
        text = "\n\n".join(teile)
        return text[-max_zeichen:] if len(text) > max_zeichen else text
