# 📖 Anleitung für absolute Anfänger (Schritt für Schritt)

Diese Anleitung erklärt **ganz einfach**, wie du deine KI zum Laufen bringst –
auch wenn du noch nie programmiert hast. Lies von oben nach unten und mach jeden
Schritt nach. 🙂

> **Was ist das hier?** Nova – ein Programm, mit dem du auf deinem Computer mit einer KI
> redest (wie in einem Chat, oder einfach per Stimme). Das „Denken“ übernimmt ein
> KI-Modell, das du dir aussuchst:
>
> | Gehirn | Kosten | Was du brauchst |
> |---|---|---|
> | **Ollama** – läuft direkt auf deinem PC | **kostenlos** | Ollama installieren, ein Modell laden (z. B. Qwen, Llama, Gemma) |
> | **DeepSeek** – im Internet | **extrem günstig** (Bruchteile eines Cents pro Nachricht) | einen Schlüssel (API-Key) mit ein paar Euro Guthaben |
> | **Claude** (Anthropic) – im Internet | etwas teurer | einen Schlüssel (API-Key) mit Guthaben |
>
> Du kannst jederzeit wechseln – das Gedächtnis bleibt dabei erhalten.

---

## 🚀 Der schnellste Weg: die fertige App (ohne Python)

1. Öffne <https://github.com/GermanClaude/Selbst-lernende-KI/releases/latest>.
2. Lade unter **„Assets“** die Datei **`KI-App.exe`** herunter.
3. Leg sie in einen eigenen Ordner, z. B. `Desktop\Nova`, und starte sie mit Doppelklick.
   > Windows-Warnung „Der Computer wurde geschützt“? → **„Weitere Informationen“** →
   > **„Trotzdem ausführen“**.
4. Beim ersten Start öffnet sich **„Gehirn & Schlüssel“**: Wähle **Ollama** (kostenlos),
   **DeepSeek** oder **Claude** – den Schlüssel einfach einfügen, „Prüfen & speichern“, fertig.
5. Ab jetzt holt sich Nova neue Versionen selbst (deine alte Version wird jedes Mal gesichert).

Mehr brauchst du nicht. 🎉 Die Schritte unten sind nur nötig, wenn du Nova **aus dem
Quellcode** starten oder selbst daran mitbauen willst.

---

## Was du für den Quellcode-Weg brauchst (einmalig)
1. Einen Windows-PC (für Mac/Linux steht unten ein Extra-Hinweis).
2. **Python** 3.10 oder neuer – wir prüfen in Schritt 1, ob Windows es findet.
3. Einen **API-Schlüssel** (DeepSeek ist am günstigsten) **oder** Ollama (kostenlos, ohne Schlüssel).
4. Rund **15 Minuten** beim ersten Mal.

---

## Schritt 1 – Prüfen, ob Windows dein Python findet

Wichtig: Du kannst Python **installiert haben** und Windows findet es trotzdem
nicht im schwarzen Fenster. Das ist der häufigste Anfängerfehler – genau der, der
bei dir aufgetreten ist. So prüfst du es richtig:

1. Drücke die **Windows-Taste**, tippe `cmd`, drücke **Enter** → ein schwarzes
   Fenster öffnet sich.
2. Tippe **genau das** und drücke Enter:
   ```
   py --version
   ```
   - Erscheint `Python 3.14.0` → **perfekt, weiter zu Schritt 2.** ✅
   - Erscheint ein Fehler → probiere als Zweites:
     ```
     python --version
     ```
     Erscheint auch hier ein Fehler oder öffnet sich der **Microsoft Store** →
     lies jetzt den nächsten Kasten.

