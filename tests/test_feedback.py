"""Feedback & Bewertung: Ziel-URL, Nachricht, Senden, Ausgang, Grenzen und Nachfrage-Plan.

Alles ohne Netz: `post` und `fetch` sind Fakes.
"""
import base64
import io
import json
import logging
import os
import platform
import re
import struct
import threading
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant import __version__, feedback
from assistant.bilder import Bild, BildFehler
from assistant.config import FeedbackSettings, UpdateSettings

URL = "https://script.google.com/macros/s/AKfycbTestDeployment_123-abc/exec"
URL2 = "https://script.google.com/macros/s/AKfycbZweiteBereitstellung_9/exec"
RAW = "https://raw.githubusercontent.com/GermanClaude/Selbst-lernende-KI/HEAD/feedback-endpoint.txt"
JETZT = datetime(2026, 11, 8, 12, 0, 0)


# -- Hilfen -------------------------------------------------------------------------
def _png(breite=2, hoehe=2):
    """Kleines, gueltiges PNG ohne Pillow."""
    def chunk(art, daten):
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten))
    zeilen = b"".join(b"\x00" + b"\xff\x00\x00" * breite for _ in range(hoehe))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(zeilen)) + chunk(b"IEND", b""))


def _cfg(root, **fb):
    return SimpleNamespace(project_root=Path(root), feedback=FeedbackSettings(**fb), update=UpdateSettings(),
                           active_provider="claude", active_model="claude-opus-5-5")


class Antwort:
    def __init__(self, status=200, text='{"ok": true}'):
        self.status_code = status
        self.text = text
        self.closed = False

    def close(self):
        self.closed = True


def ok():
    return Antwort(200, '{"ok": true}')


def fehler(code):
    return Antwort(200, json.dumps({"ok": False, "fehler": code}))


class FakePost:
    """Gibt der Reihe nach die vorbereiteten Antworten zurueck (Exceptions werden geworfen)."""
    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        antwort = self.antworten.pop(0) if len(self.antworten) > 1 else self.antworten[0]
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort() if callable(antwort) else antwort


class Offline(ConnectionError):
    def __init__(self):
        super().__init__(f"HTTPSConnectionPool(host='script.google.com'): Max retries exceeded with url: {URL}")


class HttpFehler(Exception):
    def __init__(self, code):
        super().__init__(f"{code} Client Error for url: {RAW}")
        self.response = SimpleNamespace(status_code=code)


class FakeFetch:
    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.calls = []

    def __call__(self, url, timeout=15):
        self.calls.append((url, timeout))
        antwort = self.antworten.pop(0) if len(self.antworten) > 1 else self.antworten[0]
        if isinstance(antwort, BaseException):
            raise antwort
        return antwort.encode("utf-8") if isinstance(antwort, str) else antwort


def _payload(text="Hallo"):
    return feedback.baue_payload("feedback", 5, text, "", None, "menue", None)


def _ausgang(root):
    return sorted(feedback.ausgang_ordner(root).glob("*.json"))


def _stand(root):
    return json.loads((Path(root) / "data" / "feedback_state.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _sauber(monkeypatch, tmp_path):
    # Eingebaute URL leer (wie ausgeliefert) und nie in den echten data/-Ordner schreiben.
    monkeypatch.setattr(feedback, "FEEDBACK_URL", "")
    monkeypatch.setattr(feedback, "PROJECT_ROOT", tmp_path / "standard")


# -- Ziel-URL -----------------------------------------------------------------------
def test_nur_echte_apps_skript_urls_gelten():
    assert feedback.gueltige_url(URL) and feedback.gueltige_url(URL2)
    for falsch in [None, 42, "", "http://script.google.com/macros/s/AKfycbTestDeployment/exec",
                   "https://script.google.com.boese.example/macros/s/AKfycbTestDeployment/exec",
                   "https://script.google.com/macros/s/kurz/exec",
                   URL + "\n", URL + "?x=1", URL.replace("/exec", "/dev"), " " + URL,
                   "https://script.google.com/macros/s/AKfycb Test Leer/exec",
                   "https://script.google.com/macros/s/" + "a" * 300 + "/exec"]:
        assert not feedback.gueltige_url(falsch), falsch


def test_eigene_adresse_geht_vor_ungueltige_wird_ignoriert(tmp_path, monkeypatch):
    fetch = FakeFetch(URL2)
    assert feedback.ziel_url(_cfg(tmp_path, adresse=" " + URL + " "), fetch=fetch) == URL
    monkeypatch.setattr(feedback, "FEEDBACK_URL", URL2)
    assert feedback.ziel_url(_cfg(tmp_path, adresse="https://boese.example/exec"), fetch=fetch) == URL2
    assert feedback.ziel_url(_cfg(tmp_path), fetch=fetch) == URL2  # eingebaut vor Fern-Datei
    assert fetch.calls == []


def test_fern_datei_vom_standard_branch_wird_24_stunden_gemerkt(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch("\ufeff# Nova-Feedback-Postfach\n\n" + URL + "\n", URL2)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) == URL
    assert fetch.calls == [(RAW, feedback.FERN_TIMEOUT)]
    assert _stand(tmp_path)["fern"]["url"] == URL
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=23, minutes=59)) == URL
    assert len(fetch.calls) == 1  # aus dem Zwischenspeicher
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=24)) == URL2
    assert len(fetch.calls) == 2
    assert feedback.ist_eingerichtet(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=25))


