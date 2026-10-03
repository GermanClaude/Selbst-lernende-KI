"""Konfiguration laden: Provider, Einstellungen, Persona, Werte, Umgebung.

Die .env-Datei wird ohne Zusatzabhaengigkeit (kein python-dotenv noetig) gelesen.
Es gibt zwei "Gehirne" zur Auswahl:
  * claude   - Anthropic (sehr stark)
  * deepseek - DeepSeek (OpenAI-kompatibel, extrem guenstig)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+ bringt tomllib mit
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - Fallback fuer 3.10
    import tomli as tomllib  # type: ignore

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Liest eine einfache KEY=VALUE .env-Datei in os.environ (ohne Ueberschreiben)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class ProviderSettings:
    # Welches Gehirn aktiv ist: "claude" oder "deepseek".
    aktiv: str = "claude"


@dataclass
class ClaudeSettings:
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_tokens: int = 16000
    server_side_fallback: bool = False


@dataclass
class DeepSeekSettings:
    model: str = DEFAULT_DEEPSEEK_MODEL
    base_url: str = "https://api.deepseek.com"
    max_tokens: int = 2048
    temperature: float = 0.6


@dataclass
class KISettings:
    name: str = "Aria"
    language: str = "de"


@dataclass
class EconomySettings:
    # Spart Token, ohne an Qualitaet einzubuessen.
    aktiv: bool = True
    knapp_antworten: bool = True        # System-Prompt bittet um knappe Antworten
    max_werkzeug_ausgabe: int = 6000    # Werkzeug-Ausgaben kuerzen (Zeichen)
    verlauf_kompakt_nach: int = 24      # Verlauf frueh zusammenfassen (0 = aus)


@dataclass
class PriceSettings:
    # US-Dollar pro 1 Mio. Token. Bei Preisaenderung einfach hier anpassen.
    claude_input: float = 4.0
    claude_cache_hit: float = 0.4
    claude_output: float = 20.0
    deepseek_input: float = 0.28
    deepseek_cache_hit: float = 0.028
    deepseek_output: float = 0.42
    usd_zu_eur: float = 0.92

    def for_provider(self, provider: str) -> tuple[float, float, float]:
        """Gibt (input, cache_hit, output) in USD/1M fuer den Provider zurueck."""
        if provider == "deepseek":
            return (self.deepseek_input, self.deepseek_cache_hit, self.deepseek_output)
        return (self.claude_input, self.claude_cache_hit, self.claude_output)


@dataclass
class MemorySettings:
    db_path: str = "data/memory.sqlite3"
    max_facts_in_context: int = 60


@dataclass
class ConversationSettings:
    compact_after_messages: int = 40


@dataclass
class VoiceSettings:
    enabled: bool = False
    speak_responses: bool = False
    wake_word: str = ""


@dataclass
class PermissionSettings:
    safe_mode: bool = True
    auto_confirm: bool = False
    workspace_root: str = ""
    allow_full_filesystem: bool = False
    use_quarantine: bool = True
    shell_allowlist: list[str] = field(default_factory=list)
    shell_denylist: list[str] = field(default_factory=list)


@dataclass
class Config:
    provider: ProviderSettings
    claude: ClaudeSettings
    deepseek: DeepSeekSettings
    ki: KISettings
    economy: EconomySettings
    prices: PriceSettings
    memory: MemorySettings
    conversation: ConversationSettings
    voice: VoiceSettings
    permissions: PermissionSettings
    persona_text: str
    values_text: str
    project_root: Path
    anthropic_api_key: str | None
    deepseek_api_key: str | None

    # -- Komfort-Eigenschaften ---------------------------------------------
    @property
    def active_provider(self) -> str:
        return (self.provider.aktiv or "claude").strip().lower()

    @property
    def active_model(self) -> str:
        return self.deepseek.model if self.active_provider == "deepseek" else self.claude.model

    @property
    def api_key(self) -> str | None:
        """Der Schluessel des aktiven Providers."""
        return self.deepseek_api_key if self.active_provider == "deepseek" else self.anthropic_api_key

    @property
    def compact_threshold(self) -> int:
        if self.economy.aktiv and self.economy.verlauf_kompakt_nach > 0:
            return self.economy.verlauf_kompakt_nach
        return self.conversation.compact_after_messages

    @property
    def workspace_path(self) -> Path:
        root = self.permissions.workspace_root.strip()
        path = Path(root).expanduser() if root else self.project_root / "workspace"
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def cost_estimate(self, input_full: int, cache_hit: int, output: int) -> tuple[float, float]:
        """Schaetzt die Kosten (USD, EUR) fuer die gegebenen Token-Zahlen."""
        in_price, hit_price, out_price = self.prices.for_provider(self.active_provider)
        usd = (input_full * in_price + cache_hit * hit_price + output * out_price) / 1_000_000
        return (usd, usd * self.prices.usd_zu_eur)


def _read_text(path: Path, fallback: str = "") -> str:
    return path.read_text(encoding="utf-8") if path.exists() else fallback


def _merge(dc_instance: Any, data: dict[str, Any]) -> Any:
    """Uebernimmt bekannte Schluessel aus 'data' in eine Dataclass-Instanz."""
    for key, value in data.items():
        if hasattr(dc_instance, key):
            setattr(dc_instance, key, value)
    return dc_instance


def load_config(project_root: Path | None = None) -> Config:
    """Laedt die komplette Konfiguration. Fehlt settings.toml, gelten Standardwerte."""
    root = (project_root or PROJECT_ROOT).resolve()
    _load_env_file(root / ".env")

    config_dir = root / "config"
    settings_path = config_dir / "settings.toml"
    if not settings_path.exists():
        settings_path = config_dir / "settings.example.toml"

    raw: dict[str, Any] = {}
    if settings_path.exists():
        with settings_path.open("rb") as fh:
            raw = tomllib.load(fh)

    provider = _merge(ProviderSettings(), raw.get("provider", {}))
    claude = _merge(ClaudeSettings(), raw.get("claude", {}))
    deepseek = _merge(DeepSeekSettings(), raw.get("deepseek", {}))

    # Modell per Umgebungsvariable erzwingen (zielt auf den aktiven Provider).
    if os.environ.get("KI_MODEL"):
        if (provider.aktiv or "claude").strip().lower() == "deepseek":
            deepseek.model = os.environ["KI_MODEL"]
        else:
            claude.model = os.environ["KI_MODEL"]

    cfg = Config(
        provider=provider,
        claude=claude,
        deepseek=deepseek,
        ki=_merge(KISettings(), raw.get("ki", {})),
        economy=_merge(EconomySettings(), raw.get("sparsam", {})),
        prices=_merge(PriceSettings(), raw.get("preise", {})),
        memory=_merge(MemorySettings(), raw.get("memory", {})),
        conversation=_merge(ConversationSettings(), raw.get("conversation", {})),
        voice=_merge(VoiceSettings(), raw.get("voice", {})),
        permissions=_merge(PermissionSettings(), raw.get("permissions", {})),
        persona_text=_read_text(config_dir / "persona.md"),
        values_text=_read_text(config_dir / "werte.md"),
        project_root=root,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
    )
    return cfg
