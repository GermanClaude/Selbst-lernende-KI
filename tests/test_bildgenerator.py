"""Bildgenerator (AI Horde / Cloudflare) und Werkzeug bild_erstellen - alles ohne Netz."""
from __future__ import annotations

import base64
import dataclasses
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant import __version__
from assistant import bildgenerator as bg
from assistant.cancel import Abgebrochen
from assistant.config import BilderSettings, PermissionSettings, load_config
from assistant.permissions import PermissionManager
from assistant.tools import READ_ONLY_TOOLS, ToolContext, build_registry

WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TOKEN = "cf-geheimer-token-1234567890abcdef"
KONTO = "0123456789abcdef0123456789abcdef"
BILD_URL = "https://r2.example.com/bild.webp?sig=1"
CF_URL = f"https://api.cloudflare.com/client/v4/accounts/{KONTO}/ai/run/@cf/black-forest-labs/flux-1-schnell"

MODELLE = [
    {"name": "Flux.1-Schnell fp8 (Compact)", "count": 7, "eta": 72, "type": "image"},
    {"name": "Z-Image-Turbo", "count": 3, "eta": 135, "type": "image"},
    {"name": "Qwen-Image_fp8", "count": 4, "eta": 13, "type": "image"},
    {"name": "Juggernaut XL", "count": 11, "eta": 94, "type": "image"},
    {"name": "AlbedoBase XL (SDXL)", "count": 12, "eta": 42, "type": "image"},
    {"name": "Deliberate", "count": 12, "eta": 0, "type": "image"},
]


# ----- Attrappen ---------------------------------------------------------------
class Antwort:
    def __init__(self, status=200, daten=None, content=None, headers=None):
        self.status_code = status
        self._daten = daten
        if content is None:
            content = json.dumps(daten).encode() if daten is not None else b""
        self.content = content
        self.headers = headers or {}
        self.geschlossen = False

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten

    def iter_content(self, groesse):
        for i in range(0, len(self.content), groesse):
            yield self.content[i:i + groesse]

    def close(self):
        self.geschlossen = True


class FakeHttp:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self._lock = threading.Lock()

    def _rufe(self, methode, url, kw):
        with self._lock:
            self.calls.append((methode, url, kw))
        antwort = self.handler(methode, url, kw)
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort

    def get(self, url, **kw):
        return self._rufe("GET", url, kw)

    def post(self, url, **kw):
        return self._rufe("POST", url, kw)

    def delete(self, url, **kw):
        return self._rufe("DELETE", url, kw)

    def urls(self, methode=None, teil=""):
        return [u for m, u, _ in self.calls if (methode is None or m == methode) and teil in u]

    def posts(self, teil=""):
        return [kw for m, u, kw in self.calls if m == "POST" and teil in u]


def _status(**generation):
    bild = {"img": BILD_URL, "model": "Flux.1-Schnell fp8 (Compact)", "seed": "42", "censored": False}
    bild.update(generation)
    return {"done": True, "finished": 1, "generations": [bild]}


def horde_handler(checks=None, status=None, modelle=None, bild=WEBP, post=None, bild_antwort=None,
                  weiter=None):
    """Spielt AI Horde nach. checks: Liste der /check-Antworten (die letzte wiederholt sich)."""
    checks = list(checks or [{"done": True, "finished": 1}])
    zustand = {"check": 0, "post": 0}

    def handler(methode, url, kw):
        if methode == "GET" and url.startswith("https://aihorde.net/api/v2/status/models"):
            if isinstance(modelle, (Antwort, BaseException)):
                return modelle
            return Antwort(200, MODELLE if modelle is None else modelle)
        if methode == "POST" and url == "https://aihorde.net/api/v2/generate/async":
            zustand["post"] += 1
            return post or Antwort(202, {"id": f"auftrag-{zustand['post']:04d}", "kudos": 10})
        if methode == "GET" and "/api/v2/generate/check/" in url:
            i = min(zustand["check"], len(checks) - 1)
            zustand["check"] += 1
            c = checks[i]
            return c if isinstance(c, (Antwort, BaseException)) else Antwort(200, c)
        if methode == "GET" and "/api/v2/generate/status/" in url:
            return status if isinstance(status, Antwort) else Antwort(200, status or _status())
        if methode == "DELETE" and "/api/v2/generate/status/" in url:
            return Antwort(200, {})
        if methode == "GET" and url.startswith("https://r2.example.com"):
            return bild_antwort or Antwort(200, content=bild, headers={"Content-Type": "image/webp"})
        if weiter is not None:
            return weiter(methode, url, kw)
        raise AssertionError(f"unerwarteter Aufruf: {methode} {url}")

    return handler


def horde(**kw):
    return FakeHttp(horde_handler(**kw))


def cloudflare(antwort, **horde_kw):
    """Cloudflare antwortet mit `antwort`; alles andere spielt AI Horde."""
    def weiter(methode, url, kw):
        if methode == "POST" and url.startswith("https://api.cloudflare.com/"):
            return antwort
        raise AssertionError(f"unerwarteter Aufruf: {methode} {url}")

    return FakeHttp(horde_handler(weiter=weiter, **horde_kw))


class Uhr:
    def __init__(self):
        self.t = 1000.0
        self.pausen = []

    def __call__(self):
        return self.t

    def warte(self, sekunden):
        self.pausen.append(sekunden)
        self.t += sekunden


def _config(anbieter="auto", token=None, konto=None):
    return SimpleNamespace(bilder=BilderSettings(anbieter=anbieter), cloudflare_api_key=token,
                           cloudflare_account_id=konto)


def _gen(http, config=None, uhr=None, **kw):
    uhr = uhr or Uhr()
    meldungen = []
    gen = bg.Bildgenerator(config, http=http, fortschritt=meldungen.append, uhr=uhr, warten=uhr.warte, **kw)
    return gen, meldungen, uhr


