"""0.44: Premium-Freischaltung (Code, Geraetebindung, Einmaligkeit, Ablauf), Simulation, Selbstschutz.
Nutzt einen eigenen Test-Schluessel - der echte private Schluessel ist nicht im Repo."""
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

from assistant import premium as P
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager


# -- ein Test-Schluesselpaar (zwei feste Primzahlen, nur fuer die Tests - nie der echte Schluessel) --------
def _ist_prim(n: int) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):   # deterministisch fuer n < 3.3e24
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _schluessel():
    def prim(start: int) -> int:
        n = start | 1
        while not _ist_prim(n):
            n += 2
        return n
    p = prim(0xff1ca28c6b6f8e3f5d9c2a7b4e1f0d83ff1ca28c6b6f8e3f5d9c2a7b4e1f0d83ff1ca28c6b6f8e3f5d9c2a7b4e1f0d83ff1ca28c6b6f8e3f5d9c2a7b4e1f0d83)
    q = prim(0xfe3b9a7c5d1e2f408a6b4c3d2e1f0a97fe3b9a7c5d1e2f408a6b4c3d2e1f0a97fe3b9a7c5d1e2f408a6b4c3d2e1f0a97fe3b9a7c5d1e2f408a6b4c3d2e1f0a97)
    e = 65537
    return p * q, e, pow(e, -1, (p - 1) * (q - 1))


N, E, D = _schluessel()
SERVER = "https://lizenz.test"
_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _sign(daten: bytes) -> bytes:
    k = (N.bit_length() + 7) // 8
    t = _INFO + hashlib.sha256(daten).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), D, N).to_bytes(k, "big")


def _code(kennung, stufe="premium", dauer=3600, frist=7, nonce="aa" * 8, jetzt=None, **extra):
    inhalt = {"v": 1, "k": kennung, "t": stufe, "d": dauer, "b": int((jetzt or time.time()) + frist * 86400),
              "n": nonce, **extra}
    roh = json.dumps(inhalt, separators=(",", ":")).encode()
    b = base64.urlsafe_b64encode
    return "NOVA-" + b(roh).rstrip(b"=").decode() + "." + b(_sign(roh)).rstrip(b"=").decode()


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OEFFENTLICH_N", N)
    monkeypatch.setattr(P, "_SIM_HASH", hashlib.pbkdf2_hmac("sha256", b"test-pin", P._SIM_SALZ, 300000).hex())
    (tmp_path / "data").mkdir()
    return tmp_path


# -- Code und Lizenz ----------------------------------------------------------
def test_gueltiger_code_schaltet_frei(root):
    k = P.kennung(root)
    assert P.stufe(root) is None
    P.einloesen(root, _code(k, "max", 3600, u=SERVER))
    assert P.stufe(root) == "max"
    assert "Max" in P.status_text(root)


def test_code_nur_fuer_dieses_geraet(root):
    with pytest.raises(P.PremiumFehler, match="anderen Geraet"):
        P.einloesen(root, _code("ffffffffffffffff"))


def test_code_nur_einmal(root):
    k = P.kennung(root)
    c = _code(k, nonce="1234" * 4)
    P.einloesen(root, c)
    with pytest.raises(P.PremiumFehler, match="schon eingeloest"):
        P.einloesen(root, c)


def test_code_laeuft_aus(root):
    k = P.kennung(root)
    jetzt = time.time()
    P.einloesen(root, _code(k, "premium", dauer=60, u=SERVER), jetzt=jetzt)
    assert P.stufe(root, jetzt + 30) == "premium"
    assert P.stufe(root, jetzt + 120) is None       # nach 60 s vorbei


def test_einloesefrist(root):
    k = P.kennung(root)
    alt = _code(k, frist=-1)                          # Frist schon vorbei
    with pytest.raises(P.PremiumFehler, match="abgelaufen"):
        P.einloesen(root, alt)


def test_veraenderter_code_faellt_durch(root):
    k = P.kennung(root)
    c = _code(k)
    kaputt = c[:-6] + ("xxxxxx" if c[-6:] != "xxxxxx" else "yyyyyy")
    with pytest.raises(P.PremiumFehler):
        P.einloesen(root, kaputt)