def test_fern_datei_nimmt_repo_und_branch_wie_der_updater(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.update.repo, cfg.update.branch = "Jemand/Fork", "test/neu"
    fetch = FakeFetch(URL, URL2)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) == URL
    assert fetch.calls[0][0] == "https://raw.githubusercontent.com/Jemand/Fork/test/neu/feedback-endpoint.txt"
    cfg.update.branch = ""  # anderer Branch -> Zwischenspeicher gilt nicht mehr
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) == URL2
    assert fetch.calls[1][0] == "https://raw.githubusercontent.com/Jemand/Fork/HEAD/feedback-endpoint.txt"
    for unsinn in ["", "kein-repo", "../../boese/x", "a/b/c"]:
        cfg.update.repo = unsinn
        assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) is None
    assert len(fetch.calls) == 2


def test_ungueltige_fern_datei_zaehlt_als_nicht_eingerichtet(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch("https://boese.example/macros/s/AKfycbTestDeployment/exec\n" + URL)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) is None  # nur die erste Zeile zaehlt
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=5)) is None
    assert len(fetch.calls) == 1
    assert not feedback.ist_eingerichtet(cfg, fetch=fetch, jetzt=JETZT)


def test_fehlende_fern_datei_wird_auch_einen_tag_gemerkt(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch(HttpFehler(404), URL)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) is None
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=23)) is None
    assert len(fetch.calls) == 1
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(hours=24)) == URL


def test_offline_alter_stand_bleibt_und_neuer_versuch_erst_nach_einer_stunde(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch(URL, Offline(), HttpFehler(500), URL2)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) == URL
    spaeter = JETZT + timedelta(hours=25)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=spaeter) == URL  # veraltet, aber besser als nichts
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=spaeter + timedelta(minutes=59)) == URL
    assert len(fetch.calls) == 2
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=spaeter + timedelta(hours=1)) == URL  # 500
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=spaeter + timedelta(hours=2)) == URL2
    assert len(fetch.calls) == 4


def test_offline_ohne_alten_stand_heisst_nicht_eingerichtet(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch(Offline())
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT) is None
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(minutes=30)) is None
    assert len(fetch.calls) == 1


def test_ohne_netz_nur_der_zwischenspeicher(tmp_path):
    cfg = _cfg(tmp_path)
    fetch = FakeFetch(URL)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT, netz=False) is None
    assert fetch.calls == []
    feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT)
    assert feedback.ziel_url(cfg, fetch=fetch, jetzt=JETZT + timedelta(days=9), netz=False) == URL
    assert len(fetch.calls) == 1


def test_kaputter_zwischenspeicher_stoert_nicht(tmp_path):
    (tmp_path / "data").mkdir()
    for kaputt in ["{nicht json", "[1, 2]", '{"fern": "quatsch"}',
                   '{"fern": {"quelle": "%s", "url": "https://boese.example", "geprueft": "gestern", "ok": true}}'
                   % RAW]:
        (tmp_path / "data" / "feedback_state.json").write_text(kaputt, encoding="utf-8")
        fetch = FakeFetch(URL)
        assert feedback.ziel_url(_cfg(tmp_path), fetch=fetch, jetzt=JETZT) == URL
        assert len(fetch.calls) == 1


def test_standard_abruf_ist_der_des_updaters(tmp_path, monkeypatch):
    calls = []

    def fake_http_get(url, timeout=15):
        calls.append((url, timeout))
        return URL.encode()

    monkeypatch.setattr("assistant.updater._http_get", fake_http_get)
    assert feedback.ziel_url(_cfg(tmp_path), jetzt=JETZT) == URL
    assert calls == [(RAW, feedback.FERN_TIMEOUT)]


# -- Nachricht ----------------------------------------------------------------------
def test_payload_hat_genau_die_vereinbarten_felder():
    cfg = SimpleNamespace(active_provider="deepseek", active_model="deepseek-flash")
    p = feedback.baue_payload("bug", 2, "  Der Knopf geht nicht.  ", " ich bei beispiel ", None, "popup", cfg)
    assert p == {
        "app": "Nova", "v": 1, "version": __version__, "kind": "bug", "stars": 2,
        "text": "Der Knopf geht nicht.", "contact": "ich bei beispiel", "os": platform.platform(),
        "brain": "deepseek/deepseek-flash", "trigger": "popup", "website": "", "images": [],
    }
    assert feedback.baue_payload("idee", None, "x", None, [], "menue", None)["brain"] == "?"


@pytest.mark.parametrize("kind, erwartet", [
    ("bewertung", "bewertung"), ("Lob", "bewertung"), ("fehler", "bug"), ("BUG", "bug"),
    ("idee", "idee"), ("Vorschlag", "idee"), ("sonstiges", "feedback"), ("", "feedback"),
    (None, "feedback"), ("<script>", "feedback"),
])
def test_art_wird_vereinheitlicht(kind, erwartet):
    assert feedback.baue_payload(kind, 3, "", "", None, "menue", None)["kind"] == erwartet


@pytest.mark.parametrize("stars, erwartet", [
    (1, 1), (5, 5), ("4", 4), (4.6, 5), (0, None), (6, None), (-1, None), (True, None),
    ("viele", None), (None, None), (float("nan"), None), ("", None),
])
def test_sterne_nur_1_bis_5(stars, erwartet):
    assert feedback.baue_payload("bewertung", stars, "Text", "", None, "menue", None)["stars"] == erwartet


