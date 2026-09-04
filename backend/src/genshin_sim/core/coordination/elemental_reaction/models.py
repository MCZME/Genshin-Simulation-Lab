"""元素协调器使用的工作、目标资格和稳定审计模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from genshin_sim.core.elements import AuraAmount, Element, ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.impacts import ImpactRequest
from genshin_sim.core.systems.aura import AuraView
from genshin_sim.core.systems.reaction.models import (
    ReactionEffectGroup,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
)
from genshin_sim.core.systems.reaction.states import ScheduledStateTickCause


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


class ElementalInteractionBatchKind(StrEnum):
    ELEMENTAL_INTERACTION = "elemental_interaction"
    REACTION_EFFECT_GROUP = "reaction_effect_group"
    REACTION_GENERATED_IMPACT_BATCH = "reaction_generated_impact_batch"
    SCHEDULED_REACTION_ROOT = "scheduled_reaction_root"


class ElementalSettlementWorkKind(StrEnum):
    REACTION_EFFECT_GROUP = "reaction_effect_group"
    REACTION_GENERATED_IMPACT_BATCH = "reaction_generated_impact_batch"


class ReactionTargetRelation(StrEnum):
    SELF = "self"
    ALLY = "ally"
    HOSTILE = "hostile"
    NEUTRAL_OR_UNKNOWN = "neutral_or_unknown"


class ReactionTargetCapability(StrEnum):
    AURA = "aura"
    DAMAGE = "damage"
    ATTRIBUTE_STATUS = "attribute_status"


@dataclass(frozen=True, slots=True)
class CommittedElementalImpactEvidence:
    """元素交互成功提交后供窄协调流程核验的 Impact 证据。"""

    impact_ref: str
    source_impact_ref: str
    frame: int
    source_ref: ElementalSourceRef
    incoming_element: Element | None
    incoming_amount: AuraAmount

    def __post_init__(self) -> None:
        _text(self.impact_ref, "impact_ref")
        _text(self.source_impact_ref, "source_impact_ref")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.source_ref, ElementalSourceRef):
            raise ValueError("source_ref 必须是 ElementalSourceRef")
        if self.incoming_element is not None and not isinstance(self.incoming_element, Element):
            raise ValueError("incoming_element 必须是 Element 或 None")
        if not isinstance(self.incoming_amount, AuraAmount):
            raise ValueError("incoming_amount 必须是 AuraAmount")
        if self.incoming_element is None and not self.incoming_amount.is_zero:
            raise ValueError("无 incoming_element 的已提交 Impact 不能携带正元素量")


@dataclass(frozen=True, slots=True)
class ElementalSettlementWork:
    """同一 root 内下一 settlement round 执行的强类型工作。"""

    work_id: str
    root_work_id: str
    parent_work_id: str
    frame: int
    settlement_round: int
    payload: ReactionEffectGroup | ReactionGeneratedImpactBatch

    def __post_init__(self) -> None:
        for value, name in (
            (self.work_id, "work_id"),
            (self.root_work_id, "root_work_id"),
            (self.parent_work_id, "parent_work_id"),
        ):
            _text(value, name)
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if (
            isinstance(self.settlement_round, bool)
            or not isinstance(self.settlement_round, int)
            or self.settlement_round <= 0
        ):
            raise ValueError("后续 settlement_round 必须是正整数")
        if not isinstance(self.payload, ReactionEffectGroup | ReactionGeneratedImpactBatch):
            raise ValueError("ElementalSettlementWork 的 payload 不受支持")

    @property
    def kind(self) -> ElementalSettlementWorkKind:
        if isinstance(self.payload, ReactionEffectGroup):
            return ElementalSettlementWorkKind.REACTION_EFFECT_GROUP
        return ElementalSettlementWorkKind.REACTION_GENERATED_IMPACT_BATCH

    @property
    def payload_ref(self) -> str:
        if isinstance(self.payload, ReactionEffectGroup):
            return self.payload.effect_group_ref
        return self.payload.emission_batch_ref


@dataclass(frozen=True, slots=True)
class SimultaneousElementApplicationBatch:
    """同轮次、同目标的多个派生元素施加在策略选择前的冻结输入。"""

    batch_ref: str
    frame: int
    settlement_round: int
    root_work_id: str
    subject_ref: ElementalSubjectRef
    emission_batch_ref: str
    source_ref: ElementalSourceRef
    observed_aura: AuraView
    applications: tuple[ReactionGeneratedImpact, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.batch_ref, "batch_ref"),
            (self.root_work_id, "root_work_id"),
            (self.emission_batch_ref, "emission_batch_ref"),
        ):
            _text(value, name)
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if (
            isinstance(self.settlement_round, bool)
            or not isinstance(self.settlement_round, int)
            or self.settlement_round <= 0
        ):
            raise ValueError("同时元素施加的 settlement_round 必须是正整数")
        if not isinstance(self.source_ref, ElementalSourceRef):
            raise ValueError("source_ref 必须是 ElementalSourceRef")
        if not isinstance(self.observed_aura, AuraView):
            raise ValueError("observed_aura 必须是 AuraView")
        if self.observed_aura.subject_ref != self.subject_ref:
            raise ValueError("同时元素施加 Aura 观察主体必须与 subject_ref 一致")
        applications = tuple(self.applications)
        if len(applications) < 2 or any(
            not isinstance(item, ReactionGeneratedImpact) for item in applications
        ):
            raise ValueError("同时元素施加至少需要两个 ReactionGeneratedImpact")
        if tuple(item.emission_order for item in applications) != tuple(
            sorted(item.emission_order for item in applications)
        ):
            raise ValueError("同时元素施加必须保留稳定的 emission_order 输入顺序")
        if len({item.generated_impact_ref for item in applications}) != len(applications):
            raise ValueError("同时元素施加的 generated_impact_ref 不能重复")
        object.__setattr__(self, "applications", applications)

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_ref": self.batch_ref,
            "frame": self.frame,
            "settlement_round": self.settlement_round,
            "root_work_id": self.root_work_id,
            "subject_ref": {
                "kind": self.subject_ref.kind.value,
                "entity_id": self.subject_ref.entity_id,
            },
            "emission_batch_ref": self.emission_batch_ref,
            "source_ref": self.source_ref.to_dict(),
            "aura_components": tuple(
                {
                    "aura_kind": component.aura_kind.value,
                    "current_amount": component.current_amount.to_dict(),
                }
                for component in self.observed_aura.components
            ),
            "applications": tuple(
                {
                    "generated_impact_ref": item.generated_impact_ref,
                    "emission_order": item.emission_order,
                    "element": item.element.value,
                    "elemental_amount": item.elemental_amount.to_dict(),
                }
                for item in self.applications
            ),
        }


class SimultaneousElementApplicationStrategy(StrEnum):
    SUPPORTED_COMMUTATIVE = "supported_commutative"
    SUPPORTED_ORDERED = "supported_ordered"
    UNSUPPORTED_ORDER_DEPENDENT = "unsupported_order_dependent"


@dataclass(frozen=True, slots=True)
class SimultaneousElementApplicationPolicyResult:
    policy_key: str
    strategy: SimultaneousElementApplicationStrategy

    def __post_init__(self) -> None:
        _text(self.policy_key, "policy_key")
        if not isinstance(self.strategy, SimultaneousElementApplicationStrategy):
            raise ValueError("同时元素施加策略结果不受支持")


class SimultaneousElementApplicationPolicy(Protocol):
    policy_key: str

    def evaluate(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult | None: ...


class SimultaneousElementApplicationPolicyError(RuntimeError):
    """同时元素施加无法映射到唯一策略时的稳定领域错误。"""

    def __init__(
        self,
        batch: SimultaneousElementApplicationBatch,
        *,
        reason: str,
        candidate_policy_keys: tuple[str, ...] = (),
    ) -> None:
        self.batch = batch
        self.reason = reason
        self.candidate_policy_keys = tuple(candidate_policy_keys)
        super().__init__(f"同时元素施加批次没有唯一支持策略：{batch.batch_ref} ({reason})")

    def to_dict(self) -> dict[str, object]:
        payload = self.batch.to_dict()
        payload["reason"] = self.reason
        payload["candidate_policy_keys"] = self.candidate_policy_keys
        return payload


class SimultaneousElementApplicationPolicyRegistry:
    """只选择已显式注册的策略，绝不按元素枚举顺序猜测。"""

    def __init__(self, policies: tuple[SimultaneousElementApplicationPolicy, ...] = ()) -> None:
        self._policies: dict[str, SimultaneousElementApplicationPolicy] = {}
        for policy in policies:
            self.register(policy)

    def register(self, policy: SimultaneousElementApplicationPolicy) -> None:
        policy_key = policy.policy_key
        _text(policy_key, "policy_key")
        if policy_key in self._policies:
            raise ValueError(f"重复的同时元素施加策略：{policy_key}")
        self._policies[policy_key] = policy

    def resolve(
        self,
        batch: SimultaneousElementApplicationBatch,
    ) -> SimultaneousElementApplicationPolicyResult:
        evaluations = tuple(
            (policy, result)
            for _, policy in sorted(self._policies.items())
            if (result := policy.evaluate(batch)) is not None
        )
        if any(
            not isinstance(result, SimultaneousElementApplicationPolicyResult)
            or result.policy_key != policy.policy_key
            for policy, result in evaluations
        ):
            raise ValueError("同时元素施加策略返回结果必须属于当前评估策略")
        results = tuple(result for _, result in evaluations)
        if len(results) != 1:
            raise SimultaneousElementApplicationPolicyError(
                batch,
                reason="no_matching_policy" if not results else "ambiguous_policy",
                candidate_policy_keys=tuple(result.policy_key for result in results),
            )
        result = results[0]
        if result.strategy is SimultaneousElementApplicationStrategy.UNSUPPORTED_ORDER_DEPENDENT:
            raise SimultaneousElementApplicationPolicyError(
                batch,
                reason=result.strategy.value,
                candidate_policy_keys=(result.policy_key,),
            )
        return result


@dataclass(frozen=True, slots=True)
class ReactionTargetEligibility:
    subject_ref: ElementalSubjectRef
    spatial_entity_id: str
    distance_xz: float
    relation: ReactionTargetRelation
    capabilities: frozenset[ReactionTargetCapability] = frozenset()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.spatial_entity_id.strip():
            raise ValueError("spatial_entity_id 必须是非空字符串")
        if self.distance_xz < 0:
            raise ValueError("distance_xz 不能为负数")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True, slots=True)
class ReactionTargetEffectOutcome:
    target_order: int
    subject_ref: ElementalSubjectRef
    relation: ReactionTargetRelation
    capabilities: frozenset[ReactionTargetCapability]
    aura_outcome: str | None = None
    damage_outcome: str | None = None
    status_outcome: str | None = None
    gate_resolution_ref: str | None = None
    damage_request_id: str | None = None
    buff_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReactionDecisionStepRecord:
    """跨领域批次记录中已提交的一步 Reaction 决策审计。"""

    interaction_id: str
    step_ordinal: int
    selected_candidate_keys: tuple[str, ...]
    occurrence_refs: tuple[str, ...]
    state_transition_refs: tuple[str, ...]
    state_planning_intent_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.interaction_id, str) or not self.interaction_id.strip():
            raise ValueError("interaction_id 必须是非空字符串")
        if (
            isinstance(self.step_ordinal, bool)
            or not isinstance(self.step_ordinal, int)
            or self.step_ordinal < 0
        ):
            raise ValueError("step_ordinal 必须是非负整数")
        candidates = tuple(self.selected_candidate_keys)
        if not candidates or any(
            not isinstance(item, str) or not item.strip() for item in candidates
        ):
            raise ValueError("selected_candidate_keys 必须是非空字符串序列")
        occurrence_refs = tuple(self.occurrence_refs)
        if any(not isinstance(item, str) or not item.strip() for item in occurrence_refs):
            raise ValueError("occurrence_refs 必须是非空字符串序列")
        state_transition_refs = tuple(self.state_transition_refs)
        if any(not isinstance(item, str) or not item.strip() for item in state_transition_refs):
            raise ValueError("state_transition_refs 必须是非空字符串序列")
        intent_refs = tuple(self.state_planning_intent_refs)
        if any(not isinstance(item, str) or not item.strip() for item in intent_refs):
            raise ValueError("state_planning_intent_refs 必须是非空字符串序列")
        if tuple(sorted(intent_refs)) != intent_refs or len(set(intent_refs)) != len(intent_refs):
            raise ValueError("state_planning_intent_refs 必须按稳定顺序且不重复")
        object.__setattr__(self, "selected_candidate_keys", candidates)
        object.__setattr__(self, "occurrence_refs", occurrence_refs)
        object.__setattr__(self, "state_transition_refs", state_transition_refs)
        object.__setattr__(self, "state_planning_intent_refs", intent_refs)


@dataclass(frozen=True, slots=True)
class DamageImpactWork:
    """一个 root 元素 Impact 展开到单个目标的稳定工作项。"""

    work_id: str
    root_work_id: str
    target_impact_ref: str
    target_ref: str
    order: int
    request: ImpactRequest


@dataclass(frozen=True, slots=True)
class ElementalInteractionBatchRecord:
    """一次已提交元素交互或 Reaction Effect group 的审计记录。"""

    batch_id: str
    root_work_id: str
    frame: int
    settlement_round: int
    work_ids: tuple[str, ...]
    icd_request_ids: tuple[str, ...]
    aura_transition_interaction_ids: tuple[str, ...]
    reaction_occurrence_refs: tuple[str, ...]
    damage_request_ids: tuple[str, ...]
    reaction_decision_steps: tuple[ReactionDecisionStepRecord, ...] = ()
    current_impact_adjustment_refs: tuple[str, ...] = ()
    batch_kind: ElementalInteractionBatchKind = ElementalInteractionBatchKind.ELEMENTAL_INTERACTION
    parent_work_id: str | None = None
    parent_occurrence_refs: tuple[str, ...] = ()
    effect_group_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()
    target_effect_outcomes: tuple[ReactionTargetEffectOutcome, ...] = ()
    gate_resolution_refs: tuple[str, ...] = ()
    buff_request_ids: tuple[str, ...] = ()
    buff_instance_refs: tuple[str, ...] = ()
    follow_up_work_ids: tuple[str, ...] = ()
    reaction_effect_groups: tuple[ReactionEffectGroup, ...] = ()
    generated_impact_batches: tuple[ReactionGeneratedImpactBatch, ...] = ()
    emission_batch_ref: str | None = None
    generated_impact_refs: tuple[str, ...] = ()
    simultaneous_application_policy_keys: tuple[str, ...] = ()
    captured_source_observation_ref: str | None = None
    scheduled_root_work_id: str | None = None
    scheduled_tick_index: int | None = None
    scheduled_root_outcome: str | None = None
    scheduled_state_tick_causes: tuple[ScheduledStateTickCause, ...] = ()
    spatial_entity_refs: tuple[str, ...] = ()
    reaction_state_binding_refs: tuple[str, ...] = ()
    establishment_gate_resolution_refs: tuple[str, ...] = ()
