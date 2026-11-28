"""0.61: Der Codegenerator liegt im privaten Repo nur VERSCHLUESSELT (mit dem Generator-Passwort).
Nova entschluesselt ihn erst lokal. Dieser Test pinnt das Wire-Format unabhaengig vom Verschluessel-Skript."""
import hashlib
import hmac
import secrets
import zlib

import pytest

from assistant import premium as P


def _enc(klartext: bytes, passwort: str) -> bytes:
    """Baut einen Generator-Blob genau wie werkzeuge/generator_verschluesseln.py - hier bewusst eigenstaendig,
    damit der Test anschlaegt, falls sich das Format in premium.py verschiebt."""
    daten = zlib.compress(klartext, 9)
    salz, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    roh = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), salz, 200000, dklen=64)
    k_enc, k_mac = roh[:32], roh[32:]
    strom = b"".join(hmac.new(k_enc, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
                     for i in range((len(daten) + 31) // 32))[:len(daten)]
    geheim = (int.from_bytes(daten, "big") ^ int.from_bytes(strom, "big")).to_bytes(len(daten), "big") if daten else b""
    marke = hmac.new(k_mac, b"NOVAGEN1" + salz + nonce + geheim, hashlib.sha256).digest()
    return b"NOVAGEN1" + salz + nonce + marke + geheim


def test_round_trip():
    quelle = b"print('ich bin der geheime Generator')\n" * 50
    assert P.generator_entschluesseln(_enc(quelle, "geheim-123"), "geheim-123") == quelle


def test_binaer_round_trip():
    exe = bytes(range(256)) * 400                     # wie eine .exe: beliebige Bytes
    assert P.generator_entschluesseln(_enc(exe, "pw"), "pw") == exe


def test_falsches_passwort_wird_abgelehnt():
    blob = _enc(b"quellcode", "richtig")
    with pytest.raises(P.PremiumFehler, match="passt nicht"):
        P.generator_entschluesseln(blob, "falsch")


def test_manipulierter_blob_faellt_durch():
    blob = bytearray(_enc(b"quellcode", "pw"))
    blob[-1] ^= 0x01                                  # ein Bit im Geheimtext kippen
    with pytest.raises(P.PremiumFehler):
        P.generator_entschluesseln(bytes(blob), "pw")


def test_fremdes_format_faellt_durch():
    with pytest.raises(P.PremiumFehler, match="beschaedigt|Format"):
        P.generator_entschluesseln(b"kein nova-generator-blob", "pw")


def test_holen_entschluesselt_lokal(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PREMIUM_TOKEN", "github_pat_test")
    quelle = b"# der echte Generator\nVERSION='x'\n"
    holen = lambda token, pfad: _enc(quelle, "pw")     # noqa: E731 - der "Server" liefert nur den Blob
    pfad = P.codegenerator_holen(tmp_path, holen=holen, passwort="pw")
    assert pfad.read_bytes() == quelle and pfad.name == "codegenerator.py"


def test_holen_ohne_passwort_geht_nicht(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PREMIUM_TOKEN", "github_pat_test")
    with pytest.raises(P.PremiumFehler, match="Generator-Passwort"):
        P.codegenerator_holen(tmp_path, holen=lambda t, p: b"", passwort="")


def test_holen_ohne_token_geht_nicht(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PREMIUM_TOKEN", raising=False)
    with pytest.raises(P.PremiumFehler, match="NOVA_PREMIUM_TOKEN"):
        P.codegenerator_holen(tmp_path, holen=lambda t, p: b"", passwort="pw")
