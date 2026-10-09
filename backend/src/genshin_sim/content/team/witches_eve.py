"""魔女的前夜礼（魔导强化）内容定义：魔导资格标记与队伍激活判定。

机制定位（实施规划 §11.7）：跨角色的**队伍级**机制——源站「魔女的前夜礼」
系列覆盖至少 12 名角色，各角色的强化内容写在自己的「魔女的前夜礼」天赋里，
砂糖的 ``passive:9``「魔女的前夜礼·七循之理」是其中之一。四层结构：

| 层 | 规则 | 砂糖对应 |
| --- | --- | --- |
| 魔导资格 | 完成「魔女的课业·XX之题」后角色成为魔导角色 | 课业 =「仙境花之题」 |
| 魔导·秘仪 | 队伍编入 **≥2 名魔导角色**时激活 | — |
| 前夜礼效果 | 各魔导角色的强化写在其「魔女的前夜礼」天赋里 | 见 ``sucrose`` 包 |
| 增强描述 | 部分效果在魔导·秘仪下有增强版，源站记于 ``descriptionBuff`` | C6 的 +8.57142% |

**本期范围 = 最小闭环**（据 D-010：至少两个已实现领域证明相同不变量后才提取
共享模块）：魔导资格由角色内容单元在 ``metadata`` 上声明、装配期收集为
``MageRoster``；**不新建 ``core/systems/`` 级魔导模块**，系统抽离留待第二名
魔导角色落地时再定。生产环境只有一名魔导角色时不激活属预期行为（能力正确、
数据不足），不额外造特例。

判定与月兆（``core/systems/moonsign/``）同构：队伍编入 ≥N 名某类角色 → 激活
全局效果；角色识别同样用 content metadata 标记，不改资产库 schema。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.core.attributes import AttributeSubjectRef

# 魔导资格标记键：角色内容单元在 ``metadata`` 上声明自身为魔导角色。
# 与月兆的 ``moonsign`` 标记同构（角色识别走 content metadata，不改资产库
# schema）；本期裁定「默认已完成魔女的课业」，故标记是角色的静态属性、
# 不作为仿真输入项。
MAGE_MARKER_KEY = "witch_mage"

# 魔导·秘仪激活门槛：队伍编入至少 2 名魔导角色（资产 ``passive:9`` 的
# ``number_1`` 分量；内容侧默认值，实际取值以资产效果行为准）。
MAGE_ACTIVATION_THRESHOLD = 2

# 前夜礼的作用面：源站「普通攻击、重击、下落攻击、元素战技和元素爆发」五类。
#
# 项目主攻击标签按 D-076 为中文，普攻按段展开为 ``普通攻击1`` … ``普通攻击5``，
# 故这里以**具体标签集合**承载五类，不做「普通攻击」前缀归类——前缀匹配会
# 连带命中任何以该前缀开头的派生标签，集合枚举才与源站五类逐字对应。
WITCHES_EVE_DAMAGE_TAGS = frozenset(
    {
        "普通攻击1",
        "普通攻击2",
        "普通攻击3",
        "普通攻击4",
        "普通攻击5",
        "重击",
        "下落攻击",
        "元素战技",
        "元素爆发",
    }
)


@dataclass(frozen=True, slots=True)
class MageRoster:
    """队伍中的魔导角色名录。

    装配期按角色内容单元的魔导标记收集，运行期只读：hooks 用它决定投放范围
    与激活门槛。名录只给**槽位**——角色主体引用由 ``refs`` 现算，避免在运行
    态里长期持有另一个系统的对象。
    """

    slots: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        slots = tuple(self.slots)
        for slot in slots:
            if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
                raise ContentUnitValidationError(f"魔导名录槽位必须是正整数：{slot!r}")
        object.__setattr__(self, "slots", tuple(sorted(set(slots))))

    @property
    def refs(self) -> tuple[AttributeSubjectRef, ...]:
        """按槽位升序的魔导角色主体引用。"""

        return tuple(AttributeSubjectRef.character(f"character:slot_{slot}") for slot in self.slots)

    @property
    def is_active(self) -> bool:
        """魔导·秘仪是否激活（队伍魔导角色数达到门槛）。"""

        return len(self.slots) >= MAGE_ACTIVATION_THRESHOLD

    def contains_slot(self, slot: int) -> bool:
        """槽位是否属于魔导角色。"""

        return slot in self.slots


def build_mage_roster(content_units: Sequence[ContentUnit]) -> MageRoster:
    """按内容单元 metadata 的 ``witch_mage: True`` 标记收集魔导角色槽位。

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
