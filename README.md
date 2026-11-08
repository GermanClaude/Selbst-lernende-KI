# Selbst-lernende-KI 🧠

Ein **lokaler, lernfähiger KI-Assistent** für deinen PC – im Stil von „Jarvis“.
Du redest mit ihr wie mit einem Menschen (per Tastatur oder Sprache), sie merkt
sich mit der Zeit immer mehr über dich, sie hat Zugang zum Internet und kann –
wenn **du** es erlaubst – deinen Computer bedienen: Dateien lesen, schreiben,
bearbeiten, löschen, Programme starten, Dinge herunterladen und sogar Maus und
Tastatur steuern.

> 🟢 **Noch nie programmiert?** Nimm die **[Schritt-für-Schritt-Anleitung für
> Anfänger → ANLEITUNG.md](ANLEITUNG.md)**. Dort ist alles ganz einfach erklärt.

> **Wichtig und ehrlich vorab:** Diese KI trainiert **kein** eigenes neuronales
> Netz von Grund auf (das ist über Nacht auf einem normalen PC unmöglich). Ihr
> „Gehirn“ ist das Claude-Modell von Anthropic, das über das Internet denkt.
> Das **Lernen** passiert durch ein dauerhaftes Gedächtnis: Sie notiert sich
> Fakten, Vorlieben, Korrekturen und Zusammenfassungen und wird dadurch mit
> jeder Nutzung persönlicher und treffsicherer. Dieses Gedächtnis kannst du
> sogar selbst ansehen und korrigieren. Ihren Charakter und ihre Werte legst du
> in zwei Textdateien fest – so „erziehst“ du sie.

---

## Was sie kann

- 💬 **Natürliches Gespräch** in vollständigen Sätzen, auf Deutsch.
- 🔀 **Zwei Gehirne zur Auswahl**: **Claude** (sehr stark) oder **DeepSeek**
  (extrem günstig) – per Einstellung umschaltbar, jeweils mit eigenem API-Key.
- 💶 **Sparmodus + Live-Kostenanzeige**: so wenig Token wie möglich bei voller
  Leistung; `/kosten` zeigt jederzeit den geschätzten Verbrauch.
- 🧠 **Lernen & Gedächtnis**: merkt sich dauerhaft, was ihr wichtig ist über dich.
- 🌐 **Internet**: Websuche und Webseiten lesen.
- 📁 **Dateien**: lesen, schreiben, bearbeiten, auflisten, (sicher) löschen.
- 🖥️ **PC-Steuerung** (optional): Maus, Tastatur, Bildschirmfotos – wie ein Mensch.
- ⌨️ **Shell**: Befehle ausführen, Programme starten, Dinge installieren.
- 🎙️ **Sprachsteuerung** (optional): zuhören und vorlesen.
- 🎭 **Persönlichkeit & Werte**, die du selbst in Textdateien festlegst.
- 🌙 **AFK-Modus**: „Ich bin mal weg“ – sie arbeitet allein weiter, sicher und mit Bericht.
- ⚡ **Schnell oder gründlich**: Modell und Denk-Tiefe frei wählbar.
- 🔒 **Sicherheit zuerst**: ein Berechtigungssystem mit „Safe Mode“, Nachfragen
  und einem Papierkorb, damit nichts versehentlich zerstört wird.
- 📦 **Als `.exe` baubar** für den Doppelklick-Start unter Windows.

---

## Schnellstart

### 1. Voraussetzungen
- Python 3.10 oder neuer
- Ein Anthropic-API-Schlüssel von <https://console.anthropic.com/>

### 2. Gehirn wählen & Schlüssel eintragen
Kopiere `.env.example` zu `.env` und trage den Schlüssel des Gehirns ein, das du
nutzen willst:
```
ANTHROPIC_API_KEY=sk-ant-...   # für Claude
DEEPSEEK_API_KEY=sk-...        # für DeepSeek (günstig)
```
Welches Gehirn aktiv ist, stellst du in `config/settings.toml` ein:
```toml
[provider]
aktiv = "deepseek"   # oder "claude"
```

