from __future__ import annotations

from dataclasses import dataclass

import pytest

from genshin_sim.core.actions import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionManager,
    ActionRejectReason,
    ActionTimelineSpec,
    InputActionSessionState,
    SpatialQuery,
    TeamActionController,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    InputState,
    KeyEvent,
    KeyEventDispatch,
    KeyInputFrame,
    KeyPhase,
    SimulationContext,
    SimulationStopReason,
    Simulator,
    TeamRuntimeState,
    TraceInputSystem,
)
from genshin_sim.core.space import (
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime, TeamSwitchActionConsumer


@dataclass(frozen=True, slots=True)
class _ActiveSlotProvider:
    team_state: TeamRuntimeState

    @property
    def active_slot(self) -> int:
        return self.team_state.active_slot


def _team_state(size: int = 4, *, active_slot: int = 1) -> TeamRuntimeState:
    return TeamRuntimeState(
        (
            CharacterRuntimeState(
                slot=slot,
                character_key=f"character:{slot}",
                level=90,
            )
            for slot in range(1, size + 1)
        ),
        active_slot=active_slot,
    )


def _active_slot_provider(team_state: TeamRuntimeState) -> _ActiveSlotProvider:
    return _ActiveSlotProvider(team_state)


def _attach_space_runtime(
    ctx: SimulationContext,
    manager: ActionManager,
    *,
    space: Space | None = None,
    team_state: TeamRuntimeState | None = None,
    targets: TargetRuntimeCollection | None = None,
    consumers: dict[tuple[str, str], TeamSwitchActionConsumer] | None = None,
) -> SpaceRuntime:
    runtime = SpaceRuntime(
        space=space,
        team_state=team_state or _team_state(),
        targets=targets,
        action_manager=manager,
        consumers=consumers,
    )
    ctx.space_runtime = runtime
    return runtime


def _timeline(
    *,
    frame: int = 1,
    action_key: str = "keyboard.e",
    owner_slot: int = 1,
    duration_frames: int = 1,
    actor_entity_id: str | None = None,
    spatial_query: SpatialQuery | None = None,
    params: dict[str, object] | None = None,
) -> ActionTimelineSpec:
    return ActionTimelineSpec(
        action_key=action_key,
        source_key=action_key,
        owner_slot=owner_slot,
        start_frame=frame,
        duration_frames=duration_frames,
        actor_entity_id=actor_entity_id,
        spatial_query=spatial_query,
        params={} if params is None else params,
    )


def test_action_manager_schedules_timeline_and_reserves_busy_window():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.schedule_timeline(
        ctx,
        _timeline(frame=10, owner_slot=2, duration_frames=2),
    )

    assert decision.accepted
    assert decision.reject_reason is None
    assert decision.lock is not None
    assert decision.lock.owner_slot == 2
    assert decision.occupied_until_frame == 12
    assert manager.is_busy(10)
    assert manager.is_busy(11)
    assert not manager.is_busy(12)
    assert manager.decisions == (decision,)


def test_action_manager_tracks_active_instances_and_impact_points():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.schedule_timeline(
        ctx,
        _timeline(frame=1, duration_frames=2),
    )

    assert decision.instance is not None
    assert manager.instances == (decision.instance,)
    assert len(decision.instance.impact_points) == 1
    assert decision.instance.impact_points[0].frame == 1
    assert decision.instance.impact_points[0].impact_key == "keyboard.e"

    manager.update_frame(ctx, 1)
    assert manager.active_instances == (decision.instance,)

    manager.update_frame(ctx, 2)
    assert manager.active_instances == (decision.instance,)

    manager.update_frame(ctx, 3)
    assert manager.active_instances == ()
    assert manager.is_idle()


def test_action_manager_uses_impact_frame_offsets_and_waits_for_delayed_points():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="character.test.skill",
            owner_slot=1,
            start_frame=10,
            duration_frames=5,
            impact_keys=("character.test.skill.hit",),
            impact_frame_offsets={"character.test.skill.hit": 42},
            create_default_impact_point=False,
        ),
    )

    assert decision.instance is not None
    assert decision.instance.end_frame == 15
    assert decision.instance.impact_points[0].frame == 52

    manager.update_frame(ctx, 15)
    assert not manager.is_busy(15)
    assert not manager.is_idle()

    manager.update_frame(ctx, 52)
    assert manager.is_idle()


def test_action_manager_can_skip_default_impact_point():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.schedule_timeline(
        ctx,
        ActionTimelineSpec(
            action_key="character.test.burst",
            owner_slot=1,
            start_frame=1,
            create_default_impact_point=False,
        ),
    )

    assert decision.instance is not None
    assert decision.instance.impact_points == ()


