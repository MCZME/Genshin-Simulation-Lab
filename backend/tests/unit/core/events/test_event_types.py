from typing import cast

from genshin_sim.core.attributes import STAT_HP_MAX, AttributeSubjectRef
from genshin_sim.core.attributes.panel import AttributePanelChange
from genshin_sim.core.events import (
    EVENT_CATEGORY_SPECS,
    ActionStartedPayload,
    AttributePanelChangedPayload,
    AuraAppliedPayload,
    AuraIcdResolvedPayload,
    AuraInteractionResolvedPayload,
    BuffAppliedPayload,
    BuffRemovedPayload,
    CharacterEnergyChangedPayload,
    CharacterHealthChangedPayload,
    CharacterMaxHpChangedPayload,
    ContentStateChangedPayload,
    DamageAppliedPayload,
    DamageResolvedPayload,
    DirectEnergyChangeResolvedPayload,
    ElementalInteractionResolvedPayload,
    EmptyPayload,
    EnergyPickupSettledPayload,
    EnergyPickupSpawnedPayload,
    EventCategory,
    EventSpec,
    EventType,
    GameEvent,
    HealingResolvedPayload,
    InfusionAppliedPayload,
    InfusionRemovedPayload,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
    MoonsignBonusAppliedPayload,
    MoonsignBonusExpiredPayload,
    MoonsignLevelSetPayload,
    ReactionOccurredPayload,
    ReactionStateChangedPayload,
    ResonanceActivatedPayload,
    ShieldAbsorptionResolvedPayload,
    ShieldCapacityChangedPayload,
    ShieldGrantedPayload,
    ShieldRemovedPayload,
    SimulationEndedPayload,
    SpaceEntityCreatedPayload,
    SpaceEntityRemovedPayload,
    get_event_category_spec,
    get_event_spec,
)
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.healing import (
    HealingComponentResult,
    HealingResult,
)
from genshin_sim.core.systems.health import (
    CharacterHealthChangeResult,
    CharacterMaxHpReconcileResult,
    HealthChangeKind,
)


def test_event_category_defines_current_design_categories():
    assert [category.name for category in EventCategory] == [
        "BOUNDARY",
        "INTENT",
        "INTERCEPT",
        "FACT",
        "STATE_CHANGE",
        "AUDIT",
    ]


def test_event_category_specs_cover_all_categories():
    assert set(EVENT_CATEGORY_SPECS) == set(EventCategory)


def test_event_category_specs_define_current_default_rules():
    assert get_event_category_spec(EventCategory.BOUNDARY).cancelable is False
    assert get_event_category_spec(EventCategory.BOUNDARY).record_by_default is False

    assert get_event_category_spec(EventCategory.INTENT).result_committed is False
    assert get_event_category_spec(EventCategory.INTENT).record_by_default is True

    intercept = get_event_category_spec(EventCategory.INTERCEPT)
    assert intercept.cancelable is True
    assert intercept.mutable_payload is True
    assert intercept.result_committed is False

    fact = get_event_category_spec(EventCategory.FACT)
    assert fact.cancelable is False
    assert fact.mutable_payload is False
    assert fact.record_by_default is True
    assert fact.result_committed is True

    state_change = get_event_category_spec(EventCategory.STATE_CHANGE)
    assert state_change.record_by_default is True
    assert state_change.result_committed is True

    audit = get_event_category_spec(EventCategory.AUDIT)
    assert audit.record_by_default is False
    assert audit.mechanic_driver is False


def test_event_spec_inherits_category_default_rules():
    spec = EventSpec(category=EventCategory.INTERCEPT, payload_type=object)

    assert spec.effective_cancelable is True
    assert spec.effective_mutable_payload is True
    assert spec.effective_record_by_default is False
    assert spec.effective_result_committed is False
    assert spec.effective_mechanic_driver is True


def test_event_spec_can_override_category_default_rules():
    spec = EventSpec(
        category=EventCategory.BOUNDARY,
        payload_type=object,
        record_by_default=True,
    )

    assert spec.effective_cancelable is False
    assert spec.effective_mutable_payload is False
    assert spec.effective_record_by_default is True
    assert spec.effective_result_committed is True
    assert spec.effective_mechanic_driver is False