def test_text_kontakt_und_ausloeser_werden_begrenzt():
    p = feedback.baue_payload("feedback", None, "a\x00b" + "x" * 30000, "Zeile1\nZeile2\t" + "k" * 500,
                              None, "Pop-up", None)
    assert p["text"].startswith("abx") and len(p["text"]) == feedback.MAX_TEXT
    assert "\n" not in p["contact"] and p["contact"].startswith("Zeile1 Zeile2 ")
    assert len(p["contact"]) == feedback.MAX_KONTAKT
    assert p["trigger"] == "popup"
    assert feedback.baue_payload("feedback", 1, "", "", None, "irgendwas", None)["trigger"] == "menue"
    assert feedback.baue_payload("feedback", 1, "", "", None, "men\u00fc", None)["trigger"] == "menue"
    assert feedback.baue_payload("feedback", 1, "Zeile 1\nZeile 2", "", None, None, None)["text"] == "Zeile 1\nZeile 2"


def test_leeres_feedback_wird_abgelehnt():
    with pytest.raises(feedback.FeedbackFehler):
        feedback.baue_payload("feedback", None, "   ", "x", [], "menue", None)
    assert feedback.baue_payload("bewertung", 4, "", "", None, "popup", None)["stars"] == 4
    assert len(feedback.baue_payload("bug", None, "", "", [_png()], "menue", None)["images"]) == 1


def test_bilder_aus_allen_quellen(tmp_path):
    datei = tmp_path / "fehler bild.png"
    datei.write_bytes(_png(3, 3))
    b64 = base64.b64encode(_png()).decode()
    eingang = [
        {"name": "eingefuegt.png", "data": "data:image/png;base64," + b64},  # aus der App
        {"name": "roh.png", "data": b64},                                    # ohne data:-Vorsatz
        Bild("schon.png", "image/png", _png()),
        _png(),
        datei,
    ]
    p = feedback.baue_payload("bug", None, "", "", eingang, "menue", None)
    assert [b["name"] for b in p["images"]] == ["eingefuegt.png", "roh.png", "schon.png", "bild4.png",
                                               "fehler bild.png"]
    for bild in p["images"]:
        assert bild["mime"] == "image/png"
        assert base64.b64decode(bild["data"]).startswith(b"\x89PNG")
        assert set(bild) == {"name", "mime", "data"}
    pfad_als_text = feedback.baue_payload("bug", None, "", "", [f'"{datei}"'], "menue", None)
    assert pfad_als_text["images"][0]["name"] == "fehler bild.png"


def test_hoechstens_fuenf_bilder():
    with pytest.raises(BildFehler, match="5 Bilder"):
        feedback.baue_payload("bug", None, "x", "", [_png()] * 6, "menue", None)


def test_bilder_zusammen_hoechstens_10_mb(monkeypatch):
    assert feedback.MAX_BILDER_BYTES == 10 * 1024 * 1024
    monkeypatch.setattr(feedback, "MAX_BILDER_BYTES", len(_png()) * 2 - 1)
    feedback.baue_payload("bug", None, "x", "", [_png()], "menue", None)
    with pytest.raises(BildFehler) as info:
        feedback.baue_payload("bug", None, "x", "", [_png(), _png()], "menue", None)
    assert str(info.value) == feedback.MELDUNGEN["zu_gross"]


@pytest.mark.parametrize("schlecht", [
    b"<svg xmlns='http://www.w3.org/2000/svg'/>", {"name": "x.png", "data": "data:text/html;base64,PGI+"},
    {"name": "x.png", "data": ""}, {"name": "x.png"}, 12, "/gibt/es/nicht.png", "x" * 5000,
])
def test_kaputte_bilder_geben_bildfehler(schlecht):
    with pytest.raises(BildFehler):
        feedback.baue_payload("bug", None, "x", "", [schlecht], "menue", None)
    with pytest.raises(BildFehler):
        feedback.baue_payload("bug", None, "x", "", "kein-listen-objekt" if schlecht == 12 else 3.5,
                              "menue", None)


def test_grosse_bilder_werden_auf_1920_pixel_verkleinert():
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", (4000, 2000), (10, 120, 200)).save(puffer, "JPEG")
    p = feedback.baue_payload("bug", None, "", "", [puffer.getvalue()], "menue", None)
    klein = Image.open(io.BytesIO(base64.b64decode(p["images"][0]["data"])))
    assert klein.size == (1920, 960)


# -- Senden -------------------------------------------------------------------------
def test_erfolg_nur_mit_http_200_json_und_ok_true(tmp_path):
    post = FakePost(ok())
    payload = _payload("Sch\u00f6n \u00fcbersichtlich \u2013 danke!")
    erg = feedback.senden(payload, URL, post, root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund, erg.meldung) == ("gesendet", "ok", "Danke! Dein Feedback wurde gesendet.")
    assert erg.als_antwort() == {"ok": True, "status": "gesendet", "message": erg.meldung}
    assert len(post.calls) == 1
    url, kwargs = post.calls[0]
    assert url == URL
    assert kwargs["timeout"] == (10, 90)
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert "allow_redirects" not in kwargs  # Weiterleitungen folgen (Standard), POST -> GET
    assert isinstance(kwargs["data"], bytes) and max(kwargs["data"]) < 128  # ensure_ascii
    assert b"\\u00f6" in kwargs["data"]
    assert json.loads(kwargs["data"]) == payload
    assert _ausgang(tmp_path) == []


@pytest.mark.parametrize("antwort", [
    Antwort(200, '{"ok": "true"}'), Antwort(200, '{"ok": 1}'), Antwort(200, "[true]"),
    Antwort(200, '{"ergebnis": "ok"}'), Antwort(201, '{"ok": true}'), Antwort(302, ""),
])
def test_nichts_anderes_zaehlt_als_erfolg(tmp_path, antwort):
    erg = feedback.senden(_payload(), URL, FakePost(antwort), root=tmp_path, jetzt=JETZT)
    assert erg.status == "gespeichert" and len(_ausgang(tmp_path)) == 1


