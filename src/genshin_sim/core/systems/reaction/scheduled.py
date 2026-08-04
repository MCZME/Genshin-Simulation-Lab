"""ReactionState 周期根工作到结算声明的窄适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.reaction.mechanics.burning import (
    BURNING_DAMAGE_BASE_MULTIPLIER,
    BURNING_DAMAGE_KIND_KEY,
    BURNING_GATE_DEFINITION_KEY,
    BURNING_PYRO_APPLICATION_AMOUNT,
    BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
    BURNING_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged import (
    ELECTRO_CHARGED_BASE_MULTIPLIER,
    ELECTRO_CHARGED_DAMAGE_KIND_KEY,
    ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    ELECTRO_CHARGED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_ATTACK_PROFILE_KEY,
    LUNAR_ELECTRO_CHARGED_DAMAGE_KIND_KEY,
    LUNAR_ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
    LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
    LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER,
    LUNAR_STORM_CLOUD_ATTACK_RADIUS,
)
from genshin_sim.core.systems.reaction.models import (
    AreaAroundPositionSelection,
    AreaAroundSubjectSelection,
    CurrentSubjectSelection,
    ElectroChargedPropagationSelection,
    GeneratedDamageImpactEffect,
    LunarStormCloudAttackEffect,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionGeneratedImpactProvenance,
)
from genshin_sim.core.systems.reaction.states import (
    BurningCycleRootWork,
    BurningState,
    ElectroChargedState,
    ElectroChargedTickRootWork,
    LunarStormCloudAttackRootWork,
    LunarStormCloudState,
    ReactionStateRecord,
    ScheduledReactionRootWork,
)


@dataclass(frozen=True, slots=True)
class ScheduledRootAdapterResult:
    """适配器只声明当前 root 的后续工作，不执行跨领域写入。"""

    outcome: str
    effect_groups: tuple[ReactionEffectGroup, ...] = ()
    generated_impact_batches: tuple[ReactionGeneratedImpactBatch, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome not in {"prepared", "cancelled_state_ended"}:
            raise ValueError("scheduled root outcome 不受支持")
        if self.outcome == "cancelled_state_ended" and (
            self.effect_groups or self.generated_impact_batches
        ):
            raise ValueError("取消的 scheduled root 不能产生后续工作")


class ScheduledReactionRootAdapter(Protocol):
    adapter_key: str

    @property
    def root_type(self) -> type[object]: ...

    def prepare(
        self,
        root: ScheduledReactionRootWork,
        state_records: tuple[ReactionStateRecord, ...],
    ) -> ScheduledRootAdapterResult: ...


class ScheduledReactionRootAdapterRegistry:
    """以强类型 root 分发，避免公共协调器按 reaction key 分支。"""

    def __init__(self, adapters: tuple[ScheduledReactionRootAdapter, ...] = ()) -> None:
        self._adapters: dict[type[object], ScheduledReactionRootAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ScheduledReactionRootAdapter) -> None:
        if not isinstance(adapter.adapter_key, str) or not adapter.adapter_key.strip():
            raise ValueError("scheduled root adapter_key 必须是非空字符串")
        if not isinstance(adapter.root_type, type):
            raise ValueError("scheduled root adapter 必须声明 root_type")
        if adapter.root_type in self._adapters:
            raise ValueError(f"重复的 scheduled root adapter：{adapter.adapter_key}")
        self._adapters[adapter.root_type] = adapter

    def prepare(
        self,
        root: ScheduledReactionRootWork,
        state_records: tuple[ReactionStateRecord, ...],
    ) -> ScheduledRootAdapterResult:
        adapter = self._adapters.get(type(root))
        if adapter is None:
            raise ValueError(f"未注册的 scheduled root 类型：{type(root).__name__}")
        result = adapter.prepare(root, state_records)
        if not isinstance(result, ScheduledRootAdapterResult):
            raise ValueError("scheduled root adapter 必须返回 ScheduledRootAdapterResult")
        return result


class ElectroChargedScheduledRootAdapter:
    """将普通感电周期工作投影为下一 settlement round 的传播伤害。"""

    adapter_key = "reaction_scheduled_root_adapter.electro_charged"

    @property
    def root_type(self) -> type[object]:
        return ElectroChargedTickRootWork

    def prepare(
        self,
        root: ScheduledReactionRootWork,
        state_records: tuple[ReactionStateRecord, ...],
    ) -> ScheduledRootAdapterResult:
        if not isinstance(root, ElectroChargedTickRootWork):
            raise ValueError("感电 scheduled adapter 只接受 ElectroChargedTickRootWork")
        state = next(
            (
                record
                for record in state_records
                if isinstance(record, ElectroChargedState)
                and record.subject_ref == root.subject_ref
            ),
            None,
        )
        if state is None or state.instance_ref != root.state_instance_ref:
            return ScheduledRootAdapterResult("cancelled_state_ended")
        return ScheduledRootAdapterResult(
            "prepared",
            effect_groups=(_electro_charged_tick_effect_group(state, root),),
        )


class BurningScheduledRootAdapter:
    """将燃烧伤害 cursor 投影为下一 settlement round 的范围伤害。"""

    adapter_key = "reaction_scheduled_root_adapter.burning"

    @property
    def root_type(self) -> type[object]:
        return BurningCycleRootWork

    def prepare(
        self,
        root: ScheduledReactionRootWork,
        state_records: tuple[ReactionStateRecord, ...],
    ) -> ScheduledRootAdapterResult:
        if not isinstance(root, BurningCycleRootWork):
            raise ValueError("燃烧 scheduled adapter 只接受 BurningCycleRootWork")
        state = next(
            (
                record
                for record in state_records
                if isinstance(record, BurningState) and record.subject_ref == root.subject_ref
            ),
            None,
        )
        if state is None or state.instance_ref != root.state_instance_ref:
            return ScheduledRootAdapterResult("cancelled_state_ended")
        groups = () if root.damage_cause is None else (_burning_tick_effect_group(state, root),)
        generated_batches = (
            () if root.pyro_cause is None else (_burning_pyro_application_batch(state, root),)
        )
        return ScheduledRootAdapterResult(
            "prepared",
            effect_groups=groups,
            generated_impact_batches=generated_batches,
        )


class LunarStormCloudScheduledRootAdapter:
    """将雷暴云周期攻击投影为下一 settlement round 的范围攻击声明。"""

    adapter_key = "reaction_scheduled_root_adapter.lunar_storm_cloud"

    @property
    def root_type(self) -> type[object]:
        return LunarStormCloudAttackRootWork

    def prepare(
        self,
        root: ScheduledReactionRootWork,
        state_records: tuple[ReactionStateRecord, ...],
    ) -> ScheduledRootAdapterResult:
        if not isinstance(root, LunarStormCloudAttackRootWork):
            raise ValueError("雷暴云 scheduled adapter 只接受 LunarStormCloudAttackRootWork")
        state = next(
            (
                record
                for record in state_records
                if isinstance(record, LunarStormCloudState)
                and record.instance_ref == root.state_instance_ref
            ),
            None,
        )
        if state is None:
            return ScheduledRootAdapterResult("cancelled_state_ended")
        return ScheduledRootAdapterResult(
            "prepared",
            effect_groups=(_lunar_storm_cloud_attack_effect_group(state, root),),
        )


def create_default_scheduled_reaction_root_adapter_registry() -> (
    ScheduledReactionRootAdapterRegistry
):
    return ScheduledReactionRootAdapterRegistry(
        (
            ElectroChargedScheduledRootAdapter(),
            BurningScheduledRootAdapter(),
            LunarStormCloudScheduledRootAdapter(),
        )
    )


def _electro_charged_tick_effect_group(
    state: ElectroChargedState,
    root: ElectroChargedTickRootWork,
) -> ReactionEffectGroup:
    group_ref = f"{root.work_id}:effect_group:0"
    effect = GeneratedDamageImpactEffect(
        effect_ref=f"{group_ref}:effect:0",
        effect_group_ref=group_ref,
        effect_order=0,
        parent_occurrence_ref=None,
        main_attack_tag=ELECTRO_CHARGED_REACTION_KEY,
        damage_profile_key=state.captured_scaling_basis.damage_profile_key,
        damage_element=DamageElement.ELECTRO,
        gate_definition_key=ELECTRO_CHARGED_GATE_DEFINITION_KEY,
        damage_kind_key=ELECTRO_CHARGED_DAMAGE_KIND_KEY,
        captured_scaling_basis=state.captured_scaling_basis,
        transformative_base_multiplier=ELECTRO_CHARGED_BASE_MULTIPLIER,
        audit_tags=(ELECTRO_CHARGED_REACTION_KEY, "scheduled_state_tick"),
        cause=root.cause,
    )
    return ReactionEffectGroup(
        effect_group_ref=group_ref,
        parent_occurrence_ref=None,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=ElectroChargedPropagationSelection(
            selection_ref=f"{group_ref}:target_selection",
            primary_subject_ref=root.subject_ref,
        ),
        effects=(effect,),
        cause=root.cause,
    )


def _burning_tick_effect_group(
    state: BurningState,
    root: BurningCycleRootWork,
) -> ReactionEffectGroup:
    cause = root.damage_cause
    if cause is None:
        raise ValueError("燃烧伤害 Effect group 必须具有 damage cause")
    group_ref = f"{root.work_id}:burning_damage:effect_group:0"
    effect = GeneratedDamageImpactEffect(
        effect_ref=f"{group_ref}:effect:0",
        effect_group_ref=group_ref,
        effect_order=0,
        parent_occurrence_ref=None,
        main_attack_tag=BURNING_REACTION_KEY,
        damage_profile_key=state.captured_scaling_basis.damage_profile_key,
        damage_element=DamageElement.PYRO,
        gate_definition_key=BURNING_GATE_DEFINITION_KEY,
        damage_kind_key=BURNING_DAMAGE_KIND_KEY,
        captured_scaling_basis=state.captured_scaling_basis,
        transformative_base_multiplier=BURNING_DAMAGE_BASE_MULTIPLIER,
        audit_tags=(BURNING_REACTION_KEY, "scheduled_state_tick"),
        cause=cause,
    )
    return ReactionEffectGroup(
        effect_group_ref=group_ref,
        parent_occurrence_ref=None,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=AreaAroundSubjectSelection(
            selection_ref=f"{group_ref}:target_selection",
            anchor_subject_ref=root.subject_ref,
            radius=1.0,
            include_anchor=True,
        ),
        effects=(effect,),
        cause=cause,
    )


def _burning_pyro_application_batch(
    state: BurningState,
    root: BurningCycleRootWork,
) -> ReactionGeneratedImpactBatch:
    cause = root.pyro_cause
    if cause is None:
        raise ValueError("燃烧周期火 Impact batch 必须具有 pyro cause")
    batch_ref = f"{root.work_id}:burning_pyro:emission_batch:0"
    impact_ref = f"{batch_ref}:generated_impact:0"
    return ReactionGeneratedImpactBatch(
        emission_batch_ref=batch_ref,
        parent_root_work_ref=root.work_id,
        parent_occurrence_refs=(),
        settlement_round=1,
        target_selection=CurrentSubjectSelection(
            selection_ref=f"{batch_ref}:target_selection",
            subject_ref=root.subject_ref,
        ),
        source_ref=state.current_effect_owner,
        captured_source_observation=state.captured_scaling_basis,
        impacts=(
            ReactionGeneratedImpact(
                generated_impact_ref=impact_ref,
                emission_order=0,
                element=Element.PYRO,
                elemental_amount=BURNING_PYRO_APPLICATION_AMOUNT,
                aura_application_profile_key=BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
                provenance=ReactionGeneratedImpactProvenance(
                    provenance_ref=f"{impact_ref}:provenance",
                    parent_occurrence_ref=None,
                    reaction_profile_key=(state.captured_scaling_basis.reaction_profile_key),
                    cause=cause,
                ),
            ),
        ),
        causes=(cause,),
    )


def _lunar_storm_cloud_attack_effect_group(
    state: LunarStormCloudState,
    root: LunarStormCloudAttackRootWork,
) -> ReactionEffectGroup:
    if root.cause is None:
        raise ValueError("雷暴云攻击 Effect group 必须具有 scheduled cause")
    group_ref = f"{root.work_id}:effect_group:0"
    effect = LunarStormCloudAttackEffect(
        effect_ref=f"{group_ref}:effect:0",
        effect_group_ref=group_ref,
        effect_order=0,
        main_attack_tag=LUNAR_ELECTRO_CHARGED_REACTION_KEY,
        damage_profile_key=LUNAR_ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
        damage_element=DamageElement.ELECTRO,
        damage_kind_key=LUNAR_ELECTRO_CHARGED_DAMAGE_KIND_KEY,
        trigger_source_ref=state.trigger_source_ref,
        reaction_profile_key=LUNAR_ELECTRO_CHARGED_ATTACK_PROFILE_KEY,
        reaction_multiplier=LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER,
        gate_definition_key=LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
        audit_tags=(LUNAR_ELECTRO_CHARGED_REACTION_KEY, "scheduled_state_tick"),
        cause=root.cause,
    )
    return ReactionEffectGroup(
        effect_group_ref=group_ref,
        parent_occurrence_ref=None,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=AreaAroundPositionSelection(
            selection_ref=f"{group_ref}:target_selection",
            center=root.cloud_position,
            radius=LUNAR_STORM_CLOUD_ATTACK_RADIUS,
            eligibility_policy_key="reaction_target.lunar_storm_cloud_attack",
        ),
        effects=(effect,),
        cause=root.cause,
    )
