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
    """Spricht Text vor (offline, via pyttsx3)."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._engine = None
        if enabled:
            try:
                import pyttsx3

                self._engine = pyttsx3.init()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Sprachausgabe nicht verfuegbar: %s", exc)
                self.enabled = False

    def speak(self, text: str) -> None:
        if not self.enabled or not self._engine or not text.strip():
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sprachausgabe-Fehler: %s", exc)


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