def test_fremde_unterschrift_faellt_durch(root, monkeypatch):
    k = P.kennung(root)
    c = _code(k)
    monkeypatch.setattr(P, "OEFFENTLICH_N", N + 2)   # anderer Schluessel -> Unterschrift passt nicht
    with pytest.raises(P.PremiumFehler, match="ungueltig"):
        P.einloesen(root, c)


def test_aus_code_schaltet_ab(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "max", 99999, u=SERVER))
    assert P.stufe(root) == "max"
    P.einloesen(root, _code(k, "aus", nonce="ff" * 8))
    assert P.stufe(root) is None


# -- Simulation ---------------------------------------------------------------
def test_simulation_an_aus(root):
    class Reg:
        def __init__(self): self.n = []
        def register(self, w): self.n.append(w.name)
    ctl = type("C", (), {"registry": Reg()})()
    assert "aus" in P.simulation_status(root)
    assert P.simulation_umschalten(root, "test-pin") == "test_an"
    assert P.simulation_laden(root, ctl) == "max" and "premium_demo" in ctl.registry.n
    assert P.simulation_umschalten(root, "test-pin") == "test_aus"
    assert P.simulation_laden(root, ctl) is None


def test_simulation_falscher_pin(root):
    with pytest.raises(P.PremiumFehler):
        P.simulation_umschalten(root, "falsch")


# -- Selbstschutz / Sperren ---------------------------------------------------
def test_premium_dateien_gesperrt(tmp_path):
    pm = PermissionManager(PermissionSettings(), tmp_path / "ws", app_root=tmp_path)
    assert pm.ist_gesperrt((tmp_path / "data" / "premium.json").resolve())
    assert pm.ist_gesperrt((tmp_path / "data" / "premium" / "paket.zip").resolve())


def test_eigener_code_gesperrt_nur_in_exe(tmp_path, monkeypatch):
    pm = PermissionManager(PermissionSettings(), tmp_path / "ws", app_root=tmp_path)
    assert not pm.ist_gesperrt((tmp_path / "assistant" / "premium.py").resolve())  # Quellcode: offen
    monkeypatch.setattr(P.sys if hasattr(P, "sys") else sys, "frozen", True, raising=False)
    import assistant.permissions as Perm
    monkeypatch.setattr(Perm.sys, "frozen", True, raising=False)
    assert pm.ist_gesperrt((tmp_path / "assistant" / "premium.py").resolve())      # .exe: geschuetzt
    assert not pm.ist_gesperrt((tmp_path / "ws" / "meine_notiz.py").resolve())     # Arbeitsordner: offen


def test_selbstschutz_im_systemprompt():
    from assistant.personality import _SELBSTSCHUTZ
    for wort in ("vertraulich", "kopieren", "novaaiupdate"):
        assert wort in _SELBSTSCHUTZ


def test_premium_befehle_nicht_in_der_liste():
    from assistant.app.controller import COMMANDS
    text = " ".join(c for c, _ in COMMANDS)
    for versteckt in ("/novaaiupdate", "/codegenerator", "/simulation"):
        assert versteckt not in text


def test_codegenerator_braucht_token(root, monkeypatch):
    monkeypatch.delenv("NOVA_PREMIUM_TOKEN", raising=False)
    with pytest.raises(P.PremiumFehler, match="NOVA_PREMIUM_TOKEN"):
        P.codegenerator_holen(root)


# -- Entwicklermodus ----------------------------------------------------------
def test_entwicklermodus_code(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "dev", 99999, u=SERVER))
    assert P.stufe(root) == "dev" and "Entwickler" in P.status_text(root)


def test_entwicklerblock_nur_mit_dev(root, monkeypatch):
    import assistant.personality as PR
    cfg = type("C", (), {"project_root": root})()
    assert PR._entwickler_block(cfg) == ""
    P.einloesen(root, _code(P.kennung(root), "dev", 99999, u=SERVER))
    block = PR._entwickler_block(cfg)
    assert "/novaaiupdate" in block and "/codegenerator" in block and "/sandbox" in block


