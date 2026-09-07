from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from genshin_sim.core.attributes.errors import AttributeValidationError
from genshin_sim.core.attributes.keys import AttributeKey


def validate_finite_float(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AttributeValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise AttributeValidationError(f"{field_name} 必须是有限数字")
    return result


def normalize_zero(value: float) -> float:
    if value == 0.0:
        return 0.0
    return value


class AttributeSubjectKind(StrEnum):
    CHARACTER = "character"
    TARGET = "target"


class RuntimeSourceKind(StrEnum):
    ASSET = "asset"
    CONFIG = "config"
    ACTION = "action"
    MECHANIC = "mechanic"
    CONTENT = "content"
    SYSTEM = "system"


class ModifierStage(StrEnum):
    BASE_ADD = "base_add"
    PERCENT_ADD = "percent_add"
    FLAT_ADD = "flat_add"
    FINAL_MULTIPLIER = "final_multiplier"
    OVERRIDE = "override"


class TraceLevel(StrEnum):
    NONE = "none"
    APPLIED = "applied"
    FULL = "full"


class ProviderAttributeSubjectScope(StrEnum):
    QUERY_SUBJECT = "query_subject"
    QUERY_TARGET = "query_target"
    PROVIDER_OWNER = "provider_owner"


@dataclass(frozen=True, slots=True)
class AttributeSubjectRef:
    kind: AttributeSubjectKind
    entity_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AttributeSubjectKind):
            raise AttributeValidationError("属性主体 kind 不受支持")
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise AttributeValidationError("属性主体 entity_id 必须是非空字符串")

    @classmethod
    def character(cls, entity_id: str) -> AttributeSubjectRef:
        return cls(AttributeSubjectKind.CHARACTER, entity_id)

    @classmethod
    def target(cls, entity_id: str) -> AttributeSubjectRef:
        return cls(AttributeSubjectKind.TARGET, entity_id)

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "entity_id": self.entity_id}


@dataclass(frozen=True, slots=True)
class RuntimeSourceRef:
    kind: RuntimeSourceKind
    source_key: str
    instance_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimeSourceKind):
            raise AttributeValidationError("属性来源 kind 不受支持")
        if not isinstance(self.source_key, str) or not self.source_key.strip():
            raise AttributeValidationError("属性来源 source_key 必须是非空字符串")
        if self.instance_id is not None and not self.instance_id.strip():
            raise AttributeValidationError("属性来源 instance_id 提供时必须是非空字符串")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind.value,
            "source_key": self.source_key,
            "instance_id": self.instance_id,
        }


@dataclass(frozen=True, slots=True)
class AttributeQueryContext:
    tags: frozenset[str] = frozenset()
    source_ref: RuntimeSourceRef | None = None
    target_ref: AttributeSubjectRef | None = None

    def __post_init__(self) -> None:
        tags = frozenset(self.tags)
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                raise AttributeValidationError("属性查询标签必须是非空字符串")
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class AttributeQuery:
    subject_ref: AttributeSubjectRef
    attribute_key: AttributeKey
    frame: int
    context: AttributeQueryContext = field(default_factory=AttributeQueryContext)

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise AttributeValidationError("属性查询 frame 必须是非负整数")


@dataclass(frozen=True, slots=True)
class AttributeResolveOptions:
    trace_level: TraceLevel = TraceLevel.FULL

    def __post_init__(self) -> None:
        if not isinstance(self.trace_level, TraceLevel):
            raise AttributeValidationError("trace_level 不受支持")


@dataclass(frozen=True, slots=True)
class BaseAttributeContribution:
    attribute_key: AttributeKey
    value: float
    source_ref: RuntimeSourceRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_finite_float(self.value, "基础属性贡献 value"))


@dataclass(frozen=True, slots=True)
class ModifierTerm:
    target_key: AttributeKey
    stage: ModifierStage
    value: float
    provider_key: str
    source_ref: RuntimeSourceRef
    stacking_group: str | None = None
    audit_tags: tuple[str, ...] = ()
    # provider 显示名：由收集器从 ModifierProviderSpec.display_name 注入，内容未提供时为 None。
    provider_display_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ModifierStage):
            raise AttributeValidationError("modifier stage 不受支持")
        object.__setattr__(self, "value", validate_finite_float(self.value, "modifier value"))
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise AttributeValidationError("provider_key 必须是非空字符串")
        if self.stacking_group is not None and not self.stacking_group.strip():
            raise AttributeValidationError("stacking_group 提供时必须是非空字符串")
        for tag in self.audit_tags:
            if not isinstance(tag, str) or not tag.strip():
                raise AttributeValidationError("audit_tags 必须是非空字符串")
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))

    def to_dict(self) -> dict[str, object]:
        return {
            "target_key": self.target_key.value,
            "stage": self.stage.value,
            "value": self.value,
            "provider_key": self.provider_key,
            "provider_display_name": self.provider_display_name,
            "source_ref": self.source_ref.to_dict(),
            "stacking_group": self.stacking_group,
            "audit_tags": tuple(self.audit_tags),
        }


