"""Telefon-Gespraech mit Nova (Vonage): du sagst etwas, Nova erledigt es - mit allen Werkzeugen (PC, Handy,
Internet, Dateien ...) - und antwortet dir im selben Anruf. Hin und her, bis du "tschuess" sagst.

Ablauf: Vonage hoert zu (Spracherkennung) -> schickt den Text an Novas Rueckkanal -> Nova sagt "Moment" und
arbeitet (im Hintergrund, wie eine Nachricht aus der App) -> fertig: Nova gibt dem laufenden Anruf neue
Anweisungen (Antwort sprechen, wieder zuhoeren). Rueckfragen vor heiklen Aktionen ("Darf ich ...?") stellt
Nova am Telefon - "ja" oder "nein".

Braucht den Rueckkanal (Cloud-Adresse, eigene Adresse oder cloudflared - siehe anruf_vonage.py).
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import anruf_vonage as V
from .anruf import AnrufFehler

TSCHUESS = re.compile(r"(?i)\b(tsch(ue|\u00fc)ss|auf wiedersehen|auf wiederh(oe|\u00f6)ren|leg auf|auflegen|"
                      r"bis dann|bis sp(ae|\u00e4)ter|das wars?|das war es|ende|beenden|ciao|servus)\b")
JA = re.compile(r"(?i)^\W*(ja|jawohl|jo|jup|klar|okay|ok|gerne|mach( das| es)?|darfst du|einverstanden|"
                r"genau|sicher)\b")
MOMENT = "Moment, ich kuemmere mich darum."
NOCH_DA = "Ich bin noch dran."
NICHT_VERSTANDEN = "Das habe ich nicht verstanden. Sag es bitte nochmal."
WIEDERHOLEN_MAX = 3


def fuer_sprache(text: str, grenze: int = 900) -> str:
    """Antwort vorlesbar machen: ohne Markdown, Links, Code; nicht zu lang."""
    t = re.sub(r"```.*?```", " (Code steht in der App) ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", "(Link in der App)", t)
    t = re.sub(r"[*_#`>|]+", " ", t)
    t = re.sub(r"^\s*[-\u2022]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > grenze:
        t = t[:grenze].rsplit(" ", 1)[0] + " ... Den Rest schreibe ich dir in die App."
    return t or "Erledigt."


def warte_ncco() -> list[dict]:
    """Waehrend Nova arbeitet: kurz Bescheid sagen, dann alle paar Sekunden 'ich bin noch dran'."""
    return [V._sprich(MOMENT),
            {"action": "talk", "language": "de-DE", "loop": 0,
             "text": f'<speak><break time="9s"/>{NOCH_DA}</speak>'}]


@dataclass
class Gespraech(V.Rueckkanal):
    """Rueckkanal fuer ein ganzes Gespraech. bei_text(gespraech, text) laeuft in einem eigenen Faden."""
    bei_text: Callable | None = None
    vonage: object = None
    call_id: str = ""
    beendet: threading.Event = field(default_factory=threading.Event)
    _frage: dict | None = None
    _fehlversuche: int = 0
    verlauf: list = field(default_factory=list)

    def antwort_ncco(self, nutzlast: dict) -> list[dict]:
        self.call_id = str((nutzlast or {}).get("uuid") or self.call_id)
        sprache = (nutzlast or {}).get("speech") or {}
        treffer = [str(r.get("text") or "").strip() for r in sprache.get("results") or [] if isinstance(r, dict)]
        text = next((t for t in treffer if t), "")[:2000]
        frage = self._frage
        if frage is not None:                          # jemand wartet auf ja/nein
            frage["antwort"] = text
            frage["fertig"].set()
            return warte_ncco()
        if not text:
            self._fehlversuche += 1
            if self._fehlversuche >= WIEDERHOLEN_MAX:
                return [V._sprich("Ich hoere dich gerade nicht. Schreib mir sonst in der App. Bis dann!")]
            return [V._sprich(NICHT_VERSTANDEN, barge_in=True), V._hoer_zu(self.url("antwort"))]
        self._fehlversuche = 0
        self.antworten.append(text)
        self.verlauf.append(("du", text))
        if TSCHUESS.search(text) and len(text.split()) <= 6:
            return [V._sprich("Alles klar. Bis dann!")]
        if self.bei_text is not None:
            threading.Thread(target=self.bei_text, args=(self, text), name="anruf-gespraech", daemon=True).start()
        return warte_ncco()

    def bearbeiten(self, pfad: str, nutzlast) -> bytes | None:
        antwort = super().bearbeiten(pfad, nutzlast)
        if pfad == self.pfad("event") and isinstance(nutzlast, dict):
            if nutzlast.get("uuid") and not self.call_id:
                self.call_id = str(nutzlast["uuid"])
            if str(nutzlast.get("status") or "") in V._FERTIG:
                self.beendet.set()
                frage = self._frage
                if frage is not None:
                    frage["fertig"].set()
        return antwort

    def sagen(self, text: str, zuhoeren: bool = True) -> None:
        """Nova spricht (und hoert danach wieder zu). Wirft AnrufFehler, wenn der Anruf schon vorbei ist."""
        if self.beendet.is_set() or not self.call_id or self.vonage is None:
            raise AnrufFehler("Der Anruf ist schon beendet.")
        text = fuer_sprache(text)
        self.verlauf.append(("nova", text))
        ncco = [V._sprich(text, barge_in=zuhoeren)]
        if zuhoeren:
            ncco.append(V._hoer_zu(self.url("antwort")))
        self.vonage.uebergeben(self.call_id, ncco)

    def fragen(self, text: str, timeout: float = 45.0) -> str:
        """Frage stellen und auf die gesprochene Antwort warten ('' = keine Antwort)."""
        frage = {"fertig": threading.Event(), "antwort": ""}
        self._frage = frage
        try:
            self.sagen(text)
            frage["fertig"].wait(timeout)
            return frage["antwort"]
        finally:
            self._frage = None

    def darf_ich(self, beschreibung: str) -> bool:
        try:
            antwort = self.fragen(f"Darf ich: {beschreibung[:200]}? Sag ja oder nein.")
        except AnrufFehler:
            return False
        return bool(JA.search(antwort or ""))

    def auflegen(self) -> None:
        if self.call_id and self.vonage is not None and not self.beendet.is_set():
            try:
                self.vonage.auflegen(self.call_id)
            except AnrufFehler:
                pass


def begruessung(anliegen: str, name: str = "Nova") -> str:
    anliegen = re.sub(r"\s+", " ", (anliegen or "").strip())[:600]
    return (f"Hallo, hier ist {name or 'Nova'}. {anliegen} Sag mir einfach, was ich tun soll - ich kann alles "
            "machen, was ich auch in der App kann. Zum Beenden sag tschuess.").replace("  ", " ")


def starten(vonage, nummer: str, anliegen: str, name: str, minuten: int, bei_text: Callable,
            root=None) -> Gespraech:
    """Ruft an und startet das Gespraech. Wirft AnrufFehler (z.B. kein Rueckkanal moeglich)."""
    kanal = V.rueckkanal_oeffnen(anliegen, root, fabrik=Gespraech)
    if kanal is None:
        raise AnrufFehler("Fuer ein Gespraech am Telefon braucht Vonage eine Adresse, unter der ich erreichbar bin: "
                          "Nova in der Cloud, eine eigene Adresse (VONAGE_WEBHOOK_URL) oder cloudflared am PC.")
    kanal.bei_text = bei_text
    kanal.vonage = vonage
    ncco = [V._sprich(begruessung(anliegen, name), barge_in=True), V._hoer_zu(kanal.url("antwort"))]
    try:
        kanal.call_id = vonage.anrufen(nummer, ncco, minuten, kanal.url("event"))
    except AnrufFehler:
        kanal.stoppen()
        raise
    return kanal
