"""Spielmodus (assistant/spiel): Waechter, Eingaben, Sitzung, Erholung, Tagebuch, Grenzen, Bericht.

Kein echtes Spiel, kein Windows: Vordergrund, SendInput, Bildschirmfotos und das Modell sind Fakes.
"""
import io
import json
import threading
import time

import pytest

from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionError_, PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.spiel import eingabe as ein
from assistant.spiel.eingabe import Eingabe, EingabeFehler, FensterWeg, NutzerEingriff, Zielfenster
from assistant.spiel.journal import Journal
from assistant.spiel.profil import Kalibrierung, alle_profile, finde_profil, klingt_online, online_spiel
from assistant.spiel.sitzung import STILLSTAND_SCHWELLE, grenzen_aus
from assistant.spiel.steuerung import SpielSteuerung
from assistant.spiel.windows import ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED, WachHalter, parse_taste
from assistant.tools import build_registry
from assistant.tools.base import MAX_STRIKT
from assistant.tools.spiel import spiel_registry
from tests._fakes import AnthroClient, anthro_msg, text_block, tool_use_block

ML = alle_profile()["manor_lords"]
SPIEL = {"hwnd": 42, "pid": 7, "exe": "manorlords-win64-shipping.exe", "titel": "Manor Lords",
         "rechteck": (100, 50, 1920, 1080)}
NOVA = {"hwnd": 9, "pid": 1, "exe": "ki-app.exe", "titel": "Nova", "rechteck": (0, 0, 800, 600)}


class Uhr:
    """Virtuelle Zeit: schlafen laesst nur die Uhr weiterlaufen (Tests bleiben schnell)."""

    def __init__(self):
        self.t = 1000.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.t

    def schlafe(self, sekunden):
        with self.lock:
            self.t += max(0.001, float(sekunden))
        time.sleep(0)  # anderen Threads Luft lassen


class FakeTasten:
    def __init__(self):
        self.ereignisse = []
        self.pos = (0, 0)

    def taste(self, vk, runter, erweitert=False):
        self.ereignisse.append(("taste", vk, runter))

    def maus_absolut(self, x, y):
        self.pos = (x, y)
        self.ereignisse.append(("abs", x, y))

    def maus_relativ(self, dx, dy):
        self.ereignisse.append(("rel", dx, dy))

    def maus_knopf(self, knopf, runter):
        self.ereignisse.append(("knopf", knopf, runter))

    def rad(self, rasten):
        self.ereignisse.append(("rad", rasten))

    def cursor(self):
        return self.pos

    def gedrueckt(self, vk):
        return sum(1 for e in self.ereignisse if e[0] == "taste" and e[1] == vk and e[2])


class Vorne:
    def __init__(self, info=SPIEL):
        self.info = dict(info) if info else None

    def __call__(self):
        return dict(self.info) if self.info else None


def _png(farbe=(120, 90, 40), groesse=(64, 36)):
    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, "PNG")
    return puffer.getvalue()


class Bilder:
    """Jedes Bild etwas anders (das Spiel 'lebt') - oder immer gleich (festgefahren)."""

    def __init__(self, bewegt=True):
        self.bewegt = bewegt
        self.n = 0
        self.rechtecke = []

    def __call__(self, rechteck):
        self.rechtecke.append(tuple(rechteck))
        self.n += 1
        if not self.bewegt:
            return _png((100, 100, 100))
        return _png(((self.n * 37) % 200 + 30, (self.n * 53) % 200 + 30, 60))


def _eingabe(vorne=None, tasten=None, **kw):
    uhr = Uhr()
    return Eingabe(Zielfenster(hwnd=42, pid=7, exe=SPIEL["exe"], titel="Manor Lords"), ML.erlaubnis(),
                   tasten or FakeTasten(), vorne or Vorne(), schlafe=uhr.schlafe, uhr=uhr, **kw)


# -- Waechter und Eingaben -------------------------------------------------------------
def test_waechter_drueckt_nichts_wenn_das_spiel_nicht_vorne_ist():
    vorne = Vorne()
    tasten = FakeTasten()
    e = _eingabe(vorne, tasten)
    e.taste("c")
    assert tasten.gedrueckt(0x43) == 1
    vorne.info = dict(NOVA)
    with pytest.raises(FensterWeg):
        e.taste("c")
    with pytest.raises(FensterWeg):
        e.klick(0.5, 0.5)
    assert tasten.gedrueckt(0x43) == 1 and not any(ev[0] == "knopf" for ev in tasten.ereignisse)
    vorne.info = None  # z.B. gesperrter Bildschirm
    with pytest.raises(FensterWeg):
        e.taste("c")
    vorne.info = dict(SPIEL, rechteck=(0, 0, 0, 0))  # minimiert
    with pytest.raises(FensterWeg):
        e.taste("c")


def test_gleicher_prozess_mit_neuem_fenster_ist_ok_anderer_nicht():
    vorne = Vorne(dict(SPIEL, hwnd=77))  # Spiel hat sein Fenster neu gebaut (gleiche pid)
    e = _eingabe(vorne)
    e.taste("space")
    vorne.info = dict(SPIEL, hwnd=78, pid=8)  # anderes Programm mit gleichem Titel
    with pytest.raises(FensterWeg):
        e.taste("space")


