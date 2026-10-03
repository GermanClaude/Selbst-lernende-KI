"""Sicherheits- und Berechtigungssystem.

Dieses Modul ist das Schutznetz der KI. Jede Aktion hat eine Risikostufe:

    SAFE       - nur lesen / unschaedlich (z.B. Datei lesen, System-Info)
    MODERATE   - veraendernd, aber umkehrbar (Datei schreiben, Download)
    DANGEROUS  - weitreichend / schwer umkehrbar (Loeschen, Shell, PC-Steuerung)

Regeln:
  * safe_mode=true  -> DANGEROUS-Aktionen sind komplett gesperrt.
  * auto_confirm=false -> vor MODERATE/DANGEROUS wird nachgefragt.
  * Pfade werden gegen den Arbeitsordner geprueft (Sandbox), ausser
    allow_full_filesystem=true.
  * Eine Verbotsliste blockiert bestimmte Shell-Muster immer.

So kann die KI "vollen Zugriff" bekommen - aber nur, wenn du es bewusst
freischaltest, und mit einem Netz darunter.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import PermissionSettings


class Risk(enum.IntEnum):
    SAFE = 0
    MODERATE = 1
    DANGEROUS = 2


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


# Eine Funktion, die den Nutzer um Bestaetigung bittet und True/False zurueckgibt.
ConfirmFn = Callable[[str, Risk], bool]


def _default_confirm(_message: str, _risk: Risk) -> bool:
    """Ohne angebundene Oberflaeche wird aus Sicherheitsgruenden abgelehnt."""
    return False


class PermissionError_(Exception):
    """Wird geworfen, wenn eine Aktion durch die Berechtigungen verboten ist."""


class PermissionManager:
    def __init__(
        self,
        settings: PermissionSettings,
        workspace_root: Path,
        confirm_fn: ConfirmFn | None = None,
    ):
        self.settings = settings
        self.workspace_root = workspace_root.resolve()
        self.confirm_fn = confirm_fn or _default_confirm

    # -- Aktionsfreigabe ----------------------------------------------------
    def check(self, risk: Risk, description: str) -> Decision:
        """Entscheidet, ob eine Aktion der gegebenen Risikostufe laufen darf."""
        if risk >= Risk.DANGEROUS and self.settings.safe_mode:
            return Decision(
                False,
                "Safe Mode ist aktiv - gefaehrliche Aktionen sind gesperrt. "
                "Zum Freischalten in config/settings.toml 'safe_mode = false' setzen.",
            )
        if risk == Risk.SAFE:
            return Decision(True)
        if self.settings.auto_confirm:
            return Decision(True)
        # Nachfragen.
        if self.confirm_fn(description, risk):
            return Decision(True)
        return Decision(False, "Vom Nutzer abgelehnt.")

    def require(self, risk: Risk, description: str) -> None:
        """Wie check(), wirft aber bei Ablehnung eine Ausnahme."""
        decision = self.check(risk, description)
        if not decision.allowed:
            raise PermissionError_(decision.reason)

    # -- Pfadpruefung (Sandbox) --------------------------------------------
    def resolve_path(self, raw_path: str, *, must_exist: bool = False) -> Path:
        """Loest einen Pfad auf und stellt sicher, dass er erlaubt ist.

        Standardmaessig nur innerhalb des Arbeitsordners. Verhindert das
        Ausbrechen per '..' oder absoluten Pfaden.
        """
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        resolved = candidate.resolve()

        if self.settings.allow_full_filesystem:
            if must_exist and not resolved.exists():
                raise FileNotFoundError(f"Pfad existiert nicht: {resolved}")
            return resolved

        if not self._is_within(resolved, self.workspace_root):
            raise PermissionError_(
                f"Zugriff ausserhalb des Arbeitsordners ist gesperrt: {resolved}\n"
                f"Arbeitsordner: {self.workspace_root}\n"
                "Zum Erlauben in config/settings.toml 'allow_full_filesystem = true' setzen."
            )
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Pfad existiert nicht: {resolved}")
        return resolved

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    # -- Shell-Pruefung -----------------------------------------------------
    def check_shell(self, command: str) -> Decision:
        """Prueft einen Shell-Befehl gegen Verbots-/Erlaubnisliste und Safe Mode."""
        lowered = command.lower().strip()
        for pattern in self.settings.shell_denylist:
            if pattern.lower() in lowered:
                return Decision(False, f"Befehl enthaelt ein gesperrtes Muster: '{pattern}'")
        if self.settings.safe_mode:
            return Decision(
                False,
                "Safe Mode ist aktiv - Shell-Befehle sind gesperrt. "
                "Zum Freischalten 'safe_mode = false' setzen.",
            )
        first_word = lowered.split()[0] if lowered.split() else ""
        if self.settings.auto_confirm:
            return Decision(True)
        if first_word in [c.lower() for c in self.settings.shell_allowlist]:
            return Decision(True)  # Harmlose Standardbefehle ohne Rueckfrage.
        if self.confirm_fn(f"Shell-Befehl ausfuehren:\n    {command}", Risk.DANGEROUS):
            return Decision(True)
        return Decision(False, "Vom Nutzer abgelehnt.")
