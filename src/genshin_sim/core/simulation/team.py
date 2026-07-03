from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.actions import ActionDecision, ActionManager, ActionRequest
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.input import InputState, KeyEventDispatch, KeyPhase

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


class TeamSwitchStatus(StrEnum):
    """队伍切换请求的最小结果状态。"""

    SWITCHED = "switched"
    SAME_SLOT = "same_slot"
    INVALID_SLOT = "invalid_slot"


@dataclass(frozen=True, slots=True)
class TeamSwitchResult:
    """一次切换槽位请求的结果。"""

    frame: int
    requested_slot: int
    previous_slot: int
    active_slot: int
    status: TeamSwitchStatus

    @property
    def accepted(self) -> bool:
        return self.status is TeamSwitchStatus.SWITCHED


@dataclass(frozen=True, slots=True)
class ActionButtonInput:
    """送达队伍控制器但尚未解释为具体动作的按钮输入。"""

    frame: int
    key: str
    phase: KeyPhase
    active_slot: int
    held_frames: int | None
    decision: ActionDecision | None = None


@dataclass(slots=True)
class TeamRuntimeState:
    """队伍运行态的最小骨架。

    槽位使用 1-based 编号，与 `keyboard.1` ~ `keyboard.4` 保持一致。
    """

    team_size: int = 4
    active_slot: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.team_size <= 4:
            msg = "team_size must be between 1 and 4"
            raise ValueError(msg)
        if not 1 <= self.active_slot <= self.team_size:
            msg = "active_slot must be within team size"
            raise ValueError(msg)

    def switch_to(self, slot: int, frame: int) -> TeamSwitchResult:
        previous_slot = self.active_slot

        if not 1 <= slot <= self.team_size:
            return TeamSwitchResult(
                frame=frame,
                requested_slot=slot,
                previous_slot=previous_slot,
                active_slot=self.active_slot,
                status=TeamSwitchStatus.INVALID_SLOT,
            )

        if slot == self.active_slot:
            return TeamSwitchResult(
                frame=frame,
                requested_slot=slot,
                previous_slot=previous_slot,
                active_slot=self.active_slot,
                status=TeamSwitchStatus.SAME_SLOT,
            )

        self.active_slot = slot
        return TeamSwitchResult(
            frame=frame,
            requested_slot=slot,
            previous_slot=previous_slot,
            active_slot=self.active_slot,
            status=TeamSwitchStatus.SWITCHED,
        )


class BasicTeamController:
    """第一版队伍控制器骨架。

    当前解释数字键切换槽位，并可把动作按钮输入交给动作管理器决策。
    具体动作、后摇、输入锁定和角色逻辑由后续运行时对象继续处理。
    """

    def __init__(
        self,
        team_state: TeamRuntimeState | None = None,
        *,
        action_manager: ActionManager | None = None,
        switch_recovery_frames: int = 1,
        action_duration_frames: int = 1,
    ) -> None:
        if switch_recovery_frames < 0:
            msg = "switch_recovery_frames must be non-negative"
            raise ValueError(msg)
        if action_duration_frames <= 0:
            msg = "action_duration_frames must be positive"
            raise ValueError(msg)

        self.team_state = team_state or TeamRuntimeState()
        self.action_manager = action_manager
        self.switch_recovery_frames = switch_recovery_frames
        self.action_duration_frames = action_duration_frames
        self._switch_results: list[TeamSwitchResult] = []
        self._action_inputs: list[ActionButtonInput] = []

    @property
    def switch_results(self) -> tuple[TeamSwitchResult, ...]:
        return tuple(self._switch_results)

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

        if dispatch.event.key in ACTION_BUTTON_KEYS:
            decision = self._request_action(context, dispatch)
            self._action_inputs.append(
                ActionButtonInput(
                    frame=dispatch.frame,
                    key=dispatch.event.key,
                    phase=dispatch.event.phase,
                    active_slot=self.team_state.active_slot,
                    held_frames=dispatch.held_frames,
                    decision=decision,
                )
            )

    def _handle_switch_press(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
        slot: int,
    ) -> None:
        result = self.team_state.switch_to(slot, dispatch.frame)
        self._switch_results.append(result)

        if result.accepted:
            if self.action_manager is not None and self.switch_recovery_frames > 0:
                self.action_manager.reserve(
                    frame=dispatch.frame,
                    duration_frames=self.switch_recovery_frames,
                    source="character_switch",
                    active_slot=result.active_slot,
                )
            context.events.publish(
                GameEvent(
                    EventType.AFTER_CHARACTER_SWITCH,
                    frame=dispatch.frame,
                    source=self,
                    data={
                        "previous_slot": result.previous_slot,
                        "active_slot": result.active_slot,
                    },
                )
            )

    def _request_action(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
    ) -> ActionDecision | None:
        if dispatch.event.phase is not KeyPhase.PRESS:
            return None
        if self.action_manager is None:
            return None

        return self.action_manager.request_action(
            context,
            ActionRequest(
                frame=dispatch.frame,
                key=dispatch.event.key,
                active_slot=self.team_state.active_slot,
                duration_frames=self.action_duration_frames,
            )
        )