def test_html_antwort_kommt_in_den_ausgang(tmp_path):
    html = Antwort(200, "<!DOCTYPE html><html><body>Anmelden - Google Konten</body></html>")
    payload = _payload()
    erg = feedback.senden(payload, URL, FakePost(html), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "offline")
    assert erg.meldung.startswith("Keine Verbindung. Dein Feedback ist gespeichert")
    assert erg.als_antwort() == {"ok": True, "status": "gespeichert", "message": erg.meldung}
    (datei,) = _ausgang(tmp_path)
    assert erg.datei == datei and re.fullmatch(r"20261108-120000_[0-9a-f]{8}\.json", datei.name)
    eintrag = json.loads(datei.read_text(encoding="utf-8"))
    assert eintrag["payload"] == payload and eintrag["erstellt"] == "2026-11-08T12:00:00"
    assert html.closed


def test_405_wird_spaeter_nochmal_versucht(tmp_path):
    erg = feedback.senden(_payload(), URL, FakePost(Antwort(405, "Method Not Allowed")), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "fehler")
    assert "sp\u00e4ter automatisch" in erg.meldung and len(_ausgang(tmp_path)) == 1


@pytest.mark.parametrize("antwort", [Antwort(500, "Fehler"), Antwort(503, ""), Offline(), TimeoutError("timed out")])
def test_offline_timeout_und_5xx(tmp_path, antwort):
    erg = feedback.senden(_payload(), URL, FakePost(antwort), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "offline")
    assert erg.meldung == feedback.MELDUNGEN["offline"]
    assert "online" in erg.meldung and len(_ausgang(tmp_path)) == 1


def test_echter_requests_timeout(tmp_path, monkeypatch):
    requests = pytest.importorskip("requests")
    calls = []

    def langsam(url, **kwargs):
        calls.append(kwargs)
        raise requests.exceptions.ReadTimeout(f"Read timed out. (url: {url})")

    monkeypatch.setattr(requests, "post", langsam)  # Standard-post = requests.post
    erg = feedback.senden(_payload(), URL, root=tmp_path, jetzt=JETZT)
    assert erg.grund == "offline" and calls and calls[0]["timeout"] == (10, 90)


