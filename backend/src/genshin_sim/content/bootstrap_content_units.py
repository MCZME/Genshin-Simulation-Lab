"""内置内容单元注册入口（新模型）。"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CONSTELLATION_C1_HANDLER_KEY,
    BARBARA_CONSTELLATION_C2_HANDLER_KEY,
    BARBARA_CONSTELLATION_C3_HANDLER_KEY,
    BARBARA_CONSTELLATION_C4_HANDLER_KEY,
    BARBARA_CONSTELLATION_C5_HANDLER_KEY,
    BARBARA_CONSTELLATION_C6_HANDLER_KEY,
    BARBARA_ENCORE_EFFECT_HANDLER_KEY,
    BARBARA_PASSIVE_EXPLORATION_COOKING_HANDLER_KEY,
    BARBARA_PASSIVE_SEASON_HANDLER_KEY,
    create_barbara_constellation_c1,
    create_barbara_constellation_c2,
    create_barbara_constellation_c3,
    create_barbara_constellation_c4,
    create_barbara_constellation_c5,
    create_barbara_content_unit,
    create_barbara_encore_effect,
)
from genshin_sim.content.characters.testing.runtime_probe import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    create_runtime_probe_content_unit,
)
from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.content.weapons.bow.hunter_bow import (
    HUNTER_BOW_HANDLER_KEY,
    create_hunter_bow_content_unit,
)
from genshin_sim.content.weapons.catalyst.apprentice_notes import (
    APPRENTICE_NOTES_HANDLER_KEY,
    create_apprentice_notes_content_unit,
)
from genshin_sim.content.weapons.claymore.waster_greatsword import (
    WASTER_GREATSWORD_HANDLER_KEY,
    create_waster_greatsword_content_unit,
)
from genshin_sim.content.weapons.polearm.beginner_protector import (
    BEGINNER_PROTECTOR_HANDLER_KEY,
    create_beginner_protector_content_unit,
)
from genshin_sim.content.weapons.sword.dull_blade import (
    DULL_BLADE_HANDLER_KEY,
    create_dull_blade_content_unit,
)

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
    registry.register_effect_factory(
        BARBARA_ENCORE_EFFECT_HANDLER_KEY,
        create_barbara_encore_effect,
    )
    registry.register_weapon_factory(
        DULL_BLADE_HANDLER_KEY,
        create_dull_blade_content_unit,
    )
    registry.register_weapon_factory(
        WASTER_GREATSWORD_HANDLER_KEY,
        create_waster_greatsword_content_unit,
    )
    registry.register_weapon_factory(
        BEGINNER_PROTECTOR_HANDLER_KEY,
        create_beginner_protector_content_unit,
    )
    registry.register_weapon_factory(
        APPRENTICE_NOTES_HANDLER_KEY,
        create_apprentice_notes_content_unit,
    )
    registry.register_weapon_factory(
        HUNTER_BOW_HANDLER_KEY,
        create_hunter_bow_content_unit,
    )
    registry.register_effect_factory(
        BARBARA_CONSTELLATION_C1_HANDLER_KEY,
        create_barbara_constellation_c1,
    )
    registry.register_effect_factory(
        BARBARA_CONSTELLATION_C2_HANDLER_KEY,
        create_barbara_constellation_c2,
    )
    registry.register_effect_factory(
        BARBARA_CONSTELLATION_C3_HANDLER_KEY,
        create_barbara_constellation_c3,
    )
    registry.register_effect_factory(
        BARBARA_CONSTELLATION_C4_HANDLER_KEY,
        create_barbara_constellation_c4,
    )
    registry.register_effect_factory(
        BARBARA_CONSTELLATION_C5_HANDLER_KEY,
        create_barbara_constellation_c5,
    )
    registry.register_empty_effect_handler(BARBARA_CONSTELLATION_C6_HANDLER_KEY)
    registry.register_empty_effect_handler(BARBARA_PASSIVE_SEASON_HANDLER_KEY)
    registry.register_empty_effect_handler(BARBARA_PASSIVE_EXPLORATION_COOKING_HANDLER_KEY)
    for handler_key in BUILTIN_NOOP_CONTENT_HANDLER_KEYS:
        registry.register_noop_handler(handler_key)
    return registry
