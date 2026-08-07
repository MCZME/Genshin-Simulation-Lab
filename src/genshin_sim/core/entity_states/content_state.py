"""内容状态挂载记录（core 中立宿主运行态）。

挂载记录是“共享定义 + 每宿主实例”中的宿主侧：定义（``StateSchema``）
全局共享，当前值只属于本挂载；挂载记录通常由
``CharacterRuntimeState.content_states`` 持有，经装配期创建。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.state_schema import (
    StateSchema,
    StateSchemaValidationError,
)


class ContentStateMountError(Exception):
    """内容状态挂载错误基类。"""


class ContentStateMount:
    """单个宿主上的一份内容私有状态挂载实例。

    ``state_key`` 为宿主内唯一键（当前为内容包 ``handler_key``）；
    ``owner`` 为宿主身份，当前必须与 ``schema.owner_ref`` 一致，后续
    schema 去宿主化后由挂载点统一绑定。
    """

    def __init__(
        self,
        state_key: str,
        schema: StateSchema,
        *,
        owner: str | None = None,
        initial_values: Mapping[str, JSONValue] | None = None,
    ) -> None:
        if not isinstance(state_key, str) or not state_key.strip():
            raise ContentStateMountError("state_key 必须是非空字符串")
        if not isinstance(schema, StateSchema):
            raise TypeError("schema 必须是 StateSchema")
        owner = owner or schema.owner_ref
        if owner != schema.owner_ref:
            raise ContentStateMountError(
                f"挂载 owner {owner!r} 必须与 schema.owner_ref {schema.owner_ref!r} 一致"
            )
        self.state_key = state_key
        self.schema = schema
        self.owner = owner
        self._values: dict[str, JSONValue] = dict(schema.defaults())
        if initial_values is not None:
            self.apply_patch(initial_values)

    @property
    def values(self) -> Mapping[str, JSONValue]:
        """当前值的只读视图。"""

        return MappingProxyType(dict(self._values))

    def get(self, name: str) -> JSONValue:
        try:
            return self._values[name]
        except KeyError as exc:
            raise KeyError(f"未知状态字段：{name}") from exc

    def apply_patch(self, fields: Mapping[str, JSONValue]) -> None:
        """校验后原子写入；任何字段不合法都不产生部分写入。"""

        if not isinstance(fields, Mapping):
            raise TypeError("fields 必须是映射")
        staged: dict[str, JSONValue] = {}
        for name, value in fields.items():
            try:
                staged[name] = self._prepare_value(name, value)
            except StateSchemaValidationError as exc:
                raise ContentStateMountError(
                    f"宿主 {self.owner} 状态写入失败：{exc}"
                ) from exc
        self._values.update(staged)

    def snapshot(self, frame: int) -> dict[str, object]:
        """导出 JSON 兼容快照字典。"""

        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("frame 必须是非负整数")
        return {
            "owner_ref": self.owner,
            "state_key": self.state_key,
            "schema_version": 1,
            "frame": frame,
            "payload": dict(self._values),
        }

    def _prepare_value(self, name: str, value: object) -> JSONValue:
        item = self.schema.field(name)
        if item is None:
            raise StateSchemaValidationError(f"未知状态字段：{name}")
        if item.clamp and isinstance(value, int | float) and not isinstance(value, bool):
            return item.clamp_value(value)
        item.validate_value(value)
        return cast(JSONValue, value)
