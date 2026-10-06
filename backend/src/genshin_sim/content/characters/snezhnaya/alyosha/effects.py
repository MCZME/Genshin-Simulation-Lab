"""阿罗夏效果行工厂：命座 C3/C5（天赋等级提升）。

骨架阶段先接 C3/C5；P4/P5/P6 与 C1/C2/C4/C6 的行为工厂随核心机制切片
接入（bootstrap 当前为其注册空效果 handler 占位，见
`docs/工程/阿罗夏接入规划.md` §7 实施步骤 4）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CONSTELLATION_C3_HANDLER_KEY,
    ALYOSHA_CONSTELLATION_C5_HANDLER_KEY,
    ALYOSHA_CONTENT_VERSION,
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
