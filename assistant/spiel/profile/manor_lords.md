# Manor Lords – dein Spielwissen

Stand: Version 0.8.117 (Nov. 2026, Early Access). Mittelalterlicher Städtebau mit Wirtschaft, nur Einzelspieler. Die Haupt-Oberfläche wurde mit Major Update #8 (Aug. 2026) neu gebaut – Positionen aus alten Guides stimmen nicht. Verlass dich auf das, was du im Bild siehst, und auf deine Kalibrierung. Oberflächensprache kann Deutsch oder Englisch sein.

## Steuerung (Standardbelegung)
- Leertaste = Pause/Weiter (schaltet um). X = schneller, Z = langsamer. Esc = Menü/Platzierung abbrechen (bis nichts mehr offen ist).
- Kamera: W/A/S/D bewegen, Mausrad = Zoom (Aktion `scrollen`), T = Kamera zur Stadt. Drehen: `kamera_drehen` (mittlere Maustaste halten + Maus bewegen). Ein KURZER Klick der mittleren Taste setzt die Drehung auf Norden zurück. Im Zweifel nicht drehen – Nordausrichtung ist leichter zu lesen.
- C = Bau-Menü, R = Straßen, H = Hofstätte (Burgage Plot), M = Regionskarte, Tab = Info-Schilder über Gebäuden (Status, Arbeiter, Ertrag) – mit `tasten_halten` und `bild_waehrend: true` ansehen.
- Im Gebäude-Panel: E/Q = Familie zuweisen/entlassen (bzw. Kategorie im Baumenü wechseln). Strg+0–9 Kontrollgruppe setzen, 0–9 wählen.
- NIEMALS Strg+C (Kinomodus: die ganze Oberfläche verschwindet). Ist die Oberfläche weg, einmal Strg+C geht nicht (gesperrt) – sag es im Tagebuch als Problem.
- Speichern: Esc → „Speichern/Save“ → neuer Name oder rotierend „Nova_A/B/C“. Schnellspeicher-Taste unbekannt.

## Bauen mit der Maus
- Gebäude: Bau-Menü (C) → Kategorie → Gebäude → der „Geist“ hängt an der Maus → Linksklick setzt. Drehen: Linke Taste halten und seitlich ziehen (`ziehen` mit `relativ: true`, kurze Strecke). Rot = ungültig, weiß/grün = gültig. „Snap to Roads“ richtet Gebäude an Straßen aus.
- Flächen (Hofstätten, Felder, Weiden, Gärten, Marktplatz): Eckpunkte nacheinander per Linksklick setzen (Polygon). Bei Hofstätten: +/- ändert die Zahl der Grundstücke, gebogener Pfeil dreht die Front, **Hammer-Symbol bestätigt** den Bau.
- Straßen (R): Start klicken, weitere Punkte klicken, Abschluss mit Rechtsklick oder Hammer (im Bild prüfen). Über einen Fluss entsteht automatisch eine Brücke.
- Zwischen Klicks kurze Pausen lassen. Rechtsklick in Menüs schließt meist.
- Nach jeder Platzierung prüfen: Erscheint die Baustelle (Gerüst/Markierung)? Sonst Esc und neu.
- Abreißen nur nach genauer Prüfung (Gebäude anklicken → Demolish). Hofstätten kann man nicht verlegen.

## Oberfläche (Inhalt, Position bitte selbst kalibrieren)
- Obere Leiste (gilt für die Region, in der die Kamera ist): unbeschäftigte Familien, beschäftigte Familien, Wohnraum, Bevölkerung, **Zustimmung (Approval)**, öffentliche Ordnung; Regionaler Wohlstand; Vieh; **Vorräte: Monate Nahrung und Brennstoff** (überlebenswichtig); Siedlungsmenü (Stufe, Perks); Surplus (Bestand minus Bau-Reserve – immer gegen Surplus planen).
- Zeit-Widget: Datum, Jahreszeit, Pause/Tempo. Monatswechsel ist der wichtigste Takt.
- Werkzeugleiste: Straßen, Bauen, Armee, Karte, Hilfe (In-Game-Wiki), Einstellungen.
- Hover über Zustimmung zeigt, was den Hofstätten fehlt (rot = fehlt). Records-Bildschirm = Produktion vs. Verbrauch je Ware.
- Problem-Banner (Icons ohne Text, Hover zeigt Text; Klick springt zum Gebäude): „Storage Full“, „Homeless“, „No Ox Guide“, „Unburied bodies“, „Construction goods missing“ …
- Popups (Hunger, Tutorial) mit Klick auf OK oder Esc schließen.
- Tooltips erscheinen verzögert: nach `maus_bewegen` eine `warten`-Aktion (0,5 s) und dann das Bild ansehen.

