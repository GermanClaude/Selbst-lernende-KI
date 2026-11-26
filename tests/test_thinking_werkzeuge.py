"""0.48: Nach einer Werkzeug-Aenderung mitten im Gespraech (z.B. Premium) muessen alte Thinking-Bloecke raus,
sonst scheitert die naechste Anfrage an 'Invalid signature in thinking block'."""
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers.anthropic_provider import AnthropicProvider
from assistant.tools import ToolContext, build_registry


def _prov(tmp_path):
    cfg = load_config()
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, memory=Memory(tmp_path / "m.sqlite3"))
    return AnthropicProvider(cfg, "SYSTEM", build_registry(), ctx, client=object())


def test_thinking_bloecke_werden_verworfen(tmp_path):
    p = _prov(tmp_path)
    p.messages = [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "denk denk", "signature": "abc"},
            {"type": "redacted_thinking", "data": "xx"},
            {"type": "text", "text": "Hi!"},
        ]},
        {"role": "user", "content": "code NOVA-..."},
    ]
    p.werkzeuge_geaendert()
    bloecke = p.messages[1]["content"]
    typen = [b["type"] for b in bloecke]
    assert "thinking" not in typen and "redacted_thinking" not in typen
    assert typen == ["text"]            # der echte Text bleibt erhalten
    assert p.messages[0]["content"] == "Hallo"   # Nutzer-Text unangetastet


def test_leerer_assistant_block_bleibt_gueltig(tmp_path):
    p = _prov(tmp_path)
    p.messages = [{"role": "assistant", "content": [{"type": "thinking", "thinking": "x", "signature": "s"}]}]
    p.werkzeuge_geaendert()
    # Nach dem Entfernen darf der Block nicht leer sein (die API lehnt leere content-Listen ab)
    assert p.messages[0]["content"] and p.messages[0]["content"][0]["type"] == "text"


def test_ohne_thinking_unveraendert(tmp_path):
    p = _prov(tmp_path)
    p.messages = [{"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                  {"role": "user", "content": "frage"}]
    vorher = [dict(m) for m in p.messages]
    p.werkzeuge_geaendert()
    assert p.messages == vorher       # nichts zu tun, nichts kaputt
