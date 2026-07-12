from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.content import (
    RUNTIME_PROBE_ACTION_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
    RuntimeProbeState,
    create_default_registry,
)
from genshin_sim.core.events import EventType
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


def test_runtime_probe_asset_connects_to_content_runtime(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)

    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        create_default_registry(),
    ).assemble(SimulationConfig.from_mapping(_runtime_probe_config_payload()))

    assert assembled.assets[0].character.handler_key == RUNTIME_PROBE_CHARACTER_HANDLER_KEY
    assert (
        assembled.content_bundle.content_state_store.get_character_state(
            slot=1,
            handler_key=RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            expected_type=RuntimeProbeState,
        )
        == RuntimeProbeState()
    )
    assert assembled.impact_dispatcher.factory_keys == (RUNTIME_PROBE_IMPACT_KEY,)
    damage_events = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, damage_events.append)

    result = assembled.simulator.run()

    assert result.end_frame == 3
    assert assembled.action_manager.instances[0].action_key == RUNTIME_PROBE_ACTION_KEY
    assert assembled.action_manager.instances[0].impact_points[0].impact_key == (
        RUNTIME_PROBE_IMPACT_KEY
    )
    assert len(assembled.impact_runtime.dispatch_records) == 1
    dispatched = assembled.impact_runtime.dispatch_records[0].requests[0]
    assert dispatched.params["runtime_probe"] == {
        "handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
        "source_impact_key": RUNTIME_PROBE_IMPACT_KEY,
    }
    assert len(assembled.damage_handler.records) == 1
    damage = assembled.damage_handler.records[0].result
    assert damage.base_damage == 200.0
    assert damage.defense.multiplier == 0.5
    assert damage.final_damage == 100.0
    assert [event.event_type for event in damage_events] == [EventType.DAMAGE_RESOLVED]


def _runtime_probe_config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "runtime probe integration", "description": ""},
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