@pytest.mark.parametrize("kombi", [["ctrl", "c"], ["alt", "f4"], ["win"], ["ctrl", "alt", "delete"],
                                   ["alt", "tab"], ["shift", "tab"], ["ctrl", "w"], ["ctrl", "shift", "esc"],
                                   ["ctrl", "alt", "p"]])
def test_gefaehrliche_kombinationen_sind_gesperrt(kombi):
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    with pytest.raises(EingabeFehler):
        e.kombi(kombi)
    assert not tasten.ereignisse  # nichts gedrueckt


def test_strg_c_ist_auch_als_freigegebene_spieltaste_gesperrt():
    e = _eingabe()
    with pytest.raises(EingabeFehler, match="Kinomodus"):
        e.kombi(["ctrl", "c"], freigabe=True)


def test_nicht_freigegebene_taste_und_unbekannte_taste():
    e = _eingabe()
    with pytest.raises(EingabeFehler, match="nicht freigegeben"):
        e.taste("f4")
    with pytest.raises(EingabeFehler, match="Unbekannte Taste"):
        e.taste("hyperdrive")
    e.kombi(["strg", "1"])  # Kontrollgruppe ist erlaubt (deutscher Name fuer ctrl)


def test_taste_wird_gedrueckt_und_losgelassen_modifier_zuerst():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    e.kombi(["1", "ctrl"])
    tasten_ev = [ev for ev in tasten.ereignisse if ev[0] == "taste"]
    assert tasten_ev == [("taste", 0xA2, True), ("taste", 0x31, True), ("taste", 0x31, False),
                         ("taste", 0xA2, False)]


def test_koordinaten_relativ_zum_spielfenster():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    assert e.klick(0.0, 0.0) == (100, 50)
    assert e.klick(1.0, 1.0) == (100 + 1919, 50 + 1079)
    assert e.klick(0.5, 0.25) == (100 + round(0.5 * 1919), 50 + round(0.25 * 1079))
    with pytest.raises(EingabeFehler, match="au\u00dferhalb"):
        e.klick(1.5, 0.2)
    with pytest.raises(EingabeFehler):
        e.klick("links", 0.2)
    with pytest.raises(EingabeFehler):
        e.klick(float("nan"), 0.2)


def test_kamera_drehen_mit_relativen_bewegungen_und_mittlerer_taste():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    e.kamera_drehen(300, 0)
    rel = [ev for ev in tasten.ereignisse if ev[0] == "rel"]
    assert sum(ev[1] for ev in rel) == 300 and len(rel) > 3
    knoepfe = [ev for ev in tasten.ereignisse if ev[0] == "knopf"]
    assert knoepfe == [("knopf", "mitte", True), ("knopf", "mitte", False)]


def test_ziehen_relativ_und_scrollen():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    e.ziehen(0.5, 0.5, 0.6, 0.5, relativ=True)
    assert sum(ev[1] for ev in tasten.ereignisse if ev[0] == "rel") == round(0.6 * 1919) - round(0.5 * 1919)
    assert [ev for ev in tasten.ereignisse if ev[0] == "knopf"] == [("knopf", "links", True), ("knopf", "links", False)]
    e.scrollen(-3, 0.5, 0.5)
    assert [ev for ev in tasten.ereignisse if ev[0] == "rad"] == [("rad", -1)] * 3


def test_maus_selbst_bewegt_heisst_du_uebernimmst():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    e.klick(0.5, 0.5)
    tasten.pos = (5, 5)  # dein Mensch zieht die Maus weg
    with pytest.raises(NutzerEingriff):
        e.klick(0.2, 0.2)
    assert e.stopp.is_set()
    with pytest.raises(ein.Gestoppt):
        e.taste("c")


def test_loslassen_nach_fehler_mitten_im_ziehen():
    vorne = Vorne()
    tasten = FakeTasten()
    e = _eingabe(vorne, tasten)
    original = e.pruefen
    zaehler = {"n": 0}

    def pruefen():
        zaehler["n"] += 1
        if zaehler["n"] == 3:
            vorne.info = dict(NOVA)
        return original()

    e.pruefen = pruefen
    with pytest.raises(FensterWeg):
        e.ziehen(0.1, 0.1, 0.9, 0.9)
    knoepfe = [ev for ev in tasten.ereignisse if ev[0] == "knopf"]
    assert knoepfe[-1] == ("knopf", "links", False)  # nie mit gedrueckter Taste haengen bleiben


# -- Profil, Online-Sperre, Kalibrierung, Tagebuch ------------------------------------------
def test_manor_lords_wird_erkannt_browser_und_online_nicht():
    assert finde_profil(SPIEL, ["manor_lords"]) is ML
    assert finde_profil({"exe": "foo.exe", "titel": "Manor Lords"}, ["manor_lords"]) is ML
    assert finde_profil({"exe": "chrome.exe", "titel": "Manor Lords Guide - Chrome"}, ["manor_lords"]) is None
    assert finde_profil(SPIEL, []) is None
    assert online_spiel({"exe": "cs2.exe"}) == "Counter-Strike 2"
    assert klingt_online("spiel online ranked fuer mich") and not klingt_online("baue eine Stadt")


