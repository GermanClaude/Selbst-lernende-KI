"""Gemini (Google) als viertes Gehirn - mit gefaelschtem OpenAI-Client, ohne Netz."""
from datetime import datetime, timezone
from types import SimpleNamespace

from assistant import modelle, schluessel
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.gemini_provider import SIGNATUR_PLATZHALTER, GeminiProvider
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient, ds_text_chunk


def _cfg():
    cfg = load_config()
    cfg.provider.aktiv = "gemini"
    cfg.gemini_api_key = "AQ.Ab-test-schluessel-1234567890"
    cfg.gemini.model = "gemini-3.8-flash"
    cfg.gemini.denken = "low"
    return cfg


def _provider(tmp_path, streams, cfg=None):
    cfg = cfg or _cfg()
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    ctx = ToolContext(permissions=pm, memory=mem)
    prov = build_provider(cfg, "SYSTEM", build_registry(), ctx, client=DSClient(streams))
    return prov, mem


def _tool_chunk(tid, name, args, signatur=None):
    extra = {"extra_content": {"google": {"thought_signature": signatur}}} if signatur else {}
    tc = SimpleNamespace(index=0, id=tid, function=SimpleNamespace(name=name, arguments=args), model_extra=extra)
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))],
                           usage=None)


def _usage(prompt, completion, cached=0):
    details = SimpleNamespace(cached_tokens=cached)
    return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                                                              prompt_tokens_details=details))


