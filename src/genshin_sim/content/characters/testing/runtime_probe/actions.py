from __future__ import annotations

from typing import TYPE_CHECKING

from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_ACTION_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
    RUNTIME_PROBE_IMPACT_KEY,
)
from genshin_sim.core.actions import (
    ActionInterpretation,
    ActionInterpretationTrigger,
    ActionTimelineSpec,
)

if TYPE_CHECKING:
    from genshin_sim.core.actions import InputActionSession
    from genshin_sim.core.simulation import SimulationContext


class RuntimeProbeActionInterpreter:
    """把一次按下/释放输入转换为一条时间轴的测试解释器。"""

    def __init__(self, *, duration_frames: int = 1) -> None:
        if duration_frames <= 0:
            raise ValueError("duration_frames 必须是正整数")
        self.duration_frames = duration_frames

    def interpret(
        self,
        context: SimulationContext,
        session: InputActionSession,
        trigger: ActionInterpretationTrigger,
    ) -> ActionInterpretation:
        del context
        if trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretation.defer()

        if session.release_frame is None:
            return ActionInterpretation.reject("缺少释放帧")

        return ActionInterpretation.schedule(
            ActionTimelineSpec(
                action_key=RUNTIME_PROBE_ACTION_KEY,
                source_key=session.key,
                owner_slot=session.owner_slot_at_press,
                start_frame=session.release_frame,
                duration_frames=self.duration_frames,
                impact_keys=(RUNTIME_PROBE_IMPACT_KEY,),
                params={"content_handler_key": RUNTIME_PROBE_CHARACTER_HANDLER_KEY},
            )
        )
