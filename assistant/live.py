"""Live-Sprachmodus (Jarvis): reden wie im Gespraech - so schnell wie moeglich.

Was ihn schnell macht:
  * Das Mikrofon bleibt die ganze Zeit offen (kein Neustart pro Satz).
  * Vosk schreibt offline mit, WAEHREND du sprichst (deutsches Modell, ~45 MB,
    wird beim ersten Mal geladen). Ist der Satz zu Ende, liegt der Text sofort vor.
  * Schon nach einer kurzen Sprechpause (Standard 0,6 s) geht es los - endet
    der Satz auf "und", "weil" o.ae., wartet sie etwas laenger.
  * Nova spricht Satz fuer Satz, sobald der erste Satz fertig ist - nicht erst,
    wenn die ganze Antwort da ist.
  * Redest du dazwischen, hoert sie sofort auf zu sprechen und hoert dir zu.
  * Sagst du kurz danach noch etwas ("... in Berlin"), wird es an die Frage
    angehaengt, solange Nova noch nichts gesagt oder getan hat.

Ganz ohne Wartezeit wie bei Gemini Live geht es nicht: DeepSeek und Claude
verstehen nur Text. Es bleibt also: Sprache -> Text -> Nachdenken -> Sprache.

Aufbau:
  SentenceSplitter - schneidet den Antwort-Strom in vorlesbare Saetze
  LiveRecognizer   - Vosk: Text schon waehrend des Sprechens
  Ear              - hoert durchgehend zu (Sprechbeginn, -ende, Dazwischenreden)
  LiveLoop         - das Gespraech: zuhoeren, antworten, vorlesen, unterbrechen
Die Oberflaeche (App oder Terminal) haengt sich als "host" an LiveLoop.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from .anzeige import schoen
from .logging_setup import get_logger
from .voice import _importable, _rms, speech_text

logger = get_logger()

RATE = 16_000
BLOCK = 800  # 50 ms - kurze Bloecke = schnelle Reaktion

# ---------------------------------------------------------------------------
#  Saetze aus dem Antwort-Strom schneiden
# ---------------------------------------------------------------------------
_ABBREVIATIONS = {
    "z.b", "z. b", "d.h", "u.a", "o.ae", "o.\u00e4", "bzw", "ca", "dr", "nr", "usw", "evtl", "ggf", "inkl", "bspw",
    "vgl", "etc", "prof", "str", "tel", "mind", "max", "min", "mio", "mrd", "sog", "jh", "s", "u", "z", "v",
    "e.g", "i.e", "mr", "mrs", "vs",
}
_END = re.compile(r"[.!?\u2026]+[\"'\u00bb\u00ab\u201c\u201d)\]]*(?=\s)")
_TOOL_MARK = re.compile(r"(\u2026 nutze Werkzeug:|>> Agent '|<< Agent '|^\s*\[Ich arbeite weiter)")


class SentenceSplitter:
    """Nimmt Text-Stuecke an und gibt fertige, vorlesbare Saetze zurueck.

    Der erste Satz kommt so frueh wie moeglich (damit Nova sofort loslegt),
    spaetere werden zu etwas laengeren Stuecken zusammengefasst (weniger Pausen
    zwischen den Saetzen). Code-Bloecke werden nicht vorgelesen.
    """

    def __init__(self, min_len: int = 60, max_len: int = 260):
        self.min_len, self.max_len = min_len, max_len
        self.buf = ""
        self.pending = ""
        self.count = 0

    def feed(self, text: str) -> list[str]:
        self.buf += text
        return self._collect(self._cut(final=False), final=False)

    def flush(self) -> list[str]:
        """Alles Restliche (Ende der Antwort oder bevor ein Werkzeug laeuft)."""
        return self._collect(self._cut(final=True), final=True)

    def _collect(self, pieces: list[str], final: bool) -> list[str]:
        out = []
        for piece in pieces:
            spoken = speech_text(piece)
            if not spoken or not re.search(r"\w", spoken):
                continue
            if self.count == 0 and not out and not self.pending:
                out.append(spoken)  # erster Satz: sofort
                continue
            self.pending = f"{self.pending} {spoken}".strip()
            if len(self.pending) >= self.min_len:
                out.append(self.pending)
                self.pending = ""
        if final and self.pending:
            out.append(self.pending)
            self.pending = ""
        self.count += len(out)
        return out

    def _cut(self, final: bool) -> list[str]:
        out: list[str] = []
        while True:
            fence = self.buf.find("```")
            head = self.buf if fence < 0 else self.buf[:fence]
            sentences, rest = self._split(head, final=final or fence >= 0)
            out += sentences
            if fence < 0:
                self.buf = rest
                return out
            close = self.buf.find("```", fence + 3)
            if close < 0:
                if final:
                    out.append("Den Code siehst du auf dem Bildschirm.")
                    self.buf = ""
                else:
                    self.buf = self.buf[fence:]  # auf das Ende des Code-Blocks warten
                return out
            out.append("Den Code siehst du auf dem Bildschirm.")
            self.buf = self.buf[close + 3:]

    def _split(self, text: str, final: bool) -> tuple[list[str], str]:
        out: list[str] = []
        start = 0
        for match in re.finditer(r"\n|" + _END.pattern, text):
            end = match.end()
            if match.group() != "\n":
                word = re.search(r"(\S+)$", text[start:match.start()])
                token = (word.group(1) if word else "").lower()
                if match.group().startswith(".") and (token.rstrip(".") in _ABBREVIATIONS or token.isdigit()
                                                      or re.fullmatch(r"[a-z\u00e4\u00f6\u00fc]", token)):
                    continue  # "z.B.", "3. Mai", "A. Meier" - kein Satzende
            piece = text[start:end].strip()
            start = end
            if piece:
                out.append(piece)
        rest = text[start:]
        if final:
            if rest.strip():
                out.append(rest.strip())
            return out, ""
        if len(rest) > self.max_len:  # sehr langer Satz ohne Punkt: an einem Komma teilen
            cut = max(rest.rfind(", ", 0, self.max_len), rest.rfind(" ", 0, self.max_len))
            if cut > 0:
                out.append(rest[:cut + 1].strip())
                rest = rest[cut + 1:]
        return out, rest


def split_tool_lines(chunk: str) -> tuple[str, bool]:
    """Trennt Werkzeug-/Agenten-Zeilen vom Antworttext. -> (Text, Werkzeug lief)"""
    if not _TOOL_MARK.search(chunk):
        return chunk, False
    keep = [line for line in chunk.split("\n") if not _TOOL_MARK.search(line)]
    return "\n".join(keep), True


# ---------------------------------------------------------------------------
#  Vosk: Mitschrift waehrend des Sprechens
# ---------------------------------------------------------------------------
VOSK_MODELS = {
    "de": "vosk-model-small-de-0.15",
    "en": "vosk-model-small-en-us-0.15",
    "fr": "vosk-model-small-fr-0.22",
    "es": "vosk-model-small-es-0.42",
    "it": "vosk-model-small-it-0.22",
    "nl": "vosk-model-small-nl-0.22",
}
MODEL_URL = "https://alphacephei.com/vosk/models/{name}.zip"
_MODEL_CACHE: dict[str, object] = {}
_MODEL_LOCK = threading.Lock()


def models_dir(root: Path) -> Path:
    return Path(root) / "data" / "sprachmodelle"


def model_name(settings) -> str:
    custom = (getattr(settings, "live_modell", "") or "").strip()
    if custom:
        return custom
    lang = (getattr(settings, "sprache", "de") or "de").strip().lower()[:2]
    return VOSK_MODELS.get(lang, VOSK_MODELS["de"])


def model_path(root: Path, settings) -> Path:
    name = model_name(settings)
    path = Path(name)
    return path if path.is_absolute() else models_dir(root) / name


def model_ready(root: Path, settings) -> bool:
    path = model_path(root, settings)
    return path.is_dir() and any((path / sub).exists() for sub in ("am", "conf", "graph", "final.mdl"))


def live_available(root: Path, settings) -> bool:
    """Vosk installiert und Modell da?"""
    return bool(getattr(settings, "live_mitschrift", True)) and _importable("vosk") and model_ready(root, settings)


def setup_live(root: Path, settings, progress=None, install=None) -> tuple[bool, str]:
    """Richtet die Live-Mitschrift ein: Paket vosk + Sprachmodell (einmalig ~50 MB)."""
    import importlib
    import sys

    if not getattr(settings, "live_mitschrift", True):
        return False, "Die Live-Mitschrift ist ausgeschaltet ([voice] live_mitschrift = false)."
    if not _importable("vosk"):
        if getattr(sys, "frozen", False):
            return False, "In der KI.exe ist die Live-Mitschrift nicht enthalten."
        if install is None:
            from .voice import install_voice_packages as install
        ok, message = install(packages=["vosk"])
        if not ok:  # vosk braucht "srt" - das baut manches pip nur mit dieser Option
            ok, message = install(packages=["--use-pep517", "vosk"])
        importlib.invalidate_caches()
        if not ok:
            return False, message
        if not _importable("vosk"):
            return False, "vosk ist installiert, laesst sich aber erst nach einem Neustart der KI laden."
    if not model_ready(root, settings):
        try:
            download_model(root, settings, progress=progress)
        except Exception as exc:  # noqa: BLE001 - kein Internet o.ae.
            return False, f"Das Sprachmodell fuer die Live-Mitschrift konnte nicht geladen werden: {exc}"
    return True, "Die Live-Mitschrift ist bereit: Ich schreibe mit, waehrend du sprichst."


def recognizer_factory(root: Path, settings):
    """Fuer LiveLoop: erzeugt den Vosk-Erkenner im Hintergrund - oder None, wenn es keinen gibt."""
    if not live_available(root, settings):
        return None
    path = model_path(root, settings)
    return lambda: LiveRecognizer(path)


def download_model(root: Path, settings, progress=None, urlopen=None) -> Path:
    """Laedt das Vosk-Modell nach data/sprachmodelle (einmalig, ~45 MB)."""
    import shutil
    import tempfile
    import urllib.request

    target = model_path(root, settings)
    if model_ready(root, settings):
        return target
    name = target.name
    url = MODEL_URL.format(name=name)
    base = models_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    opener = urlopen or urllib.request.urlopen
    with tempfile.TemporaryDirectory(dir=base) as tmp:
        archive = Path(tmp) / f"{name}.zip"
        with opener(url, timeout=30) as response, archive.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0) if hasattr(response, "headers") else 0
            done = 0
            while True:
                data = response.read(256 * 1024)
                if not data:
                    break
                out.write(data)
                done += len(data)
                if progress:
                    progress(done, total)
        unpack = Path(tmp) / "entpackt"
        with zipfile.ZipFile(archive) as zf:
            root_dir = unpack.resolve()
            for member in zf.infolist():
                dest = (unpack / member.filename).resolve()
                if root_dir not in dest.parents and dest != root_dir:
                    raise OSError(f"Unsicherer Pfad im Sprachmodell: {member.filename}")
            zf.extractall(unpack)
        found = unpack / name
        if not found.is_dir():
            dirs = [d for d in unpack.iterdir() if d.is_dir()]
            if len(dirs) != 1:
                raise OSError("Das Sprachmodell hat einen unerwarteten Aufbau.")
            found = dirs[0]
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(found), str(target))
    return target


class LiveRecognizer:
    """Vosk-Erkenner: feed() liefert den Text bis jetzt, finish() den fertigen Satz."""

    def __init__(self, path: Path, vosk_module=None):
        vosk = vosk_module
        if vosk is None:
            import vosk  # type: ignore
        self._vosk = vosk
        key = str(path)
        with _MODEL_LOCK:
            model = _MODEL_CACHE.get(key)
            if model is None:
                try:
                    vosk.SetLogLevel(-1)
                except Exception:  # noqa: BLE001
                    pass
                model = vosk.Model(key)
                _MODEL_CACHE[key] = model
        self._model = model
        self._done: list[str] = []
        self._rec = vosk.KaldiRecognizer(model, RATE)

    def reset(self) -> None:
        self._done = []
        if hasattr(self._rec, "Reset"):
            self._rec.Reset()
        else:
            self._rec = self._vosk.KaldiRecognizer(self._model, RATE)

    def feed(self, pcm: bytes) -> str:
        if self._rec.AcceptWaveform(pcm):
            text = json.loads(self._rec.Result() or "{}").get("text", "")
            if text:
                self._done.append(text)
            partial = ""
        else:
            partial = json.loads(self._rec.PartialResult() or "{}").get("partial", "")
        return " ".join([*self._done, partial]).strip()

    def finish(self) -> str:
        text = json.loads(self._rec.FinalResult() or "{}").get("text", "")
        if text:
            self._done.append(text)
        result = " ".join(self._done).strip()
        self.reset()
        return result


def tidy(text: str) -> str:
    """Vosk schreibt alles klein und ohne Satzzeichen - fuer die Anzeige etwas schoener."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:1].upper() + text[1:] if text else ""


