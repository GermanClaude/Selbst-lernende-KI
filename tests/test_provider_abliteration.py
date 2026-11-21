"""Abliteration AI als Gehirn (unzensiert, OpenAI-kompatibel) - mit gefaelschtem Client, ohne Netz."""
from types import SimpleNamespace

from assistant import modelle, schluessel
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.abliteration_provider import AbliterationProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient, ds_text_chunk


def _cfg():
    cfg = load_config()
    cfg.provider.aktiv = "abliteration"
    cfg.abliteration_api_key = "ak_test1234567890abcdef"
    return cfg


def _provider(tmp_path, streams, cfg=None):
    cfg = cfg or _cfg()
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, memory=mem)
    prov = build_provider(cfg, "SYSTEM", build_registry(), ctx, client=DSClient(streams))
    return prov, mem


def _usage(prompt, completion, cached=0):
    details = SimpleNamespace(cached_tokens=cached)
    return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                                                             prompt_tokens_details=details))


def test_abliteration_wird_gewaehlt_und_fragt_richtig_an(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("Hallo!"), _usage(1000, 40, cached=200)]])
    assert isinstance(prov, AbliterationProvider)
    assert prov.respond("Hi") == "Hallo!"
    kw = prov.client.chat.completions.last_kwargs
    assert kw["model"] == "abliterated-model" and kw["stream"] is True
    # Normales Chat-Completions-Modell: max_tokens + temperature, KEIN reasoning/thinking
    assert "max_tokens" in kw and "max_completion_tokens" not in kw
    assert "temperature" in kw and "reasoning_effort" not in kw
    assert "extra_body" not in kw  # kein {"thinking": ...}
    assert prov.usage.cache_hit_tokens == 200 and prov.usage.input_full_tokens == 800
    assert prov.usage.output_tokens == 40
    mem.close()


def test_werkzeuge_werden_mitgeschickt_und_ausgefuehrt(tmp_path):
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


def test_schluessel_erkennung():
    key = "ak_" + "A" * 30
    assert schluessel.find_key("mein key " + key) == key
    assert schluessel.provider_for_key(key) == "abliteration"
    assert schluessel.provider_for_key("sk-deadbeefdeadbeef") == "deepseek"  # bare sk- bleibt DeepSeek
    assert "abliteration" in schluessel.PROVIDERS and schluessel.PROVIDERS["abliteration"]["prefix"] == "ak_"


def test_abliteration_fehlermeldung_guthaben():
    class Fehler(Exception):
        def __init__(self, text, status):
            super().__init__(text)
            self.status_code = status

    art, text = schluessel.classify(Fehler("insufficient balance", 402), "abliteration")
    assert art == "balance" and "Guthaben" in text


def test_schluessel_speichern_und_wechseln(tmp_path, monkeypatch):
    monkeypatch.setenv("ABLITERATION_API_KEY", "")
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "claude"
    try:
        r = schluessel.setup(cfg, key="ak_gueltig123456", tester=lambda c, p, k: (True, "ok", ""))
        assert r["ok"] and r["provider"] == "abliteration" and cfg.active_provider == "abliteration"
        assert cfg.abliteration_api_key == "ak_gueltig123456" and cfg.api_key == cfg.abliteration_api_key
        assert "ABLITERATION_API_KEY=ak_gueltig123456" in (tmp_path / ".env").read_text(encoding="utf-8")
        beschr = schluessel.describe(cfg)
        ab = next(p for p in beschr["providers"] if p["id"] == "abliteration")
        assert ab["has_key"] and ab["model"] == "abliterated-model"
    finally:
        import os
        os.environ.pop("ABLITERATION_API_KEY", None)


def test_auto_wechsel_wenn_nur_abliteration_schluessel(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ABLITERATION_API_KEY", "ak_aus-der-umgebung")
    try:
        cfg = load_config(tmp_path)
        assert cfg.active_provider == "abliteration" and cfg.provider_auto_switched == "claude"
    finally:
        import os
        os.environ.pop("ABLITERATION_API_KEY", None)


def test_modelle_und_normalisierung():
    assert modelle.preise("abliteration", "abliterated-model") == (1.0, 0.1, 3.0)
    assert modelle._finde_modell("abliteration", "ablit") == "abliterated-model"
    assert modelle.fremdes_modell("abliterated") == "abliteration"
    assert modelle.sieht_bilder("abliteration", "abliterated-model") is False
    cfg = SimpleNamespace(abliteration=SimpleNamespace(model="", base_url="x", max_tokens="viel",
                                                       temperature="heiss", denken="gruendlich"))
    modelle.normalisiere_abliteration(cfg.abliteration)
    assert cfg.abliteration.model == "abliterated-model" and cfg.abliteration.denken == "aus"
    assert cfg.abliteration.base_url == "https://api.abliteration.ai/v1"
    assert cfg.abliteration.max_tokens == 16384 and cfg.abliteration.temperature == 0.7
