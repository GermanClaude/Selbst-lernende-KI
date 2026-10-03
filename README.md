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
Danach liegt die fertige Datei unter `dist\KI.exe`. Doppelklick startet die KI
in einem Konsolenfenster. (Unter Linux/macOS: `packaging/build.sh` → `dist/KI`.)

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
3. Modell steht auf `deepseek-chat` (günstig, schnell). Falls dein Konto diesen
   Alias nicht kennt, trage unter `[deepseek] model` `deepseek-flash` oder
   `deepseek-v4-pro` ein. Für besonders schwierige Logik: `deepseek-reasoner`
   (verbraucht mehr Token).

### Wie bleibt der Token-Verbrauch extrem niedrig?

Der **Sparmodus** (`[sparsam] aktiv = true`, standardmäßig an) sorgt dafür:

- **Kurze Antworten**: die KI wird angewiesen, ohne Füllsätze auf den Punkt zu
  kommen → weniger Output-Token (Output ist am teuersten).
- **Automatisches Kontext-Caching von DeepSeek**: Weil wir den Verlauf nur
  *anhängen* und den System-Prompt stabil halten, zählt der wiederkehrende Anfang
  als „Cache-Treffer“ und kostet nur einen Bruchteil (bei `deepseek-chat` ca.
  **1/10** des normalen Input-Preises).
- **Frühe Zusammenfassung** langer Gespräche (`verlauf_kompakt_nach`), damit nicht
  jede neue Nachricht den ganzen bisherigen Verlauf erneut bezahlt.
- **Gekürzte Werkzeug-Ausgaben** (`max_werkzeug_ausgabe`), damit riesige Dateien
  nicht unnötig Token fressen.

### Was kostet das ungefähr?

Mit `deepseek-chat` (Preise ca. `$0,28` pro 1 Mio. Input-Token, `$0,028` für
Cache-Treffer, `$0,42` für Output) kostet eine typische Chat-Nachricht mit etwas
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

## Sprachsteuerung aktivieren (optional)

```bash
pip install SpeechRecognition pyttsx3 sounddevice
```
Dann in `config/settings.toml`:
```toml
[voice]
enabled = true
speak_responses = true
```
Im Chat schaltet `/sprache` den Sprachmodus an/aus.

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
| `/sprache` | Sprachmodus an/aus |
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
  voice.py         optionale Sprachein-/-ausgabe
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
  einstellbare Denk-Tiefe über `effort`). Alternativ DeepSeek `deepseek-chat`.
  Beides in `config/settings.toml` änderbar.
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
