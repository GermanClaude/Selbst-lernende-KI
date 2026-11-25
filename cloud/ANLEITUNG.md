# Nova in der Cloud – läuft, auch wenn dein PC aus ist

Die Cloud-Nova ist ein eigenes Programm im Internet. Die **Nova-Handy-App** verbindet sich mit ihr, und auf
**Telegram** antwortet sie rund um die Uhr. Ob dein PC an oder aus ist, spielt dann keine Rolle.

> **Wichtig zu wissen:** Die Cloud-Nova ist eine *eigene* Nova. Ihr Gedächtnis ist (noch) getrennt von der
> Nova auf deinem PC. Sie kann deinen PC nicht steuern und keine Dateien auf ihm sehen – sie läuft ja auf
> einem fremden Rechner.

Es gibt zwei Wege:

| | **Render (kostenlos)** | **Eigener Server (z. B. Hetzner)** |
|---|---|---|
| Kosten | 0 € | ca. 6–7 €/Monat |
| Bezahlen | keine Karte nötig (laut Render) | SEPA-Lastschrift oder Überweisung (ggf. Ausweis-Prüfung) |
| Läuft | schläft nach 15 Min. ohne Besuch, wacht in ca. 1 Min. wieder auf | immer |
| Gedächtnis | **beginnt nach jedem Aufwachen neu** | bleibt dauerhaft |
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

## Telegram

Ist `TELEGRAM_BOT_TOKEN` gesetzt, schickt Telegram die Nachrichten an deinen Bot direkt an die Cloud-Nova
(„Webhook“). Eine Nachricht weckt eine schlafende Render-Nova auch auf – die erste Antwort dauert dann etwa
eine Minute.

Telegram erlaubt nur **einen** Empfänger pro Bot: Solange die Cloud-Nova ihn beantwortet, brauchst du am PC
`/handy` nicht (am PC meldet Nova dann einen „Conflict“). Zurück zum PC: in der Cloud
`TELEGRAM_BOT_TOKEN` entfernen und einmal `https://api.telegram.org/bot<DEIN-BOT-TOKEN>/deleteWebhook` im
Browser aufrufen. Oder: für die Cloud bei @BotFather einen zweiten Bot anlegen.

## Sicherheit

- Ohne den Schlüssel (`?t=…`) kommt niemand an Nova heran. Die Adresse mit Schlüssel nicht weitergeben.
- Die Telegram-Adresse ist doppelt geschützt (geheimer Pfad + geheime Kopfzeile, die nur Telegram kennt),
  und Nova antwortet nur deiner Chat-ID.
- Deine KI-Schlüssel liegen beim Anbieter als geheime Werte, nicht im Code.