def test_code_muster_erkennt_echten_code(root):
    c = _code(P.kennung(root))
    assert P.CODE_MUSTER.match(c)
    assert not P.CODE_MUSTER.match("hallo nova wie geht es dir")
    assert not P.CODE_MUSTER.match("/novaaiupdate")


# -- Sperrung (Entwickler nimmt Zugang zurueck) -------------------------------
def _sperrliste(nonces=(), kennungen=()):
    import base64 as b64
    inner = json.dumps({"v": 1, "gesperrt": list(nonces), "kennungen": list(kennungen), "stand": 1},
                       separators=(",", ":")).encode()
    huelle = {"daten": b64.urlsafe_b64encode(inner).rstrip(b"=").decode(),
              "sig": b64.b64encode(_sign(inner)).decode()}
    return json.dumps(huelle).encode()


def test_sperrung_schaltet_ab(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "max", 99999, nonce="dead" * 4, u=SERVER))
    assert P.stufe(root) == "max"
    gesperrt = P.sperrung_pruefen(root, holen=lambda server: _sperrliste(nonces=["deaddeaddeaddead"]))
    assert gesperrt and P.stufe(root) is None and P.lizenz(root)["gesperrt"]


def test_sperrung_ganzes_geraet(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "premium", 99999, nonce="aa" * 8, u=SERVER))
    P.sperrung_pruefen(root, holen=lambda server: _sperrliste(kennungen=[k]))
    assert P.stufe(root) is None


def test_ohne_netz_bleibt_premium(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "premium", 99999, nonce="bb" * 8, u=SERVER))

    def kaputt(server):
        raise OSError("kein Netz")
    assert P.sperrung_pruefen(root, holen=kaputt) is False
    assert P.stufe(root) == "premium"       # fehlendes Netz sperrt einen Zahler nie aus


def test_gefaelschte_sperrliste_ignoriert(root, monkeypatch):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "premium", 99999, nonce="cc" * 8, u=SERVER))
    monkeypatch.setattr(P, "OEFFENTLICH_N", N + 4)   # Liste mit falschem Schluessel signiert
    assert P.sperrung_pruefen(root, holen=lambda server: _sperrliste(nonces=["cccccccccccccccc"])) is False
    assert P.lizenz(root).get("gesperrt") is None


# -- 0.52: Codes ohne Geheimnisse, Paket nur ueber den Lizenzserver ---------------
def test_echter_pin_steht_nicht_im_klartext():
    quelle = Path(P.__file__).read_text(encoding="utf-8")
    assert "1369" + "6" not in quelle and "1367" + "9" not in quelle
    import assistant.personality as PR
    assert "1369" + "6" not in Path(PR.__file__).read_text(encoding="utf-8")


def test_lizenz_speichert_keine_geheimnisse(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 99999, u=SERVER, s="GEHEIM", g="ghp_GEHEIM"))
    roh = (root / "data" / "premium.json").read_text(encoding="utf-8")
    assert "GEHEIM" not in roh
    d = P.lizenz(root)
    assert d["server"] == SERVER and d["code"].startswith("NOVA-")
    assert "zugang" not in d and "schluessel" not in d


def test_alte_geheimnisse_werden_entfernt(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 99999, u=SERVER))
    d = P.lizenz(root)
    d.update(zugang="ghp_alt", schluessel="alt")
    P._speichern(root, d)
    P.laden(root, ctl=None, sperrung=False)
    assert "zugang" not in P.lizenz(root) and "schluessel" not in P.lizenz(root)


def test_nur_https_server(root, monkeypatch):
    monkeypatch.delenv("NOVA_LIZENZSERVER_URL", raising=False)
    assert P.lizenzserver({"server": "https://nova.example.com/"}) == "https://nova.example.com"
    assert P.lizenzserver({"server": "http://boese.example.com"}) == ""
    assert P.lizenzserver({"server": "file:///etc/passwd"}) == ""
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", "https://ersatz.example.com")
    assert P.lizenzserver({}) == "https://ersatz.example.com"


