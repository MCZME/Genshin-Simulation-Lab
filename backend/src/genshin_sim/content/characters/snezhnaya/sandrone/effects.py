"""桑多涅效果行读取与效果 handler 工厂：被动 P4/P5/P6 与命座 C1–C6。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FRAMES_PER_SECOND,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_PASSIVE_P4_HANDLER_KEY,
    SANDRONE_PASSIVE_P5_HANDLER_KEY,
    SANDRONE_PASSIVE_P6_HANDLER_KEY,
    SANDRONE_TACTICS_BUFF_MECHANIC_KEY,
    SandroneP4AssetValues,
    sandrone_tactics_definition_key,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    P6BaseBonus,
    SandroneAtkToMasteryProvider,
    SandroneC1StellarBonusProvider,
    SandroneC2RayCritDamageProvider,
    SandroneC6StellarAscensionProvider,
    SandroneP4BeamBonusProvider,
    SandroneP4PrismBoostProvider,
    SandroneP6StellarBaseBonusProvider,
)
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
from genshin_sim.core.attributes import AttributeSubjectKind, ModifierProvider
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.damage import DamageModifierProvider


def _components(params: Mapping[str, object], *, purpose: str) -> tuple[float, ...]:
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or not components
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for component in components:
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes, bytearray))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components 数值必须是数字")
        values.append(float(value))
    return tuple(values)


def _component(params: Mapping[str, object], index: int, *, purpose: str) -> float:
    values = _components(params, purpose=purpose)
    if index >= len(values):
        raise ContentUnitValidationError(f"{purpose} 缺少第 {index + 1} 个数值分量")
    return values[index]


def _effect_name(params: Mapping[str, object], *, position: str) -> str:
    """读取资产效果行的正式名称（``params.name``）。

    效果行的名称随资产更新（命座与被动名称来自官方文本），内容代码不另存一份：
    错误定位与审计显示名统一用它，避免名称在代码里过期。``position`` 只在效果行
    缺名称时用于报错定位。
    """

    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContentUnitValidationError(f"{position} 的资产效果行缺少名称")
    return name.strip()


@dataclass(frozen=True, slots=True)
class SandroneC6AssetValues:
    """资产命座第 6 层效果行的机器数值（唯一来源）。"""

    extra_segment_count: int
    normal_ratio: float
    conduct_ratio: float
    swirl_ratio: float
    ascension_bonus: float


def read_c6_asset_values(params: Mapping[str, object]) -> SandroneC6AssetValues:
    """解析资产命座第 6 层效果行：追加段段数与三段倍率、星烁擢升。"""

    purpose = "命之座第6层 集束型冷凝射线"
    segment_count = _component(params, 1, purpose=purpose)
    if segment_count != int(segment_count) or segment_count <= 0:
        raise ContentUnitValidationError(f"{purpose} 追加段数必须是正整数")
    normal_ratio = _component(params, 2, purpose=purpose)
    conduct_ratio = _component(params, 4, purpose=purpose)
    swirl_ratio = _component(params, 5, purpose=purpose)
    ascension_bonus = _component(params, 7, purpose=purpose)
    if normal_ratio <= 0.0 or conduct_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 追加段倍率必须为正数")
    if ascension_bonus < 0.0:
        raise ContentUnitValidationError(f"{purpose} 星烁擢升不能为负数")
    return SandroneC6AssetValues(
        extra_segment_count=int(segment_count),
        normal_ratio=normal_ratio,
        conduct_ratio=conduct_ratio,
        swirl_ratio=swirl_ratio,
        ascension_bonus=ascension_bonus,
    )


def read_p6_base_bonus(params: Mapping[str, object]) -> P6BaseBonus:
    """解析资产被动「星耀祝礼·唯理为光」效果行：P6 星烁基础增伤折算参数。

    分量顺序（与资产一致，前两位为文本内链接编号与持续秒数）：
    [0] 链接 极星辉域  [1] 持续秒数  [2] 每 N 点攻击（100）
    [3] 增伤比例（0.7%）  [4] 上限（14%）。
    """

    purpose = "天赋「星耀祝礼·唯理为光」"
    return P6BaseBonus(
        per_100_atk=_component(params, 2, purpose=purpose),
        bonus_rate=_component(params, 3, purpose=purpose),
        cap=_component(params, 4, purpose=purpose),
    )


def read_c1_power_rate_reduction(params: Mapping[str, object]) -> float:
    """解析资产命座第 1 层效果行：解算功率提升速度折算系数（number_3，-50%）。"""

    purpose = "命之座第 1 层 鎏金未凋，夕暮已远"
    reduction = _component(params, 2, purpose=purpose)
    if not 0.0 < reduction <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 功率提升折算系数必须在 (0, 1] 区间")
    return reduction


def read_p4_asset_values(params: Mapping[str, object]) -> SandroneP4AssetValues:
    """解析资产被动「悠久的演算机关」效果行：阈值、强化倍率与光束加成。"""

    purpose = "天赋「悠久的演算机关」"
    power_threshold = _component(params, 3, purpose=purpose)
    prism_boost_multiplier = _component(params, 4, purpose=purpose)
    max_stacks = _component(params, 5, purpose=purpose)
    duration_seconds = _component(params, 6, purpose=purpose)
    power_step = _component(params, 7, purpose=purpose)
    beam_per_stack = _component(params, 10, purpose=purpose)
    if power_threshold <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 解算功率阈值必须为正数")
    if prism_boost_multiplier <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 棱晶弹强化倍率必须为正数")
    if max_stacks != int(max_stacks) or max_stacks <= 0:
        raise ContentUnitValidationError(f"{purpose} 改进战术层数上限必须是正整数")
    if duration_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 改进战术持续秒数必须为正数")
    if power_step <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 改进战术功率步长必须为正数")
    if beam_per_stack < 0.0:
        raise ContentUnitValidationError(f"{purpose} 光束每层倍率不能为负数")
    return SandroneP4AssetValues(
        power_threshold=power_threshold,
        prism_boost_multiplier=prism_boost_multiplier,
        tactics_power_step=power_step,
        tactics_max_stacks=int(max_stacks),
        tactics_duration_frames=round(duration_seconds * FRAMES_PER_SECOND),
        beam_bonus_per_stack=beam_per_stack,
    )


def _validate_owner(request: EffectContentUnitRequest, handler_key: str) -> int:
    """身份判断按 handler_key（代码实现绑定入口）：请求路由到本工厂的键必须一致。"""

    if request.handler_key != handler_key:
        raise ContentUnitValidationError(
            f"{handler_key} 收到 handler 键不符的效果请求：{request.handler_key}"
        )
    if request.slot is None:
        raise ContentUnitValidationError(f"{handler_key} 效果缺少角色槽位")
    return request.slot


def _effect_unit(
    *,
    request: EffectContentUnitRequest,
    handler_key: str,
    kind: EffectKind,
    unlock: UnlockSpec,
    purpose: str,
    event_hooks: tuple[EventHook, ...] = (),
    attribute_providers: tuple[ModifierProvider, ...] = (),
    damage_modifier_providers: tuple[DamageModifierProvider, ...] = (),
    buff_definitions: tuple[BuffDefinition, ...] = (),
    talent_level_boosts: Mapping[str, int] | None = None,
    compiled_params: Mapping[str, JSONValue] | None = None,
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=SANDRONE_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=kind,
                unlock=unlock,
                params=dict(request.params),
            ),
        ),
        event_hooks=event_hooks,
        attribute_providers=attribute_providers,
        damage_modifier_providers=damage_modifier_providers,
        buff_definitions=buff_definitions,
        talent_level_boosts=dict(talent_level_boosts or {}),
        compiled_params=dict(compiled_params or {}),
        metadata={"purpose": purpose},
    )


def create_sandrone_passive_p4(request: EffectContentUnitRequest) -> ContentUnit:
    """P4 悠久的演算机关：战技排空叠层与爆发光束加成（角色单元承载）。"""

    slot = _validate_owner(request, SANDRONE_PASSIVE_P4_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「悠久的演算机关」")
    values = read_p4_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    provider = SandroneP4PrismBoostProvider(
        owner_ref=owner_ref,
        boost_multiplier=values.prism_boost_multiplier,
        source_key=SANDRONE_PASSIVE_P4_HANDLER_KEY,
        display_name=f"{name}·棱晶弹强化",
    )
    beam_provider = SandroneP4BeamBonusProvider(
        owner_ref=owner_ref,
        bonus_per_stack=values.beam_bonus_per_stack,
        source_key=SANDRONE_PASSIVE_P4_HANDLER_KEY,
        display_name=f"{name}·光束加成",
    )
    tactics_definition_key = sandrone_tactics_definition_key(slot)
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_PASSIVE_P4_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(
            # 突破 1 阶（20 级突破）解锁。
            kind=UnlockKind.ASCENSION,
            threshold=1,
        ),
        purpose="sandrone_passive_p4",
        damage_modifier_providers=(provider, beam_provider),
        buff_definitions=(
            _tactics_buff_definition(
                tactics_definition_key,
                values.tactics_max_stacks,
                display_name=f"{name}·改进战术",
            ),
        ),
        compiled_params={
            "name": name,
            "power_threshold": values.power_threshold,
            "prism_boost_multiplier": values.prism_boost_multiplier,
            "tactics_power_step": values.tactics_power_step,
            "tactics_max_stacks": values.tactics_max_stacks,
            "tactics_duration_frames": values.tactics_duration_frames,
            "beam_bonus_per_stack": values.beam_bonus_per_stack,
            "tactics_definition_key": tactics_definition_key,
        },
    )


def _tactics_buff_definition(
    definition_key: str,
    max_stacks: int,
    *,
    display_name: str,
) -> BuffDefinition:
    """改进战术：共享期限的纯层数载体，不带属性词条。

    ``stack_refresh`` 策略与资产语义一致：每次叠层刷新全部层数的共享到期帧；
    层数满后继续申请只刷新期限（resolver 收敛，申请侧不感知层数）。定义键按
    槽位区分，冲突键刻意同值——同槽位实例互斥，层数收敛于单条记录。
    """

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=SANDRONE_TACTICS_BUFF_MECHANIC_KEY,
        handler_key=SANDRONE_PASSIVE_P4_HANDLER_KEY,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=max_stacks,
        marker_only=True,
        display_name=display_name,
    )


def create_sandrone_passive_p5(request: EffectContentUnitRequest) -> ContentUnit:
    """P5 淑女的行事准则：每 100 攻击力 +8 精通，至多 160。"""

    slot = _validate_owner(request, SANDRONE_PASSIVE_P5_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「淑女的行事准则」")
    em_per_100 = _component(request.params, 1, purpose=name)
    em_cap = _component(request.params, 2, purpose=name)
    owner_ref = f"character:slot_{slot}"
    provider = SandroneAtkToMasteryProvider(
        owner_ref=owner_ref,
        em_per_100_atk=em_per_100,
        em_cap=em_cap,
        source_key=SANDRONE_PASSIVE_P5_HANDLER_KEY,
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_PASSIVE_P5_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(
            # 突破 4 阶（60 级突破）解锁。
            kind=UnlockKind.ASCENSION,
            threshold=4,
        ),
        purpose="sandrone_passive_p5",
        attribute_providers=(provider,),
    )


def create_sandrone_passive_p6(request: EffectContentUnitRequest) -> ContentUnit:
    """P6 星耀祝礼·唯理为光：星烁基础增伤随攻击力折算（provider 词条承载）。

    折算参数取自本条资产效果行；增伤数值在伤害结算期由 provider 按桑多涅
    实时攻击力换算并署名（D-082），效果单元因此自持全部机器行为。
    """

    slot = _validate_owner(request, SANDRONE_PASSIVE_P6_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「星耀祝礼·唯理为光」")
    owner_ref = f"character:slot_{slot}"
    provider = SandroneP6StellarBaseBonusProvider(
        owner_ref=owner_ref,
        base_bonus=read_p6_base_bonus(request.params),
        source_key=SANDRONE_PASSIVE_P6_HANDLER_KEY,
        display_name=f"{name}·星烁基础增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_PASSIVE_P6_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
        purpose="sandrone_passive_p6",
        damage_modifier_providers=(provider,),
    )


def create_sandrone_constellation_c1(request: EffectContentUnitRequest) -> ContentUnit:
    """C1 鎏金未凋，夕暮已远：功率上升 -50%（角色单元承载）+ 全队星烁增伤。"""

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C1_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 1 层")
    bonus_value = _component(request.params, 3, purpose=name)
    owner_ref = f"character:slot_{slot}"
    provider = SandroneC1StellarBonusProvider(
        owner_ref=owner_ref,
        bonus_value=bonus_value,
        source_key=SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
        display_name=f"{name}·星烁增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=1),
        purpose="sandrone_constellation_c1",
        damage_modifier_providers=(provider,),
    )


def create_sandrone_constellation_c2(request: EffectContentUnitRequest) -> ContentUnit:
    """C2 回望镜中，时岁翩然：射线星超导冰伤逐射线暴伤（序号由法洁欧以请求级事实承载）。"""

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C2_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 2 层")
    crit_base = _component(request.params, 0, purpose=name)
    crit_per_ray = _component(request.params, 2, purpose=name)
    max_rays = _component(request.params, 3, purpose=name)
    owner_ref = f"character:slot_{slot}"
    provider = SandroneC2RayCritDamageProvider(
        owner_ref=owner_ref,
        crit_damage_base=crit_base,
        crit_damage_per_ray=crit_per_ray,
        max_rays=int(max_rays),
        source_key=SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
        display_name=f"{name}·射线暴伤",
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=2),
        purpose="sandrone_constellation_c2",
        damage_modifier_providers=(provider,),
    )


def create_sandrone_constellation_c3(request: EffectContentUnitRequest) -> ContentUnit:
    """C3 不叹日落，不羡月升：普通攻击天赋等级 +3。"""

    _validate_owner(request, SANDRONE_CONSTELLATION_C3_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 3 层")
    boost = _component(request.params, 1, purpose=name)
    if boost != int(boost) or boost <= 0:
        raise ContentUnitValidationError("C3 天赋等级提升必须是正整数")
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=3),
        purpose="sandrone_constellation_c3",
        talent_level_boosts={"normal_attack": int(boost)},
    )


def create_sandrone_constellation_c4(request: EffectContentUnitRequest) -> ContentUnit:
    """C4 世事皆数，昼来夜往：桑多涅的星超导/星扩散冰伤害命中召唤协同攻击。

    效果行分量顺序：星超导倍率 / 星扩散倍率 / 冷却秒数（官方文本的
    125%/187.5% 依次排列，冷却秒数为末位纯数分量）。
    """

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C4_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 4 层")
    attack_ratio = _component(request.params, 0, purpose=name)
    swirl_ratio = _component(request.params, 1, purpose=name)
    cooldown_seconds = _component(request.params, 2, purpose=name)
    if attack_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError("C4 协同攻击倍率必须为正数")
    if cooldown_seconds <= 0.0:
        raise ContentUnitValidationError("C4 协同攻击内置冷却必须为正数秒")
    owner_ref = f"character:slot_{slot}"
    hook = SandroneC4CoordinatedAttackHook(
        owner_ref=owner_ref,
        slot=slot,
        attack_ratio=attack_ratio,
        swirl_ratio=swirl_ratio,
        cooldown_frames=round(cooldown_seconds * FRAMES_PER_SECOND),
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=4),
        purpose="sandrone_constellation_c4",
        event_hooks=(hook,),
    )


def create_sandrone_constellation_c5(request: EffectContentUnitRequest) -> ContentUnit:
    """C5 万象皆灰，唯理明畅：元素爆发天赋等级 +3。"""

    _validate_owner(request, SANDRONE_CONSTELLATION_C5_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 5 层")
    boost = _component(request.params, 1, purpose=name)
    if boost != int(boost) or boost <= 0:
        raise ContentUnitValidationError("C5 天赋等级提升必须是正整数")
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=5),
        purpose="sandrone_constellation_c5",
        talent_level_boosts={"elemental_burst": int(boost)},
    )


def create_sandrone_constellation_c6(request: EffectContentUnitRequest) -> ContentUnit:
    """C6 水仙梦醒，且望晨光：集束型追加段与星烁擢升。

    集束型追加段（段数与三段倍率）在角色单元编译期折算；星烁擢升由本条效果
    单元的 provider 词条承载（按伤害来源自筛桑多涅本人，D-082）。这里解析一遍
    效果行（数值不合法时本条单元直接失败），并把取值写进 ``compiled_params``
    供装配/诊断核对。
    """

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C6_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 6 层")
    values = read_c6_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    provider = SandroneC6StellarAscensionProvider(
        owner_ref=owner_ref,
        ascension_bonus=values.ascension_bonus,
        source_key=SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
        display_name=f"{name}·星烁擢升",
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=6),
        purpose="sandrone_constellation_c6",
        damage_modifier_providers=(provider,),
        compiled_params={
            "name": name,
            "extra_segment_count": values.extra_segment_count,
            "normal_ratio": values.normal_ratio,
            "conduct_ratio": values.conduct_ratio,
            "swirl_ratio": values.swirl_ratio,
            "ascension_bonus": values.ascension_bonus,
        },
    )
