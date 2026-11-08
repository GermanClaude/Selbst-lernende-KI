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
  * Genau ein Handy pro Kopplung (an seiner Geraete-ID erkannt). Bricht die Verbindung ab, darf
    dasselbe Handy innerhalb von ``wiederverbinden_s`` ein neues Angebot schicken.
  * aiortc und av werden erst in start() geladen - fehlen sie, kommt ein deutscher Hinweis.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import io
import json
import logging
import threading
import time
from dataclasses import dataclass

from . import signal as sig

log = logging.getLogger(__name__)

ZUSTAENDE = ("wartet", "verbunden", "getrennt", "fehler")
PAKET_HINWEIS = ("F\u00fcr die Handy-Kamera fehlen noch Pakete. Im Terminal: "
                 "pip install aiortc av cryptography segno")
WLAN_HINWEIS = ("Keine Verbindung zum Handy. Handy und PC m\u00fcssen im selben WLAN sein "
                "(kein G\u00e4ste-WLAN, kein mobiles Netz).")
MAX_SDP = 24_000
MAX_DC_NACHRICHT = 4096


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
                 lan_pruefung=sig.ist_lan_adresse, uhr=time.time):
        self._relay_vorgabe = relay
        self.basis_url = basis_url
        self.gueltig = gueltig
        self.mit_code = mit_code
        self.verbinden_timeout = verbinden_timeout
        self.wiederverbinden_s = wiederverbinden_s
        self.warte_intervall = warte_intervall
        self._lan = lan_pruefung
        self._uhr = uhr
        self._sperre = threading.RLock()
        self._zustand = "getrennt"
        self._schritt = "aus"
        self._fehler: str | None = None
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
        loop = asyncio.new_event_loop()
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
        log.info("Angebot vom Handy: %d LAN-Kandidat(en), %d verworfen", behalten, verworfen)
        if behalten == 0:
            await self._sende("fehler", {"grund": "kein-lan", "g": self._versuch_geraet})
            self._setze_fehler(WLAN_HINWEIS)
            return
        self._schritt = "verbindet"
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
            await pc.setLocalDescription(await pc.createAnswer())
        except Exception as exc:  # noqa: BLE001 - z.B. kein gemeinsamer Codec
            log.warning("Angebot vom Handy nicht verwendbar (%s)", type(exc).__name__)
            await self._sende("fehler", {"grund": "angebot", "g": self._versuch_geraet})
            self._setze_fehler("Das Handy-Video passt nicht zu Nova (Codec). Bitte einen anderen Browser versuchen.")
            await self._schliesse_pc()
            return
        antwort, behalten, _ = self._filtere(pc.localDescription.sdp)
        if behalten == 0:
            await self._sende("fehler", {"grund": "pc-kein-lan", "g": self._versuch_geraet})
            self._setze_fehler("Dieser PC hat keine Adresse im Heimnetz (WLAN/LAN).")
            await self._schliesse_pc()
            return
        await self._sende("antwort", {"sdp": antwort, "g": self._versuch_geraet})
        asyncio.ensure_future(self._verbinden_aufpassen(pc))

    def _filtere(self, sdp: str) -> tuple[str, int, int]:
        return sig.filtere_sdp(sdp, self._lan)

    async def _verbinden_aufpassen(self, pc) -> None:
        await asyncio.sleep(self.verbinden_timeout)
        if pc is self._pc and pc.connectionState != "connected":
            log.info("Handy-Kamera: keine Verbindung innerhalb von %.0f s", self.verbinden_timeout)
            self._setze_fehler(WLAN_HINWEIS)
            self._frist = self._uhr() + self.wiederverbinden_s
            await self._schliesse_pc()

    async def _verbindungszustand(self, pc) -> None:
        if pc is not self._pc:
            return
        stand = pc.connectionState
        if stand == "connected":
            if not self._paar_im_lan(pc):
                log.warning("Handy-Kamera: gew\u00e4hltes Adresspaar liegt nicht im LAN - getrennt")
                self._setze_fehler(WLAN_HINWEIS)
                await self._schliesse_pc()
                return
            with self._sperre:
                self._zustand, self._schritt, self._fehler = "verbunden", "verbunden", None
                self._geraet = self._versuch_geraet  # ab jetzt gehoert die Kopplung diesem Handy
                self._war_verbunden = True
                self._verbunden_seit = self._uhr()
            log.info("Handy-Kamera verbunden")
        elif stand == "failed":
            if self._zustand == "verbunden":
                await self._getrennt("Verbindung zum Handy verloren.")
            else:
                self._setze_fehler(WLAN_HINWEIS)
                self._frist = self._uhr() + self.wiederverbinden_s
                await self._schliesse_pc()
        elif stand == "closed" and self._zustand == "verbunden":
            await self._getrennt("Verbindung zum Handy beendet.")

    def _paar_im_lan(self, pc) -> bool:
        """Best effort: das von ICE gewaehlte Paar nochmals pruefen (auch peer-reflexive)."""
        try:
            for transceiver in pc.getTransceivers():
                verbindung = transceiver.receiver.transport.transport._connection
                for paar in verbindung._nominated.values():
                    if not self._lan(paar.remote_addr[0]):
                        return False
        except Exception:  # noqa: BLE001 - interne Struktur von aiortc/aioice anders
            return True
        return True

    async def _getrennt(self, grund: str) -> None:
        with self._sperre:
            self._zustand, self._schritt = "getrennt", "getrennt"
            self._fehler = grund
            self._frame, self._cache = None, None
            self._frist = self._uhr() + self.wiederverbinden_s
        log.info("Handy-Kamera getrennt: %s", grund)
        await self._schliesse_pc()

    def _setze_fehler(self, text: str) -> None:
        with self._sperre:
            self._zustand, self._schritt, self._fehler = "fehler", "fehler", text
            self._frame, self._cache = None, None
        log.info("Handy-Kamera: %s", text)

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
