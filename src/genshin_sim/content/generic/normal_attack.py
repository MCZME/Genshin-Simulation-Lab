"""generic 普攻连段骨架。

角色包提供 ``NormalAttackChainSpec``（帧表与键），generic 提供连段状态
schema、动作构造工具与无状态解释器。解释器不保存实例可变字段：连段状态
通过 ``state_patch`` 意图提交到宿主状态容器，帧末进入快照。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerKind,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.simulation.intent_queue import IntentQueue

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext

CHAIN_STATE_LAST_ACTION_KEY = "chain_last_action_key"
CHAIN_STATE_LAST_START_FRAME = "chain_last_start_frame"

type ChainOwnerRefBuilder = Callable[[int], str]


class ChainSpecError(Exception):
    """连段规格错误基类。"""


class ChainSpecValidationError(ChainSpecError, ValueError):
    """连段规格不合法。"""


class ChainInterpreterError(ChainSpecError, RuntimeError):
    """连段解释器运行期错误（接线缺失或状态不一致）。"""


@dataclass(frozen=True, slots=True)
class ChainSegmentSpec:
    """连段中的一段动作规格（角色包数据）。"""

    action_key: str
    duration_frames: int
    hit_frame: int | None = None
    impact_key: str | None = None
    transitions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key.strip():
            raise ChainSpecValidationError("action_key 必须是非空字符串")
        if isinstance(self.duration_frames, bool) or self.duration_frames <= 0:
            raise ChainSpecValidationError("duration_frames 必须是正整数")
        if self.hit_frame is not None and (isinstance(self.hit_frame, bool) or self.hit_frame < 0):
            raise ChainSpecValidationError("hit_frame 必须是非负整数")
        if self.impact_key is not None:
            if not isinstance(self.impact_key, str) or not self.impact_key.strip():
                raise ChainSpecValidationError("impact_key 必须是非空字符串")
            if self.hit_frame is None:
                raise ChainSpecValidationError(
                    f"{self.action_key} 提供 impact_key 时必须提供 hit_frame"
                )
            if self.hit_frame >= self.duration_frames:
                raise ChainSpecValidationError(
                    f"{self.action_key} 的 hit_frame 必须小于 duration_frames"
                )
        if self.impact_key is None and self.hit_frame is not None:
            raise ChainSpecValidationError(
                f"{self.action_key} 提供 hit_frame 时必须提供 impact_key"
            )
        transitions = dict(self.transitions)
        for input_kind, frame in transitions.items():
            if not isinstance(input_kind, str) or not input_kind.strip():
                raise ChainSpecValidationError("transitions 键必须是非空字符串")
            if isinstance(frame, bool) or frame < 0:
                raise ChainSpecValidationError(f"{self.action_key} 的衔接帧不能为负数")
        object.__setattr__(self, "transitions", transitions)


type ChainSegmentSelector = Callable[
    [str | None, tuple[ChainSegmentSpec, ...]],
    ChainSegmentSpec,
]


@dataclass(frozen=True, slots=True)
class NormalAttackChainSpec:
    """角色包提供的普攻连段规格（内容包数据，含内容级键）。"""

    chain_key: str
    segments: Sequence[ChainSegmentSpec]
    input_key: str = "mouse.left"
    input_kind: str = "normal_attack"

    def __post_init__(self) -> None:
        if not isinstance(self.chain_key, str) or not self.chain_key.strip():
            raise ChainSpecValidationError("chain_key 必须是非空字符串")
        if not isinstance(self.input_key, str) or not self.input_key.strip():
            raise ChainSpecValidationError("input_key 必须是非空字符串")
        if not isinstance(self.input_kind, str) or not self.input_kind.strip():
            raise ChainSpecValidationError("input_kind 必须是非空字符串")
        segments = tuple(self.segments)
        if not segments:
            raise ChainSpecValidationError("连段至少需要一个 segment")
        keys = [segment.action_key for segment in segments]
        if len(keys) != len(set(keys)):
            raise ChainSpecValidationError("连段 segment 的 action_key 不能重复")
        object.__setattr__(self, "segments", segments)


def chain_state_schema(owner_ref: str) -> StateSchema:
    """构造连段宿主状态 schema（generic 形状，owner 由内容包传入）。"""

    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            StateField(
                name=CHAIN_STATE_LAST_ACTION_KEY,
                field_type=StateFieldType.STRING,
                default="",
            ),
            StateField(
                name=CHAIN_STATE_LAST_START_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
        ),
    )


def build_chain_actions(spec: NormalAttackChainSpec) -> tuple[TimedImpactAction, ...]:
    """把连段规格编译为可注册的定时动作。"""

    actions: list[TimedImpactAction] = []
    for segment in spec.segments:
        impact_keys: tuple[str, ...] = ()
        impact_frame_offsets: dict[str, int] = {}
        if segment.impact_key is not None and segment.hit_frame is not None:
            impact_keys = (segment.impact_key,)
            impact_frame_offsets[segment.impact_key] = segment.hit_frame
        actions.append(
            TimedImpactAction(
                action_key=segment.action_key,
                duration_frames=segment.duration_frames,
                impact_keys=impact_keys,
                impact_frame_offsets=impact_frame_offsets,
            )
        )
    return tuple(actions)


class ChainActionInterpreter:
    """无状态连段解释器。

    解释器本身没有可变字段；连段进度读写宿主状态容器（读为已提交状态，
    写走 ``state_patch`` 意图）。容器与意图队列通过仿真上下文协作对象获取。
    """

    def __init__(
        self,
        spec: NormalAttackChainSpec,
        *,
        owner_ref_builder: ChainOwnerRefBuilder | None = None,
        segment_selector: ChainSegmentSelector | None = None,
        state_key: str | None = None,
    ) -> None:
        self.spec = spec
        self._owner_ref_builder = owner_ref_builder or (lambda slot: f"character:slot_{slot}")
        self._segment_selector = segment_selector
        self._state_key = state_key or spec.chain_key

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(segment.action_key for segment in self.spec.segments)

    def interpret(
        self,
        context: SimulationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is ActionInterpretationTrigger.HOLD:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        if session.key != self.spec.input_key:
            return ActionInterpretationResult.reject(
                f"连段 {self.spec.chain_key} 不支持输入：{session.key}"
            )
        if session.owner.kind is not ActionOwnerKind.CHARACTER or session.owner.slot is None:
            return ActionInterpretationResult.reject("连段解释器需要角色归属槽位")

        slot = session.owner.slot
        owner_ref = self._owner_ref_builder(slot)
        state = self._read_chain_state(context, slot)
        raw_last_key = state.get(CHAIN_STATE_LAST_ACTION_KEY)
        last_key = raw_last_key if isinstance(raw_last_key, str) else ""
        raw_last_start = state.get(CHAIN_STATE_LAST_START_FRAME)
        last_start_frame = (
            raw_last_start
            if isinstance(raw_last_start, int) and not isinstance(raw_last_start, bool)
            else 0
        )

        rejection = self._transition_rejection(last_key, last_start_frame, session.release_frame)
        if rejection is not None:
            return ActionInterpretationResult.reject(rejection)

        next_segment = self._select_segment(last_key)
        self._queue_state_patch(
            context,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action_key=next_segment.action_key,
            start_frame=session.release_frame,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=next_segment.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params={
                    "chain_key": self.spec.chain_key,
                    "chain_segment_action_key": next_segment.action_key,
                },
                source_session_id=session.session_id,
            )
        )

    def _read_chain_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> Mapping[str, object]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=self._state_key,
            )
        except StateContainerNotFoundError as exc:
            raise ChainInterpreterError(f"缺少连段状态挂载：{exc}") from exc
        return mount.values

    def _transition_rejection(
        self,
        last_key: str,
        last_start_frame: int,
        release_frame: int,
    ) -> str | None:
        if not last_key:
            return None
        last_segment = self._segment_by_action_key(last_key)
        if last_segment is None:
            return None
        transition_frame = last_segment.transitions.get(self.spec.input_kind)
        if transition_frame is None:
            return (
                f"连段 {self.spec.chain_key} 缺少 "
                f"{last_segment.action_key} -> {self.spec.input_kind} 的衔接数据"
            )
        earliest_frame = last_start_frame + transition_frame
        if release_frame < earliest_frame:
            return (
                f"连段 {self.spec.chain_key} {last_segment.action_key} -> "
                f"{self.spec.input_kind} 最早可在第 {earliest_frame} 帧衔接"
            )
        return None

    def _select_segment(self, last_key: str) -> ChainSegmentSpec:
        if self._segment_selector is not None:
            selected = self._segment_selector(last_key or None, tuple(self.spec.segments))
            if not isinstance(selected, ChainSegmentSpec):
                raise ChainInterpreterError("segment_selector 必须返回 ChainSegmentSpec")
            return selected
        if not last_key:
            return self.spec.segments[0]
        last_segment = self._segment_by_action_key(last_key)
        if last_segment is None:
            return self.spec.segments[0]
        keys = tuple(segment.action_key for segment in self.spec.segments)
        next_index = (keys.index(last_key) + 1) % len(keys)
        return self.spec.segments[next_index]

    def _segment_by_action_key(self, action_key: str) -> ChainSegmentSpec | None:
        for segment in self.spec.segments:
            if segment.action_key == action_key:
                return segment
        return None

    def _queue_state_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        action_key: str,
        start_frame: int,
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise ChainInterpreterError("缺少 IntentQueue，无法提交连段状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"chain_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=self.spec.chain_key,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=self._state_key,
                    fields={
                        CHAIN_STATE_LAST_ACTION_KEY: action_key,
                        CHAIN_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )
