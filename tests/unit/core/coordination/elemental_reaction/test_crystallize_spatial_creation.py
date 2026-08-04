from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.core.attributes import (
    AttributeResolver,
    BaseAttributeSet,
    ModifierProviderIndex,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction import (
    CrystallizeShardAlreadyPickedError,
    CrystallizeShardExpiredError,
    CrystallizeShardOperationConflictError,
    CrystallizeShardPickupCoordinator,
    CrystallizeShardPickupRequest,
    ElementalInteractionCoordinator,
    ElementalStateFrameCoordinator,
    ReactionBoundEntityExpiryCoordinator,
    ReactionSpatialPlanningAdapter,
    ReactionStateBindingConflictError,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import ElementalInteractionResolvedPayload, EventType
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.errors import SpaceEntityPlanConflictError
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraRuntime, AuraStrength
from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
from genshin_sim.core.systems.reaction import (
    CrystallizeShardLifecycleState,
    CrystallizeSourceObservation,
    ReactionRegistry,
    ReactionRuntime,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize import (
    CrystallizeRule,
    crystallize_definition,
    crystallize_establishment_gate_definition,
)
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef
from genshin_sim.core.systems.shield import (
    ShieldPlanConflictError,
    ShieldResolver,
    ShieldRuntime,
    ShieldStore,
)

TARGET_ENTITY_ID = "target:one"


def test_crystallize_creates_bound_state_and_reaction_object_in_one_interaction_batch():
    prepared = _prepared_coordinator()

    record = prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert record.reaction_occurrence_refs == ("root:geo:target:one:0:interaction:occurrence:0",)
    assert record.reaction_state_binding_refs == (
        "reaction-state:crystallize-shard:root:geo:target:one:0:interaction:occurrence:0",
    )
    assert record.spatial_entity_refs == (
        "reaction_object:crystallize_shard:root:geo:target:one:0:interaction:occurrence:0",
    )

    state = prepared.reaction_runtime.crystallize_shard_state_for(
        ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    )
    entity = prepared.space_runtime.get_entity(record.spatial_entity_refs[0])

    assert state is not None
    assert entity is not None
    assert state.space_entity_ref == entity.entity_id
    assert entity.kind is SpatialEntityKind.REACTION_OBJECT
    assert entity.position == Vector3(3.0, 0.0, 4.0)
    assert entity.facing == Vector3(1.0, 0.0, 0.0)
    assert entity.source_key == state.instance_ref.value
    assert entity.lifecycle.created_frame == state.created_frame == 0
    assert entity.lifecycle.expires_at_frame == state.expires_at_frame == 900
    payload = next(
        event.payload
        for event in prepared.context.events.frame_events
        if event.event_type is EventType.ELEMENTAL_INTERACTION_RESOLVED
    )
    assert isinstance(payload, ElementalInteractionResolvedPayload)
    assert payload.to_dict()["spatial_entity_refs"] == list(record.spatial_entity_refs)
    assert payload.to_dict()["reaction_state_binding_refs"] == list(
        record.reaction_state_binding_refs
    )


def test_crystallize_binding_failure_leaves_aura_state_and_space_unchanged():
    prepared = _prepared_coordinator(spatial_port=_MismatchedSpatialPort)

    with pytest.raises(ReactionStateBindingConflictError, match="binding 不一致"):
        prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert prepared.reaction_runtime.state_records == ()
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    pyro = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)
    assert pyro is not None
    assert pyro.current_amount == AuraAmount("4/5")


def test_crystallize_missing_anchor_leaves_aura_state_and_space_unchanged():
    prepared = _prepared_coordinator()
    prepared.space_runtime.space.remove_entity(TARGET_ENTITY_ID)

    with pytest.raises(RuntimeError, match="缺少目标锚点"):
        prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert prepared.reaction_runtime.state_records == ()
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    pyro = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)
    assert pyro is not None
    assert pyro.current_amount == AuraAmount("4/5")


def test_crystallize_stale_space_plan_leaves_icd_aura_and_state_unchanged():
    prepared = _prepared_coordinator(spatial_port=_StaleSpatialPort)

    with pytest.raises(SpaceEntityPlanConflictError, match="已经过期"):
        prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert prepared.icd_runtime.version == 0
    assert prepared.reaction_runtime.state_records == ()
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    pyro = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)
    assert pyro is not None
    assert pyro.current_amount == AuraAmount("4/5")


