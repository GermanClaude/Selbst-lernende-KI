"""Bewertungen ins Repo schreiben (laeuft als GitHub-Action, siehe .github/workflows/bewertungen.yml).

Holt Durchschnitt und oeffentliche Rezensionen vom Feedback-Postfach (Apps-Skript,
<URL aus feedback-endpoint.txt>?aktion=bewertungen) und schreibt sie
  * nach docs/bewertungen.json (fuer andere Seiten/Werkzeuge) und
  * in die README zwischen <!-- BEWERTUNGEN:START --> und <!-- BEWERTUNGEN:ENDE -->.
Ohne Postfach oder bei einem Fehler aendert sich nichts (die Action endet ohne Commit).

Aufruf: python packaging/bewertungen.py [--pruefen]   (--pruefen: nur anzeigen, nichts schreiben)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from assistant.feedback import _url_aus_fern_text, bewertungen_saeubern  # noqa: E402

START = "<!-- BEWERTUNGEN:START -->"
ENDE = "<!-- BEWERTUNGEN:ENDE -->"
ZEIGEN = 5  # so viele Rezensionen in der README


def sterne(n: float) -> str:
    voll = int(min(5, max(0, round(float(n or 0)))))
    return "★" * voll + "☆" * (5 - voll)


def _md(text: str) -> str:
    """Text fuer Markdown entschaerfen: keine Links, kein HTML, keine Formatierung, eine Zeile."""
    text = " ".join(str(text or "").split())
    text = re.sub(r"[<>]", "", text)
    return re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", text)


def abschnitt(daten: dict | None) -> str:
    """Der README-Abschnitt zwischen den Markierungen (ohne die Markierungen)."""
    if not daten or not daten.get("anzahl"):
        return ("**Noch keine Bewertungen** – sei die erste Person! In Nova: **„Feedback & Bewertung“** "
                "in der Seitenleiste (oder `/feedback`).")
    anzahl = daten["anzahl"]
    schnitt = str(daten["schnitt"]).replace(".", ",")
    zeilen = [f"### {sterne(daten['schnitt'])} {schnitt} von 5 · {anzahl} "
              f"{'Bewertung' if anzahl == 1 else 'Bewertungen'}", ""]
    verteilung = daten.get("verteilung") or {}
    hoechst = max([int(verteilung.get(str(i), 0)) for i in range(1, 6)] + [1])
    zeilen += ["| Sterne | Anteil | Anzahl |", "|---|---|---:|"]
    for i in range(5, 0, -1):
        n = int(verteilung.get(str(i), 0))
        balken = "█" * round(10 * n / hoechst) if n else ""
        zeilen.append(f"| {'★' * i} | {balken} | {n} |")
    rezensionen = (daten.get("oeffentlich") or [])[:ZEIGEN]
    if rezensionen:
        zeilen += ["", "**Neueste Rezensionen:**", ""]
        for r in rezensionen:
            datum = ".".join(reversed(r["datum"].split("-"))) if r.get("datum") else ""
            kopf = f"{sterne(r['sterne'])} **{_md(r['name'])}**" + (f" · {datum}" if datum else "")
            zeilen.append(f"> {kopf}  \n> {_md(r['text'])}\n")
    zeilen += ["", "*Pro Installation zählt nur die letzte Bewertung. Text und Name erscheinen nur, wenn die "
               "Person es ausdrücklich erlaubt. Bewerten: in Nova unter „Feedback & Bewertung“ (oder `/feedback`).*"]
    return "\n".join(zeilen).strip()


def readme_einsetzen(readme: str, inhalt: str) -> str:
    if START not in readme or ENDE not in readme:
        raise ValueError("README hat keine Bewertungs-Markierungen")
    vorne, rest = readme.split(START, 1)
    _alt, hinten = rest.split(ENDE, 1)
    return f"{vorne}{START}\n{inhalt}\n{ENDE}{hinten}"


def holen(url: str) -> dict | None:
    import requests

    resp = requests.get(url + "?aktion=bewertungen", timeout=30,
                        headers={"User-Agent": "Nova-Repo (Bewertungen)", "Accept": "application/json"})
    resp.raise_for_status()
    return bewertungen_saeubern(resp.json())


def main(argv: list[str]) -> int:
    nur_pruefen = "--pruefen" in argv
    endpunkt = WURZEL / "feedback-endpoint.txt"
    url = _url_aus_fern_text(endpunkt.read_bytes()) if endpunkt.is_file() else None
    if not url:
        print("Kein Feedback-Postfach eingetragen (feedback-endpoint.txt) - nichts zu tun.")
        return 0
    try:
        daten = holen(url)
    except Exception as exc:  # noqa: BLE001
        print(f"Bewertungen nicht abrufbar ({type(exc).__name__}) - nichts geaendert.")
        return 0
    if daten is None:
        print("Antwort des Postfachs ungueltig - nichts geaendert.")
        return 0
    inhalt = abschnitt(daten)
    if nur_pruefen:
        print(inhalt)
        return 0
    readme = WURZEL / "README.md"
    readme.write_text(readme_einsetzen(readme.read_text(encoding="utf-8"), inhalt), encoding="utf-8")
    ziel = WURZEL / "docs" / "bewertungen.json"
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Bewertungen aktualisiert: {daten['schnitt']} von 5 ({daten['anzahl']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
