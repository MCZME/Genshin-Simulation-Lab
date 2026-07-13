from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.systems.shield.enums import ShieldLifecycleState
from genshin_sim.core.systems.shield.errors import (
    ShieldInstanceNotFoundError,
    ShieldPlanConflictError,
    ShieldValidationError,
)
from genshin_sim.core.systems.shield.models import (
    ShieldAbsorptionPlan,
    ShieldInstanceRef,
    ShieldMutationPlan,
    ShieldProtectionRef,
    ShieldRecord,
    validate_frame,
)


class ShieldStore:
    """护盾完整聚合的唯一状态所有者。"""

    __slots__ = ("_committed_operations", "_next_sequence", "_records", "_version")

    def __init__(self, records: Iterable[ShieldRecord] = ()) -> None:
        self._records: dict[ShieldInstanceRef, ShieldRecord] = {}
        self._next_sequence = 1
        self._version = 0
        self._committed_operations: set[str] = set()
        for record in records:
            self.add(record)

    @property
    def version(self) -> int:
        return self._version

    @property
    def records(self) -> tuple[ShieldRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.instance_ref))

    @property
    def active_records(self) -> tuple[ShieldRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.lifecycle_state is ShieldLifecycleState.ACTIVE
        )

    def allocate_ref(self) -> ShieldInstanceRef:
        ref = ShieldInstanceRef(self._next_sequence)
        self._next_sequence += 1
        return ref

    def get(self, instance_ref: ShieldInstanceRef) -> ShieldRecord | None:
        return self._records.get(instance_ref)

    def require(self, instance_ref: ShieldInstanceRef) -> ShieldRecord:
        record = self.get(instance_ref)
        if record is None:
            raise ShieldInstanceNotFoundError(f"护盾记录不存在：{instance_ref}")
        return record

    def add(self, record: ShieldRecord) -> ShieldRecord:
        if not isinstance(record, ShieldRecord):
            raise ShieldValidationError("record 必须是 ShieldRecord")
        if record.instance_ref in self._records:
            raise ShieldValidationError(f"护盾实例引用重复：{record.instance_ref}")
        self._records[record.instance_ref] = record
        self._next_sequence = max(self._next_sequence, record.instance_ref.sequence + 1)
        self._version += 1
        return record

    def replace(self, record: ShieldRecord) -> ShieldRecord:
        self.require(record.instance_ref)
        self._records[record.instance_ref] = record
        self._version += 1
        return record

    def active_for(
        self,
        protection_ref: ShieldProtectionRef,
        *,
        frame: int,
    ) -> tuple[ShieldRecord, ...]:
        return self.active(frame=frame, protection_ref=protection_ref)

    def active(
        self,
        *,
        frame: int,
        protection_ref: ShieldProtectionRef | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[ShieldRecord, ...]:
        validate_frame(frame)
        return tuple(
            record
            for record in self.records
            if record.is_active_at(frame)
            and (protection_ref is None or record.state.protection_ref == protection_ref)
            and (mechanic_key is None or record.mechanic_key == mechanic_key)
        )

    def due_at(self, frame: int) -> tuple[ShieldRecord, ...]:
        validate_frame(frame)
        return tuple(record for record in self.active_records if record.expires_at_frame <= frame)

    def conflicts(
        self,
        protection_ref: ShieldProtectionRef,
        conflict_key: str,
        *,
        frame: int,
    ) -> tuple[ShieldRecord, ...]:
        return tuple(
            record
            for record in self.active_for(protection_ref, frame=frame)
            if record.state.conflict_key == conflict_key
        )

    def validate(self, plan: ShieldAbsorptionPlan | ShieldMutationPlan) -> None:
        if plan.operation_id in self._committed_operations:
            raise ShieldPlanConflictError(f"护盾计划已提交：{plan.operation_id}")
        if plan.expected_store_version != self._version:
            raise ShieldPlanConflictError(
                "护盾 Store 版本冲突："
                f"expected={plan.expected_store_version}, actual={self._version}"
            )
        for expected in plan.expected_records:
            if self._records.get(expected.instance_ref) != expected:
                raise ShieldPlanConflictError(f"护盾记录前值冲突：{expected.instance_ref}")

    def commit_prevalidated(self, plan: ShieldAbsorptionPlan | ShieldMutationPlan) -> None:
        # 所有可能产生领域错误的判断必须在 validate 中完成。
        for record in plan.replacement_records:
            self._records[record.instance_ref] = record
        if plan.replacement_records:
            self._version += 1
        self._committed_operations.add(plan.operation_id)


__all__ = ["ShieldStore"]
