"""0.52: Lizenzserver - das Premium-Paket gibt nur die Cloud-Nova heraus, und nur gegen einen gueltigen Code.
Codes enthalten nichts Geheimes; der Repo-Token liegt allein beim Server."""
import base64
import http.client
import io
import json
import time
import zipfile

import pytest

from assistant import lizenzserver as L
from assistant import premium as P
from assistant.app.server import AppServer

from .test_premium import N, _code, _sign, _sperrliste

KENNUNG = "0123456789abcdef"


def _zip():
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("nova_premium/__init__.py", "VERSION = '9'\n")
    return puffer.getvalue()


ZIP = _zip()


def _repo(sperre=None, sig=None, ohne_sperrliste=True):
    dateien = {L.PAKET_ZIP: ZIP,
               L.PAKET_META: json.dumps({"sig": sig or base64.b64encode(_sign(ZIP)).decode(),
                                         "info": {"version": "9"}}).encode()}
    if sperre is not None:
        dateien[P.SPERR_PFAD] = sperre

    def holen(pfad):
        if pfad not in dateien:
            raise L.LizenzFehler("nicht_gefunden")
        return dateien[pfad]
    return holen


@pytest.fixture(autouse=True)
def schluessel(monkeypatch):
    monkeypatch.setattr(P, "OEFFENTLICH_N", N)


def test_gueltiger_code_bekommt_paket():
    antwort = L.paket_fuer_code(_code(KENNUNG, "premium", 3600), KENNUNG, holen=_repo())
    assert antwort["ok"] and base64.b64decode(antwort["zip"]) == ZIP and antwort["info"]["version"] == "9"


@pytest.mark.parametrize("code, kennung, grund", [
    ("NOVA-quatsch.quatsch", KENNUNG, "ungueltig"),
    (None, "ffffffffffffffff", "anderes_geraet"),
    (None, "", "anderes_geraet"),
])
def test_falsche_anfragen(code, kennung, grund):
    with pytest.raises(L.LizenzFehler, match=grund):
        L.paket_fuer_code(code or _code(KENNUNG), kennung, holen=_repo())


def test_aus_code_bekommt_nichts():
    with pytest.raises(L.LizenzFehler, match="keine_stufe"):
        L.paket_fuer_code(_code(KENNUNG, "aus"), KENNUNG, holen=_repo())


def test_abgelaufener_code():
    alt = time.time() - 30 * 86400
    with pytest.raises(L.LizenzFehler, match="abgelaufen"):
        L.paket_fuer_code(_code(KENNUNG, "premium", 3600, frist=1, jetzt=alt), KENNUNG, holen=_repo())


def test_gesperrter_code():
    code = _code(KENNUNG, nonce="dead" * 4)
    with pytest.raises(L.LizenzFehler, match="gesperrt"):
        L.paket_fuer_code(code, KENNUNG, holen=_repo(sperre=_sperrliste(nonces=["deaddeaddeaddead"])))
    with pytest.raises(L.LizenzFehler, match="gesperrt"):
        L.paket_fuer_code(code, KENNUNG, holen=_repo(sperre=_sperrliste(kennungen=[KENNUNG])))


def test_unsigniertes_paket_wird_nicht_ausgeliefert():
    with pytest.raises(L.LizenzFehler, match="paket_unsigniert"):
        L.paket_fuer_code(_code(KENNUNG), KENNUNG, holen=_repo(sig=base64.b64encode(b"x" * 256).decode()))


def test_aus_ohne_token(monkeypatch):
    monkeypatch.setenv("NOVA_LIZENZSERVER", "1")
    monkeypatch.delenv("NOVA_PREMIUM_REPO_TOKEN", raising=False)
    assert not L.aktiv()
    monkeypatch.setenv("NOVA_PREMIUM_REPO_TOKEN", "github_pat_test")
    assert L.aktiv()


# -- ueber HTTP -----------------------------------------------------------------
class FakeCtl:
    def state(self):
        return {"ok": True}


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("NOVA_LIZENZSERVER", "1")
    monkeypatch.setenv("NOVA_PREMIUM_REPO_TOKEN", "github_pat_GEHEIM_test")
    monkeypatch.setattr(L, "repo_holen", _repo(sperre=_sperrliste()))
    s = AppServer(lambda b: FakeCtl(), port=0, token="t" * 30, hosts="*")
    s.start()
    yield s
    s.stop()



def _post(server, body, roh=None):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    daten = roh if roh is not None else json.dumps(body).encode()
    c.request("POST", "/lizenz/paket", body=daten, headers={"Host": "nova.test", "Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, r.read()


def test_http_paket_ohne_nova_token(server):
    status, roh = _post(server, {"code": _code(KENNUNG), "kennung": KENNUNG})
    assert status == 200 and json.loads(roh)["ok"]
    assert b"GEHEIM" not in roh                 # der Repo-Token geht nie nach aussen


def test_http_falscher_code_und_bremse(server):
    for _ in range(AppServer.SPERRE_VERSUCHE):
        status, roh = _post(server, {"code": "NOVA-falsch.falsch", "kennung": KENNUNG})
        assert status == 403 and b"GEHEIM" not in roh
    assert _post(server, {"code": _code(KENNUNG), "kennung": KENNUNG})[0] == 429   # Durchprobieren gebremst


def test_http_zu_gross(server):
    assert _post(server, None, roh=b"{" + b"a" * 9000 + b"}")[0] == 400


def test_http_sperrliste(server):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    c.request("GET", "/lizenz/sperrliste", headers={"Host": "nova.test"})
    r = c.getresponse()
    assert r.status == 200 and P.sperrliste_lesen(r.read()) is not None


def test_http_aus_wenn_nicht_eingeschaltet(monkeypatch):
    monkeypatch.delenv("NOVA_LIZENZSERVER", raising=False)
    s = AppServer(lambda b: FakeCtl(), port=0, token="t" * 30, hosts="*")
    s.start()
    try:
        assert _post(s, {"code": "x", "kennung": "y"})[0] == 404
    finally:
        s.stop()