# ---------------------------------------------------------------------------
#  Durchgehend zuhoeren
# ---------------------------------------------------------------------------
_GOES_ON = {
    "und", "oder", "aber", "weil", "dass", "ob", "wenn", "als", "denn", "sondern", "also", "der", "die", "das",
    "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "mit", "in", "im", "zu", "zum", "zur", "von",
    "vom", "fuer", "f\u00fcr", "auf", "an", "am", "bei", "nach", "aus", "um", "mein", "meine", "meinen", "dein", "deine",
    "ich", "du", "wir", "bitte", "\u00e4h", "\u00e4hm", "hm", "and", "or", "but", "the", "a", "to", "of",
}


def _unfinished(text: str) -> bool:
    """Endet die Mitschrift mit einem Wort, nach dem sicher noch etwas kommt?"""
    words = (text or "").lower().split()
    return bool(words) and words[-1] in _GOES_ON


def _echo_limit(echo) -> float:
    """Ab dieser Lautstaerke ist es nicht mehr nur Novas Stimme aus dem Lautsprecher."""
    if not echo:
        return 0.0
    values = sorted(echo)
    p90 = values[min(len(values) - 1, int(len(values) * 0.9))]
    return max(p90 * 1.5, median(values) * 3.0)


@dataclass
class Utterance:
    text: str | None   # None = ohne Live-Erkennung -> erst noch umwandeln
    pcm: bytes
    seconds: float