def _cf_ok(data=JPEG):
    return Antwort(200, {"result": {"image": base64.b64encode(data).decode()}, "success": True,
                         "errors": [], "messages": []})


def _cf_fehler(status, code=None, text=""):
    fehler = [{"code": code, "message": text}] if code is not None or text else []
    return Antwort(status, {"result": None, "success": False, "errors": fehler, "messages": []})


def _warte_aufraeumen(gen):
    if gen.aufraeum_thread is not None:
        gen.aufraeum_thread.join(5)


@pytest.fixture(autouse=True)
def _leerer_cache():
    bg.modelle_cache_leeren()
    yield
    bg.modelle_cache_leeren()


# ----- Auswahl des Anbieters ------------------------------------------------------
def test_waehle_anbieter():
    assert bg.waehle_anbieter(None) == bg.HORDE == "horde"
    assert bg.waehle_anbieter(_config()) == "horde"
    assert bg.waehle_anbieter(_config(token=TOKEN, konto=KONTO)) == bg.CLOUDFLARE == "cloudflare"
    assert bg.waehle_anbieter(_config(token=TOKEN)) == "horde"            # Konto fehlt
    assert bg.waehle_anbieter(_config(konto=KONTO)) == "horde"            # Schluessel fehlt
    assert bg.waehle_anbieter(_config(token="  ", konto=KONTO)) == "horde"
    assert bg.waehle_anbieter(_config("horde", TOKEN, KONTO)) == "horde"  # ausdruecklich Horde
    assert bg.waehle_anbieter(_config("cloudflare")) == "horde"           # geht nicht ohne Schluessel
    assert bg.waehle_anbieter(_config("Cloudflare", TOKEN, KONTO)) == "cloudflare"
    assert bg.waehle_anbieter(_config("quatsch", TOKEN, KONTO)) == "cloudflare"  # unbekannt = auto
    assert bg.aktiver_anbieter(_config()) == "AI Horde"
    assert bg.aktiver_anbieter(_config(token=TOKEN, konto=KONTO)) == "Cloudflare"
    assert bg.cloudflare_eingerichtet(_config(token=TOKEN, konto=KONTO)) is True
    assert bg.cloudflare_eingerichtet(_config(token=TOKEN)) is False


def test_waehle_anbieter_mit_echter_config():
    cfg = dataclasses.replace(load_config(), bilder=BilderSettings(), cloudflare_api_key=None,
                              cloudflare_account_id=None)
    assert bg.waehle_anbieter(cfg) == "horde"
    cfg = dataclasses.replace(cfg, cloudflare_api_key=TOKEN, cloudflare_account_id=KONTO)
    assert bg.waehle_anbieter(cfg) == "cloudflare"
    cfg = dataclasses.replace(cfg, bilder=BilderSettings(anbieter="horde"))
    assert bg.waehle_anbieter(cfg) == "horde"


