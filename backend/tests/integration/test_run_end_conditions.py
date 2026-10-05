"""运行选项结束条件的纵向集成测试。

以芭芭拉元素战技为载体：动作完成后场上仍同时存在技能冷却（阻止
空闲停止）与歌声之环（空间实体长尾），用于区分「空闲时结束」与
「最后一个动作完成后结束」两种结束条件的停止帧与停止原因。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_START_FRAME,
)
from genshin_sim.core.simulation import SimulationStopReason
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import barbara as barbara_helpers

_COOLDOWN_END_FRAME = (
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_START_FRAME + BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES
)


def _assemble(payload: dict[str, object], tmp_path: Path, name: str):
    asset_db = barbara_helpers.write_barbara_asset_database(tmp_path / f"{name}.db")
    return SimulationAssembler(SQLiteAssetRepository(asset_db)).assemble(
        SimulationInput.from_mapping(payload)
    )


def test_default_end_condition_waits_for_longtail(tmp_path: Path):
    """缺省结束条件与现状一致：等冷却长尾走完才以 COMPLETED 结束。"""

    payload = barbara_helpers.barbara_input_payload(
        input_key="keyboard.e",
        max_frames=_COOLDOWN_END_FRAME + 60,
    )
    assembled = _assemble(payload, tmp_path, "default")

    result = assembled.simulator.run()

    assert result.stop_reason is SimulationStopReason.COMPLETED
    # 冷却（1920+ 帧）是最长尾：空闲结束必须晚于动作完成的帧。
    assert result.end_frame >= BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES


def test_actions_settled_end_condition_stops_after_last_action(tmp_path: Path):
    """end_condition=actions_settled：动作层静止即停，冷却与召唤物长尾被截断。"""

    payload = barbara_helpers.barbara_input_payload(
        input_key="keyboard.e",
        max_frames=_COOLDOWN_END_FRAME + 60,
    )
    assert isinstance(payload["run_options"], dict)
    payload["run_options"]["end_condition"] = "actions_settled"
    assembled = _assemble(payload, tmp_path, "actions_settled")

    result = assembled.simulator.run()

    assert result.stop_reason is SimulationStopReason.ACTIONS_SETTLED
    assert result.end_frame < BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES
    # 歌声之环（907 帧）在停止时仍活跃：动作层之外的召唤物长尾被忽略。
    assert assembled.space_runtime.created_object_runtime.objects
    assert not assembled.space_runtime.created_object_runtime.is_idle()
