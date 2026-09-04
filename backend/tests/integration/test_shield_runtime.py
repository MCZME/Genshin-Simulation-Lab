from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import (
    CharacterContentUnitRequest,
    ContentUnitRegistry,
)
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TargetingSpec,
    TimedImpactAction,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_damage_taken import CharacterIncomingDamage
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from genshin_sim.infrastructure.results_sqlite import (
    SQLiteResultRepository,
    SQLiteResultWriter,
)
from genshin_sim.infrastructure.results_sqlite.schema import RESULTS_SCHEMA_VERSION
from tests.helpers.assembly import static_asset_input_payload
from tests.helpers.fixture_assets import write_fixture_asset_database

SHIELD_HANDLER_KEY = "character.testing.shield_local"
SHIELD_ACTION_KEY = "testing.shield.action"
SHIELD_IMPACT_KEY = "testing.shield.impact"


class TestingShieldImpactFactory:
    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.SHIELD,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                element="none",
                params={
                    "shield": {
                        "mechanic_key": "testing.shield.action_grant",
                        "handler_key": "testing.shield.handler",
                        "conflict_key": "testing.shield.action_grant",
                        "duration_frames": 60,
                        "grant_policy": "replace",
                        "grant_formula": {
                            "scaling_terms": (),
                            "flat_absorption": 1_000,
                        },
                        "tags": ("testing.shield.vertical",),
                    }
                },
            ),
        )


class _ShieldActionInterpreter:
    supported_action_keys = (SHIELD_ACTION_KEY,)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        if session.key != "keyboard.e":
            return ActionInterpretationResult.reject(f"护盾夹具未映射按键 {session.key}")
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=SHIELD_ACTION_KEY,
                owner=ActionOwnerRef.character(session.owner.slot or 1),
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


def _testing_shield_content_unit(request: CharacterContentUnitRequest) -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version="dev-test",
        slot=request.slot,
        action_interpreter=_ShieldActionInterpreter(),
        actions=(
            TimedImpactAction(
                action_key=SHIELD_ACTION_KEY,
                duration_frames=1,
                impact_keys=(SHIELD_IMPACT_KEY,),
                targeting=TargetingSpec(radius=1.0),
            ),
        ),
        impact_factories={SHIELD_IMPACT_KEY: TestingShieldImpactFactory()},
        metadata={"purpose": "testing_shield_vertical_integration"},
    )


def test_action_impact_grants_shield_and_incoming_damage_reaches_health_runtime(
    tmp_path: Path,
):
    asset_db = tmp_path / "assets.db"
    write_fixture_asset_database(
        asset_db,
        character_handler_key=SHIELD_HANDLER_KEY,
    )
    unit_registry = ContentUnitRegistry()
    unit_registry.register_character_factory(
        SHIELD_HANDLER_KEY,
        _testing_shield_content_unit,
    )
    config = SimulationInput.from_mapping(
        static_asset_input_payload(meta_name="shield integration")
    )
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=unit_registry,
    ).assemble(config)
    captured = []
    for event_type in (
        EventType.SHIELD_GRANTED,
        EventType.SHIELD_CAPACITY_CHANGED,
        EventType.SHIELD_REMOVED,
        EventType.SHIELD_ABSORPTION_RESOLVED,
        EventType.DAMAGE_APPLIED,
    ):
        assembled.context.events.subscribe(event_type, captured.append)

    simulation_result = assembled.simulator.run()

    assert len(assembled.shield_handler.records) == 1
    grant = assembled.shield_handler.records[0].result
    assert grant.resolution.granted_absorption == 1_000
    assert assembled.runtime_world.updatables[:3] == (
        assembled.buff_runtime,
        assembled.infusion_runtime,
        assembled.shield_runtime,
    )
    assert (
        assembled.shield_store.require(grant.instance_ref).state.remaining_native_absorption
        == 1_000
    )

    target_ref = AttributeSubjectRef.character(
        assembled.space_runtime.team_state.current_character.combat_entity_id
    )
    application = assembled.character_damage_taken_coordinator.apply(
        CharacterIncomingDamage(
            damage_id="testing.incoming:1",
            frame=simulation_result.end_frame,
            target_ref=target_ref,
            amount=1_500,
            element=Element.PHYSICAL,
        )
    )

    assert application.shield_result.protected_damage == 1_000
    assert application.shield_result.health_bound_damage == 500
    assert application.health_result.effective_amount == 500
    assert assembled.health_runtime.get_current_hp(target_ref) == 9_500
    assert assembled.shield_store.active_records == ()

    new_event_names = [event.event_type.name for event in captured]
    assert new_event_names == [
        "SHIELD_GRANTED",
        "SHIELD_CAPACITY_CHANGED",
        "SHIELD_REMOVED",
        "SHIELD_ABSORPTION_RESOLVED",
        "DAMAGE_APPLIED",
    ]
    _assert_result_database_round_trip(
        tmp_path,
        captured,
        simulation_result.end_frame,
    )


def _assert_result_database_round_trip(
    tmp_path: Path,
    captured,
    end_frame: int,
) -> None:
    result_db = tmp_path / "results.db"
    writer = SQLiteResultWriter(result_db)
    recorded_events = tuple(
        RecordedEvent(
            frame=event.frame,
            event_type=event.event_type.name,
            data=event.payload.to_dict(),
        )
        for event in captured
    )
    session_id = writer.save_run(
        CompletedSimulationRun(
            input_schema_version=2,
            input_kind="simulation_input",
            input_meta={"name": "shield integration"},
            input_snapshot={"schema_version": 2, "kind": "simulation_input"},
            summary=SimulationRunSummary(
                stop_reason="COMPLETED",
                end_frame=end_frame,
                frames_run=end_frame,
            ),
            events=recorded_events,
            created_at="2026-07-13T00:00:00+00:00",
        )
    )

    detail = SQLiteResultRepository(result_db).get_run(session_id)

    assert RESULTS_SCHEMA_VERSION == "2"
    assert [event.event_type for event in detail.events] == [
        event.event_type for event in recorded_events
    ]
    assert detail.events[0].data["result"]["remaining_after"] == 1_000
    assert detail.events[-1].data["record"]["health_result"]["hp_after"] == 9_500
