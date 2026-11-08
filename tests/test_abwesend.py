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


def test_refused_autostart_write_leaves_no_permission_behind(tmp_path):
    cfg = load_config(tmp_path)
    cfg.permissions.auto_confirm = True
    ws = tmp_path / "ws"
    (ws / ".config" / "autostart").mkdir(parents=True)
    pm = PermissionManager(cfg.permissions, ws, app_root=tmp_path)
    pm.begin_away()
    assert not pm.check_path_write(ws / ".config" / "autostart" / "x.desktop").allowed
    assert not pm.check(Risk.MODERATE, "Aussehen zuruecksetzen").allowed  # keine liegengebliebene Freigabe


def test_away_never_touches_the_ki_folder_even_inside_the_workspace(tmp_path):
    cfg = load_config(tmp_path)
    app = tmp_path / "KI"
    (app / "config").mkdir(parents=True)
    (app / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-geheim", encoding="utf-8")
    pm = PermissionManager(cfg.permissions, tmp_path, app_root=app)  # Arbeitsordner = ganzer Ordner
    pm.begin_away()
    with pytest.raises(PermissionError_):
        pm.resolve_path(str(app / ".env"))
    assert not pm.check_path_write(app / "config" / "settings.toml").allowed
    (app / "workspace").mkdir()
    assert pm.check_path_write(app / "workspace" / "neu.txt").allowed  # ihr eigener Arbeitsordner ja


def test_search_results_unlock_fetching_while_away(tmp_path, monkeypatch):
    import types

    cfg = load_config(tmp_path)
    pm = PermissionManager(cfg.permissions, tmp_path)
    ctx = ToolContext(permissions=pm)
    reg = build_registry()
    html = ('<a class="result-link" href="https://www.example.org/artikel">Artikel</a>'
            '<td class="result-snippet">Text</td>')
    fake = types.SimpleNamespace(
        post=lambda *a, **k: types.SimpleNamespace(text=html, raise_for_status=lambda: None),
        get=lambda *a, **k: types.SimpleNamespace(text="<p>Inhalt</p>", raise_for_status=lambda: None))
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)
    pm.begin_away()
    assert reg.get("web_abrufen").run(ctx, url="https://www.example.org/artikel").startswith("Solange")
    reg.get("web_suche").run(ctx, anfrage="test")
    assert "Inhalt" in reg.get("web_abrufen").run(ctx, url="https://www.example.org/artikel#teil")
    pm.end_away()
    assert pm.away_urls == set()


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
    fetch = reg.get("web_abrufen")
    for url in ("https://x.example/?geheim=sk-123", "https://evil.example/c/DE89370400440532013000",
                "https://geheim@evil.example/", "http://example.org/", "https://192.168.0.5/",
                "https://DE89370400440532013000.evil.example/"):
        out = fetch.run(ctx, url=url)
        assert out.startswith("Solange dein Mensch weg ist"), (url, out)
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
    back = model_text_for("Hallo", back=(time.time() - 42 * 60 - 5, "BERICHT"))
    assert back.startswith("[Dein Mensch ist zurueck - er war 42 Min.") and back.endswith("Hallo")
    # unsinnige Grenzen (unendlich) lassen die Sitzung nicht abstuerzen
    odd = settings_session(AfkSettings(max_minuten=float("inf"), max_schritte=float("inf")), minutes=1e309)
    assert odd.max_minutes == 120 and odd.max_rounds == 12


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


def test_terminal_afk_leaves_no_stop_signal_behind(tmp_path, capsys):
    from types import SimpleNamespace

    from assistant.ui.cli import CLI
    from tests._fakes import AnthroStream, anthro_msg, text_block

    cfg = load_config(tmp_path)
    cfg.update.modus = "aus"
    cfg.anthropic_api_key = "sk-ant-test-schluessel"
    cfg.afk.pause_sekunden = 0
    cli = CLI(cfg)

    def stream(**kwargs):  # der Waechter haelt den Schritt an (Budget erreicht)
        cli.brain.provider.cancel()
        return AnthroStream(anthro_msg([text_block("x")]), [SimpleNamespace(type="text", text="x")])

    cli.brain.provider.client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    try:
        cli._afk_terminal("Test")
        assert not cli.brain.provider.cancel_event.is_set()
    finally:
        cli.memory.close()


def test_ctrl_c_while_summarizing_counts_as_back(tmp_path):
    from assistant.brain import Brain
    from assistant.cancel import Abgebrochen

    brain = Brain.__new__(Brain)
    brain.compact_interrupted = False

    def boom(only_if_large):
        raise KeyboardInterrupt

    brain._compact = boom
    assert brain._maybe_compact() is False and brain.compact_interrupted
    brain.compact_interrupted = False

    def cancelled(only_if_large):
        raise Abgebrochen()

    brain._compact = cancelled
    brain._maybe_compact()
    assert not brain.compact_interrupted


