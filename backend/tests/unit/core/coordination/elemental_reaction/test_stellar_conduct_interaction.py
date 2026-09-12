# 单一关注点：星超导在元素交互协调器中的全链路闭环。
from __future__ import annotations

from genshin_sim.core.attributes import (
    AttributeResolver,
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
from genshin_sim.core.systems.reaction import (
    PolestarFieldState,
    ReactionRuntime,
    StellarConductCounterState,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
)

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
    def __init__(self, *, capability_enabled: bool = True) -> None:
        target = TargetRuntimeState("star", spatial_entity_id=TARGET_ENTITY_ID)
        space = Space(
            (
                SpatialEntity(
                    TARGET_ENTITY_ID,
                    SpatialEntityKind.TARGET,
                    Vector3(0.0, 0.0, 0.0),
                ),
            )
        )
        self.space_runtime = SpaceRuntime(
            space=space,
            team_state=TeamRuntimeState((CharacterRuntimeState(1, "character:test", 90),)),
            targets=TargetRuntimeCollection((target,)),
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
        )
        self._application_sequence = 0

    def apply_element(self, element: Element, *, frame: int) -> ImpactRequest:
        self._application_sequence += 1
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_AURA,
            impact_key=f"test.stellar.{element.value}",
            owner_slot=1,
            request_id=f"root:stellar:{element.value}:{self._application_sequence}",
            target_refs=("star",),
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
