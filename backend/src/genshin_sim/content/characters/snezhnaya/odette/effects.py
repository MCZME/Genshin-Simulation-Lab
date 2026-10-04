"""奥黛塔被动与命座效果单元工厂"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.odette.data import (
    FRAMES_PER_SECOND,
    ODETTE_C2_CONDUCT_VARIANT,
    ODETTE_C2_RESISTANCE_MECHANIC_KEY,
    ODETTE_C2_SWIRL_VARIANT,
    ODETTE_CONSTELLATION_C1_HANDLER_KEY,
    ODETTE_CONSTELLATION_C2_HANDLER_KEY,
    ODETTE_CONSTELLATION_C3_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_CONTENT_VERSION,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
    ODETTE_SPLENDOR_REACTION_BONUS_PER_STACK,
    odette_c2_resistance_definition_key,
    odette_splendor_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.hooks import (
    OdetteC2ResistanceHook,
    OdetteC4CoordinatedAttackHook,
    ResistanceAuraVariantSpec,
    compile_coordinated_attack_channel,
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
from genshin_sim.content.models import EventHook
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.core.attributes import (
    RESISTANCE_ANEMO,
    RESISTANCE_CRYO,
    RESISTANCE_ELECTRO,
    AttributeKey,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.damage import DamageModifierProvider

# 天赋等级框架上限：与 TalentLevelResolver.resolve 的 max_level 默认值一致；
# C3/C5 效果行自带的「至多提升至 15 级」在这里与框架核对（不一致时显式失败，
# 而不是静默按框架值截断）。
TALENT_LEVEL_CAP = 15


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
    event_hooks: tuple[EventHook, ...] = (),
    damage_modifier_providers: tuple[DamageModifierProvider, ...] = (),
    buff_definitions: tuple[BuffDefinition, ...] = (),
    talent_level_boosts: Mapping[str, int] | None = None,
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
        event_hooks=event_hooks,
        damage_modifier_providers=damage_modifier_providers,
        buff_definitions=buff_definitions,
        talent_level_boosts=dict(talent_level_boosts or {}),
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


@dataclass(frozen=True, slots=True)
class OdetteC1AssetValues:
    """C1 效果行的机器数值：追加段两档倍率 + 华彩强化。"""

    conduct_ratio: float
    swirl_ratio: float
    extra_stacks: int
    layers_per_tick: int


@dataclass(frozen=True, slots=True)
class OdetteC2AssetValues:
    """C2 效果行的机器数值：每层华彩攻击力提升 + 减抗光环幅度。"""

    atk_per_stack: float
    resistance_reduction: float


@dataclass(frozen=True, slots=True)
class OdetteC4AssetValues:
    """C4 效果行的机器数值：均摊比例 + 内置冷却 + 协同攻击两档倍率。"""

    share_ratio: float
    cooldown_frames: int
    conduct_ratio: float
    swirl_ratio: float


def read_c1_asset_values(params: Mapping[str, object]) -> OdetteC1AssetValues:
    """解析 C1 效果行：追加段倍率（number_2 = 300% 星超导 / number_3 = 450%
    星扩散）与华彩强化（number_5 = 额外 2 层、number_7 = 后台每秒 2 层）。

    资产行原文「…相当于奥黛塔攻击力300%的星超导反应伤害；…450%的星扩散反应
    伤害。此外…额外获得2层华彩，且…清除华彩的速度提升至每秒2层」。
    """

    purpose = "命之座第1层 「不曾起舞的清晨，她望向倒影」"
    conduct_ratio = _component(params, 1, purpose=purpose)
    swirl_ratio = _component(params, 2, purpose=purpose)
    extra_stacks = _component(params, 4, purpose=purpose)
    clear_layers = _component(params, 6, purpose=purpose)
    if conduct_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 追加段倍率必须为正数")
    if extra_stacks != int(extra_stacks) or extra_stacks <= 0:
        raise ContentUnitValidationError(f"{purpose} 华彩额外叠层数必须是正整数")
    if clear_layers != int(clear_layers) or clear_layers <= 0:
        raise ContentUnitValidationError(f"{purpose} 后台清除层数必须是正整数")
    return OdetteC1AssetValues(
        conduct_ratio=conduct_ratio,
        swirl_ratio=swirl_ratio,
        extra_stacks=int(extra_stacks),
        layers_per_tick=int(clear_layers),
    )


def read_c2_asset_values(params: Mapping[str, object]) -> OdetteC2AssetValues:
    """解析 C2 效果行：每层华彩攻击力提升（number_2 = 0.07）与减抗幅度
    （number_5 = 0.2）。"""

    purpose = "命之座第2层 「她想，我要见证雪鹄未见之梦」"
    atk_per_stack = _component(params, 1, purpose=purpose)
    resistance_reduction = _component(params, 4, purpose=purpose)
    if atk_per_stack <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 每层攻击力提升必须为正数")
    if not 0.0 < resistance_reduction <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 减抗幅度必须在 (0, 1] 区间")
    return OdetteC2AssetValues(
        atk_per_stack=atk_per_stack,
        resistance_reduction=resistance_reduction,
    )


def read_c4_asset_values(params: Mapping[str, object]) -> OdetteC4AssetValues:
    """解析 C4 效果行：均摊比例（number_1 = 0.5）、内置冷却秒数（number_2 =
    3.5）、协同攻击两档倍率（number_3 = 66% 星超导 / number_4 = 99% 星扩散）。"""

    purpose = "命之座第4层 「向上，坠往恍惚、燃烧的蓝空」"
    share_ratio = _component(params, 0, purpose=purpose)
    cooldown_seconds = _component(params, 1, purpose=purpose)
    conduct_ratio = _component(params, 2, purpose=purpose)
    swirl_ratio = _component(params, 3, purpose=purpose)
    if not 0.0 < share_ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 均摊比例必须在 (0, 1] 区间")
    if cooldown_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 协同攻击内置冷却必须为正数秒")
    if conduct_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 协同攻击倍率必须为正数")
    return OdetteC4AssetValues(
        share_ratio=share_ratio,
        cooldown_frames=round(cooldown_seconds * FRAMES_PER_SECOND),
        conduct_ratio=conduct_ratio,
        swirl_ratio=swirl_ratio,
    )


def read_talent_level_boost(params: Mapping[str, object]) -> tuple[int, int]:
    """解析 C3/C5 效果行：天赋等级提升（number_2 = 3）与提升上限（number_3 = 15）。

    上限分量按框架的能力上限核对：``TalentLevelResolver`` 默认 ``max_level``
    为 15，行内上限与之一致（不一致时由内容侧显式失败，而不是静默按 15 截断）。
    """

    purpose = "命之座天赋等级提升"
    boost = _component(params, 1, purpose=purpose)
    cap = _component(params, 2, purpose=purpose)
    if boost != int(boost) or boost <= 0:
        raise ContentUnitValidationError(f"{purpose} 天赋等级提升必须是正整数")
    if cap != int(cap) or cap <= 0:
        raise ContentUnitValidationError(f"{purpose} 天赋等级上限必须是正整数")
    if int(cap) != TALENT_LEVEL_CAP:
        raise ContentUnitValidationError(
            f"{purpose} 天赋等级上限 {int(cap)} 与框架上限 {TALENT_LEVEL_CAP} 不一致"
        )
    return int(boost), int(cap)


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
        atk_per_stack = read_c2_asset_values(c2_params).atk_per_stack

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
    """P5 赤忱者的悲歌：攻击力超过起算值的部分按档提升自身星烁反应伤害。"""

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
    """P6 星耀祝礼·银晓之舞：星烁基础增伤随奥黛塔攻击力折算（词条通道）。"""

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


def create_odette_constellation_c1(request: EffectContentUnitRequest) -> ContentUnit:
    """C1 追加段与华彩强化：解析并核对效果行（两段机器数值由各自的拥有者编译）。

    追加段（星超导 300% / 星扩散 450%、共舞结束时追加）由角色单元按本行倍率
    编译进影响工厂；华彩强化（额外 +2 层、后台清除 2 层/秒）由角色单元传给
    华彩发放与衰减 hook。本条单元因此只做读数、校验与审计记录。
    """

    _validate_owner(request, ODETTE_CONSTELLATION_C1_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第1层")
    values = read_c1_asset_values(request.params)
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C1_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=1),
        purpose="odette_constellation_c1_extra_segment",
        compiled_params={
            "name": name,
            "conduct_ratio": values.conduct_ratio,
            "swirl_ratio": values.swirl_ratio,
            "extra_stacks": values.extra_stacks,
            "layers_per_tick": values.layers_per_tick,
        },
    )


def _build_c2_resistance_aura(
    slot: int,
    *,
    reduction: float,
    handler_key: str,
    display_name: str,
) -> tuple[tuple[BuffDefinition, ...], dict[str, ResistanceAuraVariantSpec]]:
    """编译 C2 两个变体的减抗 Buff 定义与 hook 侧申请参数。

    变体按辉映状态区分（星超导：冰+雷；星扩散：冰+风），各自一个定义键：
    APPLY_STATUS 要求 ``modifier_values`` 与定义模板完整匹配，合成单一定义
    会让另一元素的零值词条进入目标账本。词条值为 ``-reduction``（抗性区
    FLAT_ADD，有效抗性 = 面板值 + Σ）。
    """

    elements_by_variant = {
        ODETTE_C2_CONDUCT_VARIANT: (RESISTANCE_CRYO, RESISTANCE_ELECTRO),
        ODETTE_C2_SWIRL_VARIANT: (RESISTANCE_CRYO, RESISTANCE_ANEMO),
    }
    definitions: list[BuffDefinition] = []
    variants: dict[str, ResistanceAuraVariantSpec] = {}
    variant_labels = {
        ODETTE_C2_CONDUCT_VARIANT: "星超导",
        ODETTE_C2_SWIRL_VARIANT: "星扩散",
    }
    for variant in (ODETTE_C2_CONDUCT_VARIANT, ODETTE_C2_SWIRL_VARIANT):
        term_keys_by_element = {
            element: _c2_resistance_term_key(variant, element)
            for element in elements_by_variant[variant]
        }
        definition_key = odette_c2_resistance_definition_key(slot, variant)
        definitions.append(
            BuffDefinition(
                definition_key=definition_key,
                mechanic_key=ODETTE_C2_RESISTANCE_MECHANIC_KEY,
                handler_key=handler_key,
                conflict_key=definition_key,
                target_kinds=frozenset({AttributeSubjectKind.TARGET}),
                application_policy=BuffApplicationPolicy.REFRESH,
                value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
                max_stacks=1,
                attribute_modifiers=tuple(
                    BuffAttributeModifierTemplate(
                        term_key=term_key,
                        target_key=element,
                        stage=ModifierStage.FLAT_ADD,
                    )
                    for element, term_key in term_keys_by_element.items()
                ),
                display_name=f"{display_name}·{variant_labels[variant]}减抗",
            )
        )
        variants[variant] = ResistanceAuraVariantSpec(
            definition_key=definition_key,
            modifier_values=tuple(
                {"term_key": term_key, "value": -reduction}
                for term_key in term_keys_by_element.values()
            ),
        )
    return tuple(definitions), variants


def _c2_resistance_term_key(variant: str, element: AttributeKey) -> str:
    """C2 减抗词条键：按变体与元素区分（审计与模板一对一）。"""

    element_key = element.value.removeprefix("resistance.")
    return f"{ODETTE_C2_RESISTANCE_MECHANIC_KEY}.{variant}.{element_key}"


def create_odette_constellation_c2(request: EffectContentUnitRequest) -> ContentUnit:
    """C2 减抗光环：两个变体的减抗 Buff 定义 + 每 60 帧的判定 hook。

    每层华彩的 +7% 攻击力由 P4 工厂编译进华彩 Buff 词条（见 ``splendor.py``），
    本条单元只承载光环部分。
    """

    slot = _validate_owner(request, ODETTE_CONSTELLATION_C2_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第2层")
    values = read_c2_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    definitions, variants = _build_c2_resistance_aura(
        slot,
        reduction=values.resistance_reduction,
        handler_key=ODETTE_CONSTELLATION_C2_HANDLER_KEY,
        display_name=name,
    )
    hook = OdetteC2ResistanceHook(
        owner_ref=owner_ref,
        slot=slot,
        variants=variants,
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C2_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=2),
        purpose="odette_constellation_c2_resistance_aura",
        event_hooks=(hook,),
        buff_definitions=definitions,
        compiled_params={
            "name": name,
            "atk_per_stack": values.atk_per_stack,
            "resistance_reduction": values.resistance_reduction,
            "definition_keys": {
                variant: spec.definition_key for variant, spec in sorted(variants.items())
            },
        },
    )


def create_odette_constellation_c3(request: EffectContentUnitRequest) -> ContentUnit:
    """C3：元素战技天赋等级 +3（至多 15，上限由天赋框架承担）。"""

    _validate_owner(request, ODETTE_CONSTELLATION_C3_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第3层")
    boost, cap = read_talent_level_boost(request.params)
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C3_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=3),
        purpose="odette_constellation_c3_talent_boost",
        talent_level_boosts={"elemental_skill": boost},
        compiled_params={"name": name, "boost": boost, "cap": cap},
    )


def create_odette_constellation_c4(request: EffectContentUnitRequest) -> ContentUnit:
    """C4：协同攻击 hook（触发后延迟 5f、内置冷却取本行秒数）。

    「雪鹄之梦均摊」需要元素爆发表里的雪鹄之梦数值，由角色单元按有效 Q 等级
    编译并门控（见 ``content.py`` 与 ``dream.py``），本条单元只承载协同攻击。
    """

    slot = _validate_owner(request, ODETTE_CONSTELLATION_C4_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第4层")
    values = read_c4_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    hook = OdetteC4CoordinatedAttackHook(
        owner_ref=owner_ref,
        slot=slot,
        channel=compile_coordinated_attack_channel(
            conduct_ratio=values.conduct_ratio,
            swirl_ratio=values.swirl_ratio,
        ),
        cooldown_frames=values.cooldown_frames,
    )
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C4_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=4),
        purpose="odette_constellation_c4_coordinated_attack",
        event_hooks=(hook,),
        compiled_params={
            "name": name,
            "share_ratio": values.share_ratio,
            "cooldown_frames": values.cooldown_frames,
            "conduct_ratio": values.conduct_ratio,
            "swirl_ratio": values.swirl_ratio,
        },
    )


def create_odette_constellation_c5(request: EffectContentUnitRequest) -> ContentUnit:
    """C5：元素爆发天赋等级 +3（至多 15，上限由天赋框架承担）。"""

    _validate_owner(request, ODETTE_CONSTELLATION_C5_HANDLER_KEY)
    name = _effect_name(request.params, position="命之座第5层")
    boost, cap = read_talent_level_boost(request.params)
    return _effect_unit(
        request=request,
        handler_key=ODETTE_CONSTELLATION_C5_HANDLER_KEY,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=5),
        purpose="odette_constellation_c5_talent_boost",
        talent_level_boosts={"elemental_burst": boost},
        compiled_params={"name": name, "boost": boost, "cap": cap},
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