def _zip(inhalt=b"VERSION = '9'\n"):
    import io
    import zipfile
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("nova_premium/__init__.py", inhalt)
    return puffer.getvalue()


def test_paket_vom_lizenzserver(root):
    k = P.kennung(root)
    code = _code(k, "premium", 99999, u=SERVER)
    P.einloesen(root, code)
    roh = _zip()
    gesehen = {}

    def server(url, c, kenn):
        gesehen.update(url=url, code=c, kennung=kenn)
        return {"ok": True, "zip": base64.b64encode(roh).decode(), "sig": base64.b64encode(_sign(roh)).decode(),
                "info": {"version": "9"}}
    assert P.paket_holen(root, holen=server)["version"] == "9"
    assert gesehen == {"url": SERVER, "code": code, "kennung": k}
    assert P.paket_pfad(root).read_bytes() == roh


def test_falscher_server_kann_kein_paket_unterschieben(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 99999, u=SERVER))
    roh = _zip(b"import os; os.system('boese')\n")
    fremd = {"ok": True, "zip": base64.b64encode(roh).decode(), "sig": base64.b64encode(b"x" * 256).decode()}
    with pytest.raises(P.PremiumFehler, match="unterschrieben"):
        P.paket_holen(root, holen=lambda *a: fremd)
    assert not P.paket_pfad(root).exists()


def test_alter_code_ohne_server(root, monkeypatch):
    monkeypatch.delenv("NOVA_LIZENZSERVER_URL", raising=False)
    P.einloesen(root, _code(P.kennung(root), "premium", 99999))
    with pytest.raises(P.PremiumFehler, match="neuen Code"):
        P.paket_holen(root, holen=lambda *a: {})


def test_simulation_laedt_nie_das_echte_paket(root):
    P.paket_pfad(root).parent.mkdir(parents=True)
    P.paket_pfad(root).write_bytes(_zip())
    geladen = []
    import assistant.premium as PM
    alt = PM.laden
    PM.laden = lambda *a, **k: geladen.append(1)
    try:
        class Reg:
            def __init__(self): self.n = []
            def register(self, w): self.n.append(w.name)
        ctl = type("C", (), {"registry": Reg()})()
        P.simulation_umschalten(root, "test-pin")
        P.simulation_laden(root, ctl)
    finally:
        PM.laden = alt
    assert geladen == [] and ctl.registry.n == ["premium_demo"]


def test_alte_oeffentliche_pins_gelten_nicht_mehr():
    # die alten PINs standen im oeffentlichen Repo - sie duerfen nichts mehr oeffnen
    assert not P.sim_pin_ok("novaai." + "13696") and not P.cg_pin_ok("1367" + "9")
    assert not P.sim_pin_ok("") and not P.cg_pin_ok("x" * 100)


# -- 0.53: data/premium.json von Hand aendern bringt nichts --------------------------
def test_handgemachte_lizenz_gilt_nicht(root):
    P._speichern(root, {"stufe": "dev", "bis": time.time() + 999999})
    assert P.stufe(root) is None                       # kein unterschriebener Code -> nichts


def test_laufzeit_verlaengern_von_hand_bringt_nichts(root):
    jetzt = time.time()
    P.einloesen(root, _code(P.kennung(root), "premium", 3600, u=SERVER), jetzt=jetzt)
    d = P.lizenz(root)
    d["bis"] = jetzt + 10 * 365 * 86400
    P._speichern(root, d)
    assert P.stufe(root, jetzt + 60) == "premium"
    assert P.stufe(root, jetzt + 8 * 86400) is None    # hoechstens Frist (7 Tage) + Laufzeit (1 h)


def test_stufe_von_hand_hochsetzen_bringt_nichts(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 99999, u=SERVER))
    d = P.lizenz(root)
    d["stufe"] = "dev"
    P._speichern(root, d)
    assert P.stufe(root) is None


def test_verlaengerung_mit_zweitem_code_zaehlt(root):
    jetzt = time.time()
    k = P.kennung(root)
    P.einloesen(root, _code(k, "max", 86400, nonce="11" * 8, u=SERVER), jetzt=jetzt)
    P.einloesen(root, _code(k, "max", 86400, nonce="22" * 8, u=SERVER), jetzt=jetzt + 10)
    assert len(P.lizenz(root)["codes"]) == 2
    assert P.stufe(root, jetzt + 1.5 * 86400) == "max"  # zwei Tage gestapelt


