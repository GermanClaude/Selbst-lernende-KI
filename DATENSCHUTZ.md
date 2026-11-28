# Datenschutzerklärung

> **Wichtiger Hinweis:** Dies ist eine **Vorlage**, kein Rechtsrat. Datenschutzrecht hängt vom Land,
> vom konkreten Einsatz und von den Diensten ab, die du freischaltest. **Platzhalter in eckigen
> Klammern `[ … ]` musst du vor einer Veröffentlichung selbst ausfüllen.** Für eine ernsthafte oder
> kommerzielle Nutzung lass diese Erklärung von einer Anwältin/einem Anwalt prüfen und an deinen Fall
> anpassen. Diese Vorlage orientiert sich an der DSGVO.

Stand: **28.11.2026** (ab Version 0.77.0).

---

## 0. In einem Satz

Nova ist ein **Programm für deinen eigenen Computer**. Deine Gespräche, dein Gedächtnis und deine
Einstellungen bleiben **auf deinem Gerät**. Daten verlassen dein Gerät nur, wenn **du** eine Funktion
nutzt, die das nötig macht – vor allem, wenn du ein **KI-Modell eines fremden Anbieters** wählst. Wenn
du ein **lokales Modell** (Ollama/LM Studio) nutzt, verlassen deine Gespräche den Rechner **nicht**.

---

## 1. Verantwortlicher

Verantwortlich für die Verarbeitung personenbezogener Daten im Sinne der DSGVO ist der Herausgeber von
Nova:

```
[NAME bzw. FIRMA]
[ANSCHRIFT]
[LAND]
Kontakt: [E-MAIL]   (alternativ über die Feedback-Funktion in der App)
```

> **Hinweis zum Ausfüllen:** Die DSGVO verlangt, dass ein Verantwortlicher **benennbar und
> erreichbar** ist. Trage diese Angaben ein, **bevor** du Nova öffentlich anbietest oder
> Premium-Funktionen verkaufst. In einem **öffentlichen** Quelltext-Repository solltest du hier
> keine privaten Daten hinterlegen – fülle die Platzhalter erst in der veröffentlichten Fassung
> bzw. in der ausgelieferten App aus. Ein **Impressum** ist hier bewusst nicht enthalten; prüfe
> gesondert, ob für deinen Vertrieb eine Impressumspflicht besteht.

---

## 2. Grundprinzip: lokal zuerst

- Nova läuft **auf deinem Gerät** (Windows-App, Android-App).
- Dein **Gedächtnis**, dein **Gesprächsverlauf**, deine **Einstellungen** und deine **Schlüssel**
  werden **lokal** gespeichert (u. a. in den Ordnern `data/`, `config/` und `~/.nova…`).
- Du kannst dein Gedächtnis jederzeit **ansehen, ergänzen und löschen**.
- Es gibt **kein** zentrales Nutzerkonto, **keine** Werbung, **kein** Tracking, **keine** Analyse
  deines Nutzungsverhaltens und **keinen** Verkauf von Daten.

---

## 3. Welche Daten wohin gehen

Die folgende Übersicht zeigt, **wann** Daten dein Gerät verlassen. Fast alles ist **optional** und
hängt davon ab, welche Funktion du nutzt.

### 3.1 KI-Modelle fremder Anbieter (nur wenn du einen Cloud-Anbieter wählst)

Wählst du als „Gehirn" einen Cloud-Anbieter, werden deine **Eingaben** (Nachrichten, mitgegebener
Zusammenhang aus dem Gedächtnis, ggf. Bilder, Bildschirminhalte, Audio/Transkripte) an **dessen
Server** übertragen, damit er eine Antwort erzeugen kann. Mögliche Anbieter sind u. a.:

- **Anthropic (Claude)**, **OpenAI (ChatGPT)**, **DeepSeek**, **Google (Gemini)**,
  **Abliteration AI**, **Venice AI**, **NanoGPT**, **ElevenLabs** (Sprache), sowie
  **Bildgeneratoren**.

Für diese Anbieter gelten **deren eigene Datenschutzbestimmungen und Serverstandorte** (teils außerhalb
der EU, z. B. in den USA). Der Herausgeber von Nova hat darauf **keinen Einfluss**. Deine **API-/
Zugangsschlüssel** werden **lokal** auf deinem Gerät gespeichert und nur zur Verbindung mit dem von dir
gewählten Anbieter verwendet.

