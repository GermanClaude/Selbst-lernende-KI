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
    (tmp_path / "data").mkdir()
    return tmp_path


# -- Code und Lizenz ----------------------------------------------------------
def test_gueltiger_code_schaltet_frei(root):
    k = P.kennung(root)
    assert P.stufe(root) is None
    P.einloesen(root, _code(k, "max", 3600, s="paket-schluessel", g="token"))
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
    P.einloesen(root, _code(k, "premium", dauer=60, s="x"), jetzt=jetzt)
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
    P.einloesen(root, _code(k, "max", 99999, s="x"))
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
    assert P.simulation_umschalten(root, P.SIM_PIN) == "test_an"
    assert P.simulation_laden(root, ctl) == "max" and "premium_demo" in ctl.registry.n
    assert P.simulation_umschalten(root, P.SIM_PIN) == "test_aus"
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
