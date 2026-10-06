"""阿罗夏集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import alyosha as alyosha_helpers


@pytest.fixture
def alyosha_asset_db(tmp_path: Path) -> Path:
    return alyosha_helpers.write_alyosha_asset_database(tmp_path / "assets.db")


@pytest.fixture
def alyosha_assembled(
    alyosha_asset_db: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_key: str = "mouse.left",
        max_frames: int = 60,
        constellation: int = 0,
        input_trace: list[dict[str, object]] | None = None,
        targets: list[dict[str, object]] | None = None,
    ) -> AssembledSimulation:
        payload = alyosha_helpers.alyosha_input_payload(
            input_key=input_key,
            max_frames=max_frames,
            constellation=constellation,
            input_trace=input_trace,
            targets=targets,
        )
        return SimulationAssembler(SQLiteAssetRepository(alyosha_asset_db)).assemble(
            SimulationInput.from_mapping(payload)
        )

    return _build
