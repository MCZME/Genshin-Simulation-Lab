"""Explicit registration for built-in placeholder content."""

from genshin_sim.content.registry import NOOP_HANDLER_KEY, HandlerRegistry, NoOpRuntimeHandler

BUILTIN_NOOP_HANDLER_KEYS = (
    NOOP_HANDLER_KEY,
    "generic.static_modifiers",
    "generic.test_artifact_set",
    "generic.test_character",
    "generic.test_weapon",
)


def register_builtin_content(registry: HandlerRegistry) -> HandlerRegistry:
    handler = NoOpRuntimeHandler()
    for handler_key in BUILTIN_NOOP_HANDLER_KEYS:
        registry.register_handler(handler_key, handler)
    return registry


def create_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    register_builtin_content(registry)
    return registry