# ----- AI Horde ---------------------------------------------------------------
def test_horde_ablauf_mit_warteschlange():
    http = horde(checks=[
        {"done": False, "waiting": 1, "processing": 0, "queue_position": 3, "wait_time": 40, "is_possible": True},
        {"done": False, "waiting": 0, "processing": 1, "queue_position": 0, "wait_time": 8, "is_possible": True},
        {"done": True, "finished": 1, "waiting": 0, "processing": 0},
    ])
    gen, meldungen, uhr = _gen(http)
    erg = gen.erstellen("A red cat on a roof", "hoch")

    assert erg.data == WEBP and erg.mime == "image/webp" and erg.endung == "webp"
    assert erg.anbieter == "AI Horde" and erg.modell == "Flux.1-Schnell fp8 (Compact)"
    assert erg.hinweis == ""
    assert "In der Warteschlange: Platz 3, ca. 40 s" in meldungen
    assert "Das Bild wird gemalt, ca. 8 s" in meldungen
    assert len(uhr.pausen) == 2 and all(2 <= p <= 10 for p in uhr.pausen)

    (auftrag,) = http.posts("generate/async")
    kopf = auftrag["headers"]
    assert kopf["apikey"] == "0000000000"
    assert kopf["Client-Agent"] == f"Nova:{__version__}:https://github.com/GermanClaude/Selbst-lernende-KI"
    body = auftrag["json"]
    assert body["prompt"] == "A red cat on a roof"
    assert body["nsfw"] is False and body["censor_nsfw"] is True and body["r2"] is True
    assert body["allow_downgrade"] is True and body["slow_workers"] is True
    assert body["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    params = body["params"]
    assert (params["width"], params["height"]) == (768, 1152)
    assert params["steps"] == 4 and params["cfg_scale"] == 1.0 and params["sampler_name"] == "k_euler"
    assert params["n"] == 1 and params["seed"].isdigit() and 1 <= int(params["seed"]) < 2**31

    assert len(http.urls("GET", "/generate/status/")) == 1  # Ergebnis genau einmal abholen
    assert http.urls("GET", "/generate/check/auftrag-0001")
    assert not http.urls("DELETE")
    assert all("timeout" in kw for _m, _u, kw in http.calls)  # nie ohne Timeout
    (download,) = [kw for m, u, kw in http.calls if u == BILD_URL]
    assert download["allow_redirects"] is False and download["stream"] is True


def test_horde_formate_und_zufaelliger_seed():
    seeds = []
    for fmt, groesse in (("quadrat", (1024, 1024)), ("quer", (1152, 768)), ("hoch", (768, 1152)),
                         ("landscape", (1152, 768)), ("unbekannt", (1024, 1024))):
        http = horde()
        _gen(http)[0].erstellen("a lighthouse", fmt)
        params = http.posts("generate/async")[0]["json"]["params"]
        assert (params["width"], params["height"]) == groesse
        assert params["width"] % 64 == 0 and params["height"] % 64 == 0
        seeds.append(params["seed"])
    assert len(set(seeds)) > 1


def test_horde_modellwahl_ohne_flux_nimmt_z_image():
    http = horde(modelle=[m for m in MODELLE if "Flux" not in m["name"]])
    erg = _gen(http)[0].erstellen("a forest")
    body = http.posts("generate/async")[0]["json"]
    assert body["models"] == ["Z-Image-Turbo"]
    assert body["params"]["steps"] == 9 and body["params"]["cfg_scale"] == 1.0
    assert erg.modell == "Flux.1-Schnell fp8 (Compact)"  # was der Rechner meldet (aus der Attrappe)


def test_horde_modellwahl_nur_sdxl_mit_negativ_prompt():
    nur_sdxl = [m for m in MODELLE if "XL" in m["name"]] + [{"name": "Flux.1-Schnell", "count": 0, "eta": 0}]
    http = horde(modelle=nur_sdxl)
    _gen(http)[0].erstellen("a castle ### with stuff")
    body = http.posts("generate/async")[0]["json"]
    assert body["models"] == ["AlbedoBase XL (SDXL)", "Juggernaut XL"]  # mehr Rechner zuerst
    assert body["params"]["steps"] == 25 and body["params"]["cfg_scale"] == 6.0
    vorne, negativ = body["prompt"].split(" ### ")
    assert vorne == "a castle with stuff"  # '###' aus der Beschreibung entfernt
    assert "nsfw" in negativ and "nude" in negativ


def test_horde_lange_warteschlange_rutscht_nach_hinten():
    modelle = [{"name": "Flux.1-Schnell fp8 (Compact)", "count": 7, "eta": 900},
               {"name": "Z-Image-Turbo", "count": 3, "eta": 60}]
    http = horde(modelle=modelle)
    _gen(http)[0].erstellen("a boat")
    assert http.posts("generate/async")[0]["json"]["models"] == ["Z-Image-Turbo"]


@pytest.mark.parametrize("modelle", [Antwort(500, {"message": "kaputt"}), ConnectionError("weg"),
                                     Antwort(200, {"kein": "liste"}), []])
def test_horde_ohne_modellliste_nimmt_standardmodell(modelle):
    http = horde(modelle=modelle)
    _gen(http)[0].erstellen("a boat")
    body = http.posts("generate/async")[0]["json"]
    assert body["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    assert body["params"]["steps"] == 4


def test_horde_modellliste_wird_eine_stunde_gemerkt():
    uhr = Uhr()
    http = horde()
    _gen(http, uhr=uhr)[0].erstellen("eins")
    _gen(http, uhr=uhr)[0].erstellen("zwei")
    assert len(http.urls("GET", "/status/models")) == 1
    assert http.urls("GET", "/status/models")[0].endswith("/status/models?type=image")
    uhr.t += 3601
    _gen(http, uhr=uhr)[0].erstellen("drei")
    assert len(http.urls("GET", "/status/models")) == 2


def test_horde_faulted_bricht_ab_und_zieht_zurueck():
    http = horde(checks=[{"done": False, "faulted": True}])
    gen, _m, _u = _gen(http)
    with pytest.raises(bg.GeneratorFehler, match="Fehler gemeldet"):
        gen.erstellen("a dog")
    _warte_aufraeumen(gen)
    assert http.urls("DELETE", "/generate/status/auftrag-0001")
    assert not http.urls("GET", "/generate/status/")


def test_horde_nicht_moeglich_versucht_naechstes_modell():
    http = horde(checks=[{"done": False, "is_possible": False, "waiting": 1}, {"done": True}])
    gen, _m, _u = _gen(http)
    erg = gen.erstellen("a dog")
    assert erg.data == WEBP
    erster, zweiter = http.posts("generate/async")
    assert erster["json"]["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    assert zweiter["json"]["models"] == ["Z-Image-Turbo"]
    _warte_aufraeumen(gen)
    assert http.urls("DELETE", "auftrag-0001") and not http.urls("DELETE", "auftrag-0002")


def test_horde_nicht_moeglich_gibt_freundlich_auf():
    http = horde(checks=[{"done": False, "is_possible": False}])
    gen, _m, _u = _gen(http)
    with pytest.raises(bg.GeneratorFehler) as info:
        gen.erstellen("a dog")
    assert "kein passender Rechner" in str(info.value)
    assert len(http.posts("generate/async")) == 2  # hoechstens ein zweiter Versuch


def test_horde_gibt_nach_neun_minuten_auf():
    http = horde(checks=[{"done": False, "waiting": 1, "queue_position": 50, "wait_time": 400,
                          "is_possible": True}])
    gen, meldungen, uhr = _gen(http)
    start = uhr.t
    with pytest.raises(bg.GeneratorFehler, match="9 Minuten"):
        gen.erstellen("a dog")
    assert uhr.t - start == pytest.approx(bg.HORDE_MAX_SEKUNDEN)
    assert all(p <= 10 for p in uhr.pausen)
    assert "In der Warteschlange: Platz 50, ca. 7 Min." in meldungen
    assert not http.urls("GET", "/generate/status/")
    _warte_aufraeumen(gen)
    assert http.urls("DELETE", "/generate/status/auftrag-0001")


def test_horde_zensiertes_bild():
    http = horde(status=_status(censored=True))
    gen, _m, _u = _gen(http)
    with pytest.raises(bg.GeneratorFehler) as info:
        gen.erstellen("something")
    assert "Sicherheitsfilter" in str(info.value) and info.value.ausweichen is False
    assert not http.urls("GET", "r2.example.com")  # zensiertes Bild gar nicht erst laden


def test_horde_abbruch_beim_warten():
    stopp = threading.Event()
    http = horde(checks=[{"done": False, "waiting": 1, "queue_position": 2, "wait_time": 20}])
    uhr = Uhr()

    def warte(sekunden):
        uhr.warte(sekunden)
        stopp.set()  # Mensch drueckt waehrend der Wartezeit auf Stopp

    gen = bg.Bildgenerator(None, http=http, cancel_event=stopp, uhr=uhr, warten=warte)
    with pytest.raises(Abgebrochen):
        gen.erstellen("a dog")
    _warte_aufraeumen(gen)
    assert http.urls("DELETE", "/generate/status/auftrag-0001")
    assert not http.urls("GET", "/generate/status/")


def test_abbruch_waehrend_haengendem_netzaufruf_wirkt_sofort():
    stopp, freigabe = threading.Event(), threading.Event()
    basis = horde_handler()

    def handler(methode, url, kw):
        if "/generate/check/" in url:
            freigabe.wait(10)  # Verbindung haengt
        return basis(methode, url, kw)

    http = FakeHttp(handler)
    gen = bg.Bildgenerator(None, http=http, cancel_event=stopp)
    threading.Timer(0.3, stopp.set).start()
    beginn = time.monotonic()
    try:
        with pytest.raises(Abgebrochen):
            gen.erstellen("a dog")
        assert time.monotonic() - beginn < 3
    finally:
        freigabe.set()
    _warte_aufraeumen(gen)
    assert http.urls("DELETE", "/generate/status/auftrag-0001")


def test_abbruch_waehrend_auftrag_unterwegs_zieht_spaeter_zurueck():
    stopp, freigabe = threading.Event(), threading.Event()
    basis = horde_handler()

    def handler(methode, url, kw):
        if methode == "POST":
            freigabe.wait(10)  # Antwort auf den Auftrag kommt erst nach dem Stopp
        return basis(methode, url, kw)

    http = FakeHttp(handler)
    gen = bg.Bildgenerator(None, http=http, cancel_event=stopp)
    threading.Timer(0.3, stopp.set).start()
    with pytest.raises(Abgebrochen):
        gen.erstellen("a dog")
    assert not http.urls("DELETE")
    freigabe.set()
    ende = time.monotonic() + 5
    while not http.urls("DELETE") and time.monotonic() < ende:
        time.sleep(0.05)
    assert http.urls("DELETE", "/generate/status/auftrag-0001")
    assert not http.urls("GET", "/generate/check/")


def test_bilder_ordner(tmp_path):
    assert bg.bilder_ordner(tmp_path) == tmp_path / "bilder"
    assert bg.bilder_ordner(str(tmp_path)) == tmp_path / "bilder"


def test_abbruch_schon_vor_dem_start():
    stopp = threading.Event()
    stopp.set()
    http = horde()
    with pytest.raises(Abgebrochen):
        bg.Bildgenerator(None, http=http, cancel_event=stopp).erstellen("a dog")
    assert not http.posts()


def test_horde_check_404_und_netzaussetzer():
    http = horde(checks=[Antwort(404, {"message": "not found"})])
    with pytest.raises(bg.GeneratorFehler, match="abgelaufen"):
        _gen(http)[0].erstellen("a dog")

    http = horde(checks=[ConnectionError("kurz weg"), Antwort(502, None), {"done": True}])
    gen, _m, uhr = _gen(http)
    assert gen.erstellen("a dog").data == WEBP
    assert uhr.pausen == [10.0, 10.0]

    http = horde(checks=[ConnectionError("dauerhaft weg")])
    with pytest.raises(bg.GeneratorFehler, match="Keine Verbindung"):
        _gen(http)[0].erstellen("a dog")
    assert len(http.urls("GET", "/generate/check/")) == 5


class ReadTimeout(Exception):
    pass


@pytest.mark.parametrize("antwort, text, ausweichen", [
    (Antwort(429, {"rc": "TooManyPrompts", "message": "too many"}), "zu viele Auftr", True),
    (Antwort(403, {"rc": "AnonForbidden", "message": "no anon"}), "ohne Anmeldung", True),
    (Antwort(400, {"rc": "CorruptPrompt", "message": "nope"}), "abgelehnt (Sicherheitsfilter)", False),
    (Antwort(503, {"rc": "MaintenanceMode", "message": "maintenance"}), "gewartet", True),
    (Antwort(400, {"rc": "InvalidSize", "message": "bad"}), "Fehler 400, InvalidSize", True),
    (Antwort(202, {"kein": "id"}), "nicht angenommen", True),
    (Antwort(202, {"id": "../../boese"}), "nicht angenommen", True),
    (ConnectionError("weg"), "Keine Verbindung zu AI Horde", True),
    (ReadTimeout("zu langsam"), "antwortet gerade nicht", True),
])
def test_horde_auftrag_fehler(antwort, text, ausweichen):
    http = horde(post=antwort) if isinstance(antwort, Antwort) else FakeHttp(
        lambda m, u, kw: antwort if m == "POST" else horde_handler()(m, u, kw))
    with pytest.raises(bg.GeneratorFehler) as info:
        _gen(http)[0].erstellen("a dog")
    assert text in str(info.value)
    assert info.value.ausweichen is ausweichen
    assert not http.urls(None, "/generate/check/")


def test_horde_bild_nur_ueber_https():
    http = horde(status=_status(img="http://r2.example.com/bild.webp"))
    with pytest.raises(bg.GeneratorFehler, match="unsichere"):
        _gen(http)[0].erstellen("a dog")
    assert not http.urls("GET", "http://r2")

    weiterleitung = Antwort(302, None, headers={"Location": "http://r2.example.com/anders.webp"})
    http = horde(bild_antwort=weiterleitung)
    with pytest.raises(bg.GeneratorFehler, match="unsichere"):
        _gen(http)[0].erstellen("a dog")


def test_horde_bild_weiterleitung_https_erlaubt():
    ziele = []

    def weiter(methode, url, kw):
        ziele.append(url)
        return Antwort(200, content=WEBP)

    basis = horde_handler(bild_antwort=Antwort(302, None, headers={"Location": "https://cdn.example.net/x.webp"}),
                          weiter=weiter)
    erg = _gen(FakeHttp(basis))[0].erstellen("a dog")
    assert erg.data == WEBP and ziele == ["https://cdn.example.net/x.webp"]


def test_horde_bild_groessenbegrenzung(monkeypatch):
    http = horde(bild_antwort=Antwort(200, content=WEBP, headers={"Content-Length": str(10**9)}))
    with pytest.raises(bg.GeneratorFehler, match="zu gro"):
        _gen(http)[0].erstellen("a dog")

    monkeypatch.setattr(bg, "MAX_BILD_BYTES", 100)
    http = horde(bild=WEBP + b"\x00" * 200)  # ohne Content-Length, zu lang beim Lesen
    with pytest.raises(bg.GeneratorFehler, match="zu gro"):
        _gen(http)[0].erstellen("a dog")


@pytest.mark.parametrize("inhalt", [b"<html>Fehler</html>", b"", b"GIF00a" + b"\x00" * 10])
def test_horde_ergebnis_muss_ein_bild_sein(inhalt):
    http = horde(bild=inhalt)
    with pytest.raises(bg.GeneratorFehler, match="kein lesbares Bild"):
        _gen(http)[0].erstellen("a dog")


def test_horde_bild_als_base64_und_leere_antwort():
    http = horde(status=_status(img=base64.b64encode(PNG).decode()))
    erg = _gen(http)[0].erstellen("a dog")
    assert erg.data == PNG and erg.mime == "image/png" and erg.endung == "png"
    assert not http.urls("GET", "r2.example.com")

    http = horde(status=Antwort(200, {"done": True, "generations": []}))
    with pytest.raises(bg.GeneratorFehler, match="kein Bild"):
        _gen(http)[0].erstellen("a dog")


def test_horde_ergebnis_abholen_versucht_es_noch_einmal():
    folge = [ConnectionError("kurz weg"), Antwort(429, {"rc": "TooManyRequests"}), Antwort(200, _status())]
    basis = horde_handler()

    def handler(methode, url, kw):
        if methode == "GET" and "/generate/status/" in url:
            return folge.pop(0)
        return basis(methode, url, kw)

    http = FakeHttp(handler)
    gen, _m, uhr = _gen(http)
    assert gen.erstellen("a dog").data == WEBP
    assert uhr.pausen == [6.0, 6.0] and not folge
    assert not http.urls("DELETE")  # fertige Auftraege werden nicht zurueckgezogen

    http = FakeHttp(lambda m, u, kw: ConnectionError("weg") if "/generate/status/" in u and m == "GET"
                    else horde_handler()(m, u, kw))
    with pytest.raises(bg.GeneratorFehler, match="Keine Verbindung"):
        _gen(http)[0].erstellen("a dog")
    assert len(http.urls("GET", "/generate/status/")) == 3


def test_leere_beschreibung():
    http = horde()
    with pytest.raises(bg.GeneratorFehler, match="leer"):
        _gen(http)[0].erstellen("  \n\t ")
    assert not http.calls


# ----- Cloudflare ---------------------------------------------------------------
def test_cloudflare_erfolg():
    http = cloudflare(_cf_ok())
    gen, meldungen, _u = _gen(http, _config(token=TOKEN, konto=KONTO))
    erg = gen.erstellen("x" * 5000)
    assert erg.data == JPEG and erg.mime == "image/jpeg" and erg.endung == "jpg"
    assert erg.anbieter == "Cloudflare" and erg.hinweis == ""
    ((methode, url, kw),) = http.calls
    assert methode == "POST" and url == CF_URL
    assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kw["timeout"]
    assert kw["json"]["steps"] == 4 and isinstance(kw["json"]["seed"], int)
    assert 0 < len(kw["json"]["prompt"]) <= 2048
    assert set(kw["json"]) == {"prompt", "steps", "seed"}  # keine Groessenangabe (gibt es dort nicht)
    assert any("Cloudflare" in m for m in meldungen)


def test_cloudflare_bild_ohne_result_huelle_und_binaer():
    http = cloudflare(Antwort(200, {"image": base64.b64encode(JPEG).decode()}))
    assert _gen(http, _config(token=TOKEN, konto=KONTO))[0].erstellen("a cat").data == JPEG

    http = cloudflare(Antwort(200, content=PNG, headers={"Content-Type": "image/png"}))
    erg = _gen(http, _config(token=TOKEN, konto=KONTO))[0].erstellen("a cat")
    assert erg.data == PNG and erg.mime == "image/png"


def test_cloudflare_schluessel_ungueltig_ohne_ausweichen():
    http = cloudflare(_cf_fehler(401, 10000, "Authentication error"))
    gen, _m, _u = _gen(http, _config("cloudflare", TOKEN, KONTO))
    with pytest.raises(bg.GeneratorFehler) as info:
        gen.erstellen("a cat")
    assert "ung\u00fcltig" in str(info.value)
    assert TOKEN not in str(info.value)
    assert not http.urls(None, "aihorde")


def test_cloudflare_schluessel_ungueltig_auto_weicht_aus():
    http = cloudflare(_cf_fehler(403))
    gen, meldungen, _u = _gen(http, _config(token=TOKEN, konto=KONTO))
    erg = gen.erstellen("a cat")
    assert erg.anbieter == "AI Horde" and erg.data == WEBP
    assert "ung\u00fcltig" in erg.hinweis and "AI Horde" in erg.hinweis
    assert any("ich nehme AI Horde" in m for m in meldungen)


@pytest.mark.parametrize("antwort", [
    _cf_fehler(429, 4006, "you have used up your daily free allocation of 10,000 neurons"),
    _cf_fehler(400, 4006, "Account limited"),
    _cf_fehler(429),
])
def test_cloudflare_tageslimit_auto_weicht_auf_horde_aus(antwort):
    http = cloudflare(antwort)
    gen, meldungen, _u = _gen(http, _config(token=TOKEN, konto=KONTO))
    erg = gen.erstellen("a cat")
    assert erg.anbieter == "AI Horde"
    assert "Tageslimit" in erg.hinweis and ("Uhr" in erg.hinweis or "Mitternacht" in erg.hinweis)
    assert http.posts("generate/async")


def test_cloudflare_tageslimit_ausdruecklich_cloudflare():
    http = cloudflare(_cf_fehler(429, 4006, "daily free allocation"))
    with pytest.raises(bg.GeneratorFehler, match="Tageslimit"):
        _gen(http, _config("cloudflare", TOKEN, KONTO))[0].erstellen("a cat")
    assert not http.urls(None, "aihorde")


def test_cloudflare_sicherheitsfilter_weicht_nicht_aus():
    http = cloudflare(_cf_fehler(400, 3030, "Input prompt contains NSFW content."))
    with pytest.raises(bg.GeneratorFehler) as info:
        _gen(http, _config(token=TOKEN, konto=KONTO))[0].erstellen("something")
    assert info.value.ausweichen is False and "Sicherheitsfilter" in str(info.value)
    assert not http.urls(None, "aihorde")


@pytest.mark.parametrize("fehler", [ConnectionError("weg"), ReadTimeout("langsam"),
                                    Antwort(500, None), Antwort(404, {"errors": [{"code": 7003}]})])
def test_cloudflare_stoerung_auto_weicht_aus(fehler):
    http = cloudflare(fehler)
    erg = _gen(http, _config(token=TOKEN, konto=KONTO))[0].erstellen("a cat")
    assert erg.anbieter == "AI Horde" and erg.hinweis


def test_cloudflare_falsche_konto_id_wird_nicht_in_die_adresse_gebaut():
    http = cloudflare(_cf_ok())
    with pytest.raises(bg.GeneratorFehler, match="Konto-ID"):
        _gen(http, _config("cloudflare", TOKEN, "../../user/tokens"))[0].erstellen("a cat")
    assert not http.calls
    erg = _gen(http, _config("auto", TOKEN, "../../user/tokens"))[0].erstellen("a cat")
    assert erg.anbieter == "AI Horde" and not http.urls(None, "cloudflare")


def test_cloudflare_gewaehlt_aber_nicht_eingerichtet():
    http = horde()
    erg = _gen(http, _config("cloudflare"))[0].erstellen("a cat")
    assert erg.anbieter == "AI Horde" and "nicht eingerichtet" in erg.hinweis


def test_schluessel_nie_in_meldungen_oder_logs(caplog):
    caplog.set_level(logging.DEBUG)
    texte = []
    for antwort in (_cf_fehler(401, 10000, "Authentication error"), _cf_fehler(429, 4006, "neurons"),
                    ConnectionError(f"Fehler mit {CF_URL}"), Antwort(500, None)):
        http = cloudflare(antwort)
        gen, meldungen, _u = _gen(http, _config("cloudflare", TOKEN, KONTO))
        with pytest.raises(bg.GeneratorFehler) as info:
            gen.erstellen("a cat")
        texte += [str(info.value), *meldungen]
        assert info.value.__cause__ is None or TOKEN not in str(info.value.__cause__)
    texte += [r.getMessage() for r in caplog.records]
    assert texte and not any(TOKEN in t for t in texte)
    assert not any("cf-geheim" in t for t in texte)


def test_reset_zeit_in_ortszeit():
    jetzt = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
    assert bg._reset_text(jetzt, timezone(timedelta(hours=1))) == "ab ca. 1 Uhr nachts"
    assert bg._reset_text(jetzt, timezone(timedelta(hours=2))) == "ab ca. 2 Uhr nachts"
    assert bg._reset_text(jetzt, timezone.utc) == "ab ca. Mitternacht"
    assert bg._reset_text(jetzt, timezone(timedelta(hours=-5))) == "ab ca. 19 Uhr"
    assert bg._reset_text().startswith("ab ca. ")


# ----- Cloudflare-Schluessel pruefen ------------------------------------------------
def test_pruefe_cloudflare():
    ok = FakeHttp(lambda m, u, kw: Antwort(200, {"success": True, "result": {"status": "active"}}))
    assert bg.pruefe_cloudflare(TOKEN, http=ok) == (True, "Der Cloudflare-Schl\u00fcssel funktioniert.")
    ((_m, url, kw),) = ok.calls
    assert url == "https://api.cloudflare.com/client/v4/user/tokens/verify"
    assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}" and kw["timeout"]

    aus = FakeHttp(lambda m, u, kw: Antwort(200, {"success": True, "result": {"status": "disabled"}}))
    gut, text = bg.pruefe_cloudflare(TOKEN, http=aus)
    assert gut is False and "nicht aktiv" in text

    def konto_schluessel(m, u, kw):
        return Antwort(200, {"success": True, "result": {"status": "active"}}) if "/accounts/" in u \
            else Antwort(401, {"success": False, "errors": [{"code": 1000, "message": "Invalid API Token"}]})

    http = FakeHttp(konto_schluessel)
    assert bg.pruefe_cloudflare(TOKEN, KONTO, http=http)[0] is True
    assert http.urls()[-1] == f"https://api.cloudflare.com/client/v4/accounts/{KONTO}/tokens/verify"

    nein = FakeHttp(lambda m, u, kw: Antwort(401, {"success": False}))
    gut, text = bg.pruefe_cloudflare(TOKEN, KONTO, http=nein)
    assert gut is False and "ung\u00fcltig" in text and TOKEN not in text and len(nein.calls) == 2

    weg = FakeHttp(lambda m, u, kw: ConnectionError(f"kaputt {TOKEN}"))
    gut, text = bg.pruefe_cloudflare(TOKEN, http=weg)
    assert gut is False and "Keine Verbindung" in text and TOKEN not in text

    leer = FakeHttp(lambda m, u, kw: Antwort(200, {}))
    assert bg.pruefe_cloudflare("  ", http=leer)[0] is False
    assert bg.pruefe_cloudflare(TOKEN, "kein-konto", http=leer)[0] is False
    assert not leer.calls


# ----- Namen ------------------------------------------------------------------
def test_kurzname_und_dateistamm():
    assert bg.kurzname("A red cat on a roof") == "red-cat-roof"
    assert bg.kurzname("Gr\u00fc\u00dfe aus M\u00fcnchen!") == "gruesse-aus-muenchen"
    assert bg.kurzname("Caf\u00e9 cr\u00e8me") == "cafe-creme"
    assert bg.kurzname("") == "bild" and bg.kurzname("!!! ???") == "bild"
    assert bg.kurzname("../../etc/passwd") == "etc-passwd"
    assert len(bg.kurzname("supercalifragilistic " * 10)) <= 40
    assert len(bg.kurzname("x" * 80)) == 40
    stamm = bg.dateistamm("A cat", datetime(2026, 11, 8, 15, 30, 5))
    assert stamm == "20261108-153005_cat"
    for endung in ("webp", "jpg", "png"):
        assert bg.DATEINAME_MUSTER.match(f"{stamm}.{endung}")
    assert bg.DATEINAME_MUSTER.match(bg.dateistamm("\u2603 \u00e4\u00f6\u00fc / \\ : * ?") + ".webp")


def test_bereinige():
    assert bg.bereinige("  a\tb\n\nc\x00d  ") == "a b c d"
    assert bg.bereinige(None) == ""
    assert len(bg.bereinige("x" * 9000)) == bg.MAX_BESCHREIBUNG


# ----- Werkzeug bild_erstellen ----------------------------------------------------------
def _ctx(root, *, auto_confirm=True, confirm=True, config=None, extra=None, fragen=None):
    def confirm_fn(text, risk):
        if fragen is not None:
            fragen.append(text)
        return confirm

    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=auto_confirm), root,
                           confirm_fn=confirm_fn)
    ex = {"config": config if config is not None else _config()}
    ex.update(extra or {})
    return ToolContext(permissions=pm, memory=None, extra=ex), pm