def test_action_manager_copies_actor_entity_and_params_to_instance():
    ctx = SimulationContext()
    manager = ActionManager()

    decision = manager.schedule_timeline(
        ctx,
        _timeline(
            action_key=TEAM_SWITCH_ACTION_KEY,
            actor_entity_id="player:active",
            params={TEAM_SWITCH_TARGET_SLOT_PARAM: 2},
        ),
    )

    assert decision.instance is not None
    assert decision.instance.actor_entity_id == "player:active"
    assert decision.instance.params == {TEAM_SWITCH_TARGET_SLOT_PARAM: 2}


def test_action_manager_records_consumption_for_known_instance():
    ctx = SimulationContext()
    manager = ActionManager()
    decision = manager.schedule_timeline(ctx, _timeline())

    assert decision.instance is not None
    record = manager.record_consumption(
        frame=1,
        instance_id=decision.instance.instance_id,
        consumer_key="test.consumer",
        status="consumed",
        payload={"ok": True},
    )

    assert manager.consumption_records == (record,)
    assert record.action_key == "keyboard.e"
    assert record.payload == {"ok": True}


def test_action_manager_rejects_consumption_for_unknown_instance():
    manager = ActionManager()

    with pytest.raises(KeyError, match="未知动作实例 id：999"):
        manager.record_consumption(
            frame=1,
            instance_id=999,
            consumer_key="test.consumer",
            status="consumed",
        )


def test_action_manager_records_target_candidates_from_space_query():
    ctx = SimulationContext()
    manager = ActionManager()
    _attach_space_runtime(
        ctx,
        manager,
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                ),
                SpatialEntity(
                    "target:near",
                    SpatialEntityKind.TARGET,
                    position=Vector3(3, 999, 4),
                ),
                SpatialEntity("target:far", SpatialEntityKind.TARGET, position=Vector3(6, 0, 0)),
            ]
        ),
        targets=TargetRuntimeCollection(
            [
                TargetRuntimeState(target_id="near", spatial_entity_id="target:near"),
                TargetRuntimeState(target_id="far", spatial_entity_id="target:far"),
            ]
        ),
    )

    decision = manager.schedule_timeline(
        ctx,
        _timeline(
            spatial_query=SpatialQuery(origin=Vector3(0, 0, 0), radius=5),
        ),
    )

    assert decision.accepted
    assert decision.instance is not None
    assert decision.instance.candidate_entity_ids == ("target:near",)
    assert [
        (target.spatial_entity_id, target.target_id)
        for target in decision.instance.candidate_targets
    ] == [("target:near", "near")]
    assert len(decision.instance.impact_points) == 1
    impact_point = decision.instance.impact_points[0]
    assert impact_point.frame == 1
    assert impact_point.impact_key == "keyboard.e"
    assert impact_point.candidate_entity_ids == decision.instance.candidate_entity_ids
    assert impact_point.candidate_targets == decision.instance.candidate_targets


def test_action_manager_keeps_unresolved_candidate_entities_without_target_refs():
    ctx = SimulationContext()
    manager = ActionManager()
    _attach_space_runtime(
        ctx,
        manager,
        space=Space(
            [
                SpatialEntity("target:known", SpatialEntityKind.TARGET, position=Vector3(1, 0, 0)),
                SpatialEntity(
                    "target:unknown",
                    SpatialEntityKind.TARGET,
                    position=Vector3(2, 0, 0),
                ),
            ]
        ),
        targets=TargetRuntimeCollection(
            [TargetRuntimeState(target_id="known", spatial_entity_id="target:known")]
        ),
    )

    decision = manager.schedule_timeline(
        ctx,
        _timeline(spatial_query=SpatialQuery(origin=Vector3(), radius=5)),
    )

    assert decision.instance is not None
    assert decision.instance.candidate_entity_ids == ("target:known", "target:unknown")
    assert [
        (target.spatial_entity_id, target.target_id)
        for target in decision.instance.candidate_targets
    ] == [("target:known", "known")]


def test_action_manager_rejects_timeline_while_busy_then_accepts_after_window():
    ctx = SimulationContext()
    manager = ActionManager()
    manager.reserve(frame=1, duration_frames=2, source="character_switch", owner_slot=2)

    rejected = manager.schedule_timeline(ctx, _timeline(frame=2, owner_slot=2))
    accepted = manager.schedule_timeline(ctx, _timeline(frame=3, owner_slot=2))

    assert not rejected.accepted
    assert rejected.reject_reason is ActionRejectReason.BUSY
    assert rejected.lock is not None
    assert rejected.lock.source == "character_switch"
    assert rejected.instance is None
    assert accepted.accepted
    assert accepted.instance is not None
    assert [decision.accepted for decision in manager.decisions] == [False, True]