@pytest.mark.parametrize("antwort", [fehler("zu_gross"), Antwort(413, "Request Entity Too Large")])
def test_zu_gross_wird_abgelehnt_und_nicht_gespeichert(tmp_path, antwort):
    erg = feedback.senden(_payload(), URL, FakePost(antwort), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("abgelehnt", "zu_gross")
    assert "zu gro\u00df" in erg.meldung and "entferne ein Bild" in erg.meldung
    assert erg.als_antwort() == {"ok": False, "status": "abgelehnt", "error": erg.meldung}
    assert _ausgang(tmp_path) == []


@pytest.mark.parametrize("antwort", [fehler("limit"), Antwort(429, "Too Many Requests")])
def test_limit_des_postfachs_kommt_in_den_ausgang(tmp_path, antwort):
    erg = feedback.senden(_payload(), URL, FakePost(antwort), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "limit")
    assert erg.meldung.startswith("Gerade kommen sehr viele R\u00fcckmeldungen an.")
    assert len(_ausgang(tmp_path)) == 1


@pytest.mark.parametrize("antwort", [fehler("server"), fehler("ungueltig"), Antwort(200, '{"ok": false}')])
def test_andere_fehler_des_postfachs_kommen_in_den_ausgang(tmp_path, antwort):
    erg = feedback.senden(_payload(), URL, FakePost(antwort), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "fehler")


@pytest.mark.parametrize("url", [None, "", "https://boese.example/macros/s/AKfycbTestDeployment/exec"])
def test_ohne_postfach_wird_nur_gespeichert(tmp_path, url):
    post = FakePost(ok())
    erg = feedback.senden(_payload(), url, post, root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "keine_url")
    assert erg.meldung == ("Dein Feedback ist gespeichert und wird gesendet, sobald das "
                           "Feedback-Postfach eingerichtet ist.")
    assert post.calls == [] and len(_ausgang(tmp_path)) == 1


def test_ohne_root_landet_alles_im_programmordner(tmp_path):
    feedback.senden(_payload(), None, root=None, jetzt=JETZT)
    assert len(_ausgang(tmp_path / "standard")) == 1


def test_speichern_unmoeglich_wird_ehrlich_gemeldet(tmp_path, monkeypatch):
    def kaputt(*a, **k):
        raise OSError("Datentraeger voll")

    monkeypatch.setattr(feedback, "_in_ausgang_legen", kaputt)
    erg = feedback.senden(_payload(), URL, FakePost(Offline()), root=tmp_path, jetzt=JETZT)
    assert (erg.status, erg.grund) == ("abgelehnt", "speicher")
    assert erg.als_antwort()["ok"] is False


# -- Grenzen ------------------------------------------------------------------------
def test_hoechstens_drei_sendungen_pro_stunde(tmp_path):
    post = FakePost(ok())
    for minuten in (0, 10, 20):
        assert feedback.senden(_payload(), URL, post, root=tmp_path,
                               jetzt=JETZT + timedelta(minutes=minuten)).status == "gesendet"
    erg = feedback.senden(_payload(), URL, post, root=tmp_path, jetzt=JETZT + timedelta(minutes=59))
    assert (erg.status, erg.grund) == ("gespeichert", "grenze") and len(post.calls) == 3
    assert "sp\u00e4ter automatisch gesendet" in erg.meldung
    assert feedback.grenze_erreicht(tmp_path, JETZT + timedelta(minutes=59))
    assert not feedback.grenze_erreicht(tmp_path, JETZT + timedelta(minutes=61))
    assert feedback.senden(_payload(), URL, post, root=tmp_path,
                           jetzt=JETZT + timedelta(minutes=61)).status == "gesendet"


def test_hoechstens_zehn_sendungen_pro_tag(tmp_path):
    post = FakePost(ok())
    for stunde in range(0, 20, 2):
        assert feedback.senden(_payload(), URL, post, root=tmp_path,
                               jetzt=JETZT + timedelta(hours=stunde)).status == "gesendet"
    assert feedback.senden(_payload(), URL, post, root=tmp_path,
                           jetzt=JETZT + timedelta(hours=23, minutes=59)).grund == "grenze"
    assert len(post.calls) == 10
    assert feedback.senden(_payload(), URL, post, root=tmp_path,
                           jetzt=JETZT + timedelta(hours=24, seconds=1)).status == "gesendet"
    assert len(_stand(tmp_path)["sendungen"]) == 10  # alte Zeitstempel werden aufgeraeumt


def test_verbindungsfehler_zaehlen_nicht_beantwortete_fehler_schon(tmp_path):
    for _ in range(5):
        feedback.senden(_payload(), URL, FakePost(Offline()), root=tmp_path, jetzt=JETZT)
    assert not feedback.grenze_erreicht(tmp_path, JETZT)
    for _ in range(3):
        feedback.senden(_payload(), URL, FakePost(fehler("server")), root=tmp_path, jetzt=JETZT)
    assert feedback.grenze_erreicht(tmp_path, JETZT)


def test_zeitstempel_aus_der_zukunft_sperren_nicht(tmp_path):
    (tmp_path / "data").mkdir()
    zukunft = [(JETZT + timedelta(days=3)).isoformat()] * 20 + ["kaputt", 7, None]
    (tmp_path / "data" / "feedback_state.json").write_text(json.dumps({"sendungen": zukunft}))
    assert not feedback.grenze_erreicht(tmp_path, JETZT)
    assert feedback.senden(_payload(), URL, FakePost(ok()), root=tmp_path, jetzt=JETZT).status == "gesendet"


# -- Ausgang ------------------------------------------------------------------------
def _in_ausgang(root, anzahl, jetzt=JETZT):
    for i in range(anzahl):
        feedback.senden(_payload(f"Nachricht {i}"), None, root=root, jetzt=jetzt + timedelta(seconds=i))
    return _ausgang(root)


def test_ausgang_wird_nachgesendet(tmp_path):
    cfg = _cfg(tmp_path, adresse=URL)
    _in_ausgang(tmp_path, 2)
    post = FakePost(ok())
    assert feedback.ausgang_senden(cfg, post, jetzt=JETZT + timedelta(minutes=30)) == {
        "gesendet": 2, "geloescht": 0, "offen": 0, "uebersprungen": False}
    texte = [json.loads(k["data"])["text"] for _, k in post.calls]
    assert texte == ["Nachricht 0", "Nachricht 1"]  # aelteste zuerst
    assert feedback.ausgang_anzahl(tmp_path) == 0


def test_ausgang_raeumt_alte_kaputte_und_fremde_dateien_auf(tmp_path):
    cfg = _cfg(tmp_path, adresse=URL)
    _in_ausgang(tmp_path, 1, jetzt=JETZT - timedelta(days=31))
    _in_ausgang(tmp_path, 1, jetzt=JETZT - timedelta(days=29))
    ordner = feedback.ausgang_ordner(tmp_path)
    (ordner / "20261101-000000_kaputt.json").write_text("{nicht json", encoding="utf-8")
    (ordner / "20261101-000001_fremd.json").write_text('{"payload": {"app": "Andere"}}', encoding="utf-8")
    alt_tmp = ordner / ".x.json.123.abc.tmp"
    alt_tmp.write_text("halb", encoding="utf-8")
    os.utime(alt_tmp, (0, 0))
    post = FakePost(ok())
    zusammen = feedback.ausgang_senden(cfg, post, jetzt=JETZT)
    assert zusammen == {"gesendet": 1, "geloescht": 3, "offen": 0, "uebersprungen": False}
    assert len(post.calls) == 1 and not alt_tmp.exists() and list(ordner.iterdir()) == []


def test_ausgang_loescht_zu_grosse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, adresse=URL)
    _in_ausgang(tmp_path, 2)
    post = FakePost(fehler("zu_gross"), ok())
    zusammen = feedback.ausgang_senden(cfg, post, jetzt=JETZT)
    assert (zusammen["gesendet"], zusammen["geloescht"], zusammen["offen"]) == (1, 1, 0)
    # Auch lokal zu gross (z.B. Grenze inzwischen kleiner) -> weg, ohne zu senden
    feedback.senden(feedback.baue_payload("bug", None, "", "", [_png()], "menue", None), None,
                    root=tmp_path, jetzt=JETZT)
    monkeypatch.setattr(feedback, "MAX_BILDER_BYTES", 1)
    post2 = FakePost(ok())
    assert feedback.ausgang_senden(cfg, post2, jetzt=JETZT)["geloescht"] == 1
    assert post2.calls == [] and feedback.ausgang_anzahl(tmp_path) == 0


@pytest.mark.parametrize("problem", [Offline(), fehler("limit"), Antwort(502, "")])
def test_ausgang_hoert_bei_verbindungsproblemen_auf(tmp_path, problem):
    _in_ausgang(tmp_path, 3)
    post = FakePost(problem)
    zusammen = feedback.ausgang_senden(_cfg(tmp_path, adresse=URL), post, jetzt=JETZT)
    assert len(post.calls) == 1 and zusammen["offen"] == 3 and zusammen["gesendet"] == 0