def _hat_schluessel(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_hat_schluessel(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_hat_schluessel(v, key) for v in obj)
    return False


def test_gemini_wird_gewaehlt_und_fragt_richtig_an(tmp_path):
    prov, mem = _provider(tmp_path, [[ds_text_chunk("Hallo!"), _usage(1000, 50, cached=800)]])
    assert isinstance(prov, GeminiProvider)
    assert prov.respond("Hi") == "Hallo!"
    kw = prov.client.chat.completions.last_kwargs
    assert kw["model"] == "gemini-3.8-flash" and kw["reasoning_effort"] == "low"
    assert "extra_body" not in kw and kw["max_tokens"] >= 16384
    assert not _hat_schluessel(kw["tools"], "additionalProperties")
    assert not _hat_schluessel(kw["tools"], "strict")
    # Cache-Treffer werden guenstiger verbucht
    assert prov.usage.cache_hit_tokens == 800 and prov.usage.input_full_tokens == 200
    assert prov.usage.output_tokens == 50
    mem.close()


def test_denk_signatur_geht_unveraendert_zurueck(tmp_path):
    streams = [[_tool_chunk("call_1", "system_info", "{}", signatur="SIG-123"), _usage(10, 5)],
               [ds_text_chunk("Fertig."), _usage(10, 5)]]
    prov, mem = _provider(tmp_path, streams)
    assert prov.respond("Systeminfo") == "Fertig."
    zweite = prov.client.chat.completions.requests[1]
    assistent = next(m for m in zweite if m.get("role") == "assistant")
    assert assistent["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "SIG-123"
    assert "reasoning_content" not in assistent
    mem.close()


def test_fehlende_signatur_bekommt_den_platzhalter(tmp_path):
    streams = [[_tool_chunk("call_1", "system_info", "{}"), _usage(10, 5)],
               [ds_text_chunk("Fertig."), _usage(10, 5)]]
    prov, mem = _provider(tmp_path, streams)
    prov.respond("Systeminfo")
    zweite = prov.client.chat.completions.requests[1]
    assistent = next(m for m in zweite if m.get("role") == "assistant")
    assert assistent["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == SIGNATUR_PLATZHALTER
    mem.close()


def test_denk_tiefe_und_live_modus(tmp_path):
    cfg = _cfg()
    cfg.gemini.denken = "high"
    prov, mem = _provider(tmp_path, [[ds_text_chunk("ok"), _usage(1, 1)]], cfg)
    prov.respond("x")
    assert prov.client.chat.completions.last_kwargs["reasoning_effort"] == "high"
    assert prov.client.chat.completions.last_kwargs["max_tokens"] >= 32768
    prov.effort_override = "low"  # Jarvis-Modus: Tempo zaehlt
    prov.respond("y")
    assert prov.client.chat.completions.last_kwargs["reasoning_effort"] == "low"
    mem.close()


def test_schluessel_werden_erkannt_und_nie_an_die_ki_geschickt():
    assert schluessel.find_key("hier: AQ.Ab8RN6Kj_test-Schluessel-123456 danke") == "AQ.Ab8RN6Kj_test-Schluessel-123456"
    alt = "AIza" + "S" * 35
    assert schluessel.find_key(f"mein key {alt}") == alt
    assert schluessel.provider_for_key(alt) == "gemini"
    assert schluessel.provider_for_key("AQ.Ab12345678901234567890") == "gemini"
    assert schluessel.provider_for_key("sk-ant-abc") == "claude"
    assert schluessel.find_key("Aquarium AQ. kurz") is None


def test_gemini_fehlermeldungen():
    class Fehler(Exception):
        def __init__(self, text, status):
            super().__init__(text)
            self.status_code = status

    art, text = schluessel.classify(Fehler("RESOURCE_EXHAUSTED: quota exceeded", 429), "gemini")
    assert art == "busy" and "Kontingent" in text
    art, _ = schluessel.classify(Fehler("API key not valid. Please pass a valid API key.", 400), "gemini")
    assert art == "invalid"
    art, text = schluessel.classify(Fehler("User location is not supported for the API use.", 400), "gemini")
    assert art == "forbidden" and "Land" in text


def test_schluessel_speichern_und_gehirn_wechseln(tmp_path, monkeypatch):
    # save_key setzt GEMINI_API_KEY in os.environ - so stellt monkeypatch den alten Zustand wieder her
    monkeypatch.setenv("GEMINI_API_KEY", "")
    cfg = load_config(tmp_path)
    cfg.provider.aktiv = "claude"
    r = schluessel.setup(cfg, key="AQ.Ab-gueltig-1234567890abcdef", tester=lambda c, p, k: (True, "ok", ""))
    assert r["ok"] and r["provider"] == "gemini" and cfg.active_provider == "gemini"
    assert cfg.gemini_api_key == "AQ.Ab-gueltig-1234567890abcdef" and cfg.api_key == cfg.gemini_api_key
    assert "GEMINI_API_KEY=AQ.Ab-gueltig-1234567890abcdef" in (tmp_path / ".env").read_text(encoding="utf-8")
    beschr = schluessel.describe(cfg)
    gem = next(p for p in beschr["providers"] if p["id"] == "gemini")
    assert gem["has_key"] and gem["model"] == "gemini-3.8-flash"
    assert [m["id"] for m in beschr["modelle"]["gemini"]["modelle"]][0] == "gemini-3.8-flash"


def test_ohne_anderen_schluessel_wird_gemini_automatisch_genommen(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.Ab-aus-der-umgebung-1234567890")
    cfg = load_config(tmp_path)
    assert cfg.active_provider == "gemini" and cfg.provider_auto_switched == "claude"


def test_modelle_preise_und_alte_namen():
    vorher = datetime(2026, 11, 20, tzinfo=timezone.utc)
    nachher = datetime(2026, 12, 2, tzinfo=timezone.utc)
    assert modelle.preise("gemini", "gemini-4-carbon", now=vorher) == (2.0, 0.1, 10.0)
    assert modelle.preise("gemini", "gemini-4-carbon", now=nachher) == (4.0, 0.2, 20.0)
    assert modelle.preise("gemini", "gemini-3.5-flash-lite", now=nachher) == (0.3, 0.03, 2.5)
    assert modelle._finde_modell("gemini", "carbon") == "gemini-4-carbon"
    assert modelle._finde_modell("gemini", "gemini-2.5-flash") == "gemini-3.8-flash"
    assert modelle.fremdes_modell("hydrogen") == "gemini"
    assert modelle.sieht_bilder("gemini", "gemini-irgendwas-neues")
    cfg = SimpleNamespace(gemini=SimpleNamespace(model="gemini-2.5-pro", denken="gruendlich", base_url="x",
                                                 max_tokens="viel"))
    modelle.normalisiere_gemini(cfg.gemini)
    assert cfg.gemini.model == "gemini-4-argon" and cfg.gemini.denken == "high"
    assert cfg.gemini.base_url.startswith("https://generativelanguage") and cfg.gemini.max_tokens == 16384


def test_modell_und_denktiefe_waehlen(tmp_path):
    cfg = load_config(tmp_path)
    r = modelle.waehle(cfg, provider="gemini", model="argon", denken="gruendlich")
    assert r["ok"] and cfg.gemini.model == "gemini-4-argon" and cfg.gemini.denken == "high"
    assert "Gemini 4 Argon" in r["message"]
    r = modelle.waehle(cfg, provider="gemini", model="opus")
    assert not r["ok"]
