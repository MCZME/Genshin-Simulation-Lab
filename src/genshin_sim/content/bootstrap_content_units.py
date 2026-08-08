"""内置内容单元注册入口（新模型）。"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_CHARACTER_HANDLER_KEY,
    create_barbara_content_unit,
)
from genshin_sim.content.characters.testing.runtime_probe import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    create_runtime_probe_content_unit,
)
from genshin_sim.content.registries import ContentUnitRegistry

BUILTIN_NOOP_CONTENT_HANDLER_KEYS = (
    "artifact.unimplemented_set_bonus",
    "character.unimplemented_constellation",
    "character.unimplemented_passive",
    "character.unimplemented_special_talent",
    "generic.noop",
    "generic.static_modifiers",
    "generic.test_artifact_set",
    "generic.test_character",
    "generic.test_weapon",
    "weapon.unimplemented_passive",
)


def create_default_content_unit_registry() -> ContentUnitRegistry:
    """创建包含内置角色的默认内容单元注册表。

    内置角色直接注册新模型内容单元工厂；武器/圣遗物与效果 payload 仍走
    legacy 注册路径（M5 清理）。
    """

    registry = ContentUnitRegistry()
    registry.register_character_factory(
        BARBARA_CHARACTER_HANDLER_KEY,
        create_barbara_content_unit,
    )
    registry.register_character_factory(
        RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
        create_runtime_probe_content_unit,
    )
    for handler_key in BUILTIN_NOOP_CONTENT_HANDLER_KEYS:
        registry.register_noop_handler(handler_key)
    return registry