def test_ausgang_macht_nach_anderem_fehler_weiter(tmp_path):
    _in_ausgang(tmp_path, 2)
    post = FakePost(Antwort(405, ""), ok())
    zusammen = feedback.ausgang_senden(_cfg(tmp_path, adresse=URL), post, jetzt=JETZT)
    assert (zusammen["gesendet"], zusammen["offen"]) == (1, 1)
    (rest,) = _ausgang(tmp_path)
    assert json.loads(rest.read_text())["payload"]["text"] == "Nachricht 0"


def test_ausgang_haelt_die_grenzen_ein(tmp_path):
    cfg = _cfg(tmp_path, adresse=URL)
    _in_ausgang(tmp_path, 5)
    post = FakePost(ok())
    assert feedback.ausgang_senden(cfg, post, jetzt=JETZT)["gesendet"] == 3
    assert feedback.ausgang_senden(cfg, post, jetzt=JETZT + timedelta(minutes=30))["gesendet"] == 0
    zusammen = feedback.ausgang_senden(cfg, post, jetzt=JETZT + timedelta(minutes=61))
    assert (zusammen["gesendet"], zusammen["offen"]) == (2, 0) and len(post.calls) == 5


def test_ausgang_ohne_postfach_bleibt_liegen(tmp_path):
    _in_ausgang(tmp_path, 2)
    post = FakePost(ok())
    fetch = FakeFetch(HttpFehler(404))
    zusammen = feedback.ausgang_senden(_cfg(tmp_path), post, fetch=fetch, jetzt=JETZT)
    assert zusammen["offen"] == 2 and post.calls == [] and len(fetch.calls) == 1


def test_leerer_ausgang_fragt_nicht_im_netz_nach(tmp_path):
    fetch = FakeFetch(URL)
    assert feedback.ausgang_senden(_cfg(tmp_path), FakePost(ok()), fetch=fetch, jetzt=JETZT)["offen"] == 0
    assert fetch.calls == []


def test_ausgang_laeuft_nie_doppelt(tmp_path):
    _in_ausgang(tmp_path, 1)
    post = FakePost(ok())
    assert feedback._AUSGANG_LOCK.acquire(blocking=False)
    try:
        zusammen = feedback.ausgang_senden(_cfg(tmp_path, adresse=URL), post, jetzt=JETZT)
    finally:
        feedback._AUSGANG_LOCK.release()
    assert zusammen["uebersprungen"] is True and zusammen["offen"] == 1 and post.calls == []
    assert feedback.ausgang_senden(_cfg(tmp_path, adresse=URL), post, jetzt=JETZT)["gesendet"] == 1


def test_ausgang_hat_eine_obergrenze(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "AUSGANG_MAX_DATEIEN", 3)
    _in_ausgang(tmp_path, 5)
    texte = [json.loads(p.read_text())["payload"]["text"] for p in _ausgang(tmp_path)]
    assert texte == ["Nachricht 2", "Nachricht 3", "Nachricht 4"]  # die neuesten bleiben


# -- Alles in einem -----------------------------------------------------------------
def test_abschicken_ganzer_weg(tmp_path):
    cfg = _cfg(tmp_path, adresse=URL)
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    assert feedback.ist_faellig(cfg, JETZT)
    post = FakePost(ok())
    erg = feedback.abschicken(cfg, "Lob", 5, "Super!", "", [{"name": "a.png", "data": _png()}], "popup",
                              post=post, jetzt=JETZT)
    assert erg.als_antwort() == {"ok": True, "status": "gesendet",
                                 "message": "Danke! Dein Feedback wurde gesendet."}
    gesendet = json.loads(post.calls[0][1]["data"])
    assert (gesendet["kind"], gesendet["stars"], gesendet["trigger"]) == ("bewertung", 5, "popup")
    assert gesendet["brain"] == "claude/claude-opus-5-5" and len(gesendet["images"]) == 1
    assert not feedback.ist_faellig(cfg, JETZT + timedelta(days=11))  # gerade Feedback gegeben
    assert feedback.ist_faellig(cfg, JETZT + timedelta(days=12))


def test_abschicken_mit_falschen_bildern_sagt_warum(tmp_path):
    post = FakePost(ok())
    erg = feedback.abschicken(_cfg(tmp_path, adresse=URL), "bug", None, "x", None, [b"kein bild"],
                              post=post, jetzt=JETZT)
    antwort = erg.als_antwort()
    assert antwort["ok"] is False and "kein Bild" in antwort["error"]
    assert post.calls == [] and _ausgang(tmp_path) == []
    leer = feedback.abschicken(_cfg(tmp_path, adresse=URL), "bug", None, " ", post=post, jetzt=JETZT)
    assert (leer.status, leer.grund) == ("abgelehnt", "ungueltig")


def test_abschicken_ohne_postfach_merkt_es_sich(tmp_path):
    cfg = _cfg(tmp_path)
    erg = feedback.abschicken(cfg, "idee", None, "Dunkler Modus!", fetch=FakeFetch(HttpFehler(404)), jetzt=JETZT)
    assert (erg.status, erg.grund) == ("gespeichert", "keine_url")
    assert feedback.status(cfg, fetch=FakeFetch(HttpFehler(404)), jetzt=JETZT) == {
        "ok": True, "configured": False, "due": False, "pending": 1, "max_images": 5}
    assert _stand(tmp_path)["zuletzt_gesendet"] == "2026-11-08T12:00:00"


def test_status_fuer_die_app(tmp_path):
    cfg = _cfg(tmp_path, adresse=URL)
    feedback.nutzung_hinzufuegen(4000, root=cfg)
    assert feedback.status(cfg, jetzt=JETZT) == {
        "ok": True, "configured": True, "due": True, "pending": 0, "max_images": 5}


