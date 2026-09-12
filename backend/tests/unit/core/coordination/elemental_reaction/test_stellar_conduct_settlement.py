# 单一关注点：星超导 4 秒窗口结算后统一刷新队伍角色的辉映·星烁 Buff。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction import (
    ElementalInteractionCoordinator,
    ElementalStateFrameCoordinator,
    ReactionSpatialPlanningAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_RADIANCE_PERSISTENCE_FRAMES,
    plan_radiance_buff_requests,
    stellar_radiance_buff_definition,
)
from genshin_sim.core.elements import Element, ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import AuraRuntime
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.buff import (
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.reaction import (
    PolestarFieldStatePlanningIntent,
    ReactionStateInstanceRef,
    StellarConductAttachmentRecord,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
)

SOURCE = ElementalSourceRef("character:slot_1", "root:setup")
TARGET = ElementalSubjectRef.target("target:star")
CHARACTER_ENTITY_ID = "character:test"
SETUP_OCCURRENCE = "setup:occurrence"


class _NoopHandler:
    def prepare_impact_request(self, *args, **kwargs):  # pragma: no cover - no damage path
        raise AssertionError("星超导结算测试不应准备伤害")

    def commit_prepared_records(self, records):  # pragma: no cover
        raise AssertionError("星超导结算测试不应提交伤害")

    def publish_committed_facts(self, context, records):  # pragma: no cover
        raise AssertionError("星超导结算测试不应发布伤害")


def _setup_intent(*, frame: int = 0) -> PolestarFieldStatePlanningIntent:
    return PolestarFieldStatePlanningIntent(
        intent_ref=f"{SETUP_OCCURRENCE}:polestar-field-plan",
        parent_occurrence_ref=SETUP_OCCURRENCE,
        instance_ref=ReactionStateInstanceRef(f"reaction-state:polestar-field:{SETUP_OCCURRENCE}"),
        subject_ref=TARGET,
        space_entity_ref=f"reaction_object:polestar_field:{SETUP_OCCURRENCE}",
        trigger_source_ref=SOURCE,
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        created_frame=frame,
        expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    )


def _radiance_record(runtime: BuffRuntime, frame: int):
    records = runtime.reader.active(
        frame,
        target_ref=AttributeSubjectRef.character(CHARACTER_ENTITY_ID),
        definition_key=STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    )
    assert len(records) == 1
    return records[0]


def test_stellar_settlement_refreshes_radiance_buff_values() -> None:
    target = TargetRuntimeState("star", spatial_entity_id="target:star")
    space = Space((SpatialEntity("target:star", SpatialEntityKind.TARGET, Vector3(0.0, 0.0, 0.0)),))
    space_runtime = SpaceRuntime(
        space=space,
        team_state=TeamRuntimeState(
            (CharacterRuntimeState(1, "character:test", 90, combat_entity_id=CHARACTER_ENTITY_ID),)
        ),
        targets=TargetRuntimeCollection((target,)),
    )
    context = SimulationContext(space_runtime=space_runtime)
    attribute_registry = create_public_attribute_registry()
    attribute_resolver = AttributeResolver(
        definitions=attribute_registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((), registry=attribute_registry),
    )
    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime()
    reaction_runtime = create_default_reaction_bootstrap().create_runtime()
    spatial_port = ReactionSpatialPlanningAdapter(space)
    buff_runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry((stellar_radiance_buff_definition(),)),
        resolver=BuffResolver(),
        buff_store=BuffStore(),
        event_engine=context.events,
    )
    frame_coordinator = ElementalStateFrameCoordinator(
        aura_runtime,
        icd_runtime,
        reaction_runtime,
    )
    interaction_coordinator = ElementalInteractionCoordinator(
        aura_runtime=aura_runtime,
        icd_runtime=icd_runtime,
        reaction_runtime=reaction_runtime,
        damage_handler=_NoopHandler(),
        frame_coordinator=frame_coordinator,
        transformative_source_observer=CharacterTransformativeSourceObserver(attribute_resolver),
        spatial_planning_port=spatial_port,
        stellar_buff_port=buff_runtime,
    )
    settlement_coordinator = ElementalSettlementCoordinator(
        interaction_coordinator,
        reaction_runtime=reaction_runtime,
        aura_runtime=aura_runtime,
        frame_coordinator=frame_coordinator,
        damage_handler=_NoopHandler(),
        buff_runtime=buff_runtime,
    )

    # 会话开始：创建领域、共享计数与 Space 投影，并提交两次附着记录（2 层）。
    state_planner = reaction_runtime.begin_state_batch(0, "stellar:settlement:setup")
    state_planner.create_polestar_field(_setup_intent())
    state_planner.create_stellar_conduct_counter(
        team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
        subject_ref=TARGET,
        frame=0,
    )
    for index in (1, 2):
        state_planner.append_stellar_conduct_attachment_record(
            team_ref=STELLAR_CONDUCT_TEAM_SCOPE,
            record=StellarConductAttachmentRecord(
                record_ref=f"record:{index}",
                attack_ref=f"root:attack:{index}",
                element=Element.CRYO,
                frame=1,
                target_refs=(TARGET,),
            ),
        )
    reaction_runtime.commit_prevalidated_state_plan(state_planner.seal())
    space_planner = spatial_port.begin_batch(operation_id="stellar:settlement:setup", frame=0)
    anchor = space.get_entity("target:star")
    assert anchor is not None
    from genshin_sim.core.systems.reaction import SpatialEntityCreationEffect

    space_planner.prepare_create(
        SpatialEntityCreationEffect(
            effect_ref=f"{SETUP_OCCURRENCE}:polestar-field-spatial-create",
            parent_occurrence_ref=SETUP_OCCURRENCE,
            space_entity_ref=f"reaction_object:polestar_field:{SETUP_OCCURRENCE}",
            owner_key=STELLAR_CONDUCT_TEAM_SCOPE,
            source_key=_setup_intent().instance_ref.value,
            tags=("reaction_state.polestar_field",),
            created_frame=0,
            expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
        ),
        anchor=anchor,
    )
    spatial_port.commit_prevalidated(space_planner.seal())

    # 会话创建时辉映 Buff 以 0 层数初始化。
    buff_receipt = buff_runtime.commit_prevalidated(
        buff_runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=0,
                occurrence_ref=SETUP_OCCURRENCE,
                character_refs=(AttributeSubjectRef.character(CHARACTER_ENTITY_ID),),
                settled_stacks=0,
                field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
    )
    del buff_receipt
    record = _radiance_record(buff_runtime, 0)
    values = {item.template.term_key: item.value for item in record.state.resolved_modifiers}
    assert values["stellar.conduct.radiance.cryo_bonus"] == pytest.approx(0.20)
    assert values["stellar.conduct.radiance.direct_base_multiplier"] == pytest.approx(1.0)

    settlement_coordinator.update_frame(context, STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES)

    counter = reaction_runtime.stellar_conduct_counter_state_for(STELLAR_CONDUCT_TEAM_SCOPE)
    assert counter is not None
    assert counter.settled_stacks == 2
    refreshed = _radiance_record(buff_runtime, STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES)
    assert refreshed.instance_ref == record.instance_ref
    values = {item.template.term_key: item.value for item in refreshed.state.resolved_modifiers}
    assert values["stellar.conduct.radiance.cryo_bonus"] == pytest.approx(0.30)
    assert values["stellar.conduct.radiance.electro_bonus"] == pytest.approx(0.30)
    assert values["stellar.conduct.radiance.direct_base_multiplier"] == pytest.approx(1.5)
    # 存在时间仍锚定领域到期 + 延续窗口，结算不延长 Buff。
    assert refreshed.expires_at_frame == (
        STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES + STELLAR_RADIANCE_PERSISTENCE_FRAMES
    )
