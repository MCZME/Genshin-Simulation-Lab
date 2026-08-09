"""芭芭拉效果 handler 工厂：安可与命座 1-5（C6 不实现）。

统一把资产 ``effect_payloads`` 编译为 ContentUnit：工厂只负责组装效果声明与
行为切片（``event_hooks`` / ``talent_level_boosts`` /
``cooldown_duration_terms`` / ``attribute_providers``）；行为实现见
``hooks.py``（事件钩子）与 ``modifiers.py``（属性修饰）。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import Decimal

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ASSET_KEY,
    BARBARA_CONSTELLATION_C1_HANDLER_KEY,
    BARBARA_CONSTELLATION_C2_COOLDOWN_TERM_KEY,
    BARBARA_CONSTELLATION_C2_HANDLER_KEY,
    BARBARA_CONSTELLATION_C3_HANDLER_KEY,
    BARBARA_CONSTELLATION_C4_HANDLER_KEY,
    BARBARA_CONSTELLATION_C5_HANDLER_KEY,
    BARBARA_CONTENT_VERSION,
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    BARBARA_ENCORE_EFFECT_HANDLER_KEY,
    BARBARA_RING_OBJECT_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.hooks import (
    BarbaraConstellationC1EnergyHook,
    BarbaraConstellationC4EnergyHook,
    BarbaraRingEncoreHook,
)
from genshin_sim.content.characters.mondstadt.barbara.modifiers import (
    BarbaraConstellationC2HydroBonusProvider,
)
from genshin_sim.content.definitions.components import GenericComponent
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.definitions.effects import (
    EffectKind,
    EffectSpec,
    UnlockKind,
    UnlockSpec,
)
from genshin_sim.content.models import EventHook
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.core.systems.cooldown import (
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownKey,
    CooldownSubjectRef,
)

FRAMES_PER_SECOND = 60


def parse_numeric_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从资产 ``effect_payloads.params.components`` 读取前 ``count`` 个数值。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)


def create_barbara_encore_effect(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """把安可资产效果 payload 编译为环延长 hook 与效果声明。"""

    slot = _validate_owner(request, BARBARA_ENCORE_EFFECT_HANDLER_KEY)
    extend_seconds, max_extend_seconds = parse_numeric_component_values(
        request.params,
        count=2,
        purpose="安可效果",
    )
    extend_frames = round(extend_seconds * FRAMES_PER_SECOND)
    max_extra_frames = round(max_extend_seconds * FRAMES_PER_SECOND)
    owner_ref = f"character:slot_{slot}"
    unlock = UnlockSpec(kind=UnlockKind.ASCENSION, threshold=4)
    hook = BarbaraRingEncoreHook(
        owner_ref=owner_ref,
        slot=slot,
        object_key=BARBARA_RING_OBJECT_KEY,
        extend_frames=extend_frames,
        max_extra_frames=max_extra_frames,
    )
    effect_spec = EffectSpec(
        effect_key=request.effect_key,
        kind=EffectKind.PASSIVE,
        unlock=unlock,
        component=GenericComponent(
            kind="extend_created_object_on_energy_pickup",
            params={
                "object_key": BARBARA_RING_OBJECT_KEY,
                "extend_frames": extend_frames,
                "max_extra_frames": max_extra_frames,
            },
        ),
        params=dict(request.params),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=BARBARA_ENCORE_EFFECT_HANDLER_KEY,
        version=BARBARA_CONTENT_VERSION,
        slot=slot,
        event_hooks=(hook,),
        effects=(effect_spec,),
        metadata={"purpose": "barbara_passive_encore"},
    )


def create_barbara_constellation_c1(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """C1 彩色歌谣：周期恢复元素能量。"""

    slot = _validate_owner(request, BARBARA_CONSTELLATION_C1_HANDLER_KEY)
    interval_seconds, amount = parse_numeric_component_values(
        request.params,
        count=2,
        purpose="彩色歌谣",
    )
    interval_frames = round(interval_seconds * FRAMES_PER_SECOND)
    if interval_frames <= 0:
        raise ContentUnitValidationError("彩色歌谣恢复间隔必须折算为正帧数")
    owner_ref = f"character:slot_{slot}"
    hook = BarbaraConstellationC1EnergyHook(
        owner_ref=owner_ref,
        slot=slot,
        interval_frames=interval_frames,
        amount=amount,
    )
    return _constellation_unit(
        request=request,
        handler_key=BARBARA_CONSTELLATION_C1_HANDLER_KEY,
        threshold=1,
        purpose="barbara_constellation_c1",
        event_hooks=(hook,),
    )


def create_barbara_constellation_c2(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """C2 元气迸发：冷却降低 + 环期间当前场角色水伤加成。"""

    slot = _validate_owner(request, BARBARA_CONSTELLATION_C2_HANDLER_KEY)
    hydro_bonus, cooldown_reduction = parse_numeric_component_values(
        request.params,
        count=2,
        purpose="元气迸发",
    )
    if cooldown_reduction >= 1:
        raise ContentUnitValidationError("元气迸发的冷却降低比例必须小于 1")
    owner_ref = f"character:slot_{slot}"
    cooldown_term = CooldownDurationTerm(
        term_key=BARBARA_CONSTELLATION_C2_COOLDOWN_TERM_KEY,
        source_ref=BARBARA_CONSTELLATION_C2_HANDLER_KEY,
        stage=CooldownDurationStage.OWNER_ADJUSTMENT,
        operation=CooldownDurationOperation.MULTIPLY_CURRENT,
        value=Decimal(str(1 - cooldown_reduction)),
    )
    provider = BarbaraConstellationC2HydroBonusProvider(
        slot=slot,
        bonus_value=hydro_bonus,
        object_key=BARBARA_RING_OBJECT_KEY,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=BARBARA_CONSTELLATION_C2_HANDLER_KEY,
        version=BARBARA_CONTENT_VERSION,
        slot=slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=EffectKind.CONSTELLATION,
                unlock=UnlockSpec(
                    kind=UnlockKind.CONSTELLATION,
                    threshold=2,
                ),
                params=dict(request.params),
            ),
        ),
        cooldown_duration_terms={
            CooldownKey(
                CooldownSubjectRef.character(owner_ref),
                BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
            ): (cooldown_term,),
        },
        attribute_providers=(provider,),
        metadata={"purpose": "barbara_constellation_c2"},
    )


def create_barbara_constellation_c3(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """C3 明日之星：元素爆发天赋等级 +3。"""

    _validate_owner(request, BARBARA_CONSTELLATION_C3_HANDLER_KEY)
    boost, max_level = _parse_boost(
        request.params,
        purpose="明日之星",
    )
    return _boost_unit(
        request=request,
        handler_key=BARBARA_CONSTELLATION_C3_HANDLER_KEY,
        threshold=3,
        talent_key="elemental_burst",
        boost=boost,
        max_level=max_level,
        purpose="barbara_constellation_c3",
    )


def create_barbara_constellation_c4(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """C4 努力即魔法：重击命中敌人时按不同敌人恢复元素能量。"""

    slot = _validate_owner(request, BARBARA_CONSTELLATION_C4_HANDLER_KEY)
    amount, max_per_action = parse_numeric_component_values(
        request.params,
        count=2,
        purpose="努力即魔法",
    )
    if max_per_action < 1:
        raise ContentUnitValidationError("努力即魔法的单次上限必须至少为 1")
    owner_ref = f"character:slot_{slot}"
    hook = BarbaraConstellationC4EnergyHook(
        owner_ref=owner_ref,
        slot=slot,
        amount=amount,
        max_per_action=round(max_per_action),
    )
    return _constellation_unit(
        request=request,
        handler_key=BARBARA_CONSTELLATION_C4_HANDLER_KEY,
        threshold=4,
        purpose="barbara_constellation_c4",
        event_hooks=(hook,),
    )


def create_barbara_constellation_c5(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """C5 纯真的羁绊：元素战技天赋等级 +3。"""

    _validate_owner(request, BARBARA_CONSTELLATION_C5_HANDLER_KEY)
    boost, max_level = _parse_boost(
        request.params,
        purpose="纯真的羁绊",
    )
    return _boost_unit(
        request=request,
        handler_key=BARBARA_CONSTELLATION_C5_HANDLER_KEY,
        threshold=5,
        talent_key="elemental_skill",
        boost=boost,
        max_level=max_level,
        purpose="barbara_constellation_c5",
    )


def _validate_owner(request: EffectContentUnitRequest, handler_key: str) -> int:
    if request.owner_key != BARBARA_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{handler_key} 效果 handler 只接受芭芭拉资产：{request.owner_key}"
        )
    if request.slot is None:
        raise ContentUnitValidationError(f"{handler_key} 效果缺少角色槽位")
    return request.slot


def _constellation_unit(
    *,
    request: EffectContentUnitRequest,
    handler_key: str,
    threshold: int,
    purpose: str,
    event_hooks: tuple[EventHook, ...] = (),
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=BARBARA_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=EffectKind.CONSTELLATION,
                unlock=UnlockSpec(
                    kind=UnlockKind.CONSTELLATION,
                    threshold=threshold,
                ),
                params=dict(request.params),
            ),
        ),
        event_hooks=event_hooks,
        metadata={"purpose": purpose},
    )


def _parse_boost(
    params: Mapping[str, object],
    *,
    purpose: str,
) -> tuple[int, int]:
    boost, max_level = parse_numeric_component_values(
        params,
        count=2,
        purpose=purpose,
    )
    if int(boost) != boost or int(max_level) != max_level:
        raise ContentUnitValidationError(f"{purpose} 等级提升与上限必须是整数")
    boost_int = int(boost)
    max_level_int = int(max_level)
    if boost_int <= 0 or max_level_int <= 0 or max_level_int < boost_int:
        raise ContentUnitValidationError(f"{purpose} 等级提升必须为正整数且不超过上限")
    return boost_int, max_level_int


def _boost_unit(
    *,
    request: EffectContentUnitRequest,
    handler_key: str,
    threshold: int,
    talent_key: str,
    boost: int,
    max_level: int,
    purpose: str,
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=BARBARA_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=EffectKind.CONSTELLATION,
                unlock=UnlockSpec(
                    kind=UnlockKind.CONSTELLATION,
                    threshold=threshold,
                ),
                params=dict(request.params),
            ),
        ),
        talent_level_boosts={talent_key: boost},
        metadata={
            "purpose": purpose,
            "talent_level_max": max_level,
        },
    )
