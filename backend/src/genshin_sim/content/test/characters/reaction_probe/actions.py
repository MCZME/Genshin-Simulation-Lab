"""反应探针动作：把一次按键释放转换为带元素参数的直伤动作。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TargetingSpec,
    TimedImpactAction,
)
from genshin_sim.core.elements import Element


class ReactionProbeActionInterpreter:
    """把一次释放转换为对应按键元素的探针动作。"""

    def __init__(
        self,
        *,
        handler_key: str,
        action_key: str,
        element_by_key: Mapping[str, Element],
        display_name_by_key: Mapping[str, str],
    ) -> None:
        self._handler_key = handler_key
        self._action_key = action_key
        self._element_by_key = dict(element_by_key)
        self._display_name_by_key = dict(display_name_by_key)
        self.supported_action_keys = (action_key,)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        element = self._element_by_key.get(session.key)
        if element is None:
            return ActionInterpretationResult.reject(f"探针未映射按键 {session.key}")

        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=self._action_key,
                owner=ActionOwnerRef.character(session.owner.slot or 1),
                requested_start_frame=session.current_frame,
                params={
                    "content_handler_key": self._handler_key,
                    "probe_element": element.value,
                    "probe_display_name": self._display_name_by_key.get(session.key),
                },
                source_session_id=session.session_id,
            )
        )


def create_probe_action(
    action_key: str,
    impact_keys: tuple[str, ...],
    *,
    duration_frames: int = 1,
) -> TimedImpactAction:
    return TimedImpactAction(
        action_key=action_key,
        duration_frames=duration_frames,
        impact_keys=impact_keys,
        targeting=TargetingSpec(radius=1.0),
    )
