"""元素协调器依赖的领域窄协议。"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionEligibilityView,
)
from genshin_sim.core.coordination.elemental_reaction.models import (
    CommittedElementalImpactEvidence,
    ElementalInteractionBatchRecord,
    ReactionTargetEligibility,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialCreationReceipt,
)
from genshin_sim.core.elements import AuraAmount, AuraKind, ElementalSubjectRef
from genshin_sim.core.events import GameEvent
from genshin_sim.core.impacts import ImpactRequest
from genshin_sim.core.space import SpaceEntityCommitReceipt, SpaceEntityMutationPlan, SpatialEntity
from genshin_sim.core.systems.aura.models import (
    AuraApplicationRequest,
    AuraApplicationResult,
    AuraCommitReceipt,
    AuraComponent,
    AuraMutationPlan,
    AuraStateLinkMutationRequest,
    AuraTransitionResult,
    AuraView,
    BurningAuraApplicationRequest,
    BurningAuraEstablishmentRequest,
    FrozenAuraApplicationRequest,
    QuickenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd.models import (
    IcdCommitReceipt,
    IcdImpactRequest,
    IcdMutationPlan,
    IcdResolution,
)
from genshin_sim.core.systems.damage import (
    AmplifyingReactionInput,
    CatalyzeReactionInput,
    DamageResolutionRecord,
    LunarReactionDamageInput,
    SecondaryAmplifyingReactionInput,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.reaction.gates import ReactionDamageGatePlanner
from genshin_sim.core.systems.reaction.models import (
    CrystallizeShardStateCreationIntent,
    CrystallizeSourceObservation,
    DendroCoreStateCreationIntent,
    FreezeResistanceObservation,
    LunarCrystallizeStatePlanningIntent,
    LunarStormCloudStatePlanningIntent,
    ReactionCommitReceipt,
    ReactionEvaluationRequest,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionMutationPlan,
    ReactionResolution,
)
from genshin_sim.core.systems.reaction.resources import (
    LunarBloomDewState,
    ReactionResourceMutationPlan,
)
from genshin_sim.core.systems.reaction.runtime import (
    ReactionStoreCommitReceipt,
    ReactionStoreMutationPlan,
)
from genshin_sim.core.systems.reaction.states import (
    BurningState,
    CrystallizeShardLifecycleState,
    CrystallizeShardState,
    DendroCoreState,
    ElectroChargedState,
    FreezeRecoveryState,
    FrozenState,
    LunarCageState,
    LunarCrystallizeAccumulatorState,
    LunarCrystallizeOccurrenceRecord,
    LunarStormCloudState,
    QuickenState,
    ReactionStateCommitReceipt,
    ReactionStateInstanceRef,
    ReactionStateLifecycleWork,
    ReactionStateMutationPlan,
    ReactionStateRecord,
    SprawlingShotState,
)
from genshin_sim.core.systems.shield import (
    ShieldGrantCommitReceipt,
    ShieldGrantPlan,
    ShieldGrantRequest,
)


class AuraBatchPlanningPort(Protocol):
    """元素交互批次对 Aura 虚拟投影所需的最小能力。"""

    def view(self, subject_ref: ElementalSubjectRef) -> AuraView: ...

    def apply(self, request: AuraApplicationRequest) -> AuraApplicationResult: ...

    def apply_frozen(
        self,
        request: FrozenAuraApplicationRequest,
    ) -> AuraApplicationResult: ...

    def apply_burning(
        self,
        request: BurningAuraApplicationRequest,
    ) -> AuraApplicationResult: ...

    def apply_quicken(
        self,
        request: QuickenAuraApplicationRequest,
    ) -> AuraApplicationResult: ...

    def establish_burning(
        self,
        request: BurningAuraEstablishmentRequest,
    ) -> tuple[AuraApplicationResult, AuraApplicationResult]: ...

    def mutate_state_links(
        self,
        request: AuraStateLinkMutationRequest,
    ) -> AuraComponent: ...

    def consume(
        self,
        *,
        interaction_id: str,
        subject_ref: ElementalSubjectRef,
        aura_kind: AuraKind,
        amount: AuraAmount,
    ) -> AuraTransitionResult: ...

    def seal(self) -> AuraMutationPlan: ...


class AuraInteractionPort(Protocol):
    """协调器对 Aura 领域需要的计划与提交入口。"""

    @property
    def version(self) -> int: ...

    def view(self, subject_ref: ElementalSubjectRef) -> AuraView: ...

    def begin_batch(self, frame: int, batch_id: str) -> AuraBatchPlanningPort: ...

    def validate(self, plan: AuraMutationPlan) -> None: ...

    def commit_prevalidated(self, plan: AuraMutationPlan) -> AuraCommitReceipt: ...

    def event_publication_guard(self) -> AbstractContextManager[None]: ...


class AuraFramePort(AuraInteractionPort, Protocol):
    """元素状态帧对 Aura 领域需要的最小能力。"""

    @property
    def normalized_through_frame(self) -> int: ...

    def update_frame(self, context: object, frame: int) -> None: ...

    def is_idle(self) -> bool: ...


class AuraIcdBatchPlanningPort(Protocol):
    """元素交互批次对 Aura ICD 虚拟投影所需的最小能力。"""

    def prepare(self, request: IcdImpactRequest) -> IcdResolution: ...

    def seal(self) -> IcdMutationPlan: ...


class AuraIcdInteractionPort(Protocol):
    """协调器对 Aura ICD 领域需要的计划与提交入口。"""

    @property
    def version(self) -> int: ...

    def begin_batch(self, frame: int, batch_id: str) -> AuraIcdBatchPlanningPort: ...

    def validate(self, plan: IcdMutationPlan) -> None: ...

    def commit_prevalidated(self, plan: IcdMutationPlan) -> IcdCommitReceipt: ...


class AuraIcdFramePort(AuraIcdInteractionPort, Protocol):
    """元素状态帧对 Aura ICD 领域需要的最小能力。"""

    def update_frame(self, context: object, frame: int) -> None: ...

    def is_idle(self) -> bool: ...


class ReactionBatchPlanningPort(Protocol):
    """元素交互批次对 Reaction 虚拟投影所需的最小能力。"""

    def prepare(self, request: ReactionEvaluationRequest) -> ReactionResolution: ...

    def seal(self) -> ReactionMutationPlan: ...


class ReactionInteractionPort(Protocol):
    """协调器对 Reaction 领域需要的计划与提交入口。"""

    @property
    def version(self) -> int: ...

    def begin_batch(self, frame: int, batch_id: str) -> ReactionBatchPlanningPort: ...

    def validate(self, plan: ReactionMutationPlan) -> None: ...

    def commit_prevalidated(self, plan: ReactionMutationPlan) -> ReactionCommitReceipt: ...

    def frozen_state_for(self, subject_ref: ElementalSubjectRef) -> FrozenState | None: ...


class FreezeResistanceObservationPort(Protocol):
    """Reaction 只读冻结抗性所需的窄观察端口。"""

    def observe_freeze_resistance(
        self,
        context: object,
        *,
        subject_ref: ElementalSubjectRef,
        frame: int,
    ) -> FreezeResistanceObservation: ...


class ReactionFramePort(ReactionInteractionPort, Protocol):
    """元素状态帧对 ReactionState 需要的最小生命周期入口。"""

    def update_frame(self, context: object, frame: int) -> None: ...

    def next_required_frame(self) -> int | None: ...

    def is_idle(self) -> bool: ...


class ReactionStateInteractionPort(ReactionFramePort, Protocol):
    """Aura / ReactionState Link 批次需要的 State 计划和提交入口。"""

    @property
    def state_records(self) -> tuple[ReactionStateRecord, ...]: ...

    def frozen_state_for(self, subject_ref: ElementalSubjectRef) -> FrozenState | None: ...

    def freeze_recovery_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> FreezeRecoveryState | None: ...

    def electro_charged_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> ElectroChargedState | None: ...

    def burning_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> BurningState | None: ...

    def quicken_state_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> QuickenState | None: ...

    def crystallize_shard_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> CrystallizeShardState | None: ...

    def dendro_core_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> DendroCoreState | None: ...

    def lunar_storm_cloud_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState | None: ...

    def active_lunar_storm_clouds(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarStormCloudState, ...]: ...

    def lunar_cage_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState | None: ...

    def active_lunar_cages(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarCageState, ...]: ...

    def lunar_crystallize_accumulator_for(
        self,
        team_ref: str,
    ) -> LunarCrystallizeAccumulatorState | None: ...

    def sprawling_shot_state_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> SprawlingShotState | None: ...

    def begin_state_batch(
        self,
        frame: int,
        batch_id: str,
    ) -> ReactionStateBatchPlanningPort: ...

    def begin_resource_batch(
        self,
        frame: int,
        batch_id: str,
    ) -> ReactionResourceBatchPlanningPort: ...

    def begin_gate_batch(
        self,
        frame: int,
        operation_id: str,
    ) -> ReactionDamageGatePlanner: ...

    def validate_store_mutation_plan(self, plan: ReactionStoreMutationPlan) -> None: ...

    def commit_prevalidated_store_mutation_plan(
        self,
        plan: ReactionStoreMutationPlan,
    ) -> ReactionStoreCommitReceipt: ...

    def validate_state_plan(self, plan: ReactionStateMutationPlan) -> None: ...

    def commit_prevalidated_state_plan(
        self,
        plan: ReactionStateMutationPlan,
    ) -> ReactionStateCommitReceipt: ...

    def publish_committed_state_facts(
        self,
        context: object,
        receipt: ReactionStateCommitReceipt,
    ) -> None: ...


class ReactionResourceBatchPlanningPort(Protocol):
    def refresh_lunar_bloom_dew(self, *, team_ref: str) -> LunarBloomDewState: ...

    def seal(self) -> ReactionResourceMutationPlan: ...


class ReactionStateBatchPlanningPort(Protocol):
    def frozen_for(self, subject_ref: ElementalSubjectRef) -> FrozenState | None: ...

    def freeze_recovery_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> FreezeRecoveryState | None: ...

    def electro_charged_for(
        self,
        subject_ref: ElementalSubjectRef,
    ) -> ElectroChargedState | None: ...

    def burning_for(self, subject_ref: ElementalSubjectRef) -> BurningState | None: ...

    def quicken_for(self, subject_ref: ElementalSubjectRef) -> QuickenState | None: ...

    def active_dendro_cores(
        self,
        *,
        pool_scope: str | None = None,
    ) -> tuple[DendroCoreState, ...]: ...

    def active_lunar_cages(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarCageState, ...]: ...

    def lunar_cage_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState | None: ...

    def lunar_crystallize_accumulator_for(
        self,
        team_ref: str,
    ) -> LunarCrystallizeAccumulatorState | None: ...

    def create_lunar_cage(
        self,
        intent: LunarCrystallizeStatePlanningIntent,
        *,
        index: int,
    ) -> LunarCageState: ...

    def remove_lunar_cage(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarCageState: ...

    def replace_lunar_cage_after_harmony(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        frame: int,
    ) -> LunarCageState: ...

    def append_lunar_crystallize_record(
        self,
        *,
        team_ref: str,
        subject_ref: ElementalSubjectRef,
        record: LunarCrystallizeOccurrenceRecord,
    ) -> LunarCrystallizeAccumulatorState: ...

    def consume_lunar_crystallize_records(
        self,
        *,
        team_ref: str,
        count: int = 3,
    ) -> tuple[
        tuple[LunarCrystallizeOccurrenceRecord, ...],
        LunarCrystallizeAccumulatorState | None,
    ]: ...

    def lunar_storm_cloud_for(
        self,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState | None: ...

    def active_lunar_storm_clouds(
        self,
        *,
        team_ref: str | None = None,
    ) -> tuple[LunarStormCloudState, ...]: ...

    def create_frozen(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        state_link_ref,
        next_required_frame: int | None = None,
        decay_rate: float = 0.4,
        decay_rate_updated_frame: int | None = None,
    ) -> FrozenState: ...

    def replace_frozen(self, state: FrozenState) -> FrozenState: ...

    def create_electro_charged(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        created_by_occurrence_ref: str,
        current_effect_owner,
        captured_scaling_basis,
        next_tick_frame: int,
        next_tick_index: int = 1,
    ) -> ElectroChargedState: ...

    def create_burning(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        burning_aura_link_ref,
        dendro_like_link_refs,
        created_by_occurrence_ref: str,
        current_effect_owner,
        captured_scaling_basis,
        next_dendro_like_depletion_frame: int,
        next_damage_tick_frame: int,
        next_damage_tick_index: int,
        next_pyro_application_frame: int,
        next_pyro_application_index: int,
    ) -> BurningState: ...

    def create_quicken(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        quicken_aura_link_ref,
        created_by_occurrence_ref: str,
        last_updated_by_occurrence_ref: str | None = None,
    ) -> QuickenState: ...

    def create_crystallize_shard(
        self,
        intent: CrystallizeShardStateCreationIntent,
    ) -> object: ...

    def create_dendro_core(self, intent: DendroCoreStateCreationIntent) -> DendroCoreState: ...

    def remove_dendro_core(self, *, instance_ref: ReactionStateInstanceRef) -> DendroCoreState: ...

    def create_lunar_storm_cloud(
        self,
        intent: LunarStormCloudStatePlanningIntent,
    ) -> LunarStormCloudState: ...

    def replace_lunar_storm_cloud(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        expires_at_frame: int,
    ) -> LunarStormCloudState: ...

    def replace_lunar_storm_cloud_attack(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        next_attack_frame: int,
        next_attack_index: int,
    ) -> LunarStormCloudState: ...

    def remove_lunar_storm_cloud(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> LunarStormCloudState: ...

    def create_sprawling_shot(self, state: SprawlingShotState) -> SprawlingShotState: ...

    def remove_sprawling_shot(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
    ) -> SprawlingShotState: ...

    def terminalize_crystallize_shard(
        self,
        *,
        instance_ref: ReactionStateInstanceRef,
        lifecycle_state: CrystallizeShardLifecycleState,
    ) -> CrystallizeShardState: ...

    def replace_electro_charged(
        self,
        state: ElectroChargedState,
    ) -> ElectroChargedState: ...

    def replace_burning(self, state: BurningState) -> BurningState: ...

    def replace_quicken(self, state: QuickenState) -> QuickenState: ...

    def remove_electro_charged(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref=None,
    ) -> ElectroChargedState: ...

    def remove_burning(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref=None,
    ) -> BurningState: ...

    def remove_quicken(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref=None,
    ) -> QuickenState: ...

    def remove_frozen(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        expected_instance_ref=None,
    ) -> FrozenState: ...

    def create_freeze_recovery(
        self,
        *,
        subject_ref: ElementalSubjectRef,
        decay_rate: float,
        decay_rate_updated_frame: int | None = None,
    ) -> FreezeRecoveryState: ...

    def seal(self) -> ReactionStateMutationPlan: ...


class DamageImpactPlanningPort(Protocol):
    """协调器对 Damage 领域需要的预检和提交入口。"""

    def prepare_impact_request(
        self,
        context: object,
        request: ImpactRequest,
        *,
        amplifying_reactions: Mapping[str, AmplifyingReactionInput] | None = None,
        secondary_amplifying_reactions: (
            Mapping[str, SecondaryAmplifyingReactionInput] | None
        ) = None,
        transformative_reactions: Mapping[str, TransformativeReactionInput] | None = None,
        catalyze_reactions: Mapping[str, CatalyzeReactionInput] | None = None,
        lunar_reactions: Mapping[str, LunarReactionDamageInput] | None = None,
    ) -> tuple[DamageResolutionRecord, ...]: ...

    def commit_prepared_records(self, records: tuple[DamageResolutionRecord, ...]) -> None: ...

    def publish_committed_facts(
        self,
        context: object,
        records: tuple[DamageResolutionRecord, ...],
    ) -> None: ...


class CrystallizeSourceObservationPort(Protocol):
    """普通结晶在成立时读取来源等级与元素精通的窄观察。"""

    def observe(
        self,
        *,
        frame: int,
        source_ref,
        owner_slot: int,
        source_level: int,
    ) -> CrystallizeSourceObservation: ...


class ReactionSpatialBatchPlanningPort(Protocol):
    @property
    def creation_receipts(self) -> tuple[ReactionSpatialCreationReceipt, ...]: ...

    def prepare_create(self, effect, *, anchor: SpatialEntity) -> object: ...

    def prepare_create_entity(self, entity: SpatialEntity) -> SpatialEntity: ...

    def prepare_remove(self, entity_id: str) -> SpatialEntity: ...

    def cancel_create(self, entity_id: str) -> None: ...

    def seal(self) -> SpaceEntityMutationPlan: ...


class ReactionSpatialPlanningPort(Protocol):
    def begin_batch(
        self,
        *,
        operation_id: str,
        frame: int,
    ) -> ReactionSpatialBatchPlanningPort: ...

    def validate(self, plan: SpaceEntityMutationPlan) -> None: ...

    def commit_prevalidated(
        self,
        plan: SpaceEntityMutationPlan,
    ) -> SpaceEntityCommitReceipt: ...

    def event_publication_guard(self) -> AbstractContextManager[None]: ...


class CrystallizeShieldGrantPort(Protocol):
    """晶片拾取流程对 Shield 领域需要的最小计划与事实入口。"""

    def prepare_grant(self, request: ShieldGrantRequest) -> ShieldGrantPlan: ...

    def validate(self, plan: ShieldGrantPlan) -> None: ...

    def commit_prevalidated(self, plan: ShieldGrantPlan) -> ShieldGrantCommitReceipt: ...

    def events_for(self, receipt: ShieldGrantCommitReceipt) -> tuple[GameEvent, ...]: ...

    def publish_committed_facts(self, receipt: ShieldGrantCommitReceipt) -> None: ...

    def event_publication_guard(self) -> AbstractContextManager[None]: ...


class ReactionBoundEntityExpiryPort(Protocol):
    """Reaction State 绑定实体到期流程的唯一写入口。"""

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]: ...


class DendroCoreExpiryPort(Protocol):
    """草原核到期时终结 State/Space 并冻结后续爆炸声明。"""

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> object: ...


class LunarStormCloudExpiryPort(Protocol):
    """雷暴云到期时终结 State/Space 的唯一写入口。"""

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]: ...


class LunarCageExpiryPort(Protocol):
    """月笼到期时终结 State/Space 的唯一写入口。"""

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]: ...


class ReactionGeneratedImpactDamageInputAdapter(Protocol):
    """由 Reaction 机制把派生 Impact 映射为 Damage 所需的剧变公式输入。"""

    def transformative_input(
        self,
        *,
        batch: ReactionGeneratedImpactBatch,
        impact: ReactionGeneratedImpact,
    ) -> TransformativeReactionInput: ...


class ElementalStateFramePort(Protocol):
    """元素交互开始前需要的帧规范化入口。"""

    def normalize(self, context: object, frame: int) -> object: ...


class CommittedElementalImpactEvidencePort(Protocol):
    """草原核接触等窄流程读取已提交元素 Impact 证据的端口。"""

    def committed_elemental_impact_evidence_for(
        self,
        impact_ref: str,
    ) -> CommittedElementalImpactEvidence | None: ...


class ElementalImpactSettlementPort(Protocol):
    """元素 settlement 协调器对交互协调器需要的唯一入口。"""

    def handle_damage_impact(
        self,
        context: object,
        request: ImpactRequest,
    ) -> ElementalInteractionBatchRecord: ...

    def handle_aura_impact(
        self,
        context: object,
        request: ImpactRequest,
    ) -> ElementalInteractionBatchRecord: ...


class ReactionTargetEligibilityPort(Protocol):
    """元素协调器向范围候选查询关系与能力的窄端口。"""

    def evaluate(
        self,
        context: object,
        *,
        entity: object,
        distance_xz: float,
    ) -> ReactionTargetEligibility: ...


class ReactionEligibilityReadPort(Protocol):
    """Reaction 读取队伍 capability 准入证据的窄端口。"""

    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView: ...
