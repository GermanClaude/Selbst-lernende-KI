"""AFK-Modus: allein weiterarbeiten - sicher, begrenzt, mit Bericht."""
import time

import pytest

from assistant.abwesend import AfkSession, model_text_for, run_session, settings_session, sounds_like_away
from assistant.config import AfkSettings, load_config
from assistant.permissions import PermissionError_, PermissionManager, Risk
from assistant.tools import ToolContext, build_registry


def test_away_rules_are_strict_and_never_ask(tmp_path):
    cfg = load_config(tmp_path)
    cfg.permissions.auto_confirm = True
    cfg.permissions.safe_mode = False
    cfg.permissions.allow_full_filesystem = True
    asked = []
    pm = PermissionManager(cfg.permissions, tmp_path / "ws", confirm_fn=lambda m, r: asked.append(m) or True)
    (tmp_path / "ws").mkdir()
    old = tmp_path / "ws" / "alt.txt"
    old.write_text("wichtig", encoding="utf-8")
    pm.begin_away()
    assert pm.check(Risk.SAFE, "lesen").allowed
    assert not pm.check(Risk.MODERATE, "Aussehen aendern").allowed   # nur Datei-Aktionen nach check_path_write
    assert not pm.check(Risk.DANGEROUS, "loeschen").allowed
    assert not pm.check_shell("dir").allowed
    assert not pm.confirm_always("Autostart").allowed
    assert not pm.check_path_write(old).allowed                       # nichts Bestehendes ueberschreiben
    assert not pm.check_path_write(tmp_path / "aussen.txt").allowed     # nur im Arbeitsordner
    new = tmp_path / "ws" / "entwurf.txt"
    assert pm.check_path_write(new).allowed
    assert pm.check(Risk.MODERATE, "Neu anlegen").allowed             # genau diese Datei-Aktion
    assert not pm.check(Risk.MODERATE, "noch etwas").allowed          # Freigabe gilt nur einmal
    new.write_text("x", encoding="utf-8")
    assert pm.check_path_write(new).allowed                           # eigene neue Datei: weiter bearbeiten
    with pytest.raises(PermissionError_):
        pm.resolve_path(str(tmp_path / ".env"))                       # lesen nur im Arbeitsordner
    assert not asked
    pm.end_away()
    assert pm.check_path_write(old).allowed and pm.check(Risk.DANGEROUS, "x").allowed


def test_tools_respect_the_away_rules(tmp_path):
    cfg = load_config(tmp_path)
    cfg.permissions.auto_confirm = True
    cfg.permissions.safe_mode = False
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "alt.txt").write_text("wichtig", encoding="utf-8")
    pm = PermissionManager(cfg.permissions, ws)
    session = AfkSession()
    ctx = ToolContext(permissions=pm, extra={"afk_session": session, "config": cfg})
    reg = build_registry()
    pm.begin_away()
    out = reg.get("datei_schreiben").run(ctx, pfad="alt.txt", inhalt="kaputt")
    assert (ws / "alt.txt").read_text(encoding="utf-8") == "wichtig", out
    reg.get("datei_schreiben").run(ctx, pfad="neu.txt", inhalt="Entwurf")
    assert (ws / "neu.txt").read_text(encoding="utf-8") == "Entwurf"
    with pytest.raises(PermissionError_):
        reg.get("datei_loeschen").run(ctx, pfad="alt.txt")
    assert (ws / "alt.txt").exists()
    assert "Nicht" in reg.get("gehirn_einstellen").run(ctx, aktion="setzen", denken="maximal")
    assert "Nicht" in reg.get("vergessen").run(ctx, id=1)
    with pytest.raises(PermissionError_):
        reg.get("app_anpassen").run(ctx, aktion="zuruecksetzen")
    assert "einfache Adressen" in reg.get("web_abrufen").run(ctx, url="https://x.example/?geheim=sk-123")
    tool = reg.get("abwesenheit")
    tool.run(ctx, aktion="notiz", text="Recherche fertig")
    tool.run(ctx, aktion="vorschlag", text="alt.txt loeschen")
    tool.run(ctx, aktion="frage", text="Welche Farbe?")
    tool.run(ctx, aktion="fertig", text="Alles erledigt")
    assert session.notes == ["Recherche fertig"] and session.proposals == ["alt.txt loeschen"]
    assert session.done == "Alles erledigt"
    report = session.report()
    assert "Vorschlaege" in report and "alt.txt loeschen" in report and "Welche Farbe?" in report


