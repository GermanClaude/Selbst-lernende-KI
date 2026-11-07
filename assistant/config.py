"""Konfiguration laden: Provider, Einstellungen, Persona, Werte, Umgebung.

Die .env-Datei wird ohne Zusatzabhaengigkeit (kein python-dotenv noetig) gelesen.
Es gibt zwei "Gehirne" zur Auswahl:
  * claude   - Anthropic (sehr stark)
  * deepseek - DeepSeek (OpenAI-kompatibel, extrem guenstig)
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+ bringt tomllib mit
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - Fallback fuer 3.10
    import tomli as tomllib  # type: ignore

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


class ConfigError(Exception):
    """Eine Einstellungsdatei ist fehlerhaft - mit verstaendlicher Meldung."""


def find_app_root() -> Path:
    """Der Ordner, in dem .env, config/, data/ und workspace/ liegen.

    Aus dem Quellcode: der Projektordner. Als gepackte KI.exe: der Ordner der .exe -
    NICHT __file__, denn das zeigt dort in PyInstallers temporaeren Entpack-Ordner.
    Liegt die .exe im 'dist'-Ordner des Projekts (so wie build.bat sie ablegt) und
    steht die .env nur im Projektordner, wird der Projektordner genutzt.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    exe_dir = Path(sys.executable).resolve().parent
    parent = exe_dir.parent
    if (parent / "config").is_dir() and not (exe_dir / ".env").is_file():
        # Die .env entscheidet (aeltere Versionen legten neben der .exe schon eine
        # settings.toml an, die sonst die Projekt-.env verdecken wuerde).
        if (parent / ".env").is_file():
            return parent
        if (parent / "config" / "settings.toml").is_file() and not (
            exe_dir / "config" / "settings.toml"
        ).is_file():
            return parent
    return exe_dir