> **Nutzt du ein lokales Modell (Ollama/LM Studio), entfällt dieser Punkt – nichts wird gesendet.**

### 3.2 Premium-Freischaltung (Lizenzserver)

Wenn du **Premium** nutzt, prüft Nova deine Lizenz bei einem **Lizenzserver** (dem Cloud-Dienst des
Herausgebers, betrieben über den Hoster **[Render]**). Dabei werden übertragen:

- deine **Geräte-Kennung** (eine technische Kennung deiner Installation) und
- dein **Premium-Code**.

Zweck: die **Gültigkeit** der Lizenz, die **Gerätebindung**, eine etwaige **Laufzeit** und die
**Sperrliste** (bei Missbrauch) zu prüfen. **Inhalte deiner Gespräche werden dabei nicht übertragen.**
Rechtsgrundlage: **Vertragserfüllung** (Art. 6 Abs. 1 lit. b DSGVO) und **berechtigtes Interesse** an
der Verhinderung von Missbrauch/Raubkopien (Art. 6 Abs. 1 lit. f DSGVO).

### 3.3 Feedback & Bewertungen (nur wenn du aktiv absendest)

Sendest du über die **Feedback-Funktion** eine Rückmeldung oder Bewertung, werden übertragen:

- **Sterne** und dein **Text**, die **App-Version**, die **Art des Betriebssystems**, eine
  **Installations-Kennung** sowie – **nur wenn du sie angibst** – ein **Anzeigename** und eine
  **Kontaktangabe**, dazu bis zu **5 Bilder**, die du selbst anhängst.

Der Versand erfolgt per HTTPS an ein **Google-Apps-Skript** (Dienst von **Google**), das die Nachricht
an das Postfach des Herausgebers weiterleitet. **Name und Text werden nur dann öffentlich** (als
Rezension) angezeigt, wenn du das **ausdrücklich ankreuzt**. Rechtsgrundlagen: **Einwilligung**
(Art. 6 Abs. 1 lit. a DSGVO) für die Übermittlung und eine etwaige **Veröffentlichung**, sowie
**berechtigtes Interesse** an der Produktverbesserung (Art. 6 Abs. 1 lit. f DSGVO). Du kannst eine
veröffentlichte Rezension zurückziehen lassen – wende dich dazu an den Verantwortlichen.

### 3.4 Updates

Nova prüft bei **GitHub**, ob eine neue Version vorliegt, und lädt sie bei Bedarf herunter. Dabei sieht
GitHub technisch bedingt deine **IP-Adresse** und die Anfrage. Rechtsgrundlage: **berechtigtes
Interesse** an aktueller, sicherer Software (Art. 6 Abs. 1 lit. f DSGVO).

### 3.5 Wegwerf-E-Mail / Postfach (Premium, nur bei Nutzung)

Die Funktion **Wegwerf-E-Mail** nutzt den Fremddienst **[mail.tm]**. Temporäre Postfächer und die dort
empfangenen Nachrichten liegen auf **dessen** Servern; es gelten **dessen** Bedingungen und
Datenschutzregeln.

### 3.6 Konnektoren & Werkzeuge (nur bei Nutzung)

Nutzt du Werkzeuge oder **Konnektoren** (z. B. Internetsuche, GitHub, weitere MCP-Dienste), gehen die
jeweiligen **Anfragen** an den betreffenden Dienst. Du entscheidest, welche Konnektoren du einrichtest
und aktivierst.

### 3.7 Anrufe & Transkription (Premium, nur bei Nutzung)

Telefonie-Funktionen nutzen einen **Telefonie-Anbieter** (z. B. **[Vonage]**); dabei fallen bei diesem
Anbieter Verbindungs- und ggf. Audiodaten an. **Das Mitschneiden oder Transkribieren von Gesprächen kann
die Zustimmung aller Beteiligten erfordern** – dafür bist **du** verantwortlich (siehe
Nutzungsbedingungen).

---

## 4. Besondere Kategorien & Inhalte, die du eingibst

Was du Nova **anvertraust**, bestimmst **du**. Gibst du besonders schützenswerte Daten ein (z. B. zu
Gesundheit, Religion, Herkunft) oder Daten anderer Personen, so erfolgt das auf **deine**
Verantwortung; bei Nutzung eines Cloud-Modells werden auch diese Inhalte an den gewählten Anbieter
übertragen. Überlege bei sensiblen Inhalten, ob du ein **lokales Modell** nutzt.