def test_fremder_code_in_der_liste_zaehlt_nicht(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 60, u=SERVER))
    d = P.lizenz(root)
    d["codes"].append(_code("ffffffffffffffff", "premium", 10 * 365 * 86400, nonce="33" * 8))
    d["bis"] = time.time() + 10 * 365 * 86400
    P._speichern(root, d)
    assert P.stufe(root, time.time() + 30 * 86400) is None


# -- 0.55: Generator-Modus (ein Passwort schaltet Nova den Generator frei) ------------
def test_generator_passwort_logik(root, monkeypatch):
    import hashlib
    pw = "test-gen-passwort"
    monkeypatch.setattr(P, "_GEN_HASH", hashlib.pbkdf2_hmac("sha256", pw.encode(), P._GEN_SALZ, 300000).hex())
    assert P.gen_pin_ok(pw)
    assert not P.gen_pin_ok("falsch") and not P.gen_pin_ok("") and not P.gen_pin_ok("x" * 100)


def test_generator_modus_merken(root):
    assert P.generator_modus_an(root) is False
    P.generator_modus_setzen(root, True)
    assert P.generator_modus_an(root) is True
    P.generator_modus_setzen(root, False)
    assert P.generator_modus_an(root) is False


def test_generator_block_nur_im_modus(root):
    import assistant.personality as PR
    cfg = type("C", (), {"project_root": root})()
    assert "GENERATOR-MODUS" not in PR._entwickler_block(cfg)
    P.generator_modus_setzen(root, True)
    block = PR._entwickler_block(cfg)
    assert "GENERATOR-MODUS" in block and "/codegenerator" in block


def test_generator_datei_gesperrt(root):
    from assistant.config import PermissionSettings
    from assistant.permissions import PermissionError_, PermissionManager
    pm = PermissionManager(PermissionSettings(allow_full_filesystem=True, vollzugriff=True, safe_mode=False),
                           root / "ws", app_root=root, confirm_fn=lambda m, r: True)
    with pytest.raises(PermissionError_):
        pm.resolve_path(str(root / "data" / "generator.json"))


def test_generator_passwort_nur_als_hash(root):
    # das echte Passwort (nur in ~/.nova-premium/pins.json) darf NICHT im Quellcode stehen
    import json
    from pathlib import Path
    pins = Path.home() / ".nova-premium" / "pins.json"
    if not pins.exists():
        pytest.skip("keine pins.json")
    pw = json.loads(pins.read_text()).get("generator_modus")
    if not pw:
        pytest.skip("kein generator-Passwort gesetzt")
    assert P.gen_pin_ok(pw)                      # echtes Passwort oeffnet
    for mod in (P, __import__("assistant.personality", fromlist=["x"])):
        assert pw not in Path(mod.__file__).read_text(encoding="utf-8")


# -- 0.56: individuelle Abos (eigener Name + a la carte Funktionen) -------------------
def test_eigener_abo_name(root):
    k = P.kennung(root)
    P.einloesen(root, _code(k, "premium", 99999, u=SERVER, name="Premium Sandbox"))
    assert P.anzeigename(root) == "Premium Sandbox"
    assert "Premium Sandbox" in P.status_text(root)


def test_ohne_eigenen_namen_steht_die_stufe(root):
    P.einloesen(root, _code(P.kennung(root), "max", 99999, u=SERVER))
    assert P.anzeigename(root) == "Premium Max"


def test_features_werden_gespeichert(root):
    P.einloesen(root, _code(P.kennung(root), "premium", 99999, u=SERVER, f=["lernkarten", "gewohnheiten"]))
    assert P.features(root) == ["lernkarten", "gewohnheiten"]


def test_ohne_features_alle_der_stufe(root):
    P.einloesen(root, _code(P.kennung(root), "max", 99999, u=SERVER))
    assert P.features(root) is None