def test_event_specs_define_current_default_rules():
    simulation_started = get_event_spec(EventType.SIMULATION_STARTED)
    assert simulation_started.category is EventCategory.BOUNDARY
    assert simulation_started.payload_type is EmptyPayload
    assert simulation_started.effective_record_by_default is True

    simulation_ended = get_event_spec(EventType.SIMULATION_ENDED)
    assert simulation_ended.category is EventCategory.BOUNDARY
    assert simulation_ended.payload_type is SimulationEndedPayload
    assert simulation_ended.effective_record_by_default is True

    assert get_event_spec(EventType.FRAME_STARTED).effective_record_by_default is False
    assert get_event_spec(EventType.FRAME_ENDED).effective_record_by_default is False

    input_key_received = get_event_spec(EventType.INPUT_KEY_RECEIVED)
    assert input_key_received.category is EventCategory.INTENT
    assert input_key_received.payload_type is InputKeyReceivedPayload
    assert input_key_received.effective_record_by_default is True
    assert input_key_received.effective_result_committed is False

    input_session_boundary = get_event_spec(EventType.INPUT_SESSION_BOUNDARY_REACHED)
    assert input_session_boundary.category is EventCategory.INTENT
    assert input_session_boundary.payload_type is InputSessionBoundaryPayload
    assert input_session_boundary.effective_record_by_default is True
    assert input_session_boundary.effective_result_committed is False

    damage_resolved = get_event_spec(EventType.DAMAGE_RESOLVED)
    assert damage_resolved.category is EventCategory.FACT
    assert damage_resolved.payload_type is DamageResolvedPayload
    assert damage_resolved.effective_record_by_default is True
    assert damage_resolved.effective_result_committed is True

    healing_resolved = get_event_spec(EventType.HEALING_RESOLVED)
    assert healing_resolved.category is EventCategory.FACT
    assert healing_resolved.payload_type is HealingResolvedPayload
    assert healing_resolved.effective_record_by_default is True
    assert healing_resolved.effective_result_committed is True

    health_changed = get_event_spec(EventType.CHARACTER_HEALTH_CHANGED)
    assert health_changed.category is EventCategory.STATE_CHANGE
    assert health_changed.payload_type is CharacterHealthChangedPayload
    assert health_changed.effective_record_by_default is True
    assert health_changed.effective_result_committed is True

    max_hp_changed = get_event_spec(EventType.CHARACTER_MAX_HP_CHANGED)
    assert max_hp_changed.category is EventCategory.STATE_CHANGE
    assert max_hp_changed.payload_type is CharacterMaxHpChangedPayload
    assert max_hp_changed.effective_record_by_default is True

    assert get_event_spec(EventType.SHIELD_GRANTED).payload_type is ShieldGrantedPayload
    assert (
        get_event_spec(EventType.SHIELD_CAPACITY_CHANGED).payload_type
        is ShieldCapacityChangedPayload
    )
    assert get_event_spec(EventType.SHIELD_REMOVED).payload_type is ShieldRemovedPayload
    assert (
        get_event_spec(EventType.SHIELD_ABSORPTION_RESOLVED).payload_type
        is ShieldAbsorptionResolvedPayload
    )
    damage_applied = get_event_spec(EventType.DAMAGE_APPLIED)
    assert damage_applied.category is EventCategory.FACT
    assert damage_applied.payload_type is DamageAppliedPayload
    assert get_event_spec(EventType.BUFF_APPLIED).payload_type is BuffAppliedPayload
    assert get_event_spec(EventType.BUFF_REMOVED).payload_type is BuffRemovedPayload
    assert get_event_spec(EventType.INFUSION_APPLIED).payload_type is InfusionAppliedPayload
    assert get_event_spec(EventType.INFUSION_REMOVED).payload_type is InfusionRemovedPayload
    assert (
        get_event_spec(EventType.ENERGY_PICKUP_SPAWNED).payload_type is EnergyPickupSpawnedPayload
    )
    assert (
        get_event_spec(EventType.ENERGY_PICKUP_SETTLED).payload_type is EnergyPickupSettledPayload
    )
    assert (
        get_event_spec(EventType.DIRECT_ENERGY_CHANGE_RESOLVED).payload_type
        is DirectEnergyChangeResolvedPayload
    )
    assert (
        get_event_spec(EventType.CHARACTER_ENERGY_CHANGED).payload_type
        is CharacterEnergyChangedPayload
    )
    assert (
        get_event_spec(EventType.CONTENT_STATE_CHANGED).payload_type is ContentStateChangedPayload
    )
    assert get_event_spec(EventType.SPACE_ENTITY_CREATED).payload_type is SpaceEntityCreatedPayload
    assert get_event_spec(EventType.SPACE_ENTITY_REMOVED).payload_type is SpaceEntityRemovedPayload
    assert (
        get_event_spec(EventType.ATTRIBUTE_PANEL_CHANGED).payload_type
        is AttributePanelChangedPayload
    )
    assert get_event_spec(EventType.AURA_ICD_RESOLVED).payload_type is AuraIcdResolvedPayload
    assert get_event_spec(EventType.AURA_APPLIED).payload_type is AuraAppliedPayload
    assert (
        get_event_spec(EventType.AURA_INTERACTION_RESOLVED).payload_type
        is AuraInteractionResolvedPayload
    )
    assert get_event_spec(EventType.REACTION_OCCURRED).payload_type is ReactionOccurredPayload
    reaction_state_changed = get_event_spec(EventType.REACTION_STATE_CHANGED)
    assert reaction_state_changed.category is EventCategory.STATE_CHANGE
    assert reaction_state_changed.payload_type is ReactionStateChangedPayload
    assert (
        get_event_spec(EventType.ELEMENTAL_INTERACTION_RESOLVED).payload_type
        is ElementalInteractionResolvedPayload
    )
    assert get_event_spec(EventType.RESONANCE_ACTIVATED).payload_type is (ResonanceActivatedPayload)
    assert get_event_spec(EventType.ACTION_STARTED).payload_type is ActionStartedPayload
    assert get_event_spec(EventType.MOONSIGN_LEVEL_SET).payload_type is MoonsignLevelSetPayload
    assert (
        get_event_spec(EventType.MOONSIGN_BONUS_APPLIED).payload_type is MoonsignBonusAppliedPayload
    )
    assert (
        get_event_spec(EventType.MOONSIGN_BONUS_EXPIRED).payload_type is MoonsignBonusExpiredPayload
    )


