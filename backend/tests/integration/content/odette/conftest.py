"""奥黛塔集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import odette as odette_helpers


@pytest.fixture
def odette_asset_db(tmp_path: Path) -> Path:
    return odette_helpers.write_odette_asset_database(tmp_path / "assets.db")


@pytest.fixture
def odette_assembled(
    odette_asset_db: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_key: str = "mouse.left",
        max_frames: int = 60,
        payload: dict[str, object] | None = None,
    ) -> AssembledSimulation:
        if payload is None:
            payload = odette_helpers.odette_input_payload(
                input_key=input_key,
                max_frames=max_frames,
            )
        return SimulationAssembler(SQLiteAssetRepository(odette_asset_db)).assemble(
            SimulationInput.from_mapping(payload)
        )

    return _build
