# Prüfen mit Anwalt / selbst entscheiden

> Diese Liste sammelt alles, was ich (die KI) **nicht sicher einordnen** kann oder was eine
> **bewusste Entscheidung** von dir braucht, bevor du Nova verkaufst oder breiter anbietest.
> Sie ist **kein Rechtsrat**. Vieles aus deiner Wunschliste stammt aus einem Video über **Websites** –
> Nova ist aber eine **App, die lokal auf dem PC des Nutzers läuft**. Deshalb treffen einige Punkte
> nicht oder nur anders zu. Stand: 28.11.2026.

Legende: ✅ erledigt · ⚠️ teilweise / dein Blick nötig · 🚫 trifft auf die lokale App nicht zu ·
🧭 Grundsatz-Entscheidung für dich/deinen Anwalt.

---

## Deine Punkte – Stand

### ✅ Datenschutzerklärung mit jedem Tool
`DATENSCHUTZ.md` listet jetzt **jede** Funktion und wohin (wenn überhaupt) Daten gehen – inkl. der neuen
(Live-Coding, Video-Studio, Kokoro/Piper-Stimmen, Wegwerf-Mail, Konnektoren, God's Eye usw.). **Platzhalter
`[ … ]` musst du ausfüllen** (Verantwortlicher, Kontakt). Prüfe die Liste auf Vollständigkeit für deinen Fall.

### 🚫 Cookie-Banner „alles ablehnen" vor Analytics
Trifft auf die lokale App **nicht** zu: Nova setzt **keine Cookies** und lädt **kein Analytics/Tracking**
(geprüft – im UI-Code kommt weder Google Analytics noch ein Tag-Manager vor). Ein Cookie-Banner braucht es
nur auf einer **Website**. → Falls du eine Verkaufs-Website baust, dort umsetzen.

### ✅/🚫 Google Fonts lokal laden
Die App-Oberfläche lädt **keine** Google Fonts von Google (geprüft – keine `fonts.googleapis.com`-Verweise),
es landet also **keine IP bei Google**. Für die App bereits erfüllt. *Hinweis:* die Spaß-Seite `gods-eye.html`
lädt Fonts extern – die ist aber kein Teil des Produkts und läuft nur lokal; bei Bedarf lokal einbetten.

### ✅ Alle Fake-/Test-Bewertungen + Rezensionen zurücksetzen
Die **GitHub-Anzeige** (`docs/bewertungen.json` + README) ist auf **0** zurückgesetzt.
⚠️ **Die Live-Rezensionen auf deinem Feedback-Skript sind noch da** (6 Bewertungen, 3 öffentliche) – siehe
**„Offene Aktion: Live-Rezensionen löschen"** unten. Grund: dein Apps-Skript ist vermutlich **veraltet**
und kennt die Admin-/Lösch-Aktion nicht.

### ✅ Rezensionen: Name-Pflicht + Mindest-Nutzungszeit
Eine **öffentliche** Rezension braucht jetzt einen **Namen** (oder E-Mail/Kontakt) und ist erst nach
**20 Minuten Nutzung** absendbar (schreiben/ansehen vorher möglich). Internes Feedback bleibt anonym
möglich. Umgesetzt in `assistant/feedback.py`, mit Tests.

### 🚫/⚠️ „Upload-Speicher auf privat"
Nutzerdaten liegen **lokal** auf dem PC des Nutzers – nichts davon liegt „offen im Netz". Dein
**Premium-Repo ist privat**, Feedback geht an dein **privates** Google-Skript, Premium-Pakete über deinen
**eigenen** Lizenzserver. ⚠️ **Du prüfst:** dass dein Render-Dienst/Repo wirklich privat sind und keine
Schlüssel in Umgebungsvariablen aus Versehen öffentlich geloggt werden.

### ⚠️ Barrierefreiheit (Alt-Texte, Kontraste, Tastatur)
Ein **erster Pass** ist gemacht (Bild-Alt-Texte im README, Beschriftungen/`aria-label` an Icon-Knöpfen,
sichtbarer Tastatur-Fokus). ⚠️ **Noch offen / dein Blick:** vollständiger Kontrast-Check (WCAG AA) über alle
Zustände, komplette Tastatur-Bedienbarkeit aller Dialoge, Screenreader-Test. Eine echte
**Barrierefreiheits-Erklärung** ist nur für bestimmte Anbieter Pflicht (BFSG ab 2025 – prüfen, ob du
darunterfällst).

### ✅/⚠️ Bilder & Lizenzen
Im Repo sind nur **deine eigenen Screenshots** (`docs/bilder/*.png`) und **App-Icons**
(`web/kamera/v1/icons/*`). Keine fremden Stockfotos. ⚠️ **Bestätige:** dass die Icons selbst erstellt sind.
⚠️ Die `gods-eye.html` nutzt eine Erd-Textur von three-globe (NASA/öffentlich) extern – bei Produktnutzung
Quelle/Lizenz prüfen.

### ⚠️ Widerrufsbelehrung + Kündigungsbutton (sobald du verkaufst)
Eine **Muster-Widerrufsbelehrung** + **Muster-Widerrufsformular** liegt jetzt in `WIDERRUF.md` (Vorlage,
Platzhalter). ⚠️ **Kündigungsbutton:** in DE/EU für Dauerschuldverhältnisse (Abos) im Online-Vertrieb
**Pflicht** – lässt sich erst bauen, **wenn es ein Abo-/Bezahlsystem gibt** (noch nicht vorhanden). Mit
deinem Anwalt klären, sobald du Abos verkaufst.

---

## 🧭 Zwei größere Wünsche, die eine Grundsatz-Entscheidung brauchen

### 1) „Nutzer-Übersicht" – jetzt als ausdrückliches Opt-in gebaut ✅ (du hast zugestimmt)
Auf deinen Wunsch ist die **Nutzer-Übersicht als opt-in-Telemetrie** gebaut: **Standard AUS**, der Nutzer
muss in der App aktiv zustimmen (`/mitteilen an`). Dann sendet Nova **Geräte-Kennung, selbst gewählten
Namen, Stufe, Nutzungszeit, Version/OS** und – zur **manuellen** Prüfung – etwaige Sicherheits-Markierungen.
**Keine E-Mail**, außer der Nutzer gibt sie selbst an. Jederzeit widerrufbar. In der Datenschutzerklärung
(Abschnitt 3.9) als **Einwilligung** dokumentiert.

⚠️ **Noch nötig, damit es wirklich läuft:**
- Das **Feedback-Skript** (`packaging/nova-feedback.gs`) muss die neuen Aktionen `telemetrie`/`nutzer`/
  `nachricht`/`nachrichten`/`geraete_sperre` können und neu deployed werden (siehe Datei-Kommentare).
- Im **Generator** kommt ein Reiter **„Nutzer"** (Liste, Zeiträume, Nachricht senden, sperren).

⚠️ **Dein Blick / Anwalt:** Auch opt-in ist es personenbezogen – prüfe Einwilligungstext, Speicherdauer,
Löschkonzept (Recht auf Löschung) und dass die Zustimmung wirklich freiwillig und informiert ist. Dass du
Nutzern **Nachrichten schicken** kannst, ist Kundendienst – kein Werbekanal ohne gesonderte Einwilligung.

### 1b) Gratis-Nutzer sperren + „Neuinstallation unmöglich" – ehrliche Grenzen ⚠️
- ✅ **Gesperrt werden können jetzt auch Gratis-Nutzer:** Nova prüft beim Start eine **signierte**
  Geräte-Sperrliste und schaltet sich ab, wenn dein Gerät gesperrt ist (fail-open: kein Netz ≠ Sperre).
  Die Sperre entscheidest **du von Hand** – nichts ist automatisiert.
- ⚠️ **„Neuinstallation/Überlisten unmöglich" ist technisch NICHT erreichbar.** Die Geräte-Kennung ist jetzt
  **deutlich stabiler** (an mehreren Orten außerhalb des App-Ordners gespiegelt, notfalls aus einem
  Hardware-Merkmal abgeleitet) – ein bloßes Neuinstallieren/Daten-Löschen bringt also nichts mehr. **Aber**
  ein entschlossener Nutzer kann eine Sperre immer umgehen (neue Hardware, virtuelle Maschine, frisch
  aufgesetztes System, Dekompilieren der Exe). Ein 100 % fälschungssicheres, nicht-zurücksetzbares System
  gibt es auf fremder Hardware nicht – versprich das Nutzern/Kunden also nicht.
- ⚠️ **„Illegale Versuche im Sandbox-Modus merken":** Nova kann abgelehnte/verdächtige Aktionen als
  **Markierung** vormerken und (nur bei Zustimmung) zur **manuellen** Prüfung an dich melden. Es ist **kein**
  zuverlässiger „Legalitäts-Richter" – es erkennt nur, wenn die eingebauten Sicherheitsregeln ausgelöst
  haben. Automatisch sperren wäre riskant (Fehlalarme) und bleibt bewusst **deine** Handentscheidung.

### 2) „Namen aus der App ins Generator-Archiv (Zuordnung Name ↔ Key)"
Teilweise schon da, teils Telemetrie: Der **Name**, den ein Nutzer in einer **öffentlichen Rezension**
angibt, kommt ohnehin zu dir (Feedback-Skript). Aber „jeder Nutzer meldet sich mit Namen an, der automatisch
mit seinem Key in dein Archiv wandert" wäre wieder **Phone-Home** und bräuchte dieselbe DSGVO-Grundlage wie
Punkt 1. **E-Mail** nur, wenn der Nutzer sie ausdrücklich zur Weiterleitung angibt – das ist korrekt gedacht.
→ Gleiche Entscheidung wie oben; bis dahin: Namen trägst **du** beim Code-Erzeugen ins Archiv ein.

---

## ⚠️ Offene Aktion: Live-Rezensionen wirklich löschen
Dein Feedback-Skript (Google Apps Script) zeigt öffentlich noch **6 Bewertungen / 3 Rezensionen**. Meine
Admin-Abfrage lief ins Leere → das **deployte Skript ist veraltet** (wie der Render-Server). So wirst du sie
los – ein Weg reicht:

1. **Am einfachsten – die Tabelle leeren:** Öffne die **Google-Tabelle** hinter deinem Feedback-Skript
   (im Apps-Script-Editor: *Ressourcen/Übersicht → verknüpftes Spreadsheet*). Setze in der Spalte
   **„Sichtbar"** bei allen Zeilen **FALSE** (oder lösche die Zeilen). Fertig – die App zeigt dann 0.
2. **Oder Skript aktualisieren:** `packaging/nova-feedback.gs` neu in den Apps-Script-Editor kopieren →
   *Bereitstellen → Bereitstellungen verwalten → Neue Version*. Danach kannst du im **Generator → Reiter
   „Rezensionen"** die Einträge bequem per Knopf löschen (ist reversibel = „Wiederherstellen").

Die App holt Rezensionen stündlich neu; nach dem Löschen zeigt sie binnen ≤ 1 Stunde nichts mehr.

---

## Allgemein für deinen Anwalt
- **Verantwortlicher/Impressum/Kontakt** in `DATENSCHUTZ.md`, `LIZENZVERTRAG.md`, `WIDERRUF.md` ausfüllen.
- **Preise** sind bewusst noch nirgends hinterlegt – erst festlegen, dann eintragen.
- **Haftung/AGB** (`NUTZUNGSBEDINGUNGEN.md`) und **Lizenz** (`LIZENZVERTRAG.md`) sind Vorlagen – prüfen lassen.
- **Drittanbieter** (KI-Modelle, mail.tm, Vonage, Render, Google, GitHub, HuggingFace-Downloads für
  Stimmen): deren AGB/Datenschutz gelten zusätzlich; bei EU-Nutzern ggf. Auftragsverarbeitung/SCC prüfen.
