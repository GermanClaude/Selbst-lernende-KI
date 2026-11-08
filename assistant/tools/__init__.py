"""Werkzeug-Sammlung und Aufbau des Registry.

build_registry() stellt alle Werkzeuge zusammen. Welche gefaehrlichen Werkzeuge
tatsaechlich wirken, entscheidet zur Laufzeit der PermissionManager - hier werden
sie nur bekannt gemacht, damit das Modell weiss, dass es sie (nach Freigabe)
nutzen kann.
"""
from __future__ import annotations

from . import (abwesenheit, agents, aussehen, bild_tools, computer, filesystem, gehirn, memory_tools, sehen,
               shell, spiel, system_info, web)
from .base import Tool, ToolContext, ToolRegistry

__all__ = ["READ_ONLY_TOOLS", "Tool", "ToolContext", "ToolRegistry", "build_registry", "subset"]


def build_registry(include_computer: bool = True, include_agents: bool = True) -> ToolRegistry:
    registry = ToolRegistry()
    memory_tools.register(registry)
    filesystem.register(registry)
    system_info.register(registry)
    web.register(registry)
    shell.register(registry)
    if include_computer:
        computer.register(registry)
    if include_agents:
        agents.register(registry)
    aussehen.register(registry)
    bild_tools.register(registry)
    gehirn.register(registry)
    abwesenheit.register(registry)
    sehen.register(registry)
    spiel.register(registry)
    return registry


# Werkzeuge, die nur lesen - fuer Agenten, die nichts veraendern sollen.
READ_ONLY_TOOLS = ("datei_lesen", "ordner_auflisten", "web_suche", "web_abrufen", "system_info", "erinnern")


def subset(registry: ToolRegistry, names) -> ToolRegistry:
    """Neues Registry mit nur den genannten Werkzeugen (die es im Original gibt)."""
    result = ToolRegistry()
    for name in names:
        tool = registry.get(name)
        if tool is not None:
            result.register(tool)
    return result
