"""generic 武器被动的 Buff 定义构建部件。

不带键：本模块只提供「单属性武器 Buff 定义」的共享构建规则，键、显示名与
数值由各武器内容包传入。覆盖两类形态：

- 单实例攻击窗口（如「触发反应后攻击力提升」）：``refresh`` 策略、常数缩放；
- 命中叠层（如「命中时攻击力提升，至多 N 层」）：``stack_independent`` 策略、
  线性缩放。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)


def atk_percent_buff_definition(
    *,
    definition_key: str,
    mechanic_key: str,
    handler_key: str,
    conflict_key: str,
    term_key: str,
    display_name: str,
    application_policy: BuffApplicationPolicy,
    max_stacks: int = 1,
    stack_scaling: BuffStackScaling = BuffStackScaling.CONSTANT,
    audit_tags: tuple[str, ...] = (),
) -> BuffDefinition:
    """构建一个攻击力百分比词条的 Buff 定义。

    ``definition_key`` 与 ``conflict_key`` 按穿戴者槽位区分（与白湖冬羽一致），
    使不同穿戴者的同名 Buff 互不干扰。
    """

    if application_policy not in {
        BuffApplicationPolicy.REFRESH,
        BuffApplicationPolicy.STACK_INDEPENDENT,
    }:
        raise ContentUnitValidationError(
            "武器攻击力 Buff 只支持 refresh（单实例窗口）与 stack_independent（叠层）策略"
        )
    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=mechanic_key,
        handler_key=handler_key,
        conflict_key=conflict_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=application_policy,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=max_stacks,
        display_name=display_name,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=term_key,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=stack_scaling,
                audit_tags=audit_tags,
            ),
        ),
    )