class Ear:
    """Hoert durchgehend zu und meldet ueber post(art, daten):

      ("onset", None)        - jemand faengt an zu sprechen
      ("partial", text)      - Mitschrift bis jetzt (nur mit Vosk)
      ("utterance", Utterance) - Satz zu Ende (nach `pause` Sekunden Stille)
      ("dropped", None)      - war nur ein Geraeusch
      ("barge", None)        - Dazwischenreden, waehrend Nova spricht
      ("level", 0..1)        - Lautstaerke (~10x pro Sekunde)
      ("error", text)        - Mikrofon-Problem (das Zuhoeren endet)
    """

    def __init__(self, post, pause: float = 0.6, barge_in: bool = True, max_seconds: float = 40.0,
                 recognizer_factory=None, sd_module=None):
        self.post = post
        self.pause = max(0.3, float(pause or 0.6))
        self.barge_in = barge_in
        self.max_seconds = max_seconds
        self._factory = recognizer_factory
        self._recognizer = None
        self._sd = sd_module
        self._stop = threading.Event()
        self._nova = threading.Event()  # Nova spricht gerade
        self._thread: threading.Thread | None = None
        self.ready = threading.Event()  # Mikrofon laeuft

    # -- Steuerung -----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="zuhoeren", daemon=True)
        self._thread.start()
        if self._factory is not None:
            threading.Thread(target=self._load_recognizer, name="vosk-laden", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def set_nova_speaking(self, speaking: bool) -> None:
        if speaking:
            self._nova.set()
        else:
            self._nova.clear()

    @property
    def live(self) -> bool:
        return self._recognizer is not None

    def enable_live(self, factory) -> None:
        """Live-Mitschrift einschalten, sobald sie eingerichtet ist (ab dem naechsten Satz)."""
        if factory is not None and self._recognizer is None:
            self._factory = factory
            threading.Thread(target=self._load_recognizer, name="vosk-laden", daemon=True).start()

    def _load_recognizer(self) -> None:
        try:
            self._recognizer = self._factory()
        except Exception as exc:  # noqa: BLE001 - dann eben ohne Live-Mitschrift
            logger.warning("Live-Erkennung (Vosk) nicht verfuegbar: %s", exc)

    # -- Zuhoeren ------------------------------------------------------------
    def _run(self) -> None:
        sd = self._sd
        try:
            if sd is None:
                import sounddevice as sd  # type: ignore
            blocks: queue.Queue = queue.Queue()

            def callback(indata, frames, time_info, status):  # noqa: ARG001
                blocks.put(bytes(indata))

            with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK, callback=callback):
                self.ready.set()
                self._listen(blocks)
        except Exception as exc:  # noqa: BLE001 - kein Mikrofon, Treiber ...
            logger.warning("Zuhoeren ging nicht: %s", exc)
            if not self._stop.is_set():
                self.post("error", f"Mikrofon: {exc}")
        finally:
            self.ready.set()

    def _listen(self, blocks: queue.Queue) -> None:
        """Zeitangaben hier sind Audio-Zeit (Summe der Blockdauern) - genau und testbar."""
        noise: list[float] = []
        echo: deque = deque(maxlen=200)  # so laut ist Novas eigene Stimme im Mikrofon
        pre: deque = deque()
        pre_time = 0.0
        voiced: list[bytes] = []
        talking = False
        loud = quiet = speech = total = 0.0
        clock = last_level = 0.0
        nova_before, nova_since, nova_quiet_since = False, 0.0, -1.0
        recognizer = None
        last_partial = ""
        last_block = time.monotonic()
        while not self._stop.is_set():
            try:
                block = blocks.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - last_block > 10:
                    self.post("error", "Vom Mikrofon kommt nichts an - ist es angeschlossen und erlaubt?")
                    return
                continue
            last_block = time.monotonic()
            dur = len(block) / (2 * RATE)
            clock += dur
            level = _rms(block)
            nova = self._nova.is_set()
            if nova and not nova_before:
                nova_since = clock
            elif nova_before and not nova:
                nova_quiet_since = clock
            nova_before = nova
            if len(noise) * dur < 0.5 and not talking:  # erste halbe Sekunde: Grundrauschen
                noise.append(level)
                continue
            threshold = max(median(noise) * 2.5, 350.0)
            if clock - last_level >= 0.1:
                last_level = clock
                self.post("level", round(min(1.0, level / (threshold * 4)), 3))

            if not talking:
                pre.append(block)
                pre_time += dur
                while pre_time > 0.45 and len(pre) > 1:
                    pre_time -= len(pre.popleft()) / (2 * RATE)
                if nova:
                    if not self.barge_in or clock - nova_since < 0.5:
                        # erst hoeren, wie laut Nova selbst im Mikrofon ist
                        echo.append(level)
                        loud = 0.0
                        continue
                    limit = max(threshold * 3.0, _echo_limit(echo))
                    if level > limit:
                        loud += dur
                    else:
                        loud = 0.0
                        echo.append(level)
                    if loud < 0.3:
                        continue
                    self.post("barge", None)
                else:
                    if 0 <= nova_quiet_since and clock - nova_quiet_since < 0.3:
                        continue  # Nachhall von Novas Stimme
                    loud = loud + dur if level > threshold else 0.0
                    if level <= threshold:
                        noise = (noise + [level])[-60:]  # Raum wird leiser/lauter: nachfuehren
                    if loud < 0.1:
                        continue
                    self.post("onset", None)
                talking, voiced, quiet, speech, total = True, list(pre), 0.0, loud, pre_time
                pre.clear()
                pre_time = loud = 0.0
                recognizer, last_partial = self._recognizer, ""
                if recognizer is not None:
                    try:
                        recognizer.reset()
                        last_partial = recognizer.feed(b"".join(voiced))
                    except Exception as exc:  # noqa: BLE001
                        logger.info("Vosk: %s", exc)
                        recognizer = None
                continue

            voiced.append(block)
            total += dur
            if level >= threshold * 0.8:
                quiet = 0.0
                speech += dur
            else:
                quiet += dur
            if recognizer is not None:
                try:
                    partial = recognizer.feed(block)
                except Exception as exc:  # noqa: BLE001
                    logger.info("Vosk: %s", exc)
                    recognizer, partial = None, ""
                if partial and partial != last_partial:
                    last_partial = partial
                    self.post("partial", tidy(partial))
            if quiet < self.pause and total < self.max_seconds:
                continue
            if quiet < self.pause * 2 and total < self.max_seconds and _unfinished(last_partial):
                continue  # "... und" / "... weil" - da kommt noch was: etwas laenger warten
            talking = False
            pcm = b"".join(voiced)
            voiced = []
            text = None
            if recognizer is not None:
                try:
                    text = recognizer.finish()
                except Exception as exc:  # noqa: BLE001
                    logger.info("Vosk: %s", exc)
            if speech < 0.2 or (text is not None and not text.strip()):
                self.post("dropped", None)
            else:
                self.post("utterance", Utterance(tidy(text) if text is not None else None, pcm, total))


