from __future__ import annotations

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_ACTION_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)


class RuntimeProbeActionInterpreter:
    """把一次按下/释放输入转换为一条测试 Action。"""

    supported_action_keys = (RUNTIME_PROBE_ACTION_KEY,)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")

        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=RUNTIME_PROBE_ACTION_KEY,
                owner=ActionOwnerRef.character(session.owner.slot or 1),
                requested_start_frame=session.current_frame,
                params={"content_handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY},
                source_session_id=session.session_id,
            )
        )


def create_runtime_probe_action(*, duration_frames: int = 1) -> TimedImpactAction:
    return TimedImpactAction(
        action_key=RUNTIME_PROBE_ACTION_KEY,
        duration_frames=duration_frames,
        impact_keys=(RUNTIME_PROBE_IMPACT_KEY,),
    )
