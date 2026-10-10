"""砂糖固有天赋效果单元工厂。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_C2_EXTRA_SECONDS,
    SUCROSE_C6_BUFF_DEFINITION_KEY,
    SUCROSE_C6_MAGE_ENHANCEMENT_BONUS,
    SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_TALENT_FRAMES_PER_SECOND,
    SUCROSE_TALENT_LEVEL_CAP,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseC4HitCounterHook,
    SucroseC6AbsorbedBonusHook,
    SucroseCatalystConversionHook,
    SucroseMollisFavoniusHook,
    SucroseWitchesEveLargeSpiritHook,
    SucroseWitchesEveSmallSpiritHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    SucroseWitchesEveDamageBonusProvider,
    build_a1_mastery_buff_definition,
    build_a4_mastery_buff_definition,
    build_c6_damage_bonus_buff_definition,
    build_c6_mage_enhancement_buff_definition,
    build_witches_eve_large_buff_definition,
    build_witches_eve_small_buff_definition,
)
from genshin_sim.content.characters.mondstadt.sucrose.spirit import resolve_spirit_timing
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
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.buff import BuffDefinition


def _is_value_sequence(value: object) -> TypeGuard[Sequence[object]]:
    """非字符串 / 字节的序列：分量序列与分量的 ``values`` 共用同一判据。"""

    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _component_value(component: object, *, index: int, purpose: str) -> float:
    """取单个分量的首值（``values[0]``）；结构不符或非数字时失败。"""

    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
    raw_values = component.get("values")
    if not _is_value_sequence(raw_values) or not raw_values:
        raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
    value = raw_values[0]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
    return float(value)


def _components(
    params: Mapping[str, object],
    *,
    purpose: str,
    count: int | None = None,
    skipped: int = 0,
) -> tuple[float, ...]:
    """读取资产效果行的 ``components`` 数值序列（每个分量取 ``values[0]``）。

    ``count`` 给定时要求分量数**恰好**为该值——位置到含义的映射才不至于是隐式的；
    ``skipped`` 是开头按位置消费却不取值的分量数，这些分量只参与计数，形状与数值
    都不校验（例如前夜礼的门槛人数由 ``MageRoster`` 判定，效果包不替它建模）。
    """

    components = params.get("components")
    if not _is_value_sequence(components) or not components:
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    if count is not None and len(components) != count:
        raise ContentUnitValidationError(
            f"{purpose} 分量数不符：需要 {count} 个，实得 {len(components)}"
        )
    return tuple(
        _component_value(component, index=index, purpose=purpose)
        for index, component in enumerate(components)
        if index >= skipped
    )


def _effect_name(params: Mapping[str, object], *, purpose: str) -> str:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContentUnitValidationError(f"{purpose} 的资产效果行缺少名称")
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
    unlock: UnlockSpec,
    purpose: str,
    kind: EffectKind,
    event_hooks: tuple[EventHook, ...],
    buff_definitions: tuple[BuffDefinition, ...],
    compiled_params: Mapping[str, JSONValue],
    damage_modifier_providers: tuple[SucroseWitchesEveDamageBonusProvider, ...] = (),
    talent_level_boosts: Mapping[str, int] | None = None,
) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.owner_key,
        handler_key=handler_key,
        version=SUCROSE_CONTENT_VERSION,
        slot=request.slot,
        effects=(
            EffectSpec(
                effect_key=request.effect_key,
                kind=kind,
                unlock=unlock,
                params=dict(request.params),
            ),
        ),
        talent_level_boosts=dict(talent_level_boosts or {}),
        event_hooks=event_hooks,
        buff_definitions=buff_definitions,
        damage_modifier_providers=damage_modifier_providers,
        compiled_params=dict(compiled_params),
        metadata={"purpose": purpose},
    )


def read_a1_asset_values(params: Mapping[str, object]) -> tuple[float, int]:
    """解析 A1 效果行：精通加成值与持续秒数（``number_1`` / ``number_2``）。"""

    purpose = "天赋「触媒置换术」"
    mastery_flat, duration_seconds = _components(params, purpose=purpose)
    if mastery_flat <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 精通加成值必须为正数")
    if duration_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 持续时间必须为正数")
    return mastery_flat, round(duration_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND)


def read_a4_asset_values(params: Mapping[str, object]) -> tuple[float, int]:
    """解析 A4 效果行：精通折算比例与持续秒数（``number_1`` / ``number_2``）。"""

    purpose = "天赋「小小的慧风」"
    ratio, duration_seconds = _components(params, purpose=purpose)
    if not 0.0 < ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 精通折算比例必须在 (0, 1] 区间")
    if duration_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 持续时间必须为正数")
    return ratio, round(duration_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND)


def read_constellation_components(
    params: Mapping[str, object],
    *,
    purpose: str,
) -> tuple[float, ...]:
    """读取命座效果行的 ``components`` 数值序列。

    命座行的分量含义逐层不同（``c1 = [次数]``、``c2 = [秒]``、``c3 / c5 =
    [等级, 上限]``、``c4 = [次数, 下限, 上限, 计次秒]``、``c6 = [比例]``），
    故这里只做「取数」，各层的语义校验在该层的读取函数里做。角色单元也用它
    按命座取静态切片值（C1 充能数、C2 延长秒数）。
    """

    return _components(params, purpose=purpose)


def read_witches_eve_asset_values(
    params: Mapping[str, object],
) -> tuple[int, float, int, float]:
    """解析 ``passive:9`` 效果行：两档秒数与比例（``number_2`` … ``number_5``）。

    分量依次为 ``[门槛人数, 小型档秒数, 小型档比例, 大型档秒数, 大型档比例]``。
    **门槛人数不在此读入**——「魔导·秘仪」是否激活由 ``content/team/mage.py`` 的
    ``MageRoster`` 按共享常量判定，属**资格**而非砂糖的效果，效果包不替它建模；
    故第 1 个分量按位置消费后即丢弃，其形状与数值都不校验。两档比例必须在
    (0, 1] 区间、两个秒数必须为正数。
    """

    purpose = "天赋「魔女的前夜礼·七循之理」"
    small_seconds, small_ratio, large_seconds, large_ratio = _components(
        params, purpose=purpose, count=5, skipped=1
    )
    if not 0.0 < small_ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 小型风灵档增伤比例必须在 (0, 1] 区间")
    if not 0.0 < large_ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 大型风灵档增伤比例必须在 (0, 1] 区间")
    if small_seconds <= 0.0 or large_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 两档持续时间都必须为正数")
    return (
        round(small_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND),
        small_ratio,
        round(large_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND),
        large_ratio,
    )


def _constellation_effect_unit(
    *,
    request: EffectContentUnitRequest,
    handler_key: str,
    threshold: int,
    purpose: str,
    compiled_params: Mapping[str, JSONValue],
    event_hooks: tuple[EventHook, ...] = (),
    buff_definitions: tuple[BuffDefinition, ...] = (),
    talent_level_boosts: Mapping[str, int] | None = None,
) -> ContentUnit:
    """命座效果单元骨架：解锁阈值为层号，其余与被动同形。"""

    return _effect_unit(
        request=request,
        handler_key=handler_key,
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=threshold),
        purpose=purpose,
        event_hooks=event_hooks,
        buff_definitions=buff_definitions,
        compiled_params=compiled_params,
        talent_level_boosts=talent_level_boosts,
    )


def create_sucrose_constellation_c1(request: EffectContentUnitRequest) -> ContentUnit:
    """C1 堆叠真空域：元素战技的可使用次数 +1。

    可用次数只能由**冷却定义**承载（``max_charges`` + 独立恢复），内容侧没有
    「充能」动态通道，故本单元只负责读资产行、校验数值并登记编译参数；真正的
    切片由角色单元在编译期按命座产出（见 ``content.py``）。留一条单元是为了让
    这条资产行有明确归属。
    """

    _validate_owner(request, SUCROSE_CONSTELLATION_C1_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第1层")
    extra_charges = _read_single_int(request.params, purpose="命之座第1层")
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
        threshold=1,
        purpose="sucrose_constellation_c1_extra_charge",
        compiled_params={"name": name, "extra_charges": extra_charges},
    )


def create_sucrose_constellation_c2(request: EffectContentUnitRequest) -> ContentUnit:
    """C2 不羁型贝特：元素爆发的技能持续时间延长 2 秒（6s → 8s，3 拍 → 4 拍）。

    与 C1 同理：创建物时长是编译期静态切片，由角色单元按命座产出；本单元读
    资产行并登记秒数（拍数与生命周期由 ``resolve_spirit_timing`` 同源派生）。
    """

    _validate_owner(request, SUCROSE_CONSTELLATION_C2_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第2层")
    extra_seconds = _read_single_int(request.params, purpose="命之座第2层")
    window, duration, ticks = resolve_spirit_timing(extra_seconds)
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
        threshold=2,
        purpose="sucrose_constellation_c2_burst_duration",
        compiled_params={
            "name": name,
            "extra_seconds": extra_seconds,
            "window_frames": window,
            "duration_frames": duration,
            "tick_count": ticks,
        },
    )


def create_sucrose_constellation_c3(request: EffectContentUnitRequest) -> ContentUnit:
    """C3 零失误少女：元素战技天赋等级 +3（至多 15 级）。"""

    _validate_owner(request, SUCROSE_CONSTELLATION_C3_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第3层")
    boost, cap = _read_talent_level_boost(request.params, purpose="命之座第3层")
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
        threshold=3,
        purpose="sucrose_constellation_c3_talent_boost",
        compiled_params={"name": name, "boost": boost, "cap": cap},
        talent_level_boosts={"elemental_skill": boost},
    )


def create_sucrose_constellation_c4(request: EffectContentUnitRequest) -> ContentUnit:
    """C4 炼金的偏执：普攻 / 重击累计命中敌人 7 次 → 战技冷却随机减 1–7 秒。

    资产 ``c4 = [7, 1, -7, 0.1]``：命中次数、减少秒数下限、上限（以负值表示
    「减少」，故取绝对值）、计次间隔秒数。计次与减冷却都由 hook 承担：
    减冷却走**运行期冷却意图**（``CooldownMutationBatchRequest``），不是编译期
    时长 term——随机值只能在触发帧决定。
    """

    slot = _validate_owner(request, SUCROSE_CONSTELLATION_C4_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第4层")
    hit_count, min_seconds, max_seconds, interval_frames = _read_c4_values(request.params)
    hook = SucroseC4HitCounterHook(
        owner_ref=f"character:slot_{slot}",
        slot=slot,
        hit_count=hit_count,
        min_reduction_seconds=min_seconds,
        max_reduction_seconds=max_seconds,
        count_interval_frames=interval_frames,
    )
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
        threshold=4,
        purpose="sucrose_constellation_c4_cooldown_reduction",
        event_hooks=(hook,),
        compiled_params={
            "name": name,
            "hit_count": hit_count,
            "min_reduction_seconds": min_seconds,
            "max_reduction_seconds": max_seconds,
            "count_interval_frames": interval_frames,
        },
    )


def create_sucrose_constellation_c5(request: EffectContentUnitRequest) -> ContentUnit:
    """C5 认真普通瓶：元素爆发天赋等级 +3（至多 15 级）。"""

    _validate_owner(request, SUCROSE_CONSTELLATION_C5_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第5层")
    boost, cap = _read_talent_level_boost(request.params, purpose="命之座第5层")
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
        threshold=5,
        purpose="sucrose_constellation_c5_talent_boost",
        compiled_params={"name": name, "boost": boost, "cap": cap},
        talent_level_boosts={"elemental_burst": boost},
    )


def create_sucrose_constellation_c6(request: EffectContentUnitRequest) -> ContentUnit:
    """C6 混元熵增论：爆发发生元素转化 → 全队（含砂糖）对应元素伤害加成。

    持续时间为**爆发持续时间**：C2 延长后随之变为 8s，故按归属上下文里的命座
    数取延长秒数、经 ``resolve_spirit_timing`` 得到生命周期，与本体的窗口保持
    同一真值。

    同时登记**魔导增强**的 Buff 定义：魔导·秘仪激活时由本 hook 对魔导角色额外
    投放 +8.57142%。
    """

    slot = _validate_owner(request, SUCROSE_CONSTELLATION_C6_HANDLER_KEY)
    name = _effect_name(request.params, purpose="命之座第6层")
    bonus = _read_single_ratio(request.params, purpose="命之座第6层")
    extra_seconds = 0
    if request.owner_context.constellation >= 2:
        extra_seconds = SUCROSE_C2_EXTRA_SECONDS
    duration_frames = resolve_spirit_timing(extra_seconds)[1]
    hook = SucroseC6AbsorbedBonusHook(
        owner_ref=f"character:slot_{slot}",
        slot=slot,
        damage_bonus=bonus,
        duration_frames=duration_frames,
    )
    return _constellation_effect_unit(
        request=request,
        handler_key=SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
        threshold=6,
        purpose="sucrose_constellation_c6_elemental_damage_bonus",
        event_hooks=(hook,),
        buff_definitions=(
            build_c6_damage_bonus_buff_definition(),
            build_c6_mage_enhancement_buff_definition(),
        ),
        compiled_params={
            "name": name,
            "damage_bonus": bonus,
            "duration_frames": duration_frames,
            "mage_enhancement_bonus": SUCROSE_C6_MAGE_ENHANCEMENT_BONUS,
            "buff_definition_key": SUCROSE_C6_BUFF_DEFINITION_KEY,
            "mage_enhancement_definition_key": (SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY),
        },
    )


def _read_single_int(params: Mapping[str, object], *, purpose: str) -> int:
    """取命座行的单个正整数分量（``c1`` / ``c2``）。"""

    values = read_constellation_components(params, purpose=purpose)
    value = round(values[0])
    if value <= 0:
        raise ContentUnitValidationError(f"{purpose} 数值必须为正整数")
    return value


def _read_single_ratio(params: Mapping[str, object], *, purpose: str) -> float:
    """取命座行的单个比例分量（``c6``，落在 (0, 1]）。"""

    values = read_constellation_components(params, purpose=purpose)
    ratio = values[0]
    if not 0.0 < ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 增伤比例必须在 (0, 1] 区间")
    return ratio


def _read_talent_level_boost(params: Mapping[str, object], *, purpose: str) -> tuple[int, int]:
    """取命座行的「等级提升 / 上限」两个分量（``c3`` / ``c5``）。

    上限分量与框架的 ``TalentLevelResolver`` 默认 ``max_level``（=15）核对：
    不一致时由内容侧显式失败，而不是静默按框架值截断。
    """

    values = read_constellation_components(params, purpose=purpose)
    if len(values) < 2:
        raise ContentUnitValidationError(f"{purpose} 资产效果行缺少等级上限分量")
    boost = round(values[0])
    cap = round(values[1])
    if boost <= 0:
        raise ContentUnitValidationError(f"{purpose} 等级提升必须为正整数")
    if cap < boost:
        raise ContentUnitValidationError(f"{purpose} 等级上限不得低于提升值")
    if cap != SUCROSE_TALENT_LEVEL_CAP:
        raise ContentUnitValidationError(
            f"{purpose} 天赋等级上限 {cap} 与框架上限 {SUCROSE_TALENT_LEVEL_CAP} 不一致"
        )
    return boost, cap


def _read_c4_values(params: Mapping[str, object]) -> tuple[int, int, int, int]:
    """取 ``c4`` 的四个分量：命中次数 / 减冷却秒数区间 / 计次间隔帧数。

    以负数表示「减少」（``1 / -7``），故上限取绝对值；计次间隔给的是秒数
    （0.1），这里换算为帧。
    """

    purpose = "命之座第4层"
    values = read_constellation_components(params, purpose=purpose)
    if len(values) < 4:
        raise ContentUnitValidationError(f"{purpose} 资产效果行缺少计次间隔分量")
    hit_count = round(values[0])
    min_seconds = round(values[1])
    max_seconds = round(abs(values[2]))
    interval_seconds = values[3]
    if hit_count <= 0:
        raise ContentUnitValidationError(f"{purpose} 命中次数必须为正整数")
    if min_seconds <= 0 or max_seconds <= 0 or min_seconds > max_seconds:
        raise ContentUnitValidationError(f"{purpose} 减冷却秒数区间非法")
    if interval_seconds < 0:
        raise ContentUnitValidationError(f"{purpose} 计次间隔秒数必须非负")
    return (
        hit_count,
        min_seconds,
        max_seconds,
        round(interval_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND),
    )


def create_sucrose_passive_a1(request: EffectContentUnitRequest) -> ContentUnit:
    """A1 触媒置换术：扩散 / 星扩散触发，与被扩散元素同元素的队友 +50 精通 8s。"""

    slot = _validate_owner(request, SUCROSE_PASSIVE_A1_HANDLER_KEY)
    name = _effect_name(request.params, purpose="天赋「触媒置换术」")
    mastery_flat, duration_frames = read_a1_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    hook = SucroseCatalystConversionHook(
        owner_ref=owner_ref,
        slot=slot,
        duration_frames=duration_frames,
        mastery_flat=mastery_flat,
    )
    definition = build_a1_mastery_buff_definition()
    return _effect_unit(
        request=request,
        handler_key=SUCROSE_PASSIVE_A1_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 突破 1 阶解锁。
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=1),
        purpose="sucrose_passive_a1_catalyst_conversion",
        event_hooks=(hook,),
        buff_definitions=(definition,),
        compiled_params={
            "name": name,
            "mastery_flat": mastery_flat,
            "duration_frames": duration_frames,
            "buff_definition_key": definition.definition_key,
        },
    )


def create_sucrose_passive_a4(request: EffectContentUnitRequest) -> ContentUnit:
    """A4 小小的慧风：E / Q 命中敌人，全队（除砂糖）按砂糖快照精通 20% +精通 8s。"""

    slot = _validate_owner(request, SUCROSE_PASSIVE_A4_HANDLER_KEY)
    name = _effect_name(request.params, purpose="天赋「小小的慧风」")
    ratio, duration_frames = read_a4_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    hook = SucroseMollisFavoniusHook(
        owner_ref=owner_ref,
        slot=slot,
        ratio=ratio,
        duration_frames=duration_frames,
    )
    definition = build_a4_mastery_buff_definition()
    return _effect_unit(
        request=request,
        handler_key=SUCROSE_PASSIVE_A4_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        # 突破 4 阶解锁。
        unlock=UnlockSpec(kind=UnlockKind.ASCENSION, threshold=4),
        purpose="sucrose_passive_a4_mollis_favonius",
        event_hooks=(hook,),
        buff_definitions=(definition,),
        compiled_params={
            "name": name,
            "mastery_ratio": ratio,
            "duration_frames": duration_frames,
            "buff_definition_key": definition.definition_key,
        },
    )


def create_sucrose_passive_witches_eve(request: EffectContentUnitRequest) -> ContentUnit:
    """魔女的前夜礼·七循之理（``passive:9``）：魔导·秘仪下的两档五类伤害加成。

    两档都以队伍魔导角色数达到门槛为前提，由两个 hook 在各自的召唤时点投放
    标记 Buff（小型档投全队、大型档投魔导角色），数值由两个伤害 provider 按
    标记存在性贡献——作用面是五类**伤害**，不经过属性系统。

    解锁按 ``ALWAYS``：「完成魔女的课业」视为默认已完成、不作为仿真输入项；
    是否生效由队伍魔导角色数在运行期判断。
    """

    slot = _validate_owner(request, SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY)
    name = _effect_name(request.params, purpose="天赋「魔女的前夜礼·七循之理」")
    (
        small_duration_frames,
        small_bonus,
        large_duration_frames,
        large_bonus,
    ) = read_witches_eve_asset_values(request.params)
    owner_ref = f"character:slot_{slot}"
    small_hook = SucroseWitchesEveSmallSpiritHook(
        owner_ref=owner_ref,
        slot=slot,
        duration_frames=small_duration_frames,
    )
    large_hook = SucroseWitchesEveLargeSpiritHook(
        owner_ref=owner_ref,
        slot=slot,
        duration_frames=large_duration_frames,
    )
    small_definition = build_witches_eve_small_buff_definition()
    large_definition = build_witches_eve_large_buff_definition()
    return _effect_unit(
        request=request,
        handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
        kind=EffectKind.PASSIVE,
        unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
        purpose="sucrose_passive_witches_eve_rite",
        event_hooks=(small_hook, large_hook),
        buff_definitions=(small_definition, large_definition),
        damage_modifier_providers=(
            SucroseWitchesEveDamageBonusProvider(
                owner_ref=owner_ref,
                scope_key="small",
                buff_definition_key=small_definition.definition_key,
                bonus=small_bonus,
                display_name="魔女的前夜礼·小型风灵五类增伤",
            ),
            SucroseWitchesEveDamageBonusProvider(
                owner_ref=owner_ref,
                scope_key="large",
                buff_definition_key=large_definition.definition_key,
                bonus=large_bonus,
                display_name="魔女的前夜礼·大型风灵五类增伤",
            ),
        ),
        compiled_params={
            "name": name,
            "small_duration_frames": small_duration_frames,
            "small_bonus": small_bonus,
            "large_duration_frames": large_duration_frames,
            "large_bonus": large_bonus,
            "small_buff_definition_key": small_definition.definition_key,
            "large_buff_definition_key": large_definition.definition_key,
        },
    )
