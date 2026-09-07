"""状态效果（Buff）动态最大生命同步写协调器。

把影响 `stat.hp.max` 的 Buff 变更计划与生命值系统的最大生命比例
同步统一准备、预校验、无回调提交，并按契约顺序发布 Buff 与最大
生命事实。不影响 `stat.hp.max` 的 Buff 计划透明透传给 Buff 领域，
行为与直接调用 `BuffRuntime` 完全一致。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from genshin_sim.core.attributes import AttributeSubjectKind
from genshin_sim.core.coordination.buff_max_hp_change.errors import (
    BuffMaxHpChangeCommitError,
    BuffMaxHpChangeReentrancyError,
)
from genshin_sim.core.coordination.buff_max_hp_change.models import BuffMaxHpChangeRecord
from genshin_sim.core.coordination.buff_max_hp_change.protocols import (
    BuffMutationPort,
    HealthReconcilePort,
    MaxHpProjectionPort,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffApplicationResult,
    BuffMutationPlan,
    BuffRemovalResult,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.health import CharacterMaxHpReconcilePlan


class BuffMaxHpChangeCoordinator:
    """把影响最大生命的 Buff 变更与生命值系统按比例同步。"""

    def __init__(
        self,
        buff_port: BuffMutationPort,
        health_port: HealthReconcilePort,
        projection_port: MaxHpProjectionPort,
        event_engine: EventEngine,
        max_hp_definition_keys: frozenset[str],
    ) -> None:
        self.buff_port = buff_port
        self.health_port = health_port
        self.projection_port = projection_port
        self.event_engine = event_engine
        self._max_hp_definition_keys = frozenset(max_hp_definition_keys)
        self._active = False

    @property
    def definition_registry(self):
        return self.buff_port.definition_registry

    @property
    def max_hp_definition_keys(self) -> frozenset[str]:
        return self._max_hp_definition_keys

    def apply(self, request: ApplyBuffRequest) -> BuffApplicationResult:
        return self.apply_many((request,))[0]

    def apply_many(
        self,
        requests: Sequence[ApplyBuffRequest],
    ) -> tuple[BuffApplicationResult, ...]:
        with self._coordination_scope():
            plan = self.buff_port.prepare_apply(tuple(requests))
            self._settle(plan)
            return plan.application_results

    def remove(self, request: RemoveBuffRequest) -> BuffRemovalResult:
        with self._coordination_scope():
            plan = self.buff_port.prepare_remove(request)
            self._settle(plan)
            return plan.removal_results[0]

    def update_frame(self, context, frame: int) -> None:
        del context
        with self._coordination_scope():
            plan = self.buff_port.prepare_expiry(frame)
            if plan is not None:
                self._settle(plan)

    def is_idle(self) -> bool:
        return True

    def _settle(self, plan: BuffMutationPlan) -> BuffMaxHpChangeRecord:
        if not self._touches_max_hp(plan):
            self.buff_port.validate(plan)
            receipt = self.buff_port.commit_prevalidated(plan)
            self.buff_port.publish_committed_facts(receipt)
            return BuffMaxHpChangeRecord(buff_plan=plan, reconcile_results=())
        reconcile_plans = self._prepare_reconcile_plans(plan)
        self.buff_port.validate(plan)
        for reconcile_plan in reconcile_plans:
            self.health_port.validate_max_hp_reconcile(reconcile_plan)
        receipts = []
        try:
            buff_receipt = self.buff_port.commit_prevalidated(plan)
            for reconcile_plan in reconcile_plans:
                receipts.append(
                    self.health_port.commit_max_hp_reconcile_prevalidated(reconcile_plan)
                )
        except Exception as exc:
            raise BuffMaxHpChangeCommitError(f"预校验后的领域提交违反不得失败契约：{exc}") from exc
        self.buff_port.publish_committed_facts(buff_receipt)
        reconcile_results = []
        for receipt in receipts:
            for event in self.health_port.reconcile_events_for(receipt):
                self.event_engine.publish(event)
            reconcile_results.append(receipt.plan.result)
        return BuffMaxHpChangeRecord(buff_plan=plan, reconcile_results=tuple(reconcile_results))

    def _prepare_reconcile_plans(
        self,
        plan: BuffMutationPlan,
    ) -> list[CharacterMaxHpReconcilePlan]:
        # 目标主体没有生命运行态，最大生命同步只作用于角色。
        subjects = sorted(
            {
                record.state.target_ref
                for record in plan.replacement_records
                if record.state.target_ref.kind is AttributeSubjectKind.CHARACTER
            },
            key=lambda ref: (ref.kind.value, ref.entity_id),
        )
        reconcile_plans = []
        for subject in subjects:
            old_max_hp, new_max_hp = self.projection_port.resolve_max_hp_pair(
                subject,
                plan.frame,
                plan,
            )
            if old_max_hp == new_max_hp:
                continue
            reconcile_plan = self.health_port.prepare_max_hp_reconcile(
                subject,
                old_max_hp,
                new_max_hp,
                plan.frame,
                operation_id=f"buff-max-hp:{plan.operation_id}:{subject.entity_id}",
            )
            reconcile_plans.append(reconcile_plan)
        return reconcile_plans

    def _touches_max_hp(self, plan: BuffMutationPlan) -> bool:
        plan_keys = {record.definition.definition_key for record in plan.expected_records} | {
            record.definition.definition_key for record in plan.replacement_records
        }
        return bool(plan_keys & self._max_hp_definition_keys)

    @contextmanager
    def _coordination_scope(self) -> Iterator[None]:
        self._ensure_can_coordinate()
        self._active = True
        try:
            yield
        finally:
            self._active = False

    def _ensure_can_coordinate(self) -> None:
        if self._active:
            raise BuffMaxHpChangeReentrancyError("Buff 最大生命协调器不允许同步重入")
