"""反应伤害 Gate 的计数窗口计划与提交。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.systems.reaction.models import (
    OccurrenceCause,
    ReactionEffectCause,
)
from genshin_sim.core.systems.reaction.states import ScheduledStateTickCause


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


class ReactionDamageGateDecision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ReactionDamageGateDefinition:
    gate_definition_key: str
    damage_kind_key: str
    window_frames: int
    max_damage_instances: int

    def __post_init__(self) -> None:
        _text(self.gate_definition_key, "gate_definition_key")
        _text(self.damage_kind_key, "damage_kind_key")
        for field_name in ("window_frames", "max_damage_instances"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必须是正整数")


@dataclass(frozen=True, order=True, slots=True)
class ReactionDamageGateSlotKey:
    gate_definition_key: str
    trigger_source_ref: ElementalSourceRef
    damage_target_ref: ElementalSubjectRef
    damage_kind_key: str

    def __post_init__(self) -> None:
        _text(self.gate_definition_key, "gate_definition_key")
        _text(self.damage_kind_key, "damage_kind_key")


@dataclass(frozen=True, slots=True)
class ReactionDamageGateRecord:
    slot_key: ReactionDamageGateSlotKey
    window_started_frame: int
    ready_frame: int
    accepted_count: int
    last_accepted_frame: int
    last_occurrence_ref: str | None
    last_effect_ref: str
    revision: int
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "window_started_frame",
            "ready_frame",
            "accepted_count",
            "last_accepted_frame",
            "revision",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} 必须是非负整数")
        if self.ready_frame <= self.window_started_frame:
            raise ValueError("ready_frame 必须晚于 window_started_frame")
        if self.accepted_count <= 0:
            raise ValueError("accepted_count 必须为正整数")
        _text(self.last_effect_ref, "last_effect_ref")
        cause = self.cause or (
            OccurrenceCause(self.last_occurrence_ref)
            if self.last_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("Damage Gate Record 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.last_occurrence_ref is not None and self.last_occurrence_ref != occurrence_ref:
            raise ValueError("last_occurrence_ref 必须是 cause 的 occurrence 投影")
        object.__setattr__(self, "last_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)


@dataclass(frozen=True, slots=True)
class ReactionDamageGateRequest:
    gate_request_ref: str
    frame: int
    definition: ReactionDamageGateDefinition
    trigger_source_ref: ElementalSourceRef
    damage_target_ref: ElementalSubjectRef
    parent_occurrence_ref: str | None
    parent_effect_ref: str
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        _text(self.gate_request_ref, "gate_request_ref")
        _text(self.parent_effect_ref, "parent_effect_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("Damage Gate Request 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("parent_occurrence_ref 必须是 cause 的 occurrence 投影")
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)

    @property
    def slot_key(self) -> ReactionDamageGateSlotKey:
        return ReactionDamageGateSlotKey(
            self.definition.gate_definition_key,
            self.trigger_source_ref,
            self.damage_target_ref,
            self.definition.damage_kind_key,
        )


@dataclass(frozen=True, slots=True)
class ReactionDamageGateResolution:
    resolution_ref: str
    gate_request_ref: str
    frame: int
    slot_key: ReactionDamageGateSlotKey
    parent_occurrence_ref: str | None
    parent_effect_ref: str
    decision: ReactionDamageGateDecision
    reason: str
    window_started_frame_before: int | None
    window_started_frame_after: int | None
    ready_frame_before: int | None
    ready_frame_after: int | None
    accepted_count_before: int
    accepted_count_after: int
    window_frames: int
    max_damage_instances: int
    cause: ReactionEffectCause | None = None

    def __post_init__(self) -> None:
        cause = self.cause or (
            OccurrenceCause(self.parent_occurrence_ref)
            if self.parent_occurrence_ref is not None
            else None
        )
        if not isinstance(cause, OccurrenceCause | ScheduledStateTickCause):
            raise ValueError("Damage Gate Resolution 必须具有 ReactionEffectCause")
        occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
        if self.parent_occurrence_ref is not None and self.parent_occurrence_ref != occurrence_ref:
            raise ValueError("parent_occurrence_ref 必须是 cause 的 occurrence 投影")
        object.__setattr__(self, "parent_occurrence_ref", occurrence_ref)
        object.__setattr__(self, "cause", cause)


@dataclass(frozen=True, slots=True)
class ReactionDamageGateMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    resolutions: tuple[ReactionDamageGateResolution, ...]
    expected_records: tuple[ReactionDamageGateRecord, ...]
    replacement_records: tuple[ReactionDamageGateRecord, ...]


@dataclass(frozen=True, slots=True)
class ReactionDamageGateCommitReceipt:
    plan: ReactionDamageGateMutationPlan
    version: int


@dataclass(frozen=True, slots=True)
class ReactionDamageGateSnapshot:
    frame: int
    version: int
    records: tuple[ReactionDamageGateRecord, ...]


class _ReactionDamageGateRuntime(Protocol):
    _gate_records: dict[ReactionDamageGateSlotKey, ReactionDamageGateRecord]

    @property
    def version(self) -> int: ...

    def gate_definition(self, gate_definition_key: str) -> ReactionDamageGateDefinition: ...


class ReactionDamageGatePlanner:
    def __init__(
        self,
        runtime: _ReactionDamageGateRuntime,
        frame: int,
        operation_id: str,
    ) -> None:
        self._runtime = runtime
        self.frame = frame
        self.operation_id = operation_id
        self._working = dict(runtime._gate_records)
        self._original = dict(runtime._gate_records)
        self._expected_store_version = runtime.version
        self._resolutions: list[ReactionDamageGateResolution] = []
        self._sealed = False

    def prepare(self, request: ReactionDamageGateRequest) -> ReactionDamageGateResolution:
        if self._sealed:
            raise RuntimeError("ReactionDamageGatePlanner 已封存")
        if request.frame != self.frame:
            raise ValueError("Gate 请求帧与所属批次不一致")
        if any(item.gate_request_ref == request.gate_request_ref for item in self._resolutions):
            raise ValueError(f"重复的 Gate 请求：{request.gate_request_ref}")
        if (
            self._runtime.gate_definition(request.definition.gate_definition_key)
            != request.definition
        ):
            raise ValueError("Gate 请求引用的定义未注册或不一致")

        key = request.slot_key
        before = self._working.get(key)
        definition = request.definition
        if (
            before is not None
            and request.frame < before.ready_frame
            and before.accepted_count >= definition.max_damage_instances
        ):
            resolution = ReactionDamageGateResolution(
                resolution_ref=f"{request.gate_request_ref}:resolution",
                gate_request_ref=request.gate_request_ref,
                frame=request.frame,
                slot_key=key,
                parent_occurrence_ref=request.parent_occurrence_ref,
                parent_effect_ref=request.parent_effect_ref,
                decision=ReactionDamageGateDecision.BLOCKED,
                reason="window_limit_reached",
                window_started_frame_before=before.window_started_frame,
                window_started_frame_after=before.window_started_frame,
                ready_frame_before=before.ready_frame,
                ready_frame_after=before.ready_frame,
                accepted_count_before=before.accepted_count,
                accepted_count_after=before.accepted_count,
                window_frames=definition.window_frames,
                max_damage_instances=definition.max_damage_instances,
                cause=request.cause,
            )
            self._resolutions.append(resolution)
            return resolution

        if before is None or request.frame >= before.ready_frame:
            record = ReactionDamageGateRecord(
                slot_key=key,
                window_started_frame=request.frame,
                ready_frame=request.frame + definition.window_frames,
                accepted_count=1,
                last_accepted_frame=request.frame,
                last_occurrence_ref=request.parent_occurrence_ref,
                last_effect_ref=request.parent_effect_ref,
                revision=1 if before is None else before.revision + 1,
                cause=request.cause,
            )
        else:
            record = ReactionDamageGateRecord(
                slot_key=key,
                window_started_frame=before.window_started_frame,
                ready_frame=before.ready_frame,
                accepted_count=before.accepted_count + 1,
                last_accepted_frame=request.frame,
                last_occurrence_ref=request.parent_occurrence_ref,
                last_effect_ref=request.parent_effect_ref,
                revision=before.revision + 1,
                cause=request.cause,
            )
        self._working[key] = record
        resolution = ReactionDamageGateResolution(
            resolution_ref=f"{request.gate_request_ref}:resolution",
            gate_request_ref=request.gate_request_ref,
            frame=request.frame,
            slot_key=key,
            parent_occurrence_ref=request.parent_occurrence_ref,
            parent_effect_ref=request.parent_effect_ref,
            decision=ReactionDamageGateDecision.ALLOWED,
            reason="new_window"
            if before is None or request.frame >= before.ready_frame
            else "within_window",
            window_started_frame_before=None if before is None else before.window_started_frame,
            window_started_frame_after=record.window_started_frame,
            ready_frame_before=None if before is None else before.ready_frame,
            ready_frame_after=record.ready_frame,
            accepted_count_before=0 if before is None else before.accepted_count,
            accepted_count_after=record.accepted_count,
            window_frames=definition.window_frames,
            max_damage_instances=definition.max_damage_instances,
            cause=request.cause,
        )
        self._resolutions.append(resolution)
        return resolution

    def seal(self) -> ReactionDamageGateMutationPlan:
        if self._sealed:
            raise RuntimeError("ReactionDamageGatePlanner 已封存")
        self._sealed = True
        changed_keys = tuple(
            sorted(
                key for key, record in self._working.items() if self._original.get(key) != record
            )
        )
        return ReactionDamageGateMutationPlan(
            operation_id=self.operation_id,
            frame=self.frame,
            expected_store_version=self._expected_store_version,
            resolutions=tuple(self._resolutions),
            expected_records=tuple(
                self._original[key] for key in changed_keys if key in self._original
            ),
            replacement_records=tuple(self._working[key] for key in changed_keys),
        )
