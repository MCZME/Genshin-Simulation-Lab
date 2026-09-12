# 单一关注点：星超导在元素交互协调器中的全链路闭环。
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
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    SUPERCONDUCT_BUFF_DEFINITION_KEY,
    superconduct_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    STELLAR_FIELD_RESIST_SOURCE_KEY,
    STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_RADIANCE_PERSISTENCE_FRAMES,
    stellar_radiance_buff_definition,
)
from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSubjectRef,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import EventType, ReactionOccurredPayload
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import AuraRuntime, AuraStrength
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.buff import (
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.reaction import (
    PolestarFieldState,
    ReactionRuntime,
    StellarConductCounterState,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
)
from genshin_sim.core.systems.reaction.states import STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES

TARGET_ENTITY_ID = "target:star"


class _FixedCapabilityPort:
    """按 capability 开关返回队伍准入证据。"""

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled

    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        if not self._enabled:
            return ReactionEligibilityView(team_ref, frame)
        return ReactionEligibilityView(
            team_ref,
            frame,
            (
                ReactionCapabilityEvidence(
                    STELLAR_CONDUCT_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


class _NoDamageHandler:
    def prepare_impact_request(self, *args, **kwargs):  # pragma: no cover - aura-only case
        raise AssertionError("星超导 Aura Impact 不应准备伤害")

    def commit_prepared_records(self, records):  # pragma: no cover - aura-only case
        raise AssertionError("星超导 Aura Impact 不应提交伤害")

    def publish_committed_facts(self, context, records):  # pragma: no cover - aura-only case
        raise AssertionError("星超导 Aura Impact 不应发布伤害")


class _PreparedStellarCoordinator:
    def __init__(
        self,
        *,
        capability_enabled: bool = True,
        extra_targets: tuple[tuple[str, str, Vector3], ...] = (),
    ) -> None:
        targets = (
            TargetRuntimeState("star", spatial_entity_id=TARGET_ENTITY_ID),
            *(
                TargetRuntimeState(target_id, spatial_entity_id=spatial_entity_id)
                for target_id, spatial_entity_id, _ in extra_targets
            ),
        )
        space = Space(
            (
                SpatialEntity(
                    TARGET_ENTITY_ID,
                    SpatialEntityKind.TARGET,
                    Vector3(0.0, 0.0, 0.0),
                ),
                *(
                    SpatialEntity(
                        spatial_entity_id,
                        SpatialEntityKind.TARGET,
                        position,
                    )
                    for _, spatial_entity_id, position in extra_targets
                ),
            )
        )
        self.space_runtime = SpaceRuntime(
            space=space,
            team_state=TeamRuntimeState(
                (
                    CharacterRuntimeState(
                        1,
                        "character:test",
                        90,
                        combat_entity_id="character:test",
                    ),
                )
            ),
            targets=TargetRuntimeCollection(targets),
        )
        self.context = SimulationContext(space_runtime=self.space_runtime)
        attribute_registry = create_public_attribute_registry()
        attribute_resolver = AttributeResolver(
            definitions=attribute_registry,
            base_attributes=BaseAttributeSet(()),
            modifier_index=ModifierProviderIndex((), registry=attribute_registry),
        )
        self.aura_runtime = AuraRuntime()
        self.icd_runtime = AuraIcdRuntime()
        self.reaction_runtime = create_default_reaction_bootstrap().create_runtime()
        self.spatial_planning_port = ReactionSpatialPlanningAdapter(space)
        self.buff_runtime = BuffRuntime(
            definition_registry=BuffDefinitionRegistry(
                (superconduct_buff_definition(), stellar_radiance_buff_definition())
            ),
            resolver=BuffResolver(),
            buff_store=BuffStore(),
            event_engine=self.context.events,
        )
        self.frame_coordinator = ElementalStateFrameCoordinator(
            self.aura_runtime,
            self.icd_runtime,
            self.reaction_runtime,
        )
        self.coordinator = ElementalInteractionCoordinator(
            aura_runtime=self.aura_runtime,
            icd_runtime=self.icd_runtime,
            reaction_runtime=self.reaction_runtime,
            damage_handler=_NoDamageHandler(),
            frame_coordinator=self.frame_coordinator,
            transformative_source_observer=CharacterTransformativeSourceObserver(
                attribute_resolver
            ),
            reaction_eligibility_port=_FixedCapabilityPort(enabled=capability_enabled),
            spatial_planning_port=self.spatial_planning_port,
            stellar_buff_port=self.buff_runtime,
        )
        self._application_sequence = 0

    def apply_element(
        self,
        element: Element,
        *,
        frame: int,
        target_refs: tuple[str, ...] = ("star",),
    ) -> ImpactRequest:
        self._application_sequence += 1
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_AURA,
            impact_key=f"test.stellar.{element.value}",
            owner_slot=1,
            request_id=f"root:stellar:{element.value}:{self._application_sequence}",
            target_refs=target_refs,
            elemental_application_spec=ElementalApplicationSpec(
                impact_ref=f"impact:{element.value}:{self._application_sequence}",
                element=element,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        )

    def occurred_reaction_keys(self) -> tuple[str, ...]:
        return tuple(
            event.payload.occurrence.reaction_key
            for event in self.context.events.frame_events
            if event.event_type is EventType.REACTION_OCCURRED
            and isinstance(event.payload, ReactionOccurredPayload)
        )


def _field_state(runtime: ReactionRuntime) -> PolestarFieldState:
    return next(state for state in runtime.state_records if isinstance(state, PolestarFieldState))


def test_stellar_conduct_interaction_creates_field_and_counter_atomically() -> None:
    prepared = _PreparedStellarCoordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    record = prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )

    assert len(record.reaction_occurrence_refs) == 1
    occurrence_ref = record.reaction_occurrence_refs[0]
    assert record.spatial_entity_refs[0] == f"reaction_object:polestar_field:{occurrence_ref}"
    assert prepared.occurred_reaction_keys() == ("reaction.stellar_conduct",)

    field = _field_state(prepared.reaction_runtime)
    assert field.team_ref == "player_team"
    assert field.expires_at_frame == 420
    counter = prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team")
    assert isinstance(counter, StellarConductCounterState)
    assert counter.window_index == 1
    assert counter.next_settlement_frame == 240
    assert len(counter.excluded_attack_refs) == 1

    entity = prepared.space_runtime.get_entity(record.spatial_entity_refs[0])
    assert entity is not None
    assert entity.kind is SpatialEntityKind.REACTION_OBJECT
    assert entity.position == Vector3(0.0, 0.0, 0.0)
    assert entity.lifecycle.created_frame == 0
    assert entity.lifecycle.expires_at_frame == 420

    event_types = {event.event_type for event in prepared.context.events.frame_events}
    assert EventType.REACTION_OCCURRED in event_types
    assert EventType.REACTION_STATE_CHANGED in event_types
    assert EventType.ELEMENTAL_INTERACTION_RESOLVED in event_types


def test_stellar_conduct_interaction_refresh_syncs_space_projection() -> None:
    prepared = _PreparedStellarCoordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    first = prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )

    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=30),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=30),
    )

    field = _field_state(prepared.reaction_runtime)
    assert field.created_frame == 0
    assert field.expires_at_frame == 450
    assert field.revision == 2
    counter = prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team")
    assert counter is not None
    assert counter.window_start_frame == 0
    assert counter.next_settlement_frame == 240

    entity = prepared.space_runtime.get_entity(first.spatial_entity_refs[0])
    assert entity is not None
    assert entity.lifecycle.created_frame == 0
    assert entity.lifecycle.expires_at_frame == 450
    assert entity.position == Vector3(0.0, 0.0, 0.0)


