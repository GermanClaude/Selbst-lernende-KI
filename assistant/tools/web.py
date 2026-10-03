"""Internet-Werkzeuge: Websuche und Seiteninhalt abrufen.

Diese Werkzeuge laufen clientseitig (ueber 'requests'), damit die KI auch dann
Internetzugang hat, wenn serverseitige Tools nicht verfuegbar sind. Lesen gilt
als SAFE; es werden keine Daten aktiv irgendwohin gesendet.
"""
from __future__ import annotations

from ..permissions import Risk
from .base import Tool, ToolContext

_HEADERS = {"User-Agent": "Selbst-lernende-KI/0.1 (lokaler Assistent)"}
_MAX_CHARS = 8000


class WebSearchTool(Tool):
    name = "web_suche"
    description = (
        "Durchsucht das Internet nach einem Stichwort und gibt die besten Treffer "
        "(Titel, Kurztext, Link) zurueck. Nutze dies fuer aktuelle Informationen."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "anfrage": {"type": "string", "description": "Suchbegriff / Frage"},
            "anzahl": {"type": "integer", "description": "Anzahl Treffer (Standard 5)"},
        },
        "required": ["anfrage"],
    }

    def run(self, ctx: ToolContext, anfrage: str, anzahl: int = 5) -> str:
        ctx.permissions.require(Risk.SAFE, f"Websuche: {anfrage}")
        try:
            import requests  # lokal importieren, damit das Modul optional bleibt
        except ImportError:
            return "Das Paket 'requests' fehlt. Installiere es mit: pip install requests"

        anzahl = max(1, min(10, int(anzahl)))
        # DuckDuckGo "lite" HTML - keine API-Schluessel noetig.
        try:
            resp = requests.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": anfrage},
                headers=_HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return f"Suche fehlgeschlagen: {exc}"

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return "Das Paket 'beautifulsoup4' fehlt. Installiere es mit: pip install beautifulsoup4"

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a.result-link")
        snippets = soup.select("td.result-snippet")
        results: list[str] = []
        for i, link in enumerate(links[:anzahl]):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            snippet = snippets[i].get_text(strip=True) if i < len(snippets) else ""
            results.append(f"{i + 1}. {title}\n   {snippet}\n   {href}")
        if not results:
            return f"Keine Treffer fuer '{anfrage}'."
        return f"Suchergebnisse fuer '{anfrage}':\n\n" + "\n\n".join(results)


class WebFetchTool(Tool):
    name = "web_abrufen"
    description = "Ruft eine Webseite ab und gibt ihren lesbaren Textinhalt zurueck."
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Vollstaendige URL (https://...)"}},
        "required": ["url"],
    }

    def run(self, ctx: ToolContext, url: str) -> str:
        ctx.permissions.require(Risk.SAFE, f"Seite abrufen: {url}")
        if not url.startswith(("http://", "https://")):
            return "Bitte eine vollstaendige URL mit http(s):// angeben."
        try:
            import requests
        except ImportError:
            return "Das Paket 'requests' fehlt. Installiere es mit: pip install requests"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=25)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return f"Abruf fehlgeschlagen: {exc}"

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return "Das Paket 'beautifulsoup4' fehlt. Installiere es mit: pip install beautifulsoup4"

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        title = soup.title.get_text(strip=True) if soup.title else url
        suffix = "\n…(gekuerzt)" if len(text) > _MAX_CHARS else ""
        return f"{title}\n\n{text[:_MAX_CHARS]}{suffix}"


def register(registry) -> None:
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
