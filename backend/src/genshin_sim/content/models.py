from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from genshin_sim.core.attributes import ModifierTerm

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


@dataclass(frozen=True, slots=True)
class HookResult:
    impact_requests: Sequence[object] = field(default_factory=tuple)
    modifier_commands: Sequence[object] = field(default_factory=tuple)
    state_patches: Sequence[object] = field(default_factory=tuple)
    audit_notes: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "impact_requests", tuple(self.impact_requests))
        object.__setattr__(self, "modifier_commands", tuple(self.modifier_commands))
        object.__setattr__(self, "state_patches", tuple(self.state_patches))
        object.__setattr__(self, "audit_notes", tuple(self.audit_notes))


class EventHook(Protocol):
    @property
    def hook_key(self) -> str: ...

    @property
    def owner_ref(self) -> str: ...

    @property
    def state_key(self) -> str: ...

    @property
    def subscriptions(self) -> Sequence[str]: ...

    @property
    def priority(self) -> int: ...

    def handle(self, event: object, context: object) -> HookResult: ...


class Modifier(Protocol):
    @property
    def modifier_key(self) -> str: ...

    @property
    def owner_ref(self) -> str: ...

    @property
    def targets(self) -> Sequence[str]: ...

    @property
    def scope(self) -> str: ...

    @property
    def priority(self) -> int: ...

    def evaluate(self, query: object, context: object) -> Sequence[ModifierTerm]: ...


@dataclass(frozen=True, slots=True)
class ContentStateSnapshot:
    """一次宿主内容状态快照。"""

    owner_ref: str
    handler_key: str
    schema_version: int
    frame: int
    payload: JSONValue

    def __post_init__(self) -> None:
        if not isinstance(self.owner_ref, str) or not self.owner_ref.strip():
            raise ValueError("owner_ref 必须是非空字符串")
        if not isinstance(self.handler_key, str) or not self.handler_key.strip():
            raise ValueError("handler_key 必须是非空字符串")
        if isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise ValueError("schema_version 必须是正整数")
        if isinstance(self.frame, bool) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        validate_json_compatible(self.payload)
