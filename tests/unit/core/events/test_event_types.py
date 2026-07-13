from typing import cast

from genshin_sim.core.attributes import STAT_HP_MAX, AttributeSubjectRef
from genshin_sim.core.events import (
    EVENT_CATEGORY_SPECS,
    EVENT_SPECS,
    CharacterHealthChangedPayload,
    CharacterMaxHpChangedPayload,
    DamageResolvedPayload,
    EmptyPayload,
    EventCategory,
    EventSpec,
    EventType,
    GameEvent,
    HealingResolvedPayload,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
    SimulationEndedPayload,
    get_event_category_spec,
    get_event_spec,
)
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


def test_event_type_defines_current_events():
    assert [event_type.name for event_type in EventType] == [
        "SIMULATION_STARTED",
        "SIMULATION_ENDED",
        "FRAME_STARTED",
        "FRAME_ENDED",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "DAMAGE_RESOLVED",
        "HEALING_RESOLVED",
        "CHARACTER_HEALTH_CHANGED",
        "CHARACTER_MAX_HP_CHANGED",
    ]


def test_event_category_specs_cover_all_categories():
    assert set(EVENT_CATEGORY_SPECS) == set(EventCategory)


def test_event_specs_cover_all_event_types():
    assert set(EVENT_SPECS) == set(EventType)


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
    assert max_hp_changed.category is EventCategory.AUDIT
    assert max_hp_changed.payload_type is CharacterMaxHpChangedPayload
    assert max_hp_changed.effective_record_by_default is False


def test_event_payloads_convert_to_serializable_dicts():
    assert EmptyPayload().to_dict() == {}
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