def test_kalibrierung_je_aufloesung(tmp_path):
    k = Kalibrierung(tmp_path, "manor_lords")
    assert k.fuer((1920, 1080)) is None
    k.speichern((1920, 1080), {"zeit_widget": {"x": 0.9, "y": 0.05, "text": "Datum"}})
    assert k.fuer((1920, 1080))["elemente"]["zeit_widget"]["x"] == 0.9
    assert k.fuer((2560, 1440)) is None  # andere Aufloesung = neu kalibrieren
    assert "zeit_widget: x=0.900" in k.text((1920, 1080))
    assert k.vergessen() and k.fuer((1920, 1080)) is None


def test_tagebuch_ueberlebt_neustart(tmp_path):
    j = Journal(tmp_path, "manor_lords", "Stadt bauen", "nacht")
    j.notiz("plan", "Erst Holz, dann Haeuser")
    j.notiz("fortschritt", "Holzfaellerlager steht")
    j.zusammenfassung("Jahr 1, Fruehling: 5 Familien")
    j.speichern()
    neu = Journal.laden(j.pfad)
    text = neu.text_fuer_ki()
    assert "Erst Holz" in text and "Holzfaellerlager" in text and "Jahr 1" in text
    assert json.loads(j.pfad.read_text(encoding="utf-8"))["modus"] == "nacht"
    for i in range(500):
        neu.notiz("fortschritt", f"Schritt {i}")
    assert len(neu.eintraege) <= 400 and neu.von("plan") == ["Erst Holz, dann Haeuser"]


def test_grenzen_normal_und_nacht():
    cfg = load_config()
    g = grenzen_aus(cfg.spiel, "normal")
    n = grenzen_aus(cfg.spiel, "nacht")
    assert g.max_minuten == 120 and g.max_euro == 1.0
    assert n.max_minuten == 600 and n.max_euro == 5.0 and n.max_zuege > g.max_zuege
    assert grenzen_aus(cfg.spiel, "normal", stunden="kaputt", euro=float("inf")).max_euro == 1.0
    assert grenzen_aus(cfg.spiel, "normal", stunden=100).max_minuten == 24 * 60


def test_wach_halten_und_zuruecksetzen():
    aufrufe = []
    w = WachHalter(aufruf=lambda flags: aufrufe.append(flags) or 1)
    assert w.einschalten()
    w.ausschalten()
    w.ausschalten()  # zweimal ist harmlos
    assert aufrufe == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED, ES_CONTINUOUS]


def test_not_aus_taste_lesen():
    assert parse_taste("Strg+Alt+Umschalt+P") == (0x2 | 0x1 | 0x4, ord("P"))
    assert parse_taste("Strg+Pause") == (0x2, 0x13)
    assert parse_taste("P") is None


def test_werkzeuge_bleiben_unter_der_claude_grenze():
    specs = build_registry().specs()
    assert sum(1 for s in specs if s.get("strict")) <= MAX_STRIKT
    namen = {s["name"] for s in specs}
    assert "spiel_starten" in namen and not namen & {"spiel_aktion", "spiel_notiz", "spiel_ende"}
    spiel = spiel_registry().specs()
    assert [s["name"] for s in spiel] == ["spiel_aktion", "spiel_ende", "spiel_notiz"]
    aktion = next(s for s in spiel if s["name"] == "spiel_aktion")
    assert aktion["input_schema"]["properties"]["aktionen"]["items"]["additionalProperties"] is False
    from assistant.tools.base import MAX_OPTIONAL, zaehle_optionale

    # schlank: alle Spielwerkzeuge zusammen weit unter Claudes Grenze fuer optionale Angaben
    assert all(s.get("strict") for s in spiel)
    assert sum(zaehle_optionale(s["input_schema"]) for s in spiel) <= MAX_OPTIONAL // 2


def test_spielwerkzeuge_ohne_sitzung_tun_nichts(tmp_path):
    cfg = load_config()
    pm = PermissionManager(cfg.permissions, tmp_path)
    from assistant.tools import ToolContext

    ctx = ToolContext(permissions=pm)
    reg = spiel_registry()
    text, fehler = reg.execute(ctx, "spiel_aktion", {"aktionen": [{"typ": "taste", "taste": "c"}]})
    assert "l\u00e4uft gerade nicht" in text
    with pytest.raises(PermissionError_):
        pm.require_spiel()
    pm.begin_spiel("Manor Lords")
    pm.require_spiel()
    pm.begin_away()
    with pytest.raises(PermissionError_):
        pm.require_spiel()


# -- ganze Sitzung mit Fake-Modell ---------------------------------------------------------
def _aktion(i, aktionen, **extra):
    return (anthro_msg([tool_use_block("spiel_aktion", f"a{i}", {"aktionen": aktionen, **extra})],
                       stop_reason="tool_use"), [])


def _werkzeug(i, name, eingabe):
    return (anthro_msg([tool_use_block(name, f"w{i}", eingabe)], stop_reason="tool_use"), [])


def _text(t):
    return (anthro_msg([text_block(t)]), [])


