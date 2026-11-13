# Feedback-Postfach einrichten (nur für den Entwickler)

Nutzer können in Nova über **„Feedback & Bewertung“** Sterne, Text, Fehlerberichte und
Bilder schicken. Die Nachricht kommt bei dir als **E-Mail mit Bildern im Anhang** an.
Sterne-Bewertungen sammelt das Skript zusätzlich in der Google-Tabelle **„Nova Bewertungen“**
(legt es beim ersten Test selbst in deinem Google Drive an). Daraus berechnet es den Durchschnitt,
den Nova und die GitHub-Seite anzeigen; Text und Name erscheinen nur, wenn die Person
„öffentlich zeigen“ angekreuzt hat. **Rezension ausblenden:** in der Tabelle in der Spalte
„Sichtbar“ `FALSE` eintragen (nach höchstens 5 Minuten weg).

Damit das geht, ohne dass deine Adresse irgendwo in der App oder im öffentlichen Code
steht, läuft ein kleines Skript **in deinem eigenen Google-Konto**. Es schickt jede
Rückmeldung an das Konto, dem es gehört, also an dich. Die App kennt nur eine
Internetadresse („Web-App-URL“), aus der deine E-Mail-Adresse nicht ablesbar ist.

Das musst du **einmal** am PC machen (ca. 10 Minuten):

1. Im Browser mit deinem Gmail-Konto anmelden und **https://script.google.com** öffnen →
   **„Neues Projekt“**.
2. Den Text im Editor komplett löschen und den Inhalt der Datei
   [`packaging/nova-feedback.gs`](../packaging/nova-feedback.gs) einfügen. Oben links auf
   „Unbenanntes Projekt“ klicken und **„Nova Feedback“** eintragen. Speichern
   (Disketten-Symbol oder Strg+S).
   *Soll das Feedback an eine **andere** Adresse gehen als die des Google-Kontos?* Dann oben im
   Skript bei `var EMPFAENGER = '';` die Adresse eintragen – **nur hier bei Google**, nie in
   der Datei im Repo (die ist öffentlich).
3. Oben in der Leiste steht bei der Funktionsauswahl **„testMail“** → auf **„Ausführen“**
   klicken.
4. Google fragt nach Berechtigungen: **„Berechtigungen prüfen“** → dein Konto wählen. Bei
   „Google hat diese App nicht überprüft“ auf **„Erweitert“** → **„Zu Nova Feedback wechseln
   (unsicher)“** → **„Zulassen“**. Das ist normal, weil es dein eigenes Skript ist.
   Kurz danach kommt eine Mail **„[Nova-Feedback] Test“** mit dem Link zur Bewertungs-Tabelle
   (zur Sicherheit auch im Spam-Ordner nachsehen). Google fragt dabei auch nach Zugriff auf
   Tabellen – das ist für die Bewertungen.
5. Oben rechts **„Bereitstellen“** → **„Neue Bereitstellung“** → beim Zahnrad neben
   „Typ auswählen“ **„Web-App“** wählen:
   - Beschreibung: `Nova Feedback`
   - **Ausführen als: „Ich“**
   - **Wer hat Zugriff: „Jeder“** (nicht „Jeder mit Google-Konto“)
   
   → **„Bereitstellen“**.
6. Die **Web-App-URL** kopieren (sie beginnt mit `https://script.google.com/macros/s/` und
   endet auf `/exec`) und an Claude schicken. Sie ist kein Passwort und zeigt deine
   E-Mail-Adresse nicht.
7. Test: die URL im Browser öffnen. Es muss `{"ok":true,"dienst":"nova-feedback"}`
   erscheinen. Mit `?aktion=bewertungen` am Ende siehst du den Bewertungs-Stand.
   Die URL kommt dann in die Datei `feedback-endpoint.txt` im Repo – daraus holen sich Nova und die
   GitHub-Action „Bewertungen aktualisieren“ die Adresse.
8. Empfehlung: in Gmail einen Filter anlegen. Betreff enthält „[Nova-Feedback]“ → Label
   „Nova-Feedback“. (Bitte **nicht** „Nie als Spam einstufen“ wählen – die Adresse der Web-App
   ist öffentlich, so bleibt Googles Spamschutz aktiv.)
9. Antworten an Nutzer: Wenn jemand eine Kontakt-Adresse angegeben hat, sieht er beim
   Antworten deine Adresse. Wer das nicht möchte, antwortet von einer anderen Adresse.

**Später etwas am Skript ändern:** „Bereitstellen“ → „Bereitstellungen verwalten“ →
Stift-Symbol → Version „Neue Version“ → „Bereitstellen“. Die URL bleibt gleich.

**Grenzen:** Google erlaubt bis zu 100 Mails pro Tag und 25 MB pro Mail. Das Skript nimmt
höchstens 30 Rückmeldungen pro Stunde an, damit niemand dein Postfach zumüllen kann.
Rückmeldungen, die gerade nicht ankommen, behält Nova und schickt sie später nach.