# -- 0.57: ein Schluessel allein wird NICHT mehr automatisch eingeloest (nur mit /novaaiupdate) ----------
def test_nackter_code_loest_nicht_automatisch_ein(tmp_path):
    from assistant.app.controller import AppController
    from assistant.config import load_config

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test"
    ereignisse: list = []
    ctl = AppController(cfg, ereignisse.append)
    try:
        code = "NOVA-" + "a" * 25 + "." + "b" * 25
        assert P.CODE_MUSTER.match(code)                      # sieht aus wie ein Code
        r = ctl.submit(code)
        assert r.get("ok") is True
        # NICHT eingeloest, kein Premium dazugekommen:
        assert not P.lizenz(cfg.project_root).get("stufe")
        # Stattdessen ein Hinweis auf den Befehl - und der Code ging NIE an die KI (kein user-Ereignis):
        texte = " ".join(str(e.get("text", "")) for e in ereignisse if isinstance(e, dict))
        assert "/novaaiupdate" in texte
        assert not any(isinstance(e, dict) and e.get("type") == "user" for e in ereignisse)
    finally:
        ctl.shutdown()


def test_premium_signatur_wechsel_loest_neustart(tmp_path, monkeypatch):
    """Aendert sich die echte Premium-Stufe, soll das Fenster neu starten (altes zu, neues auf)."""
    from assistant.app.controller import AppController
    from assistant.config import load_config

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = cfg.anthropic_api_key or "sk-ant-test"
    ctl = AppController(cfg, lambda e: None)
    try:
        monkeypatch.setattr(ctl, "_premium_signatur", lambda: "premium|")
        ctl._premium_sig = None
        assert ctl._premium_wechsel_pruefen() is False       # erste Pruefung: nur merken
        assert ctl._premium_sig == "premium|"
        neugestartet = []
        monkeypatch.setattr(ctl, "_premium_neustart", lambda grund: neugestartet.append(grund))
        monkeypatch.setattr(ctl, "_premium_signatur", lambda: "")   # Stufe weg (entzogen/abgelaufen)
        assert ctl._premium_wechsel_pruefen("entzug") is True
        assert neugestartet == ["entzug"]
    finally:
        ctl.shutdown()


# -- 0.58: eine gueltige Stufe ueberlebt Updates (Lizenz/Paket/Kennung liegen in data/, das der Updater nie anfasst)
def test_update_fasst_premium_dateien_nicht_an():
    from assistant import updater as U
    for rel in ("data/premium.json", "data/premium/paket.zip", "data/premium/paket.sig",
                "data/feedback_state.json"):
        assert U._is_protected(rel), rel        # -> Update behaelt die gekaufte Stufe


def test_paket_wird_automatisch_nachgeholt_wenn_es_fehlt(root, monkeypatch):
    """Stufe gilt, aber das Paket fehlt (z.B. frisch aufgesetzt) -> laden() holt es selbst wieder,
    statt Premium fallen zu lassen."""
    P.einloesen(root, _code(P.kennung(root), "max", 3600, u=SERVER))
    assert P.stufe(root) == "max"
    assert not P.paket_pfad(root).exists()
    geholt = []

    def fake_holen(r, **kw):
        geholt.append(True)
        ziel = P.paket_pfad(r)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(b"PK\x03\x04test")
        return {"version": "test"}

    monkeypatch.setattr(P, "paket_holen", fake_holen)
    P.laden(root, ctl=None, sperrung=False)     # ctl=None: laedt nichts, aber holt das Paket nach
    assert geholt == [True]
    assert P.paket_pfad(root).exists()


# -- Freischaltung (No-Code-Upgrade: Stufe per Geraete-Kennung vom Server) -----
def _frei(codes):
    import base64 as b64
    inner = json.dumps({"v": 1, "codes": list(codes), "stand": 1}, separators=(",", ":")).encode()
    huelle = {"daten": b64.urlsafe_b64encode(inner).rstrip(b"=").decode(),
              "sig": b64.b64encode(_sign(inner)).decode()}
    return json.dumps(huelle).encode()


