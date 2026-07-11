from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class CharacterRuntimeState:
    """单个队伍槽位上的角色运行态。

    这里保存角色在仿真运行中的稳定身份与最小可变状态，不保存空间位置。
    """

    slot: int
    character_key: str
    level: int
    constellation: int = 0
    talent_levels: Mapping[str, int] = field(default_factory=dict)
    energy: float = 0.0
    combat_entity_id: str = ""

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
        if not 0 <= self.constellation <= 6:
            msg = "角色命座必须在 0 到 6 之间"
            raise ValueError(msg)
        if self.energy < 0:
            msg = "角色能量不能为负数"
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

    def gain_energy(self, amount: float) -> None:
        _validate_non_negative_amount(amount, "获得能量")
        self.energy += amount

    def consume_energy(self, amount: float) -> bool:
        _validate_non_negative_amount(amount, "消耗能量")
        if self.energy < amount:
            return False
        self.energy -= amount
        return True


def _validate_non_negative_amount(amount: float, label: str) -> None:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
        msg = f"{label}数值必须是非负数"
        raise ValueError(msg)
