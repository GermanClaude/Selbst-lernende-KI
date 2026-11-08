"""Was Nova sieht, als kleine Text-Ereignisse - und wann sie sich deshalb meldet.

Ein Ereignis (`Wahrnehmung`) enthaelt nie Pixel, nur: was passiert ist (art), wo (app, titel)
und evtl. erkannten Text. Daraus wird:
  * `bewerte`      - wie wichtig ist es (0 ... 1)?
  * `Buendler`     - gleiche Ereignisse innerhalb von 30 s nur einmal; mehrere zusammen in einem
                     kurzen Fenster (1,5 s, bei sehr Wichtigem 0,5 s) -> genau EINE Wortmeldung
  * `Weckregel`    - darf Nova sich jetzt melden? (Mindestabstand, hoechstens N pro Stunde,
                     Euro-Grenze pro Stunde, Ruhe nach deiner Nachricht)
  * `Kurzzeit`     - die letzte Minute als Text (nur im Arbeitsspeicher)
  * `maskiere`     - IBAN, Kartennummern, Schluessel und Passwoerter aus erkanntem Text entfernen
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from itertools import count

_IDS = count(1)

ARTEN = ("fenster", "titel", "dialog", "text", "inhalt", "video", "bewegung", "privat", "geschuetzt",
         "pause", "weiter", "hinweis", "quelle_fehler")

_FEHLERWORTE = re.compile(
    r"\b(fehler|error|warnung|warning|fehlgeschlagen|failed|failure|exception|traceback|abgest(?:ue|\u00fc)rzt|"
    r"absturz|crash(?:ed)?|reagiert nicht|not responding|kann nicht|konnte nicht|cannot|could not|"
    r"ung(?:ue|\u00fc)ltig|invalid|verweigert|denied|abgelehnt|besch(?:ae|\u00e4)digt|corrupt(?:ed)?|"
    r"timeout|zeit(?:ue|\u00fc)berschreitung|bluescreen|kritisch|critical|fatal)\b",
    re.IGNORECASE,
)


@dataclass
class Wahrnehmung:
    art: str
    quelle: str = "bildschirm"          # bildschirm | fenster | ocr | webcam
    app: str = ""                       # z.B. "excel.exe"
    titel: str = ""
    text: str = ""
    anteil: float = 0.0                 # so viel vom Bild hat sich geaendert (0 ... 1)
    bereich: tuple | None = None        # (x, y, breite, hoehe) im Bild
    wichtig: float = 0.0
    privat: bool = False
    t: float = field(default_factory=time.time)
    id: int = field(default_factory=lambda: next(_IDS))

    @classmethod
    def aus_dict(cls, data: dict) -> "Wahrnehmung":
        bereich = data.get("bereich")
        return cls(art=str(data.get("art") or "hinweis")[:20], quelle=str(data.get("quelle") or "bildschirm")[:20],
                   app=str(data.get("app") or "")[:80], titel=str(data.get("titel") or "")[:200],
                   text=str(data.get("text") or "")[:1200], anteil=float(data.get("anteil") or 0.0),
                   bereich=tuple(bereich) if isinstance(bereich, (list, tuple)) and len(bereich) == 4 else None,
                   privat=bool(data.get("privat")))

    def zeile(self) -> str:
        """Kurz als Text (fuer die KI und die Anzeige) - nie mit privaten Inhalten."""
        wo = self.app or ""
        if self.titel and not self.privat:
            wo = f"{wo} \u201e{self.titel[:80]}\u201c".strip()
        if self.art == "privat":
            return "Ein privates Fenster ist vorne \u2013 ich schaue nicht hin."
        if self.art == "geschuetzt":
            return "Ein Passwortfeld ist aktiv \u2013 ich schaue gerade nicht hin."
        beschreibung = {
            "fenster": "Wechsel zu",
            "titel": "Neuer Fenstertitel:",
            "dialog": "Ein Hinweis-/Dialogfenster ist aufgegangen:",
            "text": "Neuer Text",
            "inhalt": f"Gro\u00dfe \u00c4nderung im Bild ({round(self.anteil * 100)} %)",
            "video": "Bewegtes Bild (Video/Spiel)",
            "bewegung": "Bewegung vor der Webcam",
            "pause": "Pause",
            "weiter": "Weiter",
            "hinweis": "Hinweis:",
            "quelle_fehler": "Problem:",
        }.get(self.art, self.art)
        teile = [beschreibung]
        if wo and self.art not in ("bewegung",):
            teile.append(wo if self.art != "text" else f"in {wo}")
        if self.text and self.art in ("dialog", "text", "hinweis", "quelle_fehler", "titel"):
            teile.append(f": {self.text[:400]}" if self.art == "text" else self.text[:400])
        return " ".join(t for t in teile if t).replace(" :", ":").strip()


def hat_fehlerwort(*texte: str) -> bool:
    return any(_FEHLERWORTE.search(t or "") for t in texte)


@dataclass
class Kontext:
    """Was die Bewertung ausserdem wissen will."""

    stichworte: set[str] = field(default_factory=set)       # aus deinen letzten Nachrichten
    zuletzt_app: dict[str, float] = field(default_factory=dict)  # app -> wann zuletzt vorne (time.time)


def bewerte(ev: Wahrnehmung, kontext: Kontext | None = None, jetzt: float | None = None) -> float:
    """Wie wichtig ist das Ereignis (0 = gar nicht ... 1 = sofort sagen)?"""
    kontext = kontext or Kontext()
    jetzt = time.time() if jetzt is None else jetzt
    if ev.privat or ev.art in ("privat", "geschuetzt", "pause", "weiter", "hinweis", "quelle_fehler"):
        return 0.0
    fehler = hat_fehlerwort(ev.titel, ev.text)
    if ev.art == "dialog":
        return 0.95 if fehler else 0.8
    if ev.art == "fenster":
        vorher = kontext.zuletzt_app.get(ev.app)
        return 0.6 if ev.app and (vorher is None or jetzt - vorher > 600) else 0.4
    if ev.art == "titel":
        return 0.7 if fehler else 0.3
    if ev.art == "text":
        if fehler:
            return 0.85
        woerter = set(re.findall(r"[a-z\u00e4\u00f6\u00fc\u00df0-9]{4,}", ev.text.lower()))
        if kontext.stichworte and woerter & kontext.stichworte:
            return 0.65
        return 0.3
    if ev.art == "inhalt":
        return 0.45 if ev.anteil >= 0.3 else 0.2
    if ev.art == "bewegung":
        return 0.65
    if ev.art == "video":
        return 0.05
    return 0.1


_STOPPWORTE = {"bitte", "kannst", "danke", "dass", "habe", "eine", "einen", "einem", "einer", "nicht", "sind",
               "auch", "noch", "dann", "wenn", "aber", "oder", "doch", "mein", "meine", "dein", "deine", "jetzt",
               "hier", "mal", "schon", "sehr", "machen", "mach", "zeig", "sag", "bescheid", "nova"}


def stichworte(text: str) -> set[str]:
    """Woerter aus deiner Nachricht, nach denen Nova auf dem Bildschirm Ausschau haelt."""
    return {w for w in re.findall(r"[a-z\u00e4\u00f6\u00fc\u00df0-9]{4,}", str(text or "").lower())
            if w not in _STOPPWORTE}


# -- Maskieren -------------------------------------------------------------------------
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
_KARTE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SCHLUESSEL = re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{12,}|sk-ant-[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|"
                         r"AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_\-]{30,})")
_LANG = re.compile(r"\b[A-Za-z0-9_\-]{32,}")
_PASSWORT = re.compile(r"(?i)\b(passwort|kennwort|password|passcode|pin|tan|geheimzahl)\b(\s*[:=]\s*)\S+")


def maskiere(text: str) -> str:
    """Erkannten Text entschaerfen, bevor er irgendwohin geht."""
    text = str(text or "")
    text = _PASSWORT.sub(lambda m: f"{m.group(1)}{m.group(2)}[verdeckt]", text)
    text = _SCHLUESSEL.sub("[Schl\u00fcssel verdeckt]", text)
    text = _IBAN.sub("[IBAN verdeckt]", text)
    text = _KARTE.sub(lambda m: "[Nummer verdeckt]" if sum(c.isdigit() for c in m.group(0)) >= 13 else m.group(0),
                      text)
    text = _LANG.sub(lambda m: "[verdeckt]" if re.search(r"\d", m.group(0)) and re.search(r"[A-Za-z]", m.group(0))
                     else m.group(0), text)
    return text


# -- Buendeln und Entprellen --------------------------------------------------------------
class Buendler:
    """Gleiches innerhalb von `doppelt` Sekunden nur einmal; ein wichtiges Ereignis oeffnet ein
    kurzes Sammelfenster, danach kommt genau ein Buendel heraus."""

    def __init__(self, schwelle: float = 0.6, doppelt: float = 30.0, fenster: float = 1.5,
                 fenster_dringend: float = 0.5):
        self.schwelle = schwelle
        self.doppelt = doppelt
        self.fenster = fenster
        self.fenster_dringend = fenster_dringend
        self._gesehen: dict[tuple, float] = {}
        self._offen: list[Wahrnehmung] = []
        self._frist: float | None = None

    def _schluessel(self, ev: Wahrnehmung) -> tuple:
        return (ev.art, ev.app, ev.titel[:120] if ev.art in ("titel", "fenster", "dialog") else "",
                " ".join(ev.text.split())[:200])

    def hinzu(self, ev: Wahrnehmung, jetzt: float) -> bool:
        """False = doppelt (verworfen)."""
        for k, t in list(self._gesehen.items()):
            if jetzt - t > self.doppelt:
                del self._gesehen[k]
        key = self._schluessel(ev)
        if key in self._gesehen:
            return False
        self._gesehen[key] = jetzt
        if self._frist is not None:
            self._offen.append(ev)
            if ev.wichtig >= 0.9:
                self._frist = min(self._frist, jetzt + self.fenster_dringend)
        elif ev.wichtig >= self.schwelle:
            self._offen = [ev]
            self._frist = jetzt + (self.fenster_dringend if ev.wichtig >= 0.9 else self.fenster)
        return True

    def faellig(self, jetzt: float) -> list[Wahrnehmung] | None:
        if self._frist is None or jetzt < self._frist:
            return None
        buendel, self._offen, self._frist = self._offen, [], None
        return buendel

    def verwerfen(self) -> None:
        self._offen, self._frist = [], None


# -- Darf Nova sich melden? -----------------------------------------------------------------
class Weckregel:
    """Mindestabstand, hoechstens N Wortmeldungen pro Stunde (gleitend), Euro pro Stunde,
    Ruhe nach deiner letzten Nachricht."""

    def __init__(self, min_abstand: float = 20.0, max_pro_stunde: int = 20, max_euro_pro_stunde: float | None = 0.3,
                 ruhe_nach_nutzer: float = 20.0, harte_grenze: int = 360):
        self.min_abstand = float(min_abstand)
        self.max_pro_stunde = max(1, min(int(max_pro_stunde), int(harte_grenze)))
        self.max_euro = max_euro_pro_stunde  # None = kostenlos (Ollama)
        self.ruhe_nach_nutzer = float(ruhe_nach_nutzer)
        self._weckungen: deque[float] = deque()
        self._kosten: deque[tuple[float, float]] = deque()
        self._letzte: float | None = None
        self._nutzer: float | None = None

    def _aufraeumen(self, jetzt: float) -> None:
        while self._weckungen and jetzt - self._weckungen[0] >= 3600:
            self._weckungen.popleft()
        while self._kosten and jetzt - self._kosten[0][0] >= 3600:
            self._kosten.popleft()

    def euro_stunde(self, jetzt: float) -> float:
        self._aufraeumen(jetzt)
        return sum(e for _t, e in self._kosten)

    def weckungen_stunde(self, jetzt: float) -> int:
        self._aufraeumen(jetzt)
        return len(self._weckungen)

    def nutzer(self, jetzt: float) -> None:
        self._nutzer = jetzt

    def darf(self, jetzt: float, wichtig: float) -> tuple[bool, str]:
        self._aufraeumen(jetzt)
        if self._nutzer is not None and jetzt - self._nutzer < self.ruhe_nach_nutzer:
            return False, "nutzer"
        abstand = min(self.min_abstand, 5.0) if wichtig >= 0.9 else self.min_abstand
        if self._letzte is not None and jetzt - self._letzte < abstand:
            return False, "abstand"
        if len(self._weckungen) >= self.max_pro_stunde:
            return False, "anzahl"
        if self.max_euro is not None and self.euro_stunde(jetzt) >= self.max_euro:
            return False, "budget"
        return True, ""

    def gebucht(self, jetzt: float) -> None:
        self._aufraeumen(jetzt)
        self._weckungen.append(jetzt)
        self._letzte = jetzt

    def kosten(self, jetzt: float, eur: float) -> None:
        if eur and eur > 0:
            self._kosten.append((jetzt, float(eur)))

    def euro_rest(self, jetzt: float) -> float | None:
        if self.max_euro is None:
            return None
        return max(0.0, self.max_euro - self.euro_stunde(jetzt))

    def wieder_ab(self, jetzt: float) -> float | None:
        """Ab wann (Sekunden ab jetzt) wieder Platz im Stunden-Budget ist."""
        self._aufraeumen(jetzt)
        kandidaten = []
        if len(self._weckungen) >= self.max_pro_stunde and self._weckungen:
            kandidaten.append(self._weckungen[0] + 3600 - jetzt)
        if self.max_euro is not None and self._kosten and self.euro_stunde(jetzt) >= self.max_euro:
            kandidaten.append(self._kosten[0][0] + 3600 - jetzt)
        return max(0.0, min(kandidaten)) if kandidaten else None


class Kurzzeit:
    """Die letzte Minute als Text - nur im Arbeitsspeicher."""

    def __init__(self, sekunden: float = 60.0, max_zeilen: int = 40):
        self.sekunden = sekunden
        self._zeilen: deque[tuple[float, str]] = deque(maxlen=max_zeilen)

    def hinzu(self, jetzt: float, zeile: str) -> None:
        if zeile and (not self._zeilen or self._zeilen[-1][1] != zeile):
            self._zeilen.append((jetzt, zeile))

    def zeilen(self, jetzt: float) -> list[str]:
        return [z for t, z in list(self._zeilen) if jetzt - t <= self.sekunden]  # Kopie: anderer Thread haengt an

    def leeren(self) -> None:
        self._zeilen.clear()
