"""Zentrale Logging-Konfiguration."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_dir: str | Path = "logs", level: int = logging.INFO) -> logging.Logger:
    """Richtet Datei- und Konsolen-Logging ein und gibt den Haupt-Logger zurueck."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ki")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path / "ki.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Auf der Konsole nur Warnungen/Fehler, damit der Chat sauber bleibt.
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    console.setLevel(logging.WARNING)
    logger.addHandler(console)

    logger.propagate = False
    return logger


def get_logger(name: str = "ki") -> logging.Logger:
    return logging.getLogger(name)