def test_crystallize_updates_space_frame_before_nonzero_frame_creation():
    prepared = _prepared_coordinator()

    record = prepared.coordinator.handle_aura_impact(
        prepared.context,
        _geo_request(frame=1),
    )

    entity = prepared.space_runtime.get_entity(record.spatial_entity_refs[0])
    assert entity is not None
    assert prepared.space_runtime.space.current_frame == 1
    assert entity.lifecycle.created_frame == 1
    assert entity.lifecycle.expires_at_frame == 901


def test_crystallize_rejected_old_frame_keeps_all_runtime_frames_aligned():
    prepared = _prepared_coordinator()
    prepared.coordinator.handle_aura_impact(prepared.context, _geo_request(frame=1))

    with pytest.raises(ValueError, match="ReactionState 帧不能回退"):
        prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert prepared.reaction_runtime.normalized_through_frame == 1
    assert prepared.aura_runtime.normalized_through_frame == 1
    assert prepared.icd_runtime.normalized_through_frame == 1
    assert prepared.space_runtime.space.current_frame == 1


def test_crystallize_establishment_gate_blocks_without_consuming_aura_or_creating_state():
    prepared = _prepared_coordinator()
    first = prepared.coordinator.handle_aura_impact(
        prepared.context,
        _geo_request(request_id="root:geo:first"),
    )
    before_blocked = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)

    blocked = prepared.coordinator.handle_aura_impact(
        prepared.context,
        _geo_request(request_id="root:geo:blocked"),
    )

    after_blocked = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)
    assert before_blocked is not None and after_blocked is not None
    assert after_blocked.current_amount == before_blocked.current_amount
    assert len(prepared.reaction_runtime.state_records) == 1
    assert blocked.reaction_occurrence_refs == ()
    assert blocked.spatial_entity_refs == ()
    assert blocked.reaction_state_binding_refs == ()
    assert blocked.establishment_gate_resolution_refs == (
        "root:geo:blocked:target:one:0:interaction:occurrence:0:establishment-gate:resolution",
    )
    assert (
        prepared.reaction_runtime.establishment_gate_records[0].last_occurrence_ref
        == (first.reaction_occurrence_refs[0])
    )


def test_crystallize_establishment_gate_reopens_at_sixtieth_frame():
    prepared = _prepared_coordinator()
    prepared.coordinator.handle_aura_impact(
        prepared.context, _geo_request(request_id="root:geo:first")
    )
    prepared.coordinator.handle_aura_impact(
        prepared.context,
        _geo_request(request_id="root:geo:blocked"),
    )

    reopened = prepared.coordinator.handle_aura_impact(
        prepared.context,
        _geo_request(frame=60, request_id="root:geo:reopened"),
    )

    assert len(reopened.reaction_occurrence_refs) == 1
    assert len(reopened.spatial_entity_refs) == 1
    assert len(prepared.reaction_runtime.state_records) == 2
    assert (
        prepared.reaction_runtime.establishment_gate_records[0].last_occurrence_ref
        == (reopened.reaction_occurrence_refs[0])
    )


def test_crystallize_declaration_with_wrong_subject_leaves_all_domains_unchanged():
    prepared = _prepared_coordinator(
        reaction_definition=replace(
            crystallize_definition(),
            rule=_WrongSubjectCrystallizeRule(),
        )
    )

    with pytest.raises(ReactionStateBindingConflictError, match="与 occurrence 不一致"):
        prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())

    assert prepared.icd_runtime.version == 0
    assert prepared.reaction_runtime.state_records == ()
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    pyro = prepared.aura_runtime.view(_target_subject()).component_for(AuraKind.PYRO)
    assert pyro is not None
    assert pyro.current_amount == AuraAmount("4/5")


