from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.actions.manager import (
    TEAM_SWITCH_ACTION_KEY,
    TEAM_SWITCH_TARGET_SLOT_PARAM,
    ActionDecision,
    ActionManager,
    ActionTimelineSpec,
)
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.input import InputState, KeyEventDispatch, KeyPhase
from genshin_sim.core.space import ACTIVE_CHARACTER_ENTITY_ID

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


SWITCH_KEY_TO_SLOT = {
    "keyboard.1": 1,
    "keyboard.2": 2,
    "keyboard.3": 3,
    "keyboard.4": 4,
}

ACTION_BUTTON_KEYS = frozenset(
    {
        "keyboard.e",
        "keyboard.q",
        "keyboard.space",
        "mouse.left",
        "mouse.right",
    }
)


class InputActionSessionState(StrEnum):
    """动作输入会话的最小状态集合。"""

    PENDING = "pending"
    DEFERRED = "deferred"
    SCHEDULED = "scheduled"
    CANCELED = "canceled"
    RELEASED = "released"
    IGNORED = "ignored"


class ActionInterpretationTrigger(StrEnum):
    """触发角色动作解释器的原因。"""

    PRESS = "press"
    RELEASE = "release"


class ActionInterpretationKind(StrEnum):
    """角色动作解释器的最小返回类型。"""

    DEFER = "defer"
    REJECT = "reject"
    SCHEDULE_TIMELINE = "schedule_timeline"
    CANCEL_SESSION = "cancel_session"


@dataclass(slots=True)
class InputActionSession:
    """一个动作按钮从 press 到 release 的队伍级输入会话。"""

    session_id: int
    key: str
    owner_slot_at_press: int
    press_frame: int
    release_frame: int | None = None
    held_frames: int | None = None
    state: InputActionSessionState = InputActionSessionState.PENDING
    decision: ActionDecision | None = None
    cancel_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ActionInterpretation:
    """角色动作解释器返回给队伍控制器的通用结果。"""

    kind: ActionInterpretationKind
    timeline: ActionTimelineSpec | None = None
    reason: str | None = None

    @classmethod
    def defer(cls) -> ActionInterpretation:
        return cls(ActionInterpretationKind.DEFER)

    @classmethod
    def schedule(cls, timeline: ActionTimelineSpec) -> ActionInterpretation:
        return cls(ActionInterpretationKind.SCHEDULE_TIMELINE, timeline=timeline)

    @classmethod
    def reject(cls, reason: str) -> ActionInterpretation:
        return cls(ActionInterpretationKind.REJECT, reason=reason)

    @classmethod
    def cancel(cls, reason: str) -> ActionInterpretation:
        return cls(ActionInterpretationKind.CANCEL_SESSION, reason=reason)


class CharacterActionInterpreter(Protocol):
    """角色内容提供的动作解释器协议。"""

    def interpret(
        self,
        context: SimulationContext,
        session: InputActionSession,
        trigger: ActionInterpretationTrigger,
    ) -> ActionInterpretation:
        """解释一个输入会话。"""
        ...


class ActiveSlotProvider(Protocol):
    """当前场上槽位的只读提供者。"""

    @property
    def active_slot(self) -> int:
        """当前场上角色槽位。"""
        ...


class ReleaseActionInterpreter:
    """测试与最小闭环使用的默认解释器。

    press 只保留输入会话；release 时生成一个最小动作时间轴。
    """

    def __init__(self, *, action_duration_frames: int = 1) -> None:
        if action_duration_frames <= 0:
            msg = "动作持续帧数必须为正整数"
            raise ValueError(msg)
        self.action_duration_frames = action_duration_frames

    def interpret(
        self,
        context: SimulationContext,
        session: InputActionSession,
        trigger: ActionInterpretationTrigger,
    ) -> ActionInterpretation:
        del context
        if trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretation.defer()

        start_frame = session.release_frame
        if start_frame is None:
            return ActionInterpretation.reject("release frame is missing")
        return ActionInterpretation.schedule(
            ActionTimelineSpec(
                action_key=session.key,
                source_key=session.key,
                owner_slot=session.owner_slot_at_press,
                start_frame=start_frame,
                duration_frames=self.action_duration_frames,
            )
        )


