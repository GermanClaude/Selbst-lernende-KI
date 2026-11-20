# Entwicklungs-Übergabe (für neue Chats/Sessions)

Diese Datei ist das „Gedächtnis“ des Projekts für Entwickler und KI-Assistenten. Wer neu
einsteigt (oder ein neuer Claude-Chat), liest zuerst diese Datei, dann `CLAUDE.md` und
`CHANGELOG.md`. **Bei jeder größeren Änderung hier den Abschnitt „Stand“ und „Offene Punkte“
aktualisieren**, damit nie wieder Wissen verloren geht, wenn ein Chat verschwindet.

## Was ist Nova?

Ein persönlicher KI-Assistent für Windows (läuft auch unter Linux/macOS, viele Extras nur
Windows). Python-Projekt, ausgeliefert als `KI.exe` (Terminal) und `KI-App.exe` (eigenes Fenster
per pywebview). Fünf austauschbare „Gehirne“: Claude (Anthropic API-Schlüssel), DeepSeek, Gemini
(Google, OpenAI-kompatibel), OpenAI/ChatGPT, Ollama (lokal, kostenlos). Nova hat ein Langzeitgedächtnis (SQLite), Werkzeuge (Dateien, Shell, Web,
PC-Steuerung, Agenten …) und fragt vor riskanten Aktionen nach (`assistant/permissions.py`).

## Stand

- Aktuelle Version: siehe `__version__` in `assistant/__init__.py` und oben in `CHANGELOG.md`.
- Standard-Branch: `ccr-cfa1ff8c-wgsyxb` (so benannt, weil das Projekt in einer Claude-Cloud-Session
  entstand). Nur dieser Branch erzeugt Releases.
