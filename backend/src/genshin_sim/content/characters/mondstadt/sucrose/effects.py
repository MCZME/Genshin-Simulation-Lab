"""砂糖固有天赋效果单元工厂（A1 / A4 / 魔女的前夜礼）。

效果工厂只负责组装：把资产 ``passive:4`` / ``passive:5`` / ``passive:9`` 效果
行的数值读入、校验并编译为 ContentUnit 的行为切片（``event_hooks``、
``buff_definitions`` 与 ``damage_modifier_providers``）。行为实现见
``hooks.py``（触发判定与投放）与 ``modifiers.py``（Buff 定义与伤害 provider）。

数值口径：加成数值与持续时间取**资产效果行**（``components``），内容侧不复制
一份平行常量；``data.py`` 的常量只在资产缺行时作为 hook 构造的默认值与测试
基准使用。A4 的折算比例只允许落在 (0, 1] 区间——组件错位（文本序号、持续秒数
混入比例位）会在此处失败，而不是静默折算出近零精通加成。

``passive:9``「魔女的前夜礼·七循之理」的 components 为
``[2, 15, 5.71428%, 20, 7.14285%]``，依次为魔导·秘仪门槛人数、小型风灵档
秒数与比例、大型风灵档秒数与比例；门槛人数与判定口径一致时以资产为准
（名录判定仍走 ``content/team/witches_eve.py`` 的常量，两处不一致会在此报错）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_TALENT_FRAMES_PER_SECOND,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseCatalystConversionHook,
    SucroseMollisFavoniusHook,
    SucroseWitchesEveLargeSpiritHook,
    SucroseWitchesEveSmallSpiritHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    SucroseWitchesEveDamageBonusProvider,
    build_a1_mastery_buff_definition,
    build_a4_mastery_buff_definition,
    build_witches_eve_large_buff_definition,
    build_witches_eve_small_buff_definition,
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
from genshin_sim.content.team.witches_eve import MAGE_ACTIVATION_THRESHOLD
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.systems.buff import BuffDefinition


def _components(params: Mapping[str, object], *, purpose: str) -> tuple[float, ...]:
    """读取资产效果行的 ``components`` 数值序列（每个分量取 ``values[0]``）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or not components
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes, bytearray))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        values.append(float(value))
    return tuple(values)


def _effect_name(params: Mapping[str, object], *, purpose: str) -> str:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ContentUnitValidationError(f"{purpose} 的资产效果行缺少名称")
    return name.strip()


def _validate_owner(request: EffectContentUnitRequest, handler_key: str) -> int:
    if request.owner_key != SUCROSE_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{handler_key} 效果 handler 只接受砂糖资产：{request.owner_key}"
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
    event_hooks: tuple[EventHook, ...],
    buff_definitions: tuple[BuffDefinition, ...],
    compiled_params: Mapping[str, JSONValue],
    damage_modifier_providers: tuple[SucroseWitchesEveDamageBonusProvider, ...] = (),
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
                kind=EffectKind.PASSIVE,
                unlock=unlock,
                params=dict(request.params),
            ),
        ),
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


def read_witches_eve_asset_values(
    params: Mapping[str, object],
) -> tuple[int, int, float, int, float]:
    """解析 ``passive:9`` 效果行：门槛人数 / 小型档秒数与比例 / 大型档秒数与比例。

    五个分量依次对应 ``number_1`` … ``number_5``（``[2, 15, 5.71428%, 20,
    7.14285%]``）。两档比例必须为正数、两个秒数必须为正数、门槛必须 ≥2；
    资产门槛与内容侧名录判定的门槛不一致时直接失败，避免「激活判据两套真值」。
    """

    purpose = "天赋「魔女的前夜礼·七循之理」"
    min_mage_count, small_seconds, small_ratio, large_seconds, large_ratio = _components(
        params, purpose=purpose
    )
    if min_mage_count < 2.0:
        raise ContentUnitValidationError(f"{purpose} 魔导·秘仪门槛人数必须不少于 2")
    if min_mage_count != float(MAGE_ACTIVATION_THRESHOLD):
        raise ContentUnitValidationError(
            f"{purpose} 魔导·秘仪门槛人数（{min_mage_count:g}）与名录判定门槛"
            f"（{MAGE_ACTIVATION_THRESHOLD}）不一致"
        )
    if not 0.0 < small_ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 小型风灵档增伤比例必须在 (0, 1] 区间")
    if not 0.0 < large_ratio <= 1.0:
        raise ContentUnitValidationError(f"{purpose} 大型风灵档增伤比例必须在 (0, 1] 区间")
    if small_seconds <= 0.0 or large_seconds <= 0.0:
        raise ContentUnitValidationError(f"{purpose} 两档持续时间都必须为正数")
    return (
        round(min_mage_count),
        round(small_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND),
        small_ratio,
        round(large_seconds * SUCROSE_TALENT_FRAMES_PER_SECOND),
        large_ratio,
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

    解锁按 ``ALWAYS``：源站的解锁条件是「完成魔女的课业」，本期裁定默认已完成
    且不作为仿真输入项（§11.7 裁决 1）；是否生效由队伍魔导角色数在运行期判断。
    """

    slot = _validate_owner(request, SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY)
    name = _effect_name(request.params, purpose="天赋「魔女的前夜礼·七循之理」")
    (
        min_mage_count,
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
            "min_mage_count": min_mage_count,
            "small_duration_frames": small_duration_frames,
            "small_bonus": small_bonus,
            "large_duration_frames": large_duration_frames,
            "large_bonus": large_bonus,
            "small_buff_definition_key": small_definition.definition_key,
            "large_buff_definition_key": large_definition.definition_key,
        },
    )