class Umgebung:
    def __init__(self, tmp_path, scripted, bewegt=True, vorne=None, **einst):
        self.cfg = load_config(tmp_path)
        self.cfg.anthropic_api_key = "sk-ant-test"
        self.cfg.provider.aktiv = "claude"
        self.cfg.permissions.workspace_root = str(tmp_path / "workspace")
        self.cfg.spiel.laufen_sekunden = 5
        for k, v in einst.items():
            setattr(self.cfg.spiel, k, v)
        self.pm = PermissionManager(self.cfg.permissions, self.cfg.workspace_path)
        self.mem = Memory(tmp_path / "m.sqlite3")
        self.client = AnthroClient(scripted)
        self.uhr = Uhr()
        self.tasten = FakeTasten()
        self.vorne = vorne or Vorne()
        self.bilder = Bilder(bewegt)
        self.wach = []
        self.notizen = []
        self.berichte = []
        self.gebucht = []
        self.provider = []

        def fabrik(system, registry, ctx):
            p = AnthropicProvider(self.cfg, system, registry, ctx, client=self.client)
            self.provider.append(p)
            return p

        self.st = SpielSteuerung(
            self.cfg, self.pm, self.mem, fabrik, on_notiz=self.notizen.append, on_bericht=self.berichte.append,
            nutzung_buchen=self.gebucht.extend, plattform="win32", vordergrund=self.vorne,
            tasten_fabrik=lambda: self.tasten, aufnahme=self.bilder,
            wach_fabrik=lambda: WachHalter(aufruf=lambda f: self.wach.append(f) or 1),
            speichern=lambda k, v: None, uhr=self.uhr, schlafe=self.uhr.schlafe)

    def spielen(self, ziel="Bau eine wunderschoene mittelalterliche Stadt", modus="normal", **kw):
        r = self.st.starten(ziel, modus, einverstanden=True, **kw)
        assert r["ok"], r
        assert self.st.warten(20), "Sitzung endet nicht"
        return self.st.letzte_sitzung


def test_ganze_sitzung_handeln_pruefen_bericht(tmp_path):
    u = Umgebung(tmp_path, [
        _werkzeug(1, "spiel_notiz", {"art": "kalibrierung", "elemente": [
            {"name": "zeit_widget", "x": 0.92, "y": 0.04, "text": "Datum"}, {"name": "kaputt", "x": 3, "y": 1,
                                                                             "text": ""}], "text": ""}),
        _werkzeug(2, "spiel_notiz", {"art": "plan", "text": "Holzfaeller an den Wald, dann Hofstaetten"}),
        _aktion(3, [{"typ": "taste", "taste": "c"}, {"typ": "klick", "x": 0.5, "y": 0.5}]),
        _text("Holzfaellerlager platziert."),
        _werkzeug(4, "spiel_notiz", {"art": "fortschritt", "text": "Maerz Jahr 1: Holzfaellerlager steht"}),
        _werkzeug(5, "spiel_ende", {"grund": "fertig", "text": "Die Stadt hat 6 Hofstaetten und einen Markt."}),
        _text("Fertig!"),
    ])
    s = u.spielen()
    assert s.ende == "fertig" and s.zuege == 2
    # Eingaben: Bau-Menue (C = 0x43), Klick in der Fenstermitte, Pausentaste (Leertaste) zum Laufenlassen
    assert u.tasten.gedrueckt(0x43) == 1
    assert ("abs", 100 + round(0.5 * 1919), 50 + round(0.5 * 1079)) in u.tasten.ereignisse
    assert u.tasten.gedrueckt(0x20) >= 2
    # nur das Spielfenster aufgenommen
    assert set(u.bilder.rechtecke) == {SPIEL["rechteck"]}
    # wach gehalten und danach wieder freigegeben
    assert u.wach[0] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED and u.wach[-1] == ES_CONTINUOUS
    # Kalibrierung gespeichert (nur gueltige Werte)
    kalib = Kalibrierung(tmp_path / "data" / "spiele", "manor_lords").fuer((1920, 1080))
    assert set(kalib["elemente"]) == {"zeit_widget"}
    # Bericht mit Ziel, Ergebnis, Plan, Fortschritt und Bildern
    text = s.bericht_text
    assert "Die Stadt hat 6 Hofstaetten" in text and "Holzfaeller an den Wald" in text and "Holzfaellerlager steht" in text
    assert u.berichte == [s] and u.st.rueckkehr == text
    bilder = list((tmp_path / "workspace" / "spiele").rglob("*.jpg")) + list(
        (tmp_path / "workspace" / "spiele").rglob("*.png"))
    assert 1 <= len(bilder) <= 5
    assert list((tmp_path / "workspace" / "spiele").rglob("bericht_*.md"))
    assert s.journal.pfad.is_file() and "journal_" in s.journal.pfad.name
    # Kosten gebucht, Ausnahme fuer Eingaben wieder zu
    assert u.gebucht and not u.pm.spiel
    # Das Modell bekam Bilder - und im ersten Zug die Aufforderung zu kalibrieren
    erste = json.loads(u.client.messages.requests[0])
    inhalt = erste[0]["content"]
    assert any(b.get("type") == "image" for b in inhalt)
    assert "KALIBRIERUNG NOETIG" in json.dumps(inhalt)
    # Ergebnis von spiel_aktion hatte ein neues Bild
    spaeter = json.loads(u.client.messages.requests[3])
    ergebnisse = [b for m in spaeter for b in (m["content"] if isinstance(m["content"], list) else [])
                  if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert any(isinstance(r.get("content"), list) and any(c.get("type") == "image" for c in r["content"])
               for r in ergebnisse)


class Wechselnd(Vorne):
    """Nach weg() ist fuer die naechsten n Abfragen ein anderes Fenster vorne (du klickst kurz zu Nova)."""

    def __init__(self):
        super().__init__()
        self.rest = 0

    def weg(self, n):
        self.rest = n

    def __call__(self):
        if self.rest > 0:
            self.rest -= 1
            return dict(NOVA)
        return dict(SPIEL)


def test_vordergrund_weg_pausiert_und_macht_weiter(tmp_path):
    vorne = Wechselnd()
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}, {"typ": "taste", "taste": "h"}]),
                            _werkzeug(2, "spiel_ende", {"grund": "fertig", "text": "ok"}), _text("Ende")], vorne=vorne)
    original = u.bilder.__call__

    def aufnahme(rechteck):
        bild = original(rechteck)
        if u.bilder.n == 1:
            vorne.weg(30)  # gleich nach dem ersten Bild: das Spiel ist nicht mehr vorne
        return bild

    u.st.aufnahme = aufnahme
    s = u.spielen()
    assert s.ende == "fertig"
    assert any("warte" in n for n in u.notizen) and any("wieder vorne" in n for n in u.notizen)
    assert u.tasten.gedrueckt(0x48) == 0  # H wurde nicht gedrueckt, solange Nova vorne war


