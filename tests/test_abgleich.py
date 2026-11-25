"""Gedaechtnis-Abgleich PC <-> Cloud ueber ein (hier nachgebautes) GitHub-Repo, verschluesselt."""
import base64
import hashlib
import time

import pytest

from assistant import abgleich as A
from assistant.app.controller import _mask_key
from assistant.memory import Memory


@pytest.fixture(autouse=True)
def schnell(monkeypatch):
    monkeypatch.setattr(A, "_RUNDEN", 1000)          # Tests: weniger PBKDF2-Runden
    A._schluessel_cache.clear()


class FakeGitHub:
    """Ein Repo mit einer Datei - mit sha-Pruefung wie bei GitHub (Konflikt, wenn jemand dazwischen schrieb)."""

    def __init__(self, repo_da=True):
        self.inhalt, self.sha, self.repo_da, self.aufrufe, self.konflikte = None, None, repo_da, [], 0

    def __call__(self, token, method, pfad, body, timeout):
        self.aufrufe.append((method, pfad))
        if pfad == "/repos/ich/nova-gedaechtnis":
            return (200, {}) if self.repo_da else (404, {"message": "Not Found"})
        if method == "GET":
            if self.inhalt is None:
                return 404, {"message": "Not Found"}
            return 200, {"sha": self.sha, "content": base64.b64encode(self.inhalt).decode()}
        if self.konflikte:
            self.konflikte -= 1
            self.sha = "fremd-" + str(time.time())     # andere Nova hat gerade geschrieben
            return 409, {"message": "conflict"}
        if body.get("sha") != self.sha:
            return 409, {"message": "sha passt nicht"}
        self.inhalt = base64.b64decode(body["content"])
        self.sha = hashlib.sha1(self.inhalt).hexdigest()
        return 200, {"content": {"sha": self.sha}}


def _nova(tmp_path, name, gh):
    m = Memory(tmp_path / f"{name}.sqlite3")
    return m, A.Abgleich(m, "ich/nova-gedaechtnis", "TOKEN", "geheimes passwort", transport=gh)


def _inhalte(m):
    return sorted(f["content"] for f in m.exportieren()["fakten"])


def test_verschluesselung_hin_und_zurueck():
    daten = {"fakten": [{"content": "Mag keinen Kaffee"}]}
    blob = A.verschluesseln(daten, "pw-123456")
    assert b"Kaffee" not in blob and A.entschluesseln(blob, "pw-123456") == daten
    with pytest.raises(A.AbgleichFehler, match="Passwort"):
        A.entschluesseln(blob, "falsch")
    kaputt = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(A.AbgleichFehler):
        A.entschluesseln(kaputt, "pw-123456")
    assert A.verschluesseln(daten, "pw-123456") != blob                  # jedes Mal neu verschluesselt


