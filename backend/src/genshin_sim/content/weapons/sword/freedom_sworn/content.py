"""苍古自由之誓内容单元编译入口。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.sword.freedom_sworn.data import (
    DAMAGE_BONUS_COMPONENT_INDEX,
    FRAMES_PER_SECOND,
    FREEDOM_SWORN_CONTENT_VERSION,
    FREEDOM_SWORN_HANDLER_KEY,
    FREEDOM_SWORN_KEY_PREFIX,
    FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
    FREEDOM_SWORN_SONG_ATK_TERM_KEY,
    REQUIRED_COMPONENT_COUNT,
    SIGIL_LOCKOUT_SECONDS,
    SIGIL_TRIGGER_INTERVAL_SECONDS,
    SONG_ATK_COMPONENT_INDEX,
    SONG_ATTACK_TAG_DAMAGE_COMPONENT_INDEX,
    SONG_DURATION_SECONDS,
)
from genshin_sim.content.weapons.sword.freedom_sworn.hooks import FreedomSwornSigilHook
from genshin_sim.content.weapons.sword.freedom_sworn.modifiers import (
    FreedomSwornDamageBonusProvider,
    FreedomSwornSongAttackTagProvider,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)

SONG_DURATION_FRAMES = round(SONG_DURATION_SECONDS * FRAMES_PER_SECOND)
SIGIL_TRIGGER_INTERVAL_FRAMES = round(SIGIL_TRIGGER_INTERVAL_SECONDS * FRAMES_PER_SECOND)
SIGIL_LOCKOUT_FRAMES = round(SIGIL_LOCKOUT_SECONDS * FRAMES_PER_SECOND)


def freedom_sworn_song_definition_key(slot: int) -> str:
    """「千年的大乐章·抗争之歌」按穿戴者槽位区分的 Buff 定义键。"""

    return f"{FREEDOM_SWORN_KEY_PREFIX}.song.slot:{slot}"


def create_freedom_sworn_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """苍古自由之誓索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FREEDOM_SWORN_HANDLER_KEY,
        version=FREEDOM_SWORN_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "freedom_sworn_identity"},
    )


def create_freedom_sworn_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """苍古自由之誓被动「抗争的践行之歌」。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("苍古自由之誓被动缺少有效的队伍槽位")
    slot = request.slot
    damage_bonus, song_tag_bonus, song_atk_percent = _passive_values(request)
    owner_ref = f"character:slot_{slot}"
    song_definition_key = freedom_sworn_song_definition_key(slot)
    source_key = f"{FREEDOM_SWORN_KEY_PREFIX}:slot:{slot}"

    sigil_hook = FreedomSwornSigilHook(
        handler_key=FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
        owner_ref=owner_ref,
        slot=slot,
        song_atk_percent=song_atk_percent,
        song_duration_frames=SONG_DURATION_FRAMES,
        sigil_interval_frames=SIGIL_TRIGGER_INTERVAL_FRAMES,
        sigil_lockout_frames=SIGIL_LOCKOUT_FRAMES,
        definition_key=song_definition_key,
        source_key=source_key,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
        version=FREEDOM_SWORN_CONTENT_VERSION,
        slot=slot,
        event_hooks=(sigil_hook,),
        buff_definitions=(_song_buff_definition(slot, song_definition_key),),
        damage_modifier_providers=(
            FreedomSwornDamageBonusProvider(
                owner_ref=owner_ref,
                slot=slot,
                damage_bonus=damage_bonus,
                source_key=source_key,
            ),
            FreedomSwornSongAttackTagProvider(
                slot=slot,
                definition_key=song_definition_key,
                bonus=song_tag_bonus,
                source_key=source_key,
            ),
        ),
        metadata={"purpose": "freedom_sworn_passive"},
    )


def _song_buff_definition(slot: int, definition_key: str) -> BuffDefinition:
    """「千年的大乐章·抗争之歌」：队伍作用域攻击力 Buff。

    普/重/落伤害提高段的窗口也由这条 Buff 的存在性承载，因此不再另设
    仅标记的窗口 Buff。
    """

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{FREEDOM_SWORN_KEY_PREFIX}.song",
        handler_key=FREEDOM_SWORN_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=freedom_sworn_song_definition_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.TEAM}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="千年的大乐章·抗争之歌",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=FREEDOM_SWORN_SONG_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=BuffStackScaling.CONSTANT,
                audit_tags=("freedom_sworn_song",),
            ),
        ),
    )


def _passive_values(request: EffectContentUnitRequest) -> tuple[float, float, float]:
    """按精炼取（伤害提高, 普/重/落伤害提高, 攻击力提升）。"""

    params = request.params
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError("苍古自由之誓被动缺少资产效果参数 components")

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("苍古自由之誓被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("苍古自由之誓精炼必须是整数")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"苍古自由之誓精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    offset = refinement - refinement_min
    damage_bonus = _component_value(components[DAMAGE_BONUS_COMPONENT_INDEX], offset, "伤害提高")
    song_tag_bonus = _component_value(
        components[SONG_ATTACK_TAG_DAMAGE_COMPONENT_INDEX],
        offset,
        "普/重/落伤害提高",
    )
    song_atk_percent = _component_value(
        components[SONG_ATK_COMPONENT_INDEX],
        offset,
        "攻击力提升",
    )
    return damage_bonus, song_tag_bonus, song_atk_percent


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"苍古自由之誓被动缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"苍古自由之誓{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or not values
    ):
        raise ContentUnitValidationError(f"苍古自由之誓{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"苍古自由之誓{label}分量的 values 未覆盖该精炼"
            f"（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"苍古自由之誓{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"苍古自由之誓{label}分量在该精炼下必须是正数")
    return number
