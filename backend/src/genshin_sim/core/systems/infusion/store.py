from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.infusion.enums import (
    InfusionLifecycleState,
    InfusionMode,
)
from genshin_sim.core.systems.infusion.errors import (
    InfusionInstanceNotFoundError,
    InfusionPlanConflictError,
    InfusionValidationError,
)
from genshin_sim.core.systems.infusion.models import (
    InfusionInstanceRef,
    InfusionMutationPlan,
    InfusionRecord,
    validate_frame,
)


class InfusionStore:
    """活动附魔与转化记录的完整状态所有者。"""

    __slots__ = (
        "_committed_operations",
        "_committed_request_ids",
        "_next_sequence",
        "_records",
        "_version",
    )

    def __init__(self, records: Iterable[InfusionRecord] = ()) -> None:
        self._records: dict[InfusionInstanceRef, InfusionRecord] = {}
        self._next_sequence = 1
        self._version = 0
        self._committed_operations: set[str] = set()
        self._committed_request_ids: set[str] = set()
        for record in records:
            self.add(record)

    @property
    def version(self) -> int:
        return self._version

    @property
    def records(self) -> tuple[InfusionRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.instance_ref))

    @property
    def active_records(self) -> tuple[InfusionRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.lifecycle_state is InfusionLifecycleState.ACTIVE
        )

    def allocate_ref(self) -> InfusionInstanceRef:
        ref = InfusionInstanceRef(self._next_sequence)
        self._next_sequence += 1
        return ref

    def get(self, instance_ref: InfusionInstanceRef) -> InfusionRecord | None:
        return self._records.get(instance_ref)

    def require(self, instance_ref: InfusionInstanceRef) -> InfusionRecord:
        record = self.get(instance_ref)
        if record is None:
            raise InfusionInstanceNotFoundError(f"附魔实例不存在：{instance_ref}")
        return record

    def add(self, record: InfusionRecord) -> InfusionRecord:
        if not isinstance(record, InfusionRecord):
            raise InfusionValidationError("record 必须是 InfusionRecord")
        if record.instance_ref in self._records:
            raise InfusionValidationError(f"附魔实例引用重复：{record.instance_ref}")
        self._records[record.instance_ref] = record
        self._next_sequence = max(self._next_sequence, record.instance_ref.sequence + 1)
        self._version += 1
        return record

    def active(
        self,
        frame: int,
        character_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
        mode: InfusionMode | None = None,
        element: Element | None = None,
    ) -> tuple[InfusionRecord, ...]:
        validate_frame(frame)
        return tuple(
            record
            for record in self.records
            if record.is_active_at(frame)
            and (character_ref is None or record.character_ref == character_ref)
            and (definition_key is None or record.definition.definition_key == definition_key)
            and (mechanic_key is None or record.definition.mechanic_key == mechanic_key)
            and (mode is None or record.mode == mode)
            and (element is None or record.element == element)
        )

    def due_at(self, frame: int) -> tuple[InfusionRecord, ...]:
        validate_frame(frame)
        return tuple(record for record in self.active_records if record.expires_at_frame <= frame)

    def validate(self, plan: InfusionMutationPlan) -> None:
        if plan.operation_id in self._committed_operations:
            raise InfusionPlanConflictError(f"附魔计划已提交：{plan.operation_id}")
        duplicate_request_ids = self._committed_request_ids.intersection(plan.request_ids)
        if duplicate_request_ids:
            request_id = sorted(duplicate_request_ids)[0]
            raise InfusionPlanConflictError(f"附魔 request_id 已提交：{request_id}")
        if plan.expected_store_version != self._version:
            raise InfusionPlanConflictError(
                "附魔 Store 版本冲突："
                f"expected={plan.expected_store_version}, actual={self._version}"
            )
        expected_refs = {record.instance_ref for record in plan.expected_records}
        for expected in plan.expected_records:
            if self._records.get(expected.instance_ref) != expected:
                raise InfusionPlanConflictError(f"附魔记录前值冲突：{expected.instance_ref}")
        for replacement in plan.replacement_records:
            if (
                replacement.instance_ref in self._records
                and replacement.instance_ref not in expected_refs
            ):
                raise InfusionPlanConflictError(
                    f"附魔 replacement 缺少完整前值：{replacement.instance_ref}"
                )

    def commit_prevalidated(self, plan: InfusionMutationPlan) -> None:
        # 所有可能产生领域错误的判断必须在显式 validate 阶段完成。
        for record in plan.replacement_records:
            self._records[record.instance_ref] = record
        if plan.replacement_records:
            self._version += 1
        self._committed_operations.add(plan.operation_id)
        self._committed_request_ids.update(plan.request_ids)


class InfusionStoreReader:
    """只向只读协议暴露活动记录查询。"""

    __slots__ = ("_store",)

    def __init__(self, store: InfusionStore) -> None:
        self._store = store

    def active(
        self,
        frame: int,
        character_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
        mode: InfusionMode | None = None,
        element: Element | None = None,
    ) -> tuple[InfusionRecord, ...]:
        return self._store.active(
            frame,
            character_ref=character_ref,
            definition_key=definition_key,
            mechanic_key=mechanic_key,
            mode=mode,
            element=element,
        )