def test_stellar_conduct_interaction_falls_back_to_superconduct_without_capability() -> None:
    prepared = _PreparedStellarCoordinator(capability_enabled=False)
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    record = prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )

    assert record.reaction_state_binding_refs == ()
    assert record.spatial_entity_refs == ()
    assert prepared.occurred_reaction_keys() == ("reaction.superconduct",)
    assert all(
        state.slot_key.slot.value != "stellar_conduct_field"
        for state in prepared.reaction_runtime.state_records
    )
    assert prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team") is None


def _radiance_record(runtime: BuffRuntime, frame: int):
    records = runtime.reader.active(
        frame,
        definition_key=STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    )
    assert len(records) == 1
    return records[0]


def test_stellar_conduct_interaction_applies_and_refreshes_radiance_buff() -> None:
    prepared = _PreparedStellarCoordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )

    record = _radiance_record(prepared.buff_runtime, 0)
    assert record.state.target_ref.entity_id == "character:test"
    assert record.expires_at_frame == STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES + (
        STELLAR_RADIANCE_PERSISTENCE_FRAMES
    )
    values = {item.template.term_key: item.value for item in record.state.resolved_modifiers}
    assert values["stellar.conduct.radiance.cryo_bonus"] == pytest.approx(0.20)
    assert values["stellar.conduct.radiance.electro_bonus"] == pytest.approx(0.20)
    assert values["stellar.conduct.radiance.direct_base_multiplier"] == pytest.approx(1.0)

    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=30),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=30),
    )
    refreshed = _radiance_record(prepared.buff_runtime, 30)
    assert refreshed.instance_ref == record.instance_ref
    assert refreshed.last_applied_frame == 30
    assert refreshed.expires_at_frame == 30 + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES + (
        STELLAR_RADIANCE_PERSISTENCE_FRAMES
    )


