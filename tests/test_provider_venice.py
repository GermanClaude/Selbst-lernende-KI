"""Venice AI als Gehirn (unzensiert, OpenAI-kompatibel, SIEHT Bilder) - gefaelschter Client, ohne Netz."""
from types import SimpleNamespace

from assistant import modelle, schluessel
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.venice_provider import VeniceProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient, ds_text_chunk


def _cfg():
    cfg = load_config()
    cfg.provider.aktiv = "venice"
    cfg.venice_api_key = "venice-geheim-123"
    return cfg


def _provider(tmp_path, streams, cfg=None):
    cfg = cfg or _cfg()
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    prov = build_provider(cfg, "SYSTEM", build_registry(), ToolContext(permissions=pm, memory=mem),
                          client=DSClient(streams))
    return prov, mem


def _usage(prompt, completion, cached=0):
    details = SimpleNamespace(cached_tokens=cached)
    return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                                                             prompt_tokens_details=details))


def test_venice_request_shape(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("Hallo!"), _usage(500, 20)]])
    assert isinstance(prov, VeniceProvider)
    assert prov.respond("Hi") == "Hallo!"
    kw = prov.client.chat.completions.last_kwargs
    assert kw["model"] == "venice-uncensored-1-2" and kw["stream"] is True
    assert "max_tokens" in kw and "max_completion_tokens" not in kw and "temperature" in kw
    assert "reasoning_effort" not in kw
    # Venice-eigene Option: Novas Persoenlichkeit gilt, nicht Venices Standard-Prompt.
    assert kw["extra_body"]["venice_parameters"]["include_venice_system_prompt"] is False
    assert prov._sees_images() is True  # Venice sieht Bilder selbst
    mem.close()


def test_werkzeuge_werden_mitgeschickt(tmp_path):
    def tool_chunk(tid, name, args):
        tc = SimpleNamespace(index=0, id=tid, function=SimpleNamespace(name=name, arguments=args), model_extra={})
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))],
                               usage=None)

    streams = [[tool_chunk("c1", "system_info", "{}"), _usage(10, 5)],
               [ds_text_chunk("Fertig."), _usage(10, 5)]]
    prov, mem = _provider(tmp_path, streams)
    assert prov.respond("Systeminfo") == "Fertig."
    assert any(m.get("role") == "tool" for m in prov.messages)
    assert prov.client.chat.completions.last_kwargs.get("tools")
    mem.close()


def test_venice_in_providers_ohne_praefix():
    assert "venice" in schluessel.PROVIDERS and schluessel.PROVIDERS["venice"]["prefix"] == ""


def test_schluessel_speichern_mit_ausdruecklichem_anbieter(tmp_path, monkeypatch):
    monkeypatch.setenv("VENICE_API_KEY", "")
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "claude"
    try:
        # Kein Praefix -> Anbieter MUSS ausdruecklich angegeben werden (so macht es die App).
        r = schluessel.setup(cfg, key="venice-abc-999", provider="venice", tester=lambda c, p, k: (True, "ok", ""))
        assert r["ok"] and r["provider"] == "venice" and cfg.active_provider == "venice"
        assert cfg.venice_api_key == "venice-abc-999" and cfg.api_key == cfg.venice_api_key
        assert "VENICE_API_KEY=venice-abc-999" in (tmp_path / ".env").read_text(encoding="utf-8")
        ven = next(p for p in schluessel.describe(cfg)["providers"] if p["id"] == "venice")
        assert ven["has_key"] and ven["model"] == "venice-uncensored-1-2"
    finally:
        import os
        os.environ.pop("VENICE_API_KEY", None)


def test_modelle_und_normalisierung():
    assert modelle.preise("venice", "venice-uncensored-1-2") == (0.20, 0.02, 0.90)
    assert modelle._finde_modell("venice", "gemma") == "gemma-4-uncensored"
    assert modelle.fremdes_modell("venice") == "venice"
    assert modelle.sieht_bilder("venice", "venice-uncensored-1-2") is True
    cfg = SimpleNamespace(venice=SimpleNamespace(model="", base_url="x", max_tokens="viel",
                                                 temperature="heiss", denken="gruendlich"))
    modelle.normalisiere_venice(cfg.venice)
    assert cfg.venice.model == "venice-uncensored-1-2" and cfg.venice.denken == "aus"
    assert cfg.venice.base_url == "https://api.venice.ai/api/v1"
    assert cfg.venice.max_tokens == 16384 and cfg.venice.temperature == 0.7