def bundle_dir() -> Path:
    """Wo die mitgelieferten Vorlagen liegen (in der .exe: der Entpack-Ordner)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


PROJECT_ROOT = find_app_root()


def _load_env_file(path: Path) -> None:
    """Liest eine einfache KEY=VALUE .env-Datei in os.environ.

    Bereits gesetzte (nicht leere) Umgebungsvariablen haben Vorrang. Platzhalter aus
    .env.example (z.B. 'sk-ant-...') werden ignoriert.
    """
    if not path.is_file():
        return
    # utf-8-sig: Notepad speichert manchmal mit BOM, sonst hiesse der erste Schluessel
    # "\ufeffANTHROPIC_API_KEY" und wuerde nie gefunden.
    text = path.read_bytes().decode("utf-8-sig", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not value or value.endswith("..."):
            continue
        # API-Schluessel aus .env gewinnen: sonst ueberdeckt eine alte Windows-Umgebungsvariable
        # still den Schluessel, den du in der App/.env eingetragen hast.
        if not os.environ.get(key) or key.endswith("_API_KEY"):
            os.environ[key] = value


@dataclass
class ProviderSettings:
    # Welches Gehirn aktiv ist: "claude" oder "deepseek".
    aktiv: str = "claude"


@dataclass
class ClaudeSettings:
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_tokens: int = 32000
    server_side_fallback: bool = False


@dataclass
class DeepSeekSettings:
    model: str = DEFAULT_DEEPSEEK_MODEL
    base_url: str = "https://api.deepseek.com"
    max_tokens: int = 8192  # kleiner = grosse Dateien brechen beim Schreiben ab
    temperature: float = 0.6


DEFAULT_NAME = "Nova"
DEFAULT_MEANING = "Neugierige, Offene, Vernetzte Assistenz"


@dataclass
class KISettings:
    name: str = DEFAULT_NAME
    # Wofuer die Buchstaben des Namens stehen (wird angezeigt; leer = nichts).
    bedeutung: str = DEFAULT_MEANING
    # Zuletzt gewaehlter Charakter (/charakter); die Persoenlichkeit steht in persona.md.
    charakter: str = ""
    language: str = "de"
    # Laeuft die KI schon, oeffnet sich kein zweites Fenster.
    nur_ein_fenster: bool = True
    # "terminal" oder "app": womit start.bat die KI oeffnet (start-app.bat = immer App).
    oberflaeche: str = "terminal"


@dataclass
class StyleSettings:
    # Wie die KI spricht - im Chat mit /stil oder in der App unter "Charakter".
    anrede: str = "du"          # du | Sie
    laenge: str = "normal"      # kurz | normal | ausfuehrlich
    humor: str = "etwas"        # kein | etwas | viel
    emojis: str = "aus"         # aus | an


@dataclass
class EconomySettings:
    # Spart Token, ohne an Qualitaet einzubuessen.
    aktiv: bool = True
    knapp_antworten: bool = True        # System-Prompt bittet um knappe Antworten
    max_werkzeug_ausgabe: int = 6000    # Werkzeug-Ausgaben kuerzen (Zeichen)
    verlauf_kompakt_nach: int = 24      # nach so vielen DEINER Nachrichten zusammenfassen (0 = aus)


@dataclass
class PriceSettings:
    # US-Dollar pro 1 Mio. Token. Bei Preisaenderung einfach hier anpassen.
    claude_input: float = 4.0
    claude_cache_hit: float = 0.2
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
    # Nach so vielen Nachrichten von DIR wird der Verlauf zusammengefasst.
    # Werkzeug-Schritte der KI zaehlen nicht mit.
    compact_after_messages: int = 40
    # Zusaetzlich zusammenfassen, wenn der Verlauf groesser als so viele Zeichen
    # wird (~4 Zeichen = 1 Token). Schuetzt vor zu vollem Kontext. 0 = aus.
    max_verlauf_zeichen: int = 400_000
    # So viele Werkzeug-Schritte darf die KI pro Nachricht machen, bevor sie
    # anhaelt und fragt, ob sie weitermachen soll.
    max_werkzeug_runden: int = 60
    # Am Schritt-Limit automatisch so oft weiterarbeiten, bevor sie nachfragt
    # (0 = immer nachfragen). Strg+C haelt jederzeit an.
    automatisch_weiter: int = 3
    # So viele Werkzeug-Schritte darf ein Agent (agent_beauftragen) machen.
    agent_runden: int = 40


@dataclass
class VoiceSettings:
    enabled: bool = False
    speak_responses: bool = False
    wake_word: str = ""
    # F2 = Sprechtaste: halten = sprechen, kurz druecken = Mikrofon an/aus.
    f2_aufnahme: bool = True
    # Spracherkennung: "auto" (Whisper, falls installiert, sonst Google),
    # "whisper" (offline, faster-whisper) oder "google" (online, kostenlos).
    erkennung: str = "auto"
    whisper_modell: str = "small"
    sprache: str = "de"
    # Live-Sprachmodus (Jarvis): Mitschrift waehrend des Sprechens (Vosk, offline),
    # Sprechpause bis zur Antwort, Dazwischenreden stoppt Nova.
    live_mitschrift: bool = True
    pause: float = 0.6
    unterbrechen: bool = True
    # True = den Satz zusaetzlich mit Google/Whisper erkennen (genauer, ~1 s langsamer)
    live_genau: bool = False
    # Wie tief Claude im Sprachmodus nachdenkt: "low" = schnell, "" = wie im Chat
    live_denktiefe: str = "low"
    live_modell: str = ""  # leer = passendes kleines Vosk-Modell zur Sprache


@dataclass
class UpdateSettings:
    # "automatisch" = neue Versionen selbst installieren, "fragen" = vorher fragen,
    # "aus" = nie nachschauen.
    modus: str = "automatisch"
    repo: str = "GermanClaude/Selbst-lernende-KI"
    # Leer = Standard-Branch des Repos (dort landen fertige Versionen).
    branch: str = ""
    pruefen_alle_stunden: int = 24
    alte_versionen_behalten: int = 5


@dataclass
class PermissionSettings:
    safe_mode: bool = True
    auto_confirm: bool = False
    workspace_root: str = ""
    allow_full_filesystem: bool = False
    use_quarantine: bool = True
    shell_allowlist: list[str] = field(default_factory=list)
    shell_denylist: list[str] = field(default_factory=list)
    # Auch bei auto_confirm nachfragen, bevor ein automatischer Start eingerichtet
    # oder die KI erneut gestartet wird (sonst oeffnen sich Fenster "von selbst").
    autostart_immer_fragen: bool = True


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
    settings_file: Path | None = None  # tatsaechlich gelesene Einstellungsdatei
    update: UpdateSettings = field(default_factory=UpdateSettings)
    style: StyleSettings = field(default_factory=StyleSettings)
    about: dict = field(default_factory=dict)  # "Ueber mich" (config/ueber_mich.json)

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
    if not path.is_file():
        return fallback
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def _load_about(path: Path) -> dict:
    import json

    try:
        data = json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float)) and str(v).strip()} \
        if isinstance(data, dict) else {}


def _first_existing(*paths: Path) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def save_env_value(root: Path, name: str, value: str) -> Path:
    """Schreibt NAME=wert in die .env im Programmordner (andere Zeilen bleiben erhalten)."""
    path = Path(root) / ".env"
    lines = path.read_bytes().decode("utf-8-sig", errors="replace").splitlines() if path.exists() else []
    entry = f"{name}={value}"
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(name)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = entry
            break
    else:
        lines.append(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def toml_string(text: str) -> str:
    """Text als TOML-Zeichenkette (Anfuehrungszeichen, Backslashes usw. sicher maskiert)."""
    import json

    return json.dumps(str(text), ensure_ascii=False)


def save_setting(root: Path, section: str, key: str, value: str) -> Path:
    """Schreibt 'key = value' (TOML-Literal, z.B. 'true') dauerhaft in config/settings.toml.

    Kommentare und alles andere bleiben erhalten. Gibt den Pfad der Datei zurueck.
    """
    import re
    import shutil

    path = Path(root) / "config" / "settings.toml"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        example = _first_existing(path.with_name("settings.example.toml"),
                                  bundle_dir() / "config" / "settings.example.toml")
        if example:
            shutil.copyfile(example, path)
        else:
            path.write_text("", encoding="utf-8")
    lines = path.read_bytes().decode("utf-8-sig").splitlines(keepends=True)
    header = re.compile(r"^\s*\[([^\]]+)\]")
    entry = re.compile(rf"^\s*{re.escape(key)}\s*=")
    current, section_line, done = None, None, False
    for i, line in enumerate(lines):
        m = header.match(line)
        if m:
            current = m.group(1).strip()
            if current == section:
                section_line = i
            continue
        if current == section and entry.match(line):
            lines[i] = f"{key} = {value}\n"
            done = True
            break
    if not done:
        if section_line is not None:
            lines.insert(section_line + 1, f"{key} = {value}\n")
        else:
            lines.append(f"\n[{section}]\n{key} = {value}\n")
    text = "".join(lines)
    tomllib.loads(text)  # nie eine kaputte Datei schreiben
    path.write_text(text, encoding="utf-8")
    return path


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_bytes().decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(
            f"Die Einstellungsdatei ist fehlerhaft und kann nicht gelesen werden:\n"
            f"  {path}\n  {exc}\n"
            "Pruefe die genannte Zeile (Anfuehrungszeichen, = und [Abschnitte])."
        ) from exc


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
    bundled = bundle_dir() / "config"  # Vorlagen in der .exe als letzte Rueckfallebene
    settings_path = _first_existing(
        config_dir / "settings.toml",
        config_dir / "settings.example.toml",
        bundled / "settings.example.toml",
    )
    raw: dict[str, Any] = _load_toml(settings_path) if settings_path else {}

    provider = _merge(ProviderSettings(), raw.get("provider", {}))
    claude = _merge(ClaudeSettings(), raw.get("claude", {}))
    deepseek = _merge(DeepSeekSettings(), raw.get("deepseek", {}))
    # Aeltere settings.toml enthalten die frueheren, zu kleinen Standardwerte
    # (aus settings.example.toml kopiert). Damit brechen grosse Dateien beim
    # Schreiben ab - also wie "nicht gesetzt" behandeln.
    if deepseek.max_tokens == 2048:
        deepseek.max_tokens = DeepSeekSettings.max_tokens
    if claude.max_tokens == 16000:
        claude.max_tokens = ClaudeSettings.max_tokens
    ki = _merge(KISettings(), raw.get("ki", {}))
    if ki.name.strip().lower() == "aria" and "bedeutung" not in raw.get("ki", {}):
        ki.name = DEFAULT_NAME  # frueherer Standardname -> neuer Name

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
        ki=ki,
        economy=_merge(EconomySettings(), raw.get("sparsam", {})),
        prices=_merge(PriceSettings(), raw.get("preise", {})),
        memory=_merge(MemorySettings(), raw.get("memory", {})),
        conversation=_merge(ConversationSettings(), raw.get("conversation", {})),
        voice=_merge(VoiceSettings(), raw.get("voice", {})),
        permissions=_merge(PermissionSettings(), raw.get("permissions", {})),
        persona_text=_read_text(config_dir / "persona.md") or _read_text(bundled / "persona.md"),
        values_text=_read_text(config_dir / "werte.md") or _read_text(bundled / "werte.md"),
        project_root=root,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY"),
        settings_file=settings_path,
        update=_merge(UpdateSettings(), raw.get("update", {})),
        style=_merge(StyleSettings(), raw.get("stil", {})),
        about=_load_about(config_dir / "ueber_mich.json"),
    )
    # Relative Pfade gelten ab dem Programmordner, nicht ab dem aktuellen Verzeichnis.
    db_path = Path(cfg.memory.db_path).expanduser()
    if not db_path.is_absolute():
        cfg.memory.db_path = str(root / db_path)
    return cfg
