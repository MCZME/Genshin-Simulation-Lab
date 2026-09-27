"""桑多涅效果行读取与效果 handler 工厂：被动 P4/P5/P6 与命座 C1–C6。

统一把资产 ``effect_payloads`` 编译为 ContentUnit。行为切片按载体拆分：

- P5（攻击力转精通）、C1（全队星烁增伤）、C2（射线暴伤）由本包
  ``modifiers.py`` 的 provider 承载；
- C4（星超导/星扩散冰伤害命中召唤协同攻击）由 ``hooks.py`` 的事件钩子承载；
- C3/C5（天赋等级提升）以 ``talent_level_boosts`` 静态切片承载，经
  content compiler 收敛进角色单元的天赋等级解析；
- P4 与 C6 的数值行为与法洁欧状态机/影响工厂深度耦合（排空叠层、棱晶弹
  强化、集束型射线与额外段、星烁擢升），承载在角色单元内（fageou.py /
  impacts.py / stellar.py）；本文件的效果单元保留效果声明与解锁门槛，
  metadata 记录真实载体。

C6 的机器数值（段数、三段倍率、星烁擢升）由 ``read_c6_asset_values`` 从
**资产命座第 6 层效果行**解析；角色单元经 ``request.effect_params``、效果
单元经 ``request.owner_context.effect_params`` 拿到同一条效果行，不另设常量。

P8 生活天赋为空实现（bootstrap 注册 EMPTY handler，不建单元）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_C6_UNLOCK_KEY,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_P4_ASCENSION_THRESHOLD,
    SANDRONE_P5_ASCENSION_THRESHOLD,
    SANDRONE_PASSIVE_P4_HANDLER_KEY,
    SANDRONE_PASSIVE_P5_HANDLER_KEY,
    SANDRONE_PASSIVE_P6_HANDLER_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    SandroneAtkToMasteryProvider,
    SandroneC1StellarBonusProvider,
    SandroneC2RayCritDamageProvider,
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
from genshin_sim.content.registries import EffectContentUnitRequest, EffectOwnerContext
from genshin_sim.core.attributes import ModifierProvider
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.damage import DamageModifierProvider

FRAMES_PER_SECOND = 60

P4_CARRIER_NOTE = (
    "数值行为承载于角色单元：排空叠层与过期（fageou.py）、棱晶弹 400% 与"
    "光束加成（actions.py/impacts.py），常量见 data.py。"
)
P6_CARRIER_NOTE = (
    "固定天赋：capability 随角色单元静态声明，基础增伤在星烁输入组装时按"
    "攻击力折算（stellar.py stellar_base_bonus_for_atk，常量见 data.py）。"
)
C1_CARRIER_NOTE = "功率上升减速由角色单元按命座等级编译（fageou 构造参数）。"
C6_CARRIER_NOTE = (
    "集束型追加段与星烁擢升由角色单元按命座等级编译（fageou/impacts/"
    "stellar），机器数值取自本条效果行（段数/三段倍率/擢升）。"
)


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


@dataclass(frozen=True, slots=True)
class SandroneC6AssetValues:
    """资产命座第 6 层效果行的机器数值（唯一来源）。"""

    extra_segment_count: int
    normal_ratio: float
    conduct_ratio: float
    swirl_ratio: float
    ascension_bonus: float


def read_c6_asset_values(params: Mapping[str, object]) -> SandroneC6AssetValues:
    """解析资产命座第 6 层效果行：追加段段数与三段倍率、星烁擢升。

    分量顺序与资产一致（见 data.py ``SANDRONE_C6_UNLOCK_KEY`` 注释）：
    ``[1]`` 段数、``[2]`` 普通倍率、``[4]`` 星超导倍率、``[5]`` 星扩散倍率、
    ``[7]`` 星烁擢升；``[0]`` / ``[3]`` / ``[6]`` 是文本内链接编号与重复段数，
    不参与解析（与 C1/C2/C4 的按序取分量口径一致）。
    """

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


def resolve_c6_ascension_bonus(
    owner_context: EffectOwnerContext,
    *,
    purpose: str,
) -> float:
    """从拥有者上下文读取 C6 星烁擢升；未解锁第 6 层时为 0。

    跨效果行的机器耦合（C6 擢升覆盖 C4 协同攻击的星烁伤害）需要同一条效果行
    的数值，走 ``EffectOwnerContext.effect_params`` 取序，不另设常量。
    """

    if owner_context.constellation < 6:
        return 0.0
    params = owner_context.effect_params.get(SANDRONE_C6_UNLOCK_KEY)
    if params is None:
        raise ContentUnitValidationError(f"{purpose} 已解锁第 6 层但缺少 C6 资产效果行")
    return read_c6_asset_values(params).ascension_bonus


def _validate_owner(request: EffectContentUnitRequest, handler_key: str) -> int:
    if request.owner_key != SANDRONE_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{handler_key} 效果 handler 只接受桑多涅资产：{request.owner_key}"
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
    note: str | None = None,
    event_hooks: tuple[EventHook, ...] = (),
    attribute_providers: tuple[ModifierProvider, ...] = (),
    damage_modifier_providers: tuple[DamageModifierProvider, ...] = (),
    talent_level_boosts: Mapping[str, int] | None = None,
    compiled_params: Mapping[str, JSONValue] | None = None,
) -> ContentUnit:
    metadata: dict[str, str] = {"purpose": purpose}
    if note is not None:
        metadata["carrier_note"] = note
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
        talent_level_boosts=dict(talent_level_boosts or {}),
        compiled_params=dict(compiled_params or {}),
        metadata=metadata,
    )


def create_sandrone_passive_p4(request: EffectContentUnitRequest) -> ContentUnit:
    """P4 悠久的演算机关：战技排空叠层与爆发光束加成（角色单元承载）。"""

    _validate_owner(request, SANDRONE_PASSIVE_P4_HANDLER_KEY)
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_PASSIVE_P4_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(
            kind=UnlockKind.ASCENSION,
            threshold=SANDRONE_P4_ASCENSION_THRESHOLD,
        ),
        purpose="sandrone_passive_p4",
        note=P4_CARRIER_NOTE,
    )


def create_sandrone_passive_p5(request: EffectContentUnitRequest) -> ContentUnit:
    """P5 淑女的行事准则：每 100 攻击力 +8 精通，至多 160。"""

    slot = _validate_owner(request, SANDRONE_PASSIVE_P5_HANDLER_KEY)
    em_per_100 = _component(request.params, 1, purpose="淑女的行事准则")
    em_cap = _component(request.params, 2, purpose="淑女的行事准则")
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
            kind=UnlockKind.ASCENSION,
            threshold=SANDRONE_P5_ASCENSION_THRESHOLD,
        ),
        purpose="sandrone_passive_p5",
        attribute_providers=(provider,),
    )


def create_sandrone_passive_p6(request: EffectContentUnitRequest) -> ContentUnit:
    """P6 星耀祝礼·唯理为光：星烁基础增伤随攻击力折算（角色星烁通道承载）。"""

    _validate_owner(request, SANDRONE_PASSIVE_P6_HANDLER_KEY)
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_PASSIVE_P6_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
        purpose="sandrone_passive_p6",
        note=P6_CARRIER_NOTE,
    )


def create_sandrone_constellation_c1(request: EffectContentUnitRequest) -> ContentUnit:
    """C1 生命之数·演算倍增：功率上升 -50%（角色单元承载）+ 全队星烁增伤。"""

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C1_HANDLER_KEY)
    bonus_value = _component(request.params, 3, purpose="生命之数·演算倍增")
    owner_ref = f"character:slot_{slot}"
    provider = SandroneC1StellarBonusProvider(
        owner_ref=owner_ref,
        bonus_value=bonus_value,
        source_key=SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=1),
        purpose="sandrone_constellation_c1",
        note=C1_CARRIER_NOTE,
        damage_modifier_providers=(provider,),
    )


def create_sandrone_constellation_c2(request: EffectContentUnitRequest) -> ContentUnit:
    """C2 霜愈的演进法：射线星超导冰伤逐射线暴伤（会话序号由法洁欧承载）。"""

    slot = _validate_owner(request, SANDRONE_CONSTELLATION_C2_HANDLER_KEY)
    crit_base = _component(request.params, 0, purpose="霜愈的演进法")
    crit_per_ray = _component(request.params, 2, purpose="霜愈的演进法")
    max_rays = _component(request.params, 3, purpose="霜愈的演进法")
    owner_ref = f"character:slot_{slot}"
    provider = SandroneC2RayCritDamageProvider(
        owner_ref=owner_ref,
        crit_damage_base=crit_base,
        crit_damage_per_ray=crit_per_ray,
        max_rays=int(max_rays),
        source_key=SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    )
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=2),
        purpose="sandrone_constellation_c2",
        note="射线会话序号标签由法洁欧 hook 承载（按命座等级启用）。",
        damage_modifier_providers=(provider,),
    )


def create_sandrone_constellation_c3(request: EffectContentUnitRequest) -> ContentUnit:
    """C3 不叹日落，不羡月升：普通攻击天赋等级 +3。"""

    _validate_owner(request, SANDRONE_CONSTELLATION_C3_HANDLER_KEY)
    boost = _component(request.params, 1, purpose="不叹日落，不羡月升")
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
    attack_ratio = _component(request.params, 0, purpose="世事皆数，昼来夜往")
    swirl_ratio = _component(request.params, 1, purpose="世事皆数，昼来夜往")
    cooldown_seconds = _component(request.params, 2, purpose="世事皆数，昼来夜往")
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
        # C6 擢升覆盖桑多涅全部星烁伤害，含 C4 产出的协同攻击：数值取自资产
        # 命座第 6 层效果行（拥有者上下文带全部效果行），未解锁第 6 层为 0。
        ascension_bonus=resolve_c6_ascension_bonus(
            request.owner_context,
            purpose="世事皆数，昼来夜往",
        ),
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
    boost = _component(request.params, 1, purpose="万象皆灰，唯理明畅")
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
    """C6 水仙梦醒，且望晨光：集束型追加段与星烁擢升（角色单元承载）。

    机器数值在本条效果行里，行为在角色单元里：这里解析一遍效果行（数值不合法
    时本条单元直接失败），并把取值写进 ``compiled_params`` 供装配/诊断核对。
    """

    _validate_owner(request, SANDRONE_CONSTELLATION_C6_HANDLER_KEY)
    values = read_c6_asset_values(request.params)
    return _effect_unit(
        request=request,
        handler_key=SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=6),
        purpose="sandrone_constellation_c6",
        note=C6_CARRIER_NOTE,
        compiled_params={
            "extra_segment_count": values.extra_segment_count,
            "normal_ratio": values.normal_ratio,
            "conduct_ratio": values.conduct_ratio,
            "swirl_ratio": values.swirl_ratio,
            "ascension_bonus": values.ascension_bonus,
        },
    )
