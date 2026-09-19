"""西风长枪内容单元编译入口。

被动行为实现落在这里而不是效果单元：``WeaponContentUnitRequest`` 携带精炼等级，
而效果通道不携带，概率与触发间隔只能由武器内容单元确定。

概率与触发间隔从 ``request.params``（该武器效果行的资产参数）按精炼读取，本文件
自己声明需要的数据形态与校验规则。资产参数的整体形态由资产侧决定，装配层不承诺、
也不校验它，因此这里的解析规则是本包的实现细节，不是跨层契约。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.content.weapons.polearm.favonius_lance.data import (
    FAVONIUS_LANCE_CONTENT_VERSION,
    FAVONIUS_LANCE_HANDLER_KEY,
    FRAMES_PER_SECOND,
)
from genshin_sim.content.weapons.polearm.favonius_lance.hooks import (
    FavoniusLanceWindfallHook,
)

# 本包对资产效果参数的位置约定：components[0] 是触发概率，components[1] 是间隔秒数，
# 两者的 values 都按精炼顺序给出取值。
_PROBABILITY_INDEX = 0
_INTERVAL_SECONDS_INDEX = 1
_REQUIRED_COMPONENT_COUNT = 2


def create_favonius_lance_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """西风长枪内容单元工厂：基础属性之外贡献顺风而行钩子。"""

    probability, interval_frames = windfall_parameters(request.params, request.refinement)
    owner_ref = f"character:slot_{request.slot}"
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FAVONIUS_LANCE_HANDLER_KEY,
        version=FAVONIUS_LANCE_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(
            FavoniusLanceWindfallHook(
                owner_ref=owner_ref,
                slot=request.slot,
                probability=probability,
                interval_frames=interval_frames,
            ),
        ),
        metadata={"purpose": "favonius_lance_windfall"},
    )


def windfall_parameters(
    params: Mapping[str, object],
    refinement: int,
) -> tuple[float, int]:
    """按资产效果参数与精炼返回（触发概率, 触发间隔帧数）。

    参数缺失、精炼越界或取值非法都在组装阶段失败，不静默回退默认值。
    """

    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("西风长枪精炼必须是整数")

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < _REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError(
            "顺风而行缺少资产效果参数：components 需同时给出触发概率与间隔秒数"
        )

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"西风长枪精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )

    offset = refinement - refinement_min
    probability = _component_value(components[_PROBABILITY_INDEX], offset, label="触发概率")
    interval_seconds = _component_value(
        components[_INTERVAL_SECONDS_INDEX], offset, label="触发间隔"
    )
    if not 0.0 <= probability <= 1.0:
        raise ContentUnitValidationError(f"顺风而行触发概率必须在 0 到 1 之间，实际 {probability}")
    if interval_seconds <= 0.0:
        raise ContentUnitValidationError(f"顺风而行触发间隔必须为正数秒，实际 {interval_seconds}")
    return probability, round(interval_seconds * FRAMES_PER_SECOND)


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"顺风而行缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, *, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"顺风而行{label}分量必须是对象")
    values = component.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ContentUnitValidationError(f"顺风而行{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"顺风而行{label}分量的 values 未覆盖该精炼（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"顺风而行{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ContentUnitValidationError(f"顺风而行{label}分量在该精炼下不是有限数值")
    return number