---

## 5. Speicherdauer

- **Lokale Daten** (Gedächtnis, Verlauf, Einstellungen) bleiben auf deinem Gerät, **bis du sie
  löschst**. Du kannst sie jederzeit entfernen.
- **Feedback/Bewertungen** werden beim Herausgeber so lange aufbewahrt, wie es für Auswertung und
  Anzeige nötig ist, bzw. bis zu deinem Widerruf.
- **Lizenzdaten** (Kennung, Code-Status) werden so lange verarbeitet, wie es für die Lizenzprüfung und
  die Missbrauchsabwehr erforderlich ist.

---

## 6. Empfänger / Auftragsverarbeiter

Je nach genutzter Funktion können Daten an folgende Stellen gelangen: die von dir gewählten
**KI-Anbieter** (Abschnitt 3.1), der **Hoster des Lizenzservers** (**[Render]**), **Google** (Feedback),
**GitHub** (Updates) sowie weitere von dir aktivierte **Konnektoren/Anbieter**. Soweit diese Stellen
in deinem Auftrag bzw. im Auftrag des Herausgebers tätig werden, sind entsprechende Vereinbarungen zur
**Auftragsverarbeitung** abzuschließen (vom Herausgeber auszufüllen/zu prüfen).

---

## 7. Übermittlung in Drittländer

Einige Anbieter (insbesondere KI-Anbieter) verarbeiten Daten **außerhalb der EU/des EWR** (z. B. in den
USA). Für solche Übermittlungen stützen sich die jeweiligen Anbieter in der Regel auf
**Standardvertragsklauseln** oder einen **Angemessenheitsbeschluss**. Die Einzelheiten findest du in den
Datenschutzbestimmungen des jeweiligen Anbieters.

---

## 8. Deine Rechte

Du hast nach der DSGVO das Recht auf **Auskunft** (Art. 15), **Berichtigung** (Art. 16), **Löschung**
(Art. 17), **Einschränkung der Verarbeitung** (Art. 18), **Datenübertragbarkeit** (Art. 20) und
**Widerspruch** (Art. 21). Eine erteilte **Einwilligung** kannst du jederzeit mit Wirkung für die
Zukunft **widerrufen** (Art. 7 Abs. 3). Außerdem hast du ein **Beschwerderecht bei einer
Datenschutz-Aufsichtsbehörde** (Art. 77).

Da ein Großteil der Daten **nur lokal** auf deinem Gerät liegt, kannst du viele dieser Rechte
**unmittelbar selbst** ausüben (ansehen, ändern, löschen). Für Daten, die beim Herausgeber liegen
(z. B. Feedback, Lizenzstatus), wende dich an den **Verantwortlichen** (Abschnitt 1).

---

## 9. Keine automatisierte Entscheidung mit Rechtswirkung

Nova trifft **keine** rechtlich oder ähnlich erheblich wirkende Entscheidung allein automatisiert über
dich im Sinne des Art. 22 DSGVO. KI-Ausgaben sind **Vorschläge** – **du** entscheidest, was geschieht.

---

## 10. Sicherheit

Verbindungen zu Diensten erfolgen über **HTTPS**. Schlüssel und PINs werden lokal gehalten; sensible
Schutzmechanismen sind verschlüsselt. Eine absolute Sicherheit kann – wie bei jeder Software – nicht
garantiert werden. Lege **Sicherungskopien** wichtiger Daten an.

---

## 11. Minderjährige

Unzensierte Modelle und bestimmte Funktionen sind **nicht für Minderjährige** bestimmt (siehe
Nutzungsbedingungen).

---

## 12. Änderungen dieser Erklärung

Diese Datenschutzerklärung kann angepasst werden, wenn sich Funktionen oder genutzte Dienste ändern. Es
gilt die zum Zeitpunkt der Nutzung veröffentlichte Fassung (siehe „Stand" oben).

---

*Siehe auch:* [Nutzungsbedingungen & Haftungsausschluss](NUTZUNGSBEDINGUNGEN.md) ·
[Lizenzvertrag (EULA)](LIZENZVERTRAG.md)
