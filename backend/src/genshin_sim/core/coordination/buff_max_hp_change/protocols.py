"""Buff 最大生命同步协调器的领域窄端口。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import GameEvent
from genshin_sim.core.systems.buff.definitions import BuffDefinitionRegistry
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffCommitReceipt,
    BuffMutationPlan,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.health import CharacterMaxHpReconcilePlan, MaxHpReconcileReceipt


class BuffMutationPort(Protocol):
    """Buff 领域计划入口的窄端口，由 `BuffRuntime` 满足。"""

    @property
    def definition_registry(self) -> BuffDefinitionRegistry: ...

    def prepare_apply(
        self,
        requests: Sequence[ApplyBuffRequest],
    ) -> BuffMutationPlan: ...

    def prepare_expiry(self, frame: int) -> BuffMutationPlan | None: ...

    def prepare_remove(self, request: RemoveBuffRequest) -> BuffMutationPlan: ...

    def validate(self, plan: BuffMutationPlan) -> None: ...

    def commit_prevalidated(self, plan: BuffMutationPlan) -> BuffCommitReceipt: ...

    def publish_committed_facts(self, receipt: BuffCommitReceipt) -> None: ...


class HealthReconcilePort(Protocol):
    """生命值系统最大生命同步计划入口的窄端口，由 `HealthRuntime` 满足。"""

    def prepare_max_hp_reconcile(
        self,
        character_ref: AttributeSubjectRef,
        old_max_hp: float,
        new_max_hp: float,
        frame: int,
        *,
        operation_id: str,
    ) -> CharacterMaxHpReconcilePlan: ...

    def validate_max_hp_reconcile(self, plan: CharacterMaxHpReconcilePlan) -> None: ...

    def commit_max_hp_reconcile_prevalidated(
        self,
        plan: CharacterMaxHpReconcilePlan,
    ) -> MaxHpReconcileReceipt: ...

    def reconcile_events_for(
        self,
        receipt: MaxHpReconcileReceipt,
    ) -> tuple[GameEvent, ...]: ...


class MaxHpProjectionPort(Protocol):
    """用计划投影视图解析最大生命旧值与新值的窄端口。"""

    def resolve_max_hp_pair(
        self,
        subject_ref: AttributeSubjectRef,
        frame: int,
        plan: BuffMutationPlan,
    ) -> tuple[float, float]:
        """返回（提交前边界视图, 提交后视图）下的 `stat.hp.max`。"""
        ...
