"""Lokaler Webserver fuer das App-Fenster.

Nur auf 127.0.0.1 erreichbar und nur mit dem geheimen Schluessel (Token), der in
der Adresse des Fensters steckt. Zusaetzlich wird der Host-Header geprueft, damit
fremde Webseiten im Browser nicht ueber Umwege (DNS-Rebinding) Befehle schicken
koennen. Der Server spricht nur mit der eigenen Oberflaeche:
  GET  /, /static/*      Oberflaeche
  GET  /api/events       Ereignisstrom (Server-Sent Events)
  GET  /api/state, /api/history, /api/profile, /api/memory, /api/tutorial, /api/appearance, /custom.css,
       /api/setup, /api/feedback
  GET  /api/bild/<h|e>/<name>?t=   Bild anzeigen: h = hochgeladen (data/bilder/hochgeladen),
                                   e = erstellt (<Arbeitsordner>/bilder) - nur PNG/JPEG/GIF/WebP
  POST /api/send (Text + Bilder, Warteschlange, interrupt), /api/queue, /api/afk, /api/stop,
       /api/answer, /api/voice, /api/toggle, /api/profile, /api/memory, /api/jarvis, /api/tutorial,
       /api/setup, /api/modell, /api/update, /api/feedback, /api/feedback/spaeter,
       /api/feedback/gezeigt, /api/bilder/einstellen
Anfragen duerfen hoechstens 1 MB gross sein - /api/send und /api/feedback (mit Bildern) 40 MB.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..logging_setup import get_logger

logger = get_logger()

STATIC_DIR = Path(__file__).resolve().parent / "static"
_MAX_BODY = 1_000_000
_MAX_BODY_BILDER = 40 * 1024 * 1024           # /api/send und /api/feedback (Bilder als data:-URL)
_GROSSE_ANFRAGEN = ("/api/send", "/api/feedback")
_MAX_VERWERFEN = 64 * 1024 * 1024             # zu grosse Anfrage bis hierhin noch lesen (sauberes 413)
_MAX_BILD_DATEI = 30 * 1024 * 1024            # groesser liefert /api/bild nichts aus
_BILD_ARTEN = ("h", "e")                      # hochgeladen | erstellt
_ZU_GROSS = ("Die Nachricht ist zu gro\u00df (h\u00f6chstens 40 MB). Bitte weniger oder kleinere "
             "Bilder anh\u00e4ngen.")


class EventHub:
    """Verteilt Ereignisse an alle offenen Fenster (jedes hat eine eigene Warteschlange)."""

    def __init__(self):
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()
        self.last_seen = time.monotonic()
        self.ever_connected = False

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=5000)
        with self._lock:
            self._clients.append(q)
            self.ever_connected = True
            self.last_seen = time.monotonic()
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)
            self.last_seen = time.monotonic()

    @property
    def connected(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast(self, event: dict) -> None:
        data = json.dumps(event, ensure_ascii=False)
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(data)
            except queue.Full:  # Fenster haengt - nicht die KI aufhalten
                pass


class AppServer:
    def __init__(self, controller_factory, host: str = "127.0.0.1", port: int = 0):
        self.token = secrets.token_urlsafe(24)
        self.hub = EventHub()
        self.controller = None
        self._factory = controller_factory
        self.httpd = ThreadingHTTPServer((host, port), self._handler_class())
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.stopping = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> None:
        self.controller = self._factory(self.hub.broadcast)
        threading.Thread(target=self.httpd.serve_forever, name="app-server", daemon=True).start()

    def stop(self) -> None:
        self.stopping.set()
        self.hub.broadcast({"type": "bye"})
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:  # noqa: BLE001
            pass

    # -- Anfragen -----------------------------------------------------------------
    def _handler_class(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # nichts auf die (evtl. fehlende) Konsole
                logger.debug("app: " + fmt, *args)

            # Schutz: nur unser Host, nur mit Schluessel
            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").lower()
                return host in (f"127.0.0.1:{server.port}", f"localhost:{server.port}")

            def _token_ok(self, query: dict) -> bool:
                given = self.headers.get("X-KI-Token") or (query.get("t") or [""])[0]
                return hmac.compare_digest(given.encode(), server.token.encode())

            def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data: dict, code: int = 200) -> None:
                self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _deny(self, code: int = 403) -> None:
                self._json({"ok": False, "error": "nicht erlaubt"}, code)

            def do_GET(self):  # noqa: N802
                url = urlparse(self.path)
                query = parse_qs(url.query)
                if not self._host_ok():
                    return self._deny()
                if url.path in ("/", "/index.html"):
                    if not self._token_ok(query):
                        return self._send(403, "Bitte die App neu starten.".encode("utf-8"), "text/plain; charset=utf-8")
                    return self._static("index.html")
                if url.path.startswith("/static/"):
                    return self._static(url.path[len("/static/"):])
                if url.path == "/custom.css":  # Aussehen, das Nova angepasst hat
                    return self._send(200, server.controller.custom_css().encode("utf-8"), "text/css; charset=utf-8")
                if not self._token_ok(query):
                    return self._deny()
                ctl = server.controller
                if url.path == "/api/events":
                    return self._events()
                if url.path == "/api/state":
                    return self._json(ctl.state())
                if url.path == "/api/history":
                    return self._json({"messages": ctl.history[-400:]})
                if url.path == "/api/profile":
                    return self._json(ctl.profile())
                if url.path == "/api/memory":
                    return self._json(ctl.memory_facts())
                if url.path == "/api/tutorial":
                    return self._json(ctl.tutorial())
                if url.path == "/api/appearance":
                    return self._json(ctl.appearance())
                if url.path == "/api/setup":
                    return self._json(ctl.setup_info())
                if url.path == "/api/feedback":
                    return self._json(ctl.feedback_status())
                if url.path.startswith("/api/bild/"):
                    return self._bild(url.path[len("/api/bild/"):])
                return self._deny(404)

            def _bild(self, rest: str) -> None:
                """Ein Bild aus einem der beiden Bilder-Ordner - nie ein anderer Pfad, nie SVG."""
                from ..bilder import erkenne_typ
                from ..bildgenerator import DATEINAME_MUSTER

                kind, _, name = rest.partition("/")
                if kind not in _BILD_ARTEN or not DATEINAME_MUSTER.match(name):
                    return self._deny(404)
                ordner = server.controller.bild_ordner(kind)
                if ordner is None:
                    return self._deny(404)
                try:
                    ordner = Path(ordner).resolve()
                    pfad = ordner / name
                    # Auch ein Verweis (Symlink) im Ordner darf nicht nach draussen zeigen.
                    if pfad.resolve().parent != ordner or not pfad.is_file():
                        return self._deny(404)
                    if pfad.stat().st_size > _MAX_BILD_DATEI:
                        return self._deny(404)
                    data = pfad.read_bytes()
                except OSError:
                    return self._deny(404)
                mime = erkenne_typ(data)  # Typ an den Bytes, nicht am Namen (nie HTML/SVG ausliefern)
                if mime is None:
                    return self._deny(415)
                self._send(200, data, mime, {"Content-Disposition": f'inline; filename="{name}"',
                                             "Content-Security-Policy": "default-src 'none'; sandbox"})

            def _verwerfen(self, length: int) -> None:
                """Zu grosse Anfrage: den Rest lesen und wegwerfen (sonst haelt die Gegenseite die
                Antwort nie in der Hand) und danach die Verbindung schliessen - die ungelesenen
                Bytes duerfen nie als naechste Anfrage gelten."""
                self.close_connection = True
                if length > _MAX_VERWERFEN:
                    return
                try:
                    self.connection.settimeout(10)
                    rest = length
                    while rest > 0:
                        stueck = self.rfile.read(min(rest, 1 << 20))
                        if not stueck:
                            break
                        rest -= len(stueck)
                except OSError:
                    pass

            def do_POST(self):  # noqa: N802
                url = urlparse(self.path)
                if not self._host_ok() or not self._token_ok({}):
                    self.close_connection = True  # Inhalt ungelesen -> nicht weiter auf dieser Verbindung
                    return self._deny()
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length < 0:
                        raise ValueError("Content-Length")
                    grenze = _MAX_BODY_BILDER if url.path in _GROSSE_ANFRAGEN else _MAX_BODY
                    if length > grenze:
                        self._verwerfen(length)
                        return self._send(413, json.dumps({"ok": False, "error": _ZU_GROSS}, ensure_ascii=False)
                                          .encode("utf-8"), "application/json; charset=utf-8",
                                          {"Connection": "close"})
                    body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                except (ValueError, json.JSONDecodeError):
                    self.close_connection = True
                    return self._json({"ok": False, "error": "ungueltige Anfrage"}, 400)
                if not isinstance(body, dict):
                    return self._json({"ok": False, "error": "ungueltige Anfrage"}, 400)
                try:
                    return self._post(url, body)
                except (TypeError, ValueError, AttributeError, KeyError) as exc:  # kaputte Anfrage
                    return self._json({"ok": False, "error": f"ungueltige Anfrage: {exc}"}, 400)
                except Exception as exc:  # noqa: BLE001 - Antwort statt abgebrochener Verbindung
                    logger.exception("Fehler bei %s", url.path)
                    return self._json({"ok": False, "error": str(exc)}, 500)

            def _post(self, url, body: dict):
                ctl = server.controller
                if url.path == "/api/send":
                    return self._json(ctl.submit(str(body.get("text") or ""), bool(body.get("interrupt")),
                                                 images=body.get("images"), client_id=body.get("client_id")))
                if url.path == "/api/feedback":
                    return self._json(ctl.feedback_send(body))
                if url.path in ("/api/feedback/spaeter", "/api/feedback/gezeigt"):
                    return self._json(ctl.feedback_seen(url.path.rsplit("/", 1)[-1]))
                if url.path == "/api/bilder/einstellen":
                    return self._json(ctl.bilder_einstellen(body))
                if url.path == "/api/queue":
                    return self._json(ctl.queue_action(str(body.get("action", "")), body.get("id")))
                if url.path == "/api/afk":
                    return self._json(ctl.afk(body))
                if url.path == "/api/stop":
                    ctl.stop()
                    return self._json({"ok": True})
                if url.path == "/api/answer":
                    return self._json({"ok": ctl.answer(str(body.get("id", "")), str(body.get("value", "")))})
                if url.path == "/api/voice":
                    return self._json(ctl.voice(str(body.get("action", ""))))
                if url.path == "/api/toggle":
                    ctl.toggle(str(body.get("name", "")), bool(body.get("value")))
                    return self._json({"ok": True, "state": ctl.state()})
                if url.path == "/api/profile":
                    try:
                        return self._json({"ok": True, "profile": ctl.save_profile(body)})
                    except (ValueError, OSError) as exc:
                        return self._json({"ok": False, "error": str(exc)})
                if url.path == "/api/memory":
                    return self._json(ctl.memory_action(body))
                if url.path == "/api/jarvis":
                    return self._json(ctl.jarvis(str(body.get("action", "")), str(body.get("tts", "client")),
                                                 body.get("turn"), body.get("seq"), bool(body.get("progress"))))
                if url.path == "/api/tutorial":
                    return self._json(ctl.tutorial_action(str(body.get("action", ""))))
                if url.path == "/api/setup":
                    return self._json(ctl.setup_save(body))
                if url.path == "/api/modell":
                    return self._json(ctl.choose_model(body))
                if url.path == "/api/update":
                    return self._json(ctl.check_update_now())
                return self._deny(404)

            def _static(self, name: str) -> None:
                path = (STATIC_DIR / name).resolve()
                if STATIC_DIR not in path.parents or not path.is_file():
                    return self._deny(404)
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript",):
                    ctype += "; charset=utf-8"
                csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                       "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                       "frame-ancestors 'none'")
                self._send(200, path.read_bytes(), ctype, {"Content-Security-Policy": csp})

            def _events(self) -> None:
                q = server.hub.subscribe()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    hello = json.dumps({"type": "hello", "state": server.controller.state()}, ensure_ascii=False)
                    self.wfile.write(f"data: {hello}\n\n".encode("utf-8"))
                    # Offene Rueckfragen erneut zeigen (neu geladenes oder zweites Fenster) - sonst
                    # wartet die KI auf eine Antwort, die niemand mehr geben kann.
                    for ask in server.controller.open_asks():
                        self.wfile.write(f"data: {json.dumps(ask, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    while not server.stopping.is_set():
                        try:
                            data = q.get(timeout=15)
                            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")  # Verbindung lebt
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    server.hub.unsubscribe(q)
                    self.close_connection = True

        return Handler
