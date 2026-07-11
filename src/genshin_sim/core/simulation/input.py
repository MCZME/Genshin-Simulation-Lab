from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class KeyPhase(StrEnum):
    """按键事实阶段。"""

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
    """单个按键输入事实。"""

    key: str
    phase: KeyPhase


@dataclass(frozen=True, slots=True)
class KeyInputFrame:
    """同一帧内的一组输入事实。"""

    frame: int
    events: tuple[KeyEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class InputSessionPlan:
    """一次 press/release 配对后的不可变输入会话计划。"""

    session_id: int
    key: str
    press_frame: int
    release_frame: int
    press_order: int
    release_order: int
    held_frames: int


@dataclass(frozen=True, slots=True)
class InputSessionBoundary:
    """ActionManager 按帧读取的输入会话边界。"""

    frame: int
    order: int
    session_id: int
    phase: KeyPhase


@dataclass(frozen=True, slots=True)
class InputSessionTrace:
    """组装期编译出的输入会话计划与边界索引。"""

    sessions: tuple[InputSessionPlan, ...]
    boundaries: tuple[InputSessionBoundary, ...]
    _sessions_by_id: Mapping[int, InputSessionPlan]
    _boundaries_by_frame: Mapping[int, tuple[InputSessionBoundary, ...]]

    @classmethod
    def from_parts(
        cls,
        sessions: Iterable[InputSessionPlan],
        boundaries: Iterable[InputSessionBoundary],
    ) -> InputSessionTrace:
        session_tuple = tuple(sessions)
        boundary_tuple = tuple(sorted(boundaries, key=lambda item: (item.frame, item.order)))
        sessions_by_id = {session.session_id: session for session in session_tuple}
        boundaries_by_frame: dict[int, list[InputSessionBoundary]] = defaultdict(list)
        for boundary in boundary_tuple:
            boundaries_by_frame[boundary.frame].append(boundary)
        return cls(
            sessions=session_tuple,
            boundaries=boundary_tuple,
            _sessions_by_id=sessions_by_id,
            _boundaries_by_frame={
                frame: tuple(items) for frame, items in boundaries_by_frame.items()
            },
        )

    def get_session(self, session_id: int) -> InputSessionPlan:
        try:
            return self._sessions_by_id[session_id]
        except KeyError as exc:
            msg = f"未知输入会话 id：{session_id}"
            raise KeyError(msg) from exc

    def boundaries_at(self, frame: int) -> tuple[InputSessionBoundary, ...]:
        return self._boundaries_by_frame.get(frame, ())

    def has_pending_after(self, frame: int) -> bool:
        return any(boundary.frame > frame for boundary in self.boundaries)


class InputTraceError(ValueError):
    """输入轨迹结构或按键生命周期不合法。"""


class InputTraceCompiler:
    """把配置中的按键事实编译为不可变输入会话计划。"""

    def compile(self, input_frames: Iterable[KeyInputFrame]) -> InputSessionTrace:
        frames = tuple(input_frames)
        self._validate_frame_order(frames)

        next_session_id = 1
        pressed: dict[str, tuple[int, int, int]] = {}
        sessions: list[InputSessionPlan] = []
        boundaries: list[InputSessionBoundary] = []

        for input_frame in frames:
            keys_in_frame: set[str] = set()
            for order, event in enumerate(input_frame.events):
                self._validate_event(input_frame.frame, event, keys_in_frame)
                keys_in_frame.add(event.key)

                if event.phase is KeyPhase.PRESS:
                    if event.key in pressed:
                        msg = f"按键已经处于按下状态：{event.key}"
                        raise InputTraceError(msg)
                    session_id = next_session_id
                    next_session_id += 1
                    pressed[event.key] = (session_id, input_frame.frame, order)
                    boundaries.append(
                        InputSessionBoundary(
                            frame=input_frame.frame,
                            order=order,
                            session_id=session_id,
                            phase=KeyPhase.PRESS,
                        )
                    )
                    continue

                if event.key not in pressed:
                    msg = f"按键在按下前被释放：{event.key}"
                    raise InputTraceError(msg)
                session_id, press_frame, press_order = pressed.pop(event.key)
                sessions.append(
                    InputSessionPlan(
                        session_id=session_id,
                        key=event.key,
                        press_frame=press_frame,
                        release_frame=input_frame.frame,
                        press_order=press_order,
                        release_order=order,
                        held_frames=input_frame.frame - press_frame,
                    )
                )
                boundaries.append(
                    InputSessionBoundary(
                        frame=input_frame.frame,
                        order=order,
                        session_id=session_id,
                        phase=KeyPhase.RELEASE,
                    )
                )

        if pressed:
            keys = ", ".join(sorted(pressed))
            msg = f"输入轨迹结束时仍有按键未释放：{keys}"
            raise InputTraceError(msg)

        return InputSessionTrace.from_parts(
            sorted(sessions, key=lambda item: item.session_id),
            boundaries,
        )

    @staticmethod
    def _validate_frame_order(input_frames: Sequence[KeyInputFrame]) -> None:
        previous_frame = -1
        for input_frame in input_frames:
            if input_frame.frame <= 0:
                msg = "输入帧号必须为正整数"
                raise InputTraceError(msg)
            if input_frame.frame <= previous_frame:
                msg = "输入帧号必须严格递增"
                raise InputTraceError(msg)
            if not input_frame.events:
                msg = f"第 {input_frame.frame} 帧必须至少包含一个输入事件"
                raise InputTraceError(msg)
            previous_frame = input_frame.frame

    @staticmethod
    def _validate_event(frame: int, event: KeyEvent, keys_in_frame: set[str]) -> None:
        if event.key not in SUPPORTED_INPUT_KEYS:
            msg = f"不支持的输入按键：{event.key}"
            raise InputTraceError(msg)
        if event.key in keys_in_frame:
            msg = f"第 {frame} 帧存在重复按键：{event.key}"
            raise InputTraceError(msg)
