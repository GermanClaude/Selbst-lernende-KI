"""Anrufe ueber Bland AI - ohne echtes Netz (Transport eingespeist)."""
import pytest

from assistant import anruf as A
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager
from assistant.tools import ToolContext, build_registry


class FakeBland:
    def __init__(self, status_folge=None, fehler=None):
        self.aufrufe = []
        self.status_folge = list(status_folge or [{"status": "completed", "answered_by": "human",
                                                    "summary": "Er sagt: ja, loeschen.",
                                                    "concatenated_transcript": "assistant: Hallo user: Ja"}])
        self.fehler = fehler

    def __call__(self, key, method, pfad, body, timeout):
        self.aufrufe.append((method, pfad, body))
        if self.fehler:
            raise self.fehler
        if method == "POST":
            return {"status": "success", "call_id": "c-123"}
        return self.status_folge.pop(0) if len(self.status_folge) > 1 else self.status_folge[0]


def test_nummern_werden_e164():
    assert A.normalisiere_nummer("0171 1234567") == "+491711234567"
    assert A.normalisiere_nummer("+49 (171) 123-4567") == "+491711234567"
    assert A.normalisiere_nummer("0049 171 1234567") == "+491711234567"
    assert A.normalisiere_nummer("+1 415 555 0100") == "+14155550100"
    assert A.normalisiere_nummer("hallo") is None and A.normalisiere_nummer("") is None
    assert A.maskiere("+491711234567") == "+49 ... 4567"


def test_auftrag_an_bland():
    body = A.anruf_body("+491711234567", "Darf ich die alten Backups loeschen?", "Nova", max_minuten=99)
    assert body["phone_number"] == "+491711234567" and body["language"] == "de"
    assert body["max_duration"] == 15 and body["wait_for_greeting"] is True       # gedeckelt
    assert "alten Backups" in body["task"] and body["first_sentence"].startswith("Hallo, hier ist Nova")
    assert body["voicemail"]["action"] == "leave_message"
    assert "voice" not in body                                                     # nur wenn gesetzt
    assert set(body) <= {"phone_number", "task", "first_sentence", "language", "max_duration",
                         "wait_for_greeting", "record", "voicemail", "voice"}       # Bland lehnt Unbekanntes ab


def test_anrufen_und_warten():
    fake = FakeBland(status_folge=[{"status": "queued", "queue_status": "started"},
                                   {"status": "completed", "answered_by": "human", "summary": "Ja, loeschen."}])
    b = A.Bland("KEY", transport=fake)
    assert b.anrufen("+491711234567", "Frage", "Nova") == "c-123"
    info = A.warte_auf_ende(b, "c-123", max_sekunden=60, intervall=0, schlafen=lambda s: None)
    assert info["status"] == "completed"
    text = A.ergebnis_text(info)
    assert "Ja, loeschen." in text and "human" in text


def test_mailbox_wird_erkannt():
    text = A.ergebnis_text({"status": "completed", "answered_by": "voicemail"})
    assert "Mailbox" in text


def test_abgelehnter_anruf():
    b = A.Bland("KEY", transport=lambda *a: {"status": "error", "message": "invalid phone"})
    with pytest.raises(A.AnrufFehler):
        b.anrufen("+491711234567", "x")


def test_tageslimit(tmp_path):
    assert A.heute_anzahl(tmp_path) == 0
    A.heute_zaehlen(tmp_path)
    A.heute_zaehlen(tmp_path)
    assert A.heute_anzahl(tmp_path) == 2


# ------------------------------------------------------------------ Werkzeug
def _ctx(tmp_path, confirm=lambda m, r: True, away=False):
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=False), tmp_path, confirm_fn=confirm)
    pm.away = away
    return ToolContext(permissions=pm, memory=None, extra={"app_root": tmp_path, "ki_name": lambda: "Nova"})