# ---------------------------------------------------------------------------
#  Vorlesen: im Fenster (App) oder am PC (pyttsx3)
# ---------------------------------------------------------------------------
class WindowVoice:
    """Die App liest im Fenster vor (speechSynthesis). Sie meldet 'spoken', wenn fertig."""

    def __init__(self, emit):
        self.emit = emit
        self._idle = threading.Event()
        self._idle.set()
        self.turn = 0

    def begin(self, turn: int) -> None:
        self.turn = turn

    def say(self, text: str, seq: int) -> None:
        self._idle.clear()
        self.emit({"type": "say", "turn": self.turn, "seq": seq, "text": text})

    def end(self, count: int) -> None:
        self.emit({"type": "say_end", "turn": self.turn, "count": count})
        if count == 0:
            self._idle.set()

    def stop(self) -> None:
        self.emit({"type": "hush", "turn": self.turn})
        self._idle.set()

    def spoken(self, turn: int | None = None) -> None:
        if turn is None or int(turn) == self.turn:
            self._idle.set()

    def idle(self) -> bool:
        return self._idle.is_set()

    def close(self) -> None:
        self.stop()


class LocalVoice:
    """Vorlesen am PC (pyttsx3) - Terminal, oder App mit tts="server" (dann nur Untertitel)."""

    def __init__(self, speaker, emit=None):
        self.speaker = speaker
        self.emit = emit
        self.turn = 0

    def begin(self, turn: int) -> None:
        self.turn = turn

    def say(self, text: str, seq: int) -> None:
        self.speaker.say(text)
        if self.emit:
            self.emit({"type": "say", "turn": self.turn, "seq": seq, "text": text, "local": True})

    def end(self, count: int) -> None:  # noqa: ARG002
        pass

    def stop(self) -> None:
        self.speaker.stop()

    def spoken(self, turn: int | None = None) -> None:  # noqa: ARG002
        pass

    def idle(self) -> bool:
        return self.speaker.wait(0)

    def close(self) -> None:
        self.speaker.stop()


