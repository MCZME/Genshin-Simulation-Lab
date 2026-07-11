"""内置占位内容的显式注册入口。"""

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara import (
    register as register_barbara,
)
from genshin_sim.content.characters.testing.runtime_probe import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.testing.runtime_probe import (
    register as register_runtime_probe,
)
from genshin_sim.content.registry import (
    NOOP_HANDLER_KEY,
    HandlerRegistry,
    NoOpRuntimeHandler,
)

BUILTIN_NOOP_HANDLER_KEYS = (
    NOOP_HANDLER_KEY,
    "generic.static_modifiers",
    "generic.test_artifact_set",
    "generic.test_character",
    "generic.test_weapon",
)

BUILTIN_CONTENT_HANDLER_KEYS = (
    BARBARA_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
BUILTIN_HANDLER_KEYS = tuple(sorted((*BUILTIN_NOOP_HANDLER_KEYS, *BUILTIN_CONTENT_HANDLER_KEYS)))


def register_builtin_content(registry: HandlerRegistry) -> HandlerRegistry:
    handler = NoOpRuntimeHandler()
    for handler_key in BUILTIN_NOOP_HANDLER_KEYS:
        registry.register_handler(handler_key, handler)
    register_barbara(registry)
    register_runtime_probe(registry)
    return registry


def create_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    register_builtin_content(registry)
    return registry
