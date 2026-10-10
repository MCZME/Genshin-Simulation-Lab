"""魔导资格：以内容标记收集队伍中的魔导角色，并判定「魔导·秘仪」是否激活。

本模块只承载**资格**，不承载任何**效果**。各魔导角色的强化效果
由**该角色自己的内容包**实现，不在本模块。

因此本模块只做两件事：

1. **收集**：角色内容单元在 ``metadata`` 上声明 ``MAGE_MARKER_KEY: True``，装配期由
   ``build_mage_roster`` 收成只读名录。
2. **判定激活**：队伍魔导角色数达到 ``MAGE_ACTIVATION_THRESHOLD`` 时「魔导·秘仪」激活，
   效果侧据此决定是否投放（``MageRoster.is_active`` / ``contains_slot``）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)

# 魔导资格标记键：角色内容单元在 ``metadata`` 上声明自身为魔导角色。
MAGE_MARKER_KEY = "mage"

# 魔导·秘仪激活门槛：队伍编入至少 2 名魔导角色
MAGE_ACTIVATION_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class MageRoster:
    """队伍中的魔导角色名录（只读值对象，无状态、无运行期演进）。

    装配期按角色内容单元的魔导标记收集，运行期只读：效果侧用它决定激活门槛与
    投放范围。名录只记**槽位**。
    """

    slots: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        slots = tuple(self.slots)
        for slot in slots:
            if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
                raise ContentUnitValidationError(f"魔导名录槽位必须是正整数：{slot!r}")
        object.__setattr__(self, "slots", tuple(sorted(set(slots))))

    @property
    def is_active(self) -> bool:
        """「魔导·秘仪」是否激活（队伍魔导角色数达到门槛）。"""

        return len(self.slots) >= MAGE_ACTIVATION_THRESHOLD

    def contains_slot(self, slot: int) -> bool:
        """槽位是否属于魔导角色。"""

        return slot in self.slots


def build_mage_roster(content_units: Sequence[ContentUnit]) -> MageRoster:
    """按内容单元 metadata 的 ``MAGE_MARKER_KEY: True`` 标记收集魔导角色槽位。

    只认**角色**内容单元且槽位非空；同一槽位上可能有多个单元（角色单元与
    若干效果单元），取并集即可。标记缺失 / 不为 ``True`` 的槽位不参与。
    """

    slots = {
        unit.slot
        for unit in content_units
        if unit.owner_type is ContentUnitOwnerType.CHARACTER
        and unit.slot is not None
        and unit.metadata.get(MAGE_MARKER_KEY) is True
    }
    return MageRoster(tuple(slots))