@pytest.fixture
def netz(monkeypatch):
    """Ersetzt das echte Netz fuer das Werkzeug: netz(http) setzt die Attrappe."""
    def setzen(http):
        monkeypatch.setattr(bg, "_standard_http", lambda: http)
        return http

    setzen(FakeHttp(lambda m, u, kw: AssertionError(f"kein Netz erwartet: {m} {u}")))
    return setzen


def test_werkzeug_spec():
    reg = build_registry()
    tool = reg.get("bild_erstellen")
    assert tool is not None and "bild_erstellen" in reg.names()
    assert "bild_erstellen" not in READ_ONLY_TOOLS
    spec = tool.spec()
    assert spec["strict"] is True
    schema = spec["input_schema"]
    assert schema["required"] == ["beschreibung"] and schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"beschreibung", "format"}
    assert schema["properties"]["format"]["enum"] == ["quadrat", "hoch", "quer"]
    assert "ENGLISCH" in spec["description"] and "echten" in spec["description"]
    openai = tool.spec_openai()["function"]
    assert openai["name"] == "bild_erstellen" and openai["parameters"]["properties"] == schema["properties"]


def test_werkzeug_speichert_im_arbeitsordner(tmp_path, netz):
    http = netz(horde())
    bilder, fortschritt = [], []
    ctx, pm = _ctx(tmp_path, extra={"on_image": bilder.append, "on_image_progress": fortschritt.append})
    out, err = build_registry().execute(ctx, "bild_erstellen",
                                        {"beschreibung": "A red cat on a roof", "format": "quer"})
    assert not err, out
    assert out.startswith("Bild gespeichert: bilder/")
    assert "(AI Horde, Modell Flux.1-Schnell fp8 (Compact))" in out
    assert "Voller Pfad" not in out and len(out) < 600
    assert base64.b64encode(WEBP).decode()[:16] not in out

    (datei,) = list((pm.workspace_root / "bilder").iterdir())
    assert datei.suffix == ".webp" and datei.read_bytes() == WEBP
    assert bg.DATEINAME_MUSTER.match(datei.name) and datei.stem.endswith("_red-cat-roof")
    assert f"bilder/{datei.name}" in out

    (ereignis,) = bilder
    assert set(ereignis) == {"pfad", "name", "prompt", "anbieter"}
    assert isinstance(ereignis["pfad"], Path) and ereignis["pfad"] == datei
    assert ereignis["name"] == datei.name
    assert ereignis["prompt"] == "A red cat on a roof" and ereignis["anbieter"] == "AI Horde"
    assert fortschritt and all(isinstance(t, str) for t in fortschritt)

    params = http.posts("generate/async")[0]["json"]["params"]
    assert (params["width"], params["height"]) == (1152, 768)


