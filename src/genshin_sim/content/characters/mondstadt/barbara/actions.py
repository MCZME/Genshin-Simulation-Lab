from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_ACTION_KEY,
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_ELEMENTAL_BURST_ACTION_KEY,
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_JUMP_ACTION_KEY,
    BARBARA_JUMP_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_3_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_3_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_4_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_4_IMPACT_KEY,
    BARBARA_STATE_LAST_ACTION_KEY,
    BARBARA_STATE_LAST_START_FRAME,
)
from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue


class BarbaraInterpreterError(RuntimeError):
    """芭芭拉解释器运行期错误（接线缺失或状态不一致）。"""


NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"


INPUT_KIND_BY_KEY = {
    "mouse.left": NORMAL_ATTACK_INPUT,
    "mouse.right": CHARGED_ATTACK_INPUT,
    "keyboard.e": ELEMENTAL_SKILL_INPUT,
    "keyboard.q": ELEMENTAL_BURST_INPUT,
    "keyboard.space": JUMP_INPUT,
}


@dataclass(frozen=True, slots=True)
class BarbaraActionSpec:
    """芭芭拉动作状态机中的单个动作规格。"""

    action_key: str
    action_kind: str
    hit_frame: int | None
    duration_frames: int
    transitions: Mapping[str, int] = field(default_factory=dict)
    impact_key: str | None = None

    def __post_init__(self) -> None:
        if self.hit_frame is not None and self.hit_frame < 0:
            msg = "hit_frame 必须是非负整数"
            raise ValueError(msg)
        if self.duration_frames <= 0:
            msg = "duration_frames 必须是正整数"
            raise ValueError(msg)
        object.__setattr__(self, "transitions", dict(self.transitions))


BARBARA_NORMAL_ATTACK_ACTION_KEYS = (
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_3_ACTION_KEY,
    BARBARA_NORMAL_ATTACK_4_ACTION_KEY,
)

BARBARA_ACTION_TABLE: dict[str, BarbaraActionSpec] = {
    BARBARA_NORMAL_ATTACK_1_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_1_ACTION_KEY,
        action_kind=NORMAL_ATTACK_INPUT,
        hit_frame=6,
        duration_frames=15,
        impact_key=BARBARA_NORMAL_ATTACK_1_IMPACT_KEY,
        transitions={NORMAL_ATTACK_INPUT: 15, CHARGED_ATTACK_INPUT: 18},
    ),
    BARBARA_NORMAL_ATTACK_2_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_2_ACTION_KEY,
        action_kind=NORMAL_ATTACK_INPUT,
        hit_frame=11,
        duration_frames=21,
        impact_key=BARBARA_NORMAL_ATTACK_2_IMPACT_KEY,
        transitions={NORMAL_ATTACK_INPUT: 21, CHARGED_ATTACK_INPUT: 24},
    ),
    BARBARA_NORMAL_ATTACK_3_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_3_ACTION_KEY,
        action_kind=NORMAL_ATTACK_INPUT,
        hit_frame=12,
        duration_frames=22,
        impact_key=BARBARA_NORMAL_ATTACK_3_IMPACT_KEY,
        transitions={NORMAL_ATTACK_INPUT: 22, CHARGED_ATTACK_INPUT: 28},
    ),
    BARBARA_NORMAL_ATTACK_4_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_NORMAL_ATTACK_4_ACTION_KEY,
        action_kind=NORMAL_ATTACK_INPUT,
        hit_frame=32,
        duration_frames=60,
        impact_key=BARBARA_NORMAL_ATTACK_4_IMPACT_KEY,
        transitions={NORMAL_ATTACK_INPUT: 60},
    ),
    BARBARA_CHARGED_ATTACK_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_CHARGED_ATTACK_ACTION_KEY,
        action_kind=CHARGED_ATTACK_INPUT,
        hit_frame=55,
        duration_frames=56,
        impact_key=BARBARA_CHARGED_ATTACK_IMPACT_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 89,
            CHARGED_ATTACK_INPUT: 88,
            ELEMENTAL_SKILL_INPUT: 88,
            ELEMENTAL_BURST_INPUT: 87,
            JUMP_INPUT: 56,
        },
    ),
    BARBARA_ELEMENTAL_SKILL_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_ELEMENTAL_SKILL_ACTION_KEY,
        action_kind=ELEMENTAL_SKILL_INPUT,
        hit_frame=42,
        duration_frames=5,
        impact_key=BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
        transitions={
            NORMAL_ATTACK_INPUT: 54,
            CHARGED_ATTACK_INPUT: 54,
            ELEMENTAL_SKILL_INPUT: 54,
            ELEMENTAL_BURST_INPUT: 55,
            JUMP_INPUT: 5,
        },
    ),
    BARBARA_ELEMENTAL_BURST_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_ELEMENTAL_BURST_ACTION_KEY,
        action_kind=ELEMENTAL_BURST_INPUT,
        hit_frame=None,
        duration_frames=140,
        transitions={
            NORMAL_ATTACK_INPUT: 141,
            CHARGED_ATTACK_INPUT: 140,
            ELEMENTAL_SKILL_INPUT: 141,
            JUMP_INPUT: 160,
        },
    ),
    BARBARA_JUMP_ACTION_KEY: BarbaraActionSpec(
        action_key=BARBARA_JUMP_ACTION_KEY,
        action_kind=JUMP_INPUT,
        hit_frame=31,
        duration_frames=31,
        impact_key=BARBARA_JUMP_IMPACT_KEY,
        transitions={},
    ),
}