def test_session_stops_at_its_limits():
    s = AfkSession(max_rounds=3, pause_seconds=0)
    prompts = []
    assert run_session(s, prompts.append, cost_eur=lambda: 0.0) == "schritte"
    assert len(prompts) == 3 and "Schritt 3 von hoechstens 3" in prompts[-1]

    spent = [0.0]

    def costly(prompt):
        spent[0] += 0.4

    s = AfkSession(max_rounds=10, max_eur=1.0, pause_seconds=0)
    assert run_session(s, costly, cost_eur=lambda: spent[0]) == "budget"
    assert s.rounds == 3

    s = AfkSession(max_rounds=10, pause_seconds=0)
    s.started = time.time() - 3 * 3600
    assert run_session(s, prompts.append, cost_eur=lambda: 0.0) == "zeit"

    s = AfkSession(max_rounds=10, pause_seconds=0)

    def interrupted(prompt):
        raise KeyboardInterrupt

    assert run_session(s, interrupted, cost_eur=lambda: 0.0) == "zurueck"


def test_watchdog_stops_an_expensive_step_in_the_middle():
    import threading

    spent, cancelled = [0.0], threading.Event()

    def runaway(prompt):  # ein Schritt, der immer weiter Geld ausgibt, bis er angehalten wird
        while not cancelled.is_set():
            spent[0] += 0.05
            time.sleep(0.01)
        raise KeyboardInterrupt  # so endet eine angehaltene Antwort

    s = AfkSession(max_rounds=10, max_eur=0.5, pause_seconds=0)
    assert run_session(s, runaway, cost_eur=lambda: spent[0], cancel=cancelled.set, watch_interval=0.02) == "budget"
    assert s.rounds == 1 and not s.stop_event.is_set() and spent[0] < 1.5


def test_settings_and_hints():
    s = settings_session(AfkSettings(max_minuten=60, max_euro=0.5), auftrag="  Urlaub planen ", minutes=9999)
    assert s.auftrag == "Urlaub planen" and s.max_minutes == 24 * 60 and s.max_eur == 0.5
    assert "Urlaub planen" in s.round_prompt()
    assert "keinen ausdruecklichen Auftrag" in AfkSession().round_prompt()
    assert sounds_like_away("Ich bin jetzt AFK") and sounds_like_away("bin mal kurz weg")
    assert not sounds_like_away("Wie weit ist es nach Berlin?")
    assert "abwesenheit" in model_text_for("bin jetzt für länger weg")
    assert model_text_for("bin weg", active=True) == "bin weg"
    back = model_text_for("Hallo", back=(42, "BERICHT"))
    assert back.startswith("[Dein Mensch ist zurueck - er war 42 Min.") and back.endswith("Hallo")


def test_terminal_afk_mode(tmp_path, capsys):
    from assistant.ui.cli import CLI
    from tests._fakes import AnthroClient, anthro_msg, text_block, tool_use_block

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.afk.pause_sekunden = 0
    cli = CLI(cfg)
    script = [(anthro_msg([tool_use_block("abwesenheit", "t1", {"aktion": "frage", "text": "Welche Stadt?"})],
                          stop_reason="tool_use"), []),
              (anthro_msg([tool_use_block("abwesenheit", "t2", {"aktion": "fertig", "text": "Plan steht"})],
                          stop_reason="tool_use"), []),
              (anthro_msg([text_block("ok")]), [])]
    cli.brain.provider.client = AnthroClient(script)
    try:
        cli._afk_command(["Reise", "planen"])
        out = capsys.readouterr().out
        assert "[AFK-Modus]" in out and "Auftrag: Reise planen" in out
        assert "Welche Stadt?" in out and "Plan steht" in out
        assert not cli.permissions.away and "afk_session" not in cli.tool_ctx.extra
        assert cli._afk_return is not None and "Welche Stadt?" in cli._afk_return[1]
    finally:
        cli.memory.close()
