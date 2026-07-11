from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from genshin_sim.core.events import EventType, GameEvent, InputKeyConsumedPayload
from genshin_sim.core.protocols import InputSystem
from genshin_sim.core.simulation.context import SimulationContext


class KeyPhase(StrEnum):
    """按键事件阶段。"""

    PRESS = "press"
    RELEASE = "release"


SUPPORTED_INPUT_KEYS = frozenset(
    {
        "keyboard.e",
        "keyboard.q",
        "keyboard.space",
        "keyboard.1",
        "keyboard.2",
        "keyboard.3",
        "keyboard.4",
        "mouse.left",
        "mouse.right",
    }
)


@dataclass(frozen=True, slots=True)
class KeyEvent:
    """单个按键输入事件。"""

    key: str
    phase: KeyPhase


@dataclass(frozen=True, slots=True)
class KeyInputFrame:
    """同一帧内的一组输入事件。"""

    frame: int
    events: tuple[KeyEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class KeyEventDispatch:
    """送达运行时输入处理器的按键事件上下文。"""

    frame: int
    event: KeyEvent
    held_frames: int | None = None


@dataclass(slots=True)
class InputState:
    """当前输入状态。"""

    _pressed_at: dict[str, int] = field(default_factory=dict)

    def is_pressed(self, key: str) -> bool:
        return key in self._pressed_at

    def held_frames(self, key: str, current_frame: int) -> int | None:
        pressed_at = self._pressed_at.get(key)
        if pressed_at is None:
            return None
        return current_frame - pressed_at

    @property
    def pressed_keys(self) -> frozenset[str]:
        return frozenset(self._pressed_at)

    def apply(self, event: KeyEvent, frame: int) -> int | None:
        if event.phase is KeyPhase.PRESS:
            self._pressed_at[event.key] = frame
            return None

        pressed_at = self._pressed_at.pop(event.key)
        return frame - pressed_at


class InputEventHandler(Protocol):
    """输入事件进入运行时控制层的最小协议。"""

    def handle_key_event(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
        state: InputState,
    ) -> None:
        """处理一个已经更新输入状态的按键事件。"""
        ...


class InputTraceError(ValueError):
    """输入轨迹结构或按键生命周期不合法。"""


class TraceInputSystem(InputSystem):
    """按帧消费 `input_trace` 的最小输入系统。"""

    def __init__(
        self,
        input_frames: Iterable[KeyInputFrame],
        handler: InputEventHandler,
    ) -> None:
        self._frames = tuple(input_frames)
        self._validate_trace(self._frames)
        self._handler = handler
        self._state = InputState()
        self._next_index = 0

    @property
    def state(self) -> InputState:
        return self._state

    def process_frame(self, context: SimulationContext, frame: int) -> None:
        while self._next_index < len(self._frames):
            input_frame = self._frames[self._next_index]
            if input_frame.frame > frame:
                return
            if input_frame.frame < frame:
                msg = f"第 {input_frame.frame} 帧输入已错过，当前帧为 {frame}"
                raise InputTraceError(msg)

            for event in input_frame.events:
                held_frames = self._state.apply(event, frame)
                dispatch = KeyEventDispatch(frame=frame, event=event, held_frames=held_frames)
                self._handler.handle_key_event(context, dispatch, self._state)
                self._publish_input_key_consumed(context, dispatch)
            self._next_index += 1

    def is_finished(self) -> bool:
        return self._next_index >= len(self._frames)

    def _publish_input_key_consumed(
        self,
        context: SimulationContext,
        dispatch: KeyEventDispatch,
    ) -> None:
        context.events.publish(
            GameEvent(
                EventType.INPUT_KEY_CONSUMED,
                frame=dispatch.frame,
                source=self,
                payload=InputKeyConsumedPayload(
                    key=dispatch.event.key,
                    phase=dispatch.event.phase.value,
                    held_frames=dispatch.held_frames,
                ),
            )
        )

    @staticmethod
    def _validate_trace(input_frames: Sequence[KeyInputFrame]) -> None:
        previous_frame = -1
        pressed_keys: set[str] = set()

        for input_frame in input_frames:
            if input_frame.frame <= 0:
                msg = "输入帧号必须为正整数"
                raise InputTraceError(msg)
            if input_frame.frame <= previous_frame:
                msg = "输入帧号必须严格递增"
                raise InputTraceError(msg)
            previous_frame = input_frame.frame

            keys_in_frame: set[str] = set()
            for event in input_frame.events:
                if event.key not in SUPPORTED_INPUT_KEYS:
                    msg = f"不支持的输入按键：{event.key}"
                    raise InputTraceError(msg)
                if event.key in keys_in_frame:
                    msg = f"第 {input_frame.frame} 帧存在重复按键：{event.key}"
                    raise InputTraceError(msg)
                keys_in_frame.add(event.key)

                if event.phase is KeyPhase.PRESS:
                    if event.key in pressed_keys:
                        msg = f"按键已经处于按下状态：{event.key}"
                        raise InputTraceError(msg)
                    pressed_keys.add(event.key)
                    continue

                if event.key not in pressed_keys:
                    msg = f"按键在按下前被释放：{event.key}"
                    raise InputTraceError(msg)
                pressed_keys.remove(event.key)

        if pressed_keys:
            keys = ", ".join(sorted(pressed_keys))
            msg = f"输入轨迹结束时仍有按键未释放：{keys}"
            raise InputTraceError(msg)
