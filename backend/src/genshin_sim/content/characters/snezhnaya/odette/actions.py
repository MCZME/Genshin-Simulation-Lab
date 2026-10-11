"""奥黛塔动作解释挂点：动作解释由 generic 通用解释器承担。

奥黛塔的角色差异是特殊战技窗口（独舞倒影节奏）：E 在窗口内改走特殊战技
动作与专属冷却，起手按窗口状态武装锚点字段，动作参数按动作键区分普通/
特殊战技。四个差异点分别经 ``_ability_gate_override`` / ``_select_action_override``
/ ``_state_patch_extra_fields`` / ``_action_kind_value`` 挂点接入；其余行为全部由
``data.ODETTE_ACTION_SPEC`` 数据面承载。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    ODETTE_ACTION_SPEC,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY,
    ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY,
    ODETTE_SPECIAL_WINDOW_FRAMES,
    ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME,
)
from genshin_sim.content.generic.character_actions import (
    GenericCharacterActionInterpreter,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    resolve_mount,
)
from genshin_sim.core.actions import ActionInterpretationContext
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.simulation.context import SimulationContext


class OdetteActionInterpreter(GenericCharacterActionInterpreter):
    """奥黛塔动作解释器：generic 骨架 + 特殊战技窗口挂点。"""

    def __init__(
        self,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
    ) -> None:
        super().__init__(ODETTE_ACTION_SPEC, action_table=action_table)

    # --- 窗口判定 -----------------------------------------------------------------

    def _special_window_active(
        self,
        context: SimulationContext,
        slot: int,
        frame: int,
    ) -> bool:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=ODETTE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise OdetteInterpreterError(f"缺少奥黛塔状态挂载：{exc}") from exc
        raw_anchor = mount.values.get(ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME)
        anchor = (
            raw_anchor if isinstance(raw_anchor, int) and not isinstance(raw_anchor, bool) else 0
        )
        return anchor > 0 and frame - anchor < ODETTE_SPECIAL_WINDOW_FRAMES

    # --- 挂点 ---------------------------------------------------------------------

    def _ability_gate_override(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
        input_kind: str,
    ) -> tuple[str, str] | None:
        if input_kind != ELEMENTAL_SKILL_INPUT:
            return None
        if not self._special_window_active(context.simulation, slot, frame):
            return None
        return (ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY, "奥黛塔特殊战技冷却未就绪")

    def _select_action_override(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        frame: int,
        held_frames: int,
        input_kind: str,
        last_action_key: str,
        height: float,
    ) -> TimedActionSpec | None:
        if input_kind != ELEMENTAL_SKILL_INPUT:
            return None
        if not self._special_window_active(context.simulation, slot, frame):
            return None
        return self._action_table[ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY]

    def _state_patch_extra_fields(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        frame: int,
        action: TimedActionSpec,
        input_kind: str,
    ) -> Mapping[str, JSONValue]:
        # 独舞倒影节奏由创建物调度承载：普通战技/爆发起手时重锚窗口，
        # 特殊战技本身不重锚。
        if input_kind not in (ELEMENTAL_SKILL_INPUT, ELEMENTAL_BURST_INPUT):
            return {}
        if action.action_key == ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY:
            return {}
        return {ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME: frame}

    def _action_kind_value(self, *, action: TimedActionSpec, input_kind: str) -> str:
        if action.action_key == ODETTE_SPECIAL_ELEMENTAL_SKILL_ACTION_KEY:
            return ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY
        return input_kind


class OdetteInterpreterError(RuntimeError):
    """奥黛塔解释器运行期错误（接线缺失或状态不一致）。"""