> ### 🔧 „Python wurde nicht gefunden“ – die 3 Ursachen und ihre Lösung
>
> **Ursache 1: Beim Installieren fehlte das PATH-Häkchen.**
> Starte die Python-Installation von <https://www.python.org/downloads/> noch
> einmal. **Ganz unten im ersten Fenster** gibt es ein Häkchen
> **„Add python.exe to PATH“** – setze es, dann auf **Install Now**. Danach das
> schwarze Fenster **schließen und neu öffnen** und Schritt 1 wiederholen.
>
> **Ursache 2: Windows öffnet beim Tippen von `python` den Microsoft Store.**
> Das ist eine berühmt-berüchtigte Windows-Falle. Lösung:
> 1. Windows-Taste drücken, **„App-Ausführungsaliase“** tippen, Enter.
> 2. In der Liste die Schalter für **`python.exe`** und **`python3.exe`**
>    **ausschalten**.
> 3. Fenster schließen, neues `cmd` öffnen, erneut `py --version` testen.
>
> **Ursache 3: Das schwarze Fenster war schon vor der Installation offen.**
> Einfach dieses Fenster schließen und ein neues öffnen.
>
> 💡 **Merke:** Der Befehl **`py`** funktioniert auf Windows fast immer, auch wenn
> `python` zickt. Unser Startprogramm nutzt automatisch `py`, wenn es da ist.

---

## Schritt 2 – Das Projekt herunterladen

**Variante A (am einfachsten):**
1. Im Browser öffnen: `https://github.com/GermanClaude/Selbst-lernende-KI`
2. Oben links beim Zweig-Auswähler (steht oft „main“) klicken und den Branch
   **`ccr-cfa1ff8c-wgsyxb`** auswählen.
3. Rechts auf den grünen Knopf **`< > Code`** → **„Download ZIP“**.
4. Die ZIP liegt in **Downloads**. Rechtsklick → **„Alle extrahieren…“** → einen
   Ort wählen, den du wiederfindest (z. B. **Desktop**). Diesen Ordner merken.

**Variante B (mit Git, falls installiert):**
```
git clone -b ccr-cfa1ff8c-wgsyxb https://github.com/GermanClaude/Selbst-lernende-KI.git
```

---

## Schritt 3 – Ein Gehirn aussuchen (eins reicht)

### Ganz kostenlos: Ollama (läuft auf deinem PC)
1. Ollama von <https://ollama.com/download> installieren (Windows: `OllamaSetup.exe`).
2. Später in Nova unter **„Gehirn & Schlüssel“ → „Ollama“** ein empfohlenes Modell mit einem
   Klick herunterladen – z. B. `qwen3.5:4b` (ca. 3–4 GB, kann Werkzeuge benutzen und Bilder
   sehen). Für starke PCs: `qwen3.5:9b`.
3. **Jedes andere Ollama-Modell geht auch** (Llama, Gemma, Mistral, DeepSeek-R1 …) – am besten
   eins mit „tools“. Auch **LM Studio** und andere OpenAI-kompatible Server funktionieren
   (Adresse unter `[ollama]` in `config/settings.toml`, z. B. `http://localhost:1234/v1`).
- Vorteil: kostenlos, ohne Konto, deine Gespräche verlassen den PC nicht.
- Nachteil: schwächer als DeepSeek/Claude; braucht mindestens 8 GB Arbeitsspeicher
  (mit Grafikkarte deutlich schneller).

### DeepSeek (extrem günstig, sehr gut)
1. <https://platform.deepseek.com/> öffnen, Konto erstellen.
2. Etwas Guthaben aufladen (10 €/$ reichen sehr lange).
3. Menüpunkt **„API Keys“** → **„Create new API key“**.
4. Den Schlüssel (beginnt mit `sk-...`) sofort **kopieren**.
   ⚠️ Er wird nur **einmal** angezeigt.

### Claude (am stärksten, teurer)
<https://console.anthropic.com/> → Konto, Guthaben, unter **„API Keys“** einen
Schlüssel erstellen (beginnt mit `sk-ant-...`) und kopieren. Wählbar sind dann Opus, Sonnet,
Haiku und Fable – von „blitzschnell und billig“ bis „das Stärkste“.

---

## Schritt 4 – Zum ersten Mal starten

1. Öffne den Projektordner aus Schritt 2.
2. Doppelklick auf die Datei **`start.bat`**.
   > Windows-Warnung „Der Computer wurde geschützt“? → **„Weitere Informationen“**
   > → **„Trotzdem ausführen“**. Das Programm ist deins. 🙂
3. Das Fenster sagt zuerst, welches Python es gefunden hat. Falls dort der
   Python-Fehler kommt: zurück zu **Schritt 1** (der Kasten löst es).
4. Beim allerersten Start richtet sich alles automatisch ein (ein paar Minuten –
   es lädt die nötigen Bausteine herunter).