def test_werkzeug_im_terminal_ohne_rueckruf_nennt_den_pfad(tmp_path, netz):
    netz(horde())
    ctx, pm = _ctx(tmp_path)
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not err
    (datei,) = list((pm.workspace_root / "bilder").iterdir())
    assert f"Voller Pfad: {datei}" in out


def test_werkzeug_im_afk_modus_abgelehnt(tmp_path, netz):
    http = netz(horde())
    ctx, pm = _ctx(tmp_path)
    pm.begin_away()
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not err and "nur, wenn dein Mensch da ist" in out and "vorschlag" in out
    assert not http.calls
    assert not (pm.workspace_root / "bilder").exists()


def test_werkzeug_fragt_vor_dem_senden_und_respektiert_nein(tmp_path, netz):
    http = netz(horde())
    fragen = []
    ctx, pm = _ctx(tmp_path, auto_confirm=False, confirm=False, fragen=fragen)
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a secret garden"})
    assert err and "abgelehnt" in out.lower()
    assert not http.calls  # nichts hat den PC verlassen
    (frage,) = fragen
    assert "AI Horde" in frage and "a secret garden" in frage and "Datei:" in frage
    assert str(pm.workspace_root / "bilder") in frage
    assert not list(pm.workspace_root.glob("bilder/*"))


