"""砂糖固有天赋效果单元工厂（A1 触媒置换术 / A4 小小的慧风）。

效果工厂只负责组装：把资产 ``passive:4`` / ``passive:5`` 效果行的数值读入、
校验并编译为 ContentUnit 的行为切片（``event_hooks`` 与 ``buff_definitions``）。
行为实现见 ``hooks.py``（触发判定与投放）与 ``modifiers.py``（Buff 定义）。

数值口径：加成数值与持续时间取**资产效果行**（``components``），内容侧不复制
一份平行常量；``data.py`` 的常量只在资产缺行时作为 hook 构造的默认值与测试
基准使用。A4 的折算比例只允许落在 (0, 1] 区间——组件错位（文本序号、持续秒数
混入比例位）会在此处失败，而不是静默折算出近零精通加成。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_TALENT_FRAMES_PER_SECOND,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import (
    SucroseCatalystConversionHook,
    SucroseMollisFavoniusHook,
)
from genshin_sim.content.characters.mondstadt.sucrose.modifiers import (
    build_a1_mastery_buff_definition,
    build_a4_mastery_buff_definition,
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