@dataclass(frozen=True, slots=True)
class ProviderAttributeRead:
    attribute_key: AttributeKey
    subject_scope: ProviderAttributeSubjectScope = ProviderAttributeSubjectScope.QUERY_SUBJECT

    def __post_init__(self) -> None:
        if not isinstance(self.subject_scope, ProviderAttributeSubjectScope):
            raise AttributeValidationError("provider 读取主体范围不受支持")


@dataclass(frozen=True, slots=True)
class ModifierProviderSpec:
    provider_key: str
    reads: tuple[ProviderAttributeRead, ...] = ()
    writes: frozenset[AttributeKey] = frozenset()
    private_namespace: str | None = None
    owner_ref: AttributeSubjectRef | None = None
    # provider 显示名；由内容层提供，属性解析收集器注入返回 term 的审计。
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise AttributeValidationError("provider_key 必须是非空字符串")
        object.__setattr__(self, "reads", tuple(self.reads))
        object.__setattr__(self, "writes", frozenset(self.writes))
        if self.private_namespace is not None and not self.private_namespace.strip():
            raise AttributeValidationError("private_namespace 提供时必须是非空字符串")
        if self.display_name is not None and (
            not isinstance(self.display_name, str) or not self.display_name.strip()
        ):
            raise AttributeValidationError("provider display_name 提供时必须是非空字符串")


@dataclass(frozen=True, slots=True)
class AttributeResolution:
    attribute_key: AttributeKey
    subject_ref: AttributeSubjectRef
    final_value: float
    base_value: float
    applied_terms: tuple[ModifierTerm, ...]
    rejected_terms: tuple[ModifierTerm, ...]
    dependency_resolutions: tuple[AttributeResolution, ...]
    policy_key: str
    trace_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "final_value",
            validate_finite_float(self.final_value, "final_value"),
        )
        object.__setattr__(self, "base_value", validate_finite_float(self.base_value, "base_value"))
        object.__setattr__(self, "applied_terms", tuple(self.applied_terms))
        object.__setattr__(self, "rejected_terms", tuple(self.rejected_terms))
        object.__setattr__(self, "dependency_resolutions", tuple(self.dependency_resolutions))
        object.__setattr__(self, "trace_metadata", MappingProxyType(dict(self.trace_metadata)))

    def to_dict(self) -> dict[str, object]:
        """返回完整属性解析审计；递归依赖完整保存，不截断。"""

        return {
            "attribute_key": self.attribute_key.value,
            "subject_ref": self.subject_ref.to_dict(),
            "final_value": self.final_value,
            "base_value": self.base_value,
            "applied_terms": tuple(term.to_dict() for term in self.applied_terms),
            "rejected_terms": tuple(term.to_dict() for term in self.rejected_terms),
            "dependency_resolutions": tuple(
                resolution.to_dict() for resolution in self.dependency_resolutions
            ),
            "policy_key": self.policy_key,
            "trace_metadata": dict(self.trace_metadata),
        }


@dataclass(frozen=True, slots=True)
class AttributeSnapshotEntry:
    attribute_key: AttributeKey
    context: AttributeQueryContext
    value: float
    applied_terms: tuple[ModifierTerm, ...] = ()
    rejected_terms: tuple[ModifierTerm, ...] = ()
    dependency_trace: tuple[AttributeResolution, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_finite_float(self.value, "snapshot value"))
        object.__setattr__(self, "applied_terms", tuple(self.applied_terms))
        object.__setattr__(self, "rejected_terms", tuple(self.rejected_terms))
        object.__setattr__(self, "dependency_trace", tuple(self.dependency_trace))


@dataclass(frozen=True, slots=True)
class AttributeSnapshot:
    snapshot_id: str
    frame: int
    subject_ref: AttributeSubjectRef
    entries: tuple[AttributeSnapshotEntry, ...]
    trace_level: TraceLevel = TraceLevel.APPLIED

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise AttributeValidationError("snapshot_id 必须是非空字符串")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise AttributeValidationError("snapshot frame 必须是非负整数")
        if not isinstance(self.trace_level, TraceLevel):
            raise AttributeValidationError("snapshot trace_level 不受支持")
        object.__setattr__(self, "entries", tuple(self.entries))
