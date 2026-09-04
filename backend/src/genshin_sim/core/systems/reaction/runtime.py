"""Reaction Registry、计划和提交校验。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from typing import cast

from genshin_sim.core.elements import AuraAmount, AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import (
    EventType,
    GameEvent,
    ReactionStateChangedPayload,
)
from genshin_sim.core.systems.aura import (
    AuraComponent,
    AuraDecayMode,
    AuraLossPolicy,
    AuraView,
)
from genshin_sim.core.systems.reaction.establishment_gates import (
    ReactionEstablishmentGateCommitReceipt,
    ReactionEstablishmentGateDecision,
    ReactionEstablishmentGateDefinition,
    ReactionEstablishmentGateMutationPlan,
    ReactionEstablishmentGatePlanner,
    ReactionEstablishmentGateRecord,
    ReactionEstablishmentGateRequest,
    ReactionEstablishmentGateSlotKey,
)
from genshin_sim.core.systems.reaction.gates import (
    ReactionDamageGateCommitReceipt,
    ReactionDamageGateDefinition,
    ReactionDamageGateMutationPlan,
    ReactionDamageGatePlanner,
    ReactionDamageGateRecord,
    ReactionDamageGateSlotKey,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.models import (
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    CrystallizeReactionProfile,
    GeneratedDamageImpactEffect,
    ParallelAuraConsumption,
    PersistentIncomingAuraApplicationEffect,
    ReactionCommitReceipt,
    ReactionDecisionSequence,
    ReactionDecisionStep,
    ReactionDefinition,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionMutationPlan,
    ReactionOccurrence,
    ReactionResolution,
)
from genshin_sim.core.systems.reaction.resources import (
    LunarBloomDewState,
    ReactionResourceCommitReceipt,
    ReactionResourceMutationPlan,
    ReactionResourcePlanner,
    validate_resource_plan,
)
from genshin_sim.core.systems.reaction.snapshots import ReactionSnapshot
from genshin_sim.core.systems.reaction.states import (
    BurningState,
    CrystallizeShardState,
    DendroCoreState,
    ElectroChargedState,
    FreezeRecoveryState,
    FrozenState,
    LunarCageState,
    LunarCrystallizeAccumulatorState,
    LunarStormCloudState,
    QuickenState,
    ReactionStateCommitReceipt,
    ReactionStateInstanceRef,
    ReactionStateMutationPlan,
    ReactionStatePlanner,
    ReactionStateRecord,
    ReactionStateSlot,
    ReactionStateSlotKey,
    ReactionStateSnapshot,
    SprawlingShotState,
)


class ReactionSelectionError(RuntimeError):
    """多个规则无明确关系地同时匹配时抛出的错误。"""


class ReactionStoreConflictError(RuntimeError):
    """Reaction 计划与当前无状态 Store 视图不一致时抛出的错误。"""


@dataclass(frozen=True, slots=True)
class _ProjectedAuraComponent:
    """仅供复合候选评估使用的不可提交 Aura 视图。"""

    aura_kind: AuraKind
    current_amount: AuraAmount


@dataclass(frozen=True, slots=True)
class ReactionStoreMutationPlan:
    """同一感电脉冲内 Gate 与 ReactionState 的单版本写入计划。"""

    gate_plan: ReactionDamageGateMutationPlan
    state_plan: ReactionStateMutationPlan
    establishment_gate_plan: ReactionEstablishmentGateMutationPlan | None = None
    resource_plan: ReactionResourceMutationPlan | None = None

    def __post_init__(self) -> None:
        if self.gate_plan.expected_store_version != self.state_plan.expected_store_version:
            raise ValueError("Gate 与 ReactionState 计划必须使用同一 Store version")
        if self.gate_plan.frame != self.state_plan.frame:
            raise ValueError("Gate 与 ReactionState 计划帧必须一致")
        if self.establishment_gate_plan is not None:
            if self.establishment_gate_plan.expected_store_version != self.expected_store_version:
                raise ValueError("成立 Gate 与 ReactionState 计划必须使用同一 Store version")
            if self.establishment_gate_plan.frame != self.frame:
                raise ValueError("成立 Gate 与 ReactionState 计划帧必须一致")
        if self.resource_plan is not None:
            if self.resource_plan.expected_store_version != self.expected_store_version:
                raise ValueError("Reaction resource 计划必须使用同一 Store version")
            if self.resource_plan.frame != self.frame:
                raise ValueError("Reaction resource 计划帧必须一致")

    @property
    def expected_store_version(self) -> int:
        return self.gate_plan.expected_store_version

    @property
    def frame(self) -> int:
        return self.gate_plan.frame


@dataclass(frozen=True, slots=True)
class ReactionStoreCommitReceipt:
    plan: ReactionStoreMutationPlan
    version: int
    gate_receipt: ReactionDamageGateCommitReceipt
    state_receipt: ReactionStateCommitReceipt
    establishment_gate_receipt: ReactionEstablishmentGateCommitReceipt | None = None
    resource_receipt: ReactionResourceCommitReceipt | None = None


class ReactionRegistry:
    def __init__(self, definitions: tuple[ReactionDefinition, ...] = ()) -> None:
        self._definitions: dict[str, ReactionDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ReactionDefinition) -> None:
        if definition.reaction_key in self._definitions:
            raise ValueError(f"重复的 Reaction Definition：{definition.reaction_key}")
        self._definitions[definition.reaction_key] = definition

    @property
    def definitions(self) -> tuple[ReactionDefinition, ...]:
        return tuple(sorted(self._definitions.values(), key=lambda item: item.reaction_key))

    def definition_for(self, reaction_key: str) -> ReactionDefinition:
        try:
            return self._definitions[reaction_key]
        except KeyError as exc:
            raise ValueError(f"未注册的 Reaction Definition：{reaction_key}") from exc


class ReactionBatchPlanner:
    """收集当前批次的无状态 Reaction occurrence。"""

    def __init__(self, runtime: ReactionRuntime, frame: int, batch_id: str) -> None:
        self._runtime = runtime
        self.frame = frame
        self.batch_id = batch_id
        self._expected_store_version = runtime.version
        self._resolutions: list[ReactionResolution] = []
        self._interaction_ids: set[str] = set()
        self._orders: set[int] = set()
        self._establishment_gate_planner: ReactionEstablishmentGatePlanner | None = None
        self._sealed = False

    def prepare(self, request: ReactionEvaluationRequest) -> ReactionResolution:
        if self._sealed:
            raise RuntimeError("ReactionBatchPlanner 已封存")
        if request.frame != self.frame:
            raise ValueError("Reaction 请求帧与所属批次不一致")
        if request.interaction_id in self._interaction_ids:
            raise ValueError(f"重复的 Reaction interaction_id：{request.interaction_id}")
        if request.order in self._orders:
            raise ValueError(f"重复的 Reaction order：{request.order}")
        resolution = self._prepare_establishment_gates(self._runtime.evaluate(request))
        self._interaction_ids.add(request.interaction_id)
        self._orders.add(request.order)
        self._resolutions.append(resolution)
        return resolution

    def seal(self) -> ReactionMutationPlan:
        if self._sealed:
            raise RuntimeError("ReactionBatchPlanner 已封存")
        self._sealed = True
        return ReactionMutationPlan(
            f"reaction:{self.batch_id}",
            self.frame,
            tuple(sorted(self._interaction_ids)),
            self._expected_store_version,
            tuple(sorted(self._resolutions, key=lambda item: item.request.order)),
            (
                None
                if self._establishment_gate_planner is None
                else self._establishment_gate_planner.seal()
            ),
        )

    def _prepare_establishment_gates(
        self,
        resolution: ReactionResolution,
    ) -> ReactionResolution:
        gated_occurrences: list[ReactionOccurrence] = []
        for step in resolution.sequence.steps:
            for occurrence in step.occurrences:
                definition = self._runtime.registry.definition_for(occurrence.reaction_key)
                if definition.entry_kind.value != "elemental_interaction":
                    continue
                if isinstance(
                    definition.profile_for(occurrence.direction_key),
                    CrystallizeReactionProfile,
                ):
                    gated_occurrences.append(occurrence)
        if not gated_occurrences:
            return resolution
        if self._establishment_gate_planner is None:
            self._establishment_gate_planner = self._runtime.begin_establishment_gate_batch(
                self.frame,
                f"reaction-establishment:{self.batch_id}",
            )

        gate_resolutions = []
        blocked_occurrence_refs: set[str] = set()
        for occurrence in gated_occurrences:
            profile = self._runtime.registry.definition_for(occurrence.reaction_key).profile_for(
                occurrence.direction_key
            )
            assert isinstance(profile, CrystallizeReactionProfile)
            gate_resolution = self._establishment_gate_planner.prepare(
                ReactionEstablishmentGateRequest(
                    gate_request_ref=f"{occurrence.occurrence_ref}:establishment-gate",
                    frame=self.frame,
                    definition=self._runtime.establishment_gate_definition(
                        profile.establishment_gate_definition_key
                    ),
                    subject_ref=occurrence.subject_ref,
                    occurrence_ref=occurrence.occurrence_ref,
                )
            )
            gate_resolutions.append(gate_resolution)
            if (
                gate_resolution.decision
                is ReactionEstablishmentGateDecision.ESTABLISHMENT_GATE_BLOCKED
            ):
                blocked_occurrence_refs.add(occurrence.occurrence_ref)
        return _without_blocked_establishment_occurrences(
            resolution,
            blocked_occurrence_refs,
            tuple(gate_resolutions),
        )


class ReactionRuntime:
    """无状态反应不创建伪状态，但仍提供 stale plan 防护。"""

    def __init__(
        self,
        registry: ReactionRegistry,
        *,
        gate_definitions: tuple[ReactionDamageGateDefinition, ...] = (),
        establishment_gate_definitions: tuple[ReactionEstablishmentGateDefinition, ...] = (),
        external_write_guard: Callable[[], bool] | None = None,
    ) -> None:
        self.registry = registry
        self._version = 0
        self._committed_operation_ids: set[str] = set()
        self._committed_interaction_ids: set[str] = set()
        self._gate_definitions = {
            definition.gate_definition_key: definition for definition in gate_definitions
        }
        if len(self._gate_definitions) != len(gate_definitions):
            raise ValueError("重复的 Reaction Damage Gate Definition")
        self._gate_records: dict[ReactionDamageGateSlotKey, ReactionDamageGateRecord] = {}
        self._committed_gate_operation_ids: set[str] = set()
        self._establishment_gate_definitions = {
            definition.gate_definition_key: definition
            for definition in establishment_gate_definitions
        }
        if len(self._establishment_gate_definitions) != len(establishment_gate_definitions):
            raise ValueError("重复的 Reaction Establishment Gate Definition")
        self._establishment_gate_records: dict[
            ReactionEstablishmentGateSlotKey,
            ReactionEstablishmentGateRecord,
        ] = {}
        self._committed_establishment_gate_operation_ids: set[str] = set()
        self._lunar_bloom_dew_records: dict[str, LunarBloomDewState] = {}
        self._committed_resource_operation_ids: set[str] = set()
        self._state_records: dict[ReactionStateSlotKey, ReactionStateRecord] = {}
        self._crystallize_shard_records: dict[
            ReactionStateInstanceRef,
            CrystallizeShardState,
        ] = {}
        self._dendro_core_records: dict[ReactionStateInstanceRef, DendroCoreState] = {}
        self._lunar_storm_cloud_records: dict[
            ReactionStateInstanceRef,
            LunarStormCloudState,
        ] = {}
        self._lunar_cage_records: dict[ReactionStateInstanceRef, LunarCageState] = {}
        self._lunar_crystallize_accumulator_records: dict[
            str,
            LunarCrystallizeAccumulatorState,
        ] = {}
        self._sprawling_shot_records: dict[ReactionStateInstanceRef, SprawlingShotState] = {}
        self._state_instance_sequence = 0
        self._dendro_core_creation_sequence = 0
        self._normalized_through_frame = 0
        self._external_write_guard = external_write_guard
        self._fact_publication_active = False

    @property
    def version(self) -> int:
        return self._version

    def begin_batch(self, frame: int, batch_id: str) -> ReactionBatchPlanner:
        return ReactionBatchPlanner(self, frame, batch_id)

    @property
    def normalized_through_frame(self) -> int:
        return self._normalized_through_frame

    @property
    def state_records(self) -> tuple[ReactionStateRecord, ...]:
        return tuple(
            sorted(
                self._state_records.values(),
                key=lambda item: (
                    item.slot_key.subject_ref.kind.value,
                    item.slot_key.subject_ref.entity_id,
                    item.slot_key.slot.value,
                    item.slot_key.scope_key.value,
                ),
            )
        )

    def frozen_state_for(self, subject_ref: ElementalSubjectRef) -> FrozenState | None:
        record = self._state_records.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.FROZEN)
        )
        return record if isinstance(record, FrozenState) else None

    def electro_charged_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> ElectroChargedState | None:
        record = self._state_records.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.ELECTRO_CHARGED)
        )
        return record if isinstance(record, ElectroChargedState) else None

    def burning_state_for(self, subject_ref: ElementalSubjectRef) -> BurningState | None:
        record = self._state_records.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.BURNING)
        )
        return record if isinstance(record, BurningState) else None

    def quicken_state_for(self, subject_ref: ElementalSubjectRef) -> QuickenState | None:
        record = self._state_records.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.QUICKEN)
        )
        return record if isinstance(record, QuickenState) else None

    def freeze_recovery_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> FreezeRecoveryState | None:
        record = self._state_records.get(
            ReactionStateSlotKey(subject_ref, ReactionStateSlot.FREEZE_RECOVERY)
        )
        return record if isinstance(record, FreezeRecoveryState) else None

    def crystallize_shard_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> CrystallizeShardState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return self._crystallize_shard_records.get(instance_ref)

    def dendro_core_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> DendroCoreState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return self._dendro_core_records.get(instance_ref)

    def lunar_storm_cloud_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return self._lunar_storm_cloud_records.get(instance_ref)

    def active_lunar_storm_clouds(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarStormCloudState, ...]:
        if team_ref is not None and (not isinstance(team_ref, str) or not team_ref.strip()):
            raise ValueError("team_ref 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    record
                    for record in self._lunar_storm_cloud_records.values()
                    if team_ref is None or record.team_ref == team_ref
                ),
                key=lambda item: (item.created_frame, item.instance_ref.value),
            )
        )

    def lunar_cage_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return self._lunar_cage_records.get(instance_ref)

    def active_lunar_cages(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarCageState, ...]:
        if team_ref is not None and (not isinstance(team_ref, str) or not team_ref.strip()):
            raise ValueError("team_ref 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    record
                    for record in self._lunar_cage_records.values()
                    if team_ref is None or record.team_ref == team_ref
                ),
                key=lambda item: (item.created_frame, item.instance_ref.value),
            )
        )

    def lunar_crystallize_accumulator_for(
        self,
        team_ref: str,
    ) -> LunarCrystallizeAccumulatorState | None:
        if not isinstance(team_ref, str) or not team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        return self._lunar_crystallize_accumulator_records.get(team_ref)

    def active_dendro_cores(self, *, pool_scope: str | None = None) -> tuple[DendroCoreState, ...]:
        if pool_scope is not None and (not isinstance(pool_scope, str) or not pool_scope.strip()):
            raise ValueError("pool_scope 必须是非空字符串或 None")
        return tuple(
            sorted(
                (
                    record
                    for record in self._dendro_core_records.values()
                    if pool_scope is None or record.pool_scope == pool_scope
                ),
                key=lambda item: (item.creation_sequence, item.instance_ref.value),
            )
        )

    def sprawling_shot_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> SprawlingShotState | None:
        if not isinstance(instance_ref, ReactionStateInstanceRef):
            raise ValueError("instance_ref 必须是 ReactionStateInstanceRef")
        return self._sprawling_shot_records.get(instance_ref)

    def begin_state_batch(self, frame: int, batch_id: str) -> ReactionStatePlanner:
        self._ensure_external_write_allowed()
        if frame != self._normalized_through_frame:
            raise ValueError("ReactionState 批次要求所在帧已经完成规范化")
        return ReactionStatePlanner(self, frame, batch_id)

    def begin_resource_batch(self, frame: int, batch_id: str) -> ReactionResourcePlanner:
        self._ensure_external_write_allowed()
        return ReactionResourcePlanner(self, frame, batch_id)

    def lunar_bloom_dew_state_for(
        self,
        team_ref: str,
        *,
        frame: int | None = None,
    ) -> LunarBloomDewState | None:
        if not isinstance(team_ref, str) or not team_ref.strip():
            raise ValueError("team_ref 必须是非空字符串")
        state = self._lunar_bloom_dew_records.get(team_ref)
        if state is None:
            return None
        return state.normalized_at(
            self._normalized_through_frame if frame is None else frame,
        )

    @property
    def lunar_bloom_dew_records(self) -> tuple[LunarBloomDewState, ...]:
        return tuple(sorted(self._lunar_bloom_dew_records.values(), key=lambda item: item.team_ref))

    def validate_resource_plan(self, plan: ReactionResourceMutationPlan) -> None:
        validate_resource_plan(self, plan)

    def commit_prevalidated_resource_plan(
        self,
        plan: ReactionResourceMutationPlan,
    ) -> ReactionResourceCommitReceipt:
        self._ensure_external_write_allowed()
        self.validate_resource_plan(plan)
        next_records = dict(self._lunar_bloom_dew_records)
        for team_ref in plan.removed_team_refs:
            next_records.pop(team_ref, None)
        for record in plan.replacement_records:
            next_records[record.team_ref] = record
        changed = next_records != self._lunar_bloom_dew_records
        self._lunar_bloom_dew_records = next_records
        self._committed_resource_operation_ids.add(plan.operation_id)
        if changed:
            self._version += 1
        return ReactionResourceCommitReceipt(plan, self.version)

    def validate_state_plan(self, plan: ReactionStateMutationPlan) -> None:
        if plan.expected_store_version != self.version:
            raise ReactionStoreConflictError("ReactionState 变更计划已经过期")
        if plan.operation_id in self._committed_operation_ids:
            raise ReactionStoreConflictError("重复的 ReactionState 操作")
        if plan.frame != self._normalized_through_frame:
            raise ReactionStoreConflictError("ReactionState 计划帧尚未规范化")
        for expected in plan.expected_records:
            if self._state_records.get(expected.slot_key) != expected:
                raise ReactionStoreConflictError("ReactionState 记录前值冲突")
        projected_records = dict(self._state_records)
        for slot_key in plan.removed_slot_keys:
            projected_records.pop(slot_key, None)
        for record in plan.replacement_records:
            projected_records[record.slot_key] = record
        _crystallize_shard_index(projected_records.values())
        _dendro_core_index(projected_records.values())
        _lunar_storm_cloud_index(projected_records.values())
        _lunar_cage_index(projected_records.values())
        _lunar_crystallize_accumulator_index(projected_records.values())
        _sprawling_shot_index(projected_records.values())

    def commit_prevalidated_state_plan(
        self,
        plan: ReactionStateMutationPlan,
    ) -> ReactionStateCommitReceipt:
        self._ensure_external_write_allowed()
        self.validate_state_plan(plan)
        next_records = dict(self._state_records)
        for slot_key in plan.removed_slot_keys:
            next_records.pop(slot_key, None)
        for record in plan.replacement_records:
            next_records[record.slot_key] = record
        if next_records != self._state_records:
            self._state_records = next_records
            self._crystallize_shard_records = _crystallize_shard_index(next_records.values())
            self._dendro_core_records = _dendro_core_index(next_records.values())
            self._lunar_storm_cloud_records = _lunar_storm_cloud_index(next_records.values())
            self._lunar_cage_records = _lunar_cage_index(next_records.values())
            self._lunar_crystallize_accumulator_records = _lunar_crystallize_accumulator_index(
                next_records.values()
            )
            self._sprawling_shot_records = _sprawling_shot_index(next_records.values())
            self._version += 1
        self._state_instance_sequence = plan.next_state_instance_sequence
        self._dendro_core_creation_sequence = plan.next_dendro_core_creation_sequence
        self._committed_operation_ids.add(plan.operation_id)
        return ReactionStateCommitReceipt(plan, self.version)

    def publish_committed_state_facts(self, context, receipt: ReactionStateCommitReceipt) -> None:
        """只发布已经完整提交的 State 变化，并禁止 Event handler 回写当前 Store。"""

        with self.event_publication_guard():
            for change in receipt.plan.changes:
                context.events.publish(
                    GameEvent(
                        EventType.REACTION_STATE_CHANGED,
                        receipt.plan.frame,
                        ReactionStateChangedPayload(change),
                    )
                )

    def update_frame(self, context, frame: int) -> None:
        self._ensure_external_write_allowed()
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("ReactionState frame 必须是非负整数")
        if frame < self._normalized_through_frame:
            raise ValueError("ReactionState 帧不能回退")
        next_required = self.next_required_frame()
        if next_required is not None and frame > next_required:
            raise ValueError("不能跨过 ReactionState 必需处理帧")
        self._normalized_through_frame = frame

    def next_required_frame(self) -> int | None:
        return min(
            (
                record.next_required_frame
                for record in self._state_records.values()
                if record.next_required_frame is not None
            ),
            default=None,
        )

    def state_snapshot(self, frame: int) -> ReactionStateSnapshot:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("ReactionState snapshot frame 必须是非负整数")
        return ReactionStateSnapshot(
            frame,
            self._normalized_through_frame,
            self.version,
            self.state_records,
        )

    def set_external_write_guard(self, guard: Callable[[], bool] | None) -> None:
        self._external_write_guard = guard

    @property
    def gate_records(self) -> tuple[ReactionDamageGateRecord, ...]:
        return tuple(
            sorted(
                self._gate_records.values(),
                key=lambda item: (
                    item.slot_key.gate_definition_key,
                    item.slot_key.trigger_source_ref,
                    item.slot_key.damage_target_ref,
                    item.slot_key.damage_kind_key,
                ),
            )
        )

    def gate_definition(self, gate_definition_key: str) -> ReactionDamageGateDefinition:
        try:
            return self._gate_definitions[gate_definition_key]
        except KeyError as exc:
            raise ValueError(f"未注册的 Reaction Damage Gate：{gate_definition_key}") from exc

    def begin_gate_batch(self, frame: int, operation_id: str) -> ReactionDamageGatePlanner:
        return ReactionDamageGatePlanner(self, frame, operation_id)

    @property
    def establishment_gate_records(self) -> tuple[ReactionEstablishmentGateRecord, ...]:
        return tuple(
            sorted(
                self._establishment_gate_records.values(),
                key=lambda item: (
                    item.slot_key.gate_definition_key,
                    item.slot_key.subject_ref.kind.value,
                    item.slot_key.subject_ref.entity_id,
                ),
            )
        )

    def establishment_gate_definition(
        self,
        gate_definition_key: str,
    ) -> ReactionEstablishmentGateDefinition:
        try:
            return self._establishment_gate_definitions[gate_definition_key]
        except KeyError as exc:
            msg = f"未注册的 Reaction Establishment Gate：{gate_definition_key}"
            raise ValueError(msg) from exc

    def begin_establishment_gate_batch(
        self,
        frame: int,
        operation_id: str,
    ) -> ReactionEstablishmentGatePlanner:
        self._ensure_external_write_allowed()
        if frame != self._normalized_through_frame:
            raise ValueError("Reaction 成立 Gate 批次要求所在帧已经完成规范化")
        return ReactionEstablishmentGatePlanner(self, frame, operation_id)

    def snapshot(self, frame: int) -> ReactionSnapshot:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError("Reaction snapshot frame 必须是非负整数")
        return ReactionSnapshot(
            frame,
            self._normalized_through_frame,
            self.version,
            self.gate_records,
            self.state_records,
            self.establishment_gate_records,
            tuple(state.normalized_at(frame) for state in self.lunar_bloom_dew_records),
        )

    def validate_gate_plan(self, plan: ReactionDamageGateMutationPlan) -> None:
        if plan.expected_store_version != self.version:
            raise ReactionStoreConflictError("Reaction Gate 变更计划已经过期")
        if plan.operation_id in self._committed_gate_operation_ids:
            raise ReactionStoreConflictError("重复的 Reaction Gate 操作")
        for expected in plan.expected_records:
            if self._gate_records.get(expected.slot_key) != expected:
                raise ReactionStoreConflictError("Reaction Gate 记录前值冲突")

    def commit_prevalidated_gate_plan(
        self,
        plan: ReactionDamageGateMutationPlan,
    ) -> ReactionDamageGateCommitReceipt:
        self._ensure_external_write_allowed()
        self.validate_gate_plan(plan)
        for record in plan.replacement_records:
            self._gate_records[record.slot_key] = record
        self._committed_gate_operation_ids.add(plan.operation_id)
        if plan.replacement_records:
            self._version += 1
        return ReactionDamageGateCommitReceipt(plan, self.version)

    def validate_establishment_gate_plan(
        self,
        plan: ReactionEstablishmentGateMutationPlan,
    ) -> None:
        if plan.expected_store_version != self.version:
            raise ReactionStoreConflictError("Reaction 成立 Gate 变更计划已经过期")
        if plan.operation_id in self._committed_establishment_gate_operation_ids:
            raise ReactionStoreConflictError("重复的 Reaction 成立 Gate 操作")
        if plan.frame != self._normalized_through_frame:
            raise ReactionStoreConflictError("Reaction 成立 Gate 计划帧尚未规范化")
        expected_by_slot = {record.slot_key: record for record in plan.expected_records}
        for expected in expected_by_slot.values():
            if self._establishment_gate_records.get(expected.slot_key) != expected:
                raise ReactionStoreConflictError("Reaction 成立 Gate 记录前值冲突")
        for replacement in plan.replacement_records:
            before = self._establishment_gate_records.get(replacement.slot_key)
            expected = expected_by_slot.get(replacement.slot_key)
            if before is None:
                if expected is not None:
                    raise ReactionStoreConflictError("Reaction 成立 Gate 新记录不应携带前值")
                continue
            if expected != before:
                raise ReactionStoreConflictError("Reaction 成立 Gate 替换缺少完整前值")

    def commit_prevalidated_establishment_gate_plan(
        self,
        plan: ReactionEstablishmentGateMutationPlan,
    ) -> ReactionEstablishmentGateCommitReceipt:
        self._ensure_external_write_allowed()
        self.validate_establishment_gate_plan(plan)
        for record in plan.replacement_records:
            self._establishment_gate_records[record.slot_key] = record
        self._committed_establishment_gate_operation_ids.add(plan.operation_id)
        if plan.replacement_records:
            self._version += 1
        return ReactionEstablishmentGateCommitReceipt(plan, self.version)

    def validate_store_mutation_plan(self, plan: ReactionStoreMutationPlan) -> None:
        """在任何领域写入前检查 Gate 和 State 的共同前值。"""

        self.validate_gate_plan(plan.gate_plan)
        self.validate_state_plan(plan.state_plan)
        if plan.establishment_gate_plan is not None:
            self.validate_establishment_gate_plan(plan.establishment_gate_plan)
        if plan.resource_plan is not None:
            validate_resource_plan(self, plan.resource_plan)

    def commit_prevalidated_store_mutation_plan(
        self,
        plan: ReactionStoreMutationPlan,
    ) -> ReactionStoreCommitReceipt:
        """一次性提交 Gate/State，确保它们只推进一个共享 version。"""

        self._ensure_external_write_allowed()
        self.validate_store_mutation_plan(plan)
        gate_plan = plan.gate_plan
        state_plan = plan.state_plan
        establishment_gate_plan = plan.establishment_gate_plan
        resource_plan = plan.resource_plan
        next_gate_records = dict(self._gate_records)
        for record in gate_plan.replacement_records:
            next_gate_records[record.slot_key] = record
        next_establishment_gate_records = dict(self._establishment_gate_records)
        if establishment_gate_plan is not None:
            for record in establishment_gate_plan.replacement_records:
                next_establishment_gate_records[record.slot_key] = record
        next_state_records = dict(self._state_records)
        for slot_key in state_plan.removed_slot_keys:
            next_state_records.pop(slot_key, None)
        for record in state_plan.replacement_records:
            next_state_records[record.slot_key] = record
        next_resource_records = dict(self._lunar_bloom_dew_records)
        if resource_plan is not None:
            for team_ref in resource_plan.removed_team_refs:
                next_resource_records.pop(team_ref, None)
            for record in resource_plan.replacement_records:
                next_resource_records[record.team_ref] = record
        changed = (
            next_gate_records != self._gate_records
            or next_establishment_gate_records != self._establishment_gate_records
            or next_state_records != self._state_records
            or next_resource_records != self._lunar_bloom_dew_records
        )
        self._gate_records = next_gate_records
        self._establishment_gate_records = next_establishment_gate_records
        self._state_records = next_state_records
        self._lunar_bloom_dew_records = next_resource_records
        self._crystallize_shard_records = _crystallize_shard_index(next_state_records.values())
        self._dendro_core_records = _dendro_core_index(next_state_records.values())
        self._lunar_storm_cloud_records = _lunar_storm_cloud_index(next_state_records.values())
        self._lunar_cage_records = _lunar_cage_index(next_state_records.values())
        self._lunar_crystallize_accumulator_records = _lunar_crystallize_accumulator_index(
            next_state_records.values()
        )
        self._sprawling_shot_records = _sprawling_shot_index(next_state_records.values())
        self._state_instance_sequence = state_plan.next_state_instance_sequence
        self._dendro_core_creation_sequence = state_plan.next_dendro_core_creation_sequence
        self._committed_gate_operation_ids.add(gate_plan.operation_id)
        if establishment_gate_plan is not None:
            self._committed_establishment_gate_operation_ids.add(
                establishment_gate_plan.operation_id
            )
        self._committed_operation_ids.add(state_plan.operation_id)
        if changed:
            self._version += 1
        resource_receipt = None
        if resource_plan is not None:
            self._committed_resource_operation_ids.add(resource_plan.operation_id)
            resource_receipt = ReactionResourceCommitReceipt(resource_plan, self.version)
        gate_receipt = ReactionDamageGateCommitReceipt(gate_plan, self.version)
        state_receipt = ReactionStateCommitReceipt(state_plan, self.version)
        establishment_gate_receipt = (
            None
            if establishment_gate_plan is None
            else ReactionEstablishmentGateCommitReceipt(establishment_gate_plan, self.version)
        )
        return ReactionStoreCommitReceipt(
            plan,
            self.version,
            gate_receipt,
            state_receipt,
            establishment_gate_receipt,
            resource_receipt,
        )

    def evaluate(self, request: ReactionEvaluationRequest) -> ReactionResolution:
        state_matches = [
            resolution
            for definition in self.registry.definitions
            if definition.entry_kind.value == "state_trigger"
            if _definition_matches_trigger_context(definition, request)
            if (resolution := definition.rule.evaluate(request, definition)) is not None
        ]
        if len(state_matches) > 1:
            keys = ", ".join(
                match.occurrence.reaction_key
                for match in state_matches
                if match.occurrence is not None
            )
            raise ReactionSelectionError(f"Reaction 候选存在歧义：{keys}")
        if state_matches:
            state_resolution = state_matches[0]
            if _is_frozen_state_consumption(state_resolution):
                return self._continue_after_state_trigger(state_resolution)
            elemental_matches = self._elemental_matches(request)
            if elemental_matches:
                keys = ", ".join(
                    match.occurrence.reaction_key
                    for match in (state_resolution, *elemental_matches)
                    if match.occurrence is not None
                )
                raise ReactionSelectionError(f"Reaction 候选存在歧义：{keys}")
            return state_resolution

        matches = self._elemental_matches(request)
        if len(matches) > 1:
            keys = ", ".join(
                match.occurrence.reaction_key for match in matches if match.occurrence is not None
            )
            raise ReactionSelectionError(f"Reaction 候选存在歧义：{keys}")
        if matches:
            return matches[0]
        self._reject_unsupported_dendro_candidates(request)
        return ReactionResolution(request, None, None)

    def _elemental_matches(
        self,
        request: ReactionEvaluationRequest,
    ) -> list[ReactionResolution]:
        if (
            request.incoming_element is Element.HYDRO
            and request.observed_aura.component_for(AuraKind.DENDRO) is not None
            and request.observed_aura.component_for(AuraKind.QUICKEN) is not None
        ):
            raise UnsupportedDendroReactionCandidateError(
                "水不能在同一次结算中同时进入普通草与激元素绽放候选"
            )
        electro_charged_bloom_combined = self._electro_charged_dendro_bloom_combination(request)
        if electro_charged_bloom_combined is not None:
            return [electro_charged_bloom_combined]
        catalyze_combined = self._catalyze_combination(request)
        if catalyze_combined is not None:
            return [catalyze_combined]
        burning_combined = self._burning_parallel_combination(request)
        if burning_combined is not None:
            return [burning_combined]
        combined = self._water_electro_combination(request)
        if combined is not None:
            return [combined]
        multiple_aura_matches = self._multiple_aura_matches(request)
        if multiple_aura_matches:
            return multiple_aura_matches
        matches = [
            resolution
            for definition in self.registry.definitions
            if definition.entry_kind.value == "elemental_interaction"
            if _definition_matches_trigger_context(definition, request)
            if (resolution := definition.rule.evaluate(request, definition)) is not None
        ]
        return _highest_priority_matches(self.registry, matches)

    def _electro_charged_dendro_bloom_combination(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution | None:
        """冻结感电目标受草时原激化与两条确认的绽放后续。"""

        if request.incoming_element is not Element.DENDRO or request.incoming_amount.is_zero:
            return None
        hydro = request.observed_aura.component_for(AuraKind.HYDRO)
        electro = request.observed_aura.component_for(AuraKind.ELECTRO)
        if hydro is None or electro is None:
            return None

        quicken_request = replace(
            request,
            observed_aura=AuraView(request.subject_ref, (electro,)),
        )
        quicken = self._resolution_for_key(quicken_request, "reaction.quicken")
        if quicken is None or quicken.occurrence is None:
            return None
        quicken_occurrence = quicken.occurrence
        quicken_transition = quicken_occurrence.transition

        steps = [quicken.sequence.steps[0]]
        hydro_remaining = hydro.current_amount
        incoming_remaining = quicken_transition.incoming_remaining
        bloom_one = self._resolution_for_key(
            _with_elemental_application(
                request,
                order=request.order + 1,
                element=Element.DENDRO,
                amount=incoming_remaining,
                observed_aura=AuraView(request.subject_ref, (hydro,)),
            ),
            "reaction.bloom",
        )
        if bloom_one is not None and bloom_one.occurrence is not None:
            bloom_one_occurrence = bloom_one.occurrence
            hydro_remaining = bloom_one_occurrence.transition.aura_remaining
            steps.append(replace(bloom_one.sequence.steps[0], step_ordinal=len(steps)))

        projected_quicken = _ProjectedAuraComponent(
            aura_kind=AuraKind.QUICKEN,
            current_amount=quicken_transition.aura_consumed,
        )
        bloom_two = self._resolution_for_key(
            _with_elemental_application(
                request,
                order=request.order + len(steps),
                element=Element.HYDRO,
                amount=hydro_remaining,
                observed_aura=AuraView(
                    request.subject_ref,
                    (cast(AuraComponent, projected_quicken),),
                ),
            ),
            "reaction.bloom",
        )
        if bloom_two is not None and bloom_two.occurrence is not None:
            bloom_two_occurrence = bloom_two.occurrence
            hydro_used = bloom_two_occurrence.transition.incoming_consumed
            hydro_transition = replace(
                bloom_two_occurrence.transition,
                aura_kind=AuraKind.HYDRO,
                incoming_before=hydro_remaining,
                incoming_consumed=hydro_used,
                incoming_remaining=hydro_remaining - hydro_used,
                aura_before=hydro_remaining,
                aura_consumed=hydro_used,
                aura_remaining=hydro_remaining - hydro_used,
            )
            bloom_two_step = bloom_two.sequence.steps[0]
            steps.append(
                replace(
                    bloom_two_step,
                    step_ordinal=len(steps),
                    elemental_transition_effects=(
                        bloom_two_occurrence.transition,
                        hydro_transition,
                    ),
                )
            )

        return ReactionResolution(
            request,
            quicken_occurrence,
            None,
            ReactionDecisionSequence(tuple(steps)),
        )

    def _burning_parallel_combination(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution | None:
        """让已注册的火性质反应对普通火与燃元素并行使用同一后手预算。"""

        if request.incoming_element not in {
            Element.HYDRO,
            Element.CRYO,
            Element.ELECTRO,
            Element.ANEMO,
            Element.GEO,
        }:
            return None
        burning = request.observed_aura.component_for(AuraKind.BURNING)
        if burning is None:
            return None
        burning_resolution = _single_fire_property_resolution(
            self,
            request,
            component=burning,
        )
        if burning_resolution is None or burning_resolution.occurrence is None:
            return None
        burning_occurrence = burning_resolution.occurrence
        burning_branch = replace(burning_occurrence.transition, aura_kind=AuraKind.BURNING)

        branches = [burning_branch]
        pyro = request.observed_aura.component_for(AuraKind.PYRO)
        if pyro is not None:
            pyro_resolution = _single_fire_property_resolution(
                self,
                request,
                component=pyro,
            )
            if pyro_resolution is None or pyro_resolution.occurrence is None:
                raise ReactionSelectionError("普通火与燃元素的平行候选不完整")
            pyro_occurrence = pyro_resolution.occurrence
            if (
                pyro_occurrence.reaction_key != burning_occurrence.reaction_key
                or pyro_occurrence.direction_key != burning_occurrence.direction_key
                or pyro_occurrence.profile_key != burning_occurrence.profile_key
            ):
                raise ReactionSelectionError("普通火与燃元素的平行候选不一致")
            branches.append(pyro_occurrence.transition)
        parallel = ParallelAuraConsumption(
            shared_incoming_before=request.incoming_amount,
            shared_incoming_consumed=max(item.incoming_consumed for item in branches),
            shared_incoming_remaining=(
                request.incoming_amount - max(item.incoming_consumed for item in branches)
            ),
            branches=tuple(sorted(branches, key=lambda item: item.aura_kind.value)),
        )
        summary_transition = replace(
            burning_branch,
            incoming_consumed=parallel.shared_incoming_consumed,
            incoming_remaining=parallel.shared_incoming_remaining,
        )
        persistent = burning_occurrence.persistent_incoming_aura_application
        bloom = None
        if not parallel.shared_incoming_remaining.is_zero:
            if request.incoming_element is Element.HYDRO:
                dendro = request.observed_aura.component_for(AuraKind.DENDRO)
                quicken = request.observed_aura.component_for(AuraKind.QUICKEN)
                if dendro is not None and quicken is not None:
                    raise UnsupportedDendroReactionCandidateError(
                        "燃烧熄灭后的水不支持同时进入普通草和激元素候选"
                    )
                bloom_aura = dendro or quicken
                if bloom_aura is not None:
                    try:
                        bloom = self._resolution_for_key(
                            _with_elemental_application(
                                replace(request, observed_burning_state=None),
                                order=request.order + 1,
                                element=Element.HYDRO,
                                amount=parallel.shared_incoming_remaining,
                                observed_aura=AuraView(request.subject_ref, (bloom_aura,)),
                            ),
                            "reaction.bloom",
                        )
                    except ValueError as exc:
                        raise UnsupportedDendroReactionCandidateError(
                            "剩余水雷预算将进入未实现的草元素反应"
                        ) from exc
                    if bloom is None or bloom.occurrence is None:
                        raise ReactionSelectionError("燃烧熄灭后的普通绽放候选不完整")
            elif request.incoming_element is Element.ELECTRO:
                if request.observed_aura.component_for(AuraKind.DENDRO) is not None or (
                    request.observed_aura.component_for(AuraKind.QUICKEN) is not None
                ):
                    raise UnsupportedDendroReactionCandidateError(
                        "剩余雷预算将进入未实现的草元素反应"
                    )
            elif request.incoming_element is Element.CRYO:
                persistent = PersistentIncomingAuraApplicationEffect(
                    effect_ref=f"{burning_occurrence.occurrence_ref}:dendro-cryo-residual"
                )
        occurrence = replace(
            burning_occurrence,
            transition=summary_transition,
            persistent_incoming_aura_application=persistent,
            parallel_aura_consumption=parallel,
        )
        base_step = burning_resolution.sequence.steps[0]
        intents = base_step.state_planning_intents
        state = request.observed_burning_state
        if burning_branch.aura_remaining.is_zero and state is not None:
            intents = (
                *intents,
                BurningStateTerminationIntent(
                    intent_ref=f"{occurrence.occurrence_ref}:burning-depleted",
                    subject_ref=request.subject_ref,
                    frame=request.frame,
                    expected_state_instance_ref=state.instance_ref,
                    expected_state_revision=state.revision,
                    reason=BurningStateTerminationReason.BURNING_DEPLETED,
                ),
            )
        step = replace(
            base_step,
            elemental_transition_effects=(summary_transition,),
            occurrences=(occurrence,),
            state_planning_intents=intents,
        )
        steps = [step]
        if bloom is not None:
            steps.append(replace(bloom.sequence.steps[0], step_ordinal=1))
        return ReactionResolution(
            request,
            occurrence,
            burning_resolution.damage_adjustment,
            ReactionDecisionSequence(tuple(steps)),
            burning_resolution.generated_impact_batches,
        )

    def _multiple_aura_matches(
        self,
        request: ReactionEvaluationRequest,
    ) -> list[ReactionResolution]:
        """仅把显式声明的多 Aura 规则交回所属机制；运行时不解释候选顺序。"""

        matches: list[ReactionResolution] = []
        for definition in self.registry.definitions:
            if definition.entry_kind.value != "elemental_interaction":
                continue
            if not _definition_matches_trigger_context(definition, request):
                continue
            evaluator = getattr(definition.rule, "evaluate_multiple_aura", None)
            if evaluator is None:
                continue
            resolution = evaluator(request, definition)
            if resolution is not None:
                matches.append(resolution)
        if len(matches) > 1:
            keys = ", ".join(
                match.occurrence.reaction_key for match in matches if match.occurrence is not None
            )
            raise ReactionSelectionError(f"Reaction 多 Aura 候选存在歧义：{keys}")
        return matches

    def _water_electro_combination(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution | None:
        """公共水雷复合候选：先处理雷，再把剩余预算交给水。"""

        if request.incoming_element not in {Element.PYRO, Element.CRYO, Element.GEO}:
            return None
        hydro = request.observed_aura.component_for(AuraKind.HYDRO)
        electro = request.observed_aura.component_for(AuraKind.ELECTRO)
        if hydro is None or electro is None:
            return None
        first_request = replace(
            request,
            observed_aura=AuraView(
                request.subject_ref,
                tuple(
                    component
                    for component in request.observed_aura.components
                    if component.aura_kind is AuraKind.ELECTRO
                ),
            ),
        )
        first_matches = self._elemental_matches_without_combinations(first_request)
        if len(first_matches) != 1:
            return None
        first = first_matches[0]
        first_occurrence = first.occurrence
        if first_occurrence is None:
            return None
        transition = first_occurrence.transition
        if not transition.aura_remaining.is_zero or transition.incoming_remaining.is_zero:
            return first
        second_request = replace(
            request,
            order=request.order + 1,
            incoming_amount=transition.incoming_remaining,
            observed_aura=AuraView(request.subject_ref, (hydro,)),
            trigger_context=replace(
                request.trigger_context,
                elemental_application=replace(
                    request.trigger_context.elemental_application,
                    amount=transition.incoming_remaining,
                ),
            )
            if request.trigger_context is not None
            and request.trigger_context.elemental_application is not None
            else None,
        )
        second_matches = self._elemental_matches_without_combinations(second_request)
        if len(second_matches) != 1:
            return first
        second = second_matches[0]
        second_occurrence = second.occurrence
        if second_occurrence is None:
            return first
        first_step = first.sequence.steps[0]
        if request.incoming_element is Element.CRYO:
            first_occurrence = _suppress_combined_superconduct_damage(first_occurrence)
            first_step = replace(
                first_step,
                occurrences=(first_occurrence,),
            )
            second_occurrence = replace(
                second_occurrence,
                persistent_incoming_aura_application=PersistentIncomingAuraApplicationEffect(
                    effect_ref=f"{second_occurrence.occurrence_ref}:hidden-cryo",
                    loss_policy=AuraLossPolicy.LOSSLESS,
                ),
            )
        second_step = replace(
            second.sequence.steps[0],
            step_ordinal=1,
            occurrences=(second_occurrence,),
        )
        return ReactionResolution(
            request,
            first_occurrence,
            second.damage_adjustment,
            ReactionDecisionSequence((first_step, second_step)),
        )

    def _elemental_matches_without_combinations(
        self,
        request: ReactionEvaluationRequest,
    ) -> list[ReactionResolution]:
        matches = [
            resolution
            for definition in self.registry.definitions
            if definition.entry_kind.value == "elemental_interaction"
            if _definition_matches_trigger_context(definition, request)
            if (resolution := definition.rule.evaluate(request, definition)) is not None
        ]
        return _highest_priority_matches(self.registry, matches)

    def _catalyze_combination(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution | None:
        """执行已冻结的激元素复合候选，避免按注册顺序猜测。"""

        quicken = request.observed_aura.component_for(AuraKind.QUICKEN)
        dendro = request.observed_aura.component_for(AuraKind.DENDRO)
        electro = request.observed_aura.component_for(AuraKind.ELECTRO)
        cryo = request.observed_aura.component_for(AuraKind.CRYO)
        if (
            quicken is not None
            and request.incoming_element is Element.DENDRO
            and electro is not None
        ):
            return self._ordered_catalyze_and_quicken(
                request,
                additive_reaction_key="reaction.spread",
                quicken_reaction_key="reaction.quicken",
            )
        if (
            quicken is not None
            and request.incoming_element is Element.ELECTRO
            and dendro is not None
        ):
            return self._ordered_catalyze_and_quicken(
                request,
                additive_reaction_key="reaction.aggravate",
                quicken_reaction_key="reaction.quicken",
            )
        if quicken is not None and request.incoming_element is Element.ELECTRO and cryo is not None:
            return self._parallel_superconduct_and_aggravate(request)
        if (
            quicken is None
            and request.incoming_element is Element.ELECTRO
            and cryo is not None
            and dendro is not None
        ):
            return self._superconduct_then_quicken(request)
        return None

    def _ordered_catalyze_and_quicken(
        self,
        request: ReactionEvaluationRequest,
        *,
        additive_reaction_key: str,
        quicken_reaction_key: str,
    ) -> ReactionResolution:
        additive = self._resolution_for_key(request, additive_reaction_key)
        if additive is None or additive.occurrence is None:
            raise ReactionSelectionError("激化复合候选缺少附加反应决议")
        quicken = self._resolution_for_key(
            replace(request, order=request.order + 1),
            quicken_reaction_key,
        )
        if quicken is None or quicken.occurrence is None:
            raise ReactionSelectionError("激化复合候选缺少原激化决议")
        first_step = additive.sequence.steps[0]
        second_step = replace(quicken.sequence.steps[0], step_ordinal=1)
        return ReactionResolution(
            request,
            additive.occurrence,
            additive.damage_adjustment,
            ReactionDecisionSequence((first_step, second_step)),
        )

    def _parallel_superconduct_and_aggravate(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution:
        superconduct = self._resolution_for_key(request, "reaction.superconduct")
        aggravate = self._resolution_for_key(
            replace(request, order=request.order + 1),
            "reaction.aggravate",
        )
        if (
            superconduct is None
            or superconduct.occurrence is None
            or aggravate is None
            or aggravate.occurrence is None
        ):
            raise ReactionSelectionError("激冰加雷复合候选缺少超导或超激化决议")
        step = ReactionDecisionStep(
            step_ordinal=0,
            selected_candidate_keys=("reaction.superconduct", "reaction.aggravate"),
            elemental_transition_effects=(
                superconduct.occurrence.transition,
                aggravate.occurrence.transition,
            ),
            state_transition_effects=(),
            occurrences=(superconduct.occurrence, aggravate.occurrence),
        )
        return ReactionResolution(
            request,
            superconduct.occurrence,
            aggravate.damage_adjustment,
            ReactionDecisionSequence((step,)),
        )

    def _superconduct_then_quicken(
        self,
        request: ReactionEvaluationRequest,
    ) -> ReactionResolution | None:
        superconduct = self._resolution_for_key(request, "reaction.superconduct")
        if superconduct is None or superconduct.occurrence is None:
            return None
        transition = superconduct.occurrence.transition
        if transition.incoming_remaining.is_zero:
            return superconduct
        dendro = request.observed_aura.component_for(AuraKind.DENDRO)
        assert dendro is not None
        trigger_context = request.trigger_context
        assert trigger_context is not None
        elemental_application = trigger_context.elemental_application
        assert elemental_application is not None
        quicken_request = replace(
            request,
            order=request.order + 1,
            incoming_amount=transition.incoming_remaining,
            observed_aura=AuraView(request.subject_ref, (dendro,)),
            trigger_context=replace(
                trigger_context,
                elemental_application=replace(
                    elemental_application,
                    amount=transition.incoming_remaining,
                ),
            ),
        )
        quicken = self._resolution_for_key(quicken_request, "reaction.quicken")
        if quicken is None or quicken.occurrence is None:
            return superconduct
        return ReactionResolution(
            request,
            superconduct.occurrence,
            None,
            ReactionDecisionSequence(
                (
                    superconduct.sequence.steps[0],
                    replace(quicken.sequence.steps[0], step_ordinal=1),
                )
            ),
        )

    def _resolution_for_key(
        self,
        request: ReactionEvaluationRequest,
        reaction_key: str,
    ) -> ReactionResolution | None:
        definitions = [self.registry.definition_for(reaction_key)]
        if reaction_key == BLOOM_REACTION_KEY:
            with suppress(ValueError):
                definitions.append(self.registry.definition_for(LUNAR_BLOOM_REACTION_KEY))
        matches: list[ReactionResolution] = []
        for definition in definitions:
            if definition.entry_kind.value != "elemental_interaction":
                raise ReactionSelectionError("复合候选只能引用元素交互 Definition")
            resolution = definition.rule.evaluate(request, definition)
            if resolution is not None:
                matches.append(resolution)
        preferred = _highest_priority_matches(self.registry, matches)
        return preferred[0] if preferred else None

    def _reject_unsupported_dendro_candidates(
        self,
        request: ReactionEvaluationRequest,
    ) -> None:
        """对已确认但尚未实现的草系候选，在第一次写入前稳定拒绝。"""

        if request.incoming_amount.is_zero:
            return
        has_quicken = request.observed_aura.component_for(AuraKind.QUICKEN) is not None
        has_dendro = request.observed_aura.component_for(AuraKind.DENDRO) is not None
        if request.incoming_element is Element.HYDRO and (has_quicken or has_dendro):
            raise UnsupportedDendroReactionCandidateError("水进入未实现的绽放候选")
        if request.incoming_element is Element.ANEMO and has_quicken:
            raise UnsupportedDendroReactionCandidateError("雷/风扩散进入未实现的激化扩散候选")

    def _continue_after_state_trigger(
        self,
        state_resolution: ReactionResolution,
    ) -> ReactionResolution:
        occurrence = state_resolution.occurrence
        if (
            occurrence is None
            or occurrence.transition.aura_kind is not AuraKind.FROZEN
            or not occurrence.transition.aura_remaining.is_zero
            or state_resolution.request.trigger_context is None
            or state_resolution.request.trigger_context.elemental_application is None
        ):
            return state_resolution
        follow_up_request = replace(
            state_resolution.request,
            order=state_resolution.request.order + 1,
            observed_aura=AuraView(
                state_resolution.request.subject_ref,
                tuple(
                    component
                    for component in state_resolution.request.observed_aura.components
                    if component.aura_kind is not AuraKind.FROZEN
                ),
            ),
            observed_frozen_state=None,
        )
        matches = self._elemental_matches(follow_up_request)
        if len(matches) > 1:
            keys = ", ".join(
                match.occurrence.reaction_key for match in matches if match.occurrence is not None
            )
            raise ReactionSelectionError(f"碎冰后的 Reaction 候选存在歧义：{keys}")
        if not matches:
            return state_resolution
        follow_up = matches[0]
        follow_up_step = follow_up.sequence.steps[0]
        return ReactionResolution(
            state_resolution.request,
            state_resolution.occurrence,
            follow_up.damage_adjustment,
            ReactionDecisionSequence(
                (
                    *state_resolution.sequence.steps,
                    ReactionDecisionStep(
                        len(state_resolution.sequence.steps),
                        follow_up_step.selected_candidate_keys,
                        follow_up_step.elemental_transition_effects,
                        follow_up_step.state_transition_effects,
                        follow_up_step.occurrences,
                    ),
                )
            ),
        )

    def validate(self, plan: ReactionMutationPlan) -> None:
        if plan.expected_store_version != self.version:
            raise ReactionStoreConflictError("Reaction 变更计划已经过期")
        if plan.operation_id in self._committed_operation_ids:
            raise ReactionStoreConflictError("重复的 Reaction 操作")
        duplicates = set(plan.interaction_ids) & self._committed_interaction_ids
        if duplicates:
            raise ReactionStoreConflictError(f"重复的 Reaction 交互：{sorted(duplicates)!r}")
        if plan.establishment_gate_plan is not None:
            self.validate_establishment_gate_plan(plan.establishment_gate_plan)

    def commit_prevalidated(self, plan: ReactionMutationPlan) -> ReactionCommitReceipt:
        self._ensure_external_write_allowed()
        self.validate(plan)
        self._committed_operation_ids.add(plan.operation_id)
        self._committed_interaction_ids.update(plan.interaction_ids)
        return ReactionCommitReceipt(plan, self.version)

    def is_idle(self) -> bool:
        return self.next_required_frame() is None

    @contextmanager
    def event_publication_guard(self) -> Iterator[None]:
        if self._fact_publication_active:
            raise ReactionStoreConflictError("Reaction 领域事实发布不允许嵌套")
        self._fact_publication_active = True
        try:
            yield
        finally:
            self._fact_publication_active = False

    def _ensure_external_write_allowed(self) -> None:
        if self._fact_publication_active or (
            self._external_write_guard is not None and self._external_write_guard()
        ):
            raise ReactionStoreConflictError("元素结算事实发布期间不允许修改 Reaction")


def _is_frozen_state_consumption(resolution: ReactionResolution) -> bool:
    occurrence = resolution.occurrence
    return (
        occurrence is not None
        and occurrence.transition.aura_kind is AuraKind.FROZEN
        and occurrence.transition.aura_remaining.is_zero
    )


def _without_blocked_establishment_occurrences(
    resolution: ReactionResolution,
    blocked_occurrence_refs: set[str],
    gate_resolutions,
) -> ReactionResolution:
    """从显式决策序列移除 blocked occurrence 及其 Aura 消费。"""

    if not blocked_occurrence_refs:
        return replace(
            resolution,
            establishment_gate_resolutions=gate_resolutions,
        )
    steps: list[ReactionDecisionStep] = []
    surviving_occurrences: list[ReactionOccurrence] = []
    for step in resolution.sequence.steps:
        removed = tuple(
            occurrence
            for occurrence in step.occurrences
            if occurrence.occurrence_ref in blocked_occurrence_refs
        )
        occurrences = tuple(
            occurrence
            for occurrence in step.occurrences
            if occurrence.occurrence_ref not in blocked_occurrence_refs
        )
        removed_transitions = {occurrence.transition for occurrence in removed}
        transitions = tuple(
            transition
            for transition in step.elemental_transition_effects
            if transition not in removed_transitions
        )
        if not occurrences and not transitions and not step.state_transition_effects:
            continue
        removed_keys = {occurrence.reaction_key for occurrence in removed}
        candidate_keys = tuple(
            key for key in step.selected_candidate_keys if key not in removed_keys
        )
        if not candidate_keys:
            candidate_keys = tuple(
                dict.fromkeys(occurrence.reaction_key for occurrence in occurrences)
            )
        if not candidate_keys:
            continue
        steps.append(
            ReactionDecisionStep(
                len(steps),
                candidate_keys,
                transitions,
                step.state_transition_effects,
                occurrences,
            )
        )
        surviving_occurrences.extend(occurrences)
    surviving_refs = {occurrence.occurrence_ref for occurrence in surviving_occurrences}
    return replace(
        resolution,
        occurrence=(None if not surviving_occurrences else surviving_occurrences[0]),
        decision_sequence=ReactionDecisionSequence(tuple(steps)),
        generated_impact_batches=tuple(
            batch
            for batch in resolution.generated_impact_batches
            if set(batch.parent_occurrence_refs).issubset(surviving_refs)
        ),
        establishment_gate_resolutions=gate_resolutions,
    )


def _suppress_combined_superconduct_damage(occurrence: ReactionOccurrence) -> ReactionOccurrence:
    """冰水雷双反应保留超导 occurrence/减抗，只移除其独立冰伤。"""

    groups: list[ReactionEffectGroup] = []
    for group in occurrence.effect_groups:
        suppressed = tuple(
            effect.effect_ref
            for effect in group.effects
            if isinstance(effect, GeneratedDamageImpactEffect)
        )
        effects = tuple(
            effect
            for effect in group.effects
            if not isinstance(effect, GeneratedDamageImpactEffect)
        )
        if not effects:
            continue
        groups.append(
            replace(
                group,
                effects=tuple(
                    replace(effect, effect_order=index) for index, effect in enumerate(effects)
                ),
                suppressed_effect_refs=(*group.suppressed_effect_refs, *suppressed),
            )
        )
    return replace(occurrence, effect_groups=tuple(groups))


def _with_elemental_application(
    request: ReactionEvaluationRequest,
    *,
    order: int,
    element: Element,
    amount: AuraAmount,
    observed_aura: AuraView,
) -> ReactionEvaluationRequest:
    trigger_context = request.trigger_context
    if trigger_context is not None and trigger_context.elemental_application is not None:
        trigger_context = replace(
            trigger_context,
            elemental_application=replace(
                trigger_context.elemental_application,
                element=element,
                amount=amount,
            ),
        )
    return replace(
        request,
        order=order,
        incoming_element=element,
        incoming_amount=amount,
        observed_aura=observed_aura,
        trigger_context=trigger_context,
    )


def _definition_matches_trigger_context(
    definition: ReactionDefinition,
    request: ReactionEvaluationRequest,
) -> bool:
    if definition.entry_kind.value == "elemental_interaction":
        return (
            request.trigger_context is not None
            and request.trigger_context.elemental_application is not None
        )
    return request.trigger_context is not None and request.trigger_context.strike_type is not None


def _highest_priority_matches(
    registry: ReactionRegistry,
    matches: list[ReactionResolution],
) -> list[ReactionResolution]:
    if not matches:
        return []
    occurrence_matches = [match for match in matches if match.occurrence is not None]
    if not occurrence_matches:
        return matches
    highest_priority = max(
        registry.definition_for(match.occurrence.reaction_key).selection_priority
        for match in occurrence_matches
        if match.occurrence is not None
    )
    return [
        match
        for match in occurrence_matches
        if match.occurrence is not None
        and registry.definition_for(match.occurrence.reaction_key).selection_priority
        == highest_priority
    ]


def _single_fire_property_resolution(
    runtime: ReactionRuntime,
    request: ReactionEvaluationRequest,
    *,
    component: AuraComponent,
) -> ReactionResolution | None:
    """将一个火性质 Component 隔离为普通火候选，不修改真实 Aura 语义。"""

    projected_component = replace(
        component,
        aura_kind=AuraKind.PYRO,
        state_link_refs=(),
        decay_mode=AuraDecayMode.STANDARD,
    )
    projected_request = replace(
        request,
        observed_aura=AuraView(request.subject_ref, (projected_component,)),
        observed_frozen_state=None,
        observed_electro_charged_state=None,
        observed_burning_state=None,
        observed_quicken_state=None,
    )
    matches = runtime._elemental_matches_without_combinations(projected_request)
    if len(matches) > 1:
        keys = ", ".join(
            item.occurrence.reaction_key for item in matches if item.occurrence is not None
        )
        raise ReactionSelectionError(f"火性质投影候选存在歧义：{keys}")
    return matches[0] if matches else None


def _crystallize_shard_index(
    records: Iterable[ReactionStateRecord],
) -> dict[ReactionStateInstanceRef, CrystallizeShardState]:
    index: dict[ReactionStateInstanceRef, CrystallizeShardState] = {}
    for record in records:
        if not isinstance(record, CrystallizeShardState):
            continue
        if record.instance_ref in index:
            raise ReactionStoreConflictError("结晶晶片 instance_ref 冲突")
        index[record.instance_ref] = record
    return index


def _dendro_core_index(
    records: Iterable[ReactionStateRecord],
) -> dict[ReactionStateInstanceRef, DendroCoreState]:
    index: dict[ReactionStateInstanceRef, DendroCoreState] = {}
    sequences_by_pool: dict[str, set[int]] = {}
    for record in records:
        if not isinstance(record, DendroCoreState):
            continue
        if record.instance_ref in index:
            raise ReactionStoreConflictError("重复的 DendroCoreState instance_ref")
        sequences = sequences_by_pool.setdefault(record.pool_scope, set())
        if record.creation_sequence in sequences:
            raise ReactionStoreConflictError("同一草原核池存在重复 creation_sequence")
        sequences.add(record.creation_sequence)
        index[record.instance_ref] = record
    return index


def _lunar_storm_cloud_index(
    records: Iterable[ReactionStateRecord],
) -> dict[ReactionStateInstanceRef, LunarStormCloudState]:
    index: dict[ReactionStateInstanceRef, LunarStormCloudState] = {}
    for record in records:
        if not isinstance(record, LunarStormCloudState):
            continue
        if record.instance_ref in index:
            raise ReactionStoreConflictError("重复的 LunarStormCloudState instance_ref")
        index[record.instance_ref] = record
    return index


def _lunar_cage_index(
    records: Iterable[ReactionStateRecord],
) -> dict[ReactionStateInstanceRef, LunarCageState]:
    index: dict[ReactionStateInstanceRef, LunarCageState] = {}
    for record in records:
        if not isinstance(record, LunarCageState):
            continue
        if record.instance_ref in index:
            raise ReactionStoreConflictError("重复的 LunarCageState instance_ref")
        index[record.instance_ref] = record
    return index


def _lunar_crystallize_accumulator_index(
    records: Iterable[ReactionStateRecord],
) -> dict[str, LunarCrystallizeAccumulatorState]:
    index: dict[str, LunarCrystallizeAccumulatorState] = {}
    for record in records:
        if not isinstance(record, LunarCrystallizeAccumulatorState):
            continue
        if record.team_ref in index:
            raise ReactionStoreConflictError("重复的 LunarCrystallizeAccumulatorState team_ref")
        index[record.team_ref] = record
    return index


def _sprawling_shot_index(
    records: Iterable[ReactionStateRecord],
) -> dict[ReactionStateInstanceRef, SprawlingShotState]:
    index: dict[ReactionStateInstanceRef, SprawlingShotState] = {}
    for record in records:
        if not isinstance(record, SprawlingShotState):
            continue
        if record.instance_ref in index:
            raise ReactionStoreConflictError("重复的 SprawlingShotState instance_ref")
        index[record.instance_ref] = record
    return index


class UnsupportedDendroReactionCandidateError(ReactionSelectionError):
    """交互确定进入未实现的草系候选时，在第一次写入前抛出。"""
