"""Verbindung zur Nova-Handy-App: Nova (Cloud oder PC) steuert das Handy - ohne Termux, ohne ADB, ohne Kabel.

Die App (Nova-Handy.apk) hat einen Android-Bedienungshilfe-Dienst. Ist er eingeschaltet, laeuft er im
Hintergrund (die App muss nicht offen sein) und fragt bei Nova nach Auftraegen:

    Handy  --GET /api/geraet/auftrag (wartet bis zu 25 s)-->  Nova      (X-KI-Token = der App-Schluessel)
    Handy  <-- {"auftrag": {"id", "aktion", ...}} -----------  Nova
    Handy  --POST /api/geraet/ergebnis {"id", "ok", "text"}->  Nova

Das Handy baut die Verbindung auf (nicht umgekehrt) - so klappt es auch hinter Mobilfunk/WLAN-Routern.
Nova fragt dich wie immer vor dem Handeln (Stuetzraeder). Das Handy selbst verweigert: Eingaben in die
Nova-App (sonst koennte sich die KI selbst Rechte geben), Passwortfelder und den App-Installierer.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import deque

WARTEN_ABHOLEN = 25.0        # so lange haelt Nova die Abfrage des Handys offen
VERBUNDEN_FENSTER = 75.0     # so lange nach dem letzten Kontakt gilt das Handy als verbunden
STANDARD_TIMEOUT = 45.0


class GeraetFehler(RuntimeError):
    pass


class GeraeteKanal:
    """Warteschlange zwischen Novas Werkzeug (ausfuehren) und dem Handy (abholen/ergebnis)."""

    def __init__(self, uhr=time.monotonic):
        self._uhr = uhr
        self._bedingung = threading.Condition()
        self._auftraege: deque = deque()
        self._ergebnisse: dict[str, dict] = {}
        self._offen: set[str] = set()
        self.letzter_kontakt = None
        self.info: dict = {}

    # -- Seite des Handys ------------------------------------------------------
    def abholen(self, info: dict | None = None, warte: float = WARTEN_ABHOLEN) -> dict | None:
        ende = self._uhr() + max(0.0, warte)
        with self._bedingung:
            self.letzter_kontakt = self._uhr()
            if info:
                self.info = {k: str(v)[:80] for k, v in info.items() if k in _INFO_FELDER}
            while not self._auftraege:
                rest = ende - self._uhr()
                if rest <= 0:
                    return None
                self._bedingung.wait(min(rest, 5.0))
                self.letzter_kontakt = self._uhr()
            return self._auftraege.popleft()

    def ergebnis(self, auftrag_id: str, daten: dict) -> bool:
        with self._bedingung:
            self.letzter_kontakt = self._uhr()
            if auftrag_id not in self._offen:
                return False                  # unbekannt oder zu spaet - nichts annehmen
            self._offen.discard(auftrag_id)
            self._ergebnisse[auftrag_id] = {"ok": bool(daten.get("ok")), "text": str(daten.get("text") or "")[:20000],
                                            "fehler": str(daten.get("fehler") or "")[:2000]}
            self._bedingung.notify_all()
            return True

    # -- Seite von Nova --------------------------------------------------------
    def verbunden(self) -> bool:
        return self.letzter_kontakt is not None and self._uhr() - self.letzter_kontakt < VERBUNDEN_FENSTER

    def ausfuehren(self, aktion: str, angaben: dict | None = None, timeout: float = STANDARD_TIMEOUT) -> str:
        if not self.verbunden():
            raise GeraetFehler(NICHT_VERBUNDEN)
        auftrag_id = secrets.token_hex(8)
        auftrag = {"id": auftrag_id, "aktion": aktion}
        auftrag.update({k: v for k, v in (angaben or {}).items() if v not in (None, "") and k not in auftrag})
        ende = self._uhr() + timeout
        with self._bedingung:
            self._offen.add(auftrag_id)
            self._auftraege.append(auftrag)
            self._bedingung.notify_all()
            while auftrag_id not in self._ergebnisse:
                rest = ende - self._uhr()
                if rest <= 0:
                    self._offen.discard(auftrag_id)
                    try:
                        self._auftraege.remove(auftrag)   # noch nicht abgeholt: gar nicht erst ausfuehren
                    except ValueError:
                        pass
                    raise GeraetFehler("Das Handy hat nicht rechtzeitig geantwortet (kein Netz? Akku-Sparmodus?).")
                self._bedingung.wait(min(rest, 5.0))
            e = self._ergebnisse.pop(auftrag_id)
        if not e["ok"]:
            raise GeraetFehler(e["fehler"] or "Das ging auf dem Handy nicht.")
        return e["text"] or "Erledigt."

    def status_text(self) -> str:
        if not self.verbunden():
            return NICHT_VERBUNDEN
        i = self.info
        teile = [i.get("modell", "Handy"), f"Android {i['android']}" if i.get("android") else "",
                 "Bedienungshilfe an" if i.get("bedienung") == "1" else ""]
        return "Verbunden: " + ", ".join(t for t in teile if t)


_INFO_FELDER = {"modell", "android", "app", "bedienung"}

NICHT_VERBUNDEN = (
    "Die Nova-Handy-App ist nicht verbunden. Dein Mensch richtet das einmal ein: Nova-Handy.apk installieren, "
    "mit Nova verbinden (Cloud-Adresse mit ?t=Schluessel), dann in der App (Zurueck-Taste -> Hilfeseite) "
    "'Handy-Steuerung einschalten' -> in den Android-Einstellungen 'Bedienungshilfen' -> Nova -> an. "
    "Bei Android 13+ vorher: App-Info von Nova -> Drei-Punkte-Menue -> 'Eingeschraenkte Einstellungen zulassen'.")

KANAL = GeraeteKanal()   # einer pro Nova (ein Handy - das zuletzt verbundene)
