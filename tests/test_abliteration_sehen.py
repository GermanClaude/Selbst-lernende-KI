"""Abliteration AI kann 'sehen': Bilder werden von einem seh-faehigen Gehirn beschrieben."""
from types import SimpleNamespace

from assistant import modelle
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.providers import build_provider
from assistant.providers.abliteration_provider import _seh_quelle
from assistant.tools import ToolContext, build_registry
from tests._fakes import DSClient


def _cfg(deepseek=None, gemini=None, openai=None):
    cfg = load_config()
    cfg.provider.aktiv = "abliteration"
    cfg.abliteration_api_key = "ak_test"
    cfg.deepseek_api_key, cfg.gemini_api_key, cfg.openai_api_key = deepseek, gemini, openai
    return cfg


def test_seh_quelle_waehlt_deepseek_zuerst():
    seh = _seh_quelle(_cfg(deepseek="sk-x", openai="sk-proj-y"))
    assert seh and seh["model"] == modelle.DEEPSEEK_SEHMODELL
    assert "max_tokens" in seh["extra"] and seh["extra"]["extra_body"]["thinking"]["type"] == "disabled"


def test_seh_quelle_openai_nutzt_max_completion_tokens():
    seh = _seh_quelle(_cfg(openai="sk-proj-y"))
    assert seh and "max_completion_tokens" in seh["extra"] and "max_tokens" not in seh["extra"]


def test_seh_quelle_none_ohne_seh_gehirn():
    assert _seh_quelle(_cfg()) is None  # nur Abliteration, kein seh-faehiges Gehirn


class _FakeVision:
    """Ein seh-faehiges Gehirn, das jedes Bild gleich beschreibt (ohne Netz)."""
    def __init__(self, text="ein gruener Knopf links oben"):
        self.last = None
        self.text = text
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.last = kw
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


def _prov(tmp_path):
    cfg = _cfg(deepseek="sk-x")
    mem = Memory(tmp_path / "m.sqlite3")
    pm = PermissionManager(cfg.permissions, tmp_path, confirm_fn=lambda m, r: True)
    prov = build_provider(cfg, "SYS", build_registry(), ToolContext(permissions=pm, memory=mem), client=DSClient([]))
    return prov, mem


def _bild():
    return SimpleNamespace(data_url=lambda: "data:image/png;base64,AAAA", platzhalter=lambda: "[Bild: test.png]")


def test_describe_image_nutzt_seh_gehirn(tmp_path):
    prov, mem = _prov(tmp_path)
    fake = _FakeVision()
    prov._seh_geprueft = True
    prov._seh_quelle = {"client": fake, "model": "seh-modell", "extra": {"max_tokens": 1500}}
    assert not prov._sees_images()  # Abliteration selbst sieht nichts
    text = prov._describe_image(_bild())
    assert text == "ein gruener Knopf links oben"
    assert fake.last["model"] == "seh-modell"  # ueber das geliehene Seh-Gehirn
    beschr = prov._describe_images([_bild()])
    assert "Beschreibung: ein gruener Knopf" in beschr
    mem.close()


def test_describe_images_ohne_seh_gehirn_sagt_bescheid(tmp_path):
    prov, mem = _prov(tmp_path)
    prov._seh_geprueft = True
    prov._seh_quelle = None  # kein seh-faehiges Gehirn
    beschr = prov._describe_images([_bild()])
    assert "kein eigenes Bild-Modell" in beschr and "DeepSeek-, Gemini- oder OpenAI-Schluessel" in beschr
    mem.close()
