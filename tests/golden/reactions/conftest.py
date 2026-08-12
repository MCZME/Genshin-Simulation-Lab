"""元素反应 golden case 共享装配 fixture。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


@pytest.fixture
def golden_assembled(tmp_path: Path) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        meta_name: str = "reaction golden",
        max_frames: int = 240,
        target_positions: tuple[float, ...] = (0.0,),
        target_resistances: Mapping[str, float] | None = None,
        elemental_mastery: float | None = None,
    ) -> AssembledSimulation:
        asset_db = tmp_path / "assets.db"
        write_minimal_static_asset_database(asset_db)
        if elemental_mastery is not None:
            with sqlite3.connect(asset_db) as connection:
                cursor = connection.execute(
                    """
                    UPDATE character_level_stats
                    SET ascension_stat = ?, ascension_value = ?
                    WHERE character_key = ? AND level = ?
                    """,
                    ("elemental_mastery", elemental_mastery, "character:test_character", 90),
                )
            assert cursor.rowcount == 1
        return SimulationAssembler(SQLiteAssetRepository(asset_db)).assemble(
            SimulationInput.from_mapping(
                _input_payload(
                    meta_name=meta_name,
                    max_frames=max_frames,
                    target_positions=target_positions,
                    target_resistances=target_resistances,
                )
            )
        )

    return _build


def _input_payload(
    *,
    meta_name: str,
    max_frames: int,
    target_positions: tuple[float, ...],
    target_resistances: Mapping[str, float] | None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": meta_name, "description": ""},
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
                    "id": f"target_{index}",
                    "level": 90,
                    "position": {"x": position_x, "y": 0, "z": 0},
                    "resistance": dict(target_resistances or {}),
                }
                for index, position_x in enumerate(target_positions, start=1)
            ]
        },
        "input_trace": [],
        "rules": {"enabled": []},
        "run_options": {"max_frames": max_frames},
    }
