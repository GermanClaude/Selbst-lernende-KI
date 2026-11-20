"""OpenAI / ChatGPT als fuenftes Gehirn - mit gefaelschtem OpenAI-Client, ohne Netz."""
from types import SimpleNamespace

from assistant import modelle, schluessel
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.openai_provider import OpenAIProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient, ds_text_chunk


def _cfg(model="gpt-5.2", denken="aus"):
    cfg = load_config()
    cfg.provider.aktiv = "openai"
    cfg.openai_api_key = "sk-proj-test1234567890abcdef"
    cfg.openai.model = model
    cfg.openai.denken = denken
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


def test_openai_wird_gewaehlt_und_fragt_richtig_an(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("Hallo!"), _usage(1000, 40, cached=600)]], _cfg(denken="low"))
    assert isinstance(prov, OpenAIProvider)
    assert prov.respond("Hi") == "Hallo!"
    kw = prov.client.chat.completions.last_kwargs
    assert kw["model"] == "gpt-5.2" and kw["reasoning_effort"] == "low"
    # Denk-Modelle: max_completion_tokens statt max_tokens, keine temperature
    assert "max_completion_tokens" in kw and "max_tokens" not in kw and "temperature" not in kw
    assert kw["max_completion_tokens"] >= 8192 and kw["stream"] is True
    # Cache-Treffer guenstiger verbucht
    assert prov.usage.cache_hit_tokens == 600 and prov.usage.input_full_tokens == 400
    assert prov.usage.output_tokens == 40
    mem.close()


def test_aus_bedeutet_minimal_bei_denk_modell(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("ok"), _usage(1, 1)]], _cfg(denken="aus"))
    prov.respond("x")
    assert prov.client.chat.completions.last_kwargs["reasoning_effort"] == "minimal"
    mem.close()


def test_sol_luna_nutzen_werkzeuge_nur_ohne_nachdenken(tmp_path):
    # gpt-6-luna kann ueber Chat Completions keine Werkzeuge + Nachdenken -> immer reasoning_effort "none"
    prov, mem = _provider(tmp_path, [[ds_text_chunk("ok"), _usage(1, 1)]], _cfg(model="gpt-6-luna", denken="high"))
    prov.respond("x")
    assert prov.client.chat.completions.last_kwargs["reasoning_effort"] == "none"
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
    assert prov.client.chat.completions.requests[0] is not None  # tools lagen an
    assert prov.client.chat.completions.last_kwargs.get("tools")
    mem.close()


def test_schluessel_erkennung():
    assert schluessel.find_key("mein key sk-proj-" + "A" * 30) == "sk-proj-" + "A" * 30
    assert schluessel.provider_for_key("sk-proj-abc123") == "openai"
    assert schluessel.provider_for_key("sk-svcacct-abc") == "openai"
    assert schluessel.provider_for_key("sk-deadbeefdeadbeef") == "deepseek"  # bare sk- bleibt DeepSeek
    assert schluessel.provider_for_key("sk-ant-x") == "claude"


def test_openai_fehlermeldungen():
    class Fehler(Exception):
        def __init__(self, text, status):
            super().__init__(text)
            self.status_code = status

    art, text = schluessel.classify(Fehler("Error code: 429 - insufficient_quota", 429), "openai")
    assert art == "balance" and "Guthaben" in text
    art, text = schluessel.classify(Fehler("The model `gpt-4o` does not exist (model_not_found)", 404), "openai")
    assert art == "model" and "Modell" in text
    art, _ = schluessel.classify(Fehler("Incorrect API key provided", 401), "openai")
    assert art == "invalid"


def test_schluessel_speichern_und_wechseln(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "claude"
    r = schluessel.setup(cfg, key="sk-proj-gueltig123", tester=lambda c, p, k: (True, "ok", ""))
    assert r["ok"] and r["provider"] == "openai" and cfg.active_provider == "openai"
    assert cfg.openai_api_key == "sk-proj-gueltig123" and cfg.api_key == cfg.openai_api_key
    assert "OPENAI_API_KEY=sk-proj-gueltig123" in (tmp_path / ".env").read_text(encoding="utf-8")
    beschr = schluessel.describe(cfg)
    oa = next(p for p in beschr["providers"] if p["id"] == "openai")
    assert oa["has_key"] and oa["model"] == "gpt-5.2"
    assert [m["id"] for m in beschr["modelle"]["openai"]["modelle"]][0] == "gpt-5.2"


def test_auto_wechsel_wenn_nur_openai_schluessel(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-aus-der-umgebung")
    cfg = load_config(tmp_path)
    assert cfg.active_provider == "openai" and cfg.provider_auto_switched == "claude"


def test_modelle_preise_und_alte_namen():
    assert modelle.preise("openai", "gpt-5.2") == (1.75, 0.175, 14.0)
    assert modelle.preise("openai", "gpt-6-luna") == (0.1, 0.01, 0.5)
    assert modelle._finde_modell("openai", "luna") == "gpt-6-luna"
    assert modelle._finde_modell("openai", "gpt-4o") == "gpt-5.2"  # abgeloest -> Nachfolger
    assert modelle.fremdes_modell("sol") == "openai"
    assert modelle.sieht_bilder("openai", "gpt-irgendwas-neues")
    assert modelle.openai_kann_denken("gpt-5.2") and not modelle.openai_kann_denken("gpt-6-sol")
    cfg = SimpleNamespace(openai=SimpleNamespace(model="GPT-4O", denken="gruendlich", base_url="x", max_tokens="viel"))
    modelle.normalisiere_openai(cfg.openai)
    assert cfg.openai.model == "gpt-5.2" and cfg.openai.denken == "medium"
    assert cfg.openai.base_url == "https://api.openai.com/v1" and cfg.openai.max_tokens == 16384


def test_modell_und_denktiefe_waehlen(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="openai", model="luna", denken="gruendlich")
    assert r["ok"] and cfg.openai.model == "gpt-6-luna" and cfg.openai.denken == "medium"
    assert "GPT-6 Luna" in r["message"]
    r = modelle.waehle(cfg, provider="openai", model="opus")
    assert not r["ok"]