## Begriffe (EN → DE)
Burgage Plot = Hofstätte · Backyard = Hinterhof · Approval = Zustimmung · Regional Wealth = Regionaler Wohlstand · Treasury = Schatzkammer · Influence = Einfluss · Settlement Level = Siedlungsstufe · Timber = Bauholz · Firewood = Brennholz · Planks = Bretter · Logging Camp = Holzfällerlager · Woodcutter's Lodge = Brennholzhütte · Sawpit = Sägegrube · Granary = Kornspeicher · Storehouse = Lagerhaus · Marketplace/Stall = Marktplatz/Marktstand · Hitching Post = Anbindepfosten · Well = Brunnen · Wooden Church = Holzkirche · Manor = Herrenhaus · Farmhouse/Field = Bauernhaus/Feld · Hunting Camp = Jägerlager · Forager Hut = Sammlerhütte · Trading Post = Handelsposten · Tithe/Land Tax = Zehnt/Grundsteuer.

## Wirtschaft – Grundregeln
- Familien sind die Arbeitseinheit; jede isst ~1 Nahrung/Monat und braucht Brennstoff (Winter mehr).
- **Immer mindestens 1 Familie unbeschäftigt lassen** – nur sie bauen und führen Ochsen (beim großen Bauprogramm 2–3).
- Ochsen transportieren Bauholz; jeder braucht einen Platz am Anbindepfosten, sonst läuft er weg.
- Verteilung über Marktstände: Kornspeicher-Familien betreiben Essensstände, Lagerhaus-Familien Waren-Stände. Ohne Personal kein Verkauf.
- Waren im Freien können verderben → Lager früh bauen. Werkzeug nie ausgehen lassen (Wartung).
- Zustimmung: ≥ 50 % → etwa +1 Familie/Monat, ≥ 75 % → +2; < 50 % kein Zuzug, < 25 % Familien gehen. Zuzug braucht freien Wohnraum. Grundsteuer über ~10 % kostet Zustimmung.

## Bewährte Eröffnung (Jahr 1, Start im Frühling)
1. Pausiert bleiben, Gelände ansehen: Fruchtbarkeit, Höhe, Vorkommen (Beeren/Pilze, Wild/Fisch), Wald, Fluss, Handelspunkt am Königsweg.
2. Anbindepfosten bauen, zweiten Ochsen bestellen.
3. Holzfällerlager direkt am Wald/an liegenden Stämmen (2–3 Familien).
4. Kornspeicher und Lagerhaus zentral nebeneinander (je 1 Familie).
5. Hofstätten (H) kompakt, bis ~6, rund um einen freien Platz für den Marktplatz. Mindestens 1 Familie frei lassen.
6. Marktplatz mit Ständen (Nahrung, Brennholz, später Kleidung) im Zentrum.
7. Brunnen (~15 Familien), Nahrung: Jägerlager/Sammlerhütte/Fischerhütte am nächsten (reichen) Vorkommen – nie auf Beeren-/Pilzfelder bauen.
8. Brennholzhütte vor dem Herbst besetzen.
9. Holzkirche, sobald „Small Village“ (Einfluss, nötig für Hofstätten-Stufe 2).
10. Felder: mehrere kleine (0,5–0,7 Morgen) statt eines großen; Bauernhaus mit ~3 Familien. Hafer = bestes frühes Getreide (Frühjahrssaat, direkt essbar). Weizen/Roggen = Wintergetreide (Herbstsaat).
11. Ziel bis Oktober: ≥ 6 Monate Nahrung, Brennholz-Puffer.
12. Sägegrube (Bretter) für Upgrades und Kirche; Handelsposten: wenige Überschusswaren verkaufen, Werkzeug-Reserve ~5.

## Hofstätten
Stufen 1–4. Stufe 1: Wasser, Brennstoff, Kirche, 2 Nahrungssorten. Stufe 2: + Kleidung, Getränk (Taverne), mehr Vielfalt. Stufe 3: + Schuhe; schaltet Bäcker/Schuster/Käsehändler frei. Upgrade-Blocker sind fast immer Vielfalt, Reichweite oder Personal. Hinterhöfe: Hühnerstall = billigste frühe Nahrung, Gemüsegarten, Ziegen.

