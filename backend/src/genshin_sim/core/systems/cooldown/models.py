from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from genshin_sim.core.systems.cooldown.enums import (
    AbilityKind,
    CooldownConditionReason,
    CooldownDurationMode,
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownFactKind,
    CooldownMutationReason,
    CooldownSubjectType,
)
from genshin_sim.core.systems.cooldown.errors import (
    CooldownDurationResolutionError,
    CooldownInvariantError,
    CooldownValidationError,
)
from genshin_sim.core.systems.cooldown.policies import validate_term_policy


def validate_frame(value: int, name: str = "frame") -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CooldownValidationError(f"{name} 必须是非负整数")


def validate_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CooldownValidationError(f"{name} 必须是非空且无首尾空白的字符串")


def validate_non_negative_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CooldownValidationError(f"{name} 必须是非负整数")


def decimal_value(value: Decimal | float | int, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal | float | int):
        raise CooldownDurationResolutionError(f"{name} 必须是有限数字")
    if isinstance(value, float) and not math.isfinite(value):
        raise CooldownDurationResolutionError(f"{name} 必须是有限数字")
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise CooldownDurationResolutionError(f"{name} 必须是有限数字")
    return result


@dataclass(frozen=True, slots=True)
class CooldownSubjectRef:
    subject_type: CooldownSubjectType
    subject_id: str

    def __post_init__(self) -> None:
        if self.subject_type is not CooldownSubjectType.CHARACTER:
            raise CooldownValidationError("冷却系统目前只支持角色主体")
        validate_text(self.subject_id, "subject_id")

    @classmethod
    def character(cls, subject_id: str) -> CooldownSubjectRef:
        return cls(CooldownSubjectType.CHARACTER, subject_id)


@dataclass(frozen=True, slots=True)
class CooldownKey:
    subject: CooldownSubjectRef
    ability_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.subject, CooldownSubjectRef):
            raise CooldownValidationError("subject 必须是 CooldownSubjectRef")
        validate_text(self.ability_key, "ability_key")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.subject.subject_type.value, self.subject.subject_id, self.ability_key)


@dataclass(frozen=True, slots=True)
class CooldownDefinition:
    key: CooldownKey
    ability_kind: AbilityKind
    base_duration_frames: int
    max_charges: int
    duration_mode: CooldownDurationMode
    source_ref: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.key, CooldownKey) or not isinstance(self.ability_kind, AbilityKind):
            raise CooldownValidationError("冷却定义 key 或 ability_kind 非法")
        if not isinstance(self.duration_mode, CooldownDurationMode):
            raise CooldownValidationError("duration_mode 非法")
        validate_non_negative_int(self.base_duration_frames, "base_duration_frames")
        if (
            isinstance(self.max_charges, bool)
            or not isinstance(self.max_charges, int)
            or self.max_charges <= 0
        ):
            raise CooldownValidationError("max_charges 必须是正整数")
        validate_text(self.source_ref, "source_ref")
        tags = tuple(sorted(set(self.tags)))
        for tag in tags:
            validate_text(tag, "tag")
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class CooldownDurationTerm:
    term_key: str
    source_ref: str
    stage: CooldownDurationStage
    operation: CooldownDurationOperation
    value: Decimal | float | int
    reference_stage: CooldownDurationStage | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        validate_text(self.term_key, "term_key")
        validate_text(self.source_ref, "source_ref")
        if not isinstance(self.stage, CooldownDurationStage) or not isinstance(
            self.operation, CooldownDurationOperation
        ):
            raise CooldownDurationResolutionError("冷却时长 term 的 stage 或 operation 非法")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise CooldownDurationResolutionError("priority 必须是整数")
        value = decimal_value(self.value, "term value")
        if self.operation is CooldownDurationOperation.MULTIPLY_CURRENT and value < 0:
            raise CooldownDurationResolutionError("MULTIPLY_CURRENT 的倍率不能为负")
        validate_term_policy(self.stage, self.operation, self.reference_stage)
        object.__setattr__(self, "value", value)

    @property
    def sort_key(self) -> tuple[int, str, str]:
        return (self.priority, self.term_key, self.source_ref)


@dataclass(frozen=True, slots=True)
class CooldownDurationResolution:
    base_duration_frames: int
    resolved_duration_frames: int
    terms: tuple[CooldownDurationTerm, ...]
    stage_totals: tuple[tuple[CooldownDurationStage, Decimal], ...]
    rounded_from: Decimal | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActiveRecovery:
    started_frame: int
    ready_frame: int
    interval_frames: int
    chain_id: str
    start_source_ref: str
    duration_audit: CooldownDurationResolution

    def __post_init__(self) -> None:
        validate_frame(self.started_frame, "started_frame")
        validate_frame(self.ready_frame, "ready_frame")
        validate_non_negative_int(self.interval_frames, "interval_frames")
        if self.ready_frame != self.started_frame + self.interval_frames:
            raise CooldownInvariantError("ready_frame 必须等于 started_frame + interval_frames")
        validate_text(self.chain_id, "chain_id")
        validate_text(self.start_source_ref, "start_source_ref")


@dataclass(frozen=True, slots=True)
class CooldownRecord:
    key: CooldownKey
    ability_kind: AbilityKind
    max_charges: int
    available_charges: int
    active_recovery: ActiveRecovery | None = None
    queued_recoveries: int = 0
    revision: int = 0
    last_changed_frame: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.key, CooldownKey) or not isinstance(self.ability_kind, AbilityKind):
            raise CooldownInvariantError("冷却记录 key 或 ability_kind 非法")
        for name in ("max_charges", "available_charges", "queued_recoveries", "revision"):
            validate_non_negative_int(getattr(self, name), name)
        validate_frame(self.last_changed_frame, "last_changed_frame")
        if self.max_charges <= 0 or self.available_charges > self.max_charges:
            raise CooldownInvariantError("available_charges 越界")
        if (
            self.available_charges + self.queued_recoveries + int(self.active_recovery is not None)
            != self.max_charges
        ):
            raise CooldownInvariantError("冷却次数不守恒")


