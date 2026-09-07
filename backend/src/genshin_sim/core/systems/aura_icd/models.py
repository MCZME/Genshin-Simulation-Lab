"""元素附着 ICD 的定义、运行态记录和批量计划。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.elements import AuraAmount, ElementalSubjectRef
from genshin_sim.core.systems.aura_icd.enums import IcdOutcome


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _frame(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, slots=True)
class IcdDefinition:
    sequence_key: str
    reset_interval_frames: int
    application_sequence: tuple[AuraAmount, ...]

    def __post_init__(self) -> None:
        _text(self.sequence_key, "sequence_key")
        if (
            isinstance(self.reset_interval_frames, bool)
            or not isinstance(self.reset_interval_frames, int)
            or self.reset_interval_frames <= 0
        ):
            raise ValueError("reset_interval_frames 必须是正整数")
        sequence = tuple(self.application_sequence)
        if not sequence:
            raise ValueError("application_sequence 不能为空")
        object.__setattr__(self, "application_sequence", sequence)


class IcdDefinitionRegistry:
    """组装后冻结的 ICD Definition 注册表。"""

    def __init__(self, definitions: tuple[IcdDefinition, ...] = ()) -> None:
        self._definitions: dict[str, IcdDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: IcdDefinition) -> None:
        if definition.sequence_key in self._definitions:
            raise ValueError(f"重复的 ICD Definition：{definition.sequence_key}")
        self._definitions[definition.sequence_key] = definition

    def require(self, sequence_key: str) -> IcdDefinition:
        try:
            return self._definitions[sequence_key]
        except KeyError as exc:
            raise KeyError(f"未注册的 ICD Definition：{sequence_key}") from exc

    @property
    def definitions(self) -> tuple[IcdDefinition, ...]:
        return tuple(sorted(self._definitions.values(), key=lambda item: item.sequence_key))


@dataclass(frozen=True, slots=True)
class IcdBinding:
    tag_key: str
    sequence_key: str

    def __post_init__(self) -> None:
        _text(self.tag_key, "tag_key")
        _text(self.sequence_key, "sequence_key")


@dataclass(frozen=True, order=True, slots=True)
class AuraIcdAttackerRef:
    scope_key: str

    def __post_init__(self) -> None:
        _text(self.scope_key, "scope_key")

    def to_dict(self) -> dict[str, str]:
        return {"scope_key": self.scope_key}


@dataclass(frozen=True, order=True, slots=True)
class IcdKey:
    attacker_ref: AuraIcdAttackerRef
    defender_ref: ElementalSubjectRef
    tag_key: str
    sequence_key: str

    def __post_init__(self) -> None:
        _text(self.tag_key, "tag_key")
        _text(self.sequence_key, "sequence_key")

    def to_dict(self) -> dict[str, object]:
        return {
            "attacker_ref": self.attacker_ref.to_dict(),
            "defender_ref": self.defender_ref.to_dict(),
            "tag_key": self.tag_key,
            "sequence_key": self.sequence_key,
        }


@dataclass(frozen=True, slots=True)
class IcdImpactRequest:
    request_id: str
    impact_ref: str
    frame: int
    order: int
    attacker_ref: AuraIcdAttackerRef
    defender_ref: ElementalSubjectRef
    binding: IcdBinding | None = None

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.impact_ref, "impact_ref")
        _frame(self.frame, "frame")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")


@dataclass(frozen=True, slots=True)
class IcdRecord:
    key: IcdKey
    window_started_frame: int
    resets_at_frame: int
    next_sequence_index: int
    last_hit_frame: int
    revision: int = 0

    def __post_init__(self) -> None:
        _frame(self.window_started_frame, "window_started_frame")
        _frame(self.resets_at_frame, "resets_at_frame")
        _frame(self.last_hit_frame, "last_hit_frame")
        if self.resets_at_frame <= self.window_started_frame:
            raise ValueError("resets_at_frame 必须晚于窗口开始帧")
        if self.next_sequence_index < 0 or self.revision < 0:
            raise ValueError("ICD Record 游标和 revision 不能为负数")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key.to_dict(),
            "window_started_frame": self.window_started_frame,
            "resets_at_frame": self.resets_at_frame,
            "next_sequence_index": self.next_sequence_index,
            "last_hit_frame": self.last_hit_frame,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class IcdResolution:
    request_id: str
    impact_ref: str
    frame: int
    order: int
    attacker_ref: AuraIcdAttackerRef
    defender_ref: ElementalSubjectRef
    tag_key: str | None
    sequence_key: str | None
    outcome: IcdOutcome
    sequence_index: int | None
    coefficient: AuraAmount
    window_started_frame: int | None
    resets_at_frame: int | None
    before: IcdRecord | None
    after: IcdRecord | None

    @property
    def allows_application(self) -> bool:
        return not self.coefficient.is_zero


@dataclass(frozen=True, slots=True)
class IcdMutationPlan:
    operation_id: str
    frame: int
    request_ids: tuple[str, ...]
    expected_store_version: int
    replacements: tuple[IcdRecord, ...]
    removed_keys: tuple[IcdKey, ...]
    resolutions: tuple[IcdResolution, ...]


@dataclass(frozen=True, slots=True)
class IcdCommitReceipt:
    plan: IcdMutationPlan
    version: int


@dataclass(frozen=True, slots=True)
class IcdSnapshot:
    frame: int
    normalized_through_frame: int
    records: tuple[IcdRecord, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "normalized_through_frame": self.normalized_through_frame,
            "records": [record.to_dict() for record in self.records],
        }