5. Danach öffnet sich automatisch der **Editor mit der Datei `.env`**. Trage dort
   deinen Schlüssel ein:
   - DeepSeek:
     ```
     DEEPSEEK_API_KEY=sk-hier-dein-schluessel
     ```
   - Oder Claude:
     ```
     ANTHROPIC_API_KEY=sk-ant-hier-dein-schluessel
     ```
   - Die jeweils andere Zeile einfach so lassen.
   - **Mit Ollama** brauchst du keinen Schlüssel – dann den Editor einfach wieder schließen.
6. **Speichern** (Strg + S) und den Editor **schließen**.

Fertig eingerichtet. 🎉

---

## Schritt 5 – Das Gehirn auswählen

**Am einfachsten:** in der App auf **„Gehirn“** in der Seitenleiste klicken (oder im Chat
`/gehirn ollama`, `/gehirn deepseek`, `/gehirn claude` tippen). Einen Schlüssel kannst du
auch einfach in den Chat einfügen – Nova erkennt, wofür er ist, und schaltet um. Der
Schlüssel wird dabei nie an die KI geschickt.

**Oder von Hand:**
1. Im Projektordner den Unterordner **`config`** öffnen.
2. Die Datei **`settings.toml`** öffnen (Rechtsklick → „Öffnen mit“ → „Editor“).
3. Ganz oben steht:
   ```
   [provider]
   aktiv = "claude"
   ```
   Ändere es zu `"deepseek"` (billig) oder `"ollama"` (kostenlos auf deinem PC).
4. **Speichern** und schließen.

---

## Schritt 6 – Mit der KI reden

- Ab jetzt reicht ein **Doppelklick auf `start.bat`**.
- Unten im Fenster tippen und Enter drücken. Schreib wie mit einem Menschen,
  zum Beispiel:
  - „Hallo, wer bist du?“
  - „Merk dir, dass ich am liebsten kurze, klare Antworten mag.“
  - „Suche im Internet nach den heutigen Nachrichten.“
  - „Leg im Arbeitsordner eine Textdatei namens notizen.txt an.“
- Beenden: **`/beenden`** tippen und Enter.

**Nützliche Befehle** (mit `/` tippen):

| Befehl | Bedeutung |
|--------|-----------|
| `/hilfe` | zeigt alle Befehle |
| `/status` | zeigt Gehirn, Modell und Sicherheitslage |
| `/kosten` | zeigt Token-Verbrauch und geschätzte Kosten der Sitzung |
| `/gedaechtnis` | zeigt, was die KI gelernt hat |
| `/sprache einrichten` | Spracheingabe per F2 einrichten (einmalig) |
| `/bild <Pfad>` | ein Bild anhängen, das Nova sich ansehen soll |
| `/feedback` | Feedback & Bewertung schicken |
| `/update` | nach einer neuen Version schauen |
| `/versionen` / `/zurueck <Nr>` | alte Versionen anzeigen / zurückholen |
| `/autostart` | zeigen und abstellen, was die KI von selbst startet |
| `/erlauben alles` | nie mehr nachfragen (bei einer Rückfrage geht auch **a**) |
| `/beenden` | Sitzung beenden |

**Sprechen statt tippen:** einmal `/sprache einrichten` eingeben. Danach
**F2 gedrückt halten** und sprechen (loslassen = fertig) – oder **F2 kurz
drücken**, sprechen, **nochmal F2**. Der Text erscheint in der Eingabezeile,
dann Enter.

**Einfach reden wie mit Jarvis:** `/jarvis` eingeben (in der App: Knopf
**Jarvis-Modus**). Jetzt einfach sprechen – Nova schreibt mit, während du redest,
antwortet laut und hört dann wieder zu. Du kannst sie jederzeit unterbrechen.
Zurück zum Tippen: „Chat-Modus“ sagen. Beim ersten Mal lädt sie einmalig ein
deutsches Sprachmodell (~50 MB) – das dauert kurz.

**Bilder zeigen und erstellen:** In der App ein Bild mit **Strg+V** einfügen, ins
Fenster ziehen oder über die **Büroklammer** wählen – Nova sieht es. Im Terminal:
`/bild C:\Pfad\zum\bild.png` (oder das Bild einfach ins Fenster ziehen). Bilder
erstellen: einfach „Mal mir …“ schreiben – kostenlos, manchmal mit kurzer Wartezeit.
Die Bilder landen im Arbeitsordner unter `bilder`.

