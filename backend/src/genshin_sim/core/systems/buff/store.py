from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.buff.enums import BuffLifecycleState
from genshin_sim.core.systems.buff.errors import (
    BuffInstanceNotFoundError,
    BuffPlanConflictError,
    BuffValidationError,
)
from genshin_sim.core.systems.buff.models import (
    BuffInstanceRef,
    BuffMutationPlan,
    BuffRecord,
    validate_frame,
)


class BuffStore:
    """完整 BuffRecord 的唯一状态所有者。"""

    __slots__ = (
        "_committed_operations",
        "_committed_request_ids",
        "_next_sequence",
        "_records",
        "_version",
    )

    def __init__(self, records: Iterable[BuffRecord] = ()) -> None:
        self._records: dict[BuffInstanceRef, BuffRecord] = {}
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
    def records(self) -> tuple[BuffRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.instance_ref))

    @property
    def active_records(self) -> tuple[BuffRecord, ...]:
        return tuple(
            record for record in self.records if record.lifecycle_state is BuffLifecycleState.ACTIVE
        )

    def allocate_ref(self) -> BuffInstanceRef:
        ref = BuffInstanceRef(self._next_sequence)
        self._next_sequence += 1
        return ref

    def get(self, instance_ref: BuffInstanceRef) -> BuffRecord | None:
        return self._records.get(instance_ref)

    def require(self, instance_ref: BuffInstanceRef) -> BuffRecord:
        record = self.get(instance_ref)
        if record is None:
            raise BuffInstanceNotFoundError(f"Buff 实例不存在：{instance_ref}")
        return record

    def add(self, record: BuffRecord) -> BuffRecord:
        if not isinstance(record, BuffRecord):
            raise BuffValidationError("record 必须是 BuffRecord")
        if record.instance_ref in self._records:
            raise BuffValidationError(f"Buff 实例引用重复：{record.instance_ref}")
        self._records[record.instance_ref] = record
        self._next_sequence = max(self._next_sequence, record.instance_ref.sequence + 1)
        self._version += 1
        return record

    def active(
        self,
        frame: int,
        target_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[BuffRecord, ...]:
        validate_frame(frame)
        return tuple(
            record
            for record in self.records
            if record.is_active_at(frame)
            and (target_ref is None or record.state.target_ref == target_ref)
            and (definition_key is None or record.definition.definition_key == definition_key)
            and (mechanic_key is None or record.definition.mechanic_key == mechanic_key)
        )

    def due_at(self, frame: int) -> tuple[BuffRecord, ...]:
        validate_frame(frame)
        return tuple(record for record in self.active_records if record.expires_at_frame <= frame)

    def conflicts(
        self,
        target_ref: AttributeSubjectRef,
        conflict_key: str,
        frame: int,
    ) -> tuple[BuffRecord, ...]:
        return tuple(
            record
            for record in self.active(frame, target_ref=target_ref)
            if record.definition.conflict_key == conflict_key
        )

    def validate(self, plan: BuffMutationPlan) -> None:
        if plan.operation_id in self._committed_operations:
            raise BuffPlanConflictError(f"Buff 计划已提交：{plan.operation_id}")
        duplicate_request_ids = self._committed_request_ids.intersection(plan.request_ids)
        if duplicate_request_ids:
            request_id = sorted(duplicate_request_ids)[0]
            raise BuffPlanConflictError(f"Buff request_id 已提交：{request_id}")
        if plan.expected_store_version != self._version:
            raise BuffPlanConflictError(
                "Buff Store 版本冲突："
                f"expected={plan.expected_store_version}, actual={self._version}"
            )
        expected_refs = {record.instance_ref for record in plan.expected_records}
        for expected in plan.expected_records:
            if self._records.get(expected.instance_ref) != expected:
                raise BuffPlanConflictError(f"Buff 记录前值冲突：{expected.instance_ref}")
        for replacement in plan.replacement_records:
            if (
                replacement.instance_ref in self._records
                and replacement.instance_ref not in expected_refs
            ):
                raise BuffPlanConflictError(
                    f"Buff replacement 缺少完整前值：{replacement.instance_ref}"
                )

    def commit_prevalidated(self, plan: BuffMutationPlan) -> None:
        # 所有可能产生领域错误的判断必须在显式 validate 阶段完成。
        for record in plan.replacement_records:
            self._records[record.instance_ref] = record
        if plan.replacement_records:
            self._version += 1
        self._committed_operations.add(plan.operation_id)
        self._committed_request_ids.update(plan.request_ids)


class BuffStoreReader:
    """只向 provider 和 content 只读协议暴露活动记录查询。"""

    __slots__ = ("_store",)

    def __init__(self, store: BuffStore) -> None:
        self._store = store

    def active(
        self,
        frame: int,
        target_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[BuffRecord, ...]:
        return self._store.active(
            frame,
            target_ref=target_ref,
            definition_key=definition_key,
            mechanic_key=mechanic_key,
        )
