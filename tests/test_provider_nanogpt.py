"""NanoGPT als Gehirn (unzensiert, OpenAI-kompatibel, sieht Bilder, Zahlung auch per Karte)."""
from types import SimpleNamespace

from assistant import modelle, schluessel
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.nanogpt_provider import NanogptProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient, ds_text_chunk


def _cfg():
    cfg = load_config()
    cfg.provider.aktiv = "nanogpt"
    cfg.nanogpt_api_key = "ng-geheim-123"
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


def test_nanogpt_request_shape(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("Hallo!"), _usage(500, 20)]])
    assert isinstance(prov, NanogptProvider)
    assert prov.respond("Hi") == "Hallo!"
    kw = prov.client.chat.completions.last_kwargs
    assert kw["model"] == "z-ai/glm-5.3-uncensored" and kw["stream"] is True
    assert "max_tokens" in kw and "max_completion_tokens" not in kw and "temperature" in kw
    assert "reasoning_effort" not in kw and "extra_body" not in kw
    assert prov._sees_images() is True
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


def test_in_providers_ohne_praefix():
    assert "nanogpt" in schluessel.PROVIDERS and schluessel.PROVIDERS["nanogpt"]["prefix"] == ""


def test_schluessel_speichern_mit_ausdruecklichem_anbieter(tmp_path, monkeypatch):
    monkeypatch.setenv("NANOGPT_API_KEY", "")
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "claude"
    try:
        r = schluessel.setup(cfg, key="ng-abc-999", provider="nanogpt", tester=lambda c, p, k: (True, "ok", ""))
        assert r["ok"] and r["provider"] == "nanogpt" and cfg.active_provider == "nanogpt"
        assert cfg.nanogpt_api_key == "ng-abc-999" and cfg.api_key == cfg.nanogpt_api_key
        assert "NANOGPT_API_KEY=ng-abc-999" in (tmp_path / ".env").read_text(encoding="utf-8")
        ng = next(p for p in schluessel.describe(cfg)["providers"] if p["id"] == "nanogpt")
        assert ng["has_key"] and ng["model"] == "z-ai/glm-5.3-uncensored"
    finally:
        import os
        os.environ.pop("NANOGPT_API_KEY", None)


def test_modelle_mit_slash_id_und_normalisierung():
    assert modelle.preise("nanogpt", "z-ai/glm-5.3-uncensored") == (0.5, 0.05, 1.5)
    assert modelle._finde_modell("nanogpt", "glmflash") == "z-ai/glm-5.3-flash-uncensored"
    assert modelle.fremdes_modell("ablit2") == "nanogpt"
    assert modelle.sieht_bilder("nanogpt", "z-ai/glm-5.3-uncensored") is True
    cfg = SimpleNamespace(nanogpt=SimpleNamespace(model="", base_url="x", max_tokens="viel",
                                                  temperature="heiss", denken="gruendlich"))
    modelle.normalisiere_nanogpt(cfg.nanogpt)
    assert cfg.nanogpt.model == "z-ai/glm-5.3-uncensored" and cfg.nanogpt.denken == "aus"
    assert cfg.nanogpt.base_url == "https://api.nano-gpt.com/api/v1"
    # Modell mit "/" bleibt erhalten (nicht faelschlich zurueckgesetzt)
    ng2 = SimpleNamespace(model="abliteration-ai/abliterated-model-large-v2", base_url="https://api.nano-gpt.com/api/v1",
                          max_tokens=16384, temperature=0.7, denken="aus")
    modelle.normalisiere_nanogpt(ng2)
    assert ng2.model == "abliteration-ai/abliterated-model-large-v2"