@dataclass(frozen=True, slots=True)
class CooldownQuery:
    key: CooldownKey
    frame: int

    def __post_init__(self) -> None:
        validate_frame(self.frame)


@dataclass(frozen=True, slots=True)
class CooldownView:
    key: CooldownKey
    ability_kind: AbilityKind
    max_charges: int
    available_charges: int
    active_ready_frame: int | None
    remaining_frames: int
    queued_recoveries: int
    chain_id: str | None
    revision: int


@dataclass(frozen=True, slots=True)
class CooldownConditionResult:
    query: CooldownQuery
    satisfied: bool
    reason: CooldownConditionReason
    view: CooldownView


@dataclass(frozen=True, slots=True)
class StartCooldownRequest:
    request_id: str
    key: CooldownKey
    frame: int
    source_ref: str
    requested_base_duration_frames: int | None = None
    duration_terms: tuple[CooldownDurationTerm, ...] = ()

    def __post_init__(self) -> None:
        validate_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_text(self.source_ref, "source_ref")
        if self.requested_base_duration_frames is not None:
            validate_non_negative_int(
                self.requested_base_duration_frames, "requested_base_duration_frames"
            )
        object.__setattr__(self, "duration_terms", tuple(self.duration_terms))


@dataclass(frozen=True, slots=True)
class ReduceRemainingCooldownRequest:
    request_id: str
    key: CooldownKey
    frame: int
    reduction_frames: int
    source_ref: str

    def __post_init__(self) -> None:
        validate_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_non_negative_int(self.reduction_frames, "reduction_frames")
        validate_text(self.source_ref, "source_ref")


@dataclass(frozen=True, slots=True)
class ResetActiveCooldownRequest:
    request_id: str
    key: CooldownKey
    frame: int
    source_ref: str

    def __post_init__(self) -> None:
        validate_text(self.request_id, "request_id")
        validate_frame(self.frame)
        validate_text(self.source_ref, "source_ref")


@dataclass(frozen=True, slots=True)
class CooldownFact:
    fact_id: str
    fact_kind: CooldownFactKind
    frame: int
    key: CooldownKey
    operation_id: str
    chain_id: str | None
    before_available_charges: int
    after_available_charges: int
    active_ready_frame: int | None
    queued_recoveries: int
    source_ref: str
    duration_audit: CooldownDurationResolution | None = None
    before_record: CooldownRecord | None = None
    after_record: CooldownRecord | None = None

    @property
    def sort_key(self) -> tuple[int, tuple[str, str, str], str, str]:
        order = {
            CooldownFactKind.STARTED: 0,
            CooldownFactKind.REDUCED: 1,
            CooldownFactKind.RESET: 2,
            CooldownFactKind.CHARGE_RECOVERED: 3,
            CooldownFactKind.CHAIN_COMPLETED: 4,
        }[self.fact_kind]
        return (self.frame, self.key.sort_key, f"{order:02d}", self.operation_id)


@dataclass(frozen=True, slots=True)
class CooldownMutationPlan:
    request_id: str
    key: CooldownKey
    expected_store_revision: int
    expected_record_revision: int
    before: CooldownRecord
    after: CooldownRecord
    facts: tuple[CooldownFact, ...]
    resolution: CooldownDurationResolution | None = None
    reused_chain_resolution: bool = False
    ignored_reason: CooldownMutationReason | None = None


@dataclass(frozen=True, slots=True)
class PrepareStartCooldownResult:
    condition: CooldownConditionResult
    plan: CooldownMutationPlan | None


@dataclass(frozen=True, slots=True)
class CooldownMutationResult:
    request_id: str
    key: CooldownKey
    applied: bool
    reason: CooldownMutationReason | None
    before: CooldownRecord
    after: CooldownRecord
    facts: tuple[CooldownFact, ...]
    resolution: CooldownDurationResolution | None = None
    reused_chain_resolution: bool = False


CooldownMutationRequest = (
    StartCooldownRequest | ReduceRemainingCooldownRequest | ResetActiveCooldownRequest
)


@dataclass(frozen=True, slots=True)
class CooldownMutationBatchRequest:
    batch_id: str
    frame: int
    requests: tuple[CooldownMutationRequest, ...]

    def __post_init__(self) -> None:
        validate_text(self.batch_id, "batch_id")
        validate_frame(self.frame)
        object.__setattr__(self, "requests", tuple(self.requests))
        if not self.requests:
            raise CooldownValidationError("batch requests 不能为空")
        if any(request.frame != self.frame for request in self.requests):
            raise CooldownValidationError("batch 中所有请求必须使用 batch frame")


@dataclass(frozen=True, slots=True)
class CooldownMutationBatchPlan:
    batch_id: str
    frame: int
    expected_store_revision: int
    item_plans: tuple[CooldownMutationPlan, ...]
    facts: tuple[CooldownFact, ...]


@dataclass(frozen=True, slots=True)
class CooldownMutationBatchResult:
    batch_id: str
    frame: int
    item_results: tuple[CooldownMutationResult, ...]
    facts: tuple[CooldownFact, ...]


@dataclass(frozen=True, slots=True)
class NormalizeCooldownsResult:
    frame: int
    changed_records: tuple[CooldownRecord, ...]
    facts: tuple[CooldownFact, ...]
