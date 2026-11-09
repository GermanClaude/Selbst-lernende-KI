"""HandyKamera: Nova empfaengt das Kamerabild eines Handys per WebRTC (aiortc), nur im LAN.

Das Handy ist der Anbieter (Offerer): es schickt ein SDP-Angebot mit Videospur + DataChannel
("steuerung") verschluesselt uebers Relais. Nova antwortet (Answerer) und nimmt das Video an.

    kamera = HandyKamera()              # Standard: NtfyRelay (ntfy.sh)
    info = kamera.start()               # -> KopplungsInfo(link, code, ablauf, ...)
    zeige_qr(info.link)                 # siehe qr.py
    ...
    kamera.zustand                      # "wartet" | "verbunden" | "getrennt" | "fehler"
    bild = kamera.latest_frame()        # PIL.Image (verkleinert) oder None
    jpeg = kamera.latest_frame(als="jpeg", max_kante=1024)
    kamera.stop()

Eigenheiten:
  * aiortc laeuft in einem eigenen asyncio-Thread (Daemon). Alle oeffentlichen Methoden sind
    thread-sicher und blockieren hoechstens kurz.
  * Das Video wird laufend dekodiert (sonst staut sich aiortc's Warteschlange), aber nur das
    letzte Bild bleibt als Referenz liegen. Umwandeln/Verkleinern passiert erst bei latest_frame().
    Nichts wird gespeichert oder aufgezeichnet.
  * Keine STUN-/TURN-Server. Kandidaten der Gegenseite (und eigene) ausserhalb des LANs werden
    verworfen (siehe signal.filtere_sdp); nach dem Verbinden wird das gewaehlte Paar nochmals geprueft.
  * Genau ein Handy pro Kopplung (an seiner Geraete-ID erkannt). Gebunden wird erst, wenn eine
    Verbindung wirklich steht - ein gescheiterter Versuch sperrt die Kopplung nicht. Waehrend eine
    Verbindung laeuft, wird JEDES neue Angebot abgelehnt ("noch-verbunden"; kein Uebernehmen per
    Relais). Erst wenn sie getrennt/gescheitert ist, darf dasselbe Handy innerhalb von
    ``wiederverbinden_s`` neu anbieten.
  * Die Handy-Seite prueft ihrerseits Novas Antwort (nur LAN-Kandidaten) und vor dem ersten Bild
    das gewaehlte Adresspaar per getStats() - erst dann haengt sie die Kameraspur an.
  * aiortc und av werden erst in start() geladen - fehlen sie, kommt ein deutscher Hinweis.
  * Fehlersuche: Klappt die Verbindung nicht, steht in status()["grund"] ein Kuerzel (siehe GRUENDE)
    und in "fehler"/"tipp" ein Satz fuer Nicht-Techniker. Dafuer zaehlt Nova die Kandidaten des
    Angebots (IP / versteckter mDNS-Name / nicht im LAN), vergleicht die Netze von Handy und PC und
    zaehlt die Pruefpakete, die vom Handy wirklich ankommen (0 = Firewall/WLAN-Isolierung).
  * Versteckt der Browser die Adresse (nur xxxx.local), loest Nova den Namen ueber das System auf
    (netz.mdns_aufloesen) und wartet sonst trotzdem auf die Pruefpakete des Handys - daraus lernt
    ICE die echte Adresse ("a=end-of-candidates" wird dafuer entfernt).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import io
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field

from . import netz
from . import signal as sig

log = logging.getLogger(__name__)

ZUSTAENDE = ("wartet", "verbunden", "getrennt", "fehler")
PAKET_HINWEIS = ("F\u00fcr die Handy-Kamera fehlen noch Pakete. Im Terminal: "
                 "pip install aiortc av cryptography segno")
WLAN_HINWEIS = ("Keine Verbindung zum Handy. Handy und PC m\u00fcssen im selben WLAN sein "
                "(kein G\u00e4ste-WLAN, kein mobiles Netz).")
MAX_SDP = 24_000
MAX_DC_NACHRICHT = 4096
MAX_MDNS_NAMEN = 8

_FIREWALL_TIPP = "hier auf \u201eFirewall freigeben\u201c klicken (Windows fragt einmal nach)"
_ROUTER_TIPP = ("im Router \u201eWLAN-Ger\u00e4te d\u00fcrfen miteinander kommunizieren\u201c einschalten "
                "(keine WLAN-Isolierung, kein G\u00e4ste-WLAN)")
# Kuerzel -> (Grund, Tipp). Texte fuer Nicht-Techniker; {handy}/{pc} = Netze, z.B. 192.168.178.x
GRUENDE = {
    "kein-lan": ("Das Handy hat Nova keine Adresse im Heimnetz (WLAN) geschickt.",
                 "Am Handy das WLAN einschalten und mit demselben WLAN wie der PC verbinden "
                 "(mobile Daten ausschalten)."),
    "anderes-netz": ("Handy ({handy}) und PC ({pc}) sind in verschiedenen Netzen.",
                     "Ist das Handy im G\u00e4ste-WLAN oder an einem Repeater mit eigenem Netz? "
                     "Bitte mit demselben WLAN wie der PC verbinden."),
    "mdns": ("Vom Handy kam am PC nichts an \u2013 und der Browser am Handy versteckt seine Adresse.",
             f"Erst {_FIREWALL_TIPP}. Am Handy den Link in Chrome bzw. Safari \u00f6ffnen "
             "(nicht in der Google-App oder einem QR-Scanner)."),
    "keine-pakete": ("Die Pr\u00fcfpakete des Handys kommen am PC nicht an.",
                     f"Meist blockiert die Windows-Firewall: {_FIREWALL_TIPP}. Hilft das nicht: {_ROUTER_TIPP}."),
    "keine-verbindung": ("Handy und PC haben sich im WLAN nicht gefunden.",
                         f"Erst {_FIREWALL_TIPP}. Hilft das nicht: {_ROUTER_TIPP}."),
    "einseitig": ("Das Handy meldet sich am PC, aber die Verbindung kommt nicht zustande.",
                  f"VPN an Handy und PC ausschalten; {_ROUTER_TIPP}."),
    "abbruch": ("Die Verbindung zum Handy begann, brach dann aber ab.",
                "Am Handy \u201eNeu verbinden\u201c tippen; hilft das nicht, Chrome bzw. Safari nehmen."),
    "nicht-lan": ("Die Verbindung lief nicht \u00fcber dein Heimnetz \u2013 deshalb getrennt.",
                  "Handy und PC ins selbe WLAN (kein VPN, kein mobiles Netz)."),
    "pc-kein-lan": ("Dieser PC hat keine Adresse im Heimnetz (WLAN/LAN).",
                    "Den PC mit dem WLAN oder per Kabel mit dem Router verbinden."),
    "codec": ("Das Handy-Video passt nicht zu Nova (Codec).", "Am Handy einen anderen Browser versuchen."),
}
# Bei diesen Gruenden ist ein Verbindungsversuch gescheitert (die App bietet dann die Firewall-Freigabe an)
VERBINDUNGS_GRUENDE = frozenset(("kein-lan", "anderes-netz", "mdns", "keine-pakete", "keine-verbindung",
                                 "einseitig", "abbruch", "nicht-lan"))


@dataclass
class Versuch:
    """Diagnose eines Verbindungsversuchs - nur Zahlen und Netze, nie SDP/Schluessel."""

    kandidaten: sig.KandidatenZahl = field(default_factory=sig.KandidatenZahl)
    mdns_aufgeloest: int = 0
    handy_ips: list = field(default_factory=list)
    pc_netze: list = field(default_factory=list)
    netz_passt: bool | None = None
    eingehend: int | None = None     # Pruefpakete vom Handy (None = nicht messbar)
    erfolgreich: int | None = None   # Adresspaare, auf die das Handy geantwortet hat
    nominiert: bool = False          # ICE fertig (danach scheiterte es also an DTLS o.ae.)

    def als_dict(self) -> dict:
        return {"kandidaten": self.kandidaten.als_dict(), "mdns_aufgeloest": self.mdns_aufgeloest,
                "netz_passt": self.netz_passt, "handy_netz": netz.ip_text(self.handy_ips),
                "pc_netz": netz.netz_text(self.pc_netze), "eingehend": self.eingehend,
                "erfolgreich": self.erfolgreich, "nominiert": self.nominiert}


def ermittle_grund(versuch: Versuch | None) -> str:
    """Warum kam keine Verbindung zustande? -> Kuerzel aus GRUENDE (Reihenfolge = Wahrscheinlichkeit)."""
    if versuch is None:
        return "keine-verbindung"
    if versuch.netz_passt is False:
        return "anderes-netz"
    if versuch.nominiert:
        return "abbruch"
    if versuch.eingehend:
        return "einseitig"
    k = versuch.kandidaten
    if k.mdns and not k.ip_lan and not versuch.mdns_aufgeloest:
        return "mdns"
    return "keine-pakete" if versuch.eingehend == 0 else "keine-verbindung"


def grund_texte(grund: str, versuch: Versuch | None = None) -> tuple[str, str]:
    """-> (Grund-Satz, Tipp) fuer die Anzeige."""
    text, tipp = GRUENDE.get(grund, (WLAN_HINWEIS, ""))
    if versuch is not None and "{" in text:
        text = text.format(handy=netz.ip_text(versuch.handy_ips) or "?", pc=netz.netz_text(versuch.pc_netze) or "?")
    return text, tipp


class HandyKameraFehler(RuntimeError):
    """Handy-Kamera laesst sich nicht starten (Text fuer den Nutzer)."""


def lade_webrtc():
    """Importiert aiortc + av erst jetzt. -> aiortc-Modul. Wirft HandyKameraFehler mit Hinweis."""
    try:
        import aiortc  # noqa: PLC0415
        import av  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001
        raise HandyKameraFehler(f"{PAKET_HINWEIS} ({type(exc).__name__}).") from exc
    return aiortc


@dataclass(frozen=True)
class KopplungsInfo:
    """Was die Oberflaeche anzeigt: Link fuer den QR-Code, optional Kurzcode, Ablaufzeit."""

    link: str
    ablauf: int                 # Unix-Sekunden
    code: str | None = None     # z.B. "7KQ2-M9XD" (Eingabe in der installierten Handy-App)

    def __repr__(self) -> str:  # Link/Code enthalten das Geheimnis
        return f"KopplungsInfo(ablauf={self.ablauf}, code={'ja' if self.code else 'nein'})"

    def als_dict(self) -> dict:
        return {"link": self.link, "ablauf": self.ablauf, "code": self.code}


class HandyKamera:
    """Eine Handy-Kamera-Kopplung samt WebRTC-Verbindung (siehe Moduldoku)."""

    def __init__(self, relay: sig.Relay | None = None, *, basis_url: str = sig.STANDARD_BASIS_URL,
                 gueltig: float = sig.GUELTIG_S, mit_code: bool = True, verbinden_timeout: float = 30.0,
                 wiederverbinden_s: float = 600.0, warte_intervall: float = 20.0,
                 lan_pruefung=sig.ist_lan_adresse, uhr=time.time, mdns_aufloeser=netz.mdns_aufloesen,
                 mdns_timeout: float = 2.5, pc_netze=netz.pc_netze, aiortc_mdns: bool | None = None):
        self._relay_vorgabe = relay
        self.basis_url = basis_url
        self.gueltig = gueltig
        self.mit_code = mit_code
        self.verbinden_timeout = verbinden_timeout
        self.wiederverbinden_s = wiederverbinden_s
        self.warte_intervall = warte_intervall
        self._lan = lan_pruefung
        self._uhr = uhr
        self._mdns = mdns_aufloeser
        self.mdns_timeout = mdns_timeout
        # Unter Windows loest das System .local-Namen selbst auf (siehe netz.mdns_aufloesen); was es nicht
        # schafft, schafft aiortc erst recht nicht (braucht Port 5353, den die Firewall sperrt) -> weglassen.
        self.aiortc_mdns = (os.name != "nt") if aiortc_mdns is None else bool(aiortc_mdns)
        self._pc_netze = pc_netze
        self._sperre = threading.RLock()
        self._zustand = "getrennt"
        self._schritt = "aus"
        self._fehler: str | None = None
        self._grund: str | None = None
        self._tipp: str | None = None
        self._versuch: Versuch | None = None
        self._info: KopplungsInfo | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._haupt: asyncio.Task | None = None
        self._relay: sig.Relay | None = None
        self._eigenes_relay = False
        self._kopplung: sig.Kopplung | None = None
        self._kanal: sig.Kanal | None = None
        self._pc = None
        self._dc = None
        self._geraet: str | None = None          # erst gebunden, wenn eine Verbindung steht
        self._versuch_geraet: str | None = None  # Handy des laufenden Verbindungsversuchs
        self._frist = 0.0
        self._war_verbunden = False
        self._verbunden_seit: float | None = None
        self._frame = None
        self._frame_zeit = 0.0
        self._frame_nr = 0
        self._cache: tuple | None = None
        self._kamera_seite: str | None = None
        self._handy_sichtbar: bool | None = None
        self.bilder = 0
        self.verworfene_kandidaten = 0

    # -- oeffentlich ----------------------------------------------------------------------
    @property
    def zustand(self) -> str:
        return self._zustand

    @property
    def fehler(self) -> str | None:
        return self._fehler

    @property
    def info(self) -> KopplungsInfo | None:
        return self._info

    @property
    def bild_nr(self) -> int:
        """Zaehlt jedes neue Bild hoch (zum Erkennen, ob seit dem letzten Abholen eins kam)."""
        return self._frame_nr

    def laeuft(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> KopplungsInfo:
        """Neue Kopplung erzeugen und im Hintergrund auf das Handy warten. Alte wird beendet."""
        lade_webrtc()
        self.stop()
        kopplung = sig.Kopplung.neu(self.gueltig, self._uhr)
        code = sig.neuer_code() if self.mit_code else None
        with self._sperre:
            self._kopplung = kopplung
            self._kanal = sig.Kanal(kopplung, "n", self._uhr)
            if self._relay_vorgabe is not None:
                self._relay, self._eigenes_relay = self._relay_vorgabe, False
            else:
                self._relay, self._eigenes_relay = sig.NtfyRelay(), True
            self._info = KopplungsInfo(kopplung.link(self.basis_url), kopplung.ablauf,
                                       sig.code_anzeige(code) if code else None)
            self._zustand, self._schritt, self._fehler = "wartet", "wartet_auf_handy", None
            self._grund = self._tipp = self._versuch = None
            self._geraet, self._war_verbunden, self._verbunden_seit = None, False, None
            self._versuch_geraet = None
            self._frist = float(kopplung.ablauf)
            self._frame, self._cache, self.bilder, self.verworfene_kandidaten = None, None, 0, 0
            bereit = threading.Event()
            self._thread = threading.Thread(target=self._thread_haupt, args=(code, bereit),
                                            name="handy-kamera", daemon=True)
            self._thread.start()
        bereit.wait(5)
        return self._info

    def stop(self, grund: str = "") -> None:
        """Verbindung beenden (Handy bekommt 'stopp'), Thread aufraeumen. Mehrfach aufrufbar."""
        thread, loop = self._thread, self._loop
        if thread is None:
            return
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._beenden(), loop).result(timeout=6)
            except (Exception, concurrent.futures.CancelledError):  # noqa: BLE001 - Loop schon zu o.ae.
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass
        thread.join(timeout=6)
        with self._sperre:
            if self._eigenes_relay and self._relay is not None:
                self._relay.schliessen()
            self._thread = self._loop = self._haupt = None
            self._pc = self._dc = None
            self._frame, self._cache = None, None
            self._zustand, self._schritt, self._fehler = "getrennt", "aus", (grund or None)
            self._grund = self._tipp = None
        log.info("Handy-Kamera beendet")

    def latest_frame(self, max_kante: int | None = 1280, als: str = "pil", qualitaet: int = 80,
                     max_alter: float | None = 5.0):
        """Letztes Bild: PIL.Image (RGB) oder JPEG-Bytes (``als="jpeg"``), verkleinert auf
        ``max_kante`` (laengste Seite). None, wenn keins da oder aelter als ``max_alter`` Sekunden."""
        with self._sperre:
            frame, zeit, nr = self._frame, self._frame_zeit, self._frame_nr
        if frame is None or (max_alter is not None and time.monotonic() - zeit > max_alter):
            return None
        schluessel = (nr, max_kante, als, qualitaet)
        cache = self._cache
        if cache is not None and cache[0] == schluessel:
            return cache[1]
        breite, hoehe = int(frame.width), int(frame.height)
        faktor = min(1.0, max_kante / max(breite, hoehe)) if max_kante else 1.0
        neu_b, neu_h = max(2, int(breite * faktor) // 2 * 2), max(2, int(hoehe * faktor) // 2 * 2)
        try:
            bild = frame.reformat(width=neu_b, height=neu_h, format="rgb24").to_image()
        except Exception:  # noqa: BLE001 - kaputtes Bild
            log.debug("Handy-Bild l\u00e4sst sich nicht umwandeln", exc_info=True)
            return None
        ergebnis = bild
        if als == "jpeg":
            puffer = io.BytesIO()
            bild.save(puffer, "JPEG", quality=int(qualitaet))
            ergebnis = puffer.getvalue()
        self._cache = (schluessel, ergebnis)
        return ergebnis

    def status(self) -> dict:
        """Fuer Oberflaeche/Gehirn (ohne Geheimnisse)."""
        with self._sperre:
            frame = self._frame
            alter = round(time.monotonic() - self._frame_zeit, 1) if frame is not None else None
            return {
                "zustand": self._zustand,
                "schritt": self._schritt,
                "fehler": self._fehler,
                "ablauf": self._info.ablauf if self._info else None,
                "verbunden_seit": self._verbunden_seit,
                "bilder": self.bilder,
                "bild_alter": alter,
                "aufloesung": [int(frame.width), int(frame.height)] if frame is not None else None,
                "kamera": self._kamera_seite,
                "handy_sichtbar": self._handy_sichtbar,
                "relay": getattr(self._relay, "name", None),
                "grund": self._grund,
                "tipp": self._tipp,
                "verbindung_gescheitert": self._grund in VERBINDUNGS_GRUENDE,
                "diagnose": self._versuch.als_dict() if self._versuch is not None else None,
            }

    def warte_auf(self, zustaende, timeout: float = 10.0) -> bool:
        """Blockiert, bis einer der Zustaende erreicht ist (Tests/CLI)."""
        if isinstance(zustaende, str):
            zustaende = (zustaende,)
        ende = time.monotonic() + timeout
        while time.monotonic() < ende:
            if self._zustand in zustaende:
                return True
            time.sleep(0.05)
        return self._zustand in zustaende

    # -- Thread / Loop --------------------------------------------------------------------
    def _thread_haupt(self, code: str | None, bereit: threading.Event) -> None:
        # Bewusst SelectorEventLoop (auch unter Windows): Im ProactorEventLoop von Python 3.12 hoert ein
        # UDP-Socket nach einem einzigen ICMP "Port unerreichbar" (WSAECONNRESET) fuer immer auf zu
        # empfangen - dann kommen die Pruefpakete des Handys nie mehr an (erst in neueren Pythons behoben).
        loop = asyncio.SelectorEventLoop()
        self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            self._haupt = loop.create_task(self._ablauf(code))
            loop.call_soon(bereit.set)
            loop.run_forever()  # endet mit _beenden() -> loop.stop()
        finally:
            try:
                rest = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for aufgabe in rest:
                    aufgabe.cancel()
                if rest:
                    loop.run_until_complete(asyncio.gather(*rest, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except BaseException:  # noqa: BLE001 - Aufraeumen darf nie haengen bleiben
                pass
            loop.close()
            bereit.set()

    async def _im_thread(self, funktion, *args):
        """Blockierende Funktion (Relais) in einem Daemon-Thread - haelt das Beenden nicht auf."""
        loop = asyncio.get_running_loop()
        zukunft = loop.create_future()

        def fertig(ergebnis, fehler):
            if not zukunft.done():
                if fehler is not None:
                    zukunft.set_exception(fehler)
                else:
                    zukunft.set_result(ergebnis)

        def lauf():
            try:
                ergebnis, fehler = funktion(*args), None
            except Exception as exc:  # noqa: BLE001
                ergebnis, fehler = None, exc
            try:
                loop.call_soon_threadsafe(fertig, ergebnis, fehler)
            except RuntimeError:  # Loop schon geschlossen
                pass

        threading.Thread(target=lauf, name="handy-kamera-relay", daemon=True).start()
        return await zukunft

    async def _ablauf(self, code: str | None) -> None:
        try:
            if code:
                thema, text = sig.code_nachricht(self._kopplung, code, self._uhr)
                await self._im_thread(self._relay.senden, thema, text)
            await self._lauschen()
        except asyncio.CancelledError:
            raise
        except sig.RelayFehler as exc:
            self._setze_fehler(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.error("Handy-Kamera: unerwarteter Fehler (%s)", type(exc).__name__)
            self._setze_fehler("Die Handy-Kamera ist auf einen Fehler gesto\u00dfen. Bitte neu koppeln.")
        finally:
            await self._schliesse_pc()

    async def _lauschen(self) -> None:
        # Das Thema ist neu und zufaellig -> "alles" ist sicher und unabhaengig von der PC-Uhr.
        seit: str | None = None
        gesehen: set[str] = set()
        fehlversuche = 0
        while True:
            if self._zustand != "verbunden" and self._uhr() > self._frist:
                if self._war_verbunden:
                    with self._sperre:
                        if self._zustand != "fehler":
                            self._zustand = "getrennt"
                        self._schritt = "beendet"
                else:
                    self._setze_fehler("Der QR-Code ist abgelaufen. Bitte in Nova einen neuen anzeigen lassen.")
                return
            try:
                eingang = await self._im_thread(self._relay.empfangen, self._kanal.thema, seit,
                                                self.warte_intervall)
                fehlversuche = 0
            except sig.RelayFehler as exc:
                fehlversuche += 1
                if fehlversuche >= 4 and self._zustand != "verbunden":
                    raise
                log.info("Relais: %s", exc)
                await asyncio.sleep(min(30.0, 2.0 * fehlversuche))
                continue
            for eintrag in eingang:
                if eintrag.id:
                    if eintrag.id in gesehen:
                        continue
                    gesehen.add(eintrag.id)
                    seit = eintrag.id
                try:
                    nachricht = self._kanal.oeffne(eintrag.text)
                except sig.SignalFehler as exc:
                    log.debug("Signal-Nachricht verworfen: %s", exc)
                    continue
                if nachricht is not None:
                    try:
                        await self._behandle(nachricht)
                    except sig.RelayFehler as exc:  # Antwort kam nicht raus - Handy darf neu anfragen
                        self._setze_fehler(str(exc))
                        await self._schliesse_pc()

    async def _sende(self, typ: str, daten: dict | None = None) -> None:
        text = self._kanal.verpacke(typ, daten)
        await self._im_thread(self._relay.senden, self._kanal.thema, text)

    async def _behandle(self, nachricht: sig.Nachricht) -> None:
        daten = nachricht.daten
        geraet = str(daten.get("g") or "")[:64]
        if nachricht.typ == "angebot":
            sdp = daten.get("sdp")
            if not isinstance(sdp, str) or not sdp or len(sdp) > MAX_SDP or not geraet:
                return
            if self._zustand == "verbunden":
                # Laufende Verbindung nie per Relais uebernehmen lassen (auch nicht vom selben Geraet):
                # erst wenn sie getrennt/gescheitert ist, darf ein neues Angebot kommen.
                log.info("Angebot w\u00e4hrend einer laufenden Verbindung abgewiesen")
                await self._sende("fehler", {"grund": "noch-verbunden", "g": geraet})
                return
            gebunden = self._geraet or (self._versuch_geraet if self._pc is not None else None)
            if gebunden and geraet != gebunden:
                log.info("Zweites Handy abgewiesen (eine Kopplung = ein Handy)")
                await self._sende("besetzt", {"g": geraet})
                return
            self._versuch_geraet = geraet
            await self._verbinden(sdp)
        elif (nachricht.typ == "tschuess" and self._zustand != "verbunden"
              and geraet in (self._geraet, self._versuch_geraet)):
            await self._getrennt("Am Handy beendet.")

    async def _verbinden(self, sdp_angebot: str) -> None:
        aiortc = lade_webrtc()
        await self._schliesse_pc()
        angebot, behalten, verworfen = self._filtere(sdp_angebot)
        self.verworfene_kandidaten += verworfen
        versuch = Versuch(kandidaten=sig.kandidaten_zaehlen(sdp_angebot, self._lan))
        self._versuch = versuch
        k = versuch.kandidaten
        if behalten == 0:
            log.info("Angebot vom Handy ohne LAN-Kandidaten (%d nicht im LAN) - abgelehnt", k.nicht_lan)
            await self._sende("fehler", {"grund": "kein-lan", "g": self._versuch_geraet})
            self._setze_grund("kein-lan")
            return
        with self._sperre:  # neuer Versuch: alter Fehler gilt nicht mehr
            self._zustand, self._schritt = "wartet", "verbindet"
            self._fehler = self._grund = self._tipp = None
        aufgeloest = {}
        if k.mdns:
            # Browser versteckt die Adresse: selbst aufloesen (sonst bleibt nur, auf das Handy zu warten)
            aufgeloest = await self._mdns_aufloesen(k.mdns_namen[:MAX_MDNS_NAMEN])
            angebot = sig.mdns_ersetzen(angebot, aufgeloest)
            if not self.aiortc_mdns:
                # Windows: nur aufgeloeste Adressen an aiortc (auch in gemischten Angeboten); die uebrigen
                # Namen fallen weg - die Pruefpakete des Handys kommen dann als peer-reflexive Kandidaten.
                angebot = sig.filtere_sdp(angebot, lambda a: not sig.ist_mdns_name(a) and self._lan(a))[0]
        angebot = sig.ohne_kandidaten_ende(angebot)
        versuch.mdns_aufgeloest = len(aufgeloest)
        versuch.handy_ips = list(k.lan_ips) + [ip for ip in aufgeloest.values() if ip not in k.lan_ips]
        try:
            versuch.pc_netze = list(self._pc_netze() or [])
        except Exception:  # noqa: BLE001 - nur Diagnose
            versuch.pc_netze = []
        versuch.netz_passt = netz.im_selben_netz(versuch.handy_ips, versuch.pc_netze)
        log.info("Angebot vom Handy: %d IP-, %d mDNS-Kandidat(en) (%d aufgel\u00f6st), %d nicht im LAN; "
                 "Handy-Netz %s, PC-Netze %s, gleiches Netz: %s", k.ip_lan, k.mdns, len(aufgeloest), k.nicht_lan,
                 netz.ip_text(versuch.handy_ips) or "?", netz.netz_text(versuch.pc_netze) or "?",
                 {True: "ja", False: "NEIN", None: "unbekannt"}[versuch.netz_passt])
        pc = aiortc.RTCPeerConnection(aiortc.RTCConfiguration(iceServers=[]))
        self._pc = pc

        @pc.on("track")
        def _spur(track):
            if track.kind == "video":
                asyncio.ensure_future(self._lies(track, pc))

        @pc.on("datachannel")
        def _kanal(kanal):
            self._steuerkanal(kanal, pc)

        @pc.on("connectionstatechange")
        async def _zustand():
            await self._verbindungszustand(pc)

        try:
            await pc.setRemoteDescription(aiortc.RTCSessionDescription(angebot, "offer"))
            self._ice_beobachten(pc, versuch)
            await pc.setLocalDescription(await pc.createAnswer())
        except Exception as exc:  # noqa: BLE001 - z.B. kein gemeinsamer Codec
            log.warning("Angebot vom Handy nicht verwendbar (%s)", type(exc).__name__)
            await self._sende("fehler", {"grund": "angebot", "g": self._versuch_geraet})
            self._setze_grund("codec")
            await self._schliesse_pc()
            return
        antwort, behalten, _ = self._filtere(pc.localDescription.sdp)
        if behalten == 0:
            await self._sende("fehler", {"grund": "pc-kein-lan", "g": self._versuch_geraet})
            self._setze_grund("pc-kein-lan")
            await self._schliesse_pc()
            return
        log.info("Antwort an das Handy: %d LAN-Kandidat(en) des PCs", behalten)
        await self._sende("antwort", {"sdp": antwort, "g": self._versuch_geraet})
        asyncio.ensure_future(self._verbinden_aufpassen(pc))

    def _filtere(self, sdp: str) -> tuple[str, int, int]:
        return sig.filtere_sdp(sdp, self._lan)

    async def _mdns_aufloesen(self, namen: list) -> dict:
        """mDNS-Namen parallel ueber das System aufloesen (je hoechstens mdns_timeout). -> {name: ip}"""
        if not namen or self._mdns is None:
            return {}

        async def eins(name):
            try:
                return name, await asyncio.wait_for(self._im_thread(self._mdns, name), self.mdns_timeout)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                return name, None

        ergebnis = {}
        for name, ip in await asyncio.gather(*(eins(n) for n in namen)):
            # nur echte LAN-Adressen (nie ein Name, nie eine oeffentliche Adresse)
            if isinstance(ip, str) and ip and not sig.ist_mdns_name(ip) and self._lan(ip):
                ergebnis[name] = ip
        return ergebnis

    @staticmethod
    def _ice_verbindungen(pc) -> list:
        """Die aioice-Verbindungen der PeerConnection (interne Struktur - best effort)."""
        verbindungen = []
        transporte = [t.receiver.transport for t in pc.getTransceivers()]
        if getattr(pc, "sctp", None) is not None:
            transporte.append(pc.sctp.transport)
        for dtls in transporte:
            try:
                verbindung = dtls.transport._connection
            except AttributeError:
                continue
            if all(verbindung is not v for v in verbindungen):
                verbindungen.append(verbindung)
        return verbindungen

    def _ice_beobachten(self, pc, versuch: Versuch) -> None:
        """Zaehlt die Pruefpakete (STUN-Anfragen), die vom Handy wirklich am PC ankommen."""
        try:
            verbindungen = self._ice_verbindungen(pc)
            for verbindung in verbindungen:
                original = verbindung.request_received

                def zaehlen(message, addr, protocol, _original=original):
                    versuch.eingehend = (versuch.eingehend or 0) + 1
                    return _original(message, addr, protocol)

                verbindung.request_received = zaehlen
            if verbindungen:
                versuch.eingehend = 0
        except Exception:  # noqa: BLE001 - andere aiortc-Version: Diagnose ohne diese Zahl
            log.debug("ICE-Pakete lassen sich nicht z\u00e4hlen", exc_info=True)

    def _ice_stand(self, pc, versuch: Versuch | None) -> None:
        """Vor dem Schliessen festhalten: wie weit kam ICE? (Antworten vom Handy, Paar gewaehlt?)"""
        if versuch is None:
            return
        try:
            erfolgreich = 0
            for verbindung in self._ice_verbindungen(pc):
                erfolgreich += sum(1 for p in verbindung._check_list if getattr(p.state, "name", "") == "SUCCEEDED")
                versuch.nominiert = versuch.nominiert or bool(verbindung._nominated)
            versuch.erfolgreich = erfolgreich
        except Exception:  # noqa: BLE001
            pass

    async def _gescheitert(self, pc, anlass: str) -> None:
        versuch = self._versuch
        self._ice_stand(pc, versuch)
        grund = ermittle_grund(versuch)
        if versuch is not None:
            log.info("Handy-Kamera: keine Verbindung (%s) - Grund: %s (Pakete vom Handy: %s, Antworten: %s, "
                     "ICE fertig: %s)", anlass, grund, versuch.eingehend, versuch.erfolgreich,
                     "ja" if versuch.nominiert else "nein")
        self._setze_grund(grund)
        self._frist = self._uhr() + self.wiederverbinden_s
        await self._schliesse_pc()

    async def _verbinden_aufpassen(self, pc) -> None:
        await asyncio.sleep(self.verbinden_timeout)
        if pc is self._pc and pc.connectionState != "connected":
            await self._gescheitert(pc, f"nach {self.verbinden_timeout:.0f} s")

    async def _verbindungszustand(self, pc) -> None:
        if pc is not self._pc:
            return
        stand = pc.connectionState
        if stand == "connected":
            if not self._paar_im_lan(pc):
                log.warning("Handy-Kamera: gew\u00e4hltes Adresspaar liegt nicht im LAN - getrennt")
                self._setze_grund("nicht-lan")
                await self._schliesse_pc()
                return
            with self._sperre:
                self._zustand, self._schritt, self._fehler = "verbunden", "verbunden", None
                self._grund = self._tipp = None
                self._geraet = self._versuch_geraet  # ab jetzt gehoert die Kopplung diesem Handy
                self._war_verbunden = True
                self._verbunden_seit = self._uhr()
            log.info("Handy-Kamera verbunden")
        elif stand == "failed":
            if self._zustand == "verbunden":
                await self._getrennt("Verbindung zum Handy verloren.")
            else:
                await self._gescheitert(pc, "abgebrochen")
        elif stand == "closed" and self._zustand == "verbunden":
            await self._getrennt("Verbindung zum Handy beendet.")

    def _paar_im_lan(self, pc) -> bool:
        """Das von ICE gewaehlte Paar nochmals pruefen (auch peer-reflexive). Im Zweifel: False.

        Fehlt die interne Struktur von aioice (andere Version), werden ersatzweise ALLE Kandidaten der
        Gegenseite geprueft, die die ICE-Transporte kennen (dazu gehoeren auch gelernte peer-reflexive).
        Geht beides nicht, gilt die Verbindung als nicht im LAN (lieber trennen als ins Internet senden)."""
        try:
            verbindungen = [v for v in self._ice_verbindungen(pc) if hasattr(v, "_nominated")]
            paare = [paar for v in verbindungen for paar in v._nominated.values()]
            if paare:
                return all(self._lan(paar.remote_addr[0]) for paar in paare)
            return self._ferne_kandidaten_im_lan(pc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Handy-Kamera: Adresspaar nicht pr\u00fcfbar (%s) - getrennt", type(exc).__name__)
            return False

    def _ferne_kandidaten_im_lan(self, pc) -> bool:
        """Ersatzpruefung ueber die oeffentliche Schnittstelle der ICE-Transporte."""
        transporte = [t.receiver.transport.transport for t in pc.getTransceivers()]
        if getattr(pc, "sctp", None) is not None:
            transporte.append(pc.sctp.transport.transport)
        adressen = []
        for ice in transporte:
            for kandidat in ice.getRemoteCandidates():
                adressen.append(getattr(kandidat, "ip", None) or "")
        if not adressen:
            log.warning("Handy-Kamera: kein Adresspaar und keine Kandidaten der Gegenseite bekannt - getrennt")
            return False
        return all(self._lan(adresse) for adresse in adressen)

    async def _getrennt(self, grund: str) -> None:
        with self._sperre:
            self._zustand, self._schritt = "getrennt", "getrennt"
            self._fehler = grund
            self._frame, self._cache = None, None
            self._frist = self._uhr() + self.wiederverbinden_s
        log.info("Handy-Kamera getrennt: %s", grund)
        await self._schliesse_pc()

    def _setze_fehler(self, text: str, grund: str | None = None, tipp: str | None = None) -> None:
        with self._sperre:
            self._zustand, self._schritt, self._fehler = "fehler", "fehler", text
            self._grund, self._tipp = grund, tipp
            self._frame, self._cache = None, None
        log.info("Handy-Kamera: %s", text)

    def _setze_grund(self, grund: str) -> None:
        text, tipp = grund_texte(grund, self._versuch)
        self._setze_fehler(text, grund, tipp or None)

    async def _lies(self, track, pc) -> None:
        while pc is self._pc:
            try:
                frame = await track.recv()
            except Exception:  # noqa: BLE001 - MediaStreamError: Spur zu Ende
                return
            with self._sperre:
                if pc is not self._pc:
                    return
                self._frame = frame
                self._frame_zeit = time.monotonic()
                self._frame_nr += 1
                self.bilder += 1

    def _steuerkanal(self, kanal, pc) -> None:
        self._dc = kanal

        def senden(daten: dict) -> None:
            try:
                if kanal.readyState == "open":
                    kanal.send(json.dumps(daten))
            except Exception:  # noqa: BLE001
                pass

        @kanal.on("open")
        def _offen():
            senden({"t": "hallo", "name": "Nova", "v": sig.PROTOKOLL})

        if kanal.readyState == "open":
            senden({"t": "hallo", "name": "Nova", "v": sig.PROTOKOLL})

        @kanal.on("message")
        def _nachricht(roh):
            if pc is not self._pc or not isinstance(roh, str) or len(roh) > MAX_DC_NACHRICHT:
                return
            try:
                daten = json.loads(roh)
            except ValueError:
                return
            if not isinstance(daten, dict):
                return
            typ = daten.get("t")
            if typ == "ping":
                senden({"t": "pong"})
            elif typ == "status":
                seite = daten.get("kamera")
                if seite in ("vorne", "hinten"):
                    self._kamera_seite = seite
                if isinstance(daten.get("sichtbar"), bool):
                    self._handy_sichtbar = daten["sichtbar"]
            elif typ == "stopp":
                asyncio.ensure_future(self._getrennt("Am Handy beendet."))

    async def _schliesse_pc(self) -> None:
        pc, self._pc, self._dc = self._pc, None, None
        if pc is not None:
            try:
                await asyncio.wait_for(pc.close(), timeout=5)
            except Exception:  # noqa: BLE001
                pass

    async def _beenden(self) -> None:
        kanal = self._dc
        if kanal is not None:
            try:
                if kanal.readyState == "open":
                    kanal.send(json.dumps({"t": "stopp"}))
                    await asyncio.sleep(0.2)  # damit es noch rausgeht
            except Exception:  # noqa: BLE001
                pass
        haupt = self._haupt
        if haupt is not None and not haupt.done() and haupt is not asyncio.current_task():
            haupt.cancel()
            try:
                await haupt
            except BaseException:  # noqa: BLE001 - CancelledError ist hier normal
                pass
        await self._schliesse_pc()
        asyncio.get_running_loop().call_soon(asyncio.get_running_loop().stop)
