# Neuigkeiten

Jede Version hat hier einen Abschnitt `## <Version> – <Datum>`. Der Updater zeigt
beim Aktualisieren alle Abschnitte zwischen deiner und der neuen Version an, und
deine KI erklärt sie dir in eigenen Worten.

## 0.2.0 – 2026-11-07

**Sprechen per F2**
- F2 gedrückt **halten** und sprechen – loslassen, fertig.
- Oder F2 **kurz drücken**: „Mikrofon AN“ erscheint, du sprichst so lange du willst,
  nochmal F2 beendet die Aufnahme (Esc bricht ab).
- Der erkannte Text landet in der Eingabezeile – kurz prüfen, dann Enter.
- Einrichten mit `/sprache einrichten` (installiert alles Nötige). Erkennung über
  Google (online, kostenlos) oder – falls installiert – offline mit Whisper.

**Automatische Updates**
- Einmal am Tag schaut die KI im GitHub-Repo nach einer neuen Version, erklärt dir,
  was neu ist, und installiert sie (einstellbar unter `[update]`).
- Jede alte Version wird vorher gesichert: `/versionen` zeigt sie, `/zurueck <Nr>`
  holt eine zurück. `/update` schaut sofort nach.
- Deine Daten und Einstellungen (`.env`, `settings.toml`, `persona.md`, `werte.md`,
  Gedächtnis, Arbeitsordner) fasst ein Update nie an.

**Programmieren klappt wieder**
- Die KI hört nicht mehr nach 25 Schritten stumm auf und vergisst nicht mehr alles,
  was sie gerade gelesen hat. Am Schritt-Limit sagt sie Bescheid – schreib „weiter“.
- Lange Dateien liest sie abschnittsweise, große Dateien schreibt sie in Teilen.
- Wenn Claude eine Anfrage ablehnt, bleibt die Sitzung trotzdem benutzbar.

**Windows**
- Keine Abstürze mehr wegen Umlauten in Befehlsausgaben („charmap codec“).
- Programme, die die KI im Hintergrund startet, lassen sie nicht mehr hängen.
- KI.exe findet `.env` und `config\settings.toml` wieder; `/status` zeigt, welche
  Dateien sie liest.

## 0.1.0 – 2026-10-03

- Erste Version: lernfähiger Assistent mit Claude oder DeepSeek, Gedächtnis,
  Werten, Internet, Dateien, Shell und PC-Steuerung.
