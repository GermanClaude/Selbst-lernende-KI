"""Skills: gespeicherte Anweisungen (global oder pro Gehirn), vom Nutzer oder der KI."""
from assistant import skills as sk
from assistant.tools import ToolContext, build_registry
from assistant.permissions import PermissionManager
from assistant.config import PermissionSettings
from types import SimpleNamespace


def _root(tmp_path):
    (tmp_path / "config").mkdir(exist_ok=True)
    return tmp_path


def test_hinzufuegen_laden_persistiert(tmp_path):
    root = _root(tmp_path)
    ok, msg = sk.hinzufuegen(root, "Knapp", "Antworte extrem kurz, spare Tokens.")
    assert ok and "Knapp" in msg
    skills = sk.laden(root)
    assert len(skills) == 1 and skills[0].name == "Knapp" and skills[0].provider == "" and skills[0].an


def test_prompt_block_global_und_pro_gehirn(tmp_path):
    root = _root(tmp_path)
    sk.hinzufuegen(root, "Knapp", "kurz antworten")              # alle
    sk.hinzufuegen(root, "ClaudeStil", "sei besonders praezise", provider="claude")
    block_claude = sk.prompt_block(root, "claude")
    block_deepseek = sk.prompt_block(root, "deepseek")
    assert "Knapp" in block_claude and "ClaudeStil" in block_claude   # beide fuer Claude
    assert "Knapp" in block_deepseek and "ClaudeStil" not in block_deepseek  # claude-Skill nicht bei DeepSeek


def test_umschalten_und_entfernen(tmp_path):
    root = _root(tmp_path)
    sk.hinzufuegen(root, "X", "tu was")
    assert sk.umschalten(root, "X", False) is True
    assert sk.prompt_block(root, "claude") == ""          # ausgeschaltet -> nicht im Prompt
    assert sk.entfernen(root, "X") is True and sk.laden(root) == []


def test_ueberschreiben_gleicher_name(tmp_path):
    root = _root(tmp_path)
    sk.hinzufuegen(root, "A", "erste")
    sk.hinzufuegen(root, "a", "zweite")  # gleicher Name (Gross/Klein egal) -> ersetzt
    skills = sk.laden(root)
    assert len(skills) == 1 and skills[0].anweisung == "zweite"


def test_werkzeug_skill(tmp_path):
    root = _root(tmp_path)
    reg = build_registry()
    assert any(getattr(t, "name", "") == "skill" for t in reg._tools.values())
    pm = PermissionManager(PermissionSettings(safe_mode=False, auto_confirm=True), root,
                           confirm_fn=lambda m, r: True)
    cfg = SimpleNamespace(project_root=root, active_provider="venice")
    ctx = ToolContext(permissions=pm, extra={"config": cfg})
    out, err = reg.execute(ctx, "skill", {"aktion": "hinzufuegen", "name": "Sparsam",
                                          "anweisung": "wenig Tokens", "nur_dieses_gehirn": True})
    assert not err
    skills = sk.laden(root)
    assert skills[0].provider == "venice"  # nur_dieses_gehirn -> aktives Gehirn
    out2, _ = reg.execute(ctx, "skill", {"aktion": "liste"})
    assert "Sparsam" in out2
