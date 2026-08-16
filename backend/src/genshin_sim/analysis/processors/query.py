"""状态查询与事件查询执行器。

查询是 analysis 读取侧的通用能力：给定查询条件（运行、帧、路径、过滤），
返回"定位信息 + 值"的结果集合。执行器通过 ``RunReader`` 读取结果库数据，
不依赖 application 或 SQLite 具体实现。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from genshin_sim.analysis.processors.paths import (
    StatePathError,
    parse_state_path,
    resolve_state_path,
)
from genshin_sim.analysis.processors.state_fold import (
    RecordedEventLike,
    fold_state,
)


class QueryValidationError(ValueError):
    """查询条件非法。"""


class RunDetailLike(Protocol):
    """结果库运行详情的读取形状。"""

    @property
    def initial_snapshot(self) -> Mapping[str, object] | None: ...

    @property
    def events(self) -> Sequence[RecordedEventLike]: ...


class RunReader(Protocol):
    """analysis 读取结果库运行数据的窄协议。"""

    def get_run(self, session_id: str) -> RunDetailLike: ...


@dataclass(frozen=True, slots=True)
class StateQuery:
    """状态查询：按运行、帧、路径定位状态数据。"""

    session_ids: tuple[str, ...]
    frames: tuple[int, ...]
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.session_ids:
            raise QueryValidationError("session_ids 不能为空")
        if not self.frames:
            raise QueryValidationError("frames 不能为空")
        if not self.paths:
            raise QueryValidationError("paths 不能为空")
        for frame in self.frames:
            if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
                raise QueryValidationError("frames 必须是非负整数")
        for path in self.paths:
            parse_state_path(path)


@dataclass(frozen=True, slots=True)
class EventQuery:
    """事件查询：按事件类型、帧范围、载荷路径与等值过滤定位事件数据。"""

    session_id: str
    event_types: tuple[str, ...]
    frame_min: int | None = None
    frame_max: int | None = None
    payload_path: str | None = None
    filters: tuple[tuple[str, str], ...] = ()
    offset: int = 0
    limit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise QueryValidationError("session_id 必须是非空字符串")
        if not self.event_types:
            raise QueryValidationError("event_types 不能为空")
        if self.frame_min is not None and (
            isinstance(self.frame_min, bool)
            or not isinstance(self.frame_min, int)
            or self.frame_min < 0
        ):
            raise QueryValidationError("frame_min 必须是非负整数")
        if self.frame_max is not None and (
            isinstance(self.frame_max, bool)
            or not isinstance(self.frame_max, int)
            or self.frame_max < 0
        ):
            raise QueryValidationError("frame_max 必须是非负整数")
        if (
            self.frame_min is not None
            and self.frame_max is not None
            and self.frame_max < self.frame_min
        ):
            raise QueryValidationError("frame_max 不能小于 frame_min")
        if self.payload_path is not None:
            parse_state_path(self.payload_path)
        for path, expected in self.filters:
            parse_state_path(path)
            if not isinstance(expected, str):
                raise QueryValidationError("过滤期望值必须是字符串")
        if isinstance(self.offset, bool) or not isinstance(self.offset, int) or self.offset < 0:
            raise QueryValidationError("offset 必须是非负整数")
        if self.limit is not None and (
            isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0
        ):
            raise QueryValidationError("limit 必须是正整数或 None")


@dataclass(frozen=True, slots=True)
class StateQueryResult:
    """状态查询结果：定位信息 + 值。"""

    session_id: str
    frame: int
    path: str
    value: object

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "frame": self.frame,
            "path": self.path,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class EventQueryResult:
    """事件查询结果：定位信息 + 值。"""

    session_id: str
    ordinal: int
    frame: int
    event_type: str
    path: str | None
    value: object

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "ordinal": self.ordinal,
            "frame": self.frame,
            "event_type": self.event_type,
            "path": self.path,
            "value": self.value,
        }


def query_state(
    reader: RunReader,
    query: StateQuery,
) -> tuple[StateQueryResult, ...]:
    """执行状态查询：每个 (session, frame, path) 独立解析。"""

    results: list[StateQueryResult] = []
    for session_id in query.session_ids:
        run = reader.get_run(session_id)
        for frame in query.frames:
            view = fold_state(run.initial_snapshot, run.events, frame)
            providers = cast(dict[str, object], view.providers)
            for path in query.paths:
                results.append(
                    StateQueryResult(
                        session_id=session_id,
                        frame=frame,
                        path=path,
                        value=resolve_state_path(providers, path),
                    )
                )
    return tuple(results)


def query_events(
    reader: RunReader,
    query: EventQuery,
) -> tuple[EventQueryResult, ...]:
    """执行事件查询：类型/帧范围/等值过滤后按路径取值并分页。"""

    run = reader.get_run(query.session_id)
    matched: list[EventQueryResult] = []
    for ordinal, event in enumerate(run.events):
        if event.event_type not in query.event_types:
            continue
        if query.frame_min is not None and event.frame < query.frame_min:
            continue
        if query.frame_max is not None and event.frame > query.frame_max:
            continue
        if not all(
            _payload_matches(event.data, path, expected) for path, expected in query.filters
        ):
            continue
        value: object = event.data
        if query.payload_path is not None:
            value = resolve_state_path(event.data, query.payload_path)
        matched.append(
            EventQueryResult(
                session_id=query.session_id,
                ordinal=ordinal,
                frame=event.frame,
                event_type=event.event_type,
                path=query.payload_path,
                value=value,
            )
        )
    if query.limit is None:
        return tuple(matched[query.offset :])
    return tuple(matched[query.offset : query.offset + query.limit])


def _payload_matches(payload: Mapping[str, object], path: str, expected: str) -> bool:
    try:
        actual = resolve_state_path(payload, path)
    except StatePathError:
        return False
    return actual == expected or str(actual) == expected