## Checkliste am Monatsanfang
- Unbeschäftigte Familien ≥ 1? Wohnraum ≥ Familien + 1?
- Zustimmung ≥ 50 % (Ziel 75 %)? Wenn gefallen: über Zustimmung hovern, fehlende Bedarfe beheben.
- Vorräte Nahrung/Brennstoff (Monate) – Trend gegenüber Vormonat?
- Problem-Banner abarbeiten (Storage Full → Lager/Limit; No Ox Guide → Familie freigeben; Homeless → Hofstätten).
- Bretter/Bauholz/Werkzeug-Surplus > 0, Ochsen frei und mit Platz, alle Marktstände besetzt.
- Hofstätten mit „Upgrade verfügbar“ upgraden. Alle 1–3 Monate speichern.

## Jahreszeiten
- Frühling (Mär–Mai): Felder pflügen, Hafer/Gerste/Flachs säen, Hofstätten bauen, Ochsen nachkaufen.
- Sommer (Jun–Aug): Großprojekte (Kirche, Herrenhaus), Brennholz-Vorrat, Schafschur.
- Herbst (Sep–Nov): Ernte zuerst (mehr Familien ins Bauernhaus), Weizen/Roggen säen, Wintervorräte prüfen (6 Monate Nahrung, Brennholz, Tierfutter).
- Winter (Dez–Feb): Familien auf Holz, Bau, Verarbeitung umsetzen; keine weit entfernten Baustellen.

## Anfängerfehler – und woran du sie im Bild erkennst
| Fehler | Zeichen |
|---|---|
| Keine freie Familie | Unbeschäftigt = 0, Baustellen ohne Arbeiter, Banner „No Ox Guide“ |
| Lager voll | Banner „Storage Full“, Warenhaufen im Freien |
| Zu wenig Nahrung | Vorräte < 6 Monate im Oktober, Hunger-Popup, Totenkopf im Log |
| Brennstoff fehlt | Kälte-Warnung, Brennstoff-Monate niedrig |
| Obdachlose | Zelte, Banner „Homeless“, Wohnraum < Familien |
| Zustimmung < 50 % | Zahl rot/gelb, kein Zuzug am Monatsersten |
| Stände unbesetzt | Marktstände leer, Bedarf rot trotz vollem Lager |
| Kinomodus an | keine Oberfläche sichtbar |

## Eine wunderschöne mittelalterliche Stadt
- **Herz der Stadt:** Kirche und Marktplatz bilden zusammen das Zentrum; der Marktplatz liegt als offener Platz an der Hauptstraße, die Kirche markant daneben (später Steinkirche).
- **Straßen folgen dem Gelände:** geschwungene, organische Straßen entlang der Höhenlinien und des Flusses statt Schachbrett; eine Hauptstraße vom Königsweg zum Markt, davon abzweigende Gassen. Kreuzungen als kleine Plätze.
- **Hofstätten in Reihen und Clustern:** schmale, tiefe Grundstücke dicht an dicht entlang der Straßen, Fronten zur Straße, Hinterhöfe nach hinten (Gärten, Hühner) – das typische mittelalterliche Straßendorf. Lieber mehrere Cluster um kleine Plätze als verstreute Einzelhäuser.
- **Ringe nach außen:** innen Wohnen, Markt, Kirche, Brunnen; dann Handwerk und Lager nah an der Hauptstraße; außen Felder, Weiden, Holzfäller, Jäger. Felder als Flickenteppich unregelmäßiger Formen außerhalb der Häuser.
- **Versorgung im Blick:** Brunnen und Marktstände so verteilen, dass alle Hofstätten abgedeckt sind (Versorgungs-Overlay prüfen).
- **Natur stehen lassen:** Waldränder, Flussufer und Hügel als Kulisse erhalten; nicht alles roden.
- Erst funktionieren, dann schön: Wachstum und Versorgung haben Vorrang, aber plane die Form von Anfang an (Platz für Markt und Kirche freihalten).

## Sicherheitsregeln für dich
- Bauwerkzeuge nur im pausierten Spiel bedienen; vor dem Weiterlaufen alle Werkzeuge mit Esc schließen.
- Kein „Visit Mode“ (3rd-Person), kein Abriss ohne Prüfung, keinen Spielstand ohne neuen Namen überschreiben.
- Unklarer Zustand: Esc (bis nichts offen ist), T (zur Stadt), neues Bild.