def test_spiel_kommt_nicht_zurueck_dann_schluss(tmp_path):
    vorne = Vorne()
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("ok")], vorne=vorne,
                 warten_auf_spiel_sekunden=30)

    def aufnahme(rechteck):
        vorne.info = dict(NOVA)  # nach dem ersten Bild ist das Spiel weg - fuer immer
        return _png()

    u.st.aufnahme = aufnahme
    s = u.spielen()
    assert s.ende == "fenster" and "zu lange nicht im Vordergrund" in s.bericht_text


def test_festgefahren_erholungsleiter_und_ende(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("Ich warte.")], bewegt=False)
    s = u.spielen()
    assert s.ende == "festgefahren"
    probleme = " ".join(s.journal.von("problem"))
    assert "Stufe 1" in probleme and "Stufe 2" in probleme and "Stufe 3" in probleme
    assert u.tasten.gedrueckt(0x1B) >= 2  # Esc in Stufe 2
    assert STILLSTAND_SCHWELLE > 0
    # nach Stufe 3 wird neu kalibriert
    anfragen = " ".join(u.client.messages.requests)
    assert "festzuhaengen" in anfragen


def test_fehlschlaege_loesen_die_erholung_aus(tmp_path):
    skript = []
    for i in range(12):  # jeder Zug versucht dasselbe Verbotene
        skript += [_aktion(i, [{"typ": "taste", "taste": "ctrl+c"}]), _text("hm")]
    u = Umgebung(tmp_path, skript)
    u.cfg.spiel.max_schritte = 6
    s = u.spielen()
    assert s.ende in ("schritte", "festgefahren")
    assert "Kinomodus" in " ".join(u.client.messages.requests)
    assert "Erholung" in " ".join(s.journal.von("problem"))


def test_budget_grenze_stoppt(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("weiter")])
    s = u.spielen(euro=0.01)
    assert s.ende == "budget" and "Kosten-Budget" in s.bericht_text


def test_zuege_grenze_und_gespraech_neu_aus_tagebuch(tmp_path):
    u = Umgebung(tmp_path, [
        _werkzeug(1, "spiel_notiz", {"art": "plan", "text": "PLAN-ALPHA: Markt in die Mitte"}),
        _text("ok"),
    ], neustart_nach_zuegen=2)
    u.cfg.spiel.max_schritte = 5
    s = u.spielen()
    assert s.ende == "schritte" and s.zuege == 5
    assert len(u.provider) >= 2  # frisches Gespraech
    # das neue Gespraech beginnt mit Ziel + Tagebuch (der Plan steht drin) - ohne alte Bilder
    neue = [json.loads(r) for r in u.client.messages.requests if len(json.loads(r)) == 1]
    assert len(neue) >= 2 and "PLAN-ALPHA" in json.dumps(neue[-1])
    assert "wunderschoene" in json.dumps(neue[-1])
    assert s.journal.daten["zusammenfassungen"]  # vorher zusammengefasst


def test_stopp_von_aussen_und_not_aus(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 2}]), _text("weiter")])
    gestartet = {}

    class NotAus:
        def stop(self):
            gestartet["gestoppt"] = True

    def notaus(gedrueckt):
        gestartet["taste"] = gedrueckt
        return NotAus()

    u.st.notaus_fabrik = notaus
    assert u.st.starten("Stadt", einverstanden=True)["ok"]
    for _ in range(200):
        if "taste" in gestartet:
            break
        time.sleep(0.01)
    gestartet["taste"]()  # Strg+Alt+Umschalt+P
    assert u.st.warten(20)
    s = u.st.letzte_sitzung
    assert s.ende == "taste" and gestartet.get("gestoppt")


def test_start_wartet_auf_das_spiel_und_verweigert_online(tmp_path):
    vorne = Vorne(NOVA)
    u = Umgebung(tmp_path, [_text("ok")], vorne=vorne)
    assert u.st.starten("Stadt", einverstanden=True)["ok"]
    assert u.st.status()["zustand"] in ("sucht", "spielt", "wartet", "laeuft")
    vorne.info = {"hwnd": 5, "pid": 5, "exe": "cs2.exe", "titel": "Counter-Strike 2", "rechteck": (0, 0, 10, 10)}
    assert u.st.warten(20)
    assert u.st.letzte_sitzung is None and any("Online-Spiel" in n for n in u.notizen)
    assert not u.tasten.ereignisse
    r = u.st.starten("Spiel fuer mich online ranked", einverstanden=True)
    assert not r["ok"] and "Online" in r["error"]


