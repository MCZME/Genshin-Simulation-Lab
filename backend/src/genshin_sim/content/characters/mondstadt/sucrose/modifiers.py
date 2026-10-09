"""砂糖内容属性修饰：固有天赋 A1 / A4 的元素精通 Buff 定义。

A1「触媒置换术」与 A4「小小的慧风」都是**限时元素精通提升**，作用对象是
队伍中的**角色主体**（逐个投放），因此两者都用 Buff 定义承载、由 ``hooks.py``
的对应钩子在触发帧发放：

- A1 = 固定 +50 精通（``FLAT_ADD``），来源是被扩散元素对应的元素类型匹配，
  本身不是「基于其他属性折算」的转化效果，故产物标记保持默认（可被二次转化）。
- A4 = 砂糖快照精通的 20%（``FLAT_ADD``，数值在触发帧算好后随申请携带），
  属转化效果：产物标记 ``reconvertible=False``（不可被二次转化），避免被另一
  次「读精通再折算」的效果二次吸收（实施规划 §11.4、属性系统契约 §11.4）。

两者均为覆盖刷新（重触发刷新时长、不叠数值，实施规划 §11.7 第 4 项同口径）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_BUFF_DEFINITION_KEY,
    SUCROSE_A1_CONFLICT_KEY,
    SUCROSE_A1_MASTERY_TERM_KEY,
    SUCROSE_A1_MECHANIC_KEY,
    SUCROSE_A4_BUFF_DEFINITION_KEY,
    SUCROSE_A4_CONFLICT_KEY,
    SUCROSE_A4_MASTERY_TERM_KEY,
    SUCROSE_A4_MECHANIC_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
)
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)


def build_a1_mastery_buff_definition() -> BuffDefinition:
    """A1 触媒置换术：与被扩散元素同元素的角色 +50 元素精通（覆盖刷新）。"""

    return BuffDefinition(
        definition_key=SUCROSE_A1_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_A1_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_A1_HANDLER_KEY,
        conflict_key=SUCROSE_A1_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SUCROSE_A1_MASTERY_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_A1_HANDLER_KEY}),
        display_name="触媒置换术·元素精通",
    )


def build_a4_mastery_buff_definition() -> BuffDefinition:
    """A4 小小的慧风：全队（除砂糖）按砂糖快照精通 20% 提升精通（覆盖刷新）。

    产物标记 ``reconvertible=False``：该加成的数值由「读砂糖精通再折算」得出，
    属转化效果，不能再被另一次同类折算读入（实施规划 §11.4）。
    """

    return BuffDefinition(
        definition_key=SUCROSE_A4_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_A4_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_A4_HANDLER_KEY,
        conflict_key=SUCROSE_A4_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SUCROSE_A4_MASTERY_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
                reconvertible=False,
            ),
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_A4_HANDLER_KEY}),
        display_name="小小的慧风·元素精通",
    )
