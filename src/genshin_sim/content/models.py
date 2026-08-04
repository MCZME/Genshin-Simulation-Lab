from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeVar, cast, overload

from genshin_sim.core.attributes import (
    AttributeDefinition,
    ModifierProvider,
    ModifierStackingGroupDefinition,
    ModifierTerm,
)
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    validate_reaction_capability_key,
)
from genshin_sim.core.systems.buff import BuffDefinition
from genshin_sim.core.systems.damage import (
    DamageModifierProvider,
    DamageModifierStackingGroupDefinition,
)

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]

StateT = TypeVar("StateT")


class ContentStateStoreError(Exception):
    """内容运行态存储错误基类。"""


class ContentStateSlotError(ContentStateStoreError, ValueError):
    """内容运行态操作缺少必要的归属槽位。"""


class ContentStateNotFoundError(ContentStateStoreError, LookupError):
    """请求的内容运行态不存在。"""


class ContentStateTypeError(ContentStateStoreError, TypeError):
    """请求的内容运行态类型不符合预期。"""


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} 必须是非空字符串")


def _validate_slot(owner_type: str, slot: int | None) -> int:
    owner_label = _owner_type_label(owner_type)
    if slot is None:
        raise ContentStateSlotError(f"{owner_label}内容运行态需要 slot")
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise ContentStateSlotError(f"{owner_label}内容运行态 slot 必须是整数")
    return slot