def test_pc_und_cloud_lernen_voneinander(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    cloud, cloud_ab = _nova(tmp_path, "cloud", gh)
    pc.remember("Heisst mit Vornamen Max", "person")
    pc.add_episode("Ueber den Urlaub gesprochen")
    assert "1 neu" not in pc_ab.jetzt()                                  # erster Abgleich: legt nur ab
    cloud.remember("Mag Pizza", "vorliebe")
    assert "1 neu" in cloud_ab.jetzt()                                   # holt Max
    assert _inhalte(cloud) == ["Heisst mit Vornamen Max", "Mag Pizza"]
    assert cloud.recent_episodes() == ["Ueber den Urlaub gesprochen"]
    pc_ab.jetzt()
    assert _inhalte(pc) == ["Heisst mit Vornamen Max", "Mag Pizza"]
    assert b"Pizza" not in gh.inhalt                                     # GitHub sieht nur Zeichensalat


def test_vergessen_kommt_nicht_zurueck(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    cloud, cloud_ab = _nova(tmp_path, "cloud", gh)
    fid = pc.remember("Alte Adresse: Musterweg 1")
    pc_ab.jetzt()
    cloud_ab.jetzt()
    assert "Alte Adresse: Musterweg 1" in _inhalte(cloud)
    pc.forget(fid)
    pc_ab.jetzt()
    assert "vergessen" in cloud_ab.jetzt()
    assert _inhalte(cloud) == [] and _inhalte(pc) == []
    time.sleep(0.01)
    cloud.remember("Alte Adresse: Musterweg 1")                          # spaeter neu gelernt -> bleibt
    cloud_ab.jetzt()
    pc_ab.jetzt()
    assert _inhalte(pc) == ["Alte Adresse: Musterweg 1"]


def test_neueres_gewinnt(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    cloud, cloud_ab = _nova(tmp_path, "cloud", gh)
    pc.remember("Lieblingsfarbe blau", "vorliebe", importance=2)
    pc_ab.jetzt()
    cloud_ab.jetzt()
    time.sleep(0.01)
    cloud.remember("Lieblingsfarbe blau", "vorliebe", importance=5)
    cloud_ab.jetzt()
    assert "1 aktualisiert" in pc_ab.jetzt()
    assert pc.top_facts()[0].importance == 5


def test_konflikt_wird_wiederholt(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    pc.remember("x")
    pc_ab.jetzt()
    pc.remember("y")
    gh.konflikte = 1
    pc_ab.jetzt()
    assert sorted(f["content"] for f in A.entschluesseln(gh.inhalt, "geheimes passwort")["fakten"]) == ["x", "y"]


def test_ohne_aenderung_kein_netz(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    pc.remember("x")
    pc_ab.jetzt()
    vorher = len(gh.aufrufe)
    assert pc_ab.jetzt(nur_wenn_geaendert=True) == "unveraendert" and len(gh.aufrufe) == vorher
    assert pc_ab.jetzt() == "schon aktuell"                              # nur ein Blick, nichts abgelegt
    assert [m for m, _ in gh.aufrufe[vorher:]] == ["GET"]


def test_aenderung_baut_den_prompt_neu(tmp_path):
    gh = FakeGitHub()
    pc, pc_ab = _nova(tmp_path, "pc", gh)
    cloud, cloud_ab = _nova(tmp_path, "cloud", gh)
    pc.remember("x")
    pc_ab.jetzt()
    neu = []
    cloud_ab.bei_aenderung = lambda: neu.append(1)
    cloud_ab.jetzt()
    assert neu == [1]


def test_falsches_repo_und_passwort(tmp_path):
    m, ab = _nova(tmp_path, "pc", FakeGitHub(repo_da=False))
    with pytest.raises(A.AbgleichFehler, match="gibt es nicht"):
        ab.jetzt()
    gh = FakeGitHub()
    m1, ab1 = _nova(tmp_path, "a", gh)
    m1.remember("x")
    ab1.jetzt()
    m2 = Memory(tmp_path / "b.sqlite3")
    with pytest.raises(A.AbgleichFehler, match="Passwort"):
        A.Abgleich(m2, "ich/nova-gedaechtnis", "TOKEN", "anderes", transport=gh).jetzt()
    assert _inhalte(m2) == []                                            # nichts kaputtgemacht


def test_eingerichtet_nur_mit_allen_werten(monkeypatch):
    for k in ("NOVA_ABGLEICH_REPO", "NOVA_ABGLEICH_TOKEN", "NOVA_ABGLEICH_PASSWORT"):
        monkeypatch.delenv(k, raising=False)
    assert not A.eingerichtet()
    monkeypatch.setenv("NOVA_ABGLEICH_REPO", "ich/nova-gedaechtnis")
    monkeypatch.setenv("NOVA_ABGLEICH_TOKEN", "t")
    assert not A.eingerichtet()
    monkeypatch.setenv("NOVA_ABGLEICH_PASSWORT", "geheim123")
    assert A.eingerichtet()


def test_einrichten_wird_im_verlauf_verdeckt():
    text, anzeige = _mask_key("/abgleich einrichten ich/nova-gedaechtnis github_pat_ABC mein passwort")
    assert "github_pat_ABC" not in anzeige and "passwort" not in anzeige.replace("/abgleich einrichten", "")