### 3. Starten
**Windows:** Doppelklick auf `start.bat`
**Linux/macOS:**
```bash
./start.sh
```
Beim ersten Start richtet sich alles automatisch ein. Danach kannst du einfach
losreden.

Alternativ von Hand:
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m assistant
```

---

## Als `.exe` bauen (Windows)

```bat
packaging\build.bat
```
Danach liegen zwei Programme in `dist\`: **`KI.exe`** (im Terminal) und
**`KI-App.exe`** (eigenes Programmfenster). (Unter Linux/macOS: `packaging/build.sh` → `dist/KI`.)

Wo die `.exe` ihre Dateien sucht:
- Liegt sie im `dist`-Ordner des Projekts, nutzt sie `.env`, `config\`, `data\`
  und `workspace\` des **Projektordners** – also dasselbe Gedächtnis wie `start.bat`.
- Kopierst du sie woandershin, nutzt sie den **Ordner der `.exe`** und legt dort
  beim ersten Start `.env` und `config\settings.toml` an.
- `/status` im Chat zeigt, welche Einstellungs- und Schlüssel-Datei sie gerade liest.

> Hinweis: Eine Windows-`.exe` muss **auf Windows** gebaut werden. Der Code ist
> plattformübergreifend; die Build-Skripte gibt es für beide Welten.

---

## So „erziehst“ du deine KI

Zwei Dateien im Ordner `config/` bestimmen, wer deine KI ist:

| Datei | Wofür |
|-------|-------|
| `config/persona.md` | Charakter, Tonfall, Name, Verhalten |
| `config/werte.md` | Grundsätze, Regeln, Grenzen („Gewissen“) |

Ändere sie, wie du magst – die KI liest sie bei jedem Start neu. Zusätzlich lernt
sie **im Gespräch**: Sage ihr Dinge wie „merk dir, dass ich morgens geduzt werden
will“, und sie legt das in ihrem Gedächtnis ab.

> Die eingebauten Sicherheitsgrenzen des zugrunde liegenden Modells (vom Anbieter)
> bleiben bestehen; `werte.md` bestimmt das Verhalten **deiner** KI darüber hinaus.

---

## Gehirn wählen: Claude oder DeepSeek 💶

Du kannst zwischen zwei „Gehirnen“ umschalten (in `config/settings.toml`):

| Provider | Stärke | Kosten | Einstellung |
|----------|--------|--------|-------------|
| **Claude** (Anthropic) | höchste Qualität | höher | `aktiv = "claude"` |
| **DeepSeek** | sehr gut, OpenAI-kompatibel | **extrem günstig** | `aktiv = "deepseek"` |

**DeepSeek einrichten:**
1. Schlüssel von <https://platform.deepseek.com/> in `.env` als `DEEPSEEK_API_KEY`.
2. In `config/settings.toml`: `[provider] aktiv = "deepseek"`.
3. Modell steht auf `deepseek-flash` (schnell, extrem günstig). Für schwere
   Aufgaben gibt es `deepseek-v4-pro`. Die alten Namen `deepseek-chat` und
   `deepseek-reasoner` hat DeepSeek abgeschaltet – sie werden automatisch umgestellt.

### Modell und Denk-Tiefe wählen (schnell oder gründlich)

In der App unter **Gehirn & Schlüssel** oder im Chat mit `/modell` und `/denken`:

| Gehirn | Modelle | Denk-Tiefe |
|--------|---------|------------|
| **Claude** | Opus 5.5 (stark, Standard), Sonnet 5.5 (schnell), Haiku 5.5 (blitzschnell, sehr günstig), Fable 5.1 (das stärkste, langsamer) | schnell · ausgewogen · gründlich · sehr gründlich · maximal |
| **DeepSeek** | Flash (schnell, Standard), V4 Pro (stärker) | schnell (ohne Nachdenken) · ausgewogen · gründlich · maximal |

Beispiele: `/modell sonnet`, `/modell deepseek pro`, `/denken schnell`, `/denken gründlich`.
Faustregel: Für Alltagsfragen reicht **schnell** oder **ausgewogen** – für knifflige
Programmier-Aufgaben lieber **gründlich**. Mehr Denk-Tiefe heißt: bessere Antworten,
aber länger warten und etwas höhere Kosten. Das Gespräch läuft beim Wechsel weiter.

### Wie bleibt der Token-Verbrauch extrem niedrig?

Der **Sparmodus** (`[sparsam] aktiv = true`, standardmäßig an) sorgt dafür:

- **Kurze Antworten**: die KI wird angewiesen, ohne Füllsätze auf den Punkt zu
  kommen → weniger Output-Token (Output ist am teuersten).
- **Automatisches Kontext-Caching von DeepSeek**: Weil wir den Verlauf nur
  *anhängen* und den System-Prompt stabil halten, zählt der wiederkehrende Anfang
  als „Cache-Treffer“ und kostet nur einen Bruchteil (bei `deepseek-flash` ca.
  **1/50** des normalen Input-Preises).
- **Frühe Zusammenfassung** langer Gespräche (`verlauf_kompakt_nach`), damit nicht
  jede neue Nachricht den ganzen bisherigen Verlauf erneut bezahlt.
- **Gekürzte Werkzeug-Ausgaben** (`max_werkzeug_ausgabe`), damit riesige Dateien
  nicht unnötig Token fressen.

### Was kostet das ungefähr?

Mit `deepseek-flash` (Preise ca. `$0,15` pro 1 Mio. Input-Token, `$0,003` für
Cache-Treffer, `$0,60` für Output; werktags 2–5 und 7–11 Uhr deutscher Winterzeit
doppelt so viel) kostet eine typische Chat-Nachricht mit etwas
Kontext oft **deutlich unter einem Zehntelcent**. Ein gemessenes Beispiel aus dem
Projekt (Frage + Werkzeugnutzung + Antwort) lag bei **~0,00005 €**.

> Grobe Einordnung: Bei **10 €** Guthaben und sparsamer, alltäglicher Nutzung
> (einige Dutzend Nachrichten pro Tag) kommst du realistisch **sehr lange** hin –
> die „10 Tage“ aus deiner Frage sind damit locker drin, bei moderater Nutzung
> eher Wochen. Der genaue Wert hängt davon ab, wie viel du schreibst und wie
> große Dateien/Webseiten die KI liest. Mit `/kosten` siehst du den laufenden
> Verbrauch jederzeit live.

Die Preise für die Anzeige stehen in `config/settings.toml` unter `[preise]` –
ändern sich die DeepSeek-Preise, passt du dort einfach die Zahlen an.

---

## Sicherheit & Berechtigungen (bitte lesen)

Die KI kann viel – deshalb ist ein Schutznetz eingebaut. Alles steuerst du in
`config/settings.toml` (beim ersten Start aus der Vorlage erzeugt, oder per
`python -m assistant --einrichten`):

| Einstellung | Bedeutung | Standard |
|-------------|-----------|----------|
| `safe_mode` | Sperrt **gefährliche** Aktionen (Löschen, Shell, PC-Steuerung) komplett | `true` |
| `auto_confirm` | Wenn `false`, fragt die KI vor jeder schreibenden/gefährlichen Aktion nach | `false` |
| `workspace_root` | Arbeitsordner („Sandbox“); Dateiwerkzeuge dürfen nur hier arbeiten | `workspace/` |
| `allow_full_filesystem` | Erlaubt Zugriff auf das **ganze** Dateisystem | `false` |
| `use_quarantine` | Gelöschtes wandert erst in einen Papierkorb statt endgültig weg | `true` |
| `shell_allowlist` | Harmlose Befehle, die ohne Nachfrage laufen dürfen | `echo, ls, …` |
| `shell_denylist` | Muster, die **immer** blockiert werden | `rm -rf /, …` |

**Empfehlung zum Ausprobieren:** Lass `safe_mode = true`. Dann kann die KI reden,
lesen, im Internet suchen und im Arbeitsordner schreiben – aber nichts löschen,
keine Shell-Befehle und keine Maus/Tastatur steuern.

**Volle Kontrolle freischalten** (wenn du ihr vertraust):
```toml
[permissions]
safe_mode = false          # gefährliche Werkzeuge erlauben
auto_confirm = false       # sie fragt weiterhin vor jeder Aktion nach
allow_full_filesystem = true   # Zugriff über den Arbeitsordner hinaus
```
Für einen echten „macht alles von allein“-Modus zusätzlich `auto_confirm = true`
– **mit Bedacht**, denn dann handelt sie ohne Rückfrage.

---

## Sprechen per F2

- **F2 gedrückt halten** und sprechen – loslassen, fertig.
- Oder **F2 kurz drücken**: „Mikrofon AN“ erscheint, sprich so lange du willst,
  dann **nochmal F2** (Esc bricht ab).
- Der erkannte Text steht danach in der Eingabezeile – prüfen, ggf. korrigieren,
  **Enter**.

Einmalig einrichten – im Chat:
```
/sprache einrichten
```
Das installiert `sounddevice` und `SpeechRecognition` (Erkennung über Google,
online, kostenlos). Offline-Erkennung: zusätzlich `pip install faster-whisper`
(beim ersten Sprechen wird das Modell geladen). Einstellungen unter `[voice]`.
Antworten vorlesen lassen: `/sprache vorlesen` (braucht `pip install pyttsx3`).

## Jarvis-Modus: einfach reden (live)

`/jarvis` (oder in der App der Knopf **Jarvis-Modus**) – und du redest einfach mit
Nova, ganz ohne Tastatur. Zurück: „Chat-Modus“ sagen, Esc oder Strg+C.

So schnell wie möglich:
- **Live-Mitschrift:** Nova schreibt mit, *während* du sprichst (Vosk, offline,
  kostenlos – das deutsche Modell, ~50 MB, lädt sie beim ersten Mal selbst nach
  `data/sprachmodelle/`).
- **Kurze Sprechpause genügt** (Standard 0,6 s). Endet der Satz auf „und“, „weil“
  o.ä., wartet sie etwas länger.
- **Sie spricht ab dem ersten fertigen Satz**, während der Rest der Antwort noch
  entsteht.
- **Unterbrechen:** Fang einfach an zu reden – sie hört sofort auf (mit Kopfhörer
  am zuverlässigsten). „Stopp“ hält auch eine laufende Aufgabe an.
- **Nachtrag:** „Wie wird das Wetter morgen?“ … „in Berlin“ wird zu einer Frage.
- **Rückfragen** beantwortest du mit „ja“, „immer“ oder „nein“.
- Claude denkt im Sprachmodus weniger tief nach (`live_denktiefe = "low"`), damit
  die Antwort schneller kommt.

Ehrlich: Ganz ohne Wartezeit wie bei Gemini Live geht es nicht – Gemini hört und
spricht direkt, DeepSeek und Claude verstehen nur Text. Bis Nova anfängt zu
sprechen, vergehen meist 1–2 Sekunden. Einstellungen unter `[voice]`
(`pause`, `unterbrechen`, `live_mitschrift`, `live_genau`, `live_denktiefe`).

## Novas Sphäre und die Einrichtung in der App

In der App hat Nova eine leuchtende **Sphäre** als Gesicht – sie zeigt, was Nova gerade
tut (nachdenken, arbeiten, schreiben, vorlesen, zuhören). Antippen startet den
Jarvis-Modus. Aussehen ändern: einfach Nova fragen („mach deine Sphäre grün“).

Beim ersten Start öffnet sich **„Gehirn & Schlüssel“**: DeepSeek oder Claude wählen,
Schlüssel einfügen, fertig. Den Schlüssel kannst du auch einfach in den Chat einfügen
(App und Terminal) – er geht nie an die KI. `/gehirn` zeigt bzw. wechselt das Gehirn.

## Charakter & Profil

Wie Nova sein soll, stellst du selbst ein – in der App unter **„Charakter &
Profil“**, im Terminal mit Befehlen:

| Befehl | Wirkung |
|--------|---------|
| `/charakter` | Charaktere zeigen; `/charakter butler` wählt einen (freundlich, sachlich, butler, mentor, kumpel, kreativ, coach) |
| `/stil` | z.B. `/stil anrede Sie`, `/stil laenge kurz`, `/stil humor viel`, `/stil emojis an` |
| `/ueber-mich` | was Nova über dich weiß; ändern z.B. `/ueber-mich projekte = meine Website` |
| `/werte bearbeiten` | deine Regeln für Nova im Editor öffnen |
| `/neu` | neues Gespräch – Änderungen gelten sofort |

Die Persönlichkeit steht in `config/persona.md` (beim Wählen eines Charakters wird
die alte in `data/persona-sicherungen/` gesichert), „Über mich“ in
`config/ueber_mich.json`. Updates fassen beides nie an.

## Als App oder im Terminal

- **`start-app.bat`** bzw. **`KI-App.exe`** – die KI als eigenes Programm mit
  eigenem Fenster (kein Browser; unter Windows zeigt die eingebaute Komponente
  WebView2 die Oberfläche an – wie bei Teams oder Discord). Linux/macOS: `./start.sh app`.
- **`start.bat`** bzw. **`KI.exe`** – wie bisher im Terminal.
- Im Terminal wechselt `/app` in die App; `/verknuepfung` legt ein Desktop-Symbol an.
  Mit `oberflaeche = "app"` unter `[ki]` öffnet auch `start.bat` die App.
- Die App läuft nur lokal (`127.0.0.1`, mit geheimem Schlüssel in der Adresse) –
  niemand sonst im Netz kann sie erreichen. Fenster zu = KI beendet.

## Agenten, Durcharbeiten und Selbstkontrolle

- Große Aufgaben gibt die KI teilweise an **Agenten** ab – eigene KI-Sitzungen mit
  frischem Kopf: `recherche` (sucht und fasst zusammen, ändert nichts), `helfer`
  (erledigt eine Teilaufgabe), `pruefer` (sucht kritisch nach Fehlern, ändert
  nichts). Im Chat siehst du `>> Agent 'recherche' startet …`. Für Agenten gelten
  dieselben Werte (`werte.md`) und Berechtigungen.
- Am Schritt-Limit (`max_werkzeug_runden`) arbeitet sie bis zu
  `automatisch_weiter`-mal von selbst weiter.
- Vor dem Abschluss größerer Arbeiten prüft sie ihr Ergebnis selbst.
- **Strg+C** hält die laufende Antwort an, ohne die KI zu beenden.

## Warteschlange und Dazwischenreden (App)

- Du kannst schreiben, während Nova noch arbeitet: **Enter** stellt die Nachricht in
  die **Warteschlange** (sie ist dran, sobald die laufende Antwort fertig ist),
  **Strg+Enter** unterbricht Nova und sie beantwortet die neue Nachricht sofort.
- Über dem Eingabefeld siehst du, was wartet – mit „Jetzt“ (unterbrechen) und „✕“ (entfernen).
- **Stopp** hält an; wartende Nachrichten kommen zurück ins Eingabefeld.

## AFK-Modus: „Ich bin mal weg“

Sag Nova „Ich bin jetzt AFK“ oder „Ich bin für zwei Stunden weg, recherchier bitte …“,
drück in der App **„Ich bin weg“** oder tippe `/afk <Auftrag>`. Dann arbeitet sie in
Schritten allein weiter – an deinem Auftrag oder an dem, woran ihr zuletzt gearbeitet
habt – und handelt so, wie du es nach allem, was sie über dich weiß, wollen würdest.

- **Erlaubt**: lesen, im Internet recherchieren, planen, **neue** Dateien im
  Arbeitsordner anlegen, sich Dinge merken.
- **Nicht erlaubt** (egal wie die Stützräder stehen): löschen, bestehende Dateien
  überschreiben, Befehle/Programme ausführen, den PC steuern, etwas verschicken oder
  kaufen. Solche Schritte schreibt sie als **Vorschlag** auf. Nachgefragt wird in der
  Zeit nie – es ist ja niemand da.
- **Grenzen**: höchstens 2 Stunden, ca. 1 € und 12 Schritte (in der App beim Start
  wählbar, sonst in `config/settings.toml` unter `[afk]`).
- **Zurück**: einfach eine Nachricht schreiben (im Terminal: Strg+C). Du bekommst einen
  Bericht mit Ergebnissen, Vorschlägen zum Freigeben und offenen Fragen.

## Automatische Updates

Einmal am Tag schaut die KI im GitHub-Repo nach einer neuen Version. Gibt es eine,
erklärt dir deine KI (Claude oder DeepSeek) in eigenen Worten, was neu ist, und
installiert sie – die bisherige Version wird vorher im Ordner `versionen\`
gesichert. Danach startet sie von selbst neu (über `start.bat` / `start.sh`).

- `/update` – sofort nachschauen
- `/versionen` – gesicherte alte Versionen anzeigen
- `/zurueck <Nr>` – zu einer alten Version zurück (automatische Updates pausieren
  dann, bis du wieder `/update` eingibst)

Deine Daten bleiben bei jedem Update unangetastet: `.env`, `config\settings.toml`,
`config\persona.md`, `config\werte.md`, Gedächtnis (`data\`) und Arbeitsordner.
Einstellen unter `[update]` (`modus = "automatisch" | "fragen" | "aus"`).
Die `KI.exe` holt sich neue Versionen aus den GitHub-Releases.

**Neue Version veröffentlichen:** in `assistant/__init__.py` die `__version__`
erhöhen, in `CHANGELOG.md` oben einen Abschnitt dazu schreiben und auf den
Standard-Branch bringen. Alle Installationen holen sie sich dann selbst; die
GitHub-Action baut dazu automatisch eine neue `KI.exe`.

## PC-Steuerung (Maus/Tastatur) aktivieren (optional)

```bash
pip install pyautogui pillow
```
Und `safe_mode = false` setzen. Not-Aus: Maus in eine Bildschirmecke reißen
stoppt die Steuerung sofort.

---

## Befehle im Chat

| Befehl | Wirkung |
|--------|---------|
| `/hilfe` | Hilfe anzeigen |
| `/status` | Einstellungen & Sicherheitslage zeigen |
| `/gedaechtnis` | anzeigen, was die KI gelernt hat |
| `/kosten` | Token-Verbrauch & geschätzte Kosten dieser Sitzung |
| `/sprache` | Stand der Spracheingabe (F2) |
| `/sprache einrichten` | Spracheingabe installieren |
| `/sprache vorlesen` | Antworten vorlesen an/aus |
| `/jarvis` | Jarvis-Modus: einfach reden, live (zurück: „Chat-Modus“ sagen) |
| `/afk [Auftrag]` | AFK-Modus: Nova arbeitet allein weiter (zurück: Nachricht bzw. Strg+C) |
| `/modell [name]` | Modell zeigen bzw. wählen (z.B. `/modell sonnet`, `/modell deepseek pro`) |
| `/denken [stufe]` | Denk-Tiefe: schnell, ausgewogen, gründlich, sehr gründlich, maximal |
| `/gehirn [deepseek\|claude]` | Gehirn zeigen bzw. wechseln |
| `/update` | jetzt nach einer neuen Version schauen |
| `/versionen` | gesicherte alte Versionen anzeigen |
| `/zurueck <Nr>` | zu einer alten Version zurückkehren |
| `/autostart` | zeigen (und abstellen), was die KI automatisch startet |
| `/app` | zur App wechseln (eigenes Fenster) |
| `/verknuepfung` | Desktop-Symbol für die App anlegen |
| `/erlauben alles` | nie mehr nachfragen, alles erlauben (dauerhaft) |
| `/erlauben fragen` | wieder vor jeder Aktion nachfragen |
| `/beenden` | Sitzung beenden (speichert eine Zusammenfassung) |

---

## Projektaufbau

```
assistant/
  __main__.py      Einstiegspunkt (python -m assistant)
  config.py        Einstellungen/Provider/Persona/Werte/Preise laden
  memory.py        dauerhaftes Gedächtnis (SQLite) – das "Lernen"
  permissions.py   Sicherheits-/Berechtigungssystem
  personality.py   baut den System-Prompt (inkl. Sparhinweis)
  brain.py         schlanke Orchestrierung (Kompaktierung, Episoden)
  providers/       austauschbare Gehirne:
    base.py          Token-/Kostenzählung, Werkzeug-Hilfen
    anthropic_provider.py   Claude
    deepseek_provider.py    DeepSeek (OpenAI-kompatibel)
  voice.py         Sprachein-/-ausgabe (F2-Sprechtaste)
  live.py          Jarvis-Modus: durchgehend zuhoeren, live mitschreiben, unterbrechen
  updater.py       automatische Updates + gesicherte alte Versionen
  app/             die KI als App: Server, Fenster, Oberflaeche (static/)
  tools/           Werkzeuge: Dateien, Shell, Web, System, Gedächtnis, PC
  ui/cli.py        die Chat-Oberfläche