**Feedback geben:** Knopf **„Feedback & Bewertung“** oder `/feedback` – Sterne, Text und
Bilder, dann „Jetzt senden“.

**Updates kommen von allein:** Einmal am Tag schaut die KI nach einer neuen
Version, erklärt dir, was neu ist, sichert die alte Version und startet neu.
Deine Schlüssel, Einstellungen und das Gedächtnis bleiben dabei erhalten.

---

## Schritt 7 (freiwillig) – Der KI mehr erlauben

Zum Schutz startet die KI im **sicheren Modus**: reden, lesen, im Internet suchen
und im Arbeitsordner schreiben – aber **kein** Löschen, keine Systembefehle, keine
Maus/Tastatur. Wenn du mehr erlauben willst, in `config/settings.toml` unter
`[permissions]`:
```
safe_mode = false            # erlaubt gefährliche Aktionen
allow_full_filesystem = true # Zugriff auf den ganzen PC statt nur Arbeitsordner
```
Die KI **fragt trotzdem vor jeder heiklen Aktion nach** – du antwortest mit `j`
(ja) oder `n` (nein).

Für **Maus-/Tastatursteuerung** („Jarvis“) einmalig im schwarzen Fenster:
```
.venv\Scripts\activate
pip install pyautogui pillow
```
> **Not-Aus:** Maus schnell in eine Bildschirmecke reißen → Steuerung stoppt sofort.

---

## Nova einstellen: Charakter, Stil, Über mich

In der App: links auf **„Charakter & Profil“**. Dort wählst du einen Charakter
(z.B. Butler, Kumpel, Mentor), stellst du/Sie, Antwortlänge, Humor und Emojis ein
und trägst unter **„Über mich“** ein, was Nova über dich wissen soll. Im Terminal
geht das mit `/charakter`, `/stil` und `/ueber-mich`. Danach **`/neu`** – dann
gilt es sofort.

## Als App statt im Terminal

Doppelklick auf **`start-app.bat`** (oder **`KI-App.exe`**) – die KI öffnet sich
als eigenes Programm mit Fenster und Knöpfen statt im schwarzen Terminal. Es öffnet
sich kein Browser. Alles andere bleibt gleich (Gedächtnis,
Einstellungen, Updates). Tipp: im Chat `/verknuepfung` eingeben, dann liegt ein
Symbol auf dem Desktop. Das Terminal gibt es weiterhin mit `start.bat`.

## Schritt 8 (freiwillig) – Eine `.exe` zum Doppelklicken bauen

Doppelklick auf `packaging\build.bat`. Nach ein paar Minuten liegt die Datei
**`dist\KI.exe`** bereit.