def test_action_manager_rejects_unsupported_action_key_when_limited():
    ctx = SimulationContext()
    manager = ActionManager(supported_action_keys={"keyboard.e"})

    decision = manager.schedule_timeline(ctx, _timeline(action_key="mouse.left"))

    assert not decision.accepted
    assert decision.reject_reason is ActionRejectReason.UNSUPPORTED
    assert manager.locks == ()


def test_action_timeline_rejects_non_positive_duration():
    with pytest.raises(ValueError, match="duration_frames 必须是正整数"):
        ActionTimelineSpec(
            action_key="keyboard.e",
            owner_slot=1,
            start_frame=1,
            duration_frames=0,
        )


def test_action_timeline_rejects_negative_impact_frame_offset():
    with pytest.raises(ValueError, match="impact_frame_offsets 的 value 必须是非负整数"):
        ActionTimelineSpec(
            action_key="keyboard.e",
            owner_slot=1,
            start_frame=1,
            impact_frame_offsets={"keyboard.e": -1},
        )


def test_spatial_query_rejects_negative_radius():
    with pytest.raises(ValueError, match="空间查询半径必须为非负数"):
        SpatialQuery(origin=Vector3(), radius=-1)


def test_team_action_controller_defers_press_until_release():
    ctx = SimulationContext()
    manager = ActionManager()
    controller = TeamActionController(_active_slot_provider(_team_state(active_slot=2)), manager)

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(frame=10, event=KeyEvent("keyboard.e", KeyPhase.PRESS)),
        InputState(),
    )

    assert manager.decisions == ()
    assert len(controller.sessions) == 1
    assert controller.sessions[0].state is InputActionSessionState.DEFERRED

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(
            frame=13,
            event=KeyEvent("keyboard.e", KeyPhase.RELEASE),
            held_frames=3,
        ),
        InputState(),
    )

    session = controller.sessions[0]
    decision = controller.action_inputs[-1].decision
    assert decision is not None
    assert decision.accepted
    assert decision.timeline.start_frame == 13
    assert decision.timeline.owner_slot == 2
    assert session.state is InputActionSessionState.SCHEDULED
    assert session.owner_slot_at_press == 2


def test_team_action_controller_translates_number_press_to_switch_action():
    ctx = SimulationContext()
    manager = ActionManager()
    team_state = _team_state(size=4, active_slot=1)
    space_runtime = _attach_space_runtime(
        ctx,
        manager,
        team_state=team_state,
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                )
            ]
        ),
    )
    controller = TeamActionController(_active_slot_provider(team_state), manager)

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(frame=7, event=KeyEvent("keyboard.2", KeyPhase.PRESS)),
        InputState(),
    )

    player = space_runtime.get_entity("player:active")
    assert team_state.active_slot == 1
    assert player is not None
    assert player.active_slot == 1
    assert controller.switch_inputs[0].decision is not None
    assert controller.switch_inputs[0].decision.accepted
    assert controller.switch_inputs[0].requested_slot == 2
    assert manager.instances[0].action_key == TEAM_SWITCH_ACTION_KEY
    assert manager.instances[0].actor_entity_id == "player:active"
    assert manager.instances[0].params == {TEAM_SWITCH_TARGET_SLOT_PARAM: 2}


def test_team_action_controller_ignores_number_release():
    manager = ActionManager()
    controller = TeamActionController(_active_slot_provider(_team_state(active_slot=1)), manager)

    controller.handle_key_event(
        SimulationContext(),
        KeyEventDispatch(
            frame=8,
            event=KeyEvent("keyboard.2", KeyPhase.RELEASE),
            held_frames=1,
        ),
        InputState(),
    )

    assert controller.active_slot_provider.active_slot == 1
    assert controller.switch_inputs == ()
    assert controller.action_inputs == ()


