"""Runtime probe 最小闭环集成：CLI → 结果库，以及装配器 → 运行时内部接线。"""

from __future__ import annotations

import json
from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.cli.main import main
from genshin_sim.content import (
    RUNTIME_PROBE_ACTION_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.core.events import EventType
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)
from genshin_sim.infrastructure.results_sqlite import SQLiteResultRepository
from tests.helpers.assembly import static_asset_input_payload


def test_cli_and_assembler_runtime_probe_closed_loop(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    asset_db = tmp_path / "assets.db"
    result_db = tmp_path / "results.db"
    input_path = tmp_path / "config.json"
    (tmp_path / "config.toml").write_text(
        'schema_version = 1\n\n[workspace]\ndata_dir = "data"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    write_minimal_static_asset_database(asset_db)
    input_path.write_text(
        json.dumps(
            static_asset_input_payload(meta_name="runtime probe integration"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            str(input_path),
            "--db",
            str(asset_db),
            "--results-db",
            str(result_db),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    session_id = _extract_session_id(output)
    detail = SQLiteResultRepository(result_db).get_run(session_id)
    assert detail.state == "completed"
    assert detail.initial_snapshot is not None
    assert {"space", "aura", "aura_icd", "team"} <= set(detail.initial_snapshot["providers"])
    event_types = [event.event_type for event in detail.events]

    assert detail.summary is not None
    assert detail.summary.stop_reason == "COMPLETED"
    assert detail.summary.end_frame == 3
    assert event_types == [
        "SIMULATION_STARTED",
        "RESONANCE_ACTIVATED",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "MOONSIGN_LEVEL_SET",
        "INPUT_KEY_RECEIVED",
        "INPUT_SESSION_BOUNDARY_REACHED",
        "ACTION_STARTED",
        "AURA_ICD_RESOLVED",
        "AURA_APPLIED",
        "DAMAGE_RESOLVED",
        "ELEMENTAL_INTERACTION_RESOLVED",
        "SIMULATION_ENDED",
    ]
    assert detail.events[1].data == {
        "active_keys": [],
        "team_size": 1,
        "established_frame": 0,
    }
    assert detail.events[2].data == {
        "key": "keyboard.e",
        "phase": "press",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[3].data["will_interpret"] is True
    assert detail.events[5].data == {
        "key": "keyboard.e",
        "phase": "release",
        "order": 0,
        "session_id": 1,
    }
    assert detail.events[6].data["held_frames"] == 1
    assert detail.events[7].data["action_key"] == "character.testing.runtime_probe.action"
    assert detail.events[10].data["result"]["final_damage"] > 0
    assert detail.events[12].data == {
        "stop_reason": "COMPLETED",
        "end_frame": 3,
        "frames_run": 3,
    }
    assert detail.input_snapshot["team"][0]["character"]["asset_key"] == (
        "character:test_character"
    )

    assembled = SimulationAssembler(SQLiteAssetRepository(asset_db)).assemble(
        SimulationInput.from_mapping(
            static_asset_input_payload(meta_name="runtime probe integration")
        )
    )

    assert assembled.assets[0].character.handler_key == RUNTIME_PROBE_CHARACTER_HANDLER_KEY
    assert assembled.content_bundle.content_state_mounts == ()
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


def _extract_session_id(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("session_id: "):
            return line.removeprefix("session_id: ").strip()
    raise AssertionError(f"session id not found in output: {output}")
