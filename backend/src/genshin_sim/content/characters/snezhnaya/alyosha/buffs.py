"""阿罗夏 Buff 定义：弋猎印记（敌人侧标记）与猎者之准（前台攻击力提升）。

作用域口径（规划文档 §5-1，spike 结论 §6-1）：

- 弋猎印记挂场景目标（``TARGET`` 主体）身上，是纯标记（``marker_only``）：
  图加林按印记存在性筛索敌、攻击激活（清除）印记并触发猎者之准。
- 猎者之准挂 ``ACTIVE_CHARACTER`` 位置级主体：全队持有（记录在队伍作用域
  上、切换前台即时生效），仅当前场上角色经属性投影读到加成（前台门控由
  ``BuffAttributeModifierProvider`` 的主体匹配语义承担）。
- C6 叠满伴生精通 Buff 与猎者之准同主体、同帧刷新/到期（由授予侧在层数
  到达 2 时随猎者之准一并发放）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_MARK_CONFLICT_KEY,
    ALYOSHA_HUNTERS_MARK_MECHANIC_KEY,
    ALYOSHA_HUNTERS_PRECISION_ATK_TERM_KEY,
    ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_CONFLICT_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_CONFLICT_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_MECHANIC_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_TERM_KEY,
    ALYOSHA_HUNTERS_PRECISION_MECHANIC_KEY,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)


def build_hunters_mark_definition() -> BuffDefinition:
    """弋猎印记：敌人侧纯标记 Buff（E/NA4 施加、图加林攻击激活清除）。"""

    return BuffDefinition(
        definition_key=ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
        mechanic_key=ALYOSHA_HUNTERS_MARK_MECHANIC_KEY,
        handler_key=ALYOSHA_CHARACTER_HANDLER_KEY,
        conflict_key=ALYOSHA_HUNTERS_MARK_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.TARGET}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        tags=frozenset({"alyosha.hunters_mark"}),
        display_name="弋猎印记",
    )


def build_hunters_precision_definition(*, max_stacks: int) -> BuffDefinition:
    """猎者之准：前台攻击力提升（随 E 等级的每层值由申请侧携带）。

    ``LINEAR`` 层数缩放：每层加成 = 申请值，实际加成 = 申请值 × 当前层数；
    C6 解锁时 ``max_stacks`` 提升到 2（后台可叠）。
    """

    return BuffDefinition(
        definition_key=ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
        mechanic_key=ALYOSHA_HUNTERS_PRECISION_MECHANIC_KEY,
        handler_key=ALYOSHA_CHARACTER_HANDLER_KEY,
        conflict_key=ALYOSHA_HUNTERS_PRECISION_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.ACTIVE_CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=max_stacks,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=ALYOSHA_HUNTERS_PRECISION_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=BuffStackScaling.LINEAR,
            ),
        ),
        tags=frozenset({"alyosha.hunters_precision"}),
        display_name="猎者之准",
    )


def build_hunters_precision_mastery_definition() -> BuffDefinition:
    """C6 叠满伴生精通：猎者之准叠至 2 层时对前台 +100 元素精通。"""

    return BuffDefinition(
        definition_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
        mechanic_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_MECHANIC_KEY,
        handler_key=ALYOSHA_CHARACTER_HANDLER_KEY,
        conflict_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.ACTIVE_CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({"alyosha.hunters_precision", "alyosha.constellation_c6"}),
        display_name="猎者之准·元素精通",
    )
