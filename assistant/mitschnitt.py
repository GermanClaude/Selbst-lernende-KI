"""Mitschnitt / Transkription: nimmt Ton auf (Mikrofon ODER System-Audio = alles, was der PC
ausgibt - Spiele, Discord/Calls, Videos, Aufnahmen) und schreibt ihn LOKAL mit Whisper in ein
Transkript. Kostet keine API-Token (Whisper laeuft auf dem PC). Laeuft beliebig lange, bis du
stoppst, und schreibt laufend in eine Textdatei (data bleibt auch bei Absturz erhalten).

Sprecher-Trennung ("wer spricht gerade") und Geschlecht sind BEST EFFORT:
  * Mehrere Sprecher auseinanderhalten geht gut nur mit einem Zusatzmodell (resemblyzer). Ist es
    nicht da, wird ohne Sprecher-Aufteilung transkribiert und ein Hinweis geschrieben.
  * Das Geschlecht wird - wenn numpy da ist - grob aus der Tonhoehe GESCHAETZT (keine Gewissheit).
Du kannst erkannten Sprechern Namen geben (Sprecher 1 -> "Aria"); sonst heissen sie "Sprecher 1/2…".

Rechtlicher Hinweis: Gespraeche/Calls mitzuschneiden kann die Zustimmung aller Beteiligten
erfordern. Das liegt in deiner Verantwortung - Nova weist beim Start darauf hin.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .logging_setup import get_logger

logger = get_logger()

_SAMPLE_RATE = 16_000
RECHTS_HINWEIS = (
    "Hinweis: Wenn andere Personen zu hoeren sind (z.B. in einem Call), brauchst du je nach Land "
    "und Situation ihre Zustimmung zum Mitschneiden. Das liegt in deiner Verantwortung."
)
INSTALL_HINWEIS = (
    "Fuer den Mitschnitt fehlt etwas. Noetig: sounddevice + faster-whisper "
    "(pip install sounddevice faster-whisper). Fuer System-Audio (Spiele/Calls) hilft zusaetzlich "
    "numpy. Mehrere Sprecher auseinanderhalten: pip install resemblyzer (optional)."
)


# ---------------------------------------------------------------------------
#  Reine Logik (ohne Audio/Modelle) - gut testbar
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    """Ein Stueck erkannter Rede."""
    start: float          # Sekunden seit Aufnahmebeginn
    ende: float
    text: str
    sprecher: str = "Sprecher 1"   # vorlaeufiges Label (von der Sprecher-Trennung)
    geschlecht: str = ""           # "m" | "w" | "" (unbekannt/geschaetzt), nur Anzeige


def _uhr(sekunden: float) -> str:
    s = max(0, int(sekunden))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def sprecher_name(label: str, namen: dict[str, str]) -> str:
    """Label -> vergebener Name, sonst das Label selbst."""
    return (namen or {}).get(label, label)


def geschlecht_aus_tonhoehe(f0_hz: float) -> str:
    """Grobe Schaetzung aus der mittleren Grundfrequenz. Breites 'unklar'-Band, damit nichts
    faelschlich behauptet wird. Rueckgabe: 'm' | 'w' | ''."""
    if not f0_hz or f0_hz <= 0:
        return ""
    if f0_hz < 150:
        return "m"
    if f0_hz > 185:
        return "w"
    return ""  # dazwischen: nicht sicher genug


def _geschlecht_text(code: str) -> str:
    return {"m": "maennlich?", "w": "weiblich?"}.get(code, "")


def transkript_zeile(seg: Segment, namen: dict[str, str]) -> str:
    """Eine Zeile fuers Transkript: '[00:01:23] Aria (weiblich?): Text'."""
    name = sprecher_name(seg.sprecher, namen)
    g = _geschlecht_text(seg.geschlecht)
    kopf = f"[{_uhr(seg.start)}] {name}"
    if g:
        kopf += f" ({g})"
    return f"{kopf}: {seg.text.strip()}"


def transkript_text(segmente: list[Segment], namen: dict[str, str] | None = None,
                    titel: str = "") -> str:
    namen = namen or {}
    zeilen = [f"# {titel}".rstrip(), ""] if titel else []
    zeilen += [transkript_zeile(s, namen) for s in segmente if s.text.strip()]
    sprecher = sorted({s.sprecher for s in segmente})
    if len(sprecher) > 1:
        zeilen += ["", "Sprecher: " + ", ".join(sprecher_name(s, namen) for s in sprecher)]
    return "\n".join(zeilen).strip() + "\n"


def zusammenfassung_prompt(transkript: str, grenze: int = 40_000) -> str:
    """Prompt, mit dem die KI (auf Wunsch) das Transkript zusammenfasst - knapp, damit es
    wenig Token kostet. Nur ein Ausschnitt, falls das Transkript sehr lang ist."""
    text = transkript if len(transkript) <= grenze else (transkript[: grenze // 2]
            + "\n…(gekuerzt)…\n" + transkript[-grenze // 2:])
    return ("Fasse dieses Gespraechs-Transkript knapp auf Deutsch zusammen: die wichtigsten Punkte "
            "als Stichpunkte, offene Fragen/To-dos, und - falls erkennbar - wer was wollte. "
            "Keine Einleitung.\n\n" + text)


# ---------------------------------------------------------------------------
#  Sprecher-Trennung (best effort) - braucht optionale Pakete
# ---------------------------------------------------------------------------
def _importierbar(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def diarisierung_moeglich() -> bool:
    """Koennen mehrere Sprecher wirklich auseinandergehalten werden? (Zusatzmodell vorhanden?)"""
    return _importierbar("resemblyzer") and _importierbar("numpy")


def _f0_schaetzen(pcm16: bytes) -> float:
    """Mittlere Grundfrequenz (Tonhoehe) einer Mono-16bit-Aufnahme per Autokorrelation. 0.0,
    wenn numpy fehlt oder nichts Stimmhaftes da ist. Nur fuer die grobe Geschlechts-Schaetzung."""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return 0.0
    x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
    if x.size < _SAMPLE_RATE // 4:
        return 0.0
    x -= x.mean()
    if np.sqrt((x * x).mean()) < 200:  # zu leise -> keine verlaessliche Tonhoehe
        return 0.0
    korr = np.correlate(x, x, mode="full")[x.size - 1:]
    lo, hi = _SAMPLE_RATE // 300, _SAMPLE_RATE // 70  # 70..300 Hz (menschliche Stimme)
    if hi >= korr.size:
        return 0.0
    versatz = int(np.argmax(korr[lo:hi])) + lo
    return _SAMPLE_RATE / versatz if versatz else 0.0


# ---------------------------------------------------------------------------
#  Der Mitschnitt (Aufnahme + Transkription, laeuft bis stop())
# ---------------------------------------------------------------------------
@dataclass
class MitschnittStatus:
    laeuft: bool = False
    quelle: str = ""          # "mikrofon" | "system" | ""
    start: float = 0.0
    segmente: int = 0
    datei: str = ""
    letzte: str = ""          # letzte transkribierte Zeile (fuer die Anzeige)
    fehler: str = ""

    def minuten(self) -> int:
        return int((time.time() - self.start) // 60) if self.start else 0


class Mitschnitt:
    """Nimmt in Haeppchen auf und transkribiert lokal, bis stop(). Schreibt laufend ins Transkript."""

    def __init__(self, ordner: Path, sprache: str = "de", chunk_sekunden: float = 30.0):
        self.ordner = Path(ordner)
        self.sprache = sprache or "de"
        self.chunk_sekunden = max(5.0, float(chunk_sekunden))
        self.status = MitschnittStatus()
        self.namen: dict[str, str] = {}
        self.segmente: list[Segment] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._whisper = None
        self._diar = None
        self._lock = threading.Lock()

    # -- Verfuegbarkeit -----------------------------------------------------
    def problem(self) -> str | None:
        if not (_importierbar("sounddevice") and _importierbar("faster_whisper")):
            return INSTALL_HINWEIS
        return None

    @staticmethod
    def quellen() -> list[str]:
        """Welche Aufnahmequellen gehen? 'mikrofon' immer (wenn sounddevice da), 'system' nur mit
        WASAPI-Loopback (Windows)."""
        q = []
        if _importierbar("sounddevice"):
            q.append("mikrofon")
            try:
                import sounddevice as sd
                if any("wasapi" in (a.get("name", "").lower()) for a in sd.query_hostapis()):
                    q.append("system")
            except Exception:  # noqa: BLE001
                pass
        return q

    # -- Start / Stop -------------------------------------------------------
    def start(self, quelle: str = "system") -> dict:
        if self.status.laeuft:
            return {"ok": False, "error": "Es laeuft schon ein Mitschnitt."}
        problem = self.problem()
        if problem:
            return {"ok": False, "error": problem, "setup": True}
        quelle = quelle if quelle in ("mikrofon", "system") else "system"
        self.ordner.mkdir(parents=True, exist_ok=True)
        stempel = time.strftime("%Y-%m-%d_%H-%M-%S")
        datei = self.ordner / f"mitschnitt_{stempel}.md"
        self.segmente, self.namen = [], {}
        self._stop.clear()
        self.status = MitschnittStatus(laeuft=True, quelle=quelle, start=time.time(), datei=str(datei))
        try:
            datei.write_text(f"# Mitschnitt {stempel}\nQuelle: {quelle}\n\n", encoding="utf-8")
        except OSError as exc:
            self.status = MitschnittStatus(fehler=str(exc))
            return {"ok": False, "error": f"Transkript-Datei nicht anlegbar: {exc}"}
        self._thread = threading.Thread(target=self._laufen, name="mitschnitt", daemon=True)
        self._thread.start()
        return {"ok": True, "quelle": quelle, "datei": str(datei), "hinweis": RECHTS_HINWEIS}

    def stop(self) -> dict:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=max(5.0, self.chunk_sekunden + 5))
        self.status.laeuft = False
        return {"ok": True, "datei": self.status.datei, "segmente": len(self.segmente),
                "minuten": self.status.minuten()}

    def benenne(self, label: str, name: str) -> None:
        """Einem Sprecher-Label einen Namen geben (Sprecher 1 -> Aria) und das Transkript neu schreiben."""
        label = label.strip()
        if label.isdigit():
            label = f"Sprecher {label}"
        with self._lock:
            self.namen[label] = name.strip()
            self._datei_schreiben()

    def zusammenfassen(self, frage_modell) -> str:
        """frage_modell(prompt)->str wird mit dem Transkript aufgerufen (nur auf Wunsch; kostet Token)."""
        with self._lock:
            text = transkript_text(self.segmente, self.namen)
        if not text.strip():
            return "Es gibt noch nichts zu transkribieren."
        return frage_modell(zusammenfassung_prompt(text)) or ""

    # -- intern -------------------------------------------------------------
    def _datei_schreiben(self) -> None:
        try:
            titel = f"Mitschnitt - {self.status.quelle}, {self.status.minuten()} Min."
            Path(self.status.datei).write_text(transkript_text(self.segmente, self.namen, titel),
                                               encoding="utf-8")
        except OSError as exc:
            logger.warning("Transkript nicht geschrieben: %s", exc)

    def _laufen(self) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
            import sounddevice as sd  # type: ignore
        except Exception as exc:  # noqa: BLE001
            self.status.fehler = f"{INSTALL_HINWEIS} ({exc})"
            self.status.laeuft = False
            return
        try:
            self._whisper = WhisperModel("small", device="cpu", compute_type="int8")
        except Exception as exc:  # noqa: BLE001
            self.status.fehler = f"Whisper-Modell nicht ladbar: {exc}"
            self.status.laeuft = False
            return
        if self.status.quelle == "system" and diarisierung_moeglich():
            try:
                from resemblyzer import VoiceEncoder  # type: ignore
                self._diar = VoiceEncoder()
            except Exception:  # noqa: BLE001
                self._diar = None
        try:
            stream = self._stream_oeffnen(sd)
        except Exception as exc:  # noqa: BLE001
            self.status.fehler = f"Aufnahmequelle nicht verfuegbar ({self.status.quelle}): {exc}"
            self.status.laeuft = False
            return
        with stream:
            while not self._stop.is_set():
                pcm = self._chunk_lesen(stream)
                if pcm:
                    self._chunk_verarbeiten(pcm)
        self.status.laeuft = False

    def _stream_oeffnen(self, sd):
        """Mikrofon ODER System-Audio (WASAPI-Loopback des Standard-Ausgabegeraets)."""
        if self.status.quelle == "system":
            try:
                wasapi = sd.WasapiSettings(loopback=True)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("System-Audio (Loopback) wird hier nicht unterstuetzt - "
                                   "nimm 'mikrofon'.") from exc
            geraet = sd.default.device[1]  # Standard-Ausgabegeraet
            return sd.RawInputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16",
                                     device=geraet, extra_settings=wasapi)
        return sd.RawInputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16")

    def _chunk_lesen(self, stream) -> bytes:
        """Liest ~chunk_sekunden Audio (oder bis Stopp). Startet den Stream beim ersten Mal."""
        if not getattr(stream, "active", False):
            stream.start()
        frames, gelesen, ziel = [], 0, int(_SAMPLE_RATE * self.chunk_sekunden)
        while gelesen < ziel and not self._stop.is_set():
            daten, _ = stream.read(min(_SAMPLE_RATE // 4, ziel - gelesen))
            roh = bytes(daten)
            frames.append(roh)
            gelesen += len(roh) // 2
        return b"".join(frames)

    def _chunk_verarbeiten(self, pcm: bytes) -> None:
        import tempfile
        import wave
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pfad = Path(tmp) / "chunk.wav"
                with wave.open(str(pfad), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(_SAMPLE_RATE)
                    w.writeframes(pcm)
                from .geheimnisse import verschleiere

                segs, _info = self._whisper.transcribe(str(pfad), language=self.sprache, vad_filter=True)
                basis = time.time() - self.status.start - self.chunk_sekunden
                f0 = _f0_schaetzen(pcm)
                neu = []
                for s in segs:
                    # Passwoerter/Schluessel, die jemand laut vorliest, NICHT ins Transkript schreiben.
                    t = verschleiere((s.text or "").strip())
                    if t:
                        neu.append(Segment(start=max(0.0, basis + s.start), ende=basis + s.end,
                                           text=t, sprecher="Sprecher 1",
                                           geschlecht=geschlecht_aus_tonhoehe(f0)))
                if neu:
                    with self._lock:
                        self.segmente.extend(neu)
                        self.status.segmente = len(self.segmente)
                        self.status.letzte = neu[-1].text[:200]
                        self._datei_schreiben()
        except Exception as exc:  # noqa: BLE001 - ein kaputtes Haeppchen darf die Aufnahme nicht beenden
            logger.warning("Chunk nicht transkribiert: %s", type(exc).__name__)