def test_start_braucht_zustimmung_und_windows(tmp_path):
    u = Umgebung(tmp_path, [_text("ok")])
    r = u.st.starten("Stadt")
    assert not r["ok"] and r["zustimmung"] and "Strg+Alt+Umschalt+P" in r["warnung"]
    u.st.tasten_fabrik = None
    u.st.plattform = "linux"
    r = u.st.starten("Stadt", einverstanden=True)
    assert not r["ok"] and "Windows" in r["error"]


def test_nicht_im_afk_modus(tmp_path):
    u = Umgebung(tmp_path, [_text("ok")])
    u.pm.begin_away()
    r = u.st.starten("Stadt", einverstanden=True)
    assert not r["ok"] and "AFK" in r["error"]


def test_vorschlag_vom_werkzeug(tmp_path):
    u = Umgebung(tmp_path, [_text("ok")])
    vorschlaege = []
    u.st.on_vorschlag = vorschlaege.append
    from assistant.tools import ToolContext

    ctx = ToolContext(permissions=u.pm, extra={"spiel_vorschlag": u.st.vorschlagen})
    text, _ = build_registry().execute(ctx, "spiel_starten", {"ziel": "Bau eine Stadt", "modus": "nacht"})
    assert "Vorgeschlagen" in text and vorschlaege == [{"ziel": "Bau eine Stadt", "modus": "nacht"}]
    assert u.st.status()["vorschlag"]["modus"] == "nacht" and not u.st.aktiv  # startet NICHT von selbst
    text, _ = build_registry().execute(ctx, "spiel_starten", {"ziel": "online pvp spielen"})
    assert "Nicht vorgeschlagen" in text


def test_ohne_augen_nur_text(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]),
                            _werkzeug(2, "spiel_ende", {"grund": "aufgeben", "text": "sehe nichts"}), _text("ok")])
    u.st.sieht_bilder = lambda: False
    u.st.ocr = lambda png: "Fruehling Jahr 1"
    r = u.st.starten("Stadt", einverstanden=True)
    assert "sieht keine Bilder" in r["text"]
    assert u.st.warten(20)
    alles = " ".join(u.client.messages.requests)
    assert "Fruehling Jahr 1" in alles and '"image"' not in alles
    assert u.st.letzte_sitzung.ende == "aufgeben"


def test_tasten_halten_mit_bild_und_spielfremde_aktion(tmp_path):
    u = Umgebung(tmp_path, [
        _aktion(1, [{"typ": "tasten_halten", "taste": "tab", "zahl": 1},
                    {"typ": "fliegen"}, {"typ": "taste", "taste": "c"}]),
        _werkzeug(2, "spiel_ende", {"grund": "fertig", "text": "ok"}), _text("ok")])
    s = u.spielen()
    assert s.ende == "fertig"
    alles = " ".join(u.client.messages.requests)
    assert "w\\u00e4hrend die Taste gehalten wurde" in alles or "w\u00e4hrend die Taste gehalten wurde" in alles
    assert "Unbekannte Aktion" in alles
    assert u.tasten.gedrueckt(0x43) == 0  # nach einem Fehler werden die weiteren Aktionen ausgelassen
    assert u.tasten.gedrueckt(0x09) == 1


# -- Korrekturen aus der Pruefung ----------------------------------------------------------
@pytest.mark.parametrize("kombi", [["alt", "tab", "tab"], ["alt", "tab", "1"], ["shift", "alt", "tab"],
                                   ["ctrl", "esc", "a"], ["ctrl", "shift", "esc", "a"], ["shift", "tab", "tab"],
                                   ["alt", "esc", "esc"], ["ctrl", "c", "c"], ["alt", "space"], ["alt", "enter", "a"],
                                   ["alt", "f4", "x"], ["shift", "ctrl", "c"]])
def test_sperrliste_laesst_sich_nicht_mit_extra_tasten_umgehen(kombi):
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    with pytest.raises(EingabeFehler):
        e.kombi(kombi)
    with pytest.raises(EingabeFehler):
        e.kombi(kombi, freigabe=True)
    assert not tasten.ereignisse


def test_erlaubte_kombinationen_gehen_weiter():
    e = _eingabe()
    for kombi in (["alt"], ["shift", "1"], ["ctrl", "shift", "1"], ["ctrl", "1"], ["alt", "w"]):
        e.kombi(kombi)


def test_gehaltene_tasten_zaehlen_mit():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    e._runter("alt")  # z.B. noch von einer vorigen Aktion gehalten
    with pytest.raises(EingabeFehler):
        e.kombi(["tab"])
    e.loslassen()
    assert tasten.gedrueckt(0x09) == 0


def test_vor_jedem_tastendruck_wird_neu_geprueft():
    class Kippt(Vorne):
        def __init__(self):
            super().__init__()
            self.n = 0

        def __call__(self):
            self.n += 1
            return dict(SPIEL) if self.n <= 2 else dict(NOVA)  # mitten in der Kombination: Fenster weg

    tasten = FakeTasten()
    e = _eingabe(Kippt(), tasten)
    with pytest.raises(FensterWeg):
        e.kombi(["ctrl", "1"])
    runter = [ev for ev in tasten.ereignisse if ev[0] == "taste" and ev[2]]
    hoch = [ev for ev in tasten.ereignisse if ev[0] == "taste" and not ev[2]]
    assert [ev[1] for ev in runter] == [0xA2] and [ev[1] for ev in hoch] == [0xA2]  # '1' nie gedrueckt