@pytest.fixture
def eingerichtet(monkeypatch):
    monkeypatch.setenv("BLAND_API_KEY", "KEY")
    monkeypatch.setenv("ANRUF_NUMMER", "0171 1234567")
    fake = FakeBland()
    monkeypatch.setattr(A, "_urllib_transport", fake)
    monkeypatch.setattr(A.Bland, "__init__", lambda self, key, transport=fake: (setattr(self, "key", key),
                                                                               setattr(self, "transport", fake))[0])
    return fake


def test_werkzeug_hat_kein_nummernfeld():
    tool = build_registry().get("anrufen")
    assert tool is not None
    assert set(tool.input_schema["properties"]) == {"anliegen", "warten"}   # niemand anderen anrufen


def test_werkzeug_ohne_einrichtung(tmp_path, monkeypatch):
    monkeypatch.delenv("BLAND_API_KEY", raising=False)
    monkeypatch.delenv("ANRUF_NUMMER", raising=False)
    out, _ = build_registry().execute(_ctx(tmp_path), "anrufen", {"anliegen": "Hallo"})
    assert "/anruf schluessel" in out


def test_werkzeug_am_pc_fragt_nach(tmp_path, eingerichtet):
    gefragt = []
    out, _ = build_registry().execute(_ctx(tmp_path, confirm=lambda m, r: gefragt.append(m) or True),
                                      "anrufen", {"anliegen": "Download fertig"})
    assert gefragt and "+49 ... 4567" in gefragt[0]
    assert eingerichtet.aufrufe[0][2]["phone_number"] == "+491711234567"
    assert "ja, loeschen" in out.lower()


def test_werkzeug_am_pc_abgelehnt_ruft_nicht_an(tmp_path, eingerichtet):
    build_registry().execute(_ctx(tmp_path, confirm=lambda m, r: False), "anrufen", {"anliegen": "x"})
    assert eingerichtet.aufrufe == []


def test_werkzeug_im_afk_ohne_nachfrage(tmp_path, eingerichtet):
    out, _ = build_registry().execute(_ctx(tmp_path, confirm=lambda m, r: pytest.fail("im AFK nicht fragen"),
                                           away=True), "anrufen", {"anliegen": "Wichtig!", "warten": False})
    assert "gestartet" in out and len(eingerichtet.aufrufe) == 1


def test_werkzeug_kostenbremse(tmp_path, eingerichtet):
    for _ in range(A.MAX_PRO_TAG):
        A.heute_zaehlen(tmp_path)
    out, _ = build_registry().execute(_ctx(tmp_path, away=True), "anrufen", {"anliegen": "x"})
    assert "Kostenbremse" in out and eingerichtet.aufrufe == []


# ------------------------------------------------------------------ Vorstellungs-Skript (Persona)
def test_standard_skript_stellt_nova_vor_und_ist_ehrlich():
    task = A.anruf_body("+491711234567", "Download fertig - entpacken?", "Nova")["task"]
    assert "Du bist Nova" in task and "{name}" not in task and "{anliegen}" not in task
    assert "nie als Mensch" in task                       # ehrlich: KI gibt sich nicht als Mensch aus
    assert "Passwoerter" in task                          # keine Geheimnisse am Telefon
    assert task.rstrip().endswith("Download fertig - entpacken?")
    assert len(task) < 2000                               # Bland empfiehlt kurze Auftraege


def test_eigenes_skript_aus_der_datei(tmp_path):
    assert A.persona_text(tmp_path) == A.PERSONA_STANDARD
    A.persona_pfad(tmp_path).parent.mkdir(parents=True)
    A.persona_pfad(tmp_path).write_text("Du bist {name} vom Schreibtisch. Thema: {anliegen}", encoding="utf-8")
    task = A.anruf_body("+491711234567", "Pizza bestellt?", "Aria", persona=A.persona_text(tmp_path))["task"]
    assert task == "Du bist Aria vom Schreibtisch. Thema: Pizza bestellt?"


def test_skript_ohne_platzhalter_bekommt_das_anliegen_angehaengt():
    task = A.persona_fuellen("Sei nett. {nicht ersetzen}", "Nova", "Ruf zurueck")
    assert "{nicht ersetzen}" in task and task.endswith("Ruf zurueck")
