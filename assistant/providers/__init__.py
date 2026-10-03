"""Provider: austauschbare "Gehirne" (Claude oder DeepSeek).

build_provider() waehlt anhand der Konfiguration das aktive Gehirn.
"""
from __future__ import annotations

from ..config import Config
from ..tools import ToolContext, ToolRegistry
from .base import LLMProvider, Usage

__all__ = ["LLMProvider", "Usage", "build_provider"]


def build_provider(
    config: Config,
    system_prompt: str,
    registry: ToolRegistry,
    tool_ctx: ToolContext,
    client: object | None = None,
) -> LLMProvider:
    if config.active_provider == "deepseek":
        from .deepseek_provider import DeepSeekProvider

        return DeepSeekProvider(config, system_prompt, registry, tool_ctx, client=client)
    from .anthropic_provider import AnthropicProvider

    return AnthropicProvider(config, system_prompt, registry, tool_ctx, client=client)
