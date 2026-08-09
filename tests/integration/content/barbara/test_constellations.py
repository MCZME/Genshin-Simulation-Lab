"""芭芭拉命座的纵向集成：能量、冷却与水伤加成跟随。"""

from __future__ import annotations

from pathlib import Path

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    AttributeQuery,
    AttributeSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.cooldown import CooldownKey, CooldownSubjectRef
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import barbara as barbara_helpers
from tests.helpers.barbara_assets import write_barbara_probe_asset_database


@pytest.mark.parametrize(
    ("constellation", "expected_energy"),
    (
        pytest.param(1, 1.0, id="c1_unlocked"),
        pytest.param(0, 0.0, id="c1_locked"),
    ),
)
def test_barbara_c1_restores_one_energy_every_600_frames(
    barbara_assembled,
    constellation: int,
    expected_energy: float,
):
    payload = barbara_helpers.barbara_config_payload(
        constellation=constellation,
        max_frames=700,
    )
    payload["input_trace"] = barbara_helpers.barbara_long_input_trace()
    assembled = barbara_assembled(payload=payload)

    assembled.simulator.run()

    energy_ref = AttributeSubjectRef.character("character:slot_1")
    assert assembled.energy_runtime.get_current_energy(energy_ref) == pytest.approx(expected_energy)


def test_barbara_c2_reduces_elemental_skill_cooldown(barbara_assembled):
    cooldown_key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_skill",
    )

    assembled_c2 = barbara_assembled(
        input_key="keyboard.e",
        max_frames=20,
        constellation=2,
    )
    assembled_c2.simulator.run()
    c2_record = assembled_c2.cooldown_runtime.store.get_record(cooldown_key)
    assert c2_record.active_recovery is not None
    assert c2_record.active_recovery.interval_frames == 1632

    assembled_c0 = barbara_assembled(input_key="keyboard.e", max_frames=20)
    assembled_c0.simulator.run()
    c0_record = assembled_c0.cooldown_runtime.store.get_record(cooldown_key)
    assert c0_record.active_recovery is not None
    assert c0_record.active_recovery.interval_frames == 1920


def test_barbara_c2_hydro_bonus_follows_active_character_on_switch(tmp_path: Path):
    asset_db = write_barbara_probe_asset_database(tmp_path / "assets.db")
    payload = barbara_helpers.barbara_probe_config_payload(
        constellation=2,
        max_frames=140,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 80, "events": [{"key": "keyboard.2", "phase": "press"}]},
            {"frame": 81, "events": [{"key": "keyboard.2", "phase": "release"}]},
            {"frame": 110, "events": [{"key": "keyboard.1", "phase": "press"}]},
            {"frame": 111, "events": [{"key": "keyboard.1", "phase": "release"}]},
        ],
    )
    assembled = SimulationAssembler(SQLiteAssetRepository(asset_db)).assemble(
        SimulationConfig.from_mapping(payload)
    )

    resolver = assembled.attribute_runtime.resolver
    slot_1 = AttributeSubjectRef.character("character:slot_1")
    slot_2 = AttributeSubjectRef.character("character:slot_2")
    captured: dict[int, dict[str, float]] = {}

    def _capture_hydro_bonus(event) -> None:
        frame = getattr(event, "frame", None)
        if frame not in (100, 130):
            return
        captured[frame] = {
            "slot_1": resolver.resolve(
                AttributeQuery(slot_1, BONUS_DAMAGE_HYDRO, frame=frame)
            ).final_value,
            "slot_2": resolver.resolve(
                AttributeQuery(slot_2, BONUS_DAMAGE_HYDRO, frame=frame)
            ).final_value,
        }

    assembled.context.events.subscribe(EventType.FRAME_STARTED, _capture_hydro_bonus)
    assembled.simulator.run()

    assert captured[100] == {
        "slot_1": pytest.approx(0.0),
        "slot_2": pytest.approx(0.15),
    }
    assert captured[130] == {
        "slot_1": pytest.approx(0.15),
        "slot_2": pytest.approx(0.0),
    }


def test_barbara_c4_restores_energy_per_distinct_target(barbara_assembled):
    assembled = barbara_assembled(
        input_key="mouse.right",
        max_frames=80,
        constellation=4,
        targets=(
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            },
            {
                "id": "target_2",
                "level": 90,
                "position": {"x": 0.5, "y": 0, "z": 0},
                "resistance": {},
            },
            {
                "id": "target_3",
                "level": 90,
                "position": {"x": 1.0, "y": 0, "z": 0},
                "resistance": {},
            },
        ),
    )

    assembled.simulator.run()

    energy_ref = AttributeSubjectRef.character("character:slot_1")
    assert assembled.energy_runtime.get_current_energy(energy_ref) == pytest.approx(3.0)


def test_barbara_c4_caps_at_five_energy_per_charged_attack(barbara_assembled):
    assembled = barbara_assembled(
        input_key="mouse.right",
        max_frames=80,
        constellation=4,
        targets=tuple(
            {
                "id": f"target_{index}",
                "level": 90,
                "position": {"x": index * 0.5, "y": 0, "z": 0},
                "resistance": {},
            }
            for index in range(6)
        ),
    )

    assembled.simulator.run()

    energy_ref = AttributeSubjectRef.character("character:slot_1")
    assert assembled.energy_runtime.get_current_energy(energy_ref) == pytest.approx(5.0)
