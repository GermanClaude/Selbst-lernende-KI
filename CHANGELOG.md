# Neuigkeiten

Jede Version hat hier einen Abschnitt `## <Version> – <Datum>`. Der Updater zeigt
beim Aktualisieren alle Abschnitte zwischen deiner und der neuen Version an, und
deine KI erklärt sie dir in eigenen Worten.

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