- Zuletzt dazugekommen: **0.21.0 AFK-Vollmacht** (`permissions.afk_autonom`/`afk_handlungsfrei`,
  `abwesend._RULES_AUTONOM`, Tests `tests/test_afk_autonom.py`) – im AFK wirklich handeln statt nur
  vorschlagen, wenn volle Freiheit gegeben ist. Davor: **0.20.0 Stimmen-Auswahlliste in der App**,
  **0.19.0 Stimme waehlbar** (`voice.CloudSpeaker`/`build_speaker`,
  `tools/stimme.py`, Befehl `/stimme`, Tests `tests/test_stimme.py`) – gratis (pyttsx3) oder
  realistisch (OpenAI/ElevenLabs). Davor: 0.18.0 Vollzugriff (dritte Stützräder-Stufe „alles"),
  0.16.0 ChatGPT/OpenAI als fünftes Gehirn, 0.17.0 eigenes Design (update-fest).

## Screenshots (`docs/bilder/`)

Die Bilder in der README stammen aus einer **Demo-Nova ohne echte Nutzerdaten** (frische Kopie
des Codes, `[provider] aktiv = "ollama"`, Updates aus, Demo-Person „Alex“). Gestartet mit
`python -m assistant --app --browser`, die Adresse steht in `data/app.json`; fotografiert mit
Playwright und installiertem Edge (`channel="msedge"`, 1280×820, Zoom 1,5, dunkles Design),
danach auf 1440 px Breite verkleinert. **Nie Screenshots aus einer echten Installation
verwenden** – darin stehen Gedächtnis, Profil und Dateipfade.

## Ablauf einer Änderung (Release)

1. Code ändern, Tests: `python -m pytest -q`.
2. `__version__` erhöhen (Korrektur: x.y.Z, neue Funktion: x.Y.0).
3. `CHANGELOG.md`: oben `## <Version> – <Datum>` mit Stichpunkten für Nicht-Techniker
   (Nova liest sie beim Update vor).
4. Auf den Standard-Branch pushen → GitHub Action `.github/workflows/release-exe.yml` baut
   `KI.exe`/`KI-App.exe`, startet sie zur Probe (`app-selbsttest.yml`) und veröffentlicht das
   Release `v<Version>`. Der eingebaute Updater (`assistant/updater.py`) holt es sich.
5. Zwischenstände ohne Release: Commit-Nachricht mit `[skip ci]`.

## Projektkarte

| Bereich | Dateien |
|---|---|
| Start, Konfiguration | `run_ki.py`, `assistant/__main__.py`, `assistant/config.py`, `config/` |
| Denken, Verlauf, Kosten | `assistant/brain.py`, `assistant/providers/` (anthropic, deepseek, gemini, openai, ollama), `assistant/modelle.py` |
| OpenAI-Besonderheiten | `providers/openai_provider.py`: Denk-Modelle brauchen `max_completion_tokens` (nicht `max_tokens`), keine `temperature`, Denk-Tiefe per `reasoning_effort`. Flaggschiffe mit Responses-API-Zwang für Tools sind bewusst nicht in der Modell-Liste. Modelle/Preise in `modelle.py` – **Stand 20.11.2026, regelmäßig prüfen** |
| Gemini-Besonderheiten | `providers/gemini_provider.py`: Denk-Signaturen an Werkzeug-Aufrufen unverändert zurückschicken (sonst 400), Nachdenken nicht abschaltbar, Schema ohne `additionalProperties`. Modelle/Preise (mit Datum der angekündigten Erhöhungen) in `modelle.py` – **Stand 13.11.2026, regelmäßig prüfen** |
| Werkzeuge | `assistant/tools/` – jedes Werkzeug eine Klasse mit `name`, `description`, `input_schema`, `run()`; Anmeldung in `tools/__init__.py` |
| Claude-Grenzen | `tools/base.py` `grenzen_einhalten()` – max. 20 „strict“-Werkzeuge, max. 24 optionale Angaben |
| Berechtigungen | `assistant/permissions.py` (`Risk.SAFE/MODERATE/DANGEROUS/AUTOSTART`, Stützräder, AFK strenger). Drei Stufen: `an` / `aus` / `alles` (= `vollzugriff`, hebt zusätzlich Shell-Sperrliste **und** Autostart-Rückfrage auf; AFK bleibt trotzdem sicher). Gesetzt in `cli.py` `set_training_wheels_stufe`, App-Schalter über `controller.toggle("vollzugriff", …)`. |
| Terminal-Oberfläche | `assistant/ui/cli.py` (alle `/befehle` in `_handle_command`) |
| App-Oberfläche | `assistant/app/` (controller.py = Logik + Befehlsliste `COMMANDS`, server.py = HTTP-API, static/ = HTML/JS) |
| Gedächtnis, Persönlichkeit | `memory.py`, `personality.py`, `profil.py`, `config/werte.md`, `persona.md` |
| Aussehen / Design | `aussehen.py` (Design-Vorlagen `THEMES`, Hintergrundbild, eigenes CSS – alles über `/custom.css` = `generated_css()` + eigenes CSS), `tools/aussehen.py`. Die Design-Dateien (`config/app-anpassung.*`, `config/app-hintergrund.*`) stehen in `updater._is_protected` → Updates fassen sie nie an. |
| Sprache / Stimme | `voice.py` (Zuhören: VoiceCapture/Whisper/Google; Vorlesen: `Speaker` = pyttsx3 gratis, `CloudSpeaker` = OpenAI/ElevenLabs realistisch; `build_speaker()` waehlt + faellt auf frei zurueck), `live.py` (Jarvis-Loop, LocalVoice/WindowVoice), `tools/stimme.py` (Werkzeug `stimme_waehlen`), Befehl `/stimme` (`cli.set_stimme`). **OpenAI-TTS `/v1/audio/speech` ist zum 6.1.2027 abgekuendigt** (Nachfolger: Realtime-API) – Modell-Konstanten in `voice.py`, Stand 20.11.2026, regelmaessig pruefen. |
| AFK-Modus | `abwesend.py` (Schleife, Rundenprompt – vorsichtig `_RULES_VORSICHTIG` oder autonom `_RULES_AUTONOM` je `AfkSession.autonom`), `tools/abwesenheit.py`. **AFK-Vollmacht:** `permissions.afk_autonomie_moeglich()` (Setting `afk_autonom` + Stützräder „aus"/„alles") und `afk_handlungsfrei()` (= im laufenden AFK) steuern, ob `check/check_shell/resolve_path/check_path_write` im AFK handeln lassen statt nur Vorschlag. Autostart bleibt im AFK immer gesperrt (`confirm_always` lehnt bei `away` ab). AFK endet nur durch echte Nachricht/Stopp – **nicht** durch Maus/Tastatur (kein Aktivitäts-Wächter im Code). |
| Live-Sehen | `assistant/sehen/` (Auge, Dienst, OCR, Fenster), `tools/sehen.py` |
| Handy als Kamera | `assistant/kamera/` (WebRTC, Signal-Server, QR, Firewall) |
| Spielmodus | `assistant/spiel/` (Sitzung, Eingabe-Wächter, Profile z. B. Manor Lords), `tools/spiel.py` |
| Bilder | `bilder.py`, `bildgenerator.py` (AI Horde / Cloudflare), `tools/bild_tools.py` |
| Sicherheits-Check | `sicherheit.py` (Sammeln per PowerShell → Signaturen → Faustregeln → Bericht), `tools/sicherheit.py` |
| Updates, Autostart | `updater.py`, `austausch.py` (exe tauschen, Verknüpfungen), `selbststart.py` |
| Feedback & Bewertungen | `feedback.py` (inkl. `bewertungen()`), `packaging/nova-feedback.gs` (Apps-Skript: Mail + Tabelle + `?aktion=bewertungen`), `packaging/bewertungen.py` + `.github/workflows/bewertungen.yml` (README-Abschnitt alle 6 h), `docs/FEEDBACK_EINRICHTEN.md` |
| Build | `packaging/` (PyInstaller), `.github/workflows/` |

## Regeln (Kurzfassung aus CLAUDE.md)

- Deutsch überall; im Python-Code ohne Umlaute, in Markdown und sichtbaren App-Texten mit Umlauten.
- Nutzerdaten dürfen Updates nie überschreiben (`updater.py`: `_PROTECTED_*`, `_CREATE_ONLY`).
- Neue Werkzeuge: Risiko über `ctx.permissions.require(...)` prüfen; alles, was Nova über den PC
  liest (Bildschirm, Dateinamen, Befehlszeilen), ist nicht vertrauenswürdig – in Beschreibungen
  darauf hinweisen. Geheimnisse (Schlüssel, Tokens) nie an das Modell schicken.
- Neue Befehle: in `cli.py` (`_handle_command` + Hilfetext oben) **und** in `app/controller.py`
  (`COMMANDS`) eintragen, dazu README-Tabelle „Befehle im Chat“.

## Offene Punkte / bekannte Probleme

- Lokal unter Windows mit Python 3.14 schlagen 9 Tests fehl – schon vor 0.13.0, mit dem
  Original-Code nachgeprüft (950 bestehen): `test_app_bilder` (Bild-Grenze im Terminal),
  `test_ollama` (Stopp während Ollama rechnet), `test_permissions::test_full_filesystem_allows_outside`,
  `test_profil::test_choose_character_backs_up_old_persona`, `test_spiel_app::test_terminal_nicht_unter_linux`,
  `test_tools_filesystem::test_read_long_file_in_sections`, drei in `test_updater` (exe-Tausch,
  Ausführbar-Bit). Vermutlich Windows-/Python-3.14-spezifisch; prüfen, ob sie unter Linux/3.12 grün sind.
- Sicherheits-Check: Der schnelle Scan braucht 1–2 Minuten (Signaturprüfung, Prozessliste).
  Idee: Knopf in der App-Seitenleiste, Ergebnisse als Karten mit „ignorieren“/„Datei prüfen“.
- Sicherheits-Check: mögliche Erweiterungen – Browser-Erweiterungen prüfen, Defender-Schnellscan
  direkt anstoßen, Vergleich mit dem letzten Bericht („neu seit letztem Scan“).
