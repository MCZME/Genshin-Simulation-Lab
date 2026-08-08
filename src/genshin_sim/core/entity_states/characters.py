from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from genshin_sim.core.entity_states.content_state import ContentStateMount
from genshin_sim.core.entity_states.energy import EnergyState
from genshin_sim.core.entity_states.health import HealthState


@dataclass(slots=True)
class CharacterRuntimeState:
    """单个队伍槽位上的角色运行态。

    这里保存角色在仿真运行中的稳定身份与最小可变状态，不保存空间位置。
    """

    slot: int
    character_key: str
    level: int
    ascension_phase: int = 0
    constellation: int = 0
    talent_levels: Mapping[str, int] = field(default_factory=dict)
    energy: EnergyState = field(default_factory=EnergyState)
    combat_entity_id: str = ""
    health: HealthState = field(default_factory=lambda: HealthState(0.0))
    content_states: Mapping[str, ContentStateMount] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.slot <= 0:
            msg = "角色槽位必须是正整数"
            raise ValueError(msg)
        if not self.character_key:
            msg = "角色 asset_key 必须是非空字符串"
            raise ValueError(msg)
        if self.level <= 0:
            msg = "角色等级必须是正整数"
            raise ValueError(msg)
        if not 0 <= self.ascension_phase <= 6:
            msg = "角色突破阶段必须在 0 到 6 之间"
            raise ValueError(msg)
        if not 0 <= self.constellation <= 6:
            msg = "角色命座必须在 0 到 6 之间"
            raise ValueError(msg)
        if not isinstance(self.energy, EnergyState):
            msg = "角色元素能量状态必须是 EnergyState"
            raise ValueError(msg)
        if not isinstance(self.health, HealthState):
            msg = "角色生命状态必须是 HealthState"
            raise ValueError(msg)

        talent_levels = dict(self.talent_levels)
        for talent_name, talent_level in talent_levels.items():
            if not talent_name:
                msg = "角色天赋名称必须是非空字符串"
                raise ValueError(msg)
            if talent_level <= 0:
                msg = "角色天赋等级必须是正整数"
                raise ValueError(msg)
        self.talent_levels = talent_levels

        if not self.combat_entity_id:
            self.combat_entity_id = f"character:slot_{self.slot}"
        if not self.combat_entity_id.strip():
            msg = "角色战斗实体 id 必须是非空字符串"
            raise ValueError(msg)

        content_states = dict(self.content_states)
        for state_key, mount in content_states.items():
            if not isinstance(mount, ContentStateMount):
                msg = "content_states 的值必须是 ContentStateMount"
                raise ValueError(msg)
            if state_key != mount.state_key:
                msg = f"content_states 键 {state_key!r} 必须与挂载 state_key 一致"
                raise ValueError(msg)
            if mount.owner != self.combat_entity_id:
                msg = (
                    f"内容状态挂载 owner {mount.owner!r} 必须等于角色实体 {self.combat_entity_id!r}"
                )
                raise ValueError(msg)
        self.content_states = content_states
