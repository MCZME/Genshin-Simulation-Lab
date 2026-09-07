# 单一关注点：内置反应状态 Buff 定义不得绕过最大生命同步边界。
from __future__ import annotations

from genshin_sim.application.assembly.buffs import _dependency_closure
from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    superconduct_buff_definition,
)


def test_builtin_reaction_status_definitions_do_not_touch_max_hp_closure():
    # 内置反应状态不经 BuffMaxHpChangeCoordinator（契约第 9 节），
    # 其定义不得直接或经属性依赖间接影响 stat.hp.max。
    registry = create_public_attribute_registry()
    max_hp_upstream = _dependency_closure(registry, STAT_HP_MAX)
    definition = superconduct_buff_definition()

    assert all(
        template.target_key not in max_hp_upstream
        for template in definition.attribute_modifiers
    )
