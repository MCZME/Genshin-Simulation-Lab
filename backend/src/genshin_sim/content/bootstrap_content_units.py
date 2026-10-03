"""内置内容单元注册入口（新模型）。"""

from __future__ import annotations

from genshin_sim.content.artifacts.disenchantment_in_deep_shadow import (
    DISENCHANTMENT_IN_DEEP_SHADOW_2P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_4P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
    create_disenchantment_in_deep_shadow_four_piece_unit,
    create_disenchantment_in_deep_shadow_identity_unit,
    create_disenchantment_in_deep_shadow_two_piece_unit,
)
from genshin_sim.content.artifacts.heart_of_the_furnace import (
    HEART_OF_THE_FURNACE_2P_HANDLER_KEY,
    HEART_OF_THE_FURNACE_4P_HANDLER_KEY,
    HEART_OF_THE_FURNACE_HANDLER_KEY,
    create_heart_of_the_furnace_four_piece_unit,
    create_heart_of_the_furnace_identity_unit,
    create_heart_of_the_furnace_two_piece_unit,
)
from genshin_sim.content.artifacts.maiden_beloved import (
    MAIDEN_BELOVED_2P_HANDLER_KEY,
    MAIDEN_BELOVED_4P_HANDLER_KEY,
    MAIDEN_BELOVED_HANDLER_KEY,
    create_maiden_beloved_four_piece_unit,
    create_maiden_beloved_identity_unit,
    create_maiden_beloved_two_piece_unit,
)
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
from genshin_sim.content.characters.snezhnaya.odette import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CONSTELLATION_C1_HANDLER_KEY,
    ODETTE_CONSTELLATION_C2_HANDLER_KEY,
    ODETTE_CONSTELLATION_C3_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
    ODETTE_PASSIVE_P8_HANDLER_KEY,
    create_odette_constellation_c6,
    create_odette_content_unit,
    create_odette_passive_p4,
)
from genshin_sim.content.characters.snezhnaya.sandrone import (
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
    SANDRONE_PASSIVE_P4_HANDLER_KEY,
    SANDRONE_PASSIVE_P5_HANDLER_KEY,
    SANDRONE_PASSIVE_P6_HANDLER_KEY,
    SANDRONE_PASSIVE_P8_HANDLER_KEY,
    create_sandrone_constellation_c1,
    create_sandrone_constellation_c2,
    create_sandrone_constellation_c3,
    create_sandrone_constellation_c4,
    create_sandrone_constellation_c5,
    create_sandrone_constellation_c6,
    create_sandrone_content_unit,
    create_sandrone_passive_p4,
    create_sandrone_passive_p5,
    create_sandrone_passive_p6,
)
from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.content.weapons.bow.favonius_warbow import (
    FAVONIUS_WARBOW_HANDLER_KEY,
    FAVONIUS_WARBOW_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_warbow_identity_unit,
    create_favonius_warbow_passive_unit,
)
from genshin_sim.content.weapons.bow.hunter_bow import (
    HUNTER_BOW_HANDLER_KEY,
    create_hunter_bow_content_unit,
)
from genshin_sim.content.weapons.catalyst.apprentice_notes import (
    APPRENTICE_NOTES_HANDLER_KEY,
    create_apprentice_notes_content_unit,
)
from genshin_sim.content.weapons.catalyst.favonius_codex import (
    FAVONIUS_CODEX_HANDLER_KEY,
    FAVONIUS_CODEX_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_codex_identity_unit,
    create_favonius_codex_passive_unit,
)
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence import (
    A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY,
    A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
    create_a_teaspoon_of_transcendence_identity_unit,
    create_a_teaspoon_of_transcendence_passive_unit,
)
from genshin_sim.content.weapons.claymore.favonius_greatsword import (
    FAVONIUS_GREATSWORD_HANDLER_KEY,
    FAVONIUS_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_greatsword_identity_unit,
    create_favonius_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.waster_greatsword import (
    WASTER_GREATSWORD_HANDLER_KEY,
    create_waster_greatsword_content_unit,
)
from genshin_sim.content.weapons.polearm.beginner_protector import (
    BEGINNER_PROTECTOR_HANDLER_KEY,
    create_beginner_protector_content_unit,
)
from genshin_sim.content.weapons.polearm.favonius_lance import (
    FAVONIUS_LANCE_HANDLER_KEY,
    FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_lance_identity_unit,
    create_favonius_lance_passive_unit,
)
from genshin_sim.content.weapons.sword.dull_blade import (
    DULL_BLADE_HANDLER_KEY,
    create_dull_blade_content_unit,
)
from genshin_sim.content.weapons.sword.favonius_sword import (
    FAVONIUS_SWORD_HANDLER_KEY,
    FAVONIUS_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_sword_identity_unit,
    create_favonius_sword_passive_unit,
)
from genshin_sim.content.weapons.sword.whitelake_frostfeather import (
    WHITELAKE_FROSTFEATHER_HANDLER_KEY,
    WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
    create_whitelake_frostfeather_identity_unit,
    create_whitelake_frostfeather_passive_unit,
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


def create_default_content_unit_registry(
    *,
    developer_mode: bool = False,
) -> ContentUnitRegistry:
    """创建包含内置角色的默认内容单元注册表。

    内置角色直接注册新模型内容单元工厂；武器/圣遗物与效果 payload 仍走
    legacy 注册路径（M5 清理）。开发者模式额外注册 ``content/test`` 包的
    测试内容；正常模式不导入测试包。
    """

    registry = ContentUnitRegistry()
    registry.register_character_factory(
        BARBARA_CHARACTER_HANDLER_KEY,
        create_barbara_content_unit,
    )
    registry.register_character_factory(
        SANDRONE_CHARACTER_HANDLER_KEY,
        create_sandrone_content_unit,
    )
    registry.register_character_factory(
        ODETTE_CHARACTER_HANDLER_KEY,
        create_odette_content_unit,
    )
    if developer_mode:
        from genshin_sim.content.test import register_test_content_units

        register_test_content_units(registry)
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
    registry.register_weapon_factory(
        WHITELAKE_FROSTFEATHER_HANDLER_KEY,
        create_whitelake_frostfeather_identity_unit,
    )
    registry.register_weapon_factory(
        A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY,
        create_a_teaspoon_of_transcendence_identity_unit,
    )
    # 西风系列五把武器各自一个内容包与一个 handler 键；判定、资产参数解读与钩子
    # 实现是共用部件（``content/generic/favonius_windfall.py``），各包只声明自己的键。
    for handler_key, factory in (
        (FAVONIUS_SWORD_HANDLER_KEY, create_favonius_sword_identity_unit),
        (FAVONIUS_GREATSWORD_HANDLER_KEY, create_favonius_greatsword_identity_unit),
        (FAVONIUS_LANCE_HANDLER_KEY, create_favonius_lance_identity_unit),
        (FAVONIUS_CODEX_HANDLER_KEY, create_favonius_codex_identity_unit),
        (FAVONIUS_WARBOW_HANDLER_KEY, create_favonius_warbow_identity_unit),
    ):
        registry.register_weapon_factory(handler_key, factory)
    # 被动行为落在效果行绑定的单元上；精炼等级由武器索引行绑定的单元提供，
    # 效果行不重复声明（见内容系统设计第 4.4 节）。
    for handler_key, factory in (
        (FAVONIUS_SWORD_PASSIVE_EFFECT_HANDLER_KEY, create_favonius_sword_passive_unit),
        (
            FAVONIUS_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
            create_favonius_greatsword_passive_unit,
        ),
        (FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY, create_favonius_lance_passive_unit),
        (FAVONIUS_CODEX_PASSIVE_EFFECT_HANDLER_KEY, create_favonius_codex_passive_unit),
        (FAVONIUS_WARBOW_PASSIVE_EFFECT_HANDLER_KEY, create_favonius_warbow_passive_unit),
        (
            WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
            create_whitelake_frostfeather_passive_unit,
        ),
        (
            A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
            create_a_teaspoon_of_transcendence_passive_unit,
        ),
    ):
        registry.register_effect_factory(handler_key, factory)
    for handler_key, factory in (
        (MAIDEN_BELOVED_HANDLER_KEY, create_maiden_beloved_identity_unit),
        (MAIDEN_BELOVED_2P_HANDLER_KEY, create_maiden_beloved_two_piece_unit),
        (MAIDEN_BELOVED_4P_HANDLER_KEY, create_maiden_beloved_four_piece_unit),
        (
            DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
            create_disenchantment_in_deep_shadow_identity_unit,
        ),
        (
            DISENCHANTMENT_IN_DEEP_SHADOW_2P_HANDLER_KEY,
            create_disenchantment_in_deep_shadow_two_piece_unit,
        ),
        (
            DISENCHANTMENT_IN_DEEP_SHADOW_4P_HANDLER_KEY,
            create_disenchantment_in_deep_shadow_four_piece_unit,
        ),
        (
            HEART_OF_THE_FURNACE_HANDLER_KEY,
            create_heart_of_the_furnace_identity_unit,
        ),
        (HEART_OF_THE_FURNACE_2P_HANDLER_KEY, create_heart_of_the_furnace_two_piece_unit),
        (HEART_OF_THE_FURNACE_4P_HANDLER_KEY, create_heart_of_the_furnace_four_piece_unit),
    ):
        registry.register_artifact_factory(handler_key, factory)
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
    for handler_key, factory in (
        (SANDRONE_PASSIVE_P4_HANDLER_KEY, create_sandrone_passive_p4),
        (SANDRONE_PASSIVE_P5_HANDLER_KEY, create_sandrone_passive_p5),
        (SANDRONE_PASSIVE_P6_HANDLER_KEY, create_sandrone_passive_p6),
        (SANDRONE_CONSTELLATION_C1_HANDLER_KEY, create_sandrone_constellation_c1),
        (SANDRONE_CONSTELLATION_C2_HANDLER_KEY, create_sandrone_constellation_c2),
        (SANDRONE_CONSTELLATION_C3_HANDLER_KEY, create_sandrone_constellation_c3),
        (SANDRONE_CONSTELLATION_C4_HANDLER_KEY, create_sandrone_constellation_c4),
        (SANDRONE_CONSTELLATION_C5_HANDLER_KEY, create_sandrone_constellation_c5),
        (SANDRONE_CONSTELLATION_C6_HANDLER_KEY, create_sandrone_constellation_c6),
    ):
        registry.register_effect_factory(handler_key, factory)
    # P8 生活天赋：不参与仿真，注册空实现。
    registry.register_empty_effect_handler(SANDRONE_PASSIVE_P8_HANDLER_KEY)
    # 奥黛塔效果行：P4 华彩与 C6 擢升已随切片 4 落地（注册真工厂）；C2 的
    # 「每层华彩再 +7% 攻击力」编译为华彩 Buff 自身的攻击力词条（P4 工厂按
    # 命座门控携带，见 effects.py），效果行本身注册空实现；其余行为按切片
    # 落地（P5/P6、C1/C3/C4/C5），先注册 UNIMPLEMENTED 占位；P8 生活天赋为
    # 空实现。
    registry.register_effect_factory(
        ODETTE_PASSIVE_P4_HANDLER_KEY,
        create_odette_passive_p4,
    )
    registry.register_effect_factory(
        ODETTE_CONSTELLATION_C6_HANDLER_KEY,
        create_odette_constellation_c6,
    )
    registry.register_empty_effect_handler(ODETTE_CONSTELLATION_C2_HANDLER_KEY)
    for handler_key in (
        ODETTE_PASSIVE_P5_HANDLER_KEY,
        ODETTE_PASSIVE_P6_HANDLER_KEY,
        ODETTE_CONSTELLATION_C1_HANDLER_KEY,
        ODETTE_CONSTELLATION_C3_HANDLER_KEY,
        ODETTE_CONSTELLATION_C4_HANDLER_KEY,
        ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    ):
        registry.register_unimplemented_effect_handler(handler_key)
    registry.register_empty_effect_handler(ODETTE_PASSIVE_P8_HANDLER_KEY)
    for handler_key in BUILTIN_NOOP_CONTENT_HANDLER_KEYS:
        registry.register_noop_handler(handler_key)
    return registry
