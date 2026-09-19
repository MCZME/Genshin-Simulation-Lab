"""西风长枪顺风而行 golden 基线。

验证能力：武器被动「顺风而行」在暴击命中敌人时产出的微粒形态——`pickup_kind`、
`element` 与 `count`。这是本机制需要长期保证的不变量：其余实现细节（触发窗口、
逐帧时序、载体延迟、资产参数解读路径）都可能随后续实现调整，不作为基准锁定。

真实数据来源及适用版本：

- 产球形态：被动触发时生成 ``3`` 个无元素微粒 ``Favonius Series``
  条目，与[元素能量系统设计](../../../../docs/架构/系统/元素能量系统设计.md)第 3.1 节
  引用的能量资料基线同源；精炼只改变产球频率，不改变数量。
- 载体延迟不在此断言：核心契约要求真实 content 显式提供该延迟，但当前没有可信来源，
  ``[20, 50]`` 是工程约定而非游戏真值，不得进入 golden 预期。

完整输入条件：单槽位队伍，芭芭拉 90 级 / 0 命 / 天赋 1-1-1，装备西风长枪（90 级、
R5），圣遗物仅 ``crit_rate`` 拉满；单目标 90 级；``rules.active`` 启用
``crit_mode: random``，使暴击由仿真随机源确定性产生；``input_trace`` 为 21 帧间隔的
持续普攻；``seed = 20260918``，``max_frames = 1200``。装备等级属性与触发概率/间隔
取自 ``tests/helpers/barbara.py`` 的**合成**夹具值，不代表任何真实资产数值（见测试
规范 §3.2）。

预期输出与允许误差：产球数量与元素按精确匹配（误差 0）。

不覆盖的行为：能量结算时点与逐帧时序、触发窗口与概率/间隔取值、载体延迟区间、
资产参数解读与精炼校验、同帧切人的帧内顺序、快照恢复与重放、真实资产库数值基线。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.energy import EnergyElement, EnergyPickupKind
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import barbara as barbara_helpers

SEED = 20260918
MAX_FRAMES = 1200


def _windfall_spawns(tmp_path: Path, *, refinement: int = 5) -> tuple[Any, ...]:
    """装配并运行芭芭拉 + 西风长枪合成夹具，返回顺风而行的产球记录。"""

    asset_db = barbara_helpers.write_barbara_favonius_lance_asset_database(tmp_path / "assets.db")
    payload = barbara_helpers.barbara_favonius_lance_input_payload(
        refinement=refinement,
        max_frames=MAX_FRAMES,
        seed=SEED,
    )
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=create_default_content_unit_registry(),
    ).assemble(SimulationInput.from_mapping(payload))

    spawns: list[Any] = []

    def _collect_spawn(event: Any) -> None:
        spawns.append(event.payload.record)

    assembled.context.events.subscribe(EventType.ENERGY_PICKUP_SPAWNED, _collect_spawn)
    assembled.simulator.run()
    return tuple(spawns)


def test_windfall_spawns_three_clear_particles(tmp_path: Path):
    spawns = _windfall_spawns(tmp_path)

    assert spawns, "暴击命中应至少触发一次顺风而行"
    for record in spawns:
        assert record.pickup_kind is EnergyPickupKind.PARTICLE
        assert record.element is EnergyElement.CLEAR
        assert record.count == 3