def test_stellar_conduct_interaction_radiance_outlives_field_by_persistence_window() -> None:
    prepared = _PreparedStellarCoordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    record = _radiance_record(prepared.buff_runtime, 0)
    field_expires = STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES

    assert record.is_active_at(field_expires)
    assert record.is_active_at(field_expires + STELLAR_RADIANCE_PERSISTENCE_FRAMES - 1)
    assert not record.is_active_at(field_expires + STELLAR_RADIANCE_PERSISTENCE_FRAMES)


def test_stellar_conduct_interaction_applies_field_resistance_inside_only() -> None:
    prepared = _PreparedStellarCoordinator(
        extra_targets=(("far", "target:far", Vector3(30.0, 0.0, 0.0)),),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0, target_refs=("star", "far")),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )

    for frame, entity_id in ((0, TARGET_ENTITY_ID), (0, "target:far")):
        records = prepared.buff_runtime.reader.active(
            frame,
            target_ref=AttributeSubjectRef.target(entity_id),
            definition_key=SUPERCONDUCT_BUFF_DEFINITION_KEY,
        )
        if entity_id == TARGET_ENTITY_ID:
            assert len(records) == 1
            assert records[0].state.source_context.source_key == (STELLAR_FIELD_RESIST_SOURCE_KEY)
            assert records[0].expires_at_frame == STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES
        else:
            assert records == ()


def test_stellar_conduct_interaction_records_attachment_after_field_creation() -> None:
    prepared = _PreparedStellarCoordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0),
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0),
    )
    counter = prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team")
    assert counter is not None
    assert counter.pending_count == 0

    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=10),
    )
    counter = prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team")
    assert counter is not None
    assert counter.pending_count == 1
    assert counter.recorded_record_refs == ("root:stellar:cryo:3:stellar-attachment:cryo",)


def test_stellar_conduct_interaction_excludes_creating_attack_attachment() -> None:
    prepared = _PreparedStellarCoordinator(
        extra_targets=(("near", "target:near", Vector3(5.0, 0.0, 0.0)),),
    )
    # 先手雷附着两个目标（尚无会话，不产生记录）。
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.ELECTRO, frame=0, target_refs=("star", "near")),
    )
    # 同一攻击在 star 触发星超导、并在 near 产生冰附着：整条记录被排除。
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        prepared.apply_element(Element.CRYO, frame=0, target_refs=("star", "near")),
    )

    counter = prepared.reaction_runtime.stellar_conduct_counter_state_for("player_team")
    assert counter is not None
    assert counter.pending_count == 0
    assert counter.recorded_record_refs == ()
    assert counter.excluded_attack_refs == ("root:stellar:cryo:2",)
