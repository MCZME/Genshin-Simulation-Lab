from genshin_sim.core.events import (
    EVENT_CATEGORY_SPECS,
    EVENT_SPECS,
    EmptyPayload,
    EventCategory,
    EventSpec,
    EventType,
    GameEvent,
    InputKeyConsumedPayload,
    SimulationEndedPayload,
    get_event_category_spec,
    get_event_spec,
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
        "INPUT_KEY_CONSUMED",
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

    input_key_consumed = get_event_spec(EventType.INPUT_KEY_CONSUMED)
    assert input_key_consumed.category is EventCategory.INTENT
    assert input_key_consumed.payload_type is InputKeyConsumedPayload
    assert input_key_consumed.effective_record_by_default is True
    assert input_key_consumed.effective_result_committed is False


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
    assert InputKeyConsumedPayload(
        key="keyboard.e",
        phase="release",
        held_frames=2,
    ).to_dict() == {
        "key": "keyboard.e",
        "phase": "release",
        "held_frames": 2,
    }


def test_game_event_rejects_wrong_payload_type():
    try:
        GameEvent(
            EventType.INPUT_KEY_CONSUMED,
            frame=1,
            payload=EmptyPayload(),
        )
    except TypeError as exc:
        assert "INPUT_KEY_CONSUMED 事件载荷类型错误" in str(exc)
    else:
        raise AssertionError("wrong payload type should fail")


def test_game_event_rejects_cancel_for_non_cancelable_event():
    event = GameEvent(
        EventType.INPUT_KEY_CONSUMED,
        frame=1,
        payload=InputKeyConsumedPayload(key="keyboard.e", phase="press"),
    )

    try:
        event.cancel()
    except RuntimeError as exc:
        assert str(exc) == "INPUT_KEY_CONSUMED 事件不允许取消"
    else:
        raise AssertionError("non-cancelable event should fail")
