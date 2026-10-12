"""内置内容单元注册入口（新模型）。"""

from __future__ import annotations

from genshin_sim.content.artifacts.berserker import (
    BERSERKER_2P_HANDLER_KEY,
    BERSERKER_4P_HANDLER_KEY,
    BERSERKER_HANDLER_KEY,
    create_berserker_four_piece_unit,
    create_berserker_identity_unit,
    create_berserker_two_piece_unit,
)
from genshin_sim.content.artifacts.blizzard_strayer import (
    BLIZZARD_STRAYER_2P_HANDLER_KEY,
    BLIZZARD_STRAYER_4P_HANDLER_KEY,
    BLIZZARD_STRAYER_HANDLER_KEY,
    create_blizzard_strayer_four_piece_unit,
    create_blizzard_strayer_identity_unit,
    create_blizzard_strayer_two_piece_unit,
)
from genshin_sim.content.artifacts.disenchantment_in_deep_shadow import (
    DISENCHANTMENT_IN_DEEP_SHADOW_2P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_4P_HANDLER_KEY,
    DISENCHANTMENT_IN_DEEP_SHADOW_HANDLER_KEY,
    create_disenchantment_in_deep_shadow_four_piece_unit,
    create_disenchantment_in_deep_shadow_identity_unit,
    create_disenchantment_in_deep_shadow_two_piece_unit,
)
from genshin_sim.content.artifacts.heart_of_depth import (
    HEART_OF_DEPTH_2P_HANDLER_KEY,
    HEART_OF_DEPTH_4P_HANDLER_KEY,
    HEART_OF_DEPTH_HANDLER_KEY,
    create_heart_of_depth_four_piece_unit,
    create_heart_of_depth_identity_unit,
    create_heart_of_depth_two_piece_unit,
)
from genshin_sim.content.artifacts.heart_of_the_furnace import (
    HEART_OF_THE_FURNACE_2P_HANDLER_KEY,
    HEART_OF_THE_FURNACE_4P_HANDLER_KEY,
    HEART_OF_THE_FURNACE_HANDLER_KEY,
    create_heart_of_the_furnace_four_piece_unit,
    create_heart_of_the_furnace_identity_unit,
    create_heart_of_the_furnace_two_piece_unit,
)
from genshin_sim.content.artifacts.instructor import (
    INSTRUCTOR_2P_HANDLER_KEY,
    INSTRUCTOR_4P_HANDLER_KEY,
    INSTRUCTOR_HANDLER_KEY,
    create_instructor_four_piece_unit,
    create_instructor_identity_unit,
    create_instructor_two_piece_unit,
)
from genshin_sim.content.artifacts.lavawalker import (
    LAVAWALKER_2P_HANDLER_KEY,
    LAVAWALKER_4P_HANDLER_KEY,
    LAVAWALKER_HANDLER_KEY,
    create_lavawalker_four_piece_unit,
    create_lavawalker_identity_unit,
    create_lavawalker_two_piece_unit,
)
from genshin_sim.content.artifacts.maiden_beloved import (
    MAIDEN_BELOVED_2P_HANDLER_KEY,
    MAIDEN_BELOVED_4P_HANDLER_KEY,
    MAIDEN_BELOVED_HANDLER_KEY,
    create_maiden_beloved_four_piece_unit,
    create_maiden_beloved_identity_unit,
    create_maiden_beloved_two_piece_unit,
)
from genshin_sim.content.artifacts.noblesse_oblige import (
    NOBLESSE_OBLIGE_2P_HANDLER_KEY,
    NOBLESSE_OBLIGE_4P_HANDLER_KEY,
    NOBLESSE_OBLIGE_HANDLER_KEY,
    create_noblesse_oblige_four_piece_unit,
    create_noblesse_oblige_identity_unit,
    create_noblesse_oblige_two_piece_unit,
)
from genshin_sim.content.artifacts.resolution_of_sojourner import (
    RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
    RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
    RESOLUTION_OF_SOJOURNER_HANDLER_KEY,
    create_resolution_of_sojourner_four_piece_unit,
    create_resolution_of_sojourner_identity_unit,
    create_resolution_of_sojourner_two_piece_unit,
)
from genshin_sim.content.artifacts.tenacity_of_the_millelith import (
    TENACITY_OF_THE_MILLELITH_2P_HANDLER_KEY,
    TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY,
    TENACITY_OF_THE_MILLELITH_HANDLER_KEY,
    create_tenacity_of_the_millelith_four_piece_unit,
    create_tenacity_of_the_millelith_identity_unit,
    create_tenacity_of_the_millelith_two_piece_unit,
)
from genshin_sim.content.artifacts.thundersoother import (
    THUNDERSOOTHER_2P_HANDLER_KEY,
    THUNDERSOOTHER_4P_HANDLER_KEY,
    THUNDERSOOTHER_HANDLER_KEY,
    create_thundersoother_four_piece_unit,
    create_thundersoother_identity_unit,
    create_thundersoother_two_piece_unit,
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
from genshin_sim.content.characters.mondstadt.sucrose import (
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    create_sucrose_constellation_c1,
    create_sucrose_constellation_c2,
    create_sucrose_constellation_c3,
    create_sucrose_constellation_c4,
    create_sucrose_constellation_c5,
    create_sucrose_constellation_c6,
    create_sucrose_content_unit,
    create_sucrose_passive_a1,
    create_sucrose_passive_a4,
    create_sucrose_passive_witches_eve,
)
from genshin_sim.content.characters.snezhnaya.alyosha import (
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C1_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C2_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C3_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C4_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C5_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C6_HANDLER_KEY,
    ALYOSHA_PASSIVE_P4_HANDLER_KEY,
    ALYOSHA_PASSIVE_P5_HANDLER_KEY,
    ALYOSHA_PASSIVE_P6_HANDLER_KEY,
    ALYOSHA_PASSIVE_P8_HANDLER_KEY,
    create_alyosha_constellation_c1,
    create_alyosha_constellation_c2,
    create_alyosha_constellation_c3,
    create_alyosha_constellation_c4,
    create_alyosha_constellation_c5,
    create_alyosha_constellation_c6,
    create_alyosha_content_unit,
    create_alyosha_passive_p4,
    create_alyosha_passive_p5,
    create_alyosha_passive_p6,
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
    create_odette_constellation_c1,
    create_odette_constellation_c2,
    create_odette_constellation_c3,
    create_odette_constellation_c4,
    create_odette_constellation_c5,
    create_odette_constellation_c6,
    create_odette_content_unit,
    create_odette_passive_p4,
    create_odette_passive_p5,
    create_odette_passive_p6,
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
from genshin_sim.content.weapons.bow.messenger import (
    MESSENGER_HANDLER_KEY,
    MESSENGER_PASSIVE_EFFECT_HANDLER_KEY,
    create_messenger_identity_unit,
    create_messenger_passive_unit,
)
from genshin_sim.content.weapons.bow.raven_bow import (
    RAVEN_BOW_HANDLER_KEY,
    RAVEN_BOW_PASSIVE_EFFECT_HANDLER_KEY,
    create_raven_bow_identity_unit,
    create_raven_bow_passive_unit,
)
from genshin_sim.content.weapons.bow.recurve_bow import (
    RECURVE_BOW_HANDLER_KEY,
    RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY,
    create_recurve_bow_identity_unit,
    create_recurve_bow_passive_unit,
)
from genshin_sim.content.weapons.bow.sharpshooters_oath import (
    SHARPSHOOTERS_OATH_HANDLER_KEY,
    SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY,
    create_sharpshooters_oath_identity_unit,
    create_sharpshooters_oath_passive_unit,
)
from genshin_sim.content.weapons.catalyst.apprentice_notes import (
    APPRENTICE_NOTES_HANDLER_KEY,
    create_apprentice_notes_content_unit,
)
from genshin_sim.content.weapons.catalyst.emerald_orb import (
    EMERALD_ORB_HANDLER_KEY,
    EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
    create_emerald_orb_identity_unit,
    create_emerald_orb_passive_unit,
)
from genshin_sim.content.weapons.catalyst.favonius_codex import (
    FAVONIUS_CODEX_HANDLER_KEY,
    FAVONIUS_CODEX_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_codex_identity_unit,
    create_favonius_codex_passive_unit,
)
from genshin_sim.content.weapons.catalyst.magic_guide import (
    MAGIC_GUIDE_HANDLER_KEY,
    MAGIC_GUIDE_PASSIVE_EFFECT_HANDLER_KEY,
    create_magic_guide_identity_unit,
    create_magic_guide_passive_unit,
)
from genshin_sim.content.weapons.catalyst.otherworldly_story import (
    OTHERWORLDLY_STORY_HANDLER_KEY,
    OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
    create_otherworldly_story_identity_unit,
    create_otherworldly_story_passive_unit,
)
from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers import (
    THRILLING_TALES_HANDLER_KEY,
    THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
    create_thrilling_tales_identity_unit,
    create_thrilling_tales_passive_unit,
)
from genshin_sim.content.weapons.catalyst.twin_nephrite import (
    TWIN_NEPHRITE_HANDLER_KEY,
    TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY,
    create_twin_nephrite_identity_unit,
    create_twin_nephrite_passive_unit,
)
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence import (
    A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY,
    A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
    create_a_teaspoon_of_transcendence_identity_unit,
    create_a_teaspoon_of_transcendence_passive_unit,
)
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword import (
    BLOODTAINTED_GREATSWORD_HANDLER_KEY,
    BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_bloodtainted_greatsword_identity_unit,
    create_bloodtainted_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.debate_club import (
    DEBATE_CLUB_HANDLER_KEY,
    DEBATE_CLUB_PASSIVE_EFFECT_HANDLER_KEY,
    create_debate_club_identity_unit,
    create_debate_club_passive_unit,
)
from genshin_sim.content.weapons.claymore.favonius_greatsword import (
    FAVONIUS_GREATSWORD_HANDLER_KEY,
    FAVONIUS_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_greatsword_identity_unit,
    create_favonius_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.ferrous_shadow import (
    FERROUS_SHADOW_HANDLER_KEY,
    FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
    create_ferrous_shadow_identity_unit,
    create_ferrous_shadow_passive_unit,
)
from genshin_sim.content.weapons.claymore.mailed_flower import (
    MAILED_FLOWER_HANDLER_KEY,
    MAILED_FLOWER_PASSIVE_EFFECT_HANDLER_KEY,
    create_mailed_flower_identity_unit,
    create_mailed_flower_passive_unit,
)
from genshin_sim.content.weapons.claymore.skyrider_greatsword import (
    SKYRIDER_GREATSWORD_HANDLER_KEY,
    SKYRIDER_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_skyrider_greatsword_identity_unit,
    create_skyrider_greatsword_passive_unit,
)
from genshin_sim.content.weapons.claymore.tidal_shadow import (
    TIDAL_SHADOW_HANDLER_KEY,
    TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
    create_tidal_shadow_identity_unit,
    create_tidal_shadow_passive_unit,
)
from genshin_sim.content.weapons.claymore.waster_greatsword import (
    WASTER_GREATSWORD_HANDLER_KEY,
    create_waster_greatsword_content_unit,
)
from genshin_sim.content.weapons.claymore.white_iron_greatsword import (
    WHITE_IRON_GREATSWORD_HANDLER_KEY,
    WHITE_IRON_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_white_iron_greatsword_identity_unit,
    create_white_iron_greatsword_passive_unit,
)
from genshin_sim.content.weapons.polearm.beginner_protector import (
    BEGINNER_PROTECTOR_HANDLER_KEY,
    create_beginner_protector_content_unit,
)
from genshin_sim.content.weapons.polearm.black_tassel import (
    BLACK_TASSEL_HANDLER_KEY,
    BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
    create_black_tassel_identity_unit,
    create_black_tassel_passive_unit,
)
from genshin_sim.content.weapons.polearm.favonius_lance import (
    FAVONIUS_LANCE_HANDLER_KEY,
    FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
    create_favonius_lance_identity_unit,
    create_favonius_lance_passive_unit,
)
from genshin_sim.content.weapons.polearm.halberd import (
    HALBERD_HANDLER_KEY,
    HALBERD_PASSIVE_EFFECT_HANDLER_KEY,
    create_halberd_identity_unit,
    create_halberd_passive_unit,
)
from genshin_sim.content.weapons.polearm.white_tassel import (
    WHITE_TASSEL_HANDLER_KEY,
    WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
    create_white_tassel_identity_unit,
    create_white_tassel_passive_unit,
)
from genshin_sim.content.weapons.sword.cool_steel import (
    COOL_STEEL_HANDLER_KEY,
    COOL_STEEL_PASSIVE_EFFECT_HANDLER_KEY,
    create_cool_steel_identity_unit,
    create_cool_steel_passive_unit,
)
from genshin_sim.content.weapons.sword.dark_iron_sword import (
    DARK_IRON_SWORD_HANDLER_KEY,
    DARK_IRON_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_dark_iron_sword_identity_unit,
    create_dark_iron_sword_passive_unit,
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
from genshin_sim.content.weapons.sword.fillet_blade import (
    FILLET_BLADE_HANDLER_KEY,
    FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
    create_fillet_blade_identity_unit,
    create_fillet_blade_passive_unit,
)
from genshin_sim.content.weapons.sword.freedom_sworn import (
    FREEDOM_SWORN_HANDLER_KEY,
    FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
    create_freedom_sworn_identity_unit,
    create_freedom_sworn_passive_unit,
)
from genshin_sim.content.weapons.sword.harbinger_of_dawn import (
    HARBINGER_OF_DAWN_HANDLER_KEY,
    HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
    create_harbinger_of_dawn_identity_unit,
    create_harbinger_of_dawn_passive_unit,
)
from genshin_sim.content.weapons.sword.skyrider_sword import (
    SKYRIDER_SWORD_HANDLER_KEY,
    SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_skyrider_sword_identity_unit,
    create_skyrider_sword_passive_unit,
)
from genshin_sim.content.weapons.sword.travelers_handy_sword import (
    TRAVELERS_HANDY_SWORD_HANDLER_KEY,
    TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
    create_travelers_handy_sword_identity_unit,
    create_travelers_handy_sword_passive_unit,
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
        SUCROSE_CHARACTER_HANDLER_KEY,
        create_sucrose_content_unit,
    )
    registry.register_character_factory(
        SANDRONE_CHARACTER_HANDLER_KEY,
        create_sandrone_content_unit,
    )
    registry.register_character_factory(
        ODETTE_CHARACTER_HANDLER_KEY,
        create_odette_content_unit,
    )
    registry.register_character_factory(
        ALYOSHA_CHARACTER_HANDLER_KEY,
        create_alyosha_content_unit,
    )
    if developer_mode:
        from genshin_sim.content.test import register_test_content_units

        register_test_content_units(registry)
    registry.register_effect_factory(
        BARBARA_ENCORE_EFFECT_HANDLER_KEY,
        create_barbara_encore_effect,
    )
    for handler_key, factory in (
        (SUCROSE_PASSIVE_A1_HANDLER_KEY, create_sucrose_passive_a1),
        (SUCROSE_PASSIVE_A4_HANDLER_KEY, create_sucrose_passive_a4),
        (SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY, create_sucrose_passive_witches_eve),
        (SUCROSE_CONSTELLATION_C1_HANDLER_KEY, create_sucrose_constellation_c1),
        (SUCROSE_CONSTELLATION_C2_HANDLER_KEY, create_sucrose_constellation_c2),
        (SUCROSE_CONSTELLATION_C3_HANDLER_KEY, create_sucrose_constellation_c3),
        (SUCROSE_CONSTELLATION_C4_HANDLER_KEY, create_sucrose_constellation_c4),
        (SUCROSE_CONSTELLATION_C5_HANDLER_KEY, create_sucrose_constellation_c5),
        (SUCROSE_CONSTELLATION_C6_HANDLER_KEY, create_sucrose_constellation_c6),
    ):
        registry.register_effect_factory(handler_key, factory)
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
    registry.register_weapon_factory(
        FREEDOM_SWORN_HANDLER_KEY,
        create_freedom_sworn_identity_unit,
    )
    registry.register_weapon_factory(
        MAILED_FLOWER_HANDLER_KEY,
        create_mailed_flower_identity_unit,
    )
    registry.register_weapon_factory(
        TIDAL_SHADOW_HANDLER_KEY,
        create_tidal_shadow_identity_unit,
    )
    # 低星（1~3 星）武器被动：判定、资产参数解读与钩子在各内容包内自持
    # （与白湖冬羽的单包结构一致），不设 generic 共享层。
    for handler_key, factory in (
        (WHITE_TASSEL_HANDLER_KEY, create_white_tassel_identity_unit),
        (HARBINGER_OF_DAWN_HANDLER_KEY, create_harbinger_of_dawn_identity_unit),
        (FERROUS_SHADOW_HANDLER_KEY, create_ferrous_shadow_identity_unit),
        (SKYRIDER_GREATSWORD_HANDLER_KEY, create_skyrider_greatsword_identity_unit),
        (SKYRIDER_SWORD_HANDLER_KEY, create_skyrider_sword_identity_unit),
        (THRILLING_TALES_HANDLER_KEY, create_thrilling_tales_identity_unit),
        (EMERALD_ORB_HANDLER_KEY, create_emerald_orb_identity_unit),
        (DARK_IRON_SWORD_HANDLER_KEY, create_dark_iron_sword_identity_unit),
        (HALBERD_HANDLER_KEY, create_halberd_identity_unit),
        (FILLET_BLADE_HANDLER_KEY, create_fillet_blade_identity_unit),
        (DEBATE_CLUB_HANDLER_KEY, create_debate_club_identity_unit),
        (TRAVELERS_HANDY_SWORD_HANDLER_KEY, create_travelers_handy_sword_identity_unit),
        (OTHERWORLDLY_STORY_HANDLER_KEY, create_otherworldly_story_identity_unit),
        # 元素影响条件增伤（issue #43 缺口 1）：条件读取统一走
        # ``TargetElementAuraReadPort``，元素影响口径由 core.elements 冻结。
        (RAVEN_BOW_HANDLER_KEY, create_raven_bow_identity_unit),
        (MAGIC_GUIDE_HANDLER_KEY, create_magic_guide_identity_unit),
        (
            BLOODTAINTED_GREATSWORD_HANDLER_KEY,
            create_bloodtainted_greatsword_identity_unit,
        ),
        (COOL_STEEL_HANDLER_KEY, create_cool_steel_identity_unit),
        # 缺口 2/3（弱点、敌人击败）当前不建模，见 D-095：这些武器照常接入，
        # 索引行与效果行都绑定，效果单元为显式 no-op，范围边界写在各自 data.py。
        (SHARPSHOOTERS_OATH_HANDLER_KEY, create_sharpshooters_oath_identity_unit),
        (MESSENGER_HANDLER_KEY, create_messenger_identity_unit),
        (RECURVE_BOW_HANDLER_KEY, create_recurve_bow_identity_unit),
        (WHITE_IRON_GREATSWORD_HANDLER_KEY, create_white_iron_greatsword_identity_unit),
        (TWIN_NEPHRITE_HANDLER_KEY, create_twin_nephrite_identity_unit),
        (BLACK_TASSEL_HANDLER_KEY, create_black_tassel_identity_unit),
    ):
        registry.register_weapon_factory(handler_key, factory)
    for handler_key, factory in (
        (WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY, create_white_tassel_passive_unit),
        (
            HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
            create_harbinger_of_dawn_passive_unit,
        ),
        (FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY, create_ferrous_shadow_passive_unit),
        (
            SKYRIDER_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
            create_skyrider_greatsword_passive_unit,
        ),
        (SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY, create_skyrider_sword_passive_unit),
        (THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY, create_thrilling_tales_passive_unit),
        (EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY, create_emerald_orb_passive_unit),
        (DARK_IRON_SWORD_PASSIVE_EFFECT_HANDLER_KEY, create_dark_iron_sword_passive_unit),
        (HALBERD_PASSIVE_EFFECT_HANDLER_KEY, create_halberd_passive_unit),
        (FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY, create_fillet_blade_passive_unit),
        (
            DEBATE_CLUB_PASSIVE_EFFECT_HANDLER_KEY,
            create_debate_club_passive_unit,
        ),
        (
            TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
            create_travelers_handy_sword_passive_unit,
        ),
        (
            OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
            create_otherworldly_story_passive_unit,
        ),
        (RAVEN_BOW_PASSIVE_EFFECT_HANDLER_KEY, create_raven_bow_passive_unit),
        (MAGIC_GUIDE_PASSIVE_EFFECT_HANDLER_KEY, create_magic_guide_passive_unit),
        (
            BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
            create_bloodtainted_greatsword_passive_unit,
        ),
        (COOL_STEEL_PASSIVE_EFFECT_HANDLER_KEY, create_cool_steel_passive_unit),
        (
            SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY,
            create_sharpshooters_oath_passive_unit,
        ),
        (MESSENGER_PASSIVE_EFFECT_HANDLER_KEY, create_messenger_passive_unit),
        (RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY, create_recurve_bow_passive_unit),
        (
            WHITE_IRON_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
            create_white_iron_greatsword_passive_unit,
        ),
        (TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY, create_twin_nephrite_passive_unit),
        (BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY, create_black_tassel_passive_unit),
    ):
        registry.register_effect_factory(handler_key, factory)
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
        (
            FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
            create_freedom_sworn_passive_unit,
        ),
        (
            MAILED_FLOWER_PASSIVE_EFFECT_HANDLER_KEY,
            create_mailed_flower_passive_unit,
        ),
        (
            TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
            create_tidal_shadow_passive_unit,
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
        (BERSERKER_HANDLER_KEY, create_berserker_identity_unit),
        (BERSERKER_2P_HANDLER_KEY, create_berserker_two_piece_unit),
        (BERSERKER_4P_HANDLER_KEY, create_berserker_four_piece_unit),
        (BLIZZARD_STRAYER_HANDLER_KEY, create_blizzard_strayer_identity_unit),
        (BLIZZARD_STRAYER_2P_HANDLER_KEY, create_blizzard_strayer_two_piece_unit),
        (BLIZZARD_STRAYER_4P_HANDLER_KEY, create_blizzard_strayer_four_piece_unit),
        (HEART_OF_DEPTH_HANDLER_KEY, create_heart_of_depth_identity_unit),
        (HEART_OF_DEPTH_2P_HANDLER_KEY, create_heart_of_depth_two_piece_unit),
        (HEART_OF_DEPTH_4P_HANDLER_KEY, create_heart_of_depth_four_piece_unit),
        (INSTRUCTOR_HANDLER_KEY, create_instructor_identity_unit),
        (INSTRUCTOR_2P_HANDLER_KEY, create_instructor_two_piece_unit),
        (INSTRUCTOR_4P_HANDLER_KEY, create_instructor_four_piece_unit),
        (LAVAWALKER_HANDLER_KEY, create_lavawalker_identity_unit),
        (LAVAWALKER_2P_HANDLER_KEY, create_lavawalker_two_piece_unit),
        (LAVAWALKER_4P_HANDLER_KEY, create_lavawalker_four_piece_unit),
        (NOBLESSE_OBLIGE_HANDLER_KEY, create_noblesse_oblige_identity_unit),
        (NOBLESSE_OBLIGE_2P_HANDLER_KEY, create_noblesse_oblige_two_piece_unit),
        (NOBLESSE_OBLIGE_4P_HANDLER_KEY, create_noblesse_oblige_four_piece_unit),
        (
            RESOLUTION_OF_SOJOURNER_HANDLER_KEY,
            create_resolution_of_sojourner_identity_unit,
        ),
        (
            RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
            create_resolution_of_sojourner_two_piece_unit,
        ),
        (
            RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
            create_resolution_of_sojourner_four_piece_unit,
        ),
        (
            TENACITY_OF_THE_MILLELITH_HANDLER_KEY,
            create_tenacity_of_the_millelith_identity_unit,
        ),
        (
            TENACITY_OF_THE_MILLELITH_2P_HANDLER_KEY,
            create_tenacity_of_the_millelith_two_piece_unit,
        ),
        (
            TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY,
            create_tenacity_of_the_millelith_four_piece_unit,
        ),
        (THUNDERSOOTHER_HANDLER_KEY, create_thundersoother_identity_unit),
        (THUNDERSOOTHER_2P_HANDLER_KEY, create_thundersoother_two_piece_unit),
        (THUNDERSOOTHER_4P_HANDLER_KEY, create_thundersoother_four_piece_unit),
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
    registry.register_empty_effect_handler(SANDRONE_PASSIVE_P8_HANDLER_KEY)
    registry.register_effect_factory(
        ODETTE_PASSIVE_P4_HANDLER_KEY,
        create_odette_passive_p4,
    )
    registry.register_effect_factory(
        ODETTE_PASSIVE_P5_HANDLER_KEY,
        create_odette_passive_p5,
    )
    registry.register_effect_factory(
        ODETTE_PASSIVE_P6_HANDLER_KEY,
        create_odette_passive_p6,
    )
    for handler_key, factory in (
        (ODETTE_CONSTELLATION_C1_HANDLER_KEY, create_odette_constellation_c1),
        (ODETTE_CONSTELLATION_C2_HANDLER_KEY, create_odette_constellation_c2),
        (ODETTE_CONSTELLATION_C3_HANDLER_KEY, create_odette_constellation_c3),
        (ODETTE_CONSTELLATION_C4_HANDLER_KEY, create_odette_constellation_c4),
        (ODETTE_CONSTELLATION_C5_HANDLER_KEY, create_odette_constellation_c5),
        (ODETTE_CONSTELLATION_C6_HANDLER_KEY, create_odette_constellation_c6),
    ):
        registry.register_effect_factory(handler_key, factory)
    registry.register_empty_effect_handler(ODETTE_PASSIVE_P8_HANDLER_KEY)
    for handler_key, factory in (
        (ALYOSHA_PASSIVE_P4_HANDLER_KEY, create_alyosha_passive_p4),
        (ALYOSHA_PASSIVE_P5_HANDLER_KEY, create_alyosha_passive_p5),
        (ALYOSHA_PASSIVE_P6_HANDLER_KEY, create_alyosha_passive_p6),
        (ALYOSHA_CONSTELLATION_C1_HANDLER_KEY, create_alyosha_constellation_c1),
        (ALYOSHA_CONSTELLATION_C2_HANDLER_KEY, create_alyosha_constellation_c2),
        (ALYOSHA_CONSTELLATION_C3_HANDLER_KEY, create_alyosha_constellation_c3),
        (ALYOSHA_CONSTELLATION_C4_HANDLER_KEY, create_alyosha_constellation_c4),
        (ALYOSHA_CONSTELLATION_C5_HANDLER_KEY, create_alyosha_constellation_c5),
        (ALYOSHA_CONSTELLATION_C6_HANDLER_KEY, create_alyosha_constellation_c6),
    ):
        registry.register_effect_factory(handler_key, factory)
    for handler_key in (ALYOSHA_PASSIVE_P8_HANDLER_KEY,):
        registry.register_empty_effect_handler(handler_key)
    for handler_key in BUILTIN_NOOP_CONTENT_HANDLER_KEYS:
        registry.register_noop_handler(handler_key)
    return registry
