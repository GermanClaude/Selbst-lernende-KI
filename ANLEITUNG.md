# 📖 Anleitung für absolute Anfänger (Schritt für Schritt)

Diese Anleitung erklärt **ganz einfach**, wie du deine KI zum Laufen bringst –
auch wenn du noch nie programmiert hast. Lies von oben nach unten und mach jeden
Schritt nach. 🙂

> **Was ist das hier?** Ein Programm, mit dem du auf deinem Computer mit einer KI
> redest (wie in einem Chat). Das „Denken“ übernimmt ein KI-Dienst im Internet –
> **DeepSeek** (sehr billig) oder **Claude** (sehr stark). Dafür brauchst du einen
> kleinen „Schlüssel“ (API-Key). Keine Sorge, ich zeige dir alles.

---

## Was du brauchst (einmalig)
1. Einen Windows-PC (für Mac/Linux steht unten ein Extra-Hinweis).
2. **Python** (du hast 3.14 ✅ – wir prüfen in Schritt 1, ob Windows es auch findet).
3. Einen **API-Schlüssel** (ein paar Euro Guthaben; DeepSeek ist am günstigsten).
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

## Schritt 3 – Einen API-Schlüssel holen (nur einen brauchst du)

### DeepSeek (billig) – empfohlen
1. <https://platform.deepseek.com/> öffnen, Konto erstellen.
2. Etwas Guthaben aufladen (10 €/$ reichen sehr lange).
3. Menüpunkt **„API Keys“** → **„Create new API key“**.
4. Den Schlüssel (beginnt mit `sk-...`) sofort **kopieren**.
   ⚠️ Er wird nur **einmal** angezeigt.

### Oder Claude (stärker, teurer)
<https://console.anthropic.com/> → Konto, Guthaben, unter **„API Keys“** einen
Schlüssel erstellen (beginnt mit `sk-ant-...`) und kopieren.

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
6. **Speichern** (Strg + S) und den Editor **schließen**.

Fertig eingerichtet. 🎉

---

## Schritt 5 – Das günstige Gehirn (DeepSeek) auswählen

Standardmäßig ist **Claude** eingestellt. Für **DeepSeek** (billig):
1. Im Projektordner den Unterordner **`config`** öffnen.
2. Die Datei **`settings.toml`** öffnen (Rechtsklick → „Öffnen mit“ → „Editor“).
3. Ganz oben steht:
   ```
   [provider]
   aktiv = "claude"
   ```
   Ändere es zu:
   ```
   [provider]
   aktiv = "deepseek"
   ```
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
| `/sprache` | Sprachsteuerung an/aus (falls eingerichtet) |
| `/beenden` | Sitzung beenden |

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

## Schritt 8 (freiwillig) – Eine `.exe` zum Doppelklicken bauen

Doppelklick auf `packaging\build.bat`. Nach ein paar Minuten liegt die Datei
**`dist\KI.exe`** bereit.

---

## 💶 Bleibt es billig?

Ja. Mit DeepSeek und dem eingebauten **Sparmodus** kostet eine normale Nachricht
oft **Bruchteile eines Cents**. Mit `/kosten` siehst du es live. 10 € Guthaben
reichen bei normaler Nutzung sehr lange.

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

**DeepSeek-Modell wird nicht gefunden** → In `config/settings.toml` unter
`[deepseek]` `model` von `deepseek-chat` auf `deepseek-flash` oder
`deepseek-v4-pro` ändern.

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