def test_werkzeug_fragt_einmal_und_malt_dann(tmp_path, netz):
    http = netz(horde())
    fragen = []
    ctx, _pm = _ctx(tmp_path, auto_confirm=False, confirm=True, fragen=fragen)
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not err and out.startswith("Bild gespeichert") and len(fragen) == 1
    assert http.posts("generate/async")


def test_werkzeug_nennt_cloudflare_in_der_frage(tmp_path, netz):
    netz(cloudflare(_cf_ok()))
    fragen, bilder = [], []
    ctx, pm = _ctx(tmp_path, auto_confirm=False, fragen=fragen, config=_config(token=TOKEN, konto=KONTO),
                   extra={"on_image": bilder.append})
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not err and "(Cloudflare, Modell" in out
    assert "Cloudflare" in fragen[0] and TOKEN not in fragen[0]
    (datei,) = list((pm.workspace_root / "bilder").iterdir())
    assert datei.suffix == ".jpg" and bilder[0]["anbieter"] == "Cloudflare"


def test_werkzeug_ausweichen_steht_im_text(tmp_path, netz):
    netz(cloudflare(_cf_fehler(429, 4006, "daily free allocation")))
    bilder = []
    ctx, _pm = _ctx(tmp_path, config=_config(token=TOKEN, konto=KONTO), extra={"on_image": bilder.append})
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not err and "(AI Horde," in out and "Hinweis:" in out and "Tageslimit" in out
    assert bilder[0]["anbieter"] == "AI Horde"


