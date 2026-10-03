import pytest

from assistant.config import PermissionSettings
from assistant.permissions import PermissionManager, Risk, PermissionError_


def _pm(tmp_path, **kw):
    defaults = dict(safe_mode=True, auto_confirm=False)
    defaults.update(kw)
    return PermissionManager(PermissionSettings(**defaults), tmp_path, confirm_fn=lambda m, r: True)


def test_safe_always_allowed(tmp_path):
    pm = _pm(tmp_path)
    assert pm.check(Risk.SAFE, "lesen").allowed


def test_dangerous_blocked_in_safe_mode(tmp_path):
    pm = _pm(tmp_path, safe_mode=True)
    assert not pm.check(Risk.DANGEROUS, "loeschen").allowed


def test_dangerous_allowed_when_confirmed(tmp_path):
    pm = _pm(tmp_path, safe_mode=False, auto_confirm=False)
    assert pm.check(Risk.DANGEROUS, "loeschen").allowed  # confirm_fn sagt ja


def test_dangerous_denied_when_rejected(tmp_path):
    pm = PermissionManager(
        PermissionSettings(safe_mode=False, auto_confirm=False),
        tmp_path,
        confirm_fn=lambda m, r: False,
    )
    assert not pm.check(Risk.DANGEROUS, "loeschen").allowed


def test_path_sandbox_blocks_escape(tmp_path):
    pm = _pm(tmp_path)
    with pytest.raises(PermissionError_):
        pm.resolve_path("../../etc/passwd")


def test_path_sandbox_allows_inside(tmp_path):
    pm = _pm(tmp_path)
    p = pm.resolve_path("unter/datei.txt")
    assert str(p).startswith(str(tmp_path.resolve()))


def test_full_filesystem_allows_outside(tmp_path):
    pm = _pm(tmp_path, allow_full_filesystem=True)
    p = pm.resolve_path("/tmp/irgendwo.txt")
    assert str(p) == "/tmp/irgendwo.txt"


def test_shell_denylist_always_blocks(tmp_path):
    pm = _pm(tmp_path, safe_mode=False, auto_confirm=True, shell_denylist=["rm -rf /"])
    assert not pm.check_shell("sudo rm -rf / jetzt").allowed


def test_shell_blocked_in_safe_mode(tmp_path):
    pm = _pm(tmp_path, safe_mode=True)
    assert not pm.check_shell("echo hallo").allowed


def test_shell_allowlist(tmp_path):
    pm = PermissionManager(
        PermissionSettings(safe_mode=False, auto_confirm=False, shell_allowlist=["echo"]),
        tmp_path,
        confirm_fn=lambda m, r: False,  # wuerde ablehnen, aber Allowlist greift
    )
    assert pm.check_shell("echo hallo").allowed
    assert not pm.check_shell("curl irgendwas").allowed
