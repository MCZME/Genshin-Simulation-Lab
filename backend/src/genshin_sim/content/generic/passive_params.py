"""generic 低星武器被动的资产参数解读部件。

不带键：本模块只提供「按精炼从资产效果参数 components 取值」的共享解析规则，
不绑定任何具体武器。参数的整体形态由资产侧决定，装配层不承诺也不校验它
（见 D-079）；解析失败一律在组装阶段抛错，不静默回退默认值。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError


def refinement_offset(
    params: Mapping[str, object],
    refinement: int | None,
    *,
    owner_label: str,
) -> int:
    """校验精炼等级并返回它在 ``values`` 序列中的下标偏移。

    ``refinement`` 由拥有者（武器索引行单元）提供，效果行不重复声明；缺失或
    越出资产声明的 ``refinement_min``/``refinement_max`` 都在组装阶段失败。
    """

    if refinement is None:
        raise ContentUnitValidationError(f"{owner_label} 缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError(f"{owner_label} 精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min", owner_label)
    refinement_max = _refinement_bound(params, "refinement_max", owner_label)
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"{owner_label} 精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    return refinement - refinement_min


def component_value(
    params: Mapping[str, object],
    *,
    component_index: int,
    offset: int,
    label: str,
    owner_label: str,
    minimum: float | None = None,
) -> float:
    """取出 ``components[component_index]`` 在给定精炼偏移下的数值分量。

    ``minimum`` 提供时校验取值下界（如概率的 0、倍率与比例的正数下界）；
    缺省时只要求有限数值。
    """

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) <= component_index
    ):
        raise ContentUnitValidationError(
            f"{owner_label} 缺少资产效果参数：components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"{owner_label}{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or not values
    ):
        raise ContentUnitValidationError(f"{owner_label}{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"{owner_label}{label}分量的 values 未覆盖该精炼（需要下标 {offset}，"
            f"实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"{owner_label}{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ContentUnitValidationError(f"{owner_label}{label}分量在该精炼下必须是有限数值")
    if minimum is not None and number < minimum:
        raise ContentUnitValidationError(
            f"{owner_label}{label}分量在该精炼下必须不小于 {minimum}，实际 {number}"
        )
    return number


def _refinement_bound(params: Mapping[str, object], key: str, owner_label: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"{owner_label} 缺少资产效果参数 {key}（整数）")
    return value
