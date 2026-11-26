# Nova in der Cloud – läuft, auch wenn dein PC aus ist

Die Cloud-Nova ist ein eigenes Programm im Internet. Die **Nova-Handy-App** verbindet sich mit ihr, und auf
**Telegram** antwortet sie rund um die Uhr. Ob dein PC an oder aus ist, spielt dann keine Rolle.

> **Wichtig zu wissen:** Die Cloud-Nova läuft auf einem fremden Rechner – sie kann deinen PC nicht steuern
> und keine Dateien auf ihm sehen. Ihr **Gedächtnis teilt sie mit der PC-Nova**, wenn du den Abgleich
> einrichtest (siehe unten, „Gedächtnis-Abgleich“).

Es gibt zwei Wege:

| | **Render (kostenlos)** | **Eigener Server (z. B. Hetzner)** |
|---|---|---|
| Kosten | 0 € | ca. 6–7 €/Monat |
| Bezahlen | keine Karte nötig (laut Render) | SEPA-Lastschrift oder Überweisung (ggf. Ausweis-Prüfung) |
| Läuft | schläft nach 15 Min. ohne Besuch, wacht in ca. 1 Min. wieder auf | immer |
| Gedächtnis | nur mit Abgleich (sonst beginnt es nach jedem Aufwachen neu) | bleibt dauerhaft |
| Arbeitsspeicher | 512 MB (knapp, reicht) | 2–4 GB |

## Weg 1: Render (kostenlos)

