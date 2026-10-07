"""阿罗夏效果行工厂：被动 P4/P5/P6 与命座 C1/C2/C3/C4/C5/C6。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CONSTELLATION_C1_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C2_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C3_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C4_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C5_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C6_HANDLER_KEY,
    ALYOSHA_CONTENT_VERSION,
    ALYOSHA_PASSIVE_P4_HANDLER_KEY,
    ALYOSHA_PASSIVE_P5_HANDLER_KEY,
    ALYOSHA_PASSIVE_P6_HANDLER_KEY,
    FRAMES_PER_SECOND,
)
from genshin_sim.content.characters.snezhnaya.alyosha.hooks import AlyoshaC1EnergyHook
from genshin_sim.content.characters.snezhnaya.alyosha.modifiers import (
    AlyoshaP5EnergyRechargeDamageBonusProvider,
    AlyoshaP6StellarConductBonusProvider,
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
from genshin_sim.content.registries import EffectContentUnitRequest


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
    talent_level_boosts: Mapping[str, int] | None = None,
    event_hooks: tuple = (),
    damage_modifier_providers: tuple = (),
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=ALYOSHA_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=kind,
                unlock=unlock,
                params=dict(request.params),
            ),
        ),
        event_hooks=tuple(event_hooks),
        damage_modifier_providers=tuple(damage_modifier_providers),
        talent_level_boosts=dict(talent_level_boosts or {}),
        metadata={"purpose": purpose},
    )


def _read_talent_boost(request: EffectContentUnitRequest, *, position: str) -> int:
    """读取命座行的天赋等级提升分量。

    资产分量顺序：[0] 提升级数（3）、[1] 天赋等级上限（15，信息性，不消费）。
    """

    name = _effect_name(request.params, position=position)
    boost = _component(request.params, 0, purpose=name)
    if boost != int(boost) or boost <= 0:
        raise ContentUnitValidationError(f"{name} 天赋等级提升必须是正整数")
    return int(boost)


def create_alyosha_constellation_c3(request: EffectContentUnitRequest) -> ContentUnit:
    """C3 Friendly Call（僚朋相唤）：元素战技天赋等级 +3。"""

    _validate_owner(request, ALYOSHA_CONSTELLATION_C3_HANDLER_KEY)
    boost = _read_talent_boost(request, position="命之座第 3 层")
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C3_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=3),
        purpose="alyosha_constellation_c3",
        talent_level_boosts={"elemental_skill": boost},
    )


def create_alyosha_constellation_c5(request: EffectContentUnitRequest) -> ContentUnit:
    """C5 When the Nightbird Falls Silent（莺啼止时）：元素爆发天赋等级 +3。"""

    _validate_owner(request, ALYOSHA_CONSTELLATION_C5_HANDLER_KEY)
    boost = _read_talent_boost(request, position="命之座第 5 层")
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C5_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=5),
        purpose="alyosha_constellation_c5",
        talent_level_boosts={"elemental_burst": boost},
    )


def create_alyosha_passive_p4(request: EffectContentUnitRequest) -> ContentUnit:
    """P4 Awakened by the Baying Hounds（惊醒沉睡的林线）：图加林攻击动作回血。

    回复比例（120% 阿罗夏攻击力）由角色内容单元读取（随轰霆猎场类型的撕咬
    tick 产出），本单元只校验效果行与分量存在并声明解锁条件。
    """

    _validate_owner(request, ALYOSHA_PASSIVE_P4_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「惊醒沉睡的林线」")
    _component(request.params, 1, purpose=name)
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_PASSIVE_P4_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 突破 1 阶（20 级突破）解锁（桑多涅 P4 同口径）。
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=1),
        purpose="alyosha_passive_p4",
    )


def create_alyosha_passive_p5(request: EffectContentUnitRequest) -> ContentUnit:
    """P5 Suffer the Winter Wheat Will（告别冬麦与残叶）：充能效率转 E/Q 增伤。

    资产分量顺序：[0] 充能效率步长 1%、[1] 每步伤害提升 0.35%、[2] 上限 70%。
    """

    slot = _validate_owner(request, ALYOSHA_PASSIVE_P5_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「告别冬麦与残叶」")
    er_step = _component(request.params, 0, purpose=name)
    bonus_per_step = _component(request.params, 1, purpose=name)
    cap = _component(request.params, 2, purpose=name)
    owner_ref = f"character:slot_{slot}"
    provider = AlyoshaP5EnergyRechargeDamageBonusProvider(
        owner_ref=owner_ref,
        er_step=er_step,
        bonus_per_step=bonus_per_step,
        cap=cap,
        source_key=ALYOSHA_PASSIVE_P5_HANDLER_KEY,
        display_name=f"{name}·充能效率增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_PASSIVE_P5_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 突破 4 阶解锁（桑多涅 P5 同口径）。
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=4),
        purpose="alyosha_passive_p5",
        damage_modifier_providers=(provider,),
    )


def create_alyosha_passive_p6(request: EffectContentUnitRequest) -> ContentUnit:
    """P6 Into the Fray（星赴险域）：猎者之准使场上角色星超导增伤按层提升。

    资产分量：[0]/[1] 为内部引用（极星辉域/猎者之准，不消费直接丢弃，
    门控走辉映证据与猎者之准层数端口）；[2] 每层增伤 20%。
    """

    slot = _validate_owner(request, ALYOSHA_PASSIVE_P6_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「星赴险域」")
    bonus_per_stack = _component(request.params, 2, purpose=name)
    owner_ref = f"character:slot_{slot}"
    provider = AlyoshaP6StellarConductBonusProvider(
        owner_ref=owner_ref,
        bonus_per_stack=bonus_per_stack,
        source_key=ALYOSHA_PASSIVE_P6_HANDLER_KEY,
        display_name=f"{name}·星超导增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_PASSIVE_P6_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 星超导机制被动：capability 随内容单元静态声明、条件在结算期判定
        # （桑多涅 P6 同口径）。
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
        purpose="alyosha_passive_p6",
        damage_modifier_providers=(provider,),
    )


def create_alyosha_constellation_c1(request: EffectContentUnitRequest) -> ContentUnit:
    """C1 Frostvale Thunderclap（寒谷轰雷）：雷相关反应回能，18 秒至多一次。

    资产分量顺序：[0] 回复能量 15、[1] 冷却 18 秒。可后台触发，满能量时
    回能被吞、照常进冷却（按实际建模）。
    """

    slot = _validate_owner(request, ALYOSHA_CONSTELLATION_C1_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 1 层")
    energy_amount = _component(request.params, 0, purpose=name)
    cooldown_seconds = _component(request.params, 1, purpose=name)
    if cooldown_seconds <= 0:
        raise ContentUnitValidationError(f"{name} 回能冷却必须为正数秒")
    hook = AlyoshaC1EnergyHook(
        owner_ref=f"character:slot_{slot}",
        slot=slot,
        energy_amount=energy_amount,
        cooldown_frames=round(cooldown_seconds * FRAMES_PER_SECOND),
    )
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C1_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=1),
        purpose="alyosha_constellation_c1",
        event_hooks=(hook,),
    )


def create_alyosha_constellation_c2(request: EffectContentUnitRequest) -> ContentUnit:
    """C2 Howl From Afar（长嗥远讯）：Q 持续 +6s；图加林攻击前施加印记。

    延长秒数与行为开关由角色内容单元读取（创建计划时长 + 撕咬 tick 的
    印记施加），本单元只校验效果行存在并声明解锁条件。
    """

    _validate_owner(request, ALYOSHA_CONSTELLATION_C2_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 2 层")
    _component(request.params, 0, purpose=name)
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C2_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=2),
        purpose="alyosha_constellation_c2",
    )


def create_alyosha_constellation_c4(request: EffectContentUnitRequest) -> ContentUnit:
    """C4 Harvest the Spoils（衔取猎品）：图加林攻击动作治疗最低生命角色。

    回复比例（60% 阿罗夏攻击力）由角色内容单元读取，本单元只校验效果行。
    """

    _validate_owner(request, ALYOSHA_CONSTELLATION_C4_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 4 层")
    _component(request.params, 1, purpose=name)
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C4_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=4),
        purpose="alyosha_constellation_c4",
    )


def create_alyosha_constellation_c6(request: EffectContentUnitRequest) -> ContentUnit:
    """C6 Standard Reclaimed（复夺旌幡）：猎者之准可叠 2 层，叠满 +100 精通。

    层数上限与精通数值由角色内容单元读取（猎者之准定义与伴生精通 Buff），
    本单元只校验效果行存在并声明解锁条件。
    """

    _validate_owner(request, ALYOSHA_CONSTELLATION_C6_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第 6 层")
    for index in (1, 3):
        _component(request.params, index, purpose=name)
    return _effect_unit(
        request=request,
        handler_key=ALYOSHA_CONSTELLATION_C6_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=6),
        purpose="alyosha_constellation_c6",
    )


# ---------------------------------------------------------------------------
# 效果行数值读取器（角色内容单元消费：轰霆猎场回血通道、Q 时长延长、
# 猎者之准层数上限与精通伴生）。
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AlyoshaC6AssetValues:
    """C6 效果行数值：猎者之准层数上限与叠满精通加成。"""

    max_stacks: int
    mastery_bonus: float

    def __post_init__(self) -> None:
        if isinstance(self.max_stacks, bool) or self.max_stacks != int(self.max_stacks):
            raise ContentUnitValidationError("C6 猎者之准层数上限必须是整数")
        if self.max_stacks < 2:
            raise ContentUnitValidationError("C6 猎者之准层数上限必须至少为 2")
        if isinstance(self.mastery_bonus, bool) or self.mastery_bonus <= 0.0:
            raise ContentUnitValidationError("C6 叠满精通加成必须为正数")
        object.__setattr__(self, "max_stacks", int(self.max_stacks))


def read_p4_heal_ratio(params: Mapping[str, object]) -> float:
    """P4 回复比例（占阿罗夏攻击力）：资产分量 [1]（[0] 为图加林内部引用）。"""

    name = _effect_name(params, position="天赋「惊醒沉睡的林线」")
    return _component(params, 1, purpose=name)


def read_c4_heal_ratio(params: Mapping[str, object]) -> float:
    """C4 回复比例（占阿罗夏攻击力）：资产分量 [1]（[0] 为图加林内部引用）。"""

    name = _effect_name(params, position="命之座第 4 层")
    return _component(params, 1, purpose=name)


def read_c2_extension_seconds(params: Mapping[str, object]) -> float:
    """C2 元素爆发持续时间延长秒数：资产分量 [0]。"""

    name = _effect_name(params, position="命之座第 2 层")
    return _component(params, 0, purpose=name)


def read_c6_asset_values(params: Mapping[str, object]) -> AlyoshaC6AssetValues:
    """C6 数值：资产分量 [1] 层数上限、[3] 叠满精通（[0]/[2] 为内部引用）。"""

    name = _effect_name(params, position="命之座第 6 层")
    return AlyoshaC6AssetValues(
        max_stacks=int(_component(params, 1, purpose=name)),
        mastery_bonus=_component(params, 3, purpose=name),
    )
