"""奥黛塔集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import odette as odette_helpers


@pytest.fixture
def odette_asset_db(tmp_path: Path) -> Path:
    return odette_helpers.write_odette_asset_database(tmp_path / "assets.db")


@pytest.fixture
def odette_assembled(
    odette_asset_db: Path,
    tmp_path: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_key: str = "mouse.left",
        max_frames: int = 60,
        payload: dict[str, object] | None = None,
        companions: int = 0,
        ascension_phase: int | None = None,
    ) -> AssembledSimulation:
        if payload is None:
            payload = odette_helpers.odette_input_payload(
                input_key=input_key,
                max_frames=max_frames,
                companions=companions,
            )
        db_path = odette_asset_db
        registry = None
        if companions or ascension_phase is not None:
            # 队伍含陪测角色或需要非满突破时按需重建资产库（默认夹具库只有满
            # 突破的奥黛塔）；陪测角色还需注册其内容单元（动作输入校验要求
            # 每个队伍槽位都有解释器）。
            db_path = odette_helpers.write_odette_asset_database(
                tmp_path / "assets-variant.db",
                companions=companions,
                ascension_phase=6 if ascension_phase is None else ascension_phase,
            )
        if companions:
            registry = create_default_content_unit_registry()
            registry.register_character_factory(
                odette_helpers.ODETTE_COMPANION_HANDLER_KEY,
                odette_helpers.create_odette_companion_content_unit,
            )
        return SimulationAssembler(
            SQLiteAssetRepository(db_path),
            content_unit_registry=registry,
        ).assemble(SimulationInput.from_mapping(payload))

    return _build
