"""JSON 兼容值的共享契约。

内容定义、意图载荷与状态快照都要求 JSON 兼容，保证可序列化与可复现。
旧 content.models 中的同名工具在后续里程碑统一迁移到本模块。
"""

from __future__ import annotations

import math

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]


def validate_json_compatible(value: object, *, path: str = "payload") -> None:
    """当值无法表示为 JSON 数据时抛出异常。"""

    if value is None or isinstance(value, bool | str | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} 必须是有限数字，实际为 {value!r}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_compatible(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} 必须使用字符串键，实际为 {key!r}")
            validate_json_compatible(item, path=f"{path}.{key}")
        return
    raise TypeError(f"{path} 必须是 JSON 兼容值，实际类型为 {type(value).__name__}")