def test_choosing_a_depth_does_not_store_a_forced_model(tmp_path, monkeypatch):
    from assistant.modelle import waehle

    monkeypatch.setenv("KI_MODEL", "claude-haiku-5-5")
    cfg = load_config(tmp_path)
    assert cfg.claude.model == "claude-haiku-5-5"
    waehle(cfg, "claude", denken="gruendlich")
    text = (tmp_path / "config" / "settings.toml").read_text(encoding="utf-8")
    assert 'model = "claude-haiku-5-5"' not in text and 'effort = "high"' in text


def test_fetching_while_away_cannot_smuggle_data_or_reach_the_home_network(tmp_path, monkeypatch):
    import socket
    import types

    from assistant.tools import web

    cfg = load_config(tmp_path)
    pm = PermissionManager(cfg.permissions, tmp_path)
    ctx = ToolContext(permissions=pm)
    fetch = build_registry().get("web_abrufen")
    pm.begin_away()
    pm.away_urls.add("https://seite.example/artikel")
    # angehaengte Leer-/Steuerzeichen wuerden beim Abruf mitgeschickt
    for tail in ("  ", " \t", "\x00"):
        assert fetch.run(ctx, url="https://seite.example/artikel" + tail).startswith("Solange")
    # der Name zeigt ins eigene Netz
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.1.1", 443))])
    assert "eigenen Netz" in fetch.run(ctx, url="https://seite.example/artikel")
    # Weiterleitung ins eigene Netz wird nicht verfolgt
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [
        (2, 1, 6, "", ("127.0.0.1" if host == "router.example" else "93.184.216.34", 443))])
    calls = []

    def get(url, **kw):
        calls.append(url)
        assert kw.get("allow_redirects") is False
        return types.SimpleNamespace(status_code=302, headers={"Location": "https://router.example/admin"},
                                     text="", raise_for_status=lambda: None)

    monkeypatch.setitem(__import__("sys").modules, "requests", types.SimpleNamespace(get=get))
    out = fetch.run(ctx, url="https://seite.example/artikel")
    assert "leitet weiter" in out and calls == ["https://seite.example/artikel"]
    assert web._host_problem("http://seite.example/") is not None


def test_own_workspace_inside_the_ki_folder_stays_usable_while_away(tmp_path):
    cfg = load_config(tmp_path)
    app = tmp_path / "KI"
    work = app / "meine-dateien"
    work.mkdir(parents=True)
    (work / "notiz.txt").write_text("x", encoding="utf-8")
    pm = PermissionManager(cfg.permissions, work, app_root=app)
    pm.begin_away()
    assert pm.resolve_path("notiz.txt", must_exist=True)
    assert pm.check_path_write(work / "neu.txt").allowed
    with pytest.raises(PermissionError_):
        pm.resolve_path(str(app / ".env"))


def test_ki_model_note_only_when_it_matters(tmp_path, monkeypatch):
    from assistant.modelle import waehle

    monkeypatch.setenv("KI_MODEL", "haiku")
    cfg = load_config(tmp_path)
    assert "KI_MODEL" in waehle(cfg, "claude", model="sonnet")["message"]
    assert "KI_MODEL" not in waehle(cfg, "claude", model="haiku")["message"]
    assert "KI_MODEL" not in waehle(cfg, "deepseek", model="pro")["message"]  # anderes Gehirn


def test_tricky_addresses_are_checked_as_they_are_really_sent(monkeypatch):
    import socket

    from assistant.tools import web

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    for url in ("https://localhost\\\\.evil.example/admin", "https://faß.evil.example/", "https://intranet/",
                "https://fritz.box/", "https://localhost./"):
        assert web._host_problem(url) is not None, url
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("100.101.102.103", 443))])
    assert web._host_problem("https://nas.tail1234.ts.net/") is not None  # Tailscale/CGNAT

    def broken(*a, **k):
        raise socket.gaierror("kaputt")

    monkeypatch.setattr(socket, "getaddrinfo", broken)
    assert web._host_problem("https://irgendwas.example/") is not None  # im Zweifel gesperrt
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert web._host_problem("https://www.example.org/seite") is None


def test_waiting_for_jarvis_ignores_a_cough_but_not_a_sentence():
    import threading
    import time as _t
    from types import SimpleNamespace

    from assistant.live import wait_until_quiet

    live = SimpleNamespace(stop_event=threading.Event(), turn=3, turn_active=False, speaking=True,
                           hearing=True, pending=None, voice_out=SimpleNamespace(idle=lambda: False))

    def cough_then_quiet():
        _t.sleep(0.3)
        live.hearing = False  # nur ein Geraeusch
        _t.sleep(0.2)
        live.speaking = False

    threading.Thread(target=cough_then_quiet).start()
    assert wait_until_quiet(live, threading.Event(), timeout=5) is True

    live.speaking, live.hearing = True, True

    def sentence():
        _t.sleep(0.2)
        live.pending = "Warte, ich hab noch eine Frage"

    threading.Thread(target=sentence).start()
    assert wait_until_quiet(live, threading.Event(), timeout=5) is False