@dataclass(frozen=True, slots=True)
class ActionButtonInput:
    """动作按钮输入审计记录。"""

    frame: int
    key: str
    phase: KeyPhase
    active_slot: int
    owner_slot_at_press: int | None
    held_frames: int | None
    session_id: int | None
    decision: ActionDecision | None = None


@dataclass(frozen=True, slots=True)
class SwitchInput:
    """切人按钮输入审计记录。"""

    frame: int
    key: str
    phase: KeyPhase
    active_slot: int
    requested_slot: int
    decision: ActionDecision | None = None


class TeamActionController(FrameUpdatable):
    """队伍级输入路由器。

    它拥有输入会话和切人协调逻辑，动作管理器只接收解释完成的时间轴。
    """

    def __init__(
        self,
        active_slot_provider: ActiveSlotProvider,
        action_manager: ActionManager,
        *,
        interpreters: dict[int, CharacterActionInterpreter] | None = None,
        default_interpreter: CharacterActionInterpreter | None = None,
        switch_recovery_frames: int = 1,
    ) -> None:
        if switch_recovery_frames <= 0:
            msg = "切人恢复帧数必须为正整数"
            raise ValueError(msg)

        self.active_slot_provider = active_slot_provider
        self.action_manager = action_manager
        self.switch_recovery_frames = switch_recovery_frames
        self._interpreters = dict(interpreters or {})
        self._default_interpreter = default_interpreter or ReleaseActionInterpreter()
        self._sessions: list[InputActionSession] = []
        self._active_sessions_by_key: dict[str, InputActionSession] = {}
        self._switch_inputs: list[SwitchInput] = []
        self._action_inputs: list[ActionButtonInput] = []
        self._current_frame = 0
        self._next_session_id = 1

    @property
    def sessions(self) -> tuple[InputActionSession, ...]:
        return tuple(self._sessions)

    @property
    def switch_inputs(self) -> tuple[SwitchInput, ...]:
        return tuple(self._switch_inputs)

    @property
    def action_inputs(self) -> tuple[ActionButtonInput, ...]:
        return tuple(self._action_inputs)

    def handle_key_event(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
        state: InputState,
    ) -> None:
        del state

        switch_slot = SWITCH_KEY_TO_SLOT.get(dispatch.event.key)
        if switch_slot is not None:
            if dispatch.event.phase is KeyPhase.PRESS:
                self._handle_switch_press(context, dispatch, switch_slot)
            return

        if dispatch.event.key not in ACTION_BUTTON_KEYS:
            return

        if dispatch.event.phase is KeyPhase.PRESS:
            self._handle_action_press(context, dispatch)
            return

        self._handle_action_release(context, dispatch)

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        del context
        self._current_frame = frame

    def is_idle(self) -> bool:
        return all(
            session.state
            not in {
                InputActionSessionState.PENDING,
                InputActionSessionState.DEFERRED,
            }
            for session in self._sessions
        )

    def _handle_switch_press(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
        slot: int,
    ) -> None:
        active_slot = self.active_slot_provider.active_slot
        timeline = ActionTimelineSpec(
            action_key=TEAM_SWITCH_ACTION_KEY,
            source_key=dispatch.event.key,
            owner_slot=active_slot,
            start_frame=dispatch.frame,
            duration_frames=self.switch_recovery_frames,
            actor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
            params={TEAM_SWITCH_TARGET_SLOT_PARAM: slot},
        )
        decision = self.action_manager.schedule_timeline(context, timeline)
        self._switch_inputs.append(
            SwitchInput(
                frame=dispatch.frame,
                key=dispatch.event.key,
                phase=dispatch.event.phase,
                active_slot=active_slot,
                requested_slot=slot,
                decision=decision,
            )
        )

    def _handle_action_press(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
    ) -> None:
        if self.action_manager.is_busy(dispatch.frame):
            timeline = ActionTimelineSpec(
                action_key=dispatch.event.key,
                source_key=dispatch.event.key,
                owner_slot=self.active_slot_provider.active_slot,
                start_frame=dispatch.frame,
            )
            decision = self.action_manager.schedule_timeline(context, timeline)
            self._action_inputs.append(
                ActionButtonInput(
                    frame=dispatch.frame,
                    key=dispatch.event.key,
                    phase=dispatch.event.phase,
                    active_slot=self.active_slot_provider.active_slot,
                    owner_slot_at_press=None,
                    held_frames=dispatch.held_frames,
                    session_id=None,
                    decision=decision,
                )
            )
            return

        session = InputActionSession(
            session_id=self._next_session_id,
            key=dispatch.event.key,
            owner_slot_at_press=self.active_slot_provider.active_slot,
            press_frame=dispatch.frame,
        )
        self._next_session_id += 1
        self._sessions.append(session)
        self._active_sessions_by_key[session.key] = session

        interpretation = self._interpreter_for(session.owner_slot_at_press).interpret(
            context,
            session,
            ActionInterpretationTrigger.PRESS,
        )
        decision = self._apply_interpretation(context, session, interpretation)
        self._record_action_input(dispatch, session, decision)

    def _handle_action_release(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
    ) -> None:
        session = self._active_sessions_by_key.pop(dispatch.event.key, None)
        if session is None:
            self._action_inputs.append(
                ActionButtonInput(
                    frame=dispatch.frame,
                    key=dispatch.event.key,
                    phase=dispatch.event.phase,
                    active_slot=self.active_slot_provider.active_slot,
                    owner_slot_at_press=None,
                    held_frames=dispatch.held_frames,
                    session_id=None,
                )
            )
            return

        session.release_frame = dispatch.frame
        session.held_frames = dispatch.held_frames
        if session.state is InputActionSessionState.CANCELED:
            self._record_action_input(dispatch, session, None)
            return

        interpretation = self._interpreter_for(session.owner_slot_at_press).interpret(
            context,
            session,
            ActionInterpretationTrigger.RELEASE,
        )
        decision = self._apply_interpretation(context, session, interpretation)
        if session.state is not InputActionSessionState.SCHEDULED:
            session.state = InputActionSessionState.RELEASED
        self._record_action_input(dispatch, session, decision)

    def _apply_interpretation(
        self,
        context: SimulationContext,
        session: InputActionSession,
        interpretation: ActionInterpretation,
    ) -> ActionDecision | None:
        if interpretation.kind is ActionInterpretationKind.DEFER:
            session.state = InputActionSessionState.DEFERRED
            return None

        if interpretation.kind is ActionInterpretationKind.CANCEL_SESSION:
            session.state = InputActionSessionState.CANCELED
            session.cancel_reason = interpretation.reason
            return None

        if interpretation.kind is ActionInterpretationKind.REJECT:
            session.state = InputActionSessionState.IGNORED
            session.cancel_reason = interpretation.reason
            return None

        if interpretation.timeline is None:
            session.state = InputActionSessionState.IGNORED
            session.cancel_reason = "missing timeline"
            return None

        decision = self.action_manager.schedule_timeline(context, interpretation.timeline)
        session.decision = decision
        session.state = (
            InputActionSessionState.SCHEDULED
            if decision.accepted
            else InputActionSessionState.IGNORED
        )
        return decision

    def _record_action_input(
        self,
        dispatch: KeyEventDispatch,
        session: InputActionSession,
        decision: ActionDecision | None,
    ) -> None:
        self._action_inputs.append(
            ActionButtonInput(
                frame=dispatch.frame,
                key=dispatch.event.key,
                phase=dispatch.event.phase,
                active_slot=self.active_slot_provider.active_slot,
                owner_slot_at_press=session.owner_slot_at_press,
                held_frames=dispatch.held_frames,
                session_id=session.session_id,
                decision=decision,
            )
        )

    def cancel_pending_sessions_for_slot(self, slot: int, *, reason: str) -> None:
        for key, session in tuple(self._active_sessions_by_key.items()):
            if session.owner_slot_at_press != slot:
                continue
            if session.state not in {
                InputActionSessionState.PENDING,
                InputActionSessionState.DEFERRED,
            }:
                continue
            session.state = InputActionSessionState.CANCELED
            session.cancel_reason = reason
            self._active_sessions_by_key.pop(key, None)

    def _interpreter_for(self, slot: int) -> CharacterActionInterpreter:
        return self._interpreters.get(slot, self._default_interpreter)
