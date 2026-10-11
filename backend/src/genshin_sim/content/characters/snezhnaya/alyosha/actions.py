"""阿罗夏动作解释挂点：动作解释由 generic 通用解释器承担。

阿罗夏的角色差异有两处，分别经命名挂点接入，其余行为全部由
``data.ALYOSHA_ACTION_SPEC`` 数据面承载：

- E 长按按住侧（``_input_override``）：长按的按住阶段（瞄准）无仿真效果，
  伤害发生在释放阶段；按住越过 250 帧实测上限时由 HOLD 触发自动起手长按
  释放阶段动作（起手成功即脱离会话，物理松开不再重复解释；冷却或衔接
  条件未就绪时保持等待，下一帧重试，物理松开仍可正常解释）。
- 点按/长按改判（``_select_action_override``）：长柄重击是武器类型通用
  形式——重击链自带一段普攻前段（N1 命中点为复合动作影响点），衔接判定
  继续走普攻衔接列，选择层按按住时长改判重击动作（重击不改变普攻连段
  位置，重击后下一次点按回第一段）；E 长按释放阶段动作同理按按住时长改判。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ACTION_SPEC,
    ALYOSHA_CHARGED_ATTACK_ACTION_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES,
    ALYOSHA_HOLD_INPUT_MIN_FRAMES,
    ELEMENTAL_SKILL_INPUT,
    NORMAL_ATTACK_INPUT,
)
from genshin_sim.content.generic.character_actions import (
    GenericCharacterActionInterpreter,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.content.generic.transitions import evaluate_transition
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
)


class AlyoshaActionInterpreter(GenericCharacterActionInterpreter):
    """阿罗夏动作解释器：generic 骨架 + E 长按按住侧与长按改判挂点。"""

    def __init__(
        self,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
    ) -> None:
        super().__init__(ALYOSHA_ACTION_SPEC, action_table=action_table)

    # --- 挂点：E 长按按住侧 -------------------------------------------------------

    def _input_override(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
        input_kind: str,
    ) -> ActionInterpretationResult | None:
        if session.trigger is not ActionInterpretationTrigger.HOLD:
            return None
        return self._interpret_hold(context, session, slot, input_kind)

    def _interpret_hold(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
        input_kind: str,
    ) -> ActionInterpretationResult:
        """按住触发：E 越过实测最长按住上限时自动进入释放阶段。

        起手帧 = 按下 + 上限帧；本路径只对 E 输入生效，其余输入的 HOLD 与
        通用骨架一致保持等待。
        """

        if input_kind != ELEMENTAL_SKILL_INPUT:
            return ActionInterpretationResult.wait()
        if session.held_frames < ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES:
            return ActionInterpretationResult.wait()
        if self._elemental_skill_rejection(context, slot, session.current_frame) is not None:
            return ActionInterpretationResult.wait()
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if not evaluate_transition(
            action_table=self._action_table,
            display_name=self._spec.display_name,
            prev_action_key=last_action_key,
            input_kind=input_kind,
            frame=session.current_frame,
            prev_start_frame=last_action_start_frame,
        ).linkable:
            return ActionInterpretationResult.wait()
        action = self._action_table[ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY]
        self._queue_state_patch(
            context,
            owner_ref=f"character:slot_{slot}",
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.current_frame,
            input_kind=input_kind,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params=self._action_params(
                    action,
                    input_kind,
                    self._current_height(context.simulation),
                ),
                source_session_id=session.session_id,
            )
        )

    # --- 挂点：点按/长按改判 -------------------------------------------------------

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
        if held_frames < ALYOSHA_HOLD_INPUT_MIN_FRAMES:
            return None
        if input_kind == NORMAL_ATTACK_INPUT:
            return self._action_table[ALYOSHA_CHARGED_ATTACK_ACTION_KEY]
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY]
        return None

    # --- 门槛 ---------------------------------------------------------------------

    def _elemental_skill_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
    ) -> str | None:
        """E 长按自动起手复用数据面门槛；端口未接线时不阻断。"""

        return self._ability_gate(context, slot, frame, ELEMENTAL_SKILL_INPUT)
