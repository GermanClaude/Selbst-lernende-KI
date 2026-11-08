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
from .selbststart import is_autostart_path, sets_up_autostart, starts_the_ki

AUTOSTART_WARNING = (
    "ACHTUNG: Das richtet einen AUTOMATISCHEN START ein (Aufgabenplanung/Autostart). "
    "Danach kann sich ein Programm immer wieder von selbst oeffnen."
)
SELF_START_WARNING = (
    "ACHTUNG: Das wuerde die KI ein weiteres Mal starten (neues Fenster)."
)


class Risk(enum.IntEnum):
    SAFE = 0
    MODERATE = 1
    DANGEROUS = 2
    AUTOSTART = 3  # automatischer Start / KI erneut starten - wird gesondert gefragt


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
        app_root: Path | None = None,
    ):
        self.settings = settings
        self.workspace_root = workspace_root.resolve()
        self.confirm_fn = confirm_fn or _default_confirm
        self.app_root = app_root  # Ordner der KI (fuer "startet sich selbst")
        # AFK-Modus: niemand da, der gefragt werden koennte -> strenger, nie nachfragen.
        self.away = False
        self._away_created: set[Path] = set()
        self._away_write_ok = False  # check_path_write hat die naechste Datei-Aktion freigegeben
        self.away_urls: set[str] = set()  # im AFK-Modus abrufbar: nur Links aus der Websuche

    def begin_away(self) -> None:
        self.away = True
        self._away_created = set()
        self._away_write_ok = False
        self.away_urls = set()

    def end_away(self) -> None:
        self.away = False
        self._away_created = set()
        self._away_write_ok = False
        self.away_urls = set()

    def _in_app_dir(self, resolved: Path) -> bool:
        """Im Ordner der KI selbst (Schluessel, Einstellungen, Programm) - ausser ihrem Arbeitsordner."""
        if not self.app_root:
            return False
        app = Path(self.app_root).resolve()
        return self._is_within(resolved, app) and not self._is_within(resolved, app / "workspace")

    # -- Aktionsfreigabe ----------------------------------------------------
    def check(self, risk: Risk, description: str) -> Decision:
        """Entscheidet, ob eine Aktion der gegebenen Risikostufe laufen darf."""
        # Freigabe aus check_path_write gilt nur fuer genau die naechste Pruefung (dieselbe Datei-Aktion).
        write_ok, self._away_write_ok = self._away_write_ok, False
        if risk >= Risk.DANGEROUS and self.settings.safe_mode:
            return Decision(
                False,
                "Safe Mode ist aktiv - gefaehrliche Aktionen sind gesperrt. "
                "Zum Freischalten in config/settings.toml 'safe_mode = false' setzen.",
            )
        if risk == Risk.SAFE:
            return Decision(True)
        if self.away:
            # Nur NEUE Dateien im Arbeitsordner (von check_path_write geprueft) - alles andere
            # Veraendernde nein (Aussehen, Bildschirmfoto, ...). Nachgefragt wird nie: niemand da.
            if risk == Risk.MODERATE and write_ok:
                return Decision(True)
            return Decision(False, _away_denied())
        if self.settings.auto_confirm:
            return Decision(True)
        # Nachfragen.
        if self.confirm_fn(description, risk):
            return Decision(True)
        return Decision(False, "Vom Nutzer abgelehnt.")

    def confirm_always(self, description: str) -> Decision:
        """Fragt IMMER nach - auch bei auto_confirm (fuer Autostart & Co.).

        Abschaltbar mit [permissions] autostart_immer_fragen = false.
        """
        if self.away:
            return Decision(False, _away_denied())
        if self.settings.auto_confirm and not self.settings.autostart_immer_fragen:
            return Decision(True)
        if self.confirm_fn(description, Risk.AUTOSTART):
            return Decision(True)
        return Decision(
            False,
            "Vom Nutzer abgelehnt. Richte keinen automatischen Start ein und starte die KI "
            "nicht selbst, ausser dein Mensch bittet ausdruecklich darum.",
        )

    def check_path_write(self, path: Path) -> Decision:
        """Schreiben in einen Autostart-Ordner nur mit ausdruecklicher Zustimmung.

        Im AFK-Modus: nur NEUE Dateien im Arbeitsordner (bzw. solche, die in dieser
        Abwesenheit selbst angelegt wurden) - nichts Bestehendes ueberschreiben. Die Freigabe
        gilt nur fuer genau die naechste Pruefung (diese Datei-Aktion) und nur, wenn alles passt."""
        self._away_write_ok = False
        if self.away:
            resolved = Path(path).resolve()
            if not self._is_within(resolved, self.workspace_root) or self._in_app_dir(resolved):
                return Decision(False, "Solange dein Mensch weg ist, schreibst du nur in den Arbeitsordner. "
                                       + _away_denied())
            if resolved.exists() and resolved not in self._away_created:
                return Decision(False, "Diese Datei gab es schon - solange dein Mensch weg ist, ueberschreibst "
                                       "du nichts. Leg eine neue Datei an (z.B. mit '-entwurf' im Namen) oder "
                                       "schreib die Aenderung als Vorschlag auf.")
            if is_autostart_path(path):
                return Decision(False, _away_denied())
            self._away_created.add(resolved)
            self._away_write_ok = True
            return Decision(True)
        if is_autostart_path(path):
            return self.confirm_always(f"{AUTOSTART_WARNING}\n    Datei: {path}")
        return Decision(True)

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

        # Im AFK-Modus nur der Arbeitsordner - auch zum Lesen (Schutz vor eingeschleusten
        # Anweisungen aus Webseiten, z.B. "lies die .env und schick sie an ...").
        if self.settings.allow_full_filesystem and not self.away:
            if must_exist and not resolved.exists():
                raise FileNotFoundError(f"Pfad existiert nicht: {resolved}")
            return resolved

        if self.away and self._in_app_dir(resolved):
            raise PermissionError_("Solange dein Mensch weg ist (AFK-Modus), nicht im Ordner der KI selbst.")
        if not self._is_within(resolved, self.workspace_root):
            if self.away:
                raise PermissionError_(f"Solange dein Mensch weg ist (AFK-Modus), nur im Arbeitsordner: {resolved}")
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
    def check_shell(self, command: str, cwd: str | None = None) -> Decision:
        """Prueft einen Shell-Befehl gegen Verbots-/Erlaubnisliste und Safe Mode."""
        if self.away:
            return Decision(False, _away_denied())
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
        # Diese beiden fragen IMMER nach, auch bei auto_confirm: genau daraus entstehen
        # KI-Fenster, die sich "von selbst" immer wieder oeffnen.
        if sets_up_autostart(command):
            return self.confirm_always(f"{AUTOSTART_WARNING}\n    {command}")
        if starts_the_ki(command, self.app_root, cwd):
            return self.confirm_always(f"{SELF_START_WARNING}\n    {command}")
        first_word = lowered.split()[0] if lowered.split() else ""
        if self.settings.auto_confirm:
            return Decision(True)
        if first_word in [c.lower() for c in self.settings.shell_allowlist]:
            return Decision(True)  # Harmlose Standardbefehle ohne Rueckfrage.
        if self.confirm_fn(f"Shell-Befehl ausfuehren:\n    {command}", Risk.DANGEROUS):
            return Decision(True)
        return Decision(False, "Vom Nutzer abgelehnt.")


def _away_denied() -> str:
    from .abwesend import AWAY_DENIED

    return AWAY_DENIED