# -- Nachfrage-Plan -----------------------------------------------------------------
def test_erste_nachfrage_nach_60_minuten_nutzung(tmp_path):
    cfg = _cfg(tmp_path)
    assert not feedback.ist_faellig(cfg, JETZT)
    assert feedback.nutzung_hinzufuegen(59 * 60, root=tmp_path) == 3540
    assert not feedback.ist_faellig(cfg, JETZT)
    assert feedback.nutzung_hinzufuegen(59.5, root=tmp_path) == 3599.5
    assert not feedback.ist_faellig(cfg, JETZT)
    feedback.nutzung_hinzufuegen(0.5, root=tmp_path)
    assert feedback.ist_faellig(cfg, JETZT)
    assert feedback.nutzung_sekunden(tmp_path) == 3600


def test_danach_alle_12_tage(tmp_path):
    cfg = _cfg(tmp_path)
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    feedback.gezeigt(JETZT, root=tmp_path)
    assert not feedback.ist_faellig(cfg, JETZT)
    assert not feedback.ist_faellig(cfg, JETZT + timedelta(days=11, hours=23, minutes=59))
    assert feedback.ist_faellig(cfg, JETZT + timedelta(days=12))
    feedback.gesendet(JETZT + timedelta(days=12), root=tmp_path)  # Senden zaehlt wie Zeigen
    assert not feedback.ist_faellig(cfg, JETZT + timedelta(days=20))
    assert feedback.ist_faellig(cfg, JETZT + timedelta(days=24))


def test_einstellungen_werden_beachtet(tmp_path):
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    assert not feedback.ist_faellig(_cfg(tmp_path, nachfragen=False), JETZT)
    assert not feedback.ist_faellig(SimpleNamespace(project_root=tmp_path), JETZT)  # ohne [feedback]
    assert feedback.ist_faellig(_cfg(tmp_path, erste_nachfrage_minuten=30), JETZT)
    assert not feedback.ist_faellig(_cfg(tmp_path, erste_nachfrage_minuten=120), JETZT)
    assert feedback.ist_faellig(_cfg(tmp_path, erste_nachfrage_minuten="quatsch"), JETZT)  # -> 60
    feedback.gezeigt(JETZT, root=tmp_path)
    assert not feedback.ist_faellig(_cfg(tmp_path, nachfrage_alle_tage=3), JETZT + timedelta(days=2))
    assert feedback.ist_faellig(_cfg(tmp_path, nachfrage_alle_tage=3), JETZT + timedelta(days=3))
    # 0 Tage hiesse "staendig" -> mindestens 1 Tag
    assert not feedback.ist_faellig(_cfg(tmp_path, nachfrage_alle_tage=0), JETZT + timedelta(hours=1))
    assert feedback.ist_faellig(_cfg(tmp_path, nachfrage_alle_tage=0), JETZT + timedelta(days=1))


@pytest.mark.parametrize("inhalt", ["", "{kaputt", "[1, 2, 3]", "null", '{"nutzung_sekunden": "viel"}',
                                    '{"nutzung_sekunden": 7200, "zuletzt_gezeigt": "gestern"}', "\x00\xff"])
def test_kaputte_datei_stoert_den_plan_nicht(tmp_path, inhalt):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "feedback_state.json").write_text(inhalt, encoding="utf-8", errors="replace")
    cfg = _cfg(tmp_path)
    feedback.ist_faellig(cfg, JETZT)  # wirft nicht
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    assert feedback.nutzung_sekunden(tmp_path) >= 3600
    assert feedback.ist_faellig(cfg, JETZT)
    feedback.gezeigt(JETZT, root=tmp_path)
    assert not feedback.ist_faellig(cfg, JETZT)


def test_fehlende_datei_und_ordner(tmp_path):
    root = tmp_path / "neu"
    assert not feedback.ist_faellig(_cfg(root), JETZT)
    assert feedback.nutzung_sekunden(root) == 0
    feedback.gezeigt(JETZT, root=root)
    assert _stand(root) == {"zuletzt_gezeigt": "2026-11-08T12:00:00"}


def test_unsinnige_nutzungszeiten_werden_ignoriert(tmp_path):
    for unsinn in (-60, 0, float("nan"), float("inf"), "viel", None, True):
        assert feedback.nutzung_hinzufuegen(unsinn, root=tmp_path) == 0
    assert feedback.nutzung_hinzufuegen("90", root=tmp_path) == 90
    assert feedback.nutzung_hinzufuegen(10 ** 9, root=tmp_path) == 90 + 6 * 3600  # Zeitsprung gekappt


def test_zeitpunkte_aus_der_zukunft_werden_ignoriert(tmp_path):
    cfg = _cfg(tmp_path)
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    feedback.gezeigt(JETZT + timedelta(days=300), root=tmp_path)  # Uhr war verstellt
    assert feedback.ist_faellig(cfg, JETZT)
    feedback.gezeigt(JETZT + timedelta(hours=2), root=tmp_path)   # kleine Abweichung zaehlt
    assert not feedback.ist_faellig(cfg, JETZT)


def test_zeiten_mit_zeitzone_gehen_auch(tmp_path):
    from datetime import timezone
    cfg = _cfg(tmp_path)
    feedback.nutzung_hinzufuegen(3600, root=tmp_path)
    jetzt_utc = datetime.now(timezone.utc)
    feedback.gezeigt(jetzt_utc, root=tmp_path)
    assert not feedback.ist_faellig(cfg, jetzt_utc + timedelta(days=1))
    assert feedback.ist_faellig(cfg, datetime.now() + timedelta(days=13))