def test_werkzeug_generatorfehler(tmp_path, netz):
    netz(horde(post=Antwort(503, {"rc": "MaintenanceMode"})))
    bilder = []
    ctx, pm = _ctx(tmp_path, extra={"on_image": bilder.append})
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert out.startswith("Kein Bild erstellt:") and "gewartet" in out
    assert not bilder and not list(pm.workspace_root.glob("bilder/*"))


@pytest.mark.parametrize("eingabe, text", [
    ({"beschreibung": "a dog", "format": "rund"}, "Unbekanntes format"),
    ({"beschreibung": "   "}, "beschreibe das Bild"),
])
def test_werkzeug_eingaben_pruefen(tmp_path, netz, eingabe, text):
    http = netz(horde())
    ctx, _pm = _ctx(tmp_path)
    out, err = build_registry().execute(ctx, "bild_erstellen", eingabe)
    assert text in out and not http.calls


def test_werkzeug_format_synonym(tmp_path, netz):
    http = netz(horde())
    ctx, _pm = _ctx(tmp_path)
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog", "format": "Portrait"})
    assert not err
    params = http.posts("generate/async")[0]["json"]["params"]
    assert (params["width"], params["height"]) == (768, 1152)


def test_werkzeug_stopp_knopf(tmp_path, netz):
    http = netz(horde())
    stopp = threading.Event()
    stopp.set()
    ctx, pm = _ctx(tmp_path, extra={"cancel_event": stopp})
    with pytest.raises(Abgebrochen):  # wie Strg+C: rutscht durch die Fehlerbehandlung
        build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert not http.posts() and not list(pm.workspace_root.glob("bilder/*"))