class BarbaraActionInterpreter:
    """按已确认帧表解释芭芭拉动作输入。

    解释器无实例可变字段；上次动作与起始帧从宿主状态容器读取，推进结果经
    ``state_patch`` 意图提交。
    """

    def __init__(
        self,
        *,
        action_table: Mapping[str, BarbaraActionSpec] | None = None,
    ) -> None:
        self._action_table = dict(action_table or BARBARA_ACTION_TABLE)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")

        input_kind = INPUT_KIND_BY_KEY.get(session.key)
        if input_kind is None:
            return ActionInterpretationResult.reject(f"芭芭拉不支持输入：{session.key}")

        if session.owner.slot is None:
            return ActionInterpretationResult.reject("芭芭拉动作需要角色归属槽位")
        owner_ref = f"character:slot_{session.owner.slot}"
        last_action_key, last_action_start_frame = self._read_state(
            cast(SimulationContext, context),
            session.owner.slot,
        )

        transition_rejection = self._transition_rejection(
            input_kind,
            session.release_frame,
            last_action_key,
            last_action_start_frame,
        )
        if transition_rejection is not None:
            return ActionInterpretationResult.reject(transition_rejection)

        action = self._select_action(input_kind, last_action_key)
        self._queue_state_patch(
            cast(SimulationContext, context),
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.release_frame,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(session.owner.slot),
                requested_start_frame=session.current_frame,
                params={
                    "content_handler_key": BARBARA_CHARACTER_HANDLER_KEY,
                    "barbara_action_kind": action.action_kind,
                    "barbara_hit_frame": action.hit_frame,
                },
                source_session_id=session.session_id,
            )
        )

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=BARBARA_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise BarbaraInterpreterError(f"缺少芭芭拉状态挂载：{exc}") from exc
        raw_key = mount.values.get(BARBARA_STATE_LAST_ACTION_KEY)
        last_key = raw_key if isinstance(raw_key, str) else ""
        raw_start = mount.values.get(BARBARA_STATE_LAST_START_FRAME)
        last_start = (
            raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
        )
        return last_key, last_start

    def _queue_state_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        action: BarbaraActionSpec,
        start_frame: int,
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise BarbaraInterpreterError("缺少 IntentQueue，无法提交芭芭拉状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"barbara_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=BARBARA_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=BARBARA_CHARACTER_HANDLER_KEY,
                    fields={
                        BARBARA_STATE_LAST_ACTION_KEY: action.action_key,
                        BARBARA_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )

    def _transition_rejection(
        self,
        input_kind: str,
        frame: int,
        last_action_key: str,
        last_action_start_frame: int,
    ) -> str | None:
        if not last_action_key:
            return None

        previous = self._action_table[last_action_key]
        transition_frame = previous.transitions.get(input_kind)
        if transition_frame is None:
            return f"芭芭拉动作缺少 {previous.action_key} -> {input_kind} 的衔接数据"

        earliest_frame = last_action_start_frame + transition_frame
        if frame < earliest_frame:
            return (
                f"芭芭拉动作 {previous.action_key} -> {input_kind} "
                f"最早可在第 {earliest_frame} 帧衔接"
            )
        return None

    def _select_action(
        self,
        input_kind: str,
        last_action_key: str,
    ) -> BarbaraActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            return self._select_normal_attack_action(last_action_key)
        if input_kind == CHARGED_ATTACK_INPUT:
            return self._action_table[BARBARA_CHARGED_ATTACK_ACTION_KEY]
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[BARBARA_ELEMENTAL_SKILL_ACTION_KEY]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[BARBARA_ELEMENTAL_BURST_ACTION_KEY]
        if input_kind == JUMP_INPUT:
            return self._action_table[BARBARA_JUMP_ACTION_KEY]
        msg = f"未知芭芭拉输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(self, last_action_key: str) -> BarbaraActionSpec:
        if last_action_key not in BARBARA_NORMAL_ATTACK_ACTION_KEYS:
            return self._action_table[BARBARA_NORMAL_ATTACK_1_ACTION_KEY]

        last_index = BARBARA_NORMAL_ATTACK_ACTION_KEYS.index(last_action_key)
        next_index = (last_index + 1) % len(BARBARA_NORMAL_ATTACK_ACTION_KEYS)
        return self._action_table[BARBARA_NORMAL_ATTACK_ACTION_KEYS[next_index]]


def create_barbara_actions(
    action_table: Mapping[str, BarbaraActionSpec] | None = None,
) -> tuple[TimedImpactAction, ...]:
    table = dict(action_table or BARBARA_ACTION_TABLE)
    actions: list[TimedImpactAction] = []
    for action in table.values():
        impact_keys: tuple[str, ...] = ()
        impact_frame_offsets: dict[str, int] = {}
        if action.impact_key is not None and action.hit_frame is not None:
            impact_keys = (action.impact_key,)
            impact_frame_offsets[action.impact_key] = action.hit_frame
        actions.append(
            TimedImpactAction(
                action_key=action.action_key,
                duration_frames=action.duration_frames,
                impact_keys=impact_keys,
                impact_frame_offsets=impact_frame_offsets,
            )
        )
    return tuple(actions)
