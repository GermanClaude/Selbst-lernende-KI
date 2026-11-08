"""Internet-Werkzeuge: Websuche und Seiteninhalt abrufen.

Diese Werkzeuge laufen clientseitig (ueber 'requests'), damit die KI auch dann
Internetzugang hat, wenn serverseitige Tools nicht verfuegbar sind. Lesen gilt
als SAFE. Achtung: Auch ein Seitenabruf schickt etwas nach aussen (die Adresse) -
deshalb darf die KI im AFK-Modus (niemand schaut zu) nur Links aus ihrer Websuche
abrufen, keine selbst gebauten Adressen.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

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
            if getattr(ctx.permissions, "away", False) and href:
                ctx.permissions.away_urls.add(_plain_url(href.strip()))
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
        away = getattr(ctx.permissions, "away", False)
        if away:
            # Niemand schaut zu: keine Daten in Adressen "verschicken" (eingeschleuste Anweisungen)
            problem = _away_url_problem(url, getattr(ctx.permissions, "away_urls", set()))
            if problem:
                return problem
            url = _plain_url(url)  # genau den gespeicherten Treffer abrufen
        try:
            import requests
        except ImportError:
            return "Das Paket 'requests' fehlt. Installiere es mit: pip install requests"
        try:
            if away:
                resp = _get_checked(requests, url)
                if isinstance(resp, str):
                    return resp
            else:
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


def _plain_url(url: str) -> str:
    return url.split("#", 1)[0]


def _host_problem(url: str) -> str | None:
    """https, keine Benutzerangaben, kein eigenes Netz - auch nicht ueber den Namen (DNS)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or "@" in parts.netloc or not host:
        return "Solange dein Mensch weg ist, rufe ich nur normale https-Adressen ab."
    try:
        ipaddress.ip_address(host)
        return "Solange dein Mensch weg ist, rufe ich keine IP-Adressen ab."
    except ValueError:
        pass
    if host == "localhost" or host.endswith((".local", ".lan", ".internal", ".localhost")):
        return "Solange dein Mensch weg ist, rufe ich nichts im eigenen Netz ab."
    import socket

    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return None  # nicht aufloesbar -> der Abruf scheitert ohnehin
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            return "Solange dein Mensch weg ist, rufe ich nichts im eigenen Netz ab."
    return None


def _away_url_problem(url: str, allowed: set) -> str | None:
    """Im AFK-Modus: nur https-Links, die die Websuche in dieser Abwesenheit geliefert hat -
    exakt so (keine angehaengten Leer-/Steuerzeichen, die beim Abruf mitgeschickt wuerden)."""
    if url != url.strip() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return "Solange dein Mensch weg ist, rufe ich nur Adressen ohne Leer- oder Steuerzeichen ab."
    if _plain_url(url) not in allowed:
        return ("Solange dein Mensch weg ist, rufe ich nur Seiten ab, die ich vorher ueber die Websuche "
                "gefunden habe (keine selbst gebauten Adressen). Such zuerst mit web_suche.")
    return _host_problem(url)


def _get_checked(requests, url: str, hops: int = 5):
    """Abruf im AFK-Modus: Weiterleitungen selbst verfolgen und jedes Ziel pruefen
    (eine Seite darf nicht ins eigene Netz oder auf http umleiten)."""
    from urllib.parse import urljoin

    for _ in range(hops + 1):
        resp = requests.get(url, headers=_HEADERS, timeout=25, allow_redirects=False)
        location = resp.headers.get("Location") if getattr(resp, "headers", None) else None
        if not (300 <= int(getattr(resp, "status_code", 200) or 200) < 400 and location):
            return resp
        url = urljoin(url, location)
        problem = _host_problem(url)
        if problem:
            return "Die Seite leitet weiter auf eine Adresse, die ich jetzt nicht abrufe. " + problem
    return "Zu viele Weiterleitungen - abgebrochen."