def test_schreiben_ist_atomar(tmp_path, monkeypatch):
    feedback.nutzung_hinzufuegen(100, root=tmp_path)
    vorher = (tmp_path / "data" / "feedback_state.json").read_text()

    def kaputt(*a, **k):
        raise OSError("Platte voll")

    monkeypatch.setattr(feedback.os, "replace", kaputt)
    feedback.nutzung_hinzufuegen(100, root=tmp_path)  # wirft nicht
    feedback.gezeigt(JETZT, root=tmp_path)
    monkeypatch.undo()
    assert (tmp_path / "data" / "feedback_state.json").read_text() == vorher
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == ["feedback_state.json"]  # kein tmp-Rest


def test_windows_sperre_beim_ersetzen_wird_abgewartet(tmp_path, monkeypatch):
    echt = os.replace
    fehlschlaege = []

    def gesperrt(quelle, ziel):
        if len(fehlschlaege) < 2:
            fehlschlaege.append(1)
            raise PermissionError("Zugriff verweigert")
        echt(quelle, ziel)

    monkeypatch.setattr(feedback.os, "replace", gesperrt)
    monkeypatch.setattr(feedback.time, "sleep", lambda s: None)
    assert feedback.nutzung_hinzufuegen(5, root=tmp_path) == 5
    assert _stand(tmp_path)["nutzung_sekunden"] == 5 and len(fehlschlaege) == 2


def test_gleichzeitiges_zaehlen_verliert_nichts(tmp_path):
    def zaehlen():
        for _ in range(25):
            feedback.nutzung_hinzufuegen(1, root=tmp_path)

    threads = [threading.Thread(target=zaehlen) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert feedback.nutzung_sekunden(tmp_path) == 200


def test_root_darf_auch_die_config_sein(tmp_path):
    cfg = _cfg(tmp_path)
    feedback.nutzung_hinzufuegen(3600, root=cfg)
    feedback.gezeigt(JETZT, root=cfg)
    assert _stand(tmp_path)["nutzung_sekunden"] == 3600
    assert feedback.ausgang_anzahl(cfg) == 0 and feedback.ausgang_ordner(cfg) == tmp_path / "data" / "feedback_ausgang"


# -- Datenschutz --------------------------------------------------------------------
@pytest.fixture
def ki_log():
    eintraege = []

    class Sammler(logging.Handler):
        def emit(self, record):
            eintraege.append(record.getMessage())

    log = logging.getLogger("ki")
    sammler, alte_stufe = Sammler(level=logging.DEBUG), log.level
    log.addHandler(sammler)
    log.setLevel(logging.DEBUG)
    yield eintraege
    log.removeHandler(sammler)
    log.setLevel(alte_stufe)


def test_log_enthaelt_weder_url_noch_inhalt(tmp_path, ki_log):
    cfg = _cfg(tmp_path)
    geheim = "Mein geheimer Text 12345"
    fetch = FakeFetch(URL)
    for antwort in (ok(), Offline(), Antwort(200, "<html>"), fehler("zu_gross"), fehler("limit")):
        feedback.abschicken(cfg, "bug", 3, geheim, "kontakt bei beispiel", [_png()], post=FakePost(antwort),
                            fetch=fetch, jetzt=JETZT + timedelta(hours=len(ki_log)))
    feedback.ausgang_senden(cfg, FakePost(Offline()), fetch=fetch, jetzt=JETZT + timedelta(days=2))
    feedback.abschicken(cfg, "bug", None, "", post=FakePost(ok()), fetch=fetch, jetzt=JETZT)
    assert ki_log, "es sollte etwas geloggt werden"
    for zeile in ki_log:
        assert re.match(r"Feedback (gesendet|gespeichert|abgelehnt)( \(.*\))?$", zeile), zeile
        for verboten in (URL, "AKfycb", "script.google", geheim, "kontakt", "raw.githubusercontent", "base64"):
            assert verboten not in zeile


def test_keine_email_adresse_im_modul():
    quelle = Path(feedback.__file__).read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+", quelle)
    assert all(ord(z) < 128 for z in quelle)  # CLAUDE.md: keine Umlaute im Python-Code


def test_meldungen_sind_deutsch_mit_echten_umlauten():
    m = feedback.MELDUNGEN
    assert m["ok"] == "Danke! Dein Feedback wurde gesendet."
    assert m["offline"] == ("Keine Verbindung. Dein Feedback ist gespeichert und wird automatisch gesendet, "
                            "sobald du wieder online bist.")
    assert m["limit"] == ("Gerade kommen sehr viele R\u00fcckmeldungen an. Dein Feedback wird sp\u00e4ter "
                          "automatisch gesendet.")
    assert "gro\u00df" in m["zu_gross"] and m["zu_gross"].endswith("entferne ein Bild.")
    assert m["keine_url"] == ("Dein Feedback ist gespeichert und wird gesendet, sobald das Feedback-Postfach "
                              "eingerichtet ist.")


def test_echtes_requests_folgt_der_weiterleitung_wie_bei_google(tmp_path, monkeypatch):
    """Apps-Skript: POST -> 302 -> GET auf eine Einmal-Adresse -> JSON. requests macht das von selbst."""
    pytest.importorskip("requests")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    angekommen = []

    class Skript(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            angekommen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(302)
            self.send_header("Location", "/echo?user_content_key=abc")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            koerper = b'{"ok": true}' if self.path.startswith("/echo") else b"<html></html>"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(koerper)))
            self.end_headers()
            self.wfile.write(koerper)

    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Skript)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{server.server_address[1]}/macros/s/x/exec"
        payload = _payload("\u00fcber Weiterleitung")
        assert feedback._versuchen(payload, adresse, None, tmp_path, JETZT) == "ok"
        assert angekommen == [payload]
    finally:
        server.shutdown()
        server.server_close()