# ---------------------------------------------------------------------------
#  Das Gespraech
# ---------------------------------------------------------------------------
_YES = ("ja", "jo", "jep", "okay", "ok", "klar", "einmal", "mach", "gerne", "gern", "erlaubt", "darfst", "passt")
_ALWAYS = ("immer", "jedes mal", "dauerhaft")
_NO = ("nein", "nee", "ne", "nicht", "stopp", "stop", "abbrechen", "lass")


_STOP = ("stopp", "stop", "halt", "abbrechen", "aufhoeren", "aufh\u00f6ren", "hoer auf", "h\u00f6r auf", "warte")


def is_stop(text: str) -> bool:
    low = re.sub(r"[^\w\u00e4\u00f6\u00fc\u00df ]", " ", text.lower())
    words = low.split()
    return 0 < len(words) <= 5 and any(p in " ".join(words) for p in _STOP)


def voice_choice(text: str, options: list[str]) -> str | None:
    """Gesprochene Antwort auf eine Rueckfrage -> passender Wert (oder None)."""
    words = re.findall(r"[a-z\u00e4\u00f6\u00fc\u00df]+", text.lower())
    joined = " ".join(words)
    if not words or len(words) > 8:
        return None
    if any(w in _NO for w in words):
        return "nein" if "nein" in options else None
    if "immer" in options and any(p in joined for p in _ALWAYS):
        return "immer"
    if any(w in _YES for w in words):
        for value in ("einmal", "ja"):
            if value in options:
                return value
    return None


