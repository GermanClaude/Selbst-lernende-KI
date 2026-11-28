# Neuigkeiten

Jede Version hat hier einen Abschnitt `## <Version> – <Datum>`. Der Updater zeigt
beim Aktualisieren alle Abschnitte zwischen deiner und der neuen Version an, und
deine KI erklärt sie dir in eigenen Worten.

## 0.65.0 – 2026-11-28

- **Wegwerf-E-Mail: mehrere Postfächer (Premium):** Deine Wegwerf-Postfächer bleiben
  jetzt erhalten – legst du ein neues an, bleibt das alte bestehen, und du kannst
  jederzeit zwischen ihnen wechseln. Du kannst dir auch einen **eigenen Namen** (und
  eine Domain aus der Liste) wünschen. So nutzt du sie fast wie echte Adressen.

## 0.64.0 – 2026-11-28

- **Wegwerf-E-Mail (Premium):** Nova kann dir ein temporäres Postfach anlegen und
  reinschauen – praktisch für Anmeldungen, bei denen du nicht deine echte Adresse
  angeben willst. Nova holt dir daraus z. B. auch den Bestätigungs-Code. Erscheint in
  der Premium-Übersicht. (Nur für Zeug zum Wegwerfen – nichts Wichtiges darüber laufen lassen.)

## 0.63.0 – 2026-11-28

- **Echtheits-Nachweis fürs Premium-Paket (Wasserzeichen):** Das Premium-Paket trägt
  jetzt ein verstecktes, signiertes Eigentums-Kennzeichen. Nova zeigt im Status, dass
  die Herkunft signiert ist, und der Entwickler kann jederzeit beweisen, dass der Code
  von ihm stammt – nur sein privater Schlüssel kann diese Unterschrift erzeugen. Das
  schützt gegen Nachbau/Diebstahl. Für normale Nutzer ändert sich nichts.

## 0.62.0 – 2026-11-28