def test_scrollen_ohne_ort_geht_zuerst_ins_spielfenster():
    tasten = FakeTasten()
    e = _eingabe(tasten=tasten)
    tasten.pos = (5, 5)  # Zeiger ausserhalb des Spiels (z.B. ueber Nova)
    e._erwartet = None
    e.scrollen(2)
    bewegt = [ev for ev in tasten.ereignisse if ev[0] == "abs"]
    assert bewegt == [("abs", 100 + round(0.5 * 1919), 50 + round(0.5 * 1079))]
    assert [ev for ev in tasten.ereignisse if ev[0] == "rad"] == [("rad", 1)] * 2
    tasten.ereignisse.clear()
    tasten.pos = (300, 300)  # schon im Spiel: dort bleiben
    e._erwartet = (300, 300)
    e.scrollen(-1)
    assert not [ev for ev in tasten.ereignisse if ev[0] == "abs"]


def test_minimiertes_fenster_hat_keine_groesse(monkeypatch):
    from assistant.sehen import windows as sw
    from assistant.spiel import windows as w

    monkeypatch.setattr(w, "ist_windows", lambda: True)
    monkeypatch.setattr(sw, "vordergrund", lambda: dict(SPIEL, rechteck=(-32000, -32000, 160, 28)))
    monkeypatch.setattr(w, "client_rechteck", lambda hwnd: None)
    info = w.vordergrund_info()
    assert info["rechteck"] == (0, 0, 0, 0)
    e = _eingabe(Vorne(info))
    with pytest.raises(FensterWeg, match="minimiert"):
        e.taste("c")


def test_bilder_nach_mitternacht_im_ordner_des_starttags(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    from assistant.spiel.sitzung import SpielSitzung

    assert SpielSitzung._ordner_datum(SimpleNamespace(bilder_ordner=Path("w/spiele/2026-11-07"))) == "20261107"
    u = Umgebung(tmp_path, [_werkzeug(1, "spiel_ende", {"grund": "fertig", "text": "ok"}), _text("ok")])
    s = u.spielen()
    for bild in s.bericht_bilder:
        assert bild.name.startswith(s.bilder_ordner.name.replace("-", "") + "_")


def test_modellfehler_zaehlen_als_fehler_und_das_spiel_laeuft_nicht_weiter(tmp_path):
    u = Umgebung(tmp_path, [RuntimeError("Netz weg")])
    s = u.spielen()
    assert s.ende == "fehler"
    assert u.tasten.gedrueckt(0x20) == 0  # nie unbeaufsichtigt weiterlaufen lassen
    # ein Aussetzer behaelt das Gespraech, ab dem zweiten in Folge ein frisches (keine Bilder-Stapel)
    assert len(u.provider) >= 4
    assert all(len(json.loads(r)) <= 2 for r in u.client.messages.requests)
    assert "nicht geantwortet" in " ".join(s.journal.von("problem"))


def test_leere_antwort_ohne_werkzeug_ist_ein_fehler(tmp_path):
    u = Umgebung(tmp_path, [_text("")])
    s = u.spielen()
    assert s.ende == "fehler" and "leere Antwort" in " ".join(s.journal.von("problem"))


def test_routine_meldungen_werden_keine_karten(tmp_path):
    u = Umgebung(tmp_path, [_werkzeug(1, "spiel_notiz", {"art": "plan", "text": "Plan A"}), _text("Zug fertig."),
                            _text("weiter")])
    u.cfg.spiel.max_schritte = 4
    s = u.spielen()
    assert s.ende == "schritte"
    assert not any(n.startswith("Zug ") or n.startswith("Plan:") for n in u.notizen)
    assert s.letztes  # das Band bekommt den Stand trotzdem


def test_stopp_waehrend_des_bildes_schickt_keine_anfrage_mehr(tmp_path):
    u = Umgebung(tmp_path, [_text("ok")])
    original = u.bilder.__call__

    def aufnahme(rechteck):
        bild = original(rechteck)
        if u.st.sitzung is not None:
            u.st.stoppen()
        return bild

    u.st.aufnahme = aufnahme
    s = u.spielen()
    assert s.ende == "nutzer" and u.client.messages.calls == 0


def test_grenze_beim_laufenlassen_pausiert_das_spiel(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("weiter")], laufen_sekunden=120)
    s = u.spielen(stunden=0.05)  # 3 Minuten - die Grenze kommt mitten im Laufenlassen
    assert s.ende == "zeit"
    assert u.tasten.gedrueckt(0x20) % 2 == 0 and s.pausiert is True
    assert "Zum Schluss pausiert." in s.journal.von("system")


def test_bei_mausuebernahme_kein_pausieren(tmp_path, monkeypatch):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "klick", "x": 0.5, "y": 0.5}, {"typ": "warten", "zahl": 0.1},
                                        {"typ": "klick", "x": 0.2, "y": 0.2}]), _text("ok")])
    original = Eingabe.warten

    def warten(self, sekunden):
        self.tasten.pos = (1, 1)  # dein Mensch greift zur Maus
        return original(self, sekunden)

    monkeypatch.setattr(Eingabe, "warten", warten)
    s = u.spielen()
    assert s.ende == "maus"
    assert "Zum Schluss pausiert." not in s.journal.von("system")


