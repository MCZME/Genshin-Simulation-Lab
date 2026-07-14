from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.application.execution import (
    CompletedSimulationRun,
    RecordedEvent,
    SimulationRunSummary,
)
from genshin_sim.content import ContentRuntimeContribution, HandlerRegistry
from genshin_sim.content.characters.testing.runtime_probe.actions import (
    RuntimeProbeActionInterpreter,
    create_runtime_probe_action,
)
from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_damage_taken import CharacterIncomingDamage
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)
from genshin_sim.infrastructure.results_sqlite import (
    SQLiteResultRepository,
    SQLiteResultWriter,
)
from genshin_sim.infrastructure.results_sqlite.schema import RESULTS_SCHEMA_VERSION


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


def _testing_shield_content(request) -> ContentRuntimeContribution:
    return ContentRuntimeContribution(
        owner_type="character",
        owner_key=request.character_key,
        handler_key=request.handler_key,
        slot=request.slot,
        action_interpreter=RuntimeProbeActionInterpreter(),
        actions=(create_runtime_probe_action(),),
        impact_factories={RUNTIME_PROBE_IMPACT_KEY: TestingShieldImpactFactory()},
        metadata={"purpose": "testing_shield_vertical_integration"},
    )


def test_action_impact_grants_shield_and_incoming_damage_reaches_health_runtime(
    tmp_path: Path,
):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    registry = HandlerRegistry()
    registry.register_character_factory(
        RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
        _testing_shield_content,
    )
    config = SimulationConfig.from_mapping(_config_payload())
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        registry,
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
    assert assembled.runtime_world.updatables[:2] == (
        assembled.buff_runtime,
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
            element=DamageElement.PHYSICAL,
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
            source_type=None if event.source is None else event.source.__class__.__name__,
            data=event.payload.to_dict(),
        )
        for event in captured
    )
    session_id = writer.save_run(
        CompletedSimulationRun(
            config_schema_version=1,
            config_kind="simulation_config",
            config_meta={"name": "shield integration"},
            config_snapshot={"schema_version": 1, "kind": "simulation_config"},
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

    assert RESULTS_SCHEMA_VERSION == "1"
    assert [event.event_type for event in detail.events] == [
        event.event_type for event in recorded_events
    ]
    assert detail.events[0].data["result"]["remaining_after"] == 1_000
    assert detail.events[-1].data["record"]["health_result"]["hp_after"] == 9_500


def _config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "shield integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:test_character",
                    "level": 90,
                    "constellation": 0,
                    "talents": {"normal_attack": 1},
                },
                "artifacts": {"sets": [], "stats": {}},
            }
        ],
        "scene": {
            "targets": [
                {
                    "id": "target_1",
                    "level": 90,
                    "position": {"x": 0, "y": 0, "z": 0},
                    "resistance": {},
                }
            ]
        },
        "input_trace": [
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": 10},
    }
