"""Optionale Sprachein- und -ausgabe.

Beides ist bewusst optional und faellt sauber zurueck, wenn die Pakete fehlen -
die KI laeuft dann einfach per Tastatur weiter.

  Spracheingabe:  SpeechRecognition (+ Mikrofon)  -> Text
  Sprachausgabe:  pyttsx3 (offline)               -> Stimme
"""
from __future__ import annotations

from .logging_setup import get_logger

logger = get_logger()


class VoiceOutput:
    """Spricht Text vor - mit der gewaehlten Stimme (kostenlos oder realistisch).

    Baut je nach Einstellung die passende Stimme (build_speaker): die kostenlose
    Computerstimme (pyttsx3) oder eine realistische Cloud-Stimme (OpenAI/ElevenLabs).
    Ohne 'settings' bleibt es die kostenlose Stimme (Rueckwaertskompatibilitaet)."""

    def __init__(self, enabled: bool = False, settings=None, keys: dict | None = None):
        self.enabled = enabled
        self._speaker = None
        if enabled:
            try:
                self._speaker = build_speaker(settings or _FreieStimme(), keys)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sprachausgabe nicht verfuegbar: %s", exc)
            if not self._speaker or not getattr(self._speaker, "available", False):
                self.enabled = False

    def stop(self) -> None:
        try:
            if self._speaker:
                self._speaker.stop()
        except Exception:  # noqa: BLE001
            pass

    def speak(self, text: str) -> None:
        if not self.enabled or not self._speaker or not text.strip():
            return
        try:
            self._speaker.speak(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sprachausgabe-Fehler: %s", exc)


class _FreieStimme:
    """Mini-Einstellung, wenn VoiceOutput ohne config gebaut wird: immer die freie Stimme."""
    stimme = "frei"
    sprache = "de"


class VoiceInput:
    """Nimmt gesprochene Sprache auf und wandelt sie in Text (via SpeechRecognition)."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._recognizer = None
        self._mic = None
        if enabled:
            try:
                import speech_recognition as sr

                self._recognizer = sr.Recognizer()
                self._mic = sr.Microphone()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Spracheingabe nicht verfuegbar: %s", exc)
                self.enabled = False

    def available(self) -> bool:
        return self.enabled and self._recognizer is not None and self._mic is not None

    def listen(self, language: str = "de-DE") -> str | None:
        """Hoert einmal zu und gibt den erkannten Text zurueck (oder None)."""
        if not self.available():
            return None
        import speech_recognition as sr

        try:
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self._recognizer.listen(source, timeout=8, phrase_time_limit=20)
            return self._recognizer.recognize_google(audio, language=language)
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Spracherkennung-Fehler: %s", exc)
            return None


# ---------------------------------------------------------------------------
#  Freie Aufnahme fuer die Sprechtaste (F2): Start/Stopp per Taste, beliebig lang.
# ---------------------------------------------------------------------------
VOICE_PACKAGES = ["sounddevice", "SpeechRecognition"]
_SAMPLE_RATE = 16_000


def pcm_als_float(pcm: bytes):
    """16-Bit-Aufnahme (Mono, 16 kHz) -> float32-Array (-1..1) fuer faster-whisper. So bekommt Whisper die
    Aufnahme direkt und braucht kein PyAV zum Einlesen einer Datei - neuere PyAV-Versionen kennen das von
    faster-whisper genutzte 'metadata_errors' nicht mehr ("open() got an unexpected keyword argument")."""
    import numpy as np

    return np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype=np.int16).astype(np.float32) / 32768.0
_CHUNK_SECONDS = 30  # Google nimmt nur kurze Stuecke - laengere Aufnahmen werden geteilt


class VoiceError(Exception):
    """Aufnahme oder Erkennung ging schief - mit verstaendlicher Meldung."""


def _importable(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class VoiceCapture:
    """Nimmt vom Mikrofon auf, bis stop() kommt, und wandelt das Gesagte in Text."""

    def __init__(self, settings):
        self.settings = settings
        self._stream = None
        self._frames: list[bytes] = []
        self._whisper = None
        self.on_level = None   # z.B. die App: Sphaere reagiert auf deine Stimme (0..1, ~10x pro Sekunde)
        self._level_at = 0.0

    # -- Verfuegbarkeit -----------------------------------------------------
    def backend(self) -> str | None:
        wanted = (self.settings.erkennung or "auto").strip().lower()
        has_whisper = _importable("faster_whisper")
        has_google = _importable("speech_recognition")
        if wanted == "whisper":
            return "whisper" if has_whisper else None
        if wanted == "google":
            return "google" if has_google else None
        # "auto": Google zuerst - schnell, ohne Modell-Download, so wie es immer lief. Whisper nur, wenn
        # Google fehlt (seit 0.27.1 steckt faster-whisper fuer den Mitschnitt in der .exe - es soll die
        # Spracheingabe nicht stillschweigend auf einen 460-MB-Download umstellen).
        return "google" if has_google else ("whisper" if has_whisper else None)

    def problem(self) -> str | None:
        """None, wenn alles bereit ist - sonst eine Erklaerung fuer den Menschen."""
        missing = []
        if not _importable("sounddevice"):
            missing.append("sounddevice")
        if self.backend() is None:
            wanted = (self.settings.erkennung or "auto").strip().lower()
            missing.append("faster-whisper" if wanted == "whisper" else "SpeechRecognition")
        if not missing:
            return None
        import sys

        if getattr(sys, "frozen", False):
            return "Die Spracheingabe ist in dieser KI.exe nicht enthalten (fehlt: " + ", ".join(missing) + ")."
        return (
            "Die Spracheingabe ist noch nicht eingerichtet (fehlt: " + ", ".join(missing) + "). "
            "Tippe /sprache einrichten - das installiert alles Noetige."
        )

    def packages(self) -> list[str]:
        """Was /sprache einrichten installiert - passend zur eingestellten Erkennung."""
        wanted = (self.settings.erkennung or "auto").strip().lower()
        return ["sounddevice", "faster-whisper" if wanted == "whisper" else "SpeechRecognition"]

    def warm_up(self) -> None:
        """Laedt die Mikrofon-Bibliothek vorab (sonst dauert der erste F2-Druck)."""
        try:
            if _importable("sounddevice"):
                import sounddevice  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            logger.info("Mikrofon-Vorbereitung: %s", exc)

    # -- Aufnahme -----------------------------------------------------------
    def start(self) -> None:
        try:
            import sounddevice as sd

            self._frames = []
            self._stream = sd.RawInputStream(
                samplerate=_SAMPLE_RATE, channels=1, dtype="int16", callback=self._on_audio
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - kein Mikrofon, Treiber, ...
            self._stream = None
            raise VoiceError(f"Mikrofon konnte nicht gestartet werden: {exc}") from exc

    def _on_audio(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        data = bytes(indata)
        self._frames.append(data)
        if self.on_level is not None:
            import time

            now = time.monotonic()
            if now - self._level_at >= 0.1:
                self._level_at = now
                try:
                    self.on_level(round(min(1.0, _rms(data) / 3000.0), 3))
                except Exception:  # noqa: BLE001 - Anzeige darf die Aufnahme nie stoeren
                    pass

    def seconds(self) -> float:
        return sum(len(f) for f in self._frames) / (2 * _SAMPLE_RATE)

    def _close(self) -> bytes:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        audio, self._frames = b"".join(self._frames), []
        return audio

    def cancel(self) -> None:
        self._close()

    def stop(self) -> str:
        """Beendet die Aufnahme und gibt den erkannten Text zurueck ("" = nichts)."""
        audio = self._close()
        if len(audio) < 2 * _SAMPLE_RATE // 3:  # unter ~0,3 s: versehentlich gedrueckt
            return ""
        return self.transcribe(audio)

    # -- Erkennung ----------------------------------------------------------
    def transcribe(self, pcm: bytes) -> str:
        backend = self.backend()
        if backend == "whisper":
            return self._transcribe_whisper(pcm)
        if backend == "google":
            return self._transcribe_google(pcm)
        raise VoiceError(self.problem() or "Keine Spracherkennung verfuegbar.")

    def _transcribe_whisper(self, pcm: bytes) -> str:
        if self._whisper is None:
            from faster_whisper import WhisperModel  # type: ignore

            # Beim allerersten Mal wird das Modell heruntergeladen (einige 100 MB).
            self._whisper = WhisperModel(self.settings.whisper_modell or "small", device="cpu", compute_type="int8")
        segments, _info = self._whisper.transcribe(
            pcm_als_float(pcm), language=self.settings.sprache or "de", vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def _transcribe_google(self, pcm: bytes) -> str:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.operation_timeout = 20  # sonst haengt es ohne Internet endlos
        lang = self.settings.sprache or "de"
        language = f"{lang}-{lang.upper()}" if len(lang) == 2 else lang
        texts: list[str] = []
        failed = 0
        last_error: Exception | None = None
        for chunk in split_audio(pcm):
            audio = sr.AudioData(chunk, _SAMPLE_RATE, 2)
            for attempt in (1, 2):  # ein kurzer Aussetzer soll nicht alles kosten
                try:
                    texts.append(recognizer.recognize_google(audio, language=language))
                    break
                except sr.UnknownValueError:
                    break  # in diesem Stueck nichts verstanden
                except (sr.RequestError, OSError) as exc:
                    if "FLAC" in str(exc):
                        raise VoiceError(
                            "Fuer die Google-Erkennung fehlt auf diesem Computer das Programm 'flac' "
                            "(z.B. Windows auf ARM). Alternative: [voice] erkennung = \"whisper\"."
                        ) from exc
                    last_error = exc
                    if attempt == 2:
                        failed += 1
                        texts.append("[…]")
        text = " ".join(t.strip() for t in texts if t).strip()
        if failed and not text.replace("[…]", "").strip():
            raise VoiceError(f"Google-Spracherkennung nicht erreichbar (Internet?): {last_error}")
        if failed:
            logger.warning("%d Teil(e) der Aufnahme nicht erkannt: %s", failed, last_error)
        return text


def split_audio(pcm: bytes, max_seconds: int = _CHUNK_SECONDS) -> list[bytes]:
    """Teilt lange Aufnahmen in Stuecke - moeglichst an leisen Stellen (Sprechpausen)."""
    from array import array

    bytes_per_second = 2 * _SAMPLE_RATE
    max_len = max_seconds * bytes_per_second
    if len(pcm) <= max_len:
        return [pcm]
    window = bytes_per_second // 10  # 100-ms-Fenster
    chunks, start = [], 0
    while len(pcm) - start > max_len:
        # In den letzten 5 Sekunden des Stuecks die leiseste Stelle suchen.
        search_from = start + max_len - 5 * bytes_per_second
        best_pos, best_energy = start + max_len, None
        for pos in range(search_from, start + max_len - window + 1, window):
            samples = array("h", pcm[pos : pos + window])
            energy = sum(abs(s) for s in samples)
            if best_energy is None or energy < best_energy:
                best_pos, best_energy = pos + window // 2, energy
        best_pos -= best_pos % 2  # nie mitten in einem 16-bit-Wert teilen
        chunks.append(pcm[start:best_pos])
        start = best_pos
    chunks.append(pcm[start:])
    return chunks


def install_voice_packages(run=None, packages: list[str] | None = None) -> tuple[bool, str]:
    """Installiert Pakete fuer Sprache (pip, in die laufende Umgebung)."""
    import subprocess
    import sys

    if getattr(sys, "frozen", False):
        return False, "In der KI.exe koennen keine Pakete nachinstalliert werden."
    run = run or subprocess.run
    result = run(
        [sys.executable, "-m", "pip", "install", *(packages or VOICE_PACKAGES)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = "\n".join(((result.stdout or "") + (result.stderr or "")).splitlines()[-6:])
        return False, "Installation fehlgeschlagen:\n" + tail
    import importlib
    import site

    importlib.invalidate_caches()
    # .pth-Dateien neuer Pakete (z.B. pywin32 fuer pyttsx3) wirken sonst erst nach
    # einem Neustart.
    for path in list(sys.path):
        if path.rstrip("/\\").endswith("site-packages"):
            site.addsitedir(path)
    return True, "Installiert."


# ---------------------------------------------------------------------------
#  Jarvis-Modus: freihaendig zuhoeren (Sprechpausen-Erkennung) und vorlesen
# ---------------------------------------------------------------------------
_BLOCK = 1600  # 100 ms bei 16 kHz


def _rms(block: bytes) -> float:
    from array import array

    samples = array("h", block)
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def listen_utterance(on_level=None, stop_event=None, max_seconds: float = 40.0, silence: float = 1.0,
                     start_timeout: float | None = None, sd_module=None) -> bytes | None:
    """Wartet, bis jemand spricht, und nimmt auf, bis eine Sprechpause kommt.

    Gibt die Aufnahme (16 kHz, 16 bit, mono) zurueck, b"" wenn in start_timeout
    niemand gesprochen hat, oder None, wenn stop_event gesetzt wurde. on_level(0..1)
    bekommt etwa 10-mal pro Sekunde die Lautstaerke (fuer die Anzeige).
    """
    import queue as queue_mod
    import time
    from collections import deque
    from statistics import median

    sd = sd_module
    if sd is None:
        import sounddevice as sd  # type: ignore

    blocks: queue_mod.Queue = queue_mod.Queue()

    def callback(indata, frames, time_info, status):  # noqa: ARG001
        blocks.put(bytes(indata))

    noise: list[float] = []
    pre: deque = deque(maxlen=4)  # 400 ms vor dem ersten Laut mitnehmen
    voiced: list[bytes] = []
    speaking, loud, quiet = False, 0, 0
    began = last_block = time.monotonic()
    with sd.RawInputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16", blocksize=_BLOCK,
                           callback=callback):
        while True:
            if stop_event is not None and stop_event.is_set():
                return None
            try:
                block = blocks.get(timeout=0.5)
                last_block = time.monotonic()
            except queue_mod.Empty:
                # Kein Ton mehr vom Mikrofon (z.B. Headset abgezogen) oder niemand spricht.
                if speaking and time.monotonic() - last_block > 3:
                    return b"".join(voiced)
                if not speaking and start_timeout and time.monotonic() - began > start_timeout:
                    return b""
                if time.monotonic() - last_block > 10:
                    raise VoiceError("Vom Mikrofon kommt nichts an - ist es angeschlossen und erlaubt?")
                continue
            level = _rms(block)
            if len(noise) < 5 and not speaking:  # erste halbe Sekunde: Grundrauschen messen
                noise.append(level)
                pre.append(block)
                continue
            threshold = max(median(noise) * 2.5, 350.0)
            if on_level:
                on_level(min(1.0, level / (threshold * 4)))
            if not speaking:
                pre.append(block)
                loud = loud + 1 if level > threshold else 0
                if loud >= 2:
                    speaking, voiced, quiet = True, list(pre), 0
                    continue
                if level <= threshold:
                    noise = (noise + [level])[-30:]  # Raum wird leiser/lauter: nachfuehren
                if start_timeout and time.monotonic() - began > start_timeout:
                    return b""
            else:
                voiced.append(block)
                quiet = quiet + 1 if level < threshold * 0.8 else 0
                if quiet * 0.1 >= silence or len(voiced) * 0.1 >= max_seconds:
                    return b"".join(voiced)


def speech_text(markdown: str) -> str:
    """Macht aus einer Markdown-Antwort gut vorlesbaren Text."""
    import re

    text = re.sub(r"```.*?```", " (Code siehe Bildschirm) ", markdown, flags=re.S)
    text = re.sub(r"```.*", " (Code siehe Bildschirm) ", text, flags=re.S)  # noch offener Codeblock
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\|?[\s:\-|]+\|?", stripped) and "-" in stripped:
            continue  # Trennzeile einer Tabelle
        if stripped.startswith("|"):
            stripped = ", ".join(c.strip() for c in stripped.strip("|").split("|") if c.strip())
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)      # Links -> Linktext
    text = re.sub(r"https?://\S+", "(Link)", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)   # Ueberschriften
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)         # Aufzaehlungen
    text = re.sub(r"[*_~>#]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


class Speaker:
    """Vorlesen im Hintergrund (pyttsx3) - mit deutscher Stimme, wenn vorhanden.

    Ein eigener Thread besitzt die Sprach-Engine (unter Windows wichtig: SAPI mag
    keine Thread-Wechsel). say() reiht ein, stop() bricht ab, wait() wartet.
    """

    def __init__(self, language: str = "de"):
        import queue as queue_mod
        import threading

        self.language = language
        self._queue: queue_mod.Queue = queue_mod.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self._engine = None
        self.completed = 0      # fertig gesprochene Saetze (fuer den Jarvis-Modus)
        self._generation = 0    # stop() beginnt eine neue Zaehlung
        self._pending = 0       # eingereiht, noch nicht fertig
        self._lock = threading.Lock()
        self.available = _importable("pyttsx3")
        self._thread = threading.Thread(target=self._run, name="vorlesen", daemon=True) if self.available else None
        if self._thread:
            self._thread.start()

    def _pick_voice(self, engine) -> None:
        try:
            for voice in engine.getProperty("voices") or []:
                info = f"{voice.id} {voice.name} {getattr(voice, 'languages', '')}".lower()
                if any(k in info for k in (self.language, "german", "deutsch", "hedda", "katja", "stefan")):
                    engine.setProperty("voice", voice.id)
                    return
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._pick_voice(self._engine)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vorlesen nicht verfuegbar: %s", exc)
            self.available = False
            return
        while True:
            item = self._queue.get()
            if item is None:
                return
            generation, text = item
            with self._lock:
                if generation != self._generation:
                    continue  # nach stop() nichts Altes mehr sprechen
                try:
                    self._engine.say(text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Vorlese-Fehler: %s", exc)
            try:
                self._engine.runAndWait()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vorlese-Fehler: %s", exc)
            with self._lock:
                if generation == self._generation:
                    self.completed += 1
                    self._pending -= 1
                    if self._pending <= 0:
                        self._pending = 0
                        self._idle.set()

    def say(self, text: str) -> None:
        text = speech_text(text)
        if not text or not self.available:
            return
        with self._lock:
            self._pending += 1
            self._idle.clear()
            self._queue.put((self._generation, text))

    def speak(self, text: str) -> None:
        """Einfacher Weg (wie VoiceOutput): sprechen und warten, bis fertig."""
        self.say(text)
        self.wait()

    def wait(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            try:
                while not self._queue.empty():
                    self._queue.get_nowait()
            except Exception:  # noqa: BLE001
                pass
            self._pending = 0
            self._idle.set()
        try:
            if self._engine:
                self._engine.stop()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
#  Stimmen-Auswahl: kostenlos (Computerstimme) oder realistisch (kostet Geld)
# ---------------------------------------------------------------------------
# OpenAI-TTS: nutzt denselben Schluessel wie das ChatGPT-Gehirn (kein neues Konto).
# ACHTUNG: OpenAI hat /v1/audio/speech samt dieser Modelle zum 6.1.2027 abgekuendigt
# (Nachfolger: Realtime-API). Laeuft bis dahin; Modell hier bei Bedarf anpassen.
# Stand 20.11.2026 - regelmaessig pruefen (siehe docs/ENTWICKLUNG.md).
OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_TTS_MODELL = "gpt-4o-mini-tts"
OPENAI_TTS_STANDARD = "cedar"  # laut OpenAI mit "marin" die natuerlichsten Stimmen
OPENAI_TTS_STIMMEN = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx",
                      "sage", "shimmer", "verse", "marin", "cedar"]

# ElevenLabs: am natuerlichsten, eigener Schluessel (xi-api-key), kein Sunset.
ELEVEN_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/"
ELEVEN_VOICES_URL = "https://api.elevenlabs.io/v2/voices"
ELEVEN_MODELL = "eleven_multilingual_v2"  # gutes Deutsch, stabil fuer lange Texte

_TTS_RATE = 24_000  # OpenAI pcm und ElevenLabs pcm_24000 liefern 24 kHz, 16 bit, mono

STIMMEN = [
    {"id": "frei", "provider": "lokal", "name": "Frei (Computerstimme)", "kostenlos": True,
     "info": "die eingebaute Stimme deines PCs - gratis, offline, ohne Konto"},
    {"id": "openai", "provider": "openai", "name": "OpenAI (realistisch)", "kostenlos": False,
     "preis": "ca. 0,60 $ je 1 Mio. Zeichen-Tokens", "schluessel": "openai",
     "info": "natuerliche Stimme ueber deinen vorhandenen ChatGPT-Schluessel (guenstig)"},
    {"id": "elevenlabs", "provider": "elevenlabs", "name": "ElevenLabs (am echtesten)", "kostenlos": False,
     "preis": "ca. 0,08 $ je 1.000 Zeichen", "schluessel": "elevenlabs",
     "info": "die natuerlichste Stimme - braucht ein eigenes (kostenloses) ElevenLabs-Konto"},
]


def stimme_info(stimme: str) -> dict:
    s = (stimme or "frei").strip().lower()
    for eintrag in STIMMEN:
        if eintrag["id"] == s:
            return eintrag
    return STIMMEN[0]


class CloudSpeaker:
    """Realistische Stimme aus der Cloud (OpenAI oder ElevenLabs) - gleiche Schnittstelle
    wie Speaker (say/speak/wait/stop/completed), damit sie ueberall einsetzbar ist.

    Spielt rohes PCM (24 kHz) ueber sounddevice ab. Fehlt sounddevice oder der Schluessel,
    ist available=False - dann nimmt build_speaker() die kostenlose Stimme.
    """

    def __init__(self, provider: str, key: str, settings, language: str = "de", http=None):
        import queue as queue_mod
        import threading

        self.provider = provider
        self.key = key or ""
        self.settings = settings
        self.language = language
        self._http = http  # fuer Tests: (url, daten_bytes, header) -> pcm_bytes
        self._queue: queue_mod.Queue = queue_mod.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self.completed = 0
        self._generation = 0
        self._pending = 0
        self._stop = False
        self._lock = threading.Lock()
        self._stream = None
        self._voice_id = (getattr(settings, "stimme_name", "") or "").strip()
        self.available = bool(self.key) and (self._http is not None or _importable("sounddevice"))
        self._thread = None
        if self.available:
            self._thread = threading.Thread(target=self._run, name="stimme-cloud", daemon=True)
            self._thread.start()

    # -- Audio holen --------------------------------------------------------
    def _request(self, url: str, body: dict, headers: dict) -> bytes:
        import json
        data = json.dumps(body).encode("utf-8")
        if self._http is not None:
            return self._http(url, data, headers)
        import urllib.request
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def _synthesize(self, text: str) -> bytes:
        tempo = float(getattr(self.settings, "stimme_tempo", 1.0) or 1.0)
        if self.provider == "openai":
            body = {
                "model": (getattr(self.settings, "stimme_modell", "") or OPENAI_TTS_MODELL),
                "input": text,
                "voice": self._voice_id or OPENAI_TTS_STANDARD,
                "response_format": "pcm",
            }
            anweisung = (getattr(self.settings, "stimme_anweisung", "") or "").strip()
            if anweisung:
                body["instructions"] = anweisung
            headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
            return self._request(OPENAI_TTS_URL, body, headers)
        # ElevenLabs
        voice_id = self._voice_id or self._eleven_default_voice()
        body = {
            "text": text,
            "model_id": (getattr(self.settings, "stimme_modell", "") or ELEVEN_MODELL),
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": tempo},
        }
        headers = {"xi-api-key": self.key, "Content-Type": "application/json"}
        url = f"{ELEVEN_TTS_URL}{voice_id}?output_format=pcm_24000"
        return self._request(url, body, headers)

    def _eleven_default_voice(self) -> str:
        """Ohne gewaehlte Stimme die erste des Kontos nehmen (einmal holen, dann merken)."""
        if self._voice_id:
            return self._voice_id
        try:
            import json
            import urllib.request
            req = urllib.request.Request(ELEVEN_VOICES_URL, headers={"xi-api-key": self.key})
            with urllib.request.urlopen(req, timeout=15) as resp:
                voices = json.loads(resp.read().decode("utf-8")).get("voices") or []
            if voices:
                self._voice_id = voices[0].get("voice_id", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ElevenLabs-Stimmen nicht abrufbar: %s", exc)
        return self._voice_id or "21m00Tcm4TlvDq8ikWAM"  # letzter Ausweg (oeffentliche Standardstimme)

    # -- Abspielen ----------------------------------------------------------
    def _play(self, pcm: bytes) -> None:
        if not pcm or self._http is not None:  # im Test nicht wirklich abspielen
            return
        import sounddevice as sd
        self._stream = sd.RawOutputStream(samplerate=_TTS_RATE, channels=1, dtype="int16")
        try:
            self._stream.start()
            block = 2 * _TTS_RATE  # ~1 s Haeppchen, damit stop() schnell greift
            for i in range(0, len(pcm), block):
                if self._stop:
                    break
                self._stream.write(pcm[i:i + block])
        finally:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            generation, text = item
            if generation != self._generation:
                continue
            try:
                self._stop = False
                pcm = self._synthesize(text)
                if generation == self._generation and not self._stop:
                    self._play(pcm)
            except Exception as exc:  # noqa: BLE001 - lieber still bleiben als abstuerzen
                logger.warning("Cloud-Stimme (%s) ging nicht: %s", self.provider, exc)
            with self._lock:
                if generation == self._generation:
                    self.completed += 1
                    self._pending -= 1
                    if self._pending <= 0:
                        self._pending = 0
                        self._idle.set()

    # -- gleiche Schnittstelle wie Speaker ----------------------------------
    def say(self, text: str) -> None:
        text = speech_text(text)
        if not text or not self.available:
            return
        with self._lock:
            self._pending += 1
            self._idle.clear()
            self._queue.put((self._generation, text))

    def speak(self, text: str) -> None:
        self.say(text)
        self.wait()

    def wait(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._stop = True
            try:
                while not self._queue.empty():
                    self._queue.get_nowait()
            except Exception:  # noqa: BLE001
                pass
            self._pending = 0
            self._idle.set()
        try:
            if self._stream is not None:
                self._stream.abort()
        except Exception:  # noqa: BLE001
            pass


def build_speaker(settings, keys: dict | None = None, language: str = "de", http=None):
    """Baut die passende Stimme: realistisch (OpenAI/ElevenLabs) wenn gewaehlt UND Schluessel da,
    sonst die kostenlose Computerstimme. Faellt immer sauber auf 'frei' zurueck."""
    keys = keys or {}
    stimme = (getattr(settings, "stimme", "") or "frei").strip().lower()
    provider = {"chatgpt": "openai", "eleven": "elevenlabs", "11labs": "elevenlabs"}.get(stimme, stimme)
    if provider in ("openai", "elevenlabs"):
        key = keys.get(provider)
        if key:
            spk = CloudSpeaker(provider, key, settings, language, http=http)
            if spk.available:
                return spk
    return Speaker(language)
