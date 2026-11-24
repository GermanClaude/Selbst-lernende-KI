# Neuigkeiten

Jede Version hat hier einen Abschnitt `## <Version> – <Datum>`. Der Updater zeigt
beim Aktualisieren alle Abschnitte zwischen deiner und der neuen Version an, und
deine KI erklärt sie dir in eigenen Worten.

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
