"""Werkzeug-Sammlung und Aufbau des Registry.

build_registry() stellt alle Werkzeuge zusammen. Welche gefaehrlichen Werkzeuge
tatsaechlich wirken, entscheidet zur Laufzeit der PermissionManager - hier werden
sie nur bekannt gemacht, damit das Modell weiss, dass es sie (nach Freigabe)
nutzen kann.
"""
from __future__ import annotations

from . import computer, filesystem, memory_tools, shell, system_info, web
from .base import Tool, ToolContext, ToolRegistry

__all__ = ["Tool", "ToolContext", "ToolRegistry", "build_registry"]


def build_registry(include_computer: bool = True) -> ToolRegistry:
    registry = ToolRegistry()
    memory_tools.register(registry)
    filesystem.register(registry)
    system_info.register(registry)
    web.register(registry)
    shell.register(registry)
    if include_computer:
        computer.register(registry)
    return registry