- **Premium-Übersicht – was jede Stufe kann:** Eine neue Übersicht zeigt alle Stufen
  (Premium / Premium Max / Entwickler) mit ihren Funktionen und hebt deine aktuelle
  Stufe hervor. Im Fenster per Klick auf das Premium-Abzeichen oben rechts (oder
  „Alle Stufen ansehen" im Premium-Dialog), im Terminal mit `/funktionen`.

## 0.61.0 – 2026-11-28

- **Codegenerator verschlüsselt abgelegt (nur Entwickler):** Der private Codegenerator
  liegt im geschlossenen Repo jetzt nur noch verschlüsselt – selbst mit Lesezugriff
  bekäme niemand lesbaren Generator-Code zu sehen. Entschlüsselt wird er erst lokal
  auf deinem PC, wenn du dein Generator-Passwort eingibst. Für normale Nutzer ändert
  sich nichts; das betrifft nur die Entwickler-Werkzeuge.

## 0.60.0 – 2026-11-28

- **Jemanden anrufen – sicherer Dialer:** Nova hilft dir jetzt beim Anrufen
  anderer. Sag ihr z. B. „ruf beim Zahnarzt an, hier ist die Nummer" oder gib ihr
  eine Nummer von einer Webseite – sie öffnet den Telefon-Dialer (am Handy oder am
  PC) mit der Nummer schon eingetippt. **Anrufen musst du selbst** – Nova wählt nie
  von allein. (Das ist etwas anderes als „ruf mich an": dort ruft Nova mit
  KI-Stimme nur deine eigene hinterlegte Nummer an.)

## 0.59.0 – 2026-11-28

- **Stufe ohne Code freischalten (No-Code-Upgrade):** Der Entwickler kann einem
  Gerät eine Stufe jetzt direkt über die Geräte-Kennung geben – du musst keinen
  Code mehr abtippen. Beim nächsten „Jetzt prüfen“ holt Nova die Freischaltung
  automatisch, und die Stufe bleibt nach jedem Update erhalten. So muss nach einem
  Update niemand mehr einen neuen Schlüssel anfordern. Sicher bleibt alles: jede
  Freischaltung ist – wie ein Code – an genau dein Gerät gebunden und vom Entwickler
  unterschrieben; eine Sperre hat weiterhin Vorrang.

## 0.58.0 – 2026-11-27

- **Agenten-Fenster (Premium Max):** Für eine große Aufgabe kann Nova jetzt mehrere
  echte, sichtbare Helfer-Fenster öffnen – jedes eine eigene Nova. Nova entscheidet,
  wie viele es braucht, gibt jedem einen Namen und eine Teilaufgabe, dirigiert sie
  vom Hauptfenster aus und teilt die Arbeit auf, damit es schneller geht. Du kannst
  den Agenten nicht hineinreden; nur Nova gibt ihnen Aufträge. Alles, was sie machen,
  wird mitprotokolliert; wenn die Arbeit fertig ist, schließt Nova die Fenster wieder
  und merkt sich das Wichtige. (Nova fragt kurz nach, bevor Fenster aufgehen.)

## 0.57.1 – 2026-11-27

- **Dein Zugang bleibt über Updates erhalten:** Deine gekaufte Stufe (und wie lange
  sie gilt) liegt in Daten, die ein Update nie anfasst – ein Update nimmt dir also
  nie dein Premium. Sollte nach einem Update das Premium-Zubehör fehlen, holt Nova
  es jetzt **von selbst** wieder, ohne dass du einen Code neu eingeben musst.
  (Ein Zugang verschwindet nur, wenn er abläuft oder der Entwickler ihn sperrt.)

## 0.57.0 – 2026-11-27

- **Schlüssel nur noch mit Befehl einlösen:** Wenn du nur einen Schlüssel ins Feld
  tippst (ohne `/novaaiupdate` davor), wird er **nicht mehr automatisch** aktiviert.
  So kann ein Code nicht mehr aus Versehen eingelöst werden. Zum Einlösen schreibst
  du jetzt bewusst: `/novaaiupdate <dein Schlüssel>`.
- **Fenster startet bei Moduswechsel neu:** Wenn sich dein Zugang ändert – entzogen,
  abgelaufen oder hoch-/heruntergestuft – schließt sich das alte Fenster und ein
  frisches öffnet sich, damit sofort der richtige Stand gilt. Das passiert von selbst
  (Nova schaut regelmäßig nach) und auch, wenn du auf „Jetzt prüfen" gehst.

## 0.56.0 – 2026-11-27

**Individuelle Premium-Abos**
- Ein Premium-Zugang kann jetzt einen **eigenen Namen** tragen (z. B. „Premium Sandbox") – der erscheint dann
  in Nova statt „Premium Max". Und er kann **genau die Funktionen** enthalten, die dazugebucht wurden
  (à la carte) statt immer das ganze Paket. Beides steckt sicher (mitunterschrieben) im Code und gilt weiter
  nur für das eine Gerät.

## 0.55.1 – 2026-11-27

**Fehler behoben**
- **`/sandbox` stürzte ab** („argument of type 'NoneType' is not iterable"), wenn gerade ein Programm mit
  Sonderzeichen im Namen lief – die Prozessliste war dann nicht lesbar. Behoben; die Sandbox startet wieder.

## 0.55.0 – 2026-11-27

**Unter der Haube**
- Verbesserungen rund um die Premium-Einrichtung und die Entwickler-Werkzeuge. Für normale Nutzer ändert
  sich nichts an der Bedienung.

## 0.54.1 – 2026-11-27

**Fehler behoben: „Charakter & Profil" und App-Freeze**
- „Charakter & Profil" öffnete versehentlich das **Premium-Fenster** statt der Profil-Einstellungen –
  und beim Schließen fror die ganze App ein, sodass nur ein Neustart half. Ursache war eine vertauschte
  Fenster-Zuordnung im App-Code. Jetzt öffnet der Knopf wieder das volle Profil-Fenster mit allen Reitern
  (Charakter, Stil, Über mich, Werte, Gedächtnis, Skills, Sicherheit, Gehirn) – alles wieder individuell
  einstellbar wie zuvor. Kein Einfrieren mehr.

## 0.54.0 – 2026-11-27

**Zugangs-Tresor: Nova kann sich für dich anmelden – deine Passwörter bleiben lokal**
- Neuer verschlüsselter Tresor für deine Logins (Dienst, Benutzer, Passwort). Alles liegt **nur auf deinem
  Gerät**, verschlüsselt mit einem **Haupt-Passwort**, das nie gespeichert wird und das Gerät nie verlässt.
- **Nova sieht deine Passwörter nie.** Das Werkzeug gibt Passwörter grundsätzlich nicht als Text aus und nimmt
  auch keines im Chat entgegen – beim Anmelden tippt die App Benutzer und Passwort direkt ins Login-Feld, am
  Modell und am KI-Anbieter vorbei. So kann Nova z. B. Instagram oder dein E-Mail-Konto für dich öffnen und
  Nachrichten schreiben, ohne dass irgendwer an die Zugangsdaten kommt.
- Die Tresor-Datei ist für alle Werkzeuge gesperrt. Selbst wer sie stiehlt, hat ohne dein Haupt-Passwort
  nichts. Jede Installation hat ihren eigenen lokalen Tresor – es gibt keinen Server, auf dem Passwörter
  liegen, also nichts zentral abzugreifen.
- Bedienen mit `/zugang` (einrichten, öffnen, `passwort <Dienst>`, Liste, entfernen). Nach 30 Minuten ohne
  Nutzung schließt sich der Tresor von selbst.

**`/simulate` – alles gefahrlos zur Probe laufen lassen**
- `/simulate <was Nova tun soll>` startet eine **frische Test-Nova** in einem eigenen Fenster, die genau
  diesen Auftrag in deinen Worten ausführt – mit eigenem, leerem Gedächtnis und eigener vorgegaukelter
  Hardware. Ideal, um z. B. zu prüfen, ob die Diagnose wirklich beim Entwickler ankommt, ohne deine echte
  Nova anzufassen.

**Premium 1.5 (mit gültigem Code)**
- **Agententeam** (`premium_agententeam`): Für große Aufgaben teilt Nova die Arbeit auf mehrere eigenständige
  Agenten auf (Recherche, je Teilschritt ein Helfer, am Ende ein Prüfer) und fasst das Ergebnis zusammen. Geht
  auch ohne Agenten – dann bekommst du einen klaren Plan, den Nova selbst abarbeitet.

**Sicherheit – nochmal geprüft**
- Vollständiger Scan beider Repos und der Codegenerator-EXE: **kein GitHub-Token, kein Paket-Schlüssel, keine
  echten Codes** irgendwo im Code. Ein Premium-Code enthält nur `{Gerät, Stufe, Laufzeit, Frist, Nummer,
  Serveradresse}`. Der Repo-Token liegt allein als Umgebungsvariable auf deinem Lizenzserver und lässt sich
  jederzeit wechseln, ohne dass ein einziger Code neu ausgegeben werden muss (siehe cloud/ANLEITUNG.md).

## 0.53.0 – 2026-11-27

**Neues Aussehen: Nova als Kommandozentrale**
- **Vier Stile** zum Aussuchen (Knopf mit der Farbpalette oben rechts – oder sag Nova einfach
  „mach dich cooler“):
  - **Cockpit** (neu, Standard): seriös und übersichtlich. Deine Aufträge stehen als klare Befehlszeilen,
    Novas Antworten als Berichtskarten.
  - **Neon**: dunkel und cool, mit leuchtendem HUD, Gitter-Hintergrund und Cyan-Akzenten.
  - **Einfach**: ganz reduziert, mit großer Kugel, großen Knöpfen und nur dem Wichtigsten. Das Menü öffnest
    du über ☰.
  - **Klassisch**: das bisherige Aussehen mit Chat-Blasen.
- **Status-Deck** unter der Kopfzeile (Cockpit/Neon): Gehirn, Prozessor- und Arbeitsspeicher-Auslastung
  live, was Nova gerade tut, Kosten, Uhrzeit.
- **Sprachmodus als HUD**: rotierende Ringe um die Kugel, Eckmarken, Uhrzeit und Systemwerte am Rand.

**Neue Werkzeuge für alle**
- **Rechner** (rechnet exakt statt im Kopf), **Einheiten umrechnen**, **Datum rechnen** (Wochentag,
  Kalenderwoche, Tage/Werktage zwischen zwei Daten), **Wetter** (ohne Schlüssel, Quelle open-meteo.com)
  und **PC-Auslastung**.
- **Skill-Bibliothek**: acht fertige Regeln, die Nova sparsamer, sorgfältiger oder vorsichtiger machen
  (z. B. „Sparsam“, „Selbst-prüfen“, „Sicher“). `/skill vorlagen` zeigt sie, `/skill vorlage Sparsam`
  schaltet eine ein.

**Premium 1.4** (mit gültigem Code)
- **PC-Gesundheitscheck**: Speicherplatz, größte Dateien, Autostarts, mit Tipps. Nova schaut nur und
  ändert nichts.
- **Lernkarten** mit Wiederholungssystem: Nova erstellt Karteikarten zu jedem Thema und fragt dich ab.
- **Gewohnheiten-Tracker** mit Serien und **Haushaltsbuch** mit Budgets und Monatsauswertung.
- **Premium Max – Ordner-Autopilot**: sortiert z. B. deinen Downloads-Ordner nach Dateityp, mit Vorschau
  und Rückgängig.

**Sicherheit**
- Premium lässt sich nicht mehr durch Bearbeiten von Dateien verlängern oder hochstufen. Die Laufzeit
  ergibt sich nur noch aus unterschriebenen Codes.
- Nova liest und ändert keine Zugangsdaten außerhalb ihres Ordners (SSH-Schlüssel, gespeicherte
  GitHub-/Git-/Cloud-Zugänge, den Premium-Signierschlüssel). Ein Befehl, der darauf zugreift, fragt immer
  nach, auch bei Vollzugriff. Im AFK-Modus geht das gar nicht.
- Neue automatische Angriffstests für den App-Server.

## 0.52.0 – 2026-11-27

**Sicherheit: Premium-Codes enthalten nichts Geheimes mehr**
- Ein Premium-Code war bisher für jeden lesbar und trug einen Zugang zum privaten Premium-Speicher in sich.
  Das ist vorbei: **Codes enthalten jetzt nur noch Gerät, Stufe, Laufzeit und die Adresse des
  Lizenzservers.** Das Premium-Paket gibt allein die Cloud-Nova des Entwicklers heraus – erst nachdem sie
  den Code geprüft hat (Unterschrift, Gerät, Ablauf, Sperrliste). Ein Gerät hält nie wieder einen Schlüssel.
- Alte, gespeicherte Zugänge werden beim nächsten Start automatisch vom Gerät gelöscht.
- Auch ein gefälschter Server kann kein fremdes Paket unterschieben: Nova lädt nur, was der Entwickler
  unterschrieben hat.
- Der Test-Modus (Simulation) lädt nie mehr das echte Premium-Paket, und sein Code steht nicht mehr im
  Klartext im Programm.
- Discord-Webhook-Adressen und neue GitHub-Token werden in Protokollen und Ausgaben jetzt geschwärzt.

**Rezensionen**
- **Öffentlich rezensieren geht jetzt einmal pro Woche** (pro Installation). Sterne und Feedback kannst du
  jederzeit schicken – nur der Haken „öffentlich zeigen“ ist bis zum angezeigten Datum gesperrt. Das
  Postfach prüft es zusätzlich.
- Der Entwickler kann öffentliche Rezensionen nach eigenem Ermessen **löschen** (ausblenden) und
  wiederherstellen.

## 0.51.0 – 2026-11-26

**Premium anfragen (Test-Ablauf, noch nicht für alle sichtbar)**
- Ein neuer **Premium**-Knopf in der Seitenleiste öffnet ein Fenster: es zeigt, was Premium bietet, und du
  kannst eine **Anfrage** stellen (Stufe, Laufzeit, Notiz). Ein Betrag ist dabei ausdrücklich eine
  **Simulation – es wird kein Geld abgebucht und keine Zahlungsdaten erhoben.** Die Anfrage geht mit deiner
  anonymen Geräte-Kennung an den Entwickler (per E-Mail und, wenn eingerichtet, Discord-Webhook
  `NOVA_DISCORD_WEBHOOK`). Du bekommst dann einen Code zum Einlösen.
- Der Knopf ist vorerst nur im Test sichtbar (Simulation/Entwicklermodus oder `NOVA_PREMIUM_SHOP=1`).

## 0.50.0 – 2026-11-26

**Premium: Finanz- & Börsen-Coach für Einsteiger**
- Neues Premium-Werkzeug **Finanzcoach**: erklärt dir die Börse, Aktien, ETFs, Zinsen, Risiko und
  Finanzbegriffe einsteigerfreundlich und ordnet öffentliche Marktdaten ein. Es ist bewusst ein **Lern-Coach**:
  **keine Anlageberatung**, keine persönlichen Kauf-/Verkaufsempfehlungen, und es handelt nichts – jede
  Entscheidung triffst du selbst auf eigenes Risiko. Ein entsprechender Hinweis steht jetzt auch im
  Rechtlichen der App.

## 0.49.0 – 2026-11-26

**Große Tour mit Sprachausgabe + Nova darf Premium erklären**
- **Neue, vorgelesene Tour (`/tour2`):** Neben der bisherigen Tour gibt es jetzt eine ausführliche, die dir
  jeden Schritt **vorliest** und alle Funktionen und Befehle genauer erklärt – vom Chat über Sprachmodus,
  Gehirn/Modelle, Internet, Dateien, Gedächtnis, Sicherheit, AFK, Live-Sehen, Handy, Anrufe, Cloud, Wachwort
  und Zeitplan bis zu den Befehlen. Mit dem Lautsprecher-Knopf schaltest du die Stimme an/aus (sie nutzt die
  Stimme deines Systems, läuft offline).
- **Nova bewirbt Premium:** Fragt jemand, was Premium kann oder kostet, erklärt Nova jetzt die Vorteile und
  wie man es freischaltet – nur den Code und den internen Aufbau gibt sie weiterhin nicht preis.

## 0.48.0 – 2026-11-26

**Premium-Feier, edlerer Startbildschirm, Fehler nach dem Freischalten behoben**
- **Fehler behoben:** Direkt nachdem Premium freigeschaltet wurde, konnte die nächste Nachricht bei Claude einen
  Fehler „Invalid signature in thinking block" auslösen (weil mitten im Gespräch neue Werkzeuge dazukamen). Das
  ist jetzt abgefangen – Premium-Funktionen stehen sofort bereit, ohne Fehler.
- **Große Freier-Animation:** Wenn du Premium freischaltest, feiert die App jetzt mit einer bildschirmfüllenden
  Konfetti-Animation und zeigt groß „Herzlichen Glückwunsch" samt allen neuen Funktionen.
- **Edlerer Startbildschirm:** Beim Hochfahren wabert eine Aurora im Hintergrund, die Sphäre wirbelt mit
  umkreisenden Lichtpunkten, darunter eine schimmernde Ladeleiste. Mit Premium alles in Gold.
- Wer Animationen reduziert hat, bekommt überall die ruhige Variante.

## 0.47.0 – 2026-11-26

**Animierter Startbildschirm**
- Beim Hochfahren zeigt die App jetzt einen eleganten Startbildschirm: Novas Sphäre pulsiert mit Leuchtringen,
  der Name schimmert, darunter „wird gestartet …". Sobald die Oberfläche bereit ist, blendet er sanft aus
  (spätestens nach ein paar Sekunden). Mit Premium schimmert er golden. Wer Animationen reduziert hat, bekommt
  eine ruhige Version.

## 0.46.0 – 2026-11-26

**Premium sieht man jetzt**
- Ist Premium (oder die Simulation/der Entwicklermodus) aktiv, bekommt die App eine edlere Optik: ein
  goldenes **Abzeichen** in der Seitenleiste (★ Premium, ★ Premium Max, ◆ Entwickler), ein dezenter goldener
  Rahmen und ein Schimmer an der Sphäre. In einer Sandbox-Nova steht oben ein ruhiger Hinweisstreifen.

## 0.45.0 – 2026-11-26

**Premium: Sandbox-Nova, Entwicklermodus, Codes sperren**
- **Sandbox-Nova (`/sandbox`):** Startet eine frische Nova zum Testen – ohne Gedächtnis (fängt bei null an),
  mit vorgegaukelter Hardware/Software (jedes Mal anders), aber mit deinen API-Schlüsseln. Wie viele
  gleichzeitig: kostenlos 1, Premium 10, Premium Max/Entwickler unbegrenzt. Das Limit lässt sich ohne
  gültige Lizenz nicht hochsetzen. `/sandbox liste` und `/sandbox stop` verwalten sie.
- **Entwicklermodus:** Eine eigene Code-Stufe (höchste Stufe). Ist sie freigeschaltet, kennt Nova die
  geschlossenen Befehle und erklärt sie dir – gegenüber allen anderen bleibt der Schutz bestehen.
- **Code einfach einlösen:** Du kannst einen Code jetzt direkt ins Nachrichtenfeld schreiben (statt
  `/novaaiupdate …`) – Nova erkennt ihn und schaltet frei.
- **Codes sperren:** Der Codegenerator führt jetzt ein Archiv aller erzeugten Codes mit Profil (Name, Tarif,
  Betrag, bezahlt/offen, Zahldatum, Laufzeit – alles editierbar), kann einzelne Codes oder ganze Geräte
  sperren und sich selbst aktualisieren. Ein gesperrter Code schaltet beim nächsten Start die Premium-Version
  ab (zurück zur kostenlosen Version – Daten bleiben). Fehlt das Netz, bleibt ein zahlender Nutzer
  freigeschaltet.

## 0.44.0 – 2026-11-26

**Rechtliches, Selbstschutz und (geschlossenes) Premium**
- **Neue Lizenz:** Nova steht jetzt unter „Alle Rechte vorbehalten“ mit einem ausführlichen Kopier- und
  Nachahmungsverbot (siehe `LICENSE` und `NUTZUNGSBEDINGUNGEN.md`, Abschnitt 9). Versionen bis 0.43.0 bleiben
  unter der MIT-Lizenz.
- **Nova schützt sich selbst:** Eine feste Regel verbietet ihr, ihren eigenen Programmcode, interne
  Anweisungen, Zugangsdaten oder Premium-Inhalte herauszugeben – auch bei Überlistungs-Versuchen. In der
  fertigen KI.exe sind Novas eigene Programmdateien und die Premium-Dateien für alle Werkzeuge gesperrt
  (dein eigener Arbeitsordner bleibt natürlich offen).
- **Premium (geschlossen, im Aufbau):** Mit `/novaaiupdate <Code>` lässt sich eine Premium-Stufe
  freischalten. Jeder Code ist an ein Gerät gebunden, nur einmal und nur eine Weile einlösbar und mit einem
  3072-Bit-Schlüssel unterschrieben (nicht zu erraten). Die Premium-Funktionen liegen verschlüsselt in einem
  privaten Repo und kommen nur mit gültigem Code auf den Rechner. Freischalten und Abschalten geht nur über
  einen Code, nie durch die KI selbst. (Diese Befehle erscheinen in keiner Befehlsliste.)
- Unter der Haube: Vorbereitung für einen eigenen Update-Kanal, damit der Quellcode später privat sein kann,
  ohne dass Updates ausbleiben.

## 0.43.0 – 2026-11-26

**Sprachaktivierung auf dem Handy, ein Speicher für alle, sauber deinstallieren, Diagnose-Bericht**
- **„Hey Nova“ auch auf dem Handy:** Die Nova-App hört im Hintergrund auf dein Wachwort, auch wenn sie zu
  ist. Dann öffnet sie sich, hört deinen Befehl, schickt ihn an Nova und liest die Antwort vor. „Hey Nova,
  wie wird das Wetter?“ geht auch in einem Satz. Das Wort ist frei wählbar, am Handy wie am PC
  (`/wachwort wort …`). „Gleich zuhören“ lässt sich abschalten. Ausschalten geht über die Mitteilung
  „Nova hört zu“, in der App, oder du sagst es Nova.
- **Ein Speicher für PC, Handy und Cloud:** Der Gedächtnis-Abgleich über dein privates GitHub-Repo teilt jetzt
  auch „Über mich“, die Persönlichkeit, deine Skills, die Telefon-Persona und den Zeitplan. Schlüssel und
  Rechte bleiben auf jedem Gerät für sich.
- **`/deinstallieren`:** Nova fragt, ob du deine Erinnerungen behalten willst. Wenn ja, legt sie eine Sicherung
  (ZIP) auf den Desktop, mit Gedächtnis, Einstellungen und Arbeitsordner, aber ohne Schlüssel. Sonst löscht
  sie alles, und bei „alles löschen“ fragt sie noch ein zweites Mal nach. Dann entfernt sie den
  Hintergrund-Lauscher, die Autostarts und die Verknüpfungen und löscht ihre Dateien (nur ihre eigenen).
  `/sicherung` legt jederzeit eine Sicherung an, `/sicherung einspielen <Datei>` lädt sie wieder. In der
  Handy-App gibt es den Knopf „Nova-App deinstallieren“.
- **Diagnose-Bericht (`/diagnose`):** Wenn etwas nicht geht, schickt Nova auf Wunsch einen Bericht an den
  Entwickler: Version, System, Hardware, letzte Fehler und Protokollzeilen. Schlüssel, Benutzername,
  E-Mail-Adressen, Telefonnummern, Gespräche und das Gedächtnis sind nie dabei, und du kannst den Bericht
  vorher ansehen. Stürzt Nova schon beim Start ab, bietet sie den Bericht von selbst an. Gesendet wird nur
  nach deinem Ja.

## 0.42.0 – 2026-11-26

**Nova überall – auch ohne PC, auch ohne geöffnete App**
- **Handy-Steuerung über die Nova-Handy-App:** Nova bedient dein Android-Handy wie mit dem Finger: Apps
  öffnen, Bildschirm lesen, tippen, schreiben, wischen, Tasten, Lautstärke, Musik, Taschenlampe,
  Benachrichtigungen, Nummer wählen, SMS vorbereiten. Das läuft im Hintergrund, auch wenn die App zu ist,
  und klappt mit jedem KI-Modell. Mit der Cloud-Nova geht es sogar, wenn der PC aus ist. Ganz ohne Termux und
  ohne Kabel. Einschalten: in der App Zurück-Taste → „Handy-Steuerung einschalten“.
- **Anrufe aus der Cloud:** Die Cloud-Nova ruft dich an, auch wenn PC und App aus sind. Vonage meldet sich
  dabei direkt bei ihr, ein Tunnel am PC ist nicht nötig.
- **Telefonieren mit Nova:** Sag „ruf mich an“. Am Telefon sagst du dann, was sie tun soll (auch mehrere
  Sachen hintereinander), sie erledigt es mit allen Werkzeugen und antwortet dir im selben Anruf. Vor heiklen
  Schritten fragt sie dich am Telefon („Darf ich …? Ja oder nein“). Zum Beenden sagst du „tschüss“
  (nur mit Vonage).
- **Zeitplan:** „Ruf mich morgen um 8 an“, „jeden Werktag um 7 das Wetter aufs Handy“, „in 20 Minuten an
  den Herd erinnern“. Nova macht das dann von selbst, in der Cloud rund um die Uhr. `/zeitplan` zeigt
  alles.
- **Wachwort am PC:** Sag „Hey Nova“ (oder dein eigenes Wort). Nova startet bzw. kommt nach vorne, und zwar
  auf einem Bildschirm, auf dem gerade kein Spiel oder Vollbild läuft. Die Spracheingabe geht gleich an
  (abschaltbar: `/wachwort sprechen aus`, oder sag es Nova). Der Lauscher ist klein, läuft offline im
  Hintergrund, startet beim Anmelden mit und hört nur auf das Wachwort. Einschalten: `/wachwort an`.

## 0.41.0 – 2026-11-26

**Nova bedient jede App – mit jedem KI-Modell**
- Bisher brauchte Nova zum Bedienen von Programmen ein Bildschirmfoto – das können nur Modelle, die Bilder
  sehen. Jetzt liest sie Fenster, Knöpfe, Felder und Menüs **als Text** über die Bedienungshilfen von
  Windows. Damit steuern auch DeepSeek & Co. jedes Programm: „Öffne Spotify und spiel meine Playlist“,
  „Trag in Excel … ein“, „Klick in den Einstellungen auf Bluetooth“.
- Neue Werkzeuge:
  - **Programme starten** nach Namen (alles aus dem Startmenü, auch Store-Apps) oder Dateien/Adressen öffnen
  - **Fenster** auflisten, nach vorne holen, minimieren, maximieren, schließen
  - **App bedienen:** Knöpfe klicken, Felder ausfüllen, Text lesen, Menüs aufklappen
  - **Bildschirm-Text:** Texterkennung mit Position – „klick auf ‚Weiter‘“, auch in Apps ohne Bedienungshilfen
  - **Maus** (klicken, ziehen, scrollen), **Tastatur** (tippen, Tastenkombinationen, Lautstärke, Musik),
    **Zwischenablage**, **laufende Programme** (anzeigen, hängende beenden)
- Alles mit Windows-Bordmitteln – keine Zusatzprogramme nötig. Tippen und Klicken klappt jetzt auch ohne
  das Zusatzpaket „pyautogui“.
- Sicher: Nova fragt vor dem Bedienen nach (wie immer abschaltbar mit `/stuetzraeder aus` bzw. `alles`).
  In ihr **eigenes** Fenster klickt und tippt sie nie (sonst könnte sie sich selbst Rechte geben),
  Passwortfelder liest und füllt sie nicht, und Windows selbst beendet sie nicht.

## 0.40.0 – 2026-11-26

**Plugins für alle KI-Modelle**
- Du kannst Nova jetzt **Plugins** geben – zusätzliche Werkzeuge, die jedes Modell nutzen kann (Claude,
  DeepSeek, Gemini, ChatGPT, Ollama …). Plugins sind „MCP-Server“, der offene Standard für KI-Werkzeuge:
  Es gibt tausende fertige (Kalender, Notion, GitHub, Datenbanken, Browser …).
- Einfügen geht wie bei Claude Desktop: die Konfiguration aus der Anleitung des Plugins kopieren und
  `/plugins einfuegen {…}` schreiben. `/plugins` zeigt, was läuft. `/plugins aus|an|entfernen <name>`.
- Sicher: Vor jedem Plugin-Aufruf fragt Nova nach (abschaltbar pro Plugin mit `/plugins vertrauen <name>`),
  Plugins bekommen keine deiner Schlüssel, und was sie zurückgeben, nimmt Nova als Daten, nicht als Befehl.

**Sicherheits-Check: die 10 typischen Lücken geprüft und abgedichtet**
- Geprüft wurden u. a. Schadcode in Namen, fremde IDs in Adressen, versteckte Admin-Seiten, Schlüssel im
  Browser, offene Datentabellen, ausgetrickste KI-Regeln, Rechte erschleichen, Codes erraten, `.env` auf
  GitHub und gefälschte Uploads. Das meiste war schon dicht – jetzt zusätzlich:
- **Deine Schlüssel bleiben geheim, auch wenn Nova ausgetrickst wird:** Befehle, die Nova ausführt, sehen
  keine API-Schlüssel und Tokens mehr, und taucht trotzdem irgendwo ein echter Schlüssel auf, wird er
  geschwärzt, bevor die KI ihn sieht.
- **Nova kann sich keine Rechte geben:** Ihre eigenen Einstellungen, Rechte, Schlüssel und die Plugin-Liste
  kann kein Werkzeug der KI lesen oder ändern – das machst nur du.
- **Telegram-Fernzugriff nur mit Code:** Beim ersten Verbinden zeigt Nova einen 6-stelligen Code, den du dem
  Bot schickst. Ein Fremder, der deinem Bot zufällig zuerst schreibt, wird nicht mehr zum Besitzer.
- **Raten zwecklos:** Wer bei der Cloud-Nova zehnmal einen falschen Schlüssel probiert, wird 10 Minuten
  gesperrt. Zu einfache Cloud-Schlüssel werden ersetzt; das Abgleich-Passwort braucht jetzt 12 Zeichen.

## 0.39.0 – 2026-11-25

**Ein Gedächtnis für alle deine Novas – PC und Cloud wissen dasselbe**
- Was Nova am PC über dich lernt, weiß jetzt auch die Cloud-Nova (und umgekehrt): Fakten, Vorlieben und
  worüber ihr gesprochen habt. Was du Nova vergessen lässt, bleibt auf allen Geräten vergessen.
- Die Ablage liegt in einem **privaten GitHub-Repo** (kostenlos) und ist mit **deinem Passwort
  verschlüsselt** – GitHub sieht nur Zeichensalat. So bleibt das Gedächtnis auch dann erhalten, wenn die
  kostenlose Cloud-Nova schläft oder der PC aus ist.
- Einrichten: `/abgleich` zeigt die drei Schritte (Repo anlegen, Token erstellen,
  `/abgleich einrichten …`). In der Cloud trägst du dieselben drei Werte ein.
- Abgeglichen wird beim Start, jede Minute, wenn es etwas Neues gibt, und beim Beenden. Sofort:
  `/abgleich jetzt`. Ausschalten: `/abgleich aus`.

## 0.38.0 – 2026-11-25

**Nova in der Cloud – die Handy-App läuft auch, wenn dein PC aus ist**
- Nova kann jetzt als eigenes Programm im Internet laufen. Die **Nova-Handy-App** verbindet sich dann mit
  dieser Cloud-Nova, und auf **Telegram** antwortet sie rund um die Uhr – ganz egal, ob dein PC an ist.
- Zwei Wege (Schritt für Schritt in `cloud/ANLEITUNG.md`):
  - **Render – kostenlos**, ohne Kreditkarte. Schläft nach 15 Minuten ohne Besuch und wacht in etwa einer
    Minute wieder auf (auch durch eine Telegram-Nachricht). Ihr Gedächtnis beginnt nach dem Aufwachen neu.
  - **Eigener kleiner Server** (z. B. Hetzner, ca. 6–7 € im Monat): läuft immer, das Gedächtnis bleibt. Ein
    Befehl richtet alles ein, inklusive https.
- In der Handy-App: Zurück-Taste → **„Nova in der Cloud“** → Adresse eintragen.
- Ohne den geheimen Schlüssel in der Adresse kommt niemand an die Cloud-Nova heran.
- Die Cloud-Nova ist eine eigene Nova: Sie kann deinen PC nicht steuern, und ihr Gedächtnis ist (noch)
  getrennt von dem auf deinem PC.

## 0.37.0 – 2026-11-25

**Anrufe jetzt auch ohne Kreditkarte – über Vonage**
- Neben Bland AI kann Nova dich jetzt auch über **Vonage** anrufen. Vonage lässt sich per **PayPal oder
  Überweisung** aufladen, und der kostenlose Testzugang (ohne Karte) ruft schon die Nummer an, mit der du
  dich bei Vonage angemeldet hast.
- So geht's: `/anruf` zeigt die Schritte. Kurz: bei Vonage registrieren, eine „Application“ anlegen (dabei
  lädt sich eine Datei `private.key` herunter), dann `/anruf vonage <Application-ID> <Pfad zur private.key>`,
  `/anruf nummer <deine Nummer>` und `/anruf test`.
- Vonage hat keine eigene Gesprächs-KI: Nova sagt dir ihr Anliegen mit deutscher Stimme. Damit sie am
  Telefon auch **deine Antwort** hört, braucht es das kostenlose Programm *cloudflared*
  (`winget install --id Cloudflare.cloudflared`) – Nova startet es während des Anrufs selbst und beendet es
  danach wieder. Ohne cloudflared gibt es eine Ansage, und du antwortest in der App oder auf Telegram.
- Wechseln zwischen den Anbietern: `/anruf anbieter bland` bzw. `/anruf anbieter vonage`.

## 0.36.0 – 2026-11-25

**Nova liest Telegram – deinen Bot und auf Wunsch auch deine eigenen Chats**
- **Nachrichten an deinen Nova-Bot:** Nova kann jetzt jederzeit im normalen Chat nachsehen, was du dem Bot
  vom Handy geschrieben hast („Was habe ich dir auf Telegram geschrieben?“) – und dir auf Telegram schreiben
  („Schick mir das aufs Handy“). Sie schreibt dabei nur an dich, an niemanden sonst.
- **Fernzugriff automatisch:** Mit `/handy auto an` startet der Handy-Fernzugriff ab jetzt immer mit der
  App – Nova antwortet dann auf Telegram, sobald der PC läuft.
- **Deine eigenen Chats (mit anderen Leuten):** Ein Bot kann die grundsätzlich nicht lesen – dafür verbindest
  du einmal dein eigenes Telegram-Konto über die offizielle Telegram-API: `/telegram konto` zeigt die Schritte
  (auf my.telegram.org eine „App“ anlegen, dann mit dem Code anmelden, den dir Telegram schickt). Danach z. B.
  „Was hat mir Lisa geschrieben?“. Nova liest nur auf Wunsch, markiert nichts als gelesen und speichert nichts
  von fremden Chats. **In deinem Namen schreibt sie nur, wenn du es bestätigst.** `/telegram konto abmelden`
  trennt die Verbindung wieder.
- Geheime Angaben in Befehlen (Anmelde-Code, Passwort, Tokens) erscheinen im Chatverlauf jetzt nur als „••••“.

## 0.35.2 – 2026-11-25

**Fehler „open() got an unexpected keyword argument 'metadata_errors'“ behoben**
- Diese Meldung kam beim Sprechen (und beim Mitschnitt), wenn die lokale Whisper-Erkennung lief: Sie hat
  die Aufnahme als Datei über die Bibliothek PyAV eingelesen, und deren neue Version kennt eine alte
  Einstellung nicht mehr. Jetzt bekommt Whisper die Aufnahme direkt – PyAV wird dafür gar nicht mehr
  gebraucht.
- Zusammen mit 0.32.1 (Spracheingabe nimmt wieder die schnelle Google-Erkennung) sollte das Reden wieder
  ganz normal klappen.

## 0.35.1 – 2026-11-25

**Nova stellt sich am Telefon richtig vor**
- Bei Anrufen (Bland AI) weiß die Telefon-KI jetzt genau, wer sie ist: Sie meldet sich als **Nova, deine
  KI vom PC**, erklärt auf Nachfrage, was sie ist, und sagt offen, dass sie eine KI ist – sie gibt sich nie
  als Mensch aus. Am Telefon nennt sie keine Passwörter oder privaten Daten. Geht jemand anderes ran,
  bittet sie nur darum, dir Bescheid zu geben, ohne Details.
- Mit `/anruf persona` bekommst du das Vorstellungs-Skript als Datei zum Anpassen
  (`config/anruf_persona.txt`; `{name}` = Name der KI, `{anliegen}` = warum sie anruft). Updates
  überschreiben deine Fassung nicht.

## 0.35.0 – 2026-11-25

**Nova auf dem Handy (Android)**
- Nova läuft jetzt auch auf deinem Android-Handy – mit denselben Funktionen und derselben Oberfläche.
  Sie läuft in **Termux** (aus F-Droid); eine Zeile richtet alles ein:
  `curl -fsSL https://raw.githubusercontent.com/GermanClaude/Selbst-lernende-KI/ccr-cfa1ff8c-wgsyxb/termux/installieren.sh | bash`
  Danach startest du sie mit `nova`.
- **Nova-App (APK):** Im GitHub-Release liegt jetzt auch **Nova-Handy.apk**. Sie zeigt Nova wie eine
  echte App; `nova` in Termux öffnet sie von selbst.
- **Das Handy steuern:** Mit der App *Termux:API* kann Nova Akku, Benachrichtigungen, Taschenlampe,
  Zwischenablage, Standort, SMS, Kontakte, Kamera und Vorlesen nutzen. Über **Kabelloses Debugging**
  (einmal koppeln mit `/handysteuerung`, kein Root nötig) steuert sie das **ganze Handy**: Bildschirm
  lesen, tippen, wischen, Text eingeben, Apps starten und installieren.
- **Linux und Kali auf dem Handy:** Nova kann über `proot-distro` Linux-Systeme (Debian, Ubuntu …)
  installieren und Kali über die offizielle NetHunter-Rootless-Anleitung von kali.org.
- Privates (SMS, Kontakte, Standort) lesen, tippen und Nachrichten senden fragt vorher nach; Apps
  installieren ist im sicheren Modus gesperrt.
- Noch nicht auf dem Handy: die Spracheingabe per Mikrofon-Knopf und die PC-Werkzeuge (Maus/Tastatur
  am PC, Live-Sehen, Spielmodus).

## 0.34.0 – 2026-11-25

**Nova steuert jetzt auch Hardware**
- **Smart Home:** Lampen, Steckdosen, Heizung, Rollläden, Szenen über **Home Assistant** (damit auch
  Philips Hue, Shelly, Tuya & Co.). Einrichten: `/geraete smarthome <Adresse> <Token>` (den Token
  erstellst du in Home Assistant unter *Profil → Langlebige Zugangs-Token*). Dann z. B. „mach das Licht
  im Wohnzimmer auf 30 %“.
- **Arduino / ESP32:** per USB-Kabel (Nova findet den Port selbst und schickt Befehle) oder per WLAN
  (`/geraete esp licht http://192.168.1.50`) – nur Geräte im eigenen Netz.
- **Bluetooth (BLE):** Geräte in der Nähe suchen, Werte lesen und schreiben (z. B. Sensoren, LED-Streifen).
- **Andere Rechner:** Raspberry Pi, Server, zweiter PC per SSH – nur Geräte, die du mit Namen einträgst
  (`/geraete ssh pi pi@192.168.1.20`), und nur mit SSH-Schlüssel, nie mit Passwort.
- Sicherheit: Lesen geht einfach so; Schalten, Senden und Schreiben fragt vorher nach. Befehle auf anderen
  Rechnern sind wie Shell-Befehle eingestuft (im sicheren Modus gesperrt). `/geraete` zeigt den Stand.

## 0.33.0 – 2026-11-25

**Nova bemerkt Fehler und kümmert sich darum**
- Geht in der App etwas schief (Fehlermeldung bei einer Antwort, Spracheingabe, Fehler im Fenster),
  merkt Nova sich das. Kann sie etwas dagegen tun und ist gerade frei, meldet sie sich sofort selbst:
  Sie erklärt kurz, was los ist, und behebt es, wenn sie kann. (Gedrosselt: jede Meldung nur einmal,
  höchstens alle 2 Minuten – nie im Kreis.)
- Hat sie gerade keine Zeit, bekommt sie bei deiner nächsten Nachricht einen Hinweis auf den Fehler.
- Jede Fehlerkarte hat jetzt den Knopf **„Nova fragen“** – ein Klick schickt ihr die Meldung.
- Nova kann mit dem neuen Werkzeug **app_fehler** selbst ins Protokoll schauen, wenn du fragst „warum geht
  X nicht?“ (Passwörter und Schlüssel werden dabei geschwärzt).

## 0.32.1 – 2026-11-25

**Spracheingabe repariert**
- Die Spracheingabe (F2 / Mikrofon-Knopf) ging seit Version 0.27.1 nicht mehr richtig: Weil für den
  Mitschnitt die lokale Whisper-Erkennung in die App gepackt wurde, hat die Spracheingabe still auf
  Whisper umgestellt – und das lädt beim ersten Mal erst ein riesiges Sprachmodell herunter. Jetzt nimmt
  sie wieder wie früher die schnelle Google-Erkennung. Whisper gibt es nur noch, wenn du es ausdrücklich
  einstellst (`[voice] erkennung = "whisper"`).
- Fehler der Spracheingabe werden jetzt im Protokoll vermerkt, damit so etwas nicht mehr unbemerkt bleibt.
- Kleinigkeit: der Ordner-Auswahldialog nutzt die neue Schnittstelle von pywebview.

## 0.32.0 – 2026-11-24

**Nova kann dich anrufen (Bland AI)**
- Neu: Nova ruft dich auf dem Handy an, wenn es wichtig ist – z. B. „ruf mich an, wenn der Download
  fertig ist“ oder wenn sie im AFK-Modus dringend eine Entscheidung braucht. Eine KI-Stimme spricht
  Deutsch, sagt worum es geht und hört sich deine Antwort an. Nova bekommt danach die Mitschrift und
  weiß, was du gesagt hast. Gehst du nicht ran, hinterlässt sie eine kurze Mailbox-Nachricht.
- **Nur deine Nummer:** Nova kann ausschließlich die Nummer anrufen, die du selbst hinterlegst –
  niemand anderen. Am PC fragt sie vorher nach; wenn du weg bist (AFK), ruft sie ohne Nachfrage an.
- **Kostenbremse:** höchstens 5 Anrufe pro Tag, jeder höchstens 3 Minuten (änderbar mit
  `/anruf minuten 5`).
- Einrichten: Konto bei bland.ai, dort einen API-Schlüssel holen und Guthaben aufladen (für Anrufe nach
  Deutschland mindestens 5 $). Dann im Chat `/anruf schluessel <KEY>`, `/anruf nummer 0171 …` und
  `/anruf test`.

## 0.31.0 – 2026-11-24

**Handy-Nachrichten gehen nicht mehr verloren, wenn der PC aus ist**
- Schreibst du deinem Telegram-Bot, während der PC oder Nova aus ist, merkt sich Nova das. Beim
  nächsten Start fragt sie dich: **„Während ich aus war, hast du mir vom Handy geschrieben: … Soll ich
  das jetzt umsetzen?“** – mit **Ja, jetzt umsetzen**, **Später fragen** oder **Verwerfen**.
- Bei „Ja“ bekommt Nova alle Nachrichten zusammen und in der richtigen Reihenfolge als einen Auftrag.
  „Später“ behält sie (auch wenn du das Fenster schließt). Ein versehentlicher Stopp zählt als „Später“,
  nie als „Verwerfen“.
- Das klappt auch, wenn du `/handy` startest: Was liegen geblieben ist, wird nicht mehr übersprungen,
  sondern erst nachgefragt.
- Wichtig: Telegram hebt Nachrichten an den Bot etwa **24 Stunden** auf. Was älter ist, kann Nova nicht
  mehr abholen. Und wie immer gilt: nur Nachrichten von **deinem** Handy (deine Chat-ID) zählen.

## 0.30.0 – 2026-11-24

**Skills jetzt per Klick verwalten**
- Neu in der App: ein eigener Reiter **Skills** (im Fenster „Charakter & Profil“, oder direkt über den
  neuen Knopf **Skills** in der Seitenleiste).
- Dort legst du Skills an (Name + Anweisung) und wählst, ob sie **für alle Gehirne** oder **nur für
  eins** gelten (z. B. nur DeepSeek). Jeden Skill kannst du mit einem Klick **an- und ausschalten**
  oder **löschen** (zur Sicherheit mit zweitem Klick).
- Skills, die sich Nova selbst angelegt hat, siehst du dort ebenfalls. Änderungen gelten ab dem
  nächsten Gespräch. Der Befehl `/skill` funktioniert weiterhin.

## 0.29.1 – 2026-11-24

**DeepSeek V4.1 Flash klar als Modell wählbar**
- Das schnelle DeepSeek-Standardmodell heißt jetzt überall **„DeepSeek V4.1 Flash"** (vorher nur
  „DeepSeek Flash") – es ist dasselbe Modell, mit korrektem Namen. Es sieht Bilder und kann
  nachdenken. Wählen in der App unter *Gehirn & Schlüssel* oder im Chat mit `/modell flash` bzw.
  `/modell v4.1 flash` (auch „deepseek-v4.1-flash" wird erkannt).
- Wie bei **jedem** Gehirn kann Nova sich dafür eigene Skills/Werkzeuge bauen: `/skill addfuer
  deepseek …` (nur für DeepSeek) oder `/skill add …` (für alle). Nova kann Skills auch selbst
  anlegen, wenn ihr ein Werkzeug fehlt.

## 0.29.0 – 2026-11-24

**Arbeitsordner frei wählbar – leg Nova Dateien hin**
- Neu: Du kannst Nova einen **Arbeitsordner** geben – so wie ein Projektordner. In der App über den
  Knopf **Arbeitsordner** (öffnet einen Ordner-Auswahldialog), im Chat mit `/arbeitsordner <Pfad>`
  (ohne Pfad zeigt er den aktuellen Ordner und was drin liegt).
- **Du legst dort Dateien für Nova ab** – z. B. Notizen, Daten oder eine Datei mit Befehlen. Nova
  weiß, wo ihr Arbeitsordner ist: relative Pfade und Shell-Befehle (ohne Ordnerangabe) beziehen sich
  jetzt auf diesen Ordner, statt irgendwo.
- Im **sicheren Modus** arbeitet Nova nur in diesem Ordner – such ihn also mit Bedacht aus.
- `/arbeitsordner oeffnen` zeigt ihn im Explorer, `/arbeitsordner zuruecksetzen` geht zurück auf den
  Standard.

## 0.28.2 – 2026-11-24

**„Jarvis-Modus" heißt jetzt „Sprachmodus"**
- Der Modus zum freien Reden heißt überall „Sprachmodus" statt „Jarvis-Modus" (Knopf in der App,
  Hilfe, Tutorial, Anleitung). Du startest ihn mit `/sprachmodus` (auch `/sprechen`); der alte
  Befehl `/jarvis` funktioniert weiter.

## 0.28.1 – 2026-11-24

**Impressum wieder entfernt**
- Die Impressum-Vorlage ist raus. `/rechtliches` zeigt jetzt nur noch die Nutzungsbedingungen und
  den Haftungsausschluss – die bleiben erhalten. (Ein Impressum ist für die rein private Nutzung in
  der Regel ohnehin nicht nötig.)

## 0.28.0 – 2026-11-24

**Nova per Handy fernsteuern – über Telegram, ohne eigenen Server**
- Neu: Du kannst Nova jetzt vom Smartphone aus bedienen. Du schreibst einem eigenen Telegram-Bot,
  Nova antwortet dir zurück – in beide Richtungen, auch wenn du nicht am PC bist.
- **Kein Server, keine Portfreigabe nötig:** Dein PC verbindet sich nur nach außen zu Telegram und
  wartet auf Nachrichten. Das läuft ganz normal hinter deinem Router.
- **Einrichtung (einmalig):** In Telegram den Bot „@BotFather" anschreiben, `/newbot`, Namen
  vergeben – du bekommst einen Token. Den gibst du Nova mit `/handy token <DEIN_TOKEN>` (oder über
  den neuen Knopf **Fernzugriff (Handy)** in der App). Dann `/handy`, und du schreibst deinem Bot
  einmal vom Handy.
- **Sicherheit:** Nova gehorcht nur **einer** Chat-ID – deiner. Die erste Nachricht beim Einrichten
  legt fest, wer steuern darf; alle anderen Absender werden ignoriert. Der Token bleibt lokal in der
  `.env` und kommt nie ins Internet-Repo. Vor heiklen Aktionen fragt Nova auch am Handy nach
  („ja"/„nein").
- Beenden: `/handy aus` (in der App) bzw. „stop" ans Handy oder Strg+C (im Terminal).

## 0.27.2 – 2026-11-24

**Rechtliches & ein schnellerer Mitschnitt**
- Neu: **Nutzungsbedingungen, Haftungsausschluss und eine Impressum-Vorlage** liegen Nova jetzt bei.
  Du rufst sie mit dem Befehl `/rechtliches` auf (oder über den neuen Knopf **Rechtliches** in der App).
  So ist klar geregelt, dass **du** entscheidest, was die KI darf, und dass der Entwickler nicht
  haftet, wenn die KI auf deine Anweisung hin z. B. Dateien löscht oder Kosten verursacht.
  ⚠️ Es sind **Vorlagen** mit Platzhaltern (z. B. `[DEIN NAME]`), die du selbst ausfüllst – und sie
  ersetzen keinen Rechtsrat. In Deutschland/der EU lässt sich Haftung nicht komplett ausschließen.
- Der Ton-Mitschnitt (`/transkript`) arbeitet im Hintergrund **spürbar schneller und sparsamer**:
  das Zusammenmischen von System-Ton und Mikrofon sowie das Erkennen der Stimmlage (für „männlich/
  weiblich?") wurden optimiert. Für dich ändert sich nichts an der Bedienung.

## 0.27.1 – 2026-11-24

**Transkription jetzt direkt in der App (ohne Zusatz-Installation)**
- Die Pakete für den Mitschnitt (`sounddevice` + `faster-whisper`) sind jetzt **fest in die KI.exe /
  KI-App.exe eingebaut**. Damit läuft `/transkript` auch in der fertigen App – ohne dass du selbst
  etwas installieren musst. (Die .exe ist dadurch spürbar größer.)
- Beim allerersten Transkribieren lädt Whisper einmalig sein Sprachmodell herunter (einige 100 MB);
  danach läuft alles lokal und ohne Tokens.

## 0.27.0 – 2026-11-24

**Skills, eigene Modelle und Mitschnitt von System-Audio + Mikrofon zusammen**
- **Skills (gespeicherte Regeln):** Du oder Nova selbst könnt dauerhafte Verhaltensregeln anlegen –
  z. B. „Antworte extrem knapp, um Tokens zu sparen". `/skill add <Name> <Anweisung>`, oder nur für
  ein Gehirn: `/skill addfuer claude …`. Nova kann sich auf Wunsch selbst einen Skill merken. Skills
  gelten ab dem nächsten Gespräch und bleiben bei Updates erhalten. (Ein Skill ist eine Anweisung in
  Worten – **kein** automatisch ausgeführter Code; das bleibt aus Sicherheitsgründen so.)
- **Eigene/neue Modelle:** Bei DeepSeek, Gemini, ChatGPT, Abliteration, Venice und NanoGPT kannst du
  jetzt **jede Modell-ID eintragen**, die dein API-Schlüssel erreicht – auch eine, die Nova noch nicht
  kennt (`/modell deepseek <genaue-id>`). Claude nimmt seine vollen IDs ohnehin an, Ollama deine
  heruntergeladenen (auch selbst trainierte) Modelle.
- **Mitschnitt: System-Audio UND Mikrofon zusammen** (wie bei Medal). `/transkript start` nimmt jetzt
  standardmäßig **beides gemischt** auf – du hörst dich und den PC-Ton in einem Transkript. Weiterhin
  wählbar: nur `system` oder nur `mikrofon`.
- Klarere Meldung in der fertigen App: Dort fehlen die Transkriptions-Pakete noch und lassen sich
  nicht nachinstallieren – Nova sagt das jetzt richtig (statt nach einem Python-Pfad zu suchen).

## 0.26.1 – 2026-11-23

**Passwort-/Geheimnis-Schutz beim Mitschreiben**
- Alles, was Nova mitschreibt (Transkripte, Aktivitäts-Protokoll), läuft jetzt vor dem Speichern
  durch einen **Geheimnis-Filter**: Passwörter, API-Schlüssel, Tokens, 2FA-Codes und Kartennummern
  werden erkannt und **unkenntlich gemacht** (`[…entfernt: Geheimnis…]`). So landen Passwörter nie
  in Novas Dateien – sie gehören in den Passwortmanager deines Browsers.
- Zur Klarstellung: Nova schneidet weiterhin **nicht** mit, *was* du oder andere tippen (kein
  Keylogger). Ein Hintergrund-Tastaturmitschnitt könnte Passwörter gar nicht zuverlässig aussparen –
  deshalb gibt es ihn bewusst nicht. Gesprochenes transkribierst du mit dem Mitschnitt (mit
  Zustimmung der Beteiligten), und auch dort werden laut vorgelesene Passwörter herausgefiltert.

## 0.26.0 – 2026-11-23

**Mitschnitt/Transkription und ein Aktivitäts-Protokoll**
- **Transkription auf Knopfdruck:** Nova schreibt Ton mit und transkribiert ihn **lokal** (mit
  Whisper) – das **kostet keine Tokens**. Quelle wählbar: dein **Mikrofon** oder das **System-Audio**
  (alles, was der PC ausgibt – Spiele, Discord/Calls, Videos, Aufnahmen). Läuft beliebig lange, bis du
  stoppst, und schreibt laufend in eine Transkript-Datei (im Arbeitsordner unter `mitschnitte/`).
  Starten: `/transkript start system` (oder `… mikrofon`), stoppen: `/transkript stop`. Auf Wunsch
  fasst Nova das Gespräch zusammen (`/transkript zusammenfassung`). Du kannst auch einfach sagen
  „transkribier das" – Nova macht es dann.
- **Mehrere Sprecher & Namen (ehrlich: „so gut es geht"):** Sprecher auseinanderzuhalten klappt
  zuverlässig nur mit einem Zusatzmodell (`pip install resemblyzer`); ist es nicht da, transkribiert
  Nova ohne Sprecher-Aufteilung und sagt dir das. Erkannten Sprechern kannst du Namen geben
  (`/transkript name 1 Aria`). Das **Geschlecht** wird – wenn möglich – nur **grob aus der Tonhöhe
  geschätzt** (mit „?" markiert), nie als sicher behauptet.
- **Aktivitäts-Protokoll (optional):** `/protokoll an` hält fest, **welche Programme/Fenster** du
  gerade nutzt – wie ein Taskmanager-Verlauf (`protokolle/`). `/protokoll zeigen` gibt eine Übersicht.
- **Bewusst NICHT gebaut: ein Keylogger.** Das Mitschreiben, *was* getippt oder in Chats (z. B.
  Discord) geschrieben wird, baue ich nicht – das würde auch fremde private Nachrichten und
  Passwörter abgreifen. Gesprochene Gespräche kannst du mit dem Mitschnitt (und Zustimmung der
  Beteiligten) transkribieren.

## 0.25.1 – 2026-11-23

**NanoGPT: Google Pay bestätigt**
- Nachgeprüft: Bei NanoGPT kannst du dein Guthaben per **Google Pay** (oder Karte, beides über
  Stripe) aufladen – kein Bitcoin nötig. Die App zeigt das jetzt klar an. PayPal bietet weiterhin
  keiner der unzensierten Anbieter an.

## 0.25.0 – 2026-11-23

**Neues Gehirn NanoGPT – unzensiert und ohne Krypto-Zwang bezahlbar**
- Venice und Abliteration lassen sich praktisch nur mit Krypto/Guthaben bezahlen. **NanoGPT** ist
  eine Alternative: unzensierte Modelle, OpenAI-kompatibel, **sieht Bilder** und nutzt Werkzeuge –
  und das Guthaben kannst du **ganz normal per Karte (Stripe)** aufladen (oder Krypto, wenn du willst).
- Ehrlich dazu: **PayPal** bietet aktuell keiner dieser unzensierten Anbieter an. **Google Pay** ist
  nirgends ausdrücklich genannt, erscheint aber im Karten-Bezahlfenster (Stripe) auf unterstützten
  Geräten oft automatisch. Wenn das für dich reicht, ist NanoGPT der bequemste Weg.
- Einrichten: in der App unter „Gehirn & Schlüssel" **NanoGPT** wählen und den Schlüssel von
  [nano-gpt.com](https://nano-gpt.com/api) einfügen, dann `/gehirn nanogpt`. Modelle:
  `z-ai/glm-5.3-uncensored` (Standard), `z-ai/glm-5.3-flash-uncensored`, `abliteration-ai/abliterated-model-large-v2`.

## 0.24.1 – 2026-11-23

**Tippen noch robuster (Umlaute überall)**
- Ergänzung zu 0.24.0: Beim Tippen in andere Programme werden **Zeilenumbrüche (Enter) und
  Tabs** jetzt als echte Tasten gesendet, und Sonderzeichen inklusive Emojis zuverlässig als
  Unicode. Umlaute (ä/ö/ü/ß) kommen damit überall richtig an – in der Suche, in Discord usw.,
  mit jedem Gehirn.

## 0.24.0 – 2026-11-23

**Neues Gehirn Venice AI, Umlaute beim Tippen, und „Versionen" zeigt die Neuerungen**
- **Venice AI** als weiteres unzensiertes Gehirn (neben Abliteration AI): OpenAI-kompatibel,
  **sieht Bilder selbst** und nutzt Werkzeuge. Schlüssel von [venice.ai](https://venice.ai/settings/api)
  in der App unter „Gehirn & Schlüssel" eintragen (Venice-Schlüssel haben kein festes Präfix), dann
  `/gehirn venice`. Modelle: `venice-uncensored-1-2` (Standard), `gemma-4-uncensored` (günstig),
  `deepseek-v4-1-flash-uncensored`. Novas eigene Persönlichkeit bleibt dabei maßgeblich.
- **Umlaute beim Tippen gehen jetzt** – vorher ließ die PC-Steuerung ä/ö/ü/ß einfach weg (z. B. in
  der Suche oder in Discord-Nachrichten). Jetzt werden Umlaute und Sonderzeichen korrekt getippt.
  Das galt für alle Gehirne und ist nun behoben.
- **„Versionen" zeigt, was jede Version gebracht hat:** `/versionen` (bzw. der Knopf in der App)
  listet jetzt zu jeder gesicherten Version eine kurze Zeile, was neu war.

## 0.23.0 – 2026-11-23

**Abliteration AI kann jetzt Bilder „sehen"**
- Das Abliteration-Modell hat selbst keine Augen. Damit es trotzdem sehen kann – genau wie
  DeepSeek das macht – lässt Nova Bilder jetzt von einem anderen, seh-fähigen Gehirn beschreiben,
  für das du einen Schlüssel hast: **DeepSeek** (am günstigsten), sonst **Gemini**, sonst **OpenAI**.
  Die Beschreibung bekommt Abliteration dann als Text.
- Das gilt für Bilder, die du schickst, genauso wie fürs Live-Sehen. Hast du kein seh-fähiges
  Gehirn hinterlegt, sagt Nova dir freundlich Bescheid, statt einfach nichts zu sehen.

## 0.22.1 – 2026-11-22

**Updates gehen jetzt schnell – egal welches Modell**
- Beim Aktualisieren hat Nova die Neuerungen „in eigenen Worten" erklärt. Mit einem langsamen
  Modell (z. B. Ollama auf einem schwächeren PC) konnte das ewig dauern. Jetzt wartet das Update
  höchstens kurz auf diese Erklärung – schafft das Modell es nicht schnell, zeigt Nova sofort die
  (ohnehin verständlichen) Versionshinweise und macht weiter. So ist ein Update in Sekunden da,
  unabhängig vom gewählten Gehirn.

## 0.22.0 – 2026-11-21

**Neues Gehirn: Abliteration AI (unzensiert)**
- Neben Claude, DeepSeek, Gemini, ChatGPT und Ollama kannst du jetzt auch **Abliteration AI**
  wählen – ein unzensiertes, OpenAI-kompatibles Modell. Schlüssel (beginnt mit `ak_`, von
  [abliteration.ai](https://abliteration.ai)) einfach in den Chat einfügen oder in der App unter
  „Gehirn & Schlüssel" eintragen, dann `/gehirn abliteration`.
- Wie jedes Gehirn kann auch dieses die vorhandenen Werkzeuge nutzen – inklusive der
  **PC-Steuerung** (Maus/Tastatur, Dateien, Programme), sobald du die Berechtigungen dafür
  freigibst (Stützräder „aus"/„alles"). Nutze das verantwortungsvoll und im Rahmen der Gesetze.
- Hinweis zu „RAW AI": die gleichnamige Play-Store-App hat keine öffentliche Schnittstelle (API),
  darum lässt sie sich nicht direkt anbinden. Abliteration AI ist die anbindbare Alternative mit
  ähnlicher Ausrichtung.

## 0.21.1 – 2026-11-21

**AFK-Modus endet nicht mehr aus Versehen**
- Ein kurzer **Mikrofon-Blip** (ein Geräusch beim Filmschauen, ein Räuspern) oder eine
  **versehentliche Taste** beendet den AFK-Modus jetzt nicht mehr. Nur eine echte Nachricht
  mit richtigem Wort (getippt oder gesprochen) oder der Stopp-Knopf holen dich zurück.
- Fülllaute wie „äh", „hm", „mhm" und einzelne Zeichen werden im AFK als Versehen behandelt
  und ignoriert; kurze echte Rückmeldungen wie „ok", „stop" oder „bin da" zählen weiterhin.

## 0.21.0 – 2026-11-21

**AFK-Modus arbeitet jetzt wirklich weiter – ohne Dauerfragen**
- Bisher war Nova im AFK-Modus (wenn du weg bist) sehr vorsichtig: sie durfte nur lesen,
  recherchieren und Entwürfe anlegen, alles andere schrieb sie nur als Vorschlag auf.
- Neu: Wenn du Nova ohnehin **volle Freiheit** gegeben hast (Stützräder „aus" oder „alles"/
  Vollzugriff), **handelt sie im AFK jetzt wirklich** – Dateien ändern, Befehle ausführen, bei
  Bedarf Maus und Tastatur steuern – und entscheidet dabei nach eigenem Ermessen, so wie du es
  wollen würdest, **ohne ständig nachzufragen**. Gedacht genau dafür: du duschst, isst, schaust
  einen Film – und sie macht in der Zeit deinen Auftrag fertig.
- **Es bleibt mit Verstand:** Schwer Umkehrbares oder was andere betrifft (viel löschen,
  verschicken, posten, Geld ausgeben, Konten/Einstellungen dauerhaft ändern) macht sie nur, wenn
  der Auftrag das klar meint – sonst schreibt sie es als Vorschlag. **Automatische Starts** richtet
  sie im AFK nie ein, und Anweisungen aus Webseiten/Dateien befolgt sie weiterhin nicht.
- **Mausbewegung oder eine versehentliche Taste beenden den AFK-Modus NICHT.** Er endet nur, wenn
  du ihm wirklich schreibst/sagst oder auf Stopp drückst. Zeit- und Kostengrenzen gelten weiter.
- Willst du es lieber vorsichtig wie bisher: `[permissions] afk_autonom = false`.

## 0.20.0 – 2026-11-21

**Stimme bequem in der App auswählen**
- Neben dem Chat-Befehl `/stimme` gibt es jetzt in der App-Seitenleiste eine echte
  **Auswahl-Liste** direkt unter „Vorlesen": Stimme wählen (Frei / OpenAI / ElevenLabs),
  bei OpenAI zusätzlich die konkrete Stimme (z. B. `cedar`, `marin`, `nova`, `coral`), bei
  ElevenLabs die Stimmen deines Kontos.
- **„Anhören"**-Knopf zum Probehören, und ein Feld, um den ElevenLabs-Schlüssel gleich dort
  einzufügen. Fehlt ein Schlüssel, sagt die Liste es dir.

## 0.19.0 – 2026-11-20

**Mit Nova reden – und sie antwortet mit einer Stimme deiner Wahl**
- Zuhören konnte Nova schon (F2-Sprechtaste und der freihändige Jarvis-Modus `/jarvis`).
  Neu ist, dass du bei der **Vorlese-Stimme** zwischen gratis und echt klingend wählen kannst:
  - **Frei** – die eingebaute Computerstimme deines PCs. Kostenlos, offline, ohne Konto (Standard).
  - **OpenAI** – eine natürliche Stimme über **deinen schon vorhandenen ChatGPT-Schlüssel**
    (kein neues Konto nötig, günstig). Sag z. B. „nimm eine echtere Stimme" oder tippe
    `/stimme openai`. Eigene Stimmen wählbar (z. B. `cedar`, `marin`, `nova`, `coral`).
  - **ElevenLabs** – die natürlichste Stimme überhaupt. Braucht ein eigenes (kostenlos
    startendes) ElevenLabs-Konto; Schlüssel eintragen mit `/stimme schluessel <KEY>`, dann
    `/stimme elevenlabs`.
- Umstellen im Chat mit `/stimme` (zeigt die Auswahl), in der App über **„Stimme wählen"** in
  der Seitenleiste, oder einfach per Sprache – Nova stellt es selbst um, wenn du sie darum bittest.
  Anhören mit `/stimme test`. Fehlt ein Schlüssel, sagt Nova es dir und bleibt bei der gratis Stimme.
- Hinweis: Die realistischen Stimmen kosten je nach Länge etwas Geld. Die kostenlose Stimme bleibt
  immer als Rückfall erhalten.

## 0.18.0 – 2026-11-20

**Neue Stufe „Vollzugriff" – Nova darf wirklich alles**
- Bisher gab es zwei Stufen: **Stützräder an** (fragt vor jeder Änderung, bleibt im
  Arbeitsordner) und **Stützräder ab** (ganzer PC, ohne Rückfragen – nur automatische
  Starts fragt sie noch).
- Neu ist eine dritte Stufe: **Vollzugriff**. Damit fällt auch das letzte Netz – Nova darf
  dann wirklich **ALLES ohne Rückfrage**: auch sonst gesperrte Befehle (z. B. ganze Ordner
  oder Laufwerke löschen, Systemdateien ändern) und automatische Starts. Den ganzen PC
  steuern und durchsuchen – ohne Bremse.
- Einschalten: im Chat `/stuetzraeder alles`, per Sprache „gib dir Vollzugriff", oder in der
  App der neue Schalter **Vollzugriff** in der Seitenleiste. Vorher kommt immer eine deutliche
  Warnung. Zurück geht jederzeit mit `/stuetzraeder aus` oder `/stuetzraeder an`.
- **Ein Schutz bleibt mit Absicht bestehen:** Wenn du weg bist (AFK-Modus), ist Nova trotzdem
  vorsichtig und führt keine riskanten Aktionen aus – auch mit Vollzugriff nicht. So kann in
  deiner Abwesenheit nichts aus dem Ruder laufen.

## 0.17.0 – 2026-11-20

**Dein eigenes Design – und Updates lassen es in Ruhe**
- **Design-Vorlagen auf Knopfdruck:** Sag „mach die App hackerhaft“ (oder
  `/aussehen vorlage hacker`) – Nova stellt den ganzen Look um. Zur Wahl: **hacker**
  (Terminal-Grün auf Schwarz), **mitternacht**, **dracula**, **retro**, **pastell**, **sonne**.
  Zurück zum Original: `/aussehen vorlage aus`.
- **Eigenes Hintergrundbild:** Gib Nova ein Bild („nimm bild.jpg als Hintergrund“ oder
  `/aussehen hintergrund <pfad>`). Es wird dezent abgedunkelt, damit der Text lesbar bleibt;
  entfernen mit `/aussehen hintergrund aus`.
- Dazu wie bisher: Farben, Schriftgröße, Ecken, Begrüßung, Sphäre und ganz eigenes CSS – Nova
  kann die App frei nach deinen Ideen umbauen.
- **Wichtig: Updates ändern dein Design nie.** Deine Vorlage, Farben, dein Bild und dein eigenes
  CSS sind vor Updates geschützt – eine neue Version lässt dein Aussehen unangetastet. Willst du
  doch wieder das Original, geht das jederzeit mit `/aussehen zuruecksetzen`.

## 0.16.0 – 2026-11-20

**Neues Gehirn: ChatGPT (OpenAI)**
- Neben Claude, DeepSeek, Gemini und Ollama kann Nova jetzt auch mit **ChatGPT** von OpenAI denken.
- Einrichten: Schlüssel unter **platform.openai.com/api-keys** erstellen und einfach in den Chat
  einfügen – oder in **„Gehirn & Schlüssel“ → „ChatGPT (OpenAI)“**. Nova erkennt einen
  `sk-proj-…`-Schlüssel, probiert ihn kurz aus und schaltet um. Der Schlüssel geht nie an die KI.
- Drei Modelle: **GPT-5.2** (stark, denkt nach und nutzt Werkzeuge – der Standard),
  **GPT-6 Sol** (ausgewogen) und **GPT-6 Luna** (am günstigsten). Alle sehen Bilder.
- Denk-Tiefe wählbar (`/denken`); im Terminal: `/gehirn openai`, `/modell openai luna`.
- Die Kostenanzeige kennt die OpenAI-Preise.
- Hinweis: Die allerneuesten Flaggschiffe (z. B. gpt-6.2-astra) nutzen Werkzeuge nur über eine
  andere Schnittstelle, die Nova nicht verwendet – darum sind sie bewusst nicht in der Liste.

## 0.15.0 – 2026-11-13

**Bewertungen: Sterne für alle sichtbar**
- Im Fenster **„Feedback & Bewertung“** siehst du jetzt, wie Nova bewertet wird: den
  **Durchschnitt** (z. B. „★★★★★ 4,6 von 5 · 23 Bewertungen“) und die neuesten
  **Rezensionen** anderer Nutzer. Der Schnitt steht auch in der Seitenleiste.
- Neu beim Bewerten: **„Meine Bewertung öffentlich zeigen“** – dann erscheinen deine Sterne und
  dein Text (wahlweise mit einem Namen) als Rezension. Deine E-Mail-Adresse wird nie gezeigt;
  Links, E-Mail-Adressen und Telefonnummern werden aus dem Text entfernt.
- Deine Sterne zählen immer anonym zum Durchschnitt – pro Installation nur deine letzte
  Bewertung (du kannst sie also jederzeit ändern).
- Auch auf der **GitHub-Seite** steht jetzt die aktuelle Bewertung – sie wird automatisch alle
  6 Stunden aktualisiert.
- Im Terminal fragt `/feedback` ebenfalls, ob die Bewertung öffentlich sein darf.

## 0.14.0 – 2026-11-13

**Neues Gehirn: Google Gemini**
- Neben Claude, DeepSeek und Ollama kann Nova jetzt auch mit **Gemini** von Google denken.
- Einrichten: Schlüssel unter **aistudio.google.com/apikey** erstellen und einfach in den Chat
  einfügen – oder in **„Gehirn & Schlüssel“ → „Gemini (Google)“**. Nova erkennt den Schlüssel
  (beginnt mit `AQ.` oder `AIza`), probiert ihn kurz aus und schaltet um. Der Schlüssel geht nie
  an die KI.
- **Kostenloser Einstieg möglich:** Google bietet einen Gratis-Zugang mit Grenzen pro Minute
  und Tag. Ist er aufgebraucht, sagt Nova dir das verständlich.
- Fünf Modelle zur Wahl: **Gemini 3.8 Flash** (Standard, schnell und günstig),
  **3.5 Flash-Lite** (am günstigsten), **Gemini 4 Hydrogen** (flott), **Argon** (sehr stark)
  und **Carbon** (das stärkste). Alle sehen Bilder.
- Denk-Tiefe: schnell, ausgewogen oder gründlich (`/denken`). Im Terminal: `/gehirn gemini`,
  `/modell gemini carbon`.
- Die Kostenanzeige kennt die Gemini-Preise – auch die von Google angekündigten
  Preiserhöhungen (Argon/Carbon ab 1.12.2026, Flash ab 1.1.2027).

## 0.13.1 – 2026-11-13

**Sicherheits-Check: kurz und übersichtlich**
- Der Bericht von `/scan` ist jetzt **kurz**: Im Chat stehen höchstens die **25 wichtigsten
  Funde** – der Rest steht in der gespeicherten Datei (ganze Liste: `/scan letzter`).
- **Viele Dateien im selben Ordner** (z. B. ein Installer, der hunderte Dateien in den
  Temp-Ordner entpackt) werden zu **einem Eintrag** zusammengefasst, statt jede Datei
  einzeln aufzuzählen. Gefährliche Funde (HOCH) bleiben immer einzeln sichtbar.
- **Weniger Fehlalarme:** Dateien, deren Signatur nicht geprüft werden konnte, gelten nicht
  mehr automatisch als verdächtig, und normale Namen mit Versionsnummer (z. B.
  „vcruntime140.dll“) gelten nicht mehr als „zufällig“.
- `/scan ignorieren` mit der Nummer eines Sammel-Eintrags blendet den **ganzen Ordner** aus.

## 0.13.0 – 2026-11-09

**Sicherheits-Check: Nova sucht nach Schadsoftware**
- Sag einfach „Scan meinen PC auf Viren“ oder tippe **`/scan`**. Nova sucht nach Spuren von
  **Malware, Spyware, Trojanern und Infostealern** (Programme, die Passwörter klauen).
- Geprüft werden: der Windows-Virenschutz und seine bisherigen Funde, alles, was beim Start
  automatisch mitläuft (Autostart und Aufgabenplanung), laufende Programme (ob sie digital
  signiert sind und wohin sie sich verbinden), neue Programmdateien und Skripte der letzten
  7 Tage und die hosts-Datei.
- Typische Tricks erkennt Nova sofort: als Dokument getarnte Programme („Rechnung.pdf.exe“),
  falsche Windows-Programme („svchost.exe“ im falschen Ordner), versteckte oder verschlüsselte
  Befehle im Autostart, Programme im Temp-Ordner, Cheat-/Crack-Dateien.
- Du bekommst eine **nummerierte Liste** (hoch / mittel / niedrig). Danach fragst du einfach
  „Was hältst du davon?“ – Nova bewertet jeden Fund fachlich, sagt dir, was harmlos ist und was
  nicht, und **du suchst aus**, was passieren soll. Nova löscht nie etwas von selbst.
- **`/scan gruendlich`** schaut 30 Tage zurück und in mehr Ordner (dauert ein paar Minuten).
- **`/scan datei <pfad>`** prüft eine einzelne Datei mit Windows Defender, Signatur und
  Prüfsumme (inklusive Link zu VirusTotal).
- Harmlos? **`/scan ignorieren 3`** (oder „Nr. 3 ist okay“) – dann meldet Nova den Fund nicht mehr.
- Der Check kostet nichts (läuft ohne KI); nur die Einschätzung danach braucht das Gehirn.
  Nur unter Windows.

## 0.12.0 – 2026-11-09

- **Handy als Kamera verbindet zuverlässiger:** Nova wartet jetzt geduldiger auf das Handy und
  findet es auch, wenn der Handy-Browser seine Adresse versteckt.
- **Neuer Knopf „Firewall freigeben“** im Fenster „Handy als Kamera“: Windows fragt einmal nach
  (Ja klicken) – danach lässt die Windows-Firewall das Handy-Bild durch. Das war meist der Grund
  für „Keine Verbindung zu Nova“.
- **Klare Fehlermeldungen:** Statt immer nur „selbes WLAN“ sagt Nova jetzt genau, woran es
  hängt (z. B. Firewall, anderes Netz, falscher Browser) – mit einem Tipp, was hilft.
- **Tipp fürs Handy:** Wird die Seite in der Google-App statt in Chrome geöffnet, sagt die Seite
  jetzt, dass man sie in Chrome (Android) bzw. Safari (iPhone) öffnen soll.

## 0.11.1 – 2026-11-09

- **Korrektur „Handy als Kamera“:** Im Kopplungs-Fenster erschien statt des QR-Codes nur ein
  leeres Bild mit dem Text „QR-Code für die Handy-Kamera“. Der QR-Code wird jetzt richtig
  angezeigt – einfach mit der Handy-Kamera scannen.

## 0.11.0 – 2026-11-08

**Spielmodus: Nova spielt selbst – auch über Nacht**
- Nova kann jetzt **Einzelspieler-Spiele selbst spielen**, zuerst **Manor Lords**. Sag einfach
  „Spiel Manor Lords und bau eine wunderschöne mittelalterliche Stadt“ – oder tippe
  `/spiel start Bau eine wunderschöne mittelalterliche Stadt`. In der App gibt es dafür in der
  Seitenleiste den Knopf **„Spielmodus“**.
- **Spiel-AFK über Nacht:** `/spiel nacht <Ziel>` (oder im Dialog „Über Nacht“) – Nova spielt
  stundenlang weiter, während du schläfst, und gibt dir am Morgen einen **Bericht** mit Ziel,
  Fortschritt, Problemen, Kosten und ein paar **Bildern aus dem Spiel**.
- So spielt Nova: Spiel pausieren, genau hinschauen, handeln (bauen, klicken, Tasten),
  kontrollieren, das Spiel ein paar Sekunden laufen lassen – und von vorn. Sie führt dabei ein
  kleines **Tagebuch**, damit sie auch nach vielen Stunden noch weiß, was ihr Plan war.
- Beim ersten Start **sucht Nova die wichtigsten Anzeigen** des Spiels (Kalibrierung) und merkt
  sie sich. Mit `/spiel kalibrieren` sucht sie neu.
- **Sicher:** Nova drückt nur etwas, solange **das Spielfenster vorne ist** – wechselst du in ein
  anderes Fenster, hält sie sofort an und wartet. Anhalten jederzeit mit **Strg+Alt+Umschalt+P**,
  dem Stopp-Knopf im Band „Nova spielt …“ oder einfach, indem du **die Maus bewegst**.
  Gefährliche Tasten (z. B. Alt+F4, die Windows-Taste, Strg+C in Manor Lords) sind gesperrt.
- **Nie Online- oder Mehrspieler-Spiele** – das verstößt gegen deren Regeln und wäre unfair.
- Grenzen für Zeit, Kosten und Züge stellst du im Dialog ein (normal: 2 Std./1 €, nachts:
  10 Std./5 €; mit Ollama kostenlos). Während Nova spielt, bleibt der PC wach – danach wie vorher.
- Tipps: Im Spiel „Randloses Vollbild“ einstellen, das Spiel nicht als Administrator starten,
  den Bildschirm nicht sperren lassen. Am besten mit einem Modell, das Bilder sieht
  (z. B. Claude Sonnet/Haiku oder DeepSeek Flash). Nur unter Windows.

## 0.10.2 – 2026-11-08

- **Zweite Korrektur für Claude:** Nach 0.10.1 kam bei Claude noch die Meldung „too many
  optional parameters“. Claude hat neben der Zahl der Werkzeuge noch eine zweite Grenze –
  Nova hält jetzt beide ein. Sollte Claude in Zukunft eine neue Grenze einführen, versucht
  Nova es automatisch noch einmal auf einfachere Weise, statt mit einem Fehler aufzuhören.

## 0.10.1 – 2026-11-08

- **Wichtige Korrektur für Claude:** Seit den neuen Werkzeugen (Bilder erstellen, Live-Sehen)
  antwortete Claude nur noch mit „Fehler vom Modell … Too many strict tools“. Das ist behoben –
  Claude antwortet wieder normal. (DeepSeek und Ollama waren nicht betroffen.)

## 0.10.0 – 2026-11-08

**Dein Handy als Kamera**
- Keine Webcam am PC? Dann nimm dein Handy: `/sehen handy` eingeben (oder in der App im
  Band „Nova sieht zu“ auf **„Handy-Kamera …“** tippen). Nova zeigt einen **QR-Code** –
  mit der Handy-Kamera scannen, „Kamera starten“ antippen, Kamera erlauben. Fertig.
- Klappt mit **iPhone und Android**, ohne App aus dem Store. Die Kamera-Seite kannst du auf
  den Startbildschirm legen; zum Koppeln geht dann auch der 8-stellige Code.
- Das Bild geht **direkt im Heim-WLAN** vom Handy zum PC. Beim Verbinden hilft ein
  Vermittlungsdienst, der aber nichts mitlesen kann – alles ist verschlüsselt.
- Es gelten dieselben Regeln wie bei Live-Sehen: Erlaubnis, „Nova sieht zu“ (auch am
  Handy), Pause/Aus beenden die Handy-Kamera sofort, Kostengrenze.
- Tipps: Handy und PC im selben WLAN, Handy ans Ladekabel, Bildschirm anlassen. Fragt
  Windows nach der Firewall, „Private Netzwerke“ erlauben.
- Ganz neu – bitte ausprobieren und Bescheid sagen, ob es bei dir verbindet.

## 0.9.0 – 2026-11-08

**Live-Sehen: Nova sieht mit**
- Auf Wunsch schaut Nova auf deinen **Bildschirm** und – in der App – durch deine **Webcam**.
  Ein schnelles „Auge“ auf deinem PC merkt in Sekundenbruchteilen, wenn sich etwas tut
  (z. B. eine Fehlermeldung, ein neues Fenster, neuer Text), und weckt Nova nur, wenn es
  wichtig ist. Sie meldet sich dann im Chat (oder per Stimme im Jarvis-Modus).
- Einschalten: Schalter in der Seitenleiste oder `/sehen an` (`/sehen aus`, `/sehen pause`,
  `/sehen bildschirm|webcam|beides`). Beim ersten Mal fragt Nova um Erlaubnis – und wieder,
  wenn du das Gehirn wechselst.
- Solange sie hinschaut, siehst du immer das Band **„Nova sieht zu“**. Pause: F4 in der App
  oder **Strg+Alt+Umschalt+S** überall. Du kannst auch sagen „Schau weg“.
- **Privat bleibt privat:** Passwortfelder, Passwort-Manager, private Browserfenster und Novas
  eigenes Fenster sieht sie nicht; Kontonummern und Schlüssel werden unkenntlich gemacht.
  Was sie sieht, kommt nicht ins Langzeitgedächtnis und wird nicht gespeichert.
- **Kosten im Griff:** standardmäßig höchstens 20 Weckungen und 0,30 € pro Stunde
  (einstellbar unter `[sehen]`). Mit Ollama kostenlos.
- Gut zu wissen: Das Bildschirm-Sehen gibt es (vorerst) nur unter Windows. Bitte probier es
  aus und sag Bescheid, wenn etwas nicht klappt – es ist ganz neu.

## 0.8.1 – 2026-11-08

- **AFK-Modus: eigenes Budget.** Im Dialog „Ich bin weg“ kannst du jetzt unter „Eigener“
  jeden Betrag eintragen (z. B. 0,30 €) – praktisch mit Claude, wo 1 € schnell zu viel ist.
  Nova merkt sich deinen letzten Betrag.
- Kleinere Beträge zur schnellen Auswahl: 0,10 €, 0,25 €, 0,50 € und 1 €.
- Auch per Befehl (`/afk 0,30€ recherchiere …`) oder einfach gesagt („Ich bin weg,
  höchstens 30 Cent“).

## 0.8.0 – 2026-11-08

**Neues kostenloses Gehirn: Ollama**
- Neben Claude und DeepSeek gibt es jetzt **Ollama**: Die KI läuft direkt auf deinem PC –
  **ohne Schlüssel, ohne Kosten**, und deine Gespräche verlassen den Rechner nicht.
- Einrichten in **„Gehirn & Schlüssel“ → „Ollama“**: Nova zeigt, ob Ollama läuft, welche
  Modelle du hast, und lädt empfohlene Modelle per Knopfdruck herunter (mit Fortschritt).
  Ollama selbst installierst du einmal von ollama.com – der Knopf dafür ist direkt dort.
- Im Terminal: `/gehirn ollama`, `/ollama` (Status) und `/ollama laden <modell>`.
- Empfehlung: `qwen3.5:4b` (ca. 3–4 GB, kann Werkzeuge benutzen und Bilder sehen). Für
  stärkere PCs: `qwen3.5:9b`.
- Gut zu wissen: Lokale Modelle sind schwächer als Claude oder DeepSeek, und wie schnell sie
  antworten, hängt von deinem PC ab (mindestens 8 GB Arbeitsspeicher, mit Grafikkarte deutlich
  schneller). Kann ein Modell keine Werkzeuge benutzen oder keine Bilder sehen, sagt Nova dir das.

## 0.7.0 – 2026-11-08

**Bilder zeigen – Nova sieht mit**
- Du kannst Bilder in den Chat einfügen (**Strg+V**), ins Fenster ziehen oder über die
  **Büroklammer** auswählen – bis zu 10 pro Nachricht, auch ohne Text. Nova sieht sie und
  kann dir z.B. Fehlermeldungen, Fotos oder Bildschirmausschnitte erklären.
- Im Terminal geht das mit `/bild <Pfad>` oder indem du ein Bild hineinziehst.
- Klappt mit Claude und DeepSeek Flash direkt; bei DeepSeek V4 Pro schaut sich Flash das
  Bild kurz an und beschreibt es.
- Auch ihre eigenen Bildschirmfotos sieht Nova jetzt wirklich (nicht nur den Dateinamen).

**Bilder erstellen lassen – kostenlos**
- Sag einfach „Mal mir …“. Nova erstellt das Bild über **AI Horde** (kostenlos, ohne
  Anmeldung, manchmal mit etwas Wartezeit) und zeigt es direkt im Chat. Gespeichert wird es
  im Arbeitsordner unter `bilder/`.
- Schneller geht es optional mit einem kostenlosen **Cloudflare**-Konto – die Anleitung steht
  in „Gehirn & Schlüssel“ unter „Bilder“.
- Bitte keine persönlichen Daten in Bildbeschreibungen: Bei AI Horde werden sie öffentlich
  geteilt.

**Feedback & Bewertung**
- Neuer Knopf **„Feedback & Bewertung“** (und `/feedback`): Sterne vergeben, Lob, Ideen oder
  Fehler beschreiben, Bilder anhängen – und mit „Jetzt senden“ direkt an den Entwickler.
- Nach etwa einer Stunde Nutzung und danach alle paar Tage fragt Nova einmal freundlich
  nach. Das kannst du einfach wegklicken.
- Ohne Internet wird dein Feedback gespeichert und später automatisch nachgeschickt.

## 0.6.1 – 2026-11-08

- **Verknüpfungen bleiben nach einem Update richtig:** Hast du die App auf den Desktop
  oder in die Taskleiste gezogen, zeigt das Symbol nach einem Update jetzt weiter auf
  die neue Version. Bisher „wanderte“ es mit der alten Version in den Sicherungsordner
  „versionen“ – und ließ sich dann nicht mehr richtig öffnen.
- Symbole, die schon falsch zeigen, repariert Nova beim ersten Start der neuen Version
  von selbst. Wird trotzdem einmal eine alte gesicherte Version gestartet, öffnet Nova
  stattdessen die aktuelle.
- **Versionsnummer überall sichtbar:** im Fenstertitel, oben im Terminal, in der
  Seitenleiste – und bei der .exe unter Rechtsklick → Eigenschaften → Details.
- Klappt ein Update einmal nicht (z.B. weil der Virenscanner die neue Datei
  festhält), sagt Nova dir das beim nächsten Start – statt still die alte Version
  weiterlaufen zu lassen. Diese Version versucht sie dann nicht immer wieder von
  selbst, sondern erst, wenn du `/update` eingibst. Die bisherige Version bleibt
  dabei immer erhalten.

## 0.6.0 – 2026-11-08

**Schnell oder gründlich – du bestimmst, wie Nova denkt**
- Im Fenster **„Gehirn & Schlüssel“** kannst du jetzt das **Modell** und die
  **Denk-Tiefe** wählen – für Claude und für DeepSeek.
  - Claude: Opus 5.5 (stark), Sonnet 5.5 (schnell), Haiku 5.5 (blitzschnell und sehr
    günstig) und Fable 5.1 (das stärkste, aber langsamer und teurer).
  - DeepSeek: Flash (schnell, extrem günstig) und V4 Pro (stärker).
  - Denk-Tiefe von „schnell“ bis „maximal“. Denkt dir Claude zu lange nach? Stell
    auf „schnell“ oder „ausgewogen“.
  - Bei jedem Modell steht, wie schnell es ist und was es ungefähr kostet (in Euro).
- Du kannst es Nova auch einfach sagen: „Denk schneller“, „Nimm Sonnet“ – oder im
  Chat `/modell` und `/denken` eingeben. Das Gespräch läuft beim Wechsel weiter.
- DeepSeek hat seine alten Modellnamen abgeschaltet – Nova stellt automatisch auf
  die neuen um. Die Kosten-Anzeige rechnet jetzt mit dem Preis des gewählten Modells.

**Dazwischenreden und Warteschlange**
- Du kannst schreiben, während Nova noch arbeitet: Die Nachricht kommt in die
  **Warteschlange** und ist danach dran. Mit **Strg+Enter** (oder „Jetzt“) unterbrichst
  du Nova und sie kümmert sich sofort um die neue Nachricht.
- „Stopp“ hält an – wartende Nachrichten landen wieder im Eingabefeld, nichts geht verloren.

**AFK-Modus: „Ich bin mal weg“**
- Sag Nova „Ich bin jetzt AFK“ (oder drück „Ich bin weg“, oder `/afk` mit einem
  Auftrag) – dann arbeitet sie allein weiter, so wie du es nach allem, was sie über
  dich weiß, wollen würdest.
- Sicher: In der Zeit liest und recherchiert sie und legt neue Dateien im
  Arbeitsordner an. Sie **löscht, überschreibt, verschickt und startet nichts** –
  solche Schritte schreibt sie dir als **Vorschlag** auf. Mit Zeit- und Kosten-Grenze.
- Wenn du zurück bist (einfach eine Nachricht schreiben), bekommst du einen Bericht:
  was erledigt ist, welche Vorschläge auf dich warten und welche Fragen sie hat.

**Außerdem**
- Anzeige **„Auf dem neuesten Stand“** in der Seitenleiste – mit „Jetzt prüfen“.
- Fragt Nova gerade etwas („Darf ich …?“) und du lädst das Fenster neu oder öffnest
  ein zweites, siehst du die Frage dort wieder.
- Wird etwas abgebrochen, während Nova auf ein „Ja“ wartet, gilt das immer als „Nein“.
- Im Sprachmodus versteht Nova Abschiede („Tschüss Nova“, „Danke, ciao“) und erledigt
  eine gerade gegebene Bitte trotzdem noch.
- Neuer Schalter **„Gesprochenes sofort senden“**: Nach Mikrofon/F2 geht der Text
  gleich ab, ohne Enter.
- **Stützräder**: Im Zustand „teilweise“ öffnet ein Klick jetzt eine Auswahl
  (anlegen oder abnehmen) – vorher ließen sie sich scheinbar nicht abnehmen.

## 0.5.1 – 2026-11-08

- Die Beispiele im Fenster „Über mich“ (Name, Alter, Wohnort …) sind jetzt allgemein
  und enthalten keine persönlichen Angaben mehr. Deine eigenen Einträge bleiben
  unverändert.

## 0.5.0 – 2026-11-08

**Nova hat jetzt ein Gesicht: eine leuchtende Sphäre**
- Groß auf dem Startbildschirm (antippen = Jarvis-Modus), klein in der Seitenleiste
  und neben jeder Antwort. Sie **lebt mit**: atmet ruhig, kreist beim Nachdenken,
  bekommt einen Ring, wenn sie arbeitet, pulsiert beim Schreiben und Vorlesen,
  folgt deiner Stimme, wenn du ins Mikrofon sprichst, und leuchtet bei einer
  Rückfrage gelb.
- Sag Nova einfach, wie ihre Sphäre aussehen soll: „Mach deine Sphäre orange“,
  „beweg dich lebhafter“ oder „zeig lieber deinen Buchstaben“.

**Einrichtung direkt in der App**
- Neues Fenster **„Gehirn & Schlüssel“**: DeepSeek oder Claude auswählen, Schlüssel
  einfügen, „Prüfen & speichern“ – mit Anleitung, wo es den Schlüssel gibt, und
  klaren Meldungen (z.B. „Guthaben leer“ mit Knopf zum Aufladen). Öffnet sich beim
  ersten Start von selbst; später über die Karte „Gehirn“.
- Knopf **„Terminal-Version öffnen“** in der Seitenleiste.

**Repariert**
- Ist für das eingestellte Gehirn kein Schlüssel da, aber für das andere schon, nimmt
  Nova automatisch das mit Schlüssel (z.B. DeepSeek statt Claude).
- Beim Speichern einer Einstellung konnte unter Windows die Datei `settings.toml`
  kaputtgehen („invalid character '\r'“) – behoben, und kaputte Dateien repariert
  Nova beim Start selbst.
- Ein in den Chat kopierter Schlüssel ist nie mehr in voller Länge zu sehen.
- Meldungen mit echten Umlauten, flüssigere Fenster.

## 0.4.3 – 2026-11-08

- **Die App verschwindet nicht mehr still.** Stürzt das App-Fenster ab oder bleibt es
  leer, sagt Nova dir Bescheid und öffnet sich auf Wunsch im Browser-Fenster. War es
  beim letzten Mal abgestürzt, bietet sie das gleich beim nächsten Start an.
- Das App-Fenster speichert seine Daten jetzt in einem lokalen Ordner (statt auf dem
  Desktop bzw. in OneDrive, wo es Probleme machen konnte).
- Auch „KI-App.exe.exe“ (passiert leicht, wenn Windows die Endungen ausblendet) startet
  als App und findet beim Update die richtige Datei.
- Jede neue Version wird vor der Veröffentlichung auf einem echten Windows gestartet –
  nur wenn das Fenster aufgeht, wird sie veröffentlicht.

## 0.4.2 – 2026-11-08

- **KI-App.exe startet auch mit anderem Namen.** Lädt man sie zweimal herunter, nennt
  Windows sie „KI-App (1).exe“ – dann blieb das Fenster aus. Jetzt egal, und auch der
  Updater findet seine Datei.
- **Nie mehr still verschwinden:** Kann sich das App-Fenster nicht öffnen, sagt Nova es
  dir und bietet an, sie im Browser-Fenster zu öffnen. Was schiefging, steht in
  `logs\ki.log` (harte Abstürze in `logs\absturz.log`).
- **Feinschliff der App:** Jarvis-Ansicht mit zwei offenen Fenstern (nur eins liest vor),
  Tour passt sich an große Schrift und schmale Fenster an, Scrollen, Fokus nach dem
  Speichern, Schlüssel-Fehler werden klarer angezeigt.
- Jarvis fängt nach „Chat-Modus“ nichts Neues mehr an.

## 0.4.1 – 2026-11-08

- **KI-App.exe startet wieder.** Sie brach beim Öffnen mit einer Fehlermeldung
  („NoneType … isatty“) ab – behoben.
- **Schlüssel einfach im Chat einfügen** – in der App und im Terminal: Kopier deinen
  DeepSeek-Schlüssel (`sk-…`) oder Claude-Schlüssel (`sk-ant-…`) in das Eingabefeld
  und drück Enter. Nova erkennt, wofür er ist, probiert ihn kurz aus, speichert ihn
  und schaltet das passende Gehirn ein. Der Schlüssel wird nie an die KI geschickt
  und nur gekürzt angezeigt.
- **Verständliche Meldungen**, wenn der Schlüssel nicht geht: falsch kopiert,
  Guthaben leer (mit Hinweis, wo du aufladen kannst) oder keine Internetverbindung.
- `/gehirn` zeigt, welches Gehirn aktiv ist, und wechselt zwischen DeepSeek und
  Claude. `/terminal` öffnet aus der App die Terminal-Version – eine Datei für beides.
- Ein in der App eingetragener Schlüssel hat jetzt Vorrang vor einem alten Schlüssel,
  der irgendwo in Windows hinterlegt ist.

## 0.4.0 – 2026-11-07

**Die KI als App**
- Neu: die KI als **eigenes Programm** mit eigenem Fenster und Symbol in der
  Taskleiste – kein Browser. Starten mit **start-app.bat** oder **KI-App.exe**.
  Das Terminal (`start.bat` bzw. `KI.exe`) gibt es weiterhin – dieselbe KI,
  dasselbe Gedächtnis.
- In der App: Antworten mit Überschriften, Listen, Tabellen und Codeblöcken (mit
  Kopier-Knopf), Werkzeug-Schritte und Agenten übersichtlich, Rückfragen als Knöpfe
  („Einmal erlauben“, „Immer erlauben“, „Nein“), ein **Stopp-Knopf**, ein
  **Mikrofon-Knopf** (halten oder klicken, F2 geht auch) und eine Seitenleiste mit
  Kosten, Gedächtnis, Updates, Autostart und dem Schalter „Alles erlauben“.
- `/app` wechselt aus dem Terminal in die App, `/verknuepfung` legt ein Symbol auf
  den Desktop. Wer immer die App will: `oberflaeche = "app"` unter `[ki]`.

**Charakter & Profil**
- Wähle, wie Nova sein soll: **freundlich, sachlich, Butler (Jarvis-Stil),
  Mentor, bester Kumpel, kreativ oder Motivations-Coach** – und bearbeite die
  Persönlichkeit danach frei. Stil einstellbar: du/Sie, kurz oder ausführlich,
  wie viel Humor, mit oder ohne Emojis.
- **Über mich:** Trag ein, was Nova über dich wissen soll (Name, wie sie dich
  nennen soll, Hobbys, Projekte, was dir wichtig ist, was sie nie tun soll).
- In der App unter „Charakter & Profil“ (auch Werte und Gedächtnis ansehen,
  ergänzen und löschen), im Terminal mit `/charakter`, `/stil`, `/ueber-mich`,
  `/werte bearbeiten`. Mit **`/neu`** beginnt ein neues Gespräch, in dem alles
  gleich gilt.

**Jarvis-Modus: einfach mit Nova reden – live**
- Ein Knopf (oder `/jarvis`) und du redest einfach mit ihr, ganz ohne Tippen.
  Zurück zum Chat: „Chat-Modus“ sagen oder den Knopf drücken.
- Nova **schreibt mit, während du sprichst** (offline, ohne Kosten), und legt
  schon nach einer **kurzen Sprechpause** los. Sie **spricht ab dem ersten
  fertigen Satz**, statt auf die ganze Antwort zu warten.
- **Du kannst sie jederzeit unterbrechen** – sie hört sofort auf zu reden und hört
  dir zu. Sagst du kurz nach deiner Frage noch etwas („… in Berlin“), nimmt sie
  das mit dazu.
- Rückfragen („Darf ich die Datei ändern?“) beantwortest du einfach mit „ja“,
  „immer“ oder „nein“.
- Beim ersten Mal lädt sie dafür einmalig ein deutsches Sprachmodell (~50 MB).
  Ganz ohne Wartezeit wie bei Gemini geht es nicht, weil DeepSeek und Claude nur
  Text verstehen – aber meist antwortet sie nach 1–2 Sekunden.

**Nova gestaltet die App, Tutorial, Stützräder**
- Sag Nova, wie die App aussehen soll („mach alles grün“, „größere Schrift“,
  „eckige Knöpfe“) – sie ändert es sofort. `/aussehen zuruecksetzen` holt das
  Original zurück.
- **Tutorial:** Nova stellt sich vor und zeigt dir an Beispielen, was sie kann
  (`/tutorial` oder Knopf „Tour“).
- **Stützräder** an/aus direkt im Programm: an = sie fragt vor Änderungen und
  bleibt im Arbeitsordner; aus = sie darf am ganzen PC alles ohne zu fragen
  (automatische Starts fragt sie trotzdem).

**Neuer Name: NOVA**
- Die KI heißt jetzt **Nova** – **N**eugierige, **O**ffene, **V**ernetzte
  **A**ssistenz. Wer noch „Aria“ eingestellt hatte, bekommt den neuen Namen
  automatisch. Mit `/name` kannst du ihr jederzeit einen anderen Namen geben,
  z.B. `/name MAX = Mein Assistent X`.

## 0.3.2 – 2026-11-07

- **Einmal zustimmen reicht:** Bei jeder Rückfrage kannst du jetzt **a** eingeben
  („ab jetzt immer“). Dann macht die KI alles durch, ohne noch einmal zu fragen –
  dauerhaft, auch nach einem Neustart. Ein- und ausschalten geht auch mit
  `/erlauben alles` und `/erlauben fragen`.
- Die `start.bat` eines Spiels oder Projekts löst keine „KI startet sich selbst“-
  Rückfrage mehr aus – nur noch die `start.bat` der KI.

## 0.3.1 – 2026-11-07

- `/autostart` findet jetzt auch ein Hintergrund-Skript, das genau **dieses**
  Fenster geöffnet hat (der typische „Wächter“, der die KI alle paar Minuten neu
  startet), und die KI sagt beim Start Bescheid, wenn so ein Skript sie geöffnet hat.
- Nachschauen und Entfernen (z.B. „schau in der Aufgabenplanung nach und lösch
  den Eintrag“) läuft ohne Alarm-Rückfrage – nur das Einrichten fragt nach.
- Ein abgestürztes oder geschlossenes Fenster sperrt den nächsten Start nicht mehr.
- Bricht die Verbindung zu Claude mitten in einer Antwort ab, stürzt die KI nicht
  mehr ab, sondern versucht es neu oder sagt Bescheid.
- Strg+C behält alles, was schon fertig ist – die KI weiß danach noch, was sie
  getan hat. Auch Strg+C beim Vorlesen schließt die KI nicht mehr.
- Agenten liefern immer einen Abschlussbericht, und der wird nicht mehr gekürzt.

## 0.3.0 – 2026-11-07

**Öffnet sich nicht mehr von selbst**
- Neuer Befehl `/autostart`: zeigt alles, was die KI automatisch startet
  (Aufgabenplanung, Autostart, Hintergrund-Skripte), und stellt es mit
  `/autostart entfernen` ab. Außerdem siehst du, wer sie zuletzt gestartet hat.
- Die KI richtet keinen automatischen Start mehr ein und startet sich nicht selbst
  neu, ohne dich ausdrücklich zu fragen – auch wenn „alles erlauben“ an ist.
- Es öffnet sich nur noch ein KI-Fenster; ein zweiter Start schließt sich still.
- Wird die KI unerwartet automatisch gestartet, sagt sie dir das gleich zu Beginn.

**Hängt nicht mehr**
- Bricht die Verbindung zu Claude/DeepSeek ab, wartet sie nicht mehr bis zu
  10 Minuten, sondern versucht es nach kurzer Zeit neu.
- „denkt nach (12 s)“ zeigt, dass sie arbeitet.
- **Strg+C** hält nur die laufende Antwort an – die KI bleibt offen und du kannst
  gleich weiterschreiben.

**Arbeitet durch, mit Agenten und Selbstkontrolle**
- Am Schritt-Limit macht sie von selbst weiter (bis zu 3-mal, einstellbar), statt
  nach „weiter“ zu fragen.
- Große Aufgaben verteilt sie auf **Agenten** mit frischem Kopf: „recherche“
  (sucht und fasst zusammen), „helfer“ (erledigt eine Teilaufgabe), „prüfer“
  (sucht kritisch nach Fehlern). Deine Werte gelten auch für die Agenten.
- Bevor sie größere Arbeiten als fertig meldet, prüft sie sie selbst (z.B. Code
  ausführen) und lässt Wichtiges von einem Prüfer-Agenten gegenchecken.

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
