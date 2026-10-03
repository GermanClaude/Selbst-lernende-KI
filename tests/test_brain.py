"""Testet die schlanke Brain-Orchestrierung mit einem Fake-Provider."""
from assistant.config import load_config
from assistant.memory import Memory
from assistant.permissions import PermissionManager
from assistant.tools import build_registry, ToolContext
from assistant.brain import Brain
from assistant.providers.base import LLMProvider, Usage


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, cfg, mem):
        reg = build_registry()
        ctx = ToolContext(permissions=PermissionManager(cfg.permissions, cfg.workspace_path), memory=mem)
        super().__init__(cfg, "SYSTEM", reg, ctx)
        self._len = 0
        self.reset_called = False
        self.usage = Usage(input_full_tokens=100, cache_hit_tokens=50, output_tokens=25)

    def respond(self, user_text, on_text=None, max_tool_rounds=25):
        self._len += 2
        if on_text:
            on_text("Antwort")
        return "Antwort"

    def history_length(self):
        return self._len

    def summarize_history(self):
        return "Zusammenfassung des Gespraechs"

    def reset_to_summary(self, summary):
        self.reset_called = True
        self._len = 2


def _brain(tmp_path):
    cfg = load_config()
    cfg.economy.verlauf_kompakt_nach = 4  # frueh kompaktieren fuer den Test
    mem = Memory(tmp_path / "m.sqlite3")
    prov = FakeProvider(cfg, mem)
    brain = Brain(cfg, mem, prov.registry, prov.tool_ctx, provider=prov)
    return brain, mem, prov


def test_respond_delegates(tmp_path):
    brain, mem, prov = _brain(tmp_path)
    out = brain.respond("Hallo")
    assert out == "Antwort"
    mem.close()


def test_compaction_triggers_and_saves_episode(tmp_path):
    brain, mem, prov = _brain(tmp_path)
    brain.respond("1")  # len 2
    brain.respond("2")  # len 4 -> >= threshold 4 -> kompaktieren
    assert prov.reset_called
    assert len(mem.recent_episodes()) >= 1
    mem.close()


def test_cost_exposed(tmp_path):
    brain, mem, prov = _brain(tmp_path)
    usd, eur = brain.cost()
    assert usd > 0 and eur > 0
    assert brain.usage.total_tokens == 175
    mem.close()
