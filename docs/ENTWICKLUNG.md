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
- **Privates Backup:** Der ganze Verlauf + alle Release-Tags liegen zusaetzlich im PRIVATEN Repo
  `GermanClaude/Nova-Backup` (das oeffentliche `GermanClaude/Selbst-lernende-KI` bleibt fuer die
  Releases/den Updater). In diesem Checkout pusht `git push origin <branch>` dank zweiter Push-URL
  automatisch in BEIDE. Nach einem frischen Clone einmal einrichten:
  `git remote set-url --add --push origin https://github.com/GermanClaude/Selbst-lernende-KI.git`
  und `git remote set-url --add --push origin https://github.com/GermanClaude/Nova-Backup.git`
  (danach `git push origin --tags` fuer die Tags). So geht nie Fortschritt verloren, auch wenn ein Chat verschwindet.
- Zuletzt dazugekommen: **0.35.0** Handy-Version: `python -m assistant --server` (`app/handy_server.py`: fester Port 8765, fester Schluessel data/server_token, beendet sich NICHT ohne Fenster, oeffnet die APK per `am start -n de.nova.handy/.MainActivity -d <url>` oder termux-open-url, termux-wake-lock); `handy_steuerung.py` + Werkzeug `handy_steuern` (Termux:API-Befehle, ADB ueber Kabelloses Debugging: uiautomator-Dump als Elementliste, input tap/swipe/text/keyevent, monkey, adb install; nur registriert, wenn Termux oder adb da ist); Termux-Block im System-Prompt; `/handysteuerung`; `termux/installieren.sh`; Android-App `android/` (reines WebView, ohne Bibliotheken, AGP 8.7.3/SDK 35/minSdk 24) und Workflow `android-apk.yml` (laeuft per workflow_run nach dem Release, haengt Nova-Handy.apk an; fester Signierschluessel aus Secret NOVA_KEYSTORE_B64/NOVA_KEYSTORE_PASS, sonst Debug-Schluessel). Tests `test_handy_version`. Davor: **0.34.0** Hardware (`geraete.py` + `tools/geraete.py`: `smarthome` (Home Assistant REST, nur erlaubte Dienste, Token in .env HA_URL/HA_TOKEN), `mikrocontroller` (pyserial, HTTP nur LAN via `lan_adresse`), `bluetooth` (bleak, asyncio.run), `ssh_geraet` (System-ssh mit BatchMode, nur eingetragene Geraete aus config/geraete.json - geschuetzt im Updater, Risk.DANGEROUS)); `/geraete`; pyserial/bleak(+winrt) per ki.spec/Workflow gebuendelt (optional). Tests `test_geraete`. Davor: **0.33.0** Fehler bemerken: `controller._fehler_merken` (Liste `_fehler`, max. 20, Log), `_fehler_reaktion` (Auto-Antwort als Hinweis-Runde ueber `run_background`, nur wenn frei, je Meldung einmal, max. alle 120 s, nie aus einer Auto-Runde heraus, nicht bei bekannten Gehirn-Fehlern), `_mit_fehler_hinweis` (offene Fehler vor die naechste Nachricht), POST `/api/fehler` (JS `window.onerror`/`unhandledrejection`, gedrosselt), Knopf "Nova fragen" an Fehlerkarten, Werkzeug `app_fehler` (Liste + Warnungen/Tracebacks aus ki.log, `verschleiere`). **0.32.1** Spracheingabe: `VoiceCapture.backend()` auto = Google zuerst (faster-whisper steckt seit 0.27.1 fuer den Mitschnitt in der .exe). Tests `test_fehler_bemerken`, `test_voice_backend`. Davor: **0.32.0** Anrufe ueber Bland AI (`anruf.py`: POST
  https://api.bland.ai/v1/calls mit phone_number E.164, task, first_sentence, language "de",
  max_duration, wait_for_greeting, voicemail leave_message; Status per GET /v1/calls/{id}; Header
  `authorization: <key>`; laut Doku 24.11.2026 - Anrufe ausserhalb USA/Kanada brauchen >= 5 $ Guthaben,
  sonst HTTP 402). Werkzeug `anrufen` (tools/anruf.py) OHNE Nummernfeld - nur `ANRUF_NUMMER` aus der
  .env; am PC Risk.MODERATE-Nachfrage, im AFK ohne; Kostenbremse 5/Tag (`data/anrufe.json`), max. 3 Min.
  Befehl `/anruf` (schluessel/nummer/minuten/test). Tests `test_anruf`. Davor: **0.31.0** Offline-Handy-Nachrichten: `handy.rueckstand_holen` (holt mit
  timeout=0 bis leer, der leere Abruf bestaetigt bei Telegram), Ablage `data/handy_offen.json`
  (`offen_*`, `offen_entfernen` loescht nur die gefragten Eintraege). `cli._handy_beim_start` (Terminal:
  vor `_loop`, App: Thread in `startup()`), `_handy_offen_fragen` mit Sperre gegen Doppel-Nachfrage; die
  App ueberschreibt `_handy_offen_entscheidung` (Dialog "question": ja/spaeter/verwerfen - Stopp =
  spaeter) und `_handy_offen_umsetzen` (`submit`, ein gebuendelter Auftrag). `/handy`-Start wirft den
  Rueckstand nicht mehr weg (nur wenn noch keine Chat-ID gebunden ist). Tests `test_handy_offline`.
  Davor: **0.30.0** Skills-Reiter in der App (Profil-Fenster, `TABS` in app.js um
  `skills` erweitert, Seitenleisten-Knopf `sb-skills` → `openProfile('skills')`; GET/POST
  `/api/skills` → `controller.skills_info`/`skills_action` über `skills.py`; Zeilen nutzen die
  `.fact`-Klassen des Gedächtnis-Reiters; Liste lädt bei jedem Öffnen neu, weil Nova Skills auch selbst
  anlegt). Tests `test_skills_panel`; im echten Browser gegen einen Wegwerf-Server geprüft (keine
  Konsolenfehler, Anlegen/An-Aus/Löschen, schmales Layout). Davor: **0.29.1** DeepSeek-Flash-Eintrag umbenannt in „DeepSeek V4.1 Flash"
  (gleiche API-ID `deepseek-flash`, laut Recherche = V4.1-Flash mit Vision + Thinking); neues
  optionales `"aliase"`-Feld je Modell in `modelle._finde_modell` (für `/modell v4.1 flash` usw.).
  Tools/Skills pro Modell gab es schon (`skill`-Werkzeug, `skills.prompt_block(provider)`). Davor:
  **0.29.0** Arbeitsordner frei wählbar (`/arbeitsordner`, App-Knopf mit
  pywebview-FOLDER_DIALOG über `controller._arbeitsordner_picker`/`launcher` `ctl._window`;
  `cli._arbeitsordner_setzen` legt an + speichert `[permissions] workspace_root` + wirkt sofort auf
  `PermissionManager.workspace_root`). Shell ohne Ordnerangabe läuft jetzt im Arbeitsordner
  (`tools/shell.py`), System-Prompt nennt den Ordner (`personality.py`). Tests `test_arbeitsordner`,
  `test_tools_shell`. Davor: **0.28.2** Begriff „Jarvis-Modus" → „Sprachmodus" (nur sichtbare Texte +
  Befehl `/sprachmodus`/`/sprechen`; interne Bezeichner, `/api/jarvis`, DOM-IDs, `/jarvis`-Alias und
  die Tagline „im Stil von Jarvis" bleiben). Davor: **0.28.1** Impressum wieder entfernt (`IMPRESSUM.md` geloescht, Verweise in
  `cli.py` `_print_rechtliches`, `ki.spec`, README, `NUTZUNGSBEDINGUNGEN.md`, COMMANDS raus);
  `/rechtliches` zeigt nur noch die Nutzungsbedingungen. Davor: **0.28.0** Handy-Fernzugriff per Telegram ohne eigenen Server (`handy.py`:
  `HandyRelay` Long-Poll/urllib, Whitelist auf EINE Chat-ID, `relais_schleife`; Befehl `/handy`
  mit Terminal-Variante in `cli.py` und Hintergrund-Variante in `app/controller.py` -
  `_handy_antwort` serialisiert über die busy-Sperre, Rückfragen gehen ans Handy; Token in `.env`
  als `TELEGRAM_BOT_TOKEN`, Chat-ID als `TELEGRAM_CHAT_ID`; App-Knopf „Fernzugriff (Handy)"; Tests
  `test_handy`). Davor: **0.27.2** Rechtliches (`NUTZUNGSBEDINGUNGEN.md`, `IMPRESSUM.md`, Befehl
  `/rechtliches`, in die .exe gebündelt) + Mitschnitt-DSP optimiert (`_mische` numpy-Pfad,
  `_f0_schaetzen` begrenzte Korrelation). Davor: **0.27.0** Skills (`skills.py`, global/pro-Gehirn), eigene Modell-IDs
  (`modelle._EIGENE_MODELLE_OK`), Mitschnitt mischt System-Audio + Mikrofon (`mitschnitt._mische`,
  Quelle "beides"), klarere .exe-Meldung. Tests `test_skills`, `test_eigene_modelle`. Davor:
  **0.26.1 / 0.26.0** Mitschnitt/Transkription (`mitschnitt.py`, lokal/token-frei,
  System-Audio, Sprecher best effort) + Aktivitaets-Protokoll (`protokoll.py`, kein Keylogger);
  Befehle `/transkript` und `/protokoll`, Werkzeug `transkription`. Tests `test_mitschnitt`,
  `test_protokoll`. Davor: **0.25.1 / 0.25.0** NanoGPT (unzensiert, OpenAI-kompatibel, sieht Bilder, Zahlung
  auch per Karte - `providers/nanogpt_provider.py`, Modell-IDs mit "/"; Tests
  `test_provider_nanogpt`). Hinweis: kein Anbieter bietet PayPal; Google Pay nur evtl. im
  Stripe-Checkout. Davor: **0.24.0** Venice AI (zweites unzensiertes Gehirn, sieht selbst Bilder;
  `providers/venice_provider.py`, `venice_parameters.include_venice_system_prompt=false`), Umlaute
  beim Tippen (`tools/computer._tippe`/`_tippe_unicode_windows` via SendInput KEYEVENTF_UNICODE -
  pyautogui.typewrite kann nur ASCII), `/versionen` zeigt pro Version die Neuerung
  (`updater.changelog_summary`). Tests: `test_provider_venice`, `test_tippen_umlaute`,
  `test_changelog_summary`. Davor: **0.23.0 Abliteration kann sehen** (`abliteration_provider._seh_quelle` leiht
  ein seh-faehiges Gehirn (DeepSeek Flash/Gemini/OpenAI) zur Bildbeschreibung, da Abliteration selbst
  kein Bild-Modell hat; `_describe_image`/`_describe_images` ueberschrieben; Tests
  `tests/test_abliteration_sehen.py`). Davor: **0.22.1 schnelle Updates** (`cli._explain_update` + `_mit_zeitlimit`/
  `UPDATE_ERKLAER_TIMEOUT`: Modell-Erklaerung der Neuerungen mit Zeitlimit, sonst sofort die rohen
  Versionshinweise – Update haengt nie an einem langsamen Modell; Tests `tests/test_update_speed.py`).
  Davor: **0.22.0 Gehirn „Abliteration AI"** (unzensiert, OpenAI-kompatibel;
  `providers/abliteration_provider.py`, Tests `tests/test_provider_abliteration.py`). „RAW AI"
  (Play-Store-App) hat keine API, daher nicht anbindbar - Abliteration AI als Alternative.
  Davor: **0.21.1 AFK endet nicht durch Blips**, **0.21.0 AFK-Vollmacht** (`permissions.afk_autonom`/`afk_handlungsfrei`,
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
| Denken, Verlauf, Kosten | `assistant/brain.py`, `assistant/providers/` (anthropic, deepseek, gemini, openai, abliteration, venice, nanogpt, ollama), `assistant/modelle.py`. Neues OpenAI-kompatibles Gehirn = DeepSeekProvider ableiten (siehe `abliteration_provider.py`: eigener Schluessel/base_url, kein Nachdenken) + in config/schluessel/modelle/providers.__init__ sowie den UI-Listen (cli `_split_provider`, controller provider_name, app.js PROVIDERS/SU_*/Key-Regex) eintragen. |
| OpenAI-Besonderheiten | `providers/openai_provider.py`: Denk-Modelle brauchen `max_completion_tokens` (nicht `max_tokens`), keine `temperature`, Denk-Tiefe per `reasoning_effort`. Flaggschiffe mit Responses-API-Zwang für Tools sind bewusst nicht in der Modell-Liste. Modelle/Preise in `modelle.py` – **Stand 20.11.2026, regelmäßig prüfen** |
| Gemini-Besonderheiten | `providers/gemini_provider.py`: Denk-Signaturen an Werkzeug-Aufrufen unverändert zurückschicken (sonst 400), Nachdenken nicht abschaltbar, Schema ohne `additionalProperties`. Modelle/Preise (mit Datum der angekündigten Erhöhungen) in `modelle.py` – **Stand 13.11.2026, regelmäßig prüfen** |
| Werkzeuge | `assistant/tools/` – jedes Werkzeug eine Klasse mit `name`, `description`, `input_schema`, `run()`; Anmeldung in `tools/__init__.py` |
| Claude-Grenzen | `tools/base.py` `grenzen_einhalten()` – max. 20 „strict“-Werkzeuge, max. 24 optionale Angaben |
| Berechtigungen | `assistant/permissions.py` (`Risk.SAFE/MODERATE/DANGEROUS/AUTOSTART`, Stützräder, AFK strenger). Drei Stufen: `an` / `aus` / `alles` (= `vollzugriff`, hebt zusätzlich Shell-Sperrliste **und** Autostart-Rückfrage auf; AFK bleibt trotzdem sicher). Gesetzt in `cli.py` `set_training_wheels_stufe`, App-Schalter über `controller.toggle("vollzugriff", …)`. |
| Terminal-Oberfläche | `assistant/ui/cli.py` (alle `/befehle` in `_handle_command`) |
| App-Oberfläche | `assistant/app/` (controller.py = Logik + Befehlsliste `COMMANDS`, server.py = HTTP-API, static/ = HTML/JS) |
| Gedächtnis, Persönlichkeit, Skills | `memory.py`, `personality.py` (Skills via `skills.prompt_block` in den System-Prompt), `profil.py`, `config/werte.md`, `persona.md`. Skills: `skills.py` (gespeicherte Anweisungen in `config/skills.json`, global oder pro Gehirn `provider`), `tools/skill.py` (Werkzeug `skill`), Befehl `/skill`. Kein Code-Nachladen - ein Skill ist Text. |
| Eigene Modelle | `modelle.waehle` akzeptiert fuer `_EIGENE_MODELLE_OK` (deepseek/gemini/openai/abliteration/venice/nanogpt) jede gueltige Modell-ID (`_gueltige_modell_id`), sofern sie nicht klar zu einem anderen Gehirn gehoert (`fremdes_modell`). Claude/Ollama ueber ihre eigenen Wege. |
| Aussehen / Design | `aussehen.py` (Design-Vorlagen `THEMES`, Hintergrundbild, eigenes CSS – alles über `/custom.css` = `generated_css()` + eigenes CSS), `tools/aussehen.py`. Die Design-Dateien (`config/app-anpassung.*`, `config/app-hintergrund.*`) stehen in `updater._is_protected` → Updates fassen sie nie an. |
| Sprache / Stimme | `voice.py` (Zuhören: VoiceCapture/Whisper/Google; Vorlesen: `Speaker` = pyttsx3 gratis, `CloudSpeaker` = OpenAI/ElevenLabs realistisch; `build_speaker()` waehlt + faellt auf frei zurueck), `live.py` (Jarvis-Loop, LocalVoice/WindowVoice), `tools/stimme.py` (Werkzeug `stimme_waehlen`), Befehl `/stimme` (`cli.set_stimme`). **OpenAI-TTS `/v1/audio/speech` ist zum 6.1.2027 abgekuendigt** (Nachfolger: Realtime-API) – Modell-Konstanten in `voice.py`, Stand 20.11.2026, regelmaessig pruefen. |
| Geheimnis-Filter | `geheimnisse.py` `verschleiere()` - macht Passwoerter/Schluessel/Tokens/2FA/Kartennummern unkenntlich; wird in `mitschnitt.py` (Transkript) und `protokoll.py` (Fenstertitel) vor dem Speichern angewandt. Kein Keylogger - ein Tastatur-Hook koennte Passwortfelder nicht zuverlaessig aussparen. |
| Mitschnitt / Transkription | `mitschnitt.py` (lokal mit faster-whisper, Mikrofon ODER System-Audio via sounddevice WASAPI-Loopback; laeuft bis stop, schreibt `workspace/mitschnitte/*.md`; Sprecher-Trennung best effort via `resemblyzer` (sonst 1 Sprecher), Geschlecht grob aus Tonhoehe `geschlecht_aus_tonhoehe`/`_f0_schaetzen`; Zusammenfassung on demand). `tools/mitschnitt.py` (Werkzeug `transkription`), Befehl `/transkript`, CLI-Callbacks in `tool_ctx.extra["mitschnitt_*"]`. Reine Logik ist getestet; Audio/Whisper lazy. |
| Aktivitaets-Protokoll | `protokoll.py` (welche Apps/Fenster aktiv sind, via ctypes `GetForegroundWindow`; schreibt bei Wechsel nach `workspace/protokolle/*.log`), Befehl `/protokoll`. **BEWUSST kein Keylogger** - keine Tastatur-/Nachrichten-Mitschrift. |
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