1. Konto auf [render.com](https://render.com) anlegen (Anmeldung mit GitHub ist am einfachsten).
2. Diese Adresse öffnen: `https://render.com/deploy?repo=https://github.com/GermanClaude/Selbst-lernende-KI`
   – Render liest die Datei `render.yaml` und schlägt den Dienst **nova** vor (Tarif *Free*, Frankfurt).
3. Render fragt nach den Werten:
   - `ANTHROPIC_API_KEY` oder `DEEPSEEK_API_KEY` – mindestens einen KI-Schlüssel (die anderen leer lassen)
   - `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` – aus der `.env` auf deinem PC (optional, für Telegram)
   - `NOVA_TOKEN` erzeugt Render selbst.
4. *Apply* – nach ein paar Minuten läuft Nova. Oben auf der Seite des Dienstes steht die Adresse,
   z. B. `https://nova-ab12.onrender.com`. Den Schlüssel findest du unter *Environment → NOVA_TOKEN*.
5. In der Handy-App: Zurück-Taste → **„Nova in der Cloud“** →
   `https://nova-ab12.onrender.com/?t=<NOVA_TOKEN>` eintragen → *Mit der Cloud verbinden*.

Neue Nova-Versionen spielt Render von selbst ein (sobald sie auf GitHub erscheinen).

## Weg 2: Eigener Server (läuft immer, Gedächtnis bleibt)

1. Einen kleinen Linux-Server mieten, z. B. bei [Hetzner](https://www.hetzner.com/cloud) (Ubuntu, kleinste
   Größe reicht).
2. Per SSH anmelden und einfügen:
   `curl -fsSL https://raw.githubusercontent.com/GermanClaude/Selbst-lernende-KI/ccr-cfa1ff8c-wgsyxb/cloud/server-installieren.sh | sh`
3. Das Skript installiert Docker, lädt Nova und legt `/opt/nova/cloud/.env` an. Dort deine Schlüssel
   eintragen (`nano /opt/nova/cloud/.env`) und das Skript nochmal ausführen.
4. Am Ende steht die Adresse da, z. B. `https://203-0-113-7.sslip.io/?t=…` – die trägst du in der Handy-App
   unter **„Nova in der Cloud“** ein. https gibt es automatisch (kostenloses Zertifikat, auch ohne eigene
   Domain dank sslip.io; eigene Domain: `NOVA_DOMAIN=nova.example.de` vor dem Skript setzen).

Update: Skript nochmal ausführen.

## Gedächtnis-Abgleich (PC ↔ Cloud)

Am PC `/abgleich` eingeben – Nova zeigt die drei Schritte (privates GitHub-Repo anlegen, Token mit
*Contents: Read and write* nur für dieses Repo, `/abgleich einrichten …`). Danach dieselben drei Werte in
der Cloud eintragen: `NOVA_ABGLEICH_REPO`, `NOVA_ABGLEICH_TOKEN`, `NOVA_ABGLEICH_PASSWORT` (bei Render unter
*Environment*, beim eigenen Server in `cloud/.env`, danach das Skript nochmal ausführen).

Die Ablage ist mit deinem Passwort verschlüsselt. Bei Render holt sich die Cloud-Nova ihr Gedächtnis nach
jedem Aufwachen wieder aus dem Repo – so geht trotz fehlendem Speicher nichts verloren.

## Telegram

Ist `TELEGRAM_BOT_TOKEN` gesetzt, schickt Telegram die Nachrichten an deinen Bot direkt an die Cloud-Nova
(„Webhook“). Eine Nachricht weckt eine schlafende Render-Nova auch auf – die erste Antwort dauert dann etwa
eine Minute.

Telegram erlaubt nur **einen** Empfänger pro Bot: Solange die Cloud-Nova ihn beantwortet, brauchst du am PC
`/handy` nicht (am PC meldet Nova dann einen „Conflict“). Zurück zum PC: in der Cloud
`TELEGRAM_BOT_TOKEN` entfernen und einmal `https://api.telegram.org/bot<DEIN-BOT-TOKEN>/deleteWebhook` im
Browser aufrufen. Oder: für die Cloud bei @BotFather einen zweiten Bot anlegen.

## Anrufe, Zeitplan und Handy-Steuerung aus der Cloud

- **Anrufe (Vonage):** `VONAGE_APP_ID`, `VONAGE_PRIVATE_KEY` und `ANRUF_NUMMER` eintragen
  (`ANRUF_ANBIETER=vonage`). Für `VONAGE_PRIVATE_KEY` den ganzen Inhalt der `private.key` einfügen (mehrzeilig
  geht; sonst als eine Zeile mit `\n` oder Base64). Die Cloud-Nova ist selbst erreichbar, deshalb hört sie
  deine Antwort am Telefon und kann ganze **Gespräche** führen („ruf mich an“), ohne cloudflared.
  Bland geht auch: `BLAND_API_KEY`.
- **Zeitplan:** „Ruf mich morgen um 8 an“ und Ähnliches führt die Cloud-Nova zur Uhrzeit von selbst aus
  (Zeitzone `NOVA_ZEITZONE`, Standard Europe/Berlin). Auf **Render Free** besucht Nova alle 10 Minuten ihre
  eigene Adresse, solange etwas geplant ist, damit sie nicht einschläft (abschalten: `NOVA_WACH_HALTEN=0`).
  Ohne dauerhaften Speicher gehen geplante Aufgaben bei einem Neustart verloren. Zuverlässig ist ein
  eigener Server (Weg 2).
- **Handy-Steuerung:** In der Nova-Handy-App die Cloud-Adresse eintragen und *Handy-Steuerung einschalten*.
  Das Handy holt sich dann die Aufträge bei der Cloud-Nova ab, auch wenn die App zu ist.

## Lizenzserver für Premium (nur für den Entwickler)

Deine Cloud-Nova kann die Premium-Pakete ausgeben – dann steckt in keinem Code mehr ein Schlüssel.

1. Auf GitHub einen **fein-granularen Token** anlegen: nur Repo *Nova-Premium*, Rechte *Contents: Read-only*.
2. Beim Anbieter (Render → Environment) eintragen: `NOVA_LIZENZSERVER` = `1` und
   `NOVA_PREMIUM_REPO_TOKEN` = der Token. Neu starten.
3. Im Codegenerator unter *Einstellungen → Adresse deiner Cloud-Nova* die https-Adresse eintragen
   (z. B. `https://nova-ab12.onrender.com`). Jeder neue Code enthält dann nur diese Adresse.
4. Paket bauen (`python werkzeuge/paket_bauen.py`) und `pakete/nova-premium.zip` + `.json` ins private Repo
   pushen.

Prüfen: `https://<deine-adresse>/lizenz/sperrliste` liefert die Sperrliste (oder „nicht gefunden“, solange du
noch nichts gesperrt hast). Ist der Lizenzserver aus, antworten beide Adressen mit 404.

## Sicherheit

- Ohne den Schlüssel (`?t=…`) kommt niemand an Nova heran. Die Adresse mit Schlüssel nicht weitergeben.
- Die Telegram-Adresse ist doppelt geschützt (geheimer Pfad + geheime Kopfzeile, die nur Telegram kennt),
  und Nova antwortet nur deiner Chat-ID.
- Deine KI-Schlüssel liegen beim Anbieter als geheime Werte, nicht im Code.
- Die Anruf-Adressen (`/vonage/…`) enthalten ein Zufallsgeheimnis und gelten nur, solange ein Anruf läuft.
- Die Handy-Steuerung meldet sich mit demselben Schlüssel (`?t=…`) an wie die App.