def _owner_type_label(owner_type: str) -> str:
    return {
        "character": "角色",
        "weapon": "武器",
        "artifact": "圣遗物",
        "generic": "通用",
    }.get(owner_type, owner_type)


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
    hook_key: str
    owner_ref: str
    subscriptions: Sequence[str]
    priority: int

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
class ContentRuntimeContribution:
    owner_type: str
    owner_key: str
    handler_key: str
    slot: int | None = None
    action_interpreter: object | None = None
    actions: Sequence[object] = field(default_factory=tuple)
    state_extension: object | None = None
    impact_factories: Mapping[str, object] = field(default_factory=dict)
    created_object_behaviors: Mapping[str, object] = field(default_factory=dict)
    event_hooks: Sequence[EventHook] = field(default_factory=tuple)
    modifiers: Sequence[Modifier] = field(default_factory=tuple)
    attribute_definitions: Sequence[AttributeDefinition] = field(default_factory=tuple)
    attribute_stacking_groups: Sequence[ModifierStackingGroupDefinition] = field(
        default_factory=tuple
    )
    attribute_providers: Sequence[ModifierProvider] = field(default_factory=tuple)
    buff_definitions: Sequence[BuffDefinition] = field(default_factory=tuple)
    damage_modifier_providers: Sequence[DamageModifierProvider] = field(default_factory=tuple)
    damage_modifier_stacking_groups: Sequence[DamageModifierStackingGroupDefinition] = field(
        default_factory=tuple
    )
    reaction_capability_keys: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.owner_type, "owner_type")
        _validate_non_empty_text(self.owner_key, "owner_key")
        _validate_non_empty_text(self.handler_key, "handler_key")
        if self.slot is not None and (
            isinstance(self.slot, bool) or not isinstance(self.slot, int)
        ):
            raise ValueError("slot 提供时必须是整数")
        capability_keys = tuple(self.reaction_capability_keys)
        if capability_keys and self.owner_type != "character":
            raise ValueError("只有角色 content 可以声明 reaction capability")
        if capability_keys and self.slot is None:
            raise ValueError("声明 reaction capability 的角色 content 必须提供 slot")
        for capability_key in capability_keys:
            validate_reaction_capability_key(capability_key)
        if len(set(capability_keys)) != len(capability_keys):
            raise ValueError("reaction_capability_keys 不能包含重复 key")
        object.__setattr__(self, "reaction_capability_keys", capability_keys)
        object.__setattr__(self, "actions", tuple(self.actions))
        for impact_key in self.impact_factories:
            _validate_non_empty_text(impact_key, "impact_factories key")
        for behavior_key in self.created_object_behaviors:
            _validate_non_empty_text(behavior_key, "created_object_behaviors key")
        object.__setattr__(self, "impact_factories", dict(self.impact_factories))
        object.__setattr__(
            self,
            "created_object_behaviors",
            dict(self.created_object_behaviors),
        )
        object.__setattr__(self, "event_hooks", tuple(self.event_hooks))
        object.__setattr__(self, "modifiers", tuple(self.modifiers))
        object.__setattr__(self, "attribute_definitions", tuple(self.attribute_definitions))
        object.__setattr__(
            self,
            "attribute_stacking_groups",
            tuple(self.attribute_stacking_groups),
        )
        object.__setattr__(self, "attribute_providers", tuple(self.attribute_providers))
        object.__setattr__(self, "buff_definitions", tuple(self.buff_definitions))
        object.__setattr__(
            self,
            "damage_modifier_providers",
            tuple(self.damage_modifier_providers),
        )
        object.__setattr__(
            self,
            "damage_modifier_stacking_groups",
            tuple(self.damage_modifier_stacking_groups),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


class ContentStateStore:
    """按归属范围保存内容扩展运行态。"""

    def __init__(self) -> None:
        self._character_states: dict[tuple[int, str], object] = {}
        self._weapon_states: dict[tuple[int, str], object] = {}
        self._artifact_states: dict[tuple[int, str], object] = {}
        self._generic_states: dict[tuple[str, str], object] = {}

    def set_character_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        state: object,
    ) -> None:
        slot_value = _validate_slot("character", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        self._character_states[(slot_value, handler_key)] = state

    def set_weapon_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        state: object,
    ) -> None:
        slot_value = _validate_slot("weapon", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        self._weapon_states[(slot_value, handler_key)] = state

    def set_artifact_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        state: object,
    ) -> None:
        slot_value = _validate_slot("artifact", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        self._artifact_states[(slot_value, handler_key)] = state

    def set_generic_state(
        self,
        *,
        owner_ref: str,
        handler_key: str,
        state: object,
    ) -> None:
        _validate_non_empty_text(owner_ref, "owner_ref")
        _validate_non_empty_text(handler_key, "handler_key")
        self._generic_states[(owner_ref, handler_key)] = state

    @overload
    def get_character_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT],
    ) -> StateT: ...

    @overload
    def get_character_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: None = None,
    ) -> object: ...

    def get_character_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT] | None = None,
    ) -> StateT | object:
        slot_value = _validate_slot("character", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        try:
            state = self._character_states[(slot_value, handler_key)]
        except KeyError as exc:
            raise ContentStateNotFoundError(
                f"缺少 slot {slot_value} 与 handler_key {handler_key!r} 的角色运行态"
            ) from exc
        if expected_type is None:
            return state
        if not isinstance(state, expected_type):
            raise ContentStateTypeError(
                f"slot {slot_value} 与 handler_key {handler_key!r} 的角色运行态"
                f"期望 {expected_type.__name__}，实际 {type(state).__name__}"
            )
        return cast(StateT, state)

    @overload
    def get_weapon_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT],
    ) -> StateT: ...

    @overload
    def get_weapon_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: None = None,
    ) -> object: ...

    def get_weapon_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT] | None = None,
    ) -> StateT | object:
        slot_value = _validate_slot("weapon", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        try:
            state = self._weapon_states[(slot_value, handler_key)]
        except KeyError as exc:
            raise ContentStateNotFoundError(
                f"缺少 slot {slot_value} 与 handler_key {handler_key!r} 的武器运行态"
            ) from exc
        return _cast_state(
            state,
            expected_type,
            owner_type="weapon",
            owner_ref=f"slot {slot_value}",
            handler_key=handler_key,
        )

    @overload
    def get_artifact_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT],
    ) -> StateT: ...

    @overload
    def get_artifact_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: None = None,
    ) -> object: ...

    def get_artifact_state(
        self,
        *,
        slot: int | None,
        handler_key: str,
        expected_type: type[StateT] | None = None,
    ) -> StateT | object:
        slot_value = _validate_slot("artifact", slot)
        _validate_non_empty_text(handler_key, "handler_key")
        try:
            state = self._artifact_states[(slot_value, handler_key)]
        except KeyError as exc:
            raise ContentStateNotFoundError(
                f"缺少 slot {slot_value} 与 handler_key {handler_key!r} 的圣遗物运行态"
            ) from exc
        return _cast_state(
            state,
            expected_type,
            owner_type="artifact",
            owner_ref=f"slot {slot_value}",
            handler_key=handler_key,
        )

    @overload
    def get_generic_state(
        self,
        *,
        owner_ref: str,
        handler_key: str,
        expected_type: type[StateT],
    ) -> StateT: ...

    @overload
    def get_generic_state(
        self,
        *,
        owner_ref: str,
        handler_key: str,
        expected_type: None = None,
    ) -> object: ...

    def get_generic_state(
        self,
        *,
        owner_ref: str,
        handler_key: str,
        expected_type: type[StateT] | None = None,
    ) -> StateT | object:
        _validate_non_empty_text(owner_ref, "owner_ref")
        _validate_non_empty_text(handler_key, "handler_key")
        try:
            state = self._generic_states[(owner_ref, handler_key)]
        except KeyError as exc:
            raise ContentStateNotFoundError(
                f"缺少归属 {owner_ref!r} 与 handler_key {handler_key!r} 的通用运行态"
            ) from exc
        return _cast_state(
            state,
            expected_type,
            owner_type="generic",
            owner_ref=owner_ref,
            handler_key=handler_key,
        )


def _cast_state[CastT](
    state: object,
    expected_type: type[CastT] | None,
    *,
    owner_type: str,
    owner_ref: str,
    handler_key: str,
) -> CastT | object:
    if expected_type is None:
        return state
    if not isinstance(state, expected_type):
        owner_label = _owner_type_label(owner_type)
        raise ContentStateTypeError(
            f"{owner_label}运行态 {owner_ref} 与 handler_key {handler_key!r}"
            f"期望 {expected_type.__name__}，实际 {type(state).__name__}"
        )
    return cast(CastT, state)


@dataclass(frozen=True, slots=True)
class ContentStateSnapshot:
    owner_ref: str
    handler_key: str
    schema_version: int
    frame: int
    payload: JSONValue

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.owner_ref, "owner_ref")
        _validate_non_empty_text(self.handler_key, "handler_key")
        if isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise ValueError("schema_version 必须是正整数")
        if isinstance(self.frame, bool) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        validate_json_compatible(self.payload)


class ContentStateSnapshotProvider(Protocol):
    def snapshot_state(self, frame: int, state: object) -> ContentStateSnapshot: ...