def test_crystallize_pickup_is_idempotent_and_grants_captured_shield():
    prepared = _prepared_coordinator()
    record = prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    prepared.frame_coordinator.normalize(prepared.context, 1)
    pickup = CrystallizeShardPickupCoordinator(
        reaction_state_port=prepared.reaction_runtime,
        spatial_planning_port=prepared.spatial_planning_port,
        shield_grant_port=prepared.shield_runtime,
    )
    request = CrystallizeShardPickupRequest("pickup:one", 1, shard_ref)
    reentrant_errors: list[str] = []

    def reenter_space(_: object) -> None:
        with pytest.raises(SpaceEntityPlanConflictError) as exc_info:
            prepared.space_runtime.space.add_entity(
                SpatialEntity(
                    "event:space-write",
                    SpatialEntityKind.REACTION_OBJECT,
                    Vector3(),
                )
            )
        reentrant_errors.append(str(exc_info.value))

    prepared.context.events.subscribe(EventType.REACTION_STATE_CHANGED, reenter_space)

    result = pickup.pickup(prepared.context, request)

    assert pickup.pickup(prepared.context, request) is result
    assert result.shard_ref == shard_ref
    assert result.element is Element.PYRO
    assert result.created_frame == 0
    assert result.expires_at_frame == 900
    assert result.picked_frame == 1
    assert result.shield_grant.maximum_after == result.captured_shield_basis.native_absorption
    assert result.shield_grant.expires_at_after == 901
    assert len(prepared.shield_runtime.shield_store.active_records) == 1
    shield = prepared.shield_runtime.shield_store.active_records[0]
    assert shield.state.element.value == "pyro"
    assert shield.state.protection_ref.to_key() == "active_team:team:player"
    state = prepared.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert state is not None
    assert state.lifecycle_state is CrystallizeShardLifecycleState.PICKED
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    assert reentrant_errors == ["Space 写保护期间不允许修改空间实体"]

    with pytest.raises(CrystallizeShardOperationConflictError):
        pickup.pickup(
            prepared.context,
            CrystallizeShardPickupRequest("pickup:one", 2, shard_ref),
        )
    with pytest.raises(CrystallizeShardAlreadyPickedError):
        pickup.pickup(
            prepared.context,
            CrystallizeShardPickupRequest("pickup:two", 1, shard_ref),
        )


def test_crystallize_expiry_at_required_frame_removes_bound_entity_and_rejects_pickup():
    prepared = _prepared_coordinator()
    record = prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])

    frame_record = prepared.frame_coordinator.normalize(prepared.context, 900)

    assert len(frame_record.lifecycle_works) == 1
    assert frame_record.lifecycle_works[0].state_instance_ref == shard_ref
    state = prepared.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert state is not None
    assert state.lifecycle_state is CrystallizeShardLifecycleState.EXPIRED
    assert state.terminal_frame == 900
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is None
    assert prepared.reaction_runtime.next_required_frame() is None

    pickup = CrystallizeShardPickupCoordinator(
        reaction_state_port=prepared.reaction_runtime,
        spatial_planning_port=prepared.spatial_planning_port,
        shield_grant_port=prepared.shield_runtime,
    )
    with pytest.raises(CrystallizeShardExpiredError):
        pickup.pickup(
            prepared.context,
            CrystallizeShardPickupRequest("pickup:expired", 900, shard_ref),
        )


def test_crystallize_pickup_shield_validation_failure_keeps_bound_shard():
    prepared = _prepared_coordinator()
    record = prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    prepared.frame_coordinator.normalize(prepared.context, 1)
    pickup = CrystallizeShardPickupCoordinator(
        reaction_state_port=prepared.reaction_runtime,
        spatial_planning_port=prepared.spatial_planning_port,
        shield_grant_port=_RejectingShieldGrantPort(prepared.shield_runtime),
    )

    with pytest.raises(ShieldPlanConflictError, match="测试护盾计划冲突"):
        pickup.pickup(
            prepared.context,
            CrystallizeShardPickupRequest("pickup:shield-stale", 1, shard_ref),
        )

    state = prepared.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert state is not None
    assert state.lifecycle_state is CrystallizeShardLifecycleState.ACTIVE
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is not None
    assert prepared.shield_runtime.shield_store.records == ()

    retry = CrystallizeShardPickupCoordinator(
        reaction_state_port=prepared.reaction_runtime,
        spatial_planning_port=prepared.spatial_planning_port,
        shield_grant_port=prepared.shield_runtime,
    ).pickup(
        prepared.context,
        CrystallizeShardPickupRequest("pickup:shield-retry", 1, shard_ref),
    )
    assert retry.shield_grant.instance_ref.sequence == 1


