"""圣遗物套装内容实现的公共辅助。

各套装文件（触发挂 Buff、攻击标签条件、运行端口条件等模式）重复使用的
装配期校验、数值解析与统一口径常量集中在本模块，避免逐文件复制导致
口径漂移：

- ``require_piece_count`` / ``require_set_row``：件数效果键与套装索引行的绑定校验；
- ``slot_owner_ref``：由槽位派生穿戴者主体引用；
- ``content_source_ref``：构造内容来源引用，套装 key 前缀由引用方传入；
- ``parse_component_values``：按正式内容 ``components`` 约定读取效果数值；
- ``FRAMES_PER_SECOND`` 与攻击标签常量：内容层统一口径。

这些工具不持有状态，只依赖 ``ArtifactContentUnitRequest`` 的公开字段与
资产库 ``components`` 结构，可在各套装间安全复用。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef

FRAMES_PER_SECOND = 60

CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"
NORMAL_ATTACK_TAG_PREFIX = "普通攻击"


def require_piece_count(
    request: ArtifactContentUnitRequest,
    *,
    expected: int,
    handler_key: str,
) -> None:
    """件数效果键必须绑定到对应件数的效果行。"""

    if request.piece_count != expected:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定 {expected} 件套效果，收到 {request.piece_count} 件"
        )


def require_set_row(request: ArtifactContentUnitRequest, *, handler_key: str) -> None:
    """套装索引行单元键只能绑定套装索引行，不能绑定件数效果行。"""

    if request.piece_count is not None:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定套装索引行，收到 {request.piece_count} 件套效果行"
        )


def slot_owner_ref(slot: int) -> str:
    """由槽位派生穿戴者主体引用（``character:slot_N``）。"""

    return f"character:slot_{slot}"


def content_source_ref(key_prefix: str, scope: str, slot: int) -> RuntimeSourceRef:
    """构造内容来源引用：``<key_prefix>:<scope>:slot:<slot>``。"""

    return RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{key_prefix}:{scope}:slot:{slot}",
    )


def parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取数值列表（与正式内容 components 约定一致）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