def test_event_payloads_convert_to_serializable_dicts():
    assert EmptyPayload().to_dict() == {}
    assert ResonanceActivatedPayload(
        active_keys=("resonance.pyro",),
        team_size=4,
        established_frame=0,
    ).to_dict() == {
        "active_keys": ("resonance.pyro",),
        "team_size": 4,
        "established_frame": 0,
    }
    assert ActionStartedPayload(
        instance_id=1,
        frame=5,
        action_key="character.test.skill",
        owner_slot=1,
        ability_key="elemental_skill",
    ).to_dict() == {
        "instance_id": 1,
        "frame": 5,
        "action_key": "character.test.skill",
        "owner_slot": 1,
        "ability_key": "elemental_skill",
    }
    assert MoonsignLevelSetPayload(
        level="ascendant",
        moonsign_character_refs=("character:slot_1",),
    ).to_dict() == {
        "level": "ascendant",
        "moonsign_character_refs": ("character:slot_1",),
        "established_frame": 0,
    }
    assert SimulationEndedPayload(
        stop_reason="COMPLETED",
        end_frame=12,
        frames_run=12,
    ).to_dict() == {
        "stop_reason": "COMPLETED",
        "end_frame": 12,
        "frames_run": 12,
    }
    assert InputKeyReceivedPayload(
        key="keyboard.e",
        phase="release",
        order=1,
        session_id=7,
    ).to_dict() == {
        "key": "keyboard.e",
        "phase": "release",
        "order": 1,
        "session_id": 7,
    }
    assert InputSessionBoundaryPayload(
        session_id=7,
        key="keyboard.e",
        phase="release",
        order=1,
        press_frame=3,
        held_frames=2,
        physical_state="released",
        control_state="listening",
        owner_kind="character",
        owner_slot=1,
        interpreter_id="character:1",
        binding_scope="active_character",
        will_interpret=True,
    ).to_dict() == {
        "session_id": 7,
        "key": "keyboard.e",
        "phase": "release",
        "order": 1,
        "press_frame": 3,
        "held_frames": 2,
        "physical_state": "released",
        "control_state": "listening",
        "owner_kind": "character",
        "owner_slot": 1,
        "interpreter_id": "character:1",
        "binding_scope": "active_character",
        "will_interpret": True,
        "skip_reason": None,
    }
    character_ref = AttributeSubjectRef.character("character:slot_1")
    healing_result = HealingResult(
        healing_id="healing:1",
        frame=3,
        source_ref=character_ref,
        target_ref=character_ref,
        component_results=(
            HealingComponentResult(
                component_key="hp",
                attribute_key=STAT_HP_MAX,
                scaling_value=1000,
                coefficient=0.1,
                value=100,
            ),
        ),
        flat_healing=0,
        base_healing=100,
        outgoing_healing_bonus=0.2,
        incoming_healing_bonus=0,
        healing_bonus_multiplier=1.2,
        final_healing=120,
    )
    healing_payload = HealingResolvedPayload(healing_result).to_dict()
    healing_payload_result = cast(dict[str, object], healing_payload["result"])
    assert healing_payload_result["final_healing"] == 120.0
    health_result = CharacterHealthChangeResult(
        change_id="health:1",
        frame=3,
        change_kind=HealthChangeKind.DAMAGE,
        target_ref=character_ref,
        source_ref=None,
        requested_amount=300,
        effective_amount=300,
        unapplied_amount=0,
        hp_before=1000,
        hp_after=700,
        max_hp=1000,
    )
    health_payload = CharacterHealthChangedPayload(health_result).to_dict()
    assert cast(dict[str, object], health_payload["result"])["hp_after"] == 700
    max_hp_result = CharacterMaxHpReconcileResult(
        frame=3,
        target_ref=character_ref,
        old_max_hp=1000,
        new_max_hp=1200,
        hp_before=500,
        hp_after=600,
    )
    max_hp_payload = CharacterMaxHpChangedPayload(max_hp_result).to_dict()
    assert cast(dict[str, object], max_hp_payload["result"])["new_max_hp"] == 1200
    space_entity = SpatialEntity(
        entity_id="reaction_object:test:1",
        kind=SpatialEntityKind.REACTION_OBJECT,
        position=Vector3(1, 0, 2),
    )
    created_payload = SpaceEntityCreatedPayload(frame=3, entity=space_entity).to_dict()
    created_entity = cast(dict[str, object], created_payload["entity"])
    assert created_payload["frame"] == 3
    assert created_entity["entity_id"] == "reaction_object:test:1"
    assert created_entity["kind"] == "reaction_object"
    removed_payload = SpaceEntityRemovedPayload(frame=4, entity=space_entity).to_dict()
    removed_entity = cast(dict[str, object], removed_payload["entity"])
    assert removed_payload["frame"] == 4
    assert removed_entity["entity_id"] == "reaction_object:test:1"
    panel_payload = AttributePanelChangedPayload(
        frame=120,
        subject_ref={"kind": "character", "entity_id": "character:slot_1"},
        changes=(
            AttributePanelChange(
                attribute_key="stat.atk.total",
                before_value=1500.0,
                after_value=1800.0,
                after_terms=(),
            ),
        ),
    ).to_dict()
    panel_changes = cast(tuple[dict[str, object], ...], panel_payload["changes"])
    assert panel_payload["frame"] == 120
    assert panel_changes[0]["attribute_key"] == "stat.atk.total"
    assert panel_changes[0]["after_value"] == 1800.0


def test_game_event_rejects_wrong_payload_type():
    try:
        GameEvent(
            EventType.INPUT_KEY_RECEIVED,
            frame=1,
            payload=EmptyPayload(),
        )
    except TypeError as exc:
        assert "INPUT_KEY_RECEIVED 事件载荷类型错误" in str(exc)
    else:
        raise AssertionError("wrong payload type should fail")


def test_game_event_rejects_cancel_for_non_cancelable_event():
    event = GameEvent(
        EventType.INPUT_KEY_RECEIVED,
        frame=1,
        payload=InputKeyReceivedPayload(
            key="keyboard.e",
            phase="press",
            order=0,
            session_id=1,
        ),
    )

    try:
        event.cancel()
    except RuntimeError as exc:
        assert str(exc) == "INPUT_KEY_RECEIVED 事件不允许取消"
    else:
        raise AssertionError("non-cancelable event should fail")