class LiveLoop:
    """Fuehrt das Live-Gespraech. Der host stellt bereit:

      start_turn(text) -> bool     Antwort im Hintergrund starten (False = gerade beschaeftigt);
                                   Text-Stuecke an on_text(), Werkzeuge an on_tool(), Ende an on_turn_end()
      cancel_turn(drop: bool)      laufende Antwort anhalten (drop = ganz zuruecknehmen)
      transcribe(pcm) -> str       Erkennung ohne Vosk (Google/Whisper)
      event(dict)                  Anzeige: Zustand, Mitschrift, Pegel ...
      busy() -> bool               arbeitet gerade (z.B. Update-Pruefung)
      pending_ask() -> dict|None   offene Rueckfrage {"id","options"} - per Stimme beantwortbar
      answer_ask(id, value)
      is_exit(text) -> bool        "Chat-Modus" o.ae. -> Live-Modus beenden
    """

    def __init__(self, host, voice_out, settings, ear: Ear | None = None, recognizer_factory=None):
        self.host = host
        self.voice_out = voice_out
        self.settings = settings
        self.genau = bool(getattr(settings, "live_genau", False))
        self.inbox: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.ear = ear or Ear(self.post, pause=getattr(settings, "pause", 0.6),
                              barge_in=getattr(settings, "unterbrechen", True),
                              recognizer_factory=recognizer_factory)
        self.error: str | None = None
        self.state = "off"
        self.turn = 0
        self.turn_active = False
        self.turn_text = ""
        self.said = 0
        self.tool_used = False
        self.tool_running = False
        self.interrupted = False
        self.cancelled = False
        self.speaking = False
        self.speech_closed = False
        self.speech_chars = 0
        self.closed_at = 0.0
        self.pending: str | None = None
        self.splitter = SentenceSplitter()

    # -- von aussen (beliebige Threads) ------------------------------------
    def post(self, kind: str, data=None) -> None:
        self.inbox.put((kind, data))

    def on_text(self, chunk: str) -> None:
        self.post("text", chunk)

    def on_tool(self) -> None:
        self.post("tool", None)

    def on_turn_end(self, cancelled: bool = False) -> None:
        self.post("turn_end", cancelled)

    def on_ask(self, text: str) -> None:
        self.post("ask", text)

    def spoken(self, turn: int | None = None) -> None:
        self.post("spoken", turn)

    def hush(self) -> None:
        self.post("hush", None)

    def stop(self) -> None:
        self.stop_event.set()
        self.post("stop", None)

    # -- Hauptschleife -----------------------------------------------------
    def run(self) -> None:
        self.ear.start()
        self._state("listening")
        try:
            while not self.stop_event.is_set():
                try:
                    kind, data = self.inbox.get(timeout=0.1)
                except queue.Empty:
                    self._tick()
                    continue
                getattr(self, f"_on_{kind}", lambda _d: None)(data)
                self._tick()
        finally:
            self.ear.stop()
            if self.speaking:
                self.voice_out.stop()
            if self.turn_active:
                self.host.cancel_turn(False)
            self._state("off", error=self.error)

    def _state(self, state: str, **extra) -> None:
        self.state = state
        event = {"type": "jarvis", "state": state}
        event.update({k: v for k, v in extra.items() if v is not None})
        self.host.event(event)

    def _idle_state(self) -> None:
        if self.turn_active:
            self._state("thinking")
        elif not self.speaking:
            self._state("listening")

    # -- Ereignisse vom Ohr --------------------------------------------------
    def _on_level(self, value) -> None:
        self.host.event({"type": "level", "value": value})

    def _on_onset(self, _data) -> None:
        if not self.speaking:
            self._state("hearing")

    def _on_barge(self, _data) -> None:
        # Sofort still sein. Angehalten wird die Antwort erst, wenn wirklich etwas
        # gesagt wurde - war es nur ein Geraeusch, redet Nova weiter (_on_dropped).
        if self.speaking:
            self._hush()
        self._state("hearing")

    def _on_partial(self, text) -> None:
        self.host.event({"type": "heard", "text": text, "final": False})

    def _on_dropped(self, _data) -> None:
        self.host.event({"type": "heard", "text": "", "final": True})
        if self.turn_active and not self.cancelled:
            self.interrupted = False  # nur ein Geraeusch: mit den naechsten Saetzen weitermachen
        self._idle_state()

    def _on_error(self, text) -> None:
        self.error = text
        self.stop_event.set()

    def _on_stop(self, _data) -> None:
        self.stop_event.set()

    def _on_utterance(self, utt: Utterance) -> None:
        text = utt.text
        if text is None or (self.genau and utt.pcm):
            self._state("recognizing")
            try:
                text = tidy(self.host.transcribe(utt.pcm) or "") or (text or "")
            except Exception as exc:  # noqa: BLE001
                self.host.event({"type": "jarvis", "state": "listening", "error": str(exc)})
                text = text or ""
        text = text.strip()
        self.host.event({"type": "heard", "text": text, "final": True})
        if not text:
            self._idle_state()
            return
        ask = self.host.pending_ask()
        if ask:
            value = voice_choice(text, [o for o in ask.get("options", [])])
            if value:
                self.host.answer_ask(ask["id"], value)
                self._idle_state()
            else:
                self.interrupted = False
                self._say("Sag bitte ja, immer oder nein.")
            return
        if self.host.is_exit(text):
            self.stop_event.set()
            return
        if self.turn_active:
            if is_stop(text):
                if self.speaking:
                    self._hush()
                self._cancel(drop=False)
                self.pending = None
                return
            if self.said == 0 and not self.tool_used and self.pending is None:
                # Nachtrag ("... in Berlin"): Frage neu stellen, alte Runde zuruecknehmen
                self.pending = f"{self.turn_text} {text}".strip()
                self._cancel(drop=True)
            elif self.tool_used:
                # Nova arbeitet gerade (Dateien, Befehle ...): nicht mittendrin abbrechen
                self.pending = text if self.pending is None else f"{self.pending} {text}"
                self.interrupted = False
                self._say("Okay, das mache ich gleich - ich bin hier noch kurz dran.")
                return
            else:
                if self.speaking:
                    self._hush()
                self.pending = text if self.pending is None else f"{self.pending} {text}"
                self._cancel(drop=False)
            self._state("thinking", text=self.pending)
            return
        if self.speaking:
            self._hush()
        if is_stop(text):
            self._state("listening")
            return
        self._send(text)

    def _cancel(self, drop: bool) -> None:
        self.interrupted = self.cancelled = True  # was noch von der alten Antwort kommt, nicht vorlesen
        self.host.cancel_turn(drop)

    # -- Ereignisse von der Antwort -------------------------------------------
    def _on_text(self, chunk: str) -> None:
        if not self.turn_active or self.interrupted:
            return
        self.tool_running = False
        for sentence in self.splitter.feed(chunk):
            self._say(sentence)

    def _on_tool(self, _data) -> None:
        if not self.turn_active:
            return
        self.tool_used = self.tool_running = True
        if not self.interrupted:
            for sentence in self.splitter.flush():  # was vor dem Werkzeug kam, gleich sagen
                self._say(sentence)
        if not self.speaking:
            self._state("thinking", working=True)

    def _on_ask(self, text: str) -> None:
        if self.interrupted:
            return
        question = speech_text(text).split(". ")[0][:220].rstrip(".")
        self._say(schoen(f"Kurze Rueckfrage: {question}. Sag ja, immer oder nein."))

    def _on_turn_end(self, cancelled) -> None:  # noqa: ARG002
        if not self.turn_active:
            return
        self.turn_active = False
        self.tool_running = False
        if not self.interrupted:
            for sentence in self.splitter.flush():
                self._say(sentence)
        if self.said and not self.interrupted:
            self.voice_out.end(self.said)  # Fenster: "spoken" melden, wenn alles gesagt ist
        self.speech_closed = True
        self.closed_at = time.monotonic()
        # Wartet noch etwas Gesagtes (pending), startet es _tick(), sobald Nova
        # fertig gesprochen hat.
        if not self.speaking and self.pending is None:
            self._state("listening")

    def _on_spoken(self, turn) -> None:
        self.voice_out.spoken(turn)

    def _on_hush(self, _data) -> None:
        """Stopp-Knopf: nicht weiterreden und die Antwort anhalten."""
        if self.speaking:
            self._hush()
        if self.turn_active:
            self._cancel(drop=False)
        self.pending = None
        self._state("listening")

    # -- Sprechen ---------------------------------------------------------------
    def _send(self, text: str) -> None:
        self.turn += 1
        self.voice_out.begin(self.turn)
        self.splitter = SentenceSplitter()
        self.said = self.speech_chars = 0
        self.tool_used = self.tool_running = self.interrupted = self.cancelled = False
        self.speech_closed = False
        self.turn_text = text
        if self.host.busy():
            self.pending = text  # sobald frei, nochmal versuchen
            self._state("thinking", text=text)
            return
        if not self.host.start_turn(text):
            self._state("listening", error="Das konnte ich gerade nicht annehmen - versuch es nochmal.")
            return
        self.turn_active = True
        self._state("thinking", text=text)

    def _say(self, sentence: str) -> None:
        if not sentence:
            return
        self.said += 1
        self.speech_chars += len(sentence)
        if not self.speaking:
            self.speaking = True
            self.ear.set_nova_speaking(True)
            self._state("speaking")
        self.voice_out.say(sentence, self.said)

    def _hush(self) -> None:
        self.interrupted = True
        self.voice_out.stop()
        self.speaking = False
        self.ear.set_nova_speaking(False)
        self._state("hearing", interrupted=True)

    def _tick(self) -> None:
        if self.speaking and self.speech_closed:
            overdue = time.monotonic() - self.closed_at > 20 + 0.12 * self.speech_chars
            if self.voice_out.idle() or overdue:
                self.speaking = False
                self.ear.set_nova_speaking(False)
                if not self.turn_active and self.pending is None:
                    self._state("listening")
        if self.pending is not None and not self.turn_active and not self.speaking and not self.host.busy():
            text, self.pending = self.pending, None
            self._send(text)
