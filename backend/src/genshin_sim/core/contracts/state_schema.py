"""内容状态 schema 运行期共享契约。

字段类型、默认值、约束、clamp 与片段合并都是纯数据契约，core 与 content
共用；内容层只负责在编译期决定“哪些效果产出哪些片段”。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible


class StateSchemaError(Exception):
    """状态 schema 错误基类。"""


class StateSchemaValidationError(StateSchemaError, ValueError):
    """状态字段声明或写入值不合法。"""


class StateSchemaConflictError(StateSchemaError, ValueError):
    """多个状态片段合并冲突。"""


class StateFieldType(StrEnum):
    """状态字段类型。"""

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    ENUM = "enum"


@dataclass(frozen=True, slots=True)
class StateField:
    """单个状态字段的声明。"""

    name: str
    field_type: StateFieldType
    default: JSONValue
    non_negative: bool = False
    max_value: int | float | None = None
    allowed_values: tuple[str, ...] = ()
    clamp: bool = False
    shared: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise StateSchemaValidationError("字段名必须是非空字符串")
        if not isinstance(self.field_type, StateFieldType):
            raise TypeError("field_type 必须是 StateFieldType")
        validate_json_compatible(self.default, path=f"fields.{self.name}.default")
        if self.field_type is StateFieldType.ENUM:
            if not self.allowed_values:
                raise StateSchemaValidationError(f"ENUM 字段 {self.name} 必须提供 allowed_values")
        elif self.allowed_values:
            raise StateSchemaValidationError(f"只有 ENUM 字段可以声明 allowed_values：{self.name}")
        if not _matches_type(self.default, self.field_type, self.allowed_values):
            raise StateSchemaValidationError(f"字段 {self.name} 默认值与类型不匹配")
        if self.max_value is not None:
            if isinstance(self.max_value, bool) or not isinstance(self.max_value, int | float):
                raise StateSchemaValidationError(f"字段 {self.name} 的 max_value 必须是数字")
            if self.field_type not in {StateFieldType.INT, StateFieldType.FLOAT}:
                raise StateSchemaValidationError(f"只有数值字段可以声明 max_value：{self.name}")
            if (
                isinstance(self.default, int | float)
                and not isinstance(self.default, bool)
                and self.default > self.max_value
            ):
                raise StateSchemaValidationError(f"字段 {self.name} 默认值超过 max_value")
        if self.non_negative:
            if self.field_type not in {StateFieldType.INT, StateFieldType.FLOAT}:
                raise StateSchemaValidationError(f"只有数值字段可以声明 non_negative：{self.name}")
            if (
                isinstance(self.default, int | float)
                and not isinstance(self.default, bool)
                and self.default < 0
            ):
                raise StateSchemaValidationError(f"字段 {self.name} 默认值不能为负数")
        object.__setattr__(self, "allowed_values", tuple(self.allowed_values))

    def validate_value(self, value: object) -> None:
        """校验写入值；超限时按声明严格失败，不静默截断。"""

        if not _matches_type(value, self.field_type, self.allowed_values):
            raise StateSchemaValidationError(
                f"字段 {self.name} 期望 {self.field_type.value}，实际 {type(value).__name__}"
            )
        if isinstance(value, int | float) and not isinstance(value, bool):
            if self.non_negative and value < 0:
                raise StateSchemaValidationError(f"字段 {self.name} 不能为负数")
            if self.max_value is not None and value > self.max_value:
                raise StateSchemaValidationError(f"字段 {self.name} 不能超过 {self.max_value}")

    def clamp_value(self, value: int | float) -> int | float:
        """对数值字段执行显式 clamp；只有声明 ``clamp=True`` 时才允许使用。"""

        if not self.clamp:
            raise StateSchemaValidationError(f"字段 {self.name} 未声明 clamp，不能截断写入")
        if self.field_type not in {StateFieldType.INT, StateFieldType.FLOAT}:
            raise StateSchemaValidationError(f"只有数值字段可以 clamp：{self.name}")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise StateSchemaValidationError(f"字段 {self.name} 必须是数字才能 clamp")
        if self.non_negative:
            value = max(value, 0)
        if self.max_value is not None:
            value = min(value, self.max_value)
        if self.field_type is StateFieldType.INT:
            return int(value)
        return float(value)


@dataclass(frozen=True, slots=True)
class StateSchemaFragment:
    """单个效果声明的状态片段（内容编译期合并输入）。"""

    owner_ref: str
    fields: tuple[StateField, ...] = ()

    def __post_init__(self) -> None:
        _validate_owner_ref(self.owner_ref)
        _validate_unique_names(self.fields, "状态片段内字段名不能重复")


@dataclass(frozen=True, slots=True)
class StateSchema:
    """合并后的完整内容状态 schema。"""

    owner_ref: str
    fields: tuple[StateField, ...]

    def __post_init__(self) -> None:
        _validate_owner_ref(self.owner_ref)
        _validate_unique_names(self.fields, "状态 schema 字段名不能重复")

    def field(self, name: str) -> StateField | None:
        for item in self.fields:
            if item.name == name:
                return item
        return None

    def defaults(self) -> dict[str, JSONValue]:
        return {item.name: item.default for item in self.fields}

    def validate_patch(self, name: str, value: object) -> None:
        item = self.field(name)
        if item is None:
            raise StateSchemaValidationError(f"未知状态字段：{name}")
        item.validate_value(value)

    def clamp_value(self, name: str, value: int | float) -> int | float:
        item = self.field(name)
        if item is None:
            raise StateSchemaValidationError(f"未知状态字段：{name}")
        return item.clamp_value(value)


def merge_state_schema_fragments(
    owner_ref: str,
    fragments: Sequence[StateSchemaFragment],
) -> StateSchema:
    """合并多个状态片段为完整 schema。

    字段名默认全局唯一；同名必须由双方显式声明 ``shared=True`` 且声明完全
    一致，否则报冲突。
    """

    merged: dict[str, StateField] = {}
    for fragment in fragments:
        if fragment.owner_ref != owner_ref:
            raise StateSchemaConflictError(
                f"状态片段归属不一致：{fragment.owner_ref} != {owner_ref}"
            )
        for item in fragment.fields:
            existing = merged.get(item.name)
            if existing is None:
                merged[item.name] = item
                continue
            if not item.shared or not existing.shared:
                raise StateSchemaConflictError(f"状态字段 {item.name} 被多个片段声明但未显式共享")
            if not _same_field_shape(existing, item):
                raise StateSchemaConflictError(f"共享状态字段 {item.name} 的声明不一致")
    return StateSchema(
        owner_ref=owner_ref,
        fields=tuple(sorted(merged.values(), key=lambda item: item.name)),
    )


def _same_field_shape(left: StateField, right: StateField) -> bool:
    return (
        left.field_type is right.field_type
        and left.default == right.default
        and left.non_negative == right.non_negative
        and left.max_value == right.max_value
        and left.allowed_values == right.allowed_values
        and left.clamp == right.clamp
    )


def _validate_owner_ref(owner_ref: str) -> None:
    if not isinstance(owner_ref, str) or not owner_ref.strip():
        raise StateSchemaValidationError("owner_ref 必须是非空字符串")


def _validate_unique_names(fields: Sequence[StateField], message: str) -> None:
    names = [item.name for item in fields]
    if len(names) != len(set(names)):
        raise StateSchemaValidationError(message)


def _matches_type(
    value: object,
    field_type: StateFieldType,
    allowed_values: tuple[str, ...],
) -> bool:
    if field_type is StateFieldType.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type is StateFieldType.FLOAT:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if field_type is StateFieldType.BOOL:
        return isinstance(value, bool)
    if field_type is StateFieldType.STRING:
        return isinstance(value, str)
    return isinstance(value, str) and value in allowed_values