def test_crystallize_expiry_stale_space_plan_keeps_shard_active():
    prepared = _prepared_coordinator()
    record = prepared.coordinator.handle_aura_impact(prepared.context, _geo_request())
    shard_ref = ReactionStateInstanceRef(record.reaction_state_binding_refs[0])
    prepared.frame_coordinator.reaction_bound_entity_expiry_coordinator = (
        ReactionBoundEntityExpiryCoordinator(
            reaction_state_port=prepared.reaction_runtime,
            spatial_planning_port=_StaleSpatialPort(prepared.space_runtime.space),
        )
    )

    with pytest.raises(SpaceEntityPlanConflictError, match="已经过期"):
        prepared.frame_coordinator.normalize(prepared.context, 900)

    state = prepared.reaction_runtime.crystallize_shard_state_for(shard_ref)
    assert state is not None
    assert state.lifecycle_state is CrystallizeShardLifecycleState.ACTIVE
    assert prepared.space_runtime.get_entity(_shard_entity_id()) is not None


class _FixedCrystallizeSourceObserver:
    def observe(
        self,
        *,
        frame: int,
        source_ref: ElementalSourceRef,
        owner_slot: int,
        source_level: int,
    ) -> CrystallizeSourceObservation:
        assert owner_slot == 1
        return CrystallizeSourceObservation(source_ref, source_level, 0.0)


class _WrongSubjectCrystallizeRule:
    def evaluate(self, request, definition):
        resolution = CrystallizeRule().evaluate(request, definition)
        assert resolution is not None and resolution.occurrence is not None
        occurrence = resolution.occurrence
        intent = occurrence.crystallize_shard_state_creation
        assert intent is not None
        wrong_occurrence = replace(
            occurrence,
            crystallize_shard_state_creation=replace(
                intent,
                subject_ref=ElementalSubjectRef.target("target:other"),
            ),
        )
        return replace(
            resolution,
            occurrence=wrong_occurrence,
            decision_sequence=replace(
                resolution.sequence,
                steps=(
                    replace(
                        resolution.sequence.steps[0],
                        occurrences=(wrong_occurrence,),
                    ),
                ),
            ),
        )


class _MismatchedSpatialPort:
    def __init__(self, space: Space) -> None:
        self._adapter = ReactionSpatialPlanningAdapter(space)

    def begin_batch(self, *, operation_id: str, frame: int):
        return _MismatchedSpatialPlanner(
            self._adapter.begin_batch(
                operation_id=operation_id,
                frame=frame,
            )
        )

    def validate(self, plan) -> None:
        self._adapter.validate(plan)

    def commit_prevalidated(self, plan):
        return self._adapter.commit_prevalidated(plan)

    def event_publication_guard(self):
        return self._adapter.event_publication_guard()


class _MismatchedSpatialPlanner:
    def __init__(self, planner) -> None:
        self._planner = planner

    def prepare_create(self, effect, *, anchor):
        return self._planner.prepare_create(effect, anchor=anchor)

    def seal(self):
        plan = self._planner.seal()
        return replace(
            plan,
            creations=(replace(plan.creations[0], source_key="state:wrong"),),
        )


class _StaleSpatialPort:
    def __init__(self, space: Space) -> None:
        self._space = space
        self._adapter = ReactionSpatialPlanningAdapter(space)

    def begin_batch(self, *, operation_id: str, frame: int):
        return self._adapter.begin_batch(operation_id=operation_id, frame=frame)

    def validate(self, plan) -> None:
        self._space.add_entity(
            SpatialEntity("external:space-write", SpatialEntityKind.CREATED_OBJECT, Vector3())
        )
        self._adapter.validate(plan)

    def commit_prevalidated(self, plan):
        return self._adapter.commit_prevalidated(plan)

    def event_publication_guard(self):
        return self._adapter.event_publication_guard()


class _NoDamageHandler:
    def prepare_impact_request(self, *args, **kwargs):  # pragma: no cover - aura-only case
        raise AssertionError("结晶 Aura Impact 不应准备伤害")

    def commit_prepared_records(self, records):  # pragma: no cover - aura-only case
        raise AssertionError("结晶 Aura Impact 不应提交伤害")

    def publish_committed_facts(self, context, records):  # pragma: no cover - aura-only case
        raise AssertionError("结晶 Aura Impact 不应发布伤害")