def test_team_action_controller_rejects_press_during_switch_recovery_and_release_is_ignored():
    ctx = SimulationContext()
    manager = ActionManager()
    controller = TeamActionController(_active_slot_provider(_team_state()), manager)
    input_system = TraceInputSystem(
        [
            KeyInputFrame(
                1,
                (
                    KeyEvent("keyboard.2", KeyPhase.PRESS),
                    KeyEvent("keyboard.e", KeyPhase.PRESS),
                ),
            ),
            KeyInputFrame(
                2,
                (
                    KeyEvent("keyboard.2", KeyPhase.RELEASE),
                    KeyEvent("keyboard.e", KeyPhase.RELEASE),
                ),
            ),
        ],
        controller,
    )

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=BasicRuntimeWorld([controller, manager]),
        max_frames=10,
    ).run()

    rejected = controller.action_inputs[0].decision
    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert rejected is not None
    assert not rejected.accepted
    assert rejected.reject_reason is ActionRejectReason.BUSY
    assert controller.action_inputs[0].session_id is None
    assert controller.action_inputs[1].decision is None
    assert controller.action_inputs[1].session_id is None
    assert controller.sessions == ()


def test_team_action_controller_cancels_pending_session_on_successful_switch():
    ctx = SimulationContext()
    manager = ActionManager()
    team_state = _team_state(size=2)
    controller = TeamActionController(_active_slot_provider(team_state), manager)
    switch_consumer = TeamSwitchActionConsumer(
        on_switch_accepted=controller.cancel_pending_sessions_for_slot,
    )
    space_runtime = _attach_space_runtime(
        ctx,
        manager,
        team_state=team_state,
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                )
            ]
        ),
        consumers={("player:active", TEAM_SWITCH_ACTION_KEY): switch_consumer},
    )

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(frame=1, event=KeyEvent("keyboard.e", KeyPhase.PRESS)),
        InputState(),
    )
    controller.handle_key_event(
        ctx,
        KeyEventDispatch(frame=2, event=KeyEvent("keyboard.2", KeyPhase.PRESS)),
        InputState(),
    )
    space_runtime.update_frame(ctx, frame=2)
    controller.handle_key_event(
        ctx,
        KeyEventDispatch(
            frame=3,
            event=KeyEvent("keyboard.e", KeyPhase.RELEASE),
            held_frames=2,
        ),
        InputState(),
    )

    assert controller.sessions[0].state is InputActionSessionState.CANCELED
    assert controller.sessions[0].cancel_reason == "character_switch"
    assert manager.decisions[0].accepted
    assert switch_consumer.results[0].accepted
    assert controller.action_inputs[-1].decision is None


def test_team_action_controller_records_rejected_switch_while_action_busy():
    ctx = SimulationContext()
    manager = ActionManager()
    team_state = _team_state(size=2)
    controller = TeamActionController(_active_slot_provider(team_state), manager)
    manager.reserve(frame=1, duration_frames=2, source="keyboard.e", owner_slot=1)

    controller.handle_key_event(
        ctx,
        KeyEventDispatch(frame=1, event=KeyEvent("keyboard.2", KeyPhase.PRESS)),
        InputState(),
    )

    assert controller.switch_inputs[0].decision is not None
    assert not controller.switch_inputs[0].decision.accepted
    assert controller.switch_inputs[0].decision.reject_reason is ActionRejectReason.BUSY
    assert team_state.active_slot == 1


def test_team_action_controller_keeps_simulator_running_until_release_action_lock_ends():
    ctx = SimulationContext()
    manager = ActionManager()
    controller = TeamActionController(_active_slot_provider(_team_state()), manager)
    input_system = TraceInputSystem(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.e", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.e", KeyPhase.RELEASE),)),
        ],
        controller,
    )

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=BasicRuntimeWorld([controller, manager]),
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 3
    assert manager.is_idle()


def test_trace_input_system_can_drive_switching_through_space_runtime():
    ctx = SimulationContext()
    manager = ActionManager()
    team_state = _team_state()
    controller = TeamActionController(_active_slot_provider(team_state), manager)
    space_runtime = _attach_space_runtime(
        ctx,
        manager,
        team_state=team_state,
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(),
                    active_slot=1,
                )
            ]
        ),
        consumers={("player:active", TEAM_SWITCH_ACTION_KEY): TeamSwitchActionConsumer()},
    )
    input_system = TraceInputSystem(
        [
            KeyInputFrame(1, (KeyEvent("keyboard.2", KeyPhase.PRESS),)),
            KeyInputFrame(2, (KeyEvent("keyboard.2", KeyPhase.RELEASE),)),
        ],
        controller,
    )

    result = Simulator(
        ctx,
        input_system=input_system,
        runtime_world=BasicRuntimeWorld([controller, manager, space_runtime]),
        max_frames=10,
    ).run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    assert result.end_frame == 2
    assert team_state.active_slot == 2
    player = space_runtime.get_entity("player:active")
    assert player is not None
    assert player.active_slot == 2
    assert manager.consumption_records[0].status == "switched"
