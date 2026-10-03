from assistant.config import load_config, DEFAULT_MODEL, DEFAULT_DEEPSEEK_MODEL


def test_load_config_defaults():
    cfg = load_config()
    assert cfg.active_provider == "claude"
    assert cfg.claude.model == DEFAULT_MODEL
    assert cfg.deepseek.model == DEFAULT_DEEPSEEK_MODEL
    assert cfg.active_model == DEFAULT_MODEL
    assert cfg.ki.name
    assert cfg.permissions.safe_mode is True
    assert cfg.persona_text
    assert cfg.values_text


def test_workspace_path_created():
    cfg = load_config()
    ws = cfg.workspace_path
    assert ws.exists() and ws.is_dir()


def test_env_model_override_targets_active_provider(monkeypatch):
    monkeypatch.setenv("KI_MODEL", "deepseek-flash")
    cfg = load_config()
    # Standard-Provider ist claude -> Override trifft claude.model
    assert cfg.claude.model == "deepseek-flash"


def test_compact_threshold_uses_economy():
    cfg = load_config()
    # Sparmodus ist standardmaessig an -> frueherer Schwellwert.
    assert cfg.compact_threshold == cfg.economy.verlauf_kompakt_nach


def test_cost_estimate_deepseek_cheaper_than_claude():
    cfg = load_config()
    # Gleiche Token: DeepSeek-Preise sind viel niedriger.
    cfg.provider.aktiv = "deepseek"
    ds_usd, _ = cfg.cost_estimate(10_000, 0, 1_000)
    cfg.provider.aktiv = "claude"
    cl_usd, _ = cfg.cost_estimate(10_000, 0, 1_000)
    assert ds_usd < cl_usd


def test_cost_estimate_cache_hits_are_cheap():
    cfg = load_config()
    cfg.provider.aktiv = "deepseek"
    full_usd, _ = cfg.cost_estimate(10_000, 0, 0)
    cached_usd, _ = cfg.cost_estimate(0, 10_000, 0)
    assert cached_usd < full_usd