class _RejectingShieldGrantPort:
    def __init__(self, runtime: ShieldRuntime) -> None:
        self._runtime = runtime

    def prepare_grant(self, request):
        return self._runtime.prepare_grant(request)

    def validate(self, plan) -> None:
        raise ShieldPlanConflictError("测试护盾计划冲突")

    def commit_prevalidated(self, plan):  # pragma: no cover - validate 必须先失败
        return self._runtime.commit_prevalidated(plan)

    def events_for(self, receipt):  # pragma: no cover - validate 必须先失败
        return self._runtime.events_for(receipt)

    def publish_committed_facts(self, receipt):  # pragma: no cover - validate 必须先失败
        return self._runtime.publish_committed_facts(receipt)

    def event_publication_guard(self):  # pragma: no cover - validate 必须先失败
        return self._runtime.event_publication_guard()


class _PreparedCoordinator:
    def __init__(self, *, spatial_port_type=None, reaction_definition=None) -> None:
        target = TargetRuntimeState("one", spatial_entity_id=TARGET_ENTITY_ID)
        space = Space(
            (
                SpatialEntity(
                    TARGET_ENTITY_ID,
                    SpatialEntityKind.TARGET,
                    Vector3(3.0, 0.0, 4.0),
                    facing=Vector3(1.0, 0.0, 0.0),
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
        self.shield_runtime = ShieldRuntime(
            resolver=ShieldResolver(attribute_resolver),
            shield_store=ShieldStore(),
            attribute_resolver=attribute_resolver,
            event_engine=self.context.events,
            team_state=self.space_runtime.team_state,
        )
        self.aura_runtime = AuraRuntime()
        self.icd_runtime = AuraIcdRuntime()
        self.reaction_runtime = ReactionRuntime(
            ReactionRegistry((reaction_definition or crystallize_definition(),)),
            establishment_gate_definitions=(crystallize_establishment_gate_definition(),),
        )
        spatial_port = None if spatial_port_type is None else spatial_port_type(space)
        self.spatial_planning_port = spatial_port or ReactionSpatialPlanningAdapter(space)
        self.frame_coordinator = ElementalStateFrameCoordinator(
            self.aura_runtime,
            self.icd_runtime,
            self.reaction_runtime,
            ReactionBoundEntityExpiryCoordinator(
                reaction_state_port=self.reaction_runtime,
                spatial_planning_port=self.spatial_planning_port,
            ),
        )
        self.coordinator = ElementalInteractionCoordinator(
            aura_runtime=self.aura_runtime,
            icd_runtime=self.icd_runtime,
            reaction_runtime=self.reaction_runtime,
            damage_handler=_NoDamageHandler(),
            frame_coordinator=self.frame_coordinator,
            crystallize_source_observer=_FixedCrystallizeSourceObserver(),
            spatial_planning_port=self.spatial_planning_port,
        )
        self.aura_runtime.apply(
            AuraApplicationRequest(
                request_id="aura:pyro",
                application_id="application:pyro",
                impact_ref="impact:pyro",
                frame=0,
                order=0,
                source_ref=ElementalSourceRef("source:pyro"),
                target_ref=_target_subject(),
                element=Element.PYRO,
                base_strength=AuraStrength.WEAK,
            )
        )


def _prepared_coordinator(*, spatial_port=None, reaction_definition=None) -> _PreparedCoordinator:
    return _PreparedCoordinator(
        spatial_port_type=spatial_port,
        reaction_definition=reaction_definition,
    )


def _geo_request(*, frame: int = 0, request_id: str = "root:geo") -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key="test.crystallize.geo",
        owner_slot=1,
        request_id=request_id,
        target_refs=("one",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref="impact:geo",
            element=Element.GEO,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )


def _target_subject():
    from genshin_sim.core.elements import ElementalSubjectRef

    return ElementalSubjectRef.target(TARGET_ENTITY_ID)


def _shard_entity_id() -> str:
    return "reaction_object:crystallize_shard:root:geo:target:one:0:interaction:occurrence:0"
