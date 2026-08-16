"""反应成立 Gate 的计数窗口计划与提交模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from genshin_sim.core.elements import ElementalSubjectRef


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _frame(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


class ReactionEstablishmentGateDecision(StrEnum):
    ALLOWED = "allowed"
    ESTABLISHMENT_GATE_BLOCKED = "establishment_gate_blocked"


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateDefinition:
    gate_definition_key: str
    window_frames: int
    max_occurrences: int

    def __post_init__(self) -> None:
        _text(self.gate_definition_key, "gate_definition_key")
        for field_name in ("window_frames", "max_occurrences"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必须是正整数")


@dataclass(frozen=True, order=True, slots=True)
class ReactionEstablishmentGateSlotKey:
    gate_definition_key: str
    subject_ref: ElementalSubjectRef

    def __post_init__(self) -> None:
        _text(self.gate_definition_key, "gate_definition_key")


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateRecord:
    slot_key: ReactionEstablishmentGateSlotKey
    window_started_frame: int
    ready_frame: int
    accepted_count: int
    last_accepted_frame: int
    last_occurrence_ref: str
    revision: int

    def __post_init__(self) -> None:
        for field_name in (
            "window_started_frame",
            "ready_frame",
            "accepted_count",
            "last_accepted_frame",
            "revision",
        ):
            _frame(getattr(self, field_name), field_name)
        if self.ready_frame <= self.window_started_frame:
            raise ValueError("ready_frame 必须晚于 window_started_frame")
        if self.accepted_count <= 0:
            raise ValueError("accepted_count 必须为正整数")
        _text(self.last_occurrence_ref, "last_occurrence_ref")


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateRequest:
    gate_request_ref: str
    frame: int
    definition: ReactionEstablishmentGateDefinition
    subject_ref: ElementalSubjectRef
    occurrence_ref: str

    def __post_init__(self) -> None:
        _text(self.gate_request_ref, "gate_request_ref")
        _text(self.occurrence_ref, "occurrence_ref")
        _frame(self.frame, "frame")
        if not isinstance(self.definition, ReactionEstablishmentGateDefinition):
            raise TypeError("definition 必须是 ReactionEstablishmentGateDefinition")
        if not isinstance(self.subject_ref, ElementalSubjectRef):
            raise TypeError("subject_ref 必须是 ElementalSubjectRef")

    @property
    def slot_key(self) -> ReactionEstablishmentGateSlotKey:
        return ReactionEstablishmentGateSlotKey(
            self.definition.gate_definition_key,
            self.subject_ref,
        )


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateResolution:
    resolution_ref: str
    gate_request_ref: str
    frame: int
    slot_key: ReactionEstablishmentGateSlotKey
    occurrence_ref: str
    decision: ReactionEstablishmentGateDecision
    reason: str
    window_started_frame_before: int | None
    window_started_frame_after: int | None
    ready_frame_before: int | None
    ready_frame_after: int | None
    accepted_count_before: int
    accepted_count_after: int
    window_frames: int
    max_occurrences: int


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    resolutions: tuple[ReactionEstablishmentGateResolution, ...]
    expected_records: tuple[ReactionEstablishmentGateRecord, ...]
    replacement_records: tuple[ReactionEstablishmentGateRecord, ...]

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id")
        _frame(self.frame, "frame")
        _frame(self.expected_store_version, "expected_store_version")
        if any(
            not isinstance(resolution, ReactionEstablishmentGateResolution)
            for resolution in self.resolutions
        ):
            raise TypeError("成立 Gate resolutions 必须全部是 ReactionEstablishmentGateResolution")
        if any(
            not isinstance(record, ReactionEstablishmentGateRecord)
            for record in self.expected_records
        ):
            raise TypeError("成立 Gate expected_records 必须全部是 ReactionEstablishmentGateRecord")
        if any(
            not isinstance(record, ReactionEstablishmentGateRecord)
            for record in self.replacement_records
        ):
            msg = "成立 Gate replacement_records 必须全部是 ReactionEstablishmentGateRecord"
            raise TypeError(msg)
        expected_records = tuple(sorted(self.expected_records, key=lambda record: record.slot_key))
        replacement_records = tuple(
            sorted(self.replacement_records, key=lambda record: record.slot_key)
        )
        expected_slots = tuple(record.slot_key for record in expected_records)
        replacement_slots = tuple(record.slot_key for record in replacement_records)
        if len(expected_slots) != len(set(expected_slots)):
            raise ValueError("成立 Gate expected_records 包含重复 slot")
        if len(replacement_slots) != len(set(replacement_slots)):
            raise ValueError("成立 Gate replacement_records 包含重复 slot")
        if not set(expected_slots).issubset(replacement_slots):
            raise ValueError("成立 Gate expected_records 必须对应 replacement_records")
        object.__setattr__(self, "resolutions", tuple(self.resolutions))
        object.__setattr__(self, "expected_records", expected_records)
        object.__setattr__(self, "replacement_records", replacement_records)


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateCommitReceipt:
    plan: ReactionEstablishmentGateMutationPlan
    version: int


@dataclass(frozen=True, slots=True)
class ReactionEstablishmentGateSnapshot:
    frame: int
    version: int
    records: tuple[ReactionEstablishmentGateRecord, ...]


class _ReactionEstablishmentGateRuntime(Protocol):
    _establishment_gate_records: dict[
        ReactionEstablishmentGateSlotKey,
        ReactionEstablishmentGateRecord,
    ]

    @property
    def version(self) -> int: ...

    def establishment_gate_definition(
        self,
        gate_definition_key: str,
    ) -> ReactionEstablishmentGateDefinition: ...


class ReactionEstablishmentGatePlanner:
    """同一 batch 内使用虚拟 Gate 投影确定唯一允许的成立请求。"""

    def __init__(
        self,
        runtime: _ReactionEstablishmentGateRuntime,
        frame: int,
        operation_id: str,
    ) -> None:
        self._runtime = runtime
        self.frame = frame
        self.operation_id = operation_id
        self._working = dict(runtime._establishment_gate_records)
        self._original = dict(runtime._establishment_gate_records)
        self._expected_store_version = runtime.version
        self._resolutions: list[ReactionEstablishmentGateResolution] = []
        self._sealed = False

    def prepare(
        self,
        request: ReactionEstablishmentGateRequest,
    ) -> ReactionEstablishmentGateResolution:
        if self._sealed:
            raise RuntimeError("ReactionEstablishmentGatePlanner 已封存")
        if request.frame != self.frame:
            raise ValueError("成立 Gate 请求帧与所属批次不一致")
        if any(item.gate_request_ref == request.gate_request_ref for item in self._resolutions):
            raise ValueError(f"重复的成立 Gate 请求：{request.gate_request_ref}")
        if (
            self._runtime.establishment_gate_definition(request.definition.gate_definition_key)
            != request.definition
        ):
            raise ValueError("成立 Gate 请求引用的定义未注册或不一致")

        before = self._working.get(request.slot_key)
        definition = request.definition
        if (
            before is not None
            and request.frame < before.ready_frame
            and before.accepted_count >= definition.max_occurrences
        ):
            resolution = ReactionEstablishmentGateResolution(
                resolution_ref=f"{request.gate_request_ref}:resolution",
                gate_request_ref=request.gate_request_ref,
                frame=request.frame,
                slot_key=request.slot_key,
                occurrence_ref=request.occurrence_ref,
                decision=ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED,
                reason="window_limit_reached",
                window_started_frame_before=before.window_started_frame,
                window_started_frame_after=before.window_started_frame,
                ready_frame_before=before.ready_frame,
                ready_frame_after=before.ready_frame,
                accepted_count_before=before.accepted_count,
                accepted_count_after=before.accepted_count,
                window_frames=definition.window_frames,
                max_occurrences=definition.max_occurrences,
            )
            self._resolutions.append(resolution)
            return resolution

        if before is None or request.frame >= before.ready_frame:
            record = ReactionEstablishmentGateRecord(
                slot_key=request.slot_key,
                window_started_frame=request.frame,
                ready_frame=request.frame + definition.window_frames,
                accepted_count=1,
                last_accepted_frame=request.frame,
                last_occurrence_ref=request.occurrence_ref,
                revision=1 if before is None else before.revision + 1,
            )
        else:
            record = ReactionEstablishmentGateRecord(
                slot_key=request.slot_key,
                window_started_frame=before.window_started_frame,
                ready_frame=before.ready_frame,
                accepted_count=before.accepted_count + 1,
                last_accepted_frame=request.frame,
                last_occurrence_ref=request.occurrence_ref,
                revision=before.revision + 1,
            )
        self._working[request.slot_key] = record
        resolution = ReactionEstablishmentGateResolution(
            resolution_ref=f"{request.gate_request_ref}:resolution",
            gate_request_ref=request.gate_request_ref,
            frame=request.frame,
            slot_key=request.slot_key,
            occurrence_ref=request.occurrence_ref,
            decision=ReactionEstablishmentGateDecision.ALLOWED,
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
            max_occurrences=definition.max_occurrences,
        )
        self._resolutions.append(resolution)
        return resolution

    def seal(self) -> ReactionEstablishmentGateMutationPlan:
        if self._sealed:
            raise RuntimeError("ReactionEstablishmentGatePlanner 已封存")
        self._sealed = True
        changed_keys = tuple(
            sorted(
                key for key, record in self._working.items() if self._original.get(key) != record
            )
        )
        return ReactionEstablishmentGateMutationPlan(
            operation_id=self.operation_id,
            frame=self.frame,
            expected_store_version=self._expected_store_version,
            resolutions=tuple(self._resolutions),
            expected_records=tuple(
                self._original[key] for key in changed_keys if key in self._original
            ),
            replacement_records=tuple(self._working[key] for key in changed_keys),
        )
