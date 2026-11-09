"""Netz-Hilfen fuer die Handy-Kamera: PC-Netze, Netz-Vergleich mit dem Handy, mDNS-Namen aufloesen.

Alles nur zur Fehlersuche bzw. als Ersatzweg - an der Regel "nur LAN" aendert sich nichts.
"""
from __future__ import annotations

import ipaddress
import logging
import socket

log = logging.getLogger(__name__)


def pc_netze() -> list:
    """IPv4-Netze aller Netzwerkkarten des PCs (z.B. WLAN 192.168.178.0/24 UND LAN-Kabel).

    Nur private Netze; Loopback faellt weg. Fehlt ``ifaddr`` (kommt mit aiortc), ist die Liste leer."""
    try:
        import ifaddr  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    netze = []
    try:
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if not isinstance(ip.ip, str):
                    continue  # IPv6 - fuer den Vergleich reicht IPv4
                try:
                    netz = ipaddress.ip_interface(f"{ip.ip}/{int(ip.network_prefix)}").network
                except ValueError:
                    continue
                if netz.is_private and not netz.is_loopback and netz not in netze:
                    netze.append(netz)
    except Exception:  # noqa: BLE001 - Netzwerkkarten nicht lesbar
        log.debug("Netzwerkkarten nicht lesbar", exc_info=True)
    return netze


def im_selben_netz(handy_ips, netze) -> bool | None:
    """True: eine IPv4-Adresse des Handys liegt in einem Netz des PCs. False: das Handy hat private
    IPv4-Adressen, aber keine passt (anderes WLAN, Gaeste-WLAN, Repeater mit eigenem Netz).
    None: nicht entscheidbar (keine IPv4 vom Handy bekannt oder Netze des PCs unbekannt)."""
    adressen = []
    for text in handy_ips or ():
        try:
            ip = ipaddress.ip_address(str(text).split("%", 1)[0])
        except ValueError:
            continue
        if ip.version == 4 and ip.is_private and not ip.is_link_local:
            adressen.append(ip)
    netze = [n for n in (netze or ()) if getattr(n, "version", 0) == 4]
    if not adressen or not netze:
        return None
    return any(ip in netz for ip in adressen for netz in netze)


def netz_text(netze) -> str:
    """Kurzform fuer Anzeige/Protokoll, z.B. "192.168.178.x"."""
    teile = []
    for netz in netze or ():
        if getattr(netz, "version", 0) != 4:
            continue
        if netz.prefixlen >= 24:
            text = ".".join(str(netz.network_address).split(".")[:3]) + ".x"
        else:
            text = str(netz)
        if text not in teile:
            teile.append(text)
    return ", ".join(teile)


def ip_text(ips) -> str:
    """Handy-Adressen fuer die Anzeige als Netz (192.168.179.x) - private Adressen, kein Geheimnis."""
    teile = []
    for text in ips or ():
        try:
            ip = ipaddress.ip_address(str(text))
        except ValueError:
            continue
        if ip.version == 4:
            kurz = ".".join(str(ip).split(".")[:3]) + ".x"
            if kurz not in teile:
                teile.append(kurz)
    return ", ".join(teile)


def mdns_aufloesen(name: str) -> str | None:
    """Loest einen mDNS-Namen (xxxx.local) ueber das Betriebssystem auf.

    Ersatzweg zu aiortc: unter Windows 10/11 beantwortet der DNS-Client des Systems .local-Namen
    selbst (eigene Firewall-Regel), waehrend aiortc dafuer Port 5353 braucht - den blockiert die
    Firewall oft. Blockiert hoechstens so lange wie das System; der Aufrufer begrenzt die Zeit."""
    from .signal import ist_mdns_name  # noqa: PLC0415

    if not ist_mdns_name(name):
        return None
    try:
        ergebnis = socket.getaddrinfo(name, None, socket.AF_INET, socket.SOCK_DGRAM)
    except (OSError, UnicodeError):
        return None
    for eintrag in ergebnis:
        adresse = eintrag[4][0]
        if isinstance(adresse, str) and adresse:
            return adresse
    return None
