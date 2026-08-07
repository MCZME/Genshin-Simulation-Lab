"""声明式通用部件（generic 构成部件）。

generic 部件不带键名，只表达形状与参数；内容包包装时才赋予内容级键。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible

type ComponentParamValidator = Callable[[Mapping[str, JSONValue]], None]


class GenericComponentError(Exception):
    """generic 部件错误基类。"""


class UnknownGenericComponentKindError(GenericComponentError, LookupError):
    """部件 kind 未注册。"""


class DuplicateGenericComponentKindError(GenericComponentError, ValueError):
    """部件 kind 重复注册。"""


class InvalidGenericComponentError(GenericComponentError, ValueError):
    """部件参数不符合 kind 的校验规则。"""


@dataclass(frozen=True, slots=True)
class GenericComponent:
    """无键的声明式通用部件。

    ``kind`` 表达“形状”（如 ``talent_level_boost``），``params`` 表达参数；
    部件自身没有身份键，身份由内容包包装时传入。
    """

    kind: str
    params: Mapping[str, JSONValue] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind 必须是非空字符串")
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version < 1
        ):
            raise ValueError("schema_version 必须是正整数")
        validate_json_compatible(self.params, path="params")
        object.__setattr__(self, "params", dict(self.params))


class GenericComponentKindRegistry:
    """按 kind 注册参数校验器的声明式注册表。"""

    def __init__(self) -> None:
        self._validators: dict[str, ComponentParamValidator] = {}

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._validators))

    def register(
        self,
        kind: str,
        validator: ComponentParamValidator,
        *,
        replace: bool = False,
    ) -> ComponentParamValidator:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("kind 必须是非空字符串")
        if not callable(validator):
            raise TypeError("validator 必须可调用")
        if kind in self._validators and not replace:
            raise DuplicateGenericComponentKindError(f"重复注册 generic 部件 kind：{kind}")
        self._validators[kind] = validator
        return validator

    def contains(self, kind: str) -> bool:
        return kind in self._validators

    def require(self, kind: str) -> ComponentParamValidator:
        try:
            return self._validators[kind]
        except KeyError as exc:
            raise UnknownGenericComponentKindError(f"未注册 generic 部件 kind：{kind}") from exc

    def validate(self, component: GenericComponent) -> None:
        validator = self.require(component.kind)
        try:
            validator(component.params)
        except GenericComponentError:
            raise
        except Exception as exc:
            raise InvalidGenericComponentError(
                f"generic 部件 {component.kind!r} 参数校验失败：{exc}"
            ) from exc