def test_werkzeug_ueberschreibt_nichts(tmp_path, netz, monkeypatch):
    netz(horde())
    monkeypatch.setattr(bg, "dateistamm", lambda beschreibung, jetzt=None: "20261108-153000_dog")
    ctx, pm = _ctx(tmp_path)
    ordner = pm.workspace_root / "bilder"
    ordner.mkdir()
    (ordner / "20261108-153000_dog.png").write_bytes(b"alt")
    reg = build_registry()
    for _ in range(2):
        out, err = reg.execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
        assert not err
    namen = sorted(p.name for p in ordner.iterdir())
    assert namen == ["20261108-153000_dog-2.webp", "20261108-153000_dog-3.webp", "20261108-153000_dog.png"]
    assert (ordner / "20261108-153000_dog.png").read_bytes() == b"alt"


def test_werkzeug_rueckruf_fehler_stoeren_nicht(tmp_path, netz, monkeypatch):
    netz(horde(checks=[{"done": False, "queue_position": 1, "wait_time": 4}, {"done": True}]))
    pausen = []
    monkeypatch.setattr(bg.Bildgenerator, "_warte", lambda self, s: pausen.append(s))  # nicht wirklich warten

    def kaputt(*_a):
        raise RuntimeError("Oberflaeche weg")

    ctx, pm = _ctx(tmp_path, extra={"on_image": kaputt, "on_image_progress": kaputt})
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert pausen == [2.0]
    assert not err and out.startswith("Bild gespeichert")
    assert len(list((pm.workspace_root / "bilder").iterdir())) == 1


def test_werkzeug_bleibt_in_der_sandbox(tmp_path, netz):
    http = netz(horde())
    arbeit = tmp_path / "arbeit"
    aussen = tmp_path / "aussen"
    arbeit.mkdir()
    aussen.mkdir()
    try:
        (arbeit / "bilder").symlink_to(aussen, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks gehen hier nicht")
    ctx, _pm = _ctx(arbeit)
    out, err = build_registry().execute(ctx, "bild_erstellen", {"beschreibung": "a dog"})
    assert err and "Arbeitsordner" in out
    assert not http.calls and not list(aussen.iterdir())
