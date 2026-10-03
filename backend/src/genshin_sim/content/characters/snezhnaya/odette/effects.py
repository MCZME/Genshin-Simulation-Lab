"""奥黛塔被动与命座效果单元工厂（切片 4：P4 华彩、C6 擢升；切片 5：P5/P6）。

机器数值一律取自资产效果行组件（``number_N`` 位置约定与桑多涅一致，前导
分量为文本内链接编号）；组件位映射见各读取函数 docstring。C2「每层华彩
再 +7% 攻击力」是华彩 Buff 自身的词条强化，随 P4 工厂按命座门控编译进
Buff 定义（见 ``splendor.py``），C2 效果行本身注册为空实现。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_CONTENT_VERSION,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
    ODETTE_SPLENDOR_REACTION_BONUS_PER_STACK,
    odette_splendor_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.modifiers import (
    OdetteP5AuthorityBonus,
    OdetteP5StellarAuthorityProvider,
    OdetteP6BaseBonus,
    OdetteP6StellarBaseBonusProvider,
)
from genshin_sim.content.characters.snezhnaya.odette.splendor import (
    OdetteSplendorAscensionProvider,
    OdetteSplendorReactionBonusProvider,
    build_splendor_buff_definition,
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
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.buff import BuffDefinition
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
            raise ContentUnitValidationError(f"{purpose} components 数值分量类型不符")
        values.append(float(value))
    return tuple(values)


def _component(params: Mapping[str, object], index: int, *, purpose: str) -> float:
    """按 0 基位置读取数值分量（sandrone 同款约定：``index=1`` 即 number_2）。"""

    values = _components(params, purpose=purpose)
    if index >= len(values):
        raise ContentUnitValidationError(f"{purpose} 缺少第 {index + 1} 个数值分量")
    return values[index]


def _effect_name(params: Mapping[str, object], *, position: str) -> str:
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
    damage_modifier_providers: tuple[DamageModifierProvider, ...] = (),
    buff_definitions: tuple[BuffDefinition, ...] = (),
    compiled_params: Mapping[str, JSONValue] | None = None,
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=ODETTE_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=kind,
                unlock=unlock,
                params=dict(request.params),
            ),
        ),
        damage_modifier_providers=damage_modifier_providers,
        buff_definitions=buff_definitions,
        compiled_params=dict(compiled_params or {}),
        metadata={"purpose": purpose},
    )


def read_p4_splendor_values(params: Mapping[str, object]) -> int:
    """解析 P4 效果行：召唤独舞倒影获得的华彩层数（number_2，number_1 为词条链接）。

    资产行原文「奥黛塔召唤独舞倒影时，还会获得4层华彩」——number_2 = 4。
    """

    purpose = "天赋「获选者的春祭」"
    grant_stacks = _component(params, 1, purpose=purpose)
    if grant_stacks != int(grant_stacks) or grant_stacks <= 0:
        raise ContentUnitValidationError(f"{purpose} 华彩发放层数必须是正整数")
    return int(grant_stacks)


def read_c1_splendor_values(params: Mapping[str, object]) -> tuple[int, int]:
    """解析 C1 效果行的华彩强化：额外叠层（number_5）与后台清除速度（number_7）。

    资产行原文「召唤独舞倒影时，奥黛塔将额外获得2层华彩，且奥黛塔处于队伍
    后台时，清除华彩的速度提升至每秒2层」——number_5 = 2、number_7 = 2
    （number_2/number_3 为 C1 追加段倍率，切片 6 消费）。
    """

    purpose = "命之座第1层 「不曾起舞的清晨，她望向倒影」"
    extra_stacks = _component(params, 4, purpose=purpose)
    clear_layers = _component(params, 6, purpose=purpose)
    if extra_stacks != int(extra_stacks) or extra_stacks <= 0:
        raise ContentUnitValidationError(f"{purpose} 华彩额外叠层数必须是正整数")
    if clear_layers != int(clear_layers) or clear_layers <= 0:
        raise ContentUnitValidationError(f"{purpose} 后台清除层数必须是正整数")
    return int(extra_stacks), int(clear_layers)


def read_c2_atk_per_stack(params: Mapping[str, object]) -> float:
    """解析 C2 效果行：每层华彩的攻击力提升（number_2，0.07）。"""

    purpose = "命之座第2层 「她想，我要见证雪鹄未见之梦」"
    atk_per_stack = _component(params, 1, purpose=purpose)
    if atk_per_stack <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 每层攻击力提升必须为正数")
    return atk_per_stack


def read_c6_ascension_values(params: Mapping[str, object]) -> tuple[float, float]:
    """解析 C6 效果行：持有者擢升（number_3 = 0.25）与奥黛塔额外擢升（number_4 = 0.2）。"""

    purpose = "命之座第6层 「伸出手，触及苍穹永恒的面容」"
    holder_bonus = _component(params, 2, purpose=purpose)
    self_extra_bonus = _component(params, 3, purpose=purpose)
    if holder_bonus < 0.0 or self_extra_bonus < 0.0:
        raise ContentUnitValidationError(f"{purpose} 星烁擢升不能为负数")
    return holder_bonus, self_extra_bonus


def read_p5_authority_bonus(params: Mapping[str, object]) -> OdetteP5AuthorityBonus:
    """解析 P5 效果行：起算攻击力（number_1 = 1000）、步长（number_2 = 100）、
    每档增伤（number_3 = 1.5%）、上限（number_4 = 30%）。

    资产行原文「基于奥黛塔攻击力超过1000点的部分，每100点攻击力都将使奥黛塔
    造成的星烁反应伤害额外造成原本1.5%的伤害，至多通过这种方式额外造成原本
    30%的伤害」——四个分量依次为上述四项，无前导链接编号。
    """

    purpose = "天赋「赤忱者的悲歌」"
    return OdetteP5AuthorityBonus(
        threshold_atk=_component(params, 0, purpose=purpose),
        per_100_atk=_component(params, 1, purpose=purpose),
        bonus_rate=_component(params, 2, purpose=purpose),
        cap=_component(params, 3, purpose=purpose),
    )


def read_p6_base_bonus(params: Mapping[str, object]) -> OdetteP6BaseBonus:
    """解析 P6 效果行：攻击力步长（number_3 = 100）、每档增伤（number_4 =
    0.7%）、上限（number_5 = 14%）。

    分量顺序与桑多涅 P6 同构：number_1 为文本内链接编号（极星辉域）、number_2
    为「触发星扩散反应后的 8 秒内」窗口秒数——两者分别由链接文本与机制侧
    （``STELLAR_SWIRL_RADIANCE_DURATION_FRAMES``）承载，内容侧不消费。
    """

    purpose = "天赋「星耀祝礼·银晓之舞」"
    return OdetteP6BaseBonus(
        per_100_atk=_component(params, 2, purpose=purpose),
        bonus_rate=_component(params, 3, purpose=purpose),
        cap=_component(params, 4, purpose=purpose),
    )


def create_odette_passive_p4(request: EffectContentUnitRequest) -> ContentUnit:
    """P4 获选者的春祭：华彩 Buff 定义 + 每层星烁增伤 provider。

    C2 命座强化（每层华彩再 +7% 攻击力）编译为华彩 Buff 的攻击力词条：
    经 owner_context 的命座取值门控，C2 行数值经 ``effect_params`` 读取
    （跨效果行机器耦合的唯一来源通道），C2 已解锁却缺行时直接失败。
    """

    slot = _validate_owner(request, ODETTE_PASSIVE_P4_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「获选者的春祭」")
    grant_stacks = read_p4_splendor_values(request.params)
    owner_ref = f"character:slot_{slot}"
    definition_key = odette_splendor_definition_key(slot)

    atk_per_stack: float | None = None
    if request.owner_context.constellation >= 2:
        c2_params = request.owner_context.effect_params.get("c2")
        if c2_params is None:
            raise ContentUnitValidationError("C2 已解锁但缺少资产效果行：c2")
        atk_per_stack = read_c2_atk_per_stack(c2_params)

    definition = build_splendor_buff_definition(
        slot,
        handler_key=ODETTE_PASSIVE_P4_HANDLER_KEY,
        display_name=f"{name}·华彩",
        atk_per_stack=atk_per_stack,
    )
    provider = OdetteSplendorReactionBonusProvider(
        owner_ref=owner_ref,
        definition_key=definition_key,
        bonus_per_stack=ODETTE_SPLENDOR_REACTION_BONUS_PER_STACK,
        source_key=ODETTE_PASSIVE_P4_HANDLER_KEY,
        display_name=f"{name}·华彩星烁增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_PASSIVE_P4_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 突破 1 阶（20 级突破）解锁。
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=1),
        purpose="odette_passive_p4_splendor",
        damage_modifier_providers=(provider,),
        buff_definitions=(definition,),
        compiled_params={
            "name": name,
            "definition_key": definition_key,
            "grant_stacks": grant_stacks,
            "atk_per_stack": atk_per_stack,
            "reaction_bonus_per_stack": ODETTE_SPLENDOR_REACTION_BONUS_PER_STACK,
        },
    )


def create_odette_passive_p5(request: EffectContentUnitRequest) -> ContentUnit:
    """P5 赤忱者的悲歌：攻击力超过起算值的部分按档提升自身星烁反应伤害。

    「额外造成原本 X% 的伤害」按 D-082 变更记录（2026-10-02）口径落在星烁
    大权区；provider 按伤害来源自筛为奥黛塔本人。突破 4 阶（60 级突破）解锁：
    静态门控在编译期按解锁条件过滤 provider（锁定命座/突破不影响伤害结算）。
    """

    slot = _validate_owner(request, ODETTE_PASSIVE_P5_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「赤忱者的悲歌」")
    owner_ref = f"character:slot_{slot}"
    provider = OdetteP5StellarAuthorityProvider(
        owner_ref=owner_ref,
        authority_bonus=read_p5_authority_bonus(request.params),
        source_key=ODETTE_PASSIVE_P5_HANDLER_KEY,
        display_name=f"{name}·星烁大权区加成",
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_PASSIVE_P5_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=4),
        purpose="odette_passive_p5_stellar_authority",
        damage_modifier_providers=(provider,),
    )


def create_odette_passive_p6(request: EffectContentUnitRequest) -> ContentUnit:
    """P6 星耀祝礼·银晓之舞：星烁基础增伤随奥黛塔攻击力折算（词条通道）。

    折算参数取自本条资产效果行；增伤数值在伤害结算期由 provider 按奥黛塔实时
    攻击力换算并署名（D-082），作用于全队造成的星烁反应伤害。星反应转换
    capability 随角色内容单元静态声明（固定天赋，见 ``content.py``）。
    """

    slot = _validate_owner(request, ODETTE_PASSIVE_P6_HANDLER_KEY)
    name = _effect_name(request.params, position="天赋「星耀祝礼·银晓之舞」")
    owner_ref = f"character:slot_{slot}"
    provider = OdetteP6StellarBaseBonusProvider(
        owner_ref=owner_ref,
        base_bonus=read_p6_base_bonus(request.params),
        source_key=ODETTE_PASSIVE_P6_HANDLER_KEY,
        display_name=f"{name}·星烁基础增伤",
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_PASSIVE_P6_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
        purpose="odette_passive_p6_stellar_base_bonus",
        damage_modifier_providers=(provider,),
    )


def create_odette_constellation_c6(request: EffectContentUnitRequest) -> ContentUnit:
    """C6：华彩持有者星烁反应伤害擢升 25%，奥黛塔额外擢升 20%（词条通道）。"""

    slot = _validate_owner(request, ODETTE_CONSTELLATION_C6_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第6层")
    holder_bonus, self_extra_bonus = read_c6_ascension_values(request.params)
    owner_ref = f"character:slot_{slot}"
    provider = OdetteSplendorAscensionProvider(
        owner_ref=owner_ref,
        definition_key=odette_splendor_definition_key(slot),
        holder_bonus=holder_bonus,
        self_extra_bonus=self_extra_bonus,
        source_key=ODETTE_CONSTELLATION_C6_HANDLER_KEY,
        display_name=f"{name}·华彩擢升",
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C6_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=6),
        purpose="odette_constellation_c6_splendor_ascension",
        damage_modifier_providers=(provider,),
        compiled_params={
            "name": name,
            "holder_bonus": holder_bonus,
            "self_extra_bonus": self_extra_bonus,
        },
    )