Die `.exe` im `dist`-Ordner benutzt deine `.env` und `config\settings.toml` aus
dem Projektordner – du musst nichts kopieren. Ziehst du `KI.exe` woandershin
(z.B. auf den Desktop), legt sie dort beim ersten Start eine eigene `.env` und
`config\` an; trag dann dort deinen Schlüssel ein. Im Chat zeigt `/status`, welche
Dateien sie gerade liest.

---

## 💶 Bleibt es billig?

Ja. Mit **Ollama** kostet es gar nichts. Mit DeepSeek und dem eingebauten **Sparmodus**
kostet eine normale Nachricht oft **Bruchteile eines Cents** – 10 € Guthaben reichen bei
normaler Nutzung sehr lange. Mit `/kosten` (oder in der Seitenleiste) siehst du den
Verbrauch live, und für AFK-Modus, Live-Sehen und Spielmodus legst du selbst eine
Kostengrenze fest.

---

## 🛟 Problemlösung (kurz & konkret)

**„Python wurde nicht gefunden“** → siehe den großen Kasten in **Schritt 1**
(PATH-Häkchen, Microsoft-Store-Aliase ausschalten, Fenster neu öffnen; notfalls
`py` statt `python` nutzen).

**`pip install` bricht mit Fehler ab (Python 3.14 ist brandneu)** →
- Wenn nur **optionale** Pakete (Sprache/PC-Steuerung) meckern: ignorieren, die
  KI läuft trotzdem.
- Wenn ein **Hauptpaket** scheitert: installiere zusätzlich **Python 3.12** von
  python.org (3.12 und 3.14 dürfen gleichzeitig installiert sein). Dann im
  Projektordner den Ordner **`.venv` löschen** und `start.bat` erneut starten –
  es nutzt dann automatisch das gefundene Python.

**„Kein DEEPSEEK_API_KEY / ANTHROPIC_API_KEY gefunden“** → In der Datei `.env`
fehlt der Schlüssel oder steht in der falschen Zeile. `.env` öffnen, Schlüssel
beim passenden Namen eintragen, speichern, neu starten.

**„Insufficient balance“ / Fehler vom Anbieter** → Guthaben leer oder Schlüssel
falsch kopiert. Guthaben prüfen, Schlüssel neu kopieren.

**DeepSeek-Modell wird nicht gefunden** → Im Chat `/modell flash` eingeben (oder in
der App unter Gehirn & Schlüssel „DeepSeek Flash“ wählen). Die alten Namen
`deepseek-chat`/`deepseek-reasoner` stellt Nova seit Version 0.6.0 selbst um.

**Nach einem Update öffnet sich das Desktop-Symbol nicht mehr (oder zeigt eine alte
Version)** → Das lag an Versionen vor 0.6.1: Das Symbol zeigte danach in den Ordner
`versionen`. Starte Nova einmal direkt aus ihrem Ordner (die `KI-App.exe` dort) – ab
0.6.1 repariert sie solche Symbole beim ersten Start selbst. Oder lösch das Symbol und
tippe im Chat `/verknuepfung`, dann legt Nova ein neues an.

**Claude denkt mir zu lange nach** → In der App unter Gehirn & Schlüssel die
Denk-Tiefe auf „schnell“ oder „ausgewogen“ stellen (im Chat: `/denken schnell`) –
oder ein schnelleres Modell wählen, z. B. `/modell sonnet` oder `/modell haiku`.

**Die KI öffnet sich immer wieder von selbst** → Im KI-Fenster `/autostart`
eingeben. Es zeigt, was sie automatisch startet (oft hat sie sich selbst in die
Windows-Aufgabenplanung eingetragen), und `/autostart entfernen alle` stellt es ab.
Seit Version 0.3.0 fragt sie vorher immer nach, bevor sie so etwas einrichtet.

**Die KI scheint zu hängen** → Steht „denkt nach (… s)“ da, arbeitet sie noch.
Mit **Strg+C** hältst du die Antwort an, ohne die KI zu schließen.

**Die KI liest beim Programmieren nur Dateien, zeigt die Kostenzeile und macht
nichts** → Ab dieser Version hält sie nach `max_werkzeug_runden` Schritten mit
einem Hinweis an – schreib dann einfach **„weiter“**. Wenn deine
`config/settings.toml` noch aus einer älteren Version stammt, prüfe dort:
`[sparsam] verlauf_kompakt_nach` sollte nicht zu klein sein (Standard 24 – zählt
jetzt nur deine Nachrichten), und bei DeepSeek `[deepseek] max_tokens = 8192`
(mit 2048 werden große Dateien beim Schreiben abgeschnitten).

**`UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`** → In älteren
Versionen hat das Shell-Werkzeug Umlaute in der Ausgabe von Windows-Befehlen
falsch gelesen. Ist behoben. Ohne Update hilft: im Projektordner `cmd` öffnen,
`chcp 1252` eingeben und dann `start.bat` starten.

**Wo finde ich `.env`?** Direkt im Projektordner. Falls du sie nicht siehst:
im Explorer oben **Ansicht → Anzeigen → Dateinamenerweiterungen** und
**ausgeblendete Elemente** einschalten.

---

## 🍏 Mac / 🐧 Linux (Kurzfassung)

Alles gleich, nur statt `start.bat` im Terminal im Projektordner:
```
./start.sh
```
Beim ersten Mal wird `.env` angelegt und geöffnet – Schlüssel eintragen,
speichern, schließen.

---

Viel Spaß mit deiner KI! Hängt etwas, schreib mir einfach die genaue
Fehlermeldung aus dem schwarzen Fenster – dann helfe ich dir gezielt weiter. 🙂