def test_freischaltung_ohne_code(root, monkeypatch):
    """Frisches Geraet ohne Code: der Entwickler vergibt per Kennung eine Stufe - Nova wendet sie an."""
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", SERVER)
    k = P.kennung(root)
    assert P.stufe(root) is None
    code = _code(k, "max", 99999, nonce="f1" * 8, u=SERVER)
    st = P.freischaltung_pruefen(root, holen=lambda server: _frei([code]))
    assert st == "max" and P.stufe(root) == "max"


def test_freischaltung_nur_eigenes_geraet(root, monkeypatch):
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", SERVER)
    fremd = _code("0123456789abcdef", "max", 99999, nonce="f2" * 8, u=SERVER)
    assert P.freischaltung_pruefen(root, holen=lambda server: _frei([fremd])) is None
    assert P.stufe(root) is None


def test_freischaltung_hebt_premium_auf_max(root):
    """Geraet hat Premium (per Code) -> Freischaltliste mit Max-Code hebt es ohne neuen Code auf Max."""
    k = P.kennung(root)
    P.einloesen(root, _code(k, "premium", 99999, nonce="f3" * 8, u=SERVER))
    assert P.stufe(root) == "premium"
    maxcode = _code(k, "max", 99999, nonce="f4" * 8, u=SERVER)
    st = P.freischaltung_pruefen(root, holen=lambda server: _frei([maxcode]))
    assert st == "max" and P.stufe(root) == "max"


def test_freischaltung_doppelt_ist_harmlos(root, monkeypatch):
    """Zweimal pruefen loest denselben Code nicht doppelt ein (Nonce schon benutzt) - Stufe bleibt einfach."""
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", SERVER)
    k = P.kennung(root)
    code = _code(k, "max", 99999, nonce="f7" * 8, u=SERVER)
    P.freischaltung_pruefen(root, holen=lambda server: _frei([code]))
    assert P.freischaltung_pruefen(root, holen=lambda server: _frei([code])) is None
    assert P.stufe(root) == "max"


def test_freischaltung_unsigniert_ignoriert(root, monkeypatch):
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", SERVER)
    k = P.kennung(root)
    code = _code(k, "max", 99999, nonce="f5" * 8, u=SERVER)
    monkeypatch.setattr(P, "OEFFENTLICH_N", N + 4)   # Liste mit falschem Schluessel signiert
    assert P.freischaltung_pruefen(root, holen=lambda server: _frei([code])) is None
    assert P.stufe(root) is None


def test_sperre_schlaegt_freischaltung(root, monkeypatch):
    """Geraet steht auf der Sperrliste (ganzes Geraet) UND auf der Freischaltliste -> die Sperre gewinnt."""
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", SERVER)
    k = P.kennung(root)
    code = _code(k, "max", 99999, nonce="f6" * 8, u=SERVER)
    monkeypatch.setattr(P, "_freischaltliste_vom_server", lambda server, **kw: _frei([code]))
    monkeypatch.setattr(P, "_sperrliste_vom_server", lambda server, **kw: _sperrliste(kennungen=[k]))
    P.laden(root, ctl=None, sperrung=True)
    assert P.stufe(root) is None and P.lizenz(root).get("gesperrt")


# -- Funktionsuebersicht je Stufe (Anzeige) -----------------------------------
def test_uebersicht_listet_alle_stufen():
    u = P.uebersicht()                       # ohne root: keine aktive Stufe
    assert [s["stufe"] for s in u["stufen"]] == ["premium", "max", "dev"]
    assert u["aktiv"] is None and all(not s["aktiv"] for s in u["stufen"])
    assert all(s["funktionen"] for s in u["stufen"])        # jede Stufe nennt Funktionen


def test_uebersicht_markiert_aktive_stufe(root):
    P.einloesen(root, _code(P.kennung(root), "max", 99999, nonce="ab" * 8, u=SERVER))
    u = P.uebersicht(root)
    assert u["aktiv"] == "max" and u["aktiv_name"] == "Premium Max"
    aktive = [s for s in u["stufen"] if s["aktiv"]]
    assert len(aktive) == 1 and aktive[0]["stufe"] == "max"


