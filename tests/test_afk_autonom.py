"""AFK-Vollmacht: Nova handelt im AFK wirklich (statt nur vorzuschlagen) - aber nur, wenn der
Mensch ihr ohnehin volle Freiheit gegeben hat. Automatische Starts bleiben gesperrt."""
from assistant.abwesend import AfkSession
from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager, Risk


def _pm(tmp_path, **perm):
    # Standard "Stuetzraeder aus" = volle Freiheit; einzelne Felder ueberschreibbar.
    base = dict(safe_mode=False, auto_confirm=True, allow_full_filesystem=True)
    base.update(perm)
    return PermissionManager(PermissionSettings(**base), tmp_path, confirm_fn=lambda m, r: False)


def test_vollmacht_nur_bei_voller_freiheit(tmp_path):
    # Stuetzraeder "an" (safe_mode an) -> keine AFK-Vollmacht moeglich.
    assert _pm(tmp_path, safe_mode=True, auto_confirm=False, allow_full_filesystem=False).afk_autonomie_moeglich() is False
    # Stuetzraeder "aus" -> moeglich.
    assert _pm(tmp_path).afk_autonomie_moeglich() is True
    # Vollzugriff -> moeglich.
    assert _pm(tmp_path, vollzugriff=True).afk_autonomie_moeglich() is True
    # Abgeschaltet per afk_autonom=False -> nie.
    assert _pm(tmp_path, afk_autonom=False).afk_autonomie_moeglich() is False


def test_afk_mit_vollmacht_darf_handeln(tmp_path):
    pm = _pm(tmp_path)
    pm.begin_away()
    assert pm.afk_handlungsfrei() is True
    assert pm.check(Risk.DANGEROUS, "Datei loeschen").allowed            # handeln ohne Rueckfrage
    assert pm.check_shell("python skript.py").allowed                    # Befehle erlaubt
    aussen = pm.resolve_path(str(tmp_path.parent / "woanders.txt"))      # voller Dateizugriff
    assert aussen == (tmp_path.parent / "woanders.txt").resolve()
    bestehend = tmp_path / "da.txt"
    bestehend.write_text("x", encoding="utf-8")
    assert pm.check_path_write(bestehend).allowed                        # darf ueberschreiben


def test_afk_mit_vollmacht_trotzdem_kein_autostart(tmp_path):
    pm = _pm(tmp_path)
    pm.begin_away()
    assert not pm.confirm_always("Autostart einrichten").allowed
    assert not pm.check_shell("schtasks /create /tn x /tr y").allowed


def test_afk_ohne_vollmacht_bleibt_vorsichtig(tmp_path):
    # afk_autonom aus -> altes, vorsichtiges Verhalten trotz voller Freiheit sonst.
    pm = _pm(tmp_path, afk_autonom=False)
    pm.begin_away()
    assert pm.afk_handlungsfrei() is False
    assert not pm.check(Risk.DANGEROUS, "Datei loeschen").allowed
    assert not pm.check_shell("python skript.py").allowed
    # Neue Datei im Arbeitsordner geht weiterhin (Entwuerfe/Notizen).
    neu = tmp_path / "entwurf.txt"
    assert pm.check_path_write(neu).allowed and pm.check(Risk.MODERATE, "schreiben").allowed


def test_nicht_afk_unveraendert(tmp_path):
    # Ausserhalb des AFK aendert die Vollmacht nichts.
    pm = _pm(tmp_path)
    assert pm.afk_handlungsfrei() is False


def test_round_prompt_autonom_vs_vorsichtig():
    s = AfkSession(auftrag="räum auf", autonom=True)
    assert "DARFST eigenstaendig handeln" in s.round_prompt()
    s2 = AfkSession(auftrag="räum auf", autonom=False)
    assert "als Vorschlag auf" in s2.round_prompt() and "DARFST eigenstaendig" not in s2.round_prompt()