def test_spielbilder_gehen_als_jpeg_und_bytes_begrenzen_das_gespraech(tmp_path, monkeypatch):
    from assistant.spiel import sitzung as sitzung_modul
    from assistant.spiel.bild import fuer_ki

    import os

    Image = pytest.importorskip("PIL.Image")
    puffer = io.BytesIO()
    Image.frombytes("RGB", (1200, 700), os.urandom(1200 * 700 * 3)).save(puffer, "PNG")  # wie ein echtes Spielbild
    gross = puffer.getvalue()
    bild = fuer_ki(gross, "x.png", 1280)
    assert bild.mime == "image/jpeg" and bild.name.endswith(".jpg") and len(bild.data) < len(gross)
    monkeypatch.setattr(sitzung_modul, "MAX_BILD_BYTES_IM_GESPRAECH", 1)
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("ok")])
    u.cfg.spiel.max_schritte = 3
    s = u.spielen()
    assert s.ende == "schritte" and len(u.provider) == 3


def test_stopp_kurz_vor_dem_start_der_sitzung_wird_nie_verschluckt(tmp_path):
    u = Umgebung(tmp_path, [_text("ok")])
    bauen = u.st._sitzung_bauen

    def bauen_und_stopp(start, info):
        sitzung = bauen(start, info)
        u.st.stoppen()  # genau zwischen Bauen und Starten
        return sitzung

    u.st._sitzung_bauen = bauen_und_stopp
    assert u.st.starten("Stadt", einverstanden=True)["ok"]
    assert u.st.warten(20)
    assert u.st.letzte_sitzung is None and not u.tasten.ereignisse and u.client.messages.calls == 0


def test_minimiertes_spiel_vorne_kein_endlos_kreisen(tmp_path):
    from assistant.spiel.sitzung import MAX_BILD_BYTES_IM_GESPRAECH

    class Zaehlend(Vorne):
        def __init__(self):
            super().__init__(dict(SPIEL, rechteck=(0, 0, 0, 0)))  # minimiert, aber "vorne"
            self.n = 0

        def __call__(self):
            self.n += 1
            return super().__call__()

    vorne = Zaehlend()
    u = Umgebung(tmp_path, [_text("ok")], vorne=vorne, warten_auf_spiel_sekunden=3600)
    s = u.spielen(stunden=0.05)
    assert s.ende == "zeit"
    assert u.client.messages.calls == 0 and not u.tasten.ereignisse
    assert len(u.notizen) < 10  # kein Strom aus "wieder vorne"-Karten
    assert vorne.n < 5000       # kein Kreisen ohne Pause
    assert MAX_BILD_BYTES_IM_GESPRAECH == 15 * 1024 * 1024


def test_wieder_vorne_meldungen_sind_gedrosselt(tmp_path):
    class Flackert(Vorne):
        def __init__(self):
            super().__init__()
            self.n = 0

        def __call__(self):
            self.n += 1
            return dict(SPIEL) if self.n % 7 else dict(NOVA)  # das Fenster wechselt staendig

    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("ok")], vorne=Flackert())
    u.cfg.spiel.max_schritte = 30
    s = u.spielen()
    karten = [n for n in u.notizen if "vorne" in n]
    assert s.ende in ("schritte", "zeit")
    assert len(karten) <= 2 + s.minuten * 2 + 2


def test_not_aus_pause_erst_wenn_die_modifier_los_sind():
    tasten = FakeTasten()
    gehalten = {"n": 0}

    def modifier_gehalten():
        gehalten["n"] += 1
        return gehalten["n"] <= 3  # Strg+Alt+Umschalt noch kurz gedrueckt

    tasten.modifier_gehalten = modifier_gehalten
    e = _eingabe(tasten=tasten)
    assert e.notfall_pause("space") and tasten.gedrueckt(0x20) == 1 and gehalten["n"] == 4
    tasten.ereignisse.clear()
    tasten.modifier_gehalten = lambda: True  # bleibt gedrueckt -> lieber gar nicht pausieren
    assert not e.notfall_pause("space") and not tasten.ereignisse


def test_not_aus_taste_waehrend_des_laufens_pausiert_erst_nach_dem_loslassen(tmp_path):
    u = Umgebung(tmp_path, [_aktion(1, [{"typ": "warten", "zahl": 0.1}]), _text("weiter")], laufen_sekunden=60)
    u.tasten.modifier_gehalten = lambda: True  # die Not-Aus-Taste wird noch gehalten
    gestartet = {}

    class NotAus:
        def stop(self):
            pass

    def notaus(gedrueckt):
        gestartet["taste"] = gedrueckt
        return NotAus()

    u.st.notaus_fabrik = notaus
    original = u.st.schlafe
    def schlafe(sek):
        s = u.st.sitzung
        if s is not None and s.zustand == "laeuft" and "taste" in gestartet:
            gestartet.pop("taste")()
        original(sek)

    u.st.schlafe = schlafe
    s = u.spielen()
    assert s.ende == "taste"
    assert u.tasten.gedrueckt(0x20) == 1  # nur das Weiterlaufen - keine Leertaste zu gehaltenen Modifiern