def test_uebersicht_text_nennt_stufennamen(root):
    t = P.uebersicht_text(root)
    assert "Premium Max" in t and "Entwickler" in t and "keine Stufe" in t


# -- Eigentums-/Urheber-Wasserzeichen im Paket --------------------------------
def _paket_mit_eigentum(root, claim=None, kaputt=False):
    import zipfile as zf
    inner = json.dumps(claim or {"werk": "Nova Premium", "inhaber": "X"},
                       separators=(",", ":"), sort_keys=True).encode()
    sig = _sign(inner)
    if kaputt:
        sig = bytes([sig[0] ^ 1]) + sig[1:]
    huelle = {"daten": base64.b64encode(inner).decode(), "sig": base64.b64encode(sig).decode()}
    p = P.paket_pfad(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with zf.ZipFile(p, "w") as z:
        z.writestr("nova_premium/__init__.py", "VERSION='x'\n")
        z.writestr("nova_premium/_eigentum.json", json.dumps(huelle))
    return p


def test_eigentum_echt(root):
    _paket_mit_eigentum(root, {"werk": "Nova Premium", "inhaber": "GermanClaude / Nova"})
    info = P.eigentum_info(root)
    assert info and info["ok"] is True and info["inhaber"] == "GermanClaude / Nova"


def test_eigentum_gefaelscht(root):
    _paket_mit_eigentum(root, kaputt=True)      # Unterschrift verfaelscht
    info = P.eigentum_info(root)
    assert info and info["ok"] is False and "inhaber" not in info


def test_eigentum_ohne_paket(root):
    assert P.eigentum_info(root) is None        # noch kein Paket installiert


# -- Lizenzserver-Bootstrap (No-Code ohne vorher eingeloesten Code) ------------
def test_lizenzserver_lokal_bootstrap(root, monkeypatch):
    # Ohne alles: keine Adresse
    assert P.lizenzserver({}, root) == ""
    # Lokale Datei wird als Fallback genommen
    gespeichert = P.lizenzserver_lokal_setzen(root, "https://beispiel-nova.onrender.com/")
    assert gespeichert == "https://beispiel-nova.onrender.com"
    assert P.lizenzserver({}, root) == "https://beispiel-nova.onrender.com"
    # Code-Adresse hat Vorrang vor der lokalen Datei
    assert P.lizenzserver({"server": "https://aus-dem-code.example.com"}, root) \
        == "https://aus-dem-code.example.com"
    # Umgebungsvariable greift auch ohne Datei/Code
    P.lizenzserver_lokal_setzen(root, "")
    assert P.lizenzserver({}, root) == ""
    monkeypatch.setenv("NOVA_LIZENZSERVER_URL", "https://via-env.onrender.com")
    assert P.lizenzserver({}, root) == "https://via-env.onrender.com"


def test_lizenzserver_lokal_setzen_prueft_adresse(root):
    with pytest.raises(P.PremiumFehler):
        P.lizenzserver_lokal_setzen(root, "ftp://boese")
    with pytest.raises(P.PremiumFehler):
        P.lizenzserver_lokal_setzen(root, "einfach-text")
    # http nur lokal erlaubt
    assert P.lizenzserver_lokal_setzen(root, "http://127.0.0.1:8000") == "http://127.0.0.1:8000"


def test_lizenzserver_txt_ist_gesperrt(tmp_path):
    pm = PermissionManager(PermissionSettings(), tmp_path / "ws", app_root=tmp_path)
    assert pm.ist_gesperrt((tmp_path / "data" / "lizenzserver.txt").resolve())


def test_lebenszeit_code_nicht_auf_10_jahre_gekappt(root):
    # Ein 'Lebenszeit'-Code (1000 Jahre) darf nicht mehr auf 10 Jahre gestutzt werden.
    k = P.kennung(root)
    jetzt = time.time()
    lebenszeit = 1000 * 365 * 86400
    P.einloesen(root, _code(k, "max", dauer=lebenszeit, u=SERVER), jetzt=jetzt)
    assert P.stufe(root, jetzt + 50 * 365 * 86400) == "max"   # nach 50 Jahren noch aktiv