config/            persona.md, werte.md, settings(.example).toml
packaging/         PyInstaller-Spec + Build-Skripte
tests/             pytest-Tests (44 Stück)
run_ki.py          Start-Skript (auch für die .exe)
start.bat/.sh      Direktstart ohne Build
```

---

## Technische Hinweise

- **Modell:** Standard ist Claude `claude-opus-5-5` (adaptives „Thinking“,
  einstellbare Denk-Tiefe über `effort`). Alternativ DeepSeek `deepseek-flash`
  (Nachdenken über `denken`). Wählbar in der App, mit `/modell` und `/denken` oder in
  `config/settings.toml`.
- **Tests:** 44 Stück (pytest), decken Gedächtnis, Berechtigungen, Werkzeuge,
  beide Provider (mit gefälschten Clients, ohne Netz) und die Kostenrechnung ab.
- **Langer Verlauf:** Sehr lange Gespräche werden automatisch zusammengefasst
  („Kompaktierung“) und als Episode ins Gedächtnis geschrieben – das hält die
  Nutzung schnell und bezahlbar und ist mit „preserved thinking“ kompatibel
  (der Gesprächsverlauf wird nur angehängt, nie nachträglich verändert).
- **Kosten:** Jede Antwort ruft die Anthropic-API auf und kostet entsprechend
  deinem Tarif. Die Denk-Tiefe (`effort`) ist der wichtigste Kostenhebel.
- **Datenschutz:** Gedächtnis und Logs liegen **lokal** bei dir (`data/`, `logs/`).

---

## Tests ausführen

```bash
pip install pytest
pytest -q
```

---

## Haftung

Dieses Werkzeug kann – nach deiner Freigabe – echte Änderungen an deinem Computer
vornehmen. Nutze `safe_mode` und `auto_confirm` bewusst. Du bist für die Aktionen
verantwortlich, die du der KI erlaubst. Starte mit den sicheren Standardwerten und
erweitere die Rechte erst, wenn du dich damit wohlfühlst.
