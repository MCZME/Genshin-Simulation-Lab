"""芭芭拉动作解释挂点：动作解释由 generic 通用解释器承担。

芭芭拉唯一的角色差异是元素爆发把治疗目标（队伍中自己的全部角色）随动作
参数透传给影响工厂，经 ``_cast_frame_effects`` 挂点注入；其余行为全部由
``data.BARBARA_ACTION_SPEC`` 数据面承载。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ACTION_SPEC,
    ELEMENTAL_BURST_INPUT,
)
from genshin_sim.content.generic.character_actions import (
    GenericCharacterActionInterpreter,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.core.actions import ActionInterpretationContext


class BarbaraActionInterpreter(GenericCharacterActionInterpreter):
    """芭芭拉动作解释器：generic 骨架 + 爆发治疗目标参数。"""

    def __init__(
        self,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
    ) -> None:
        super().__init__(BARBARA_ACTION_SPEC, action_table=action_table)

    def _cast_frame_effects(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        owner_ref: str,
        frame: int,
        session_id: int,
        input_kind: str,
    ) -> Mapping[str, object]:
        if input_kind != ELEMENTAL_BURST_INPUT:
            return {}
        return {"barbara_heal_target_refs": self._team_character_refs(context)}

    @staticmethod
    def _team_character_refs(context: ActionInterpretationContext) -> tuple[str, ...]:
        """爆发治疗目标：队伍中自己的全部角色。"""

        space_runtime = context.simulation.space_runtime
        if space_runtime is None:
            return ()
        return tuple(
            character.combat_entity_id for character in space_runtime.team_state.characters
        )
