"""状态树与事件载荷的路径取值。

路径由点分隔的段组成，支持三种段：

- 标识符：``team``、``current_hp``，按字典键取值。
- 引号键：``["character:slot_1"]``、``["stat.atk.total"]``，用于包含特殊
  字符（冒号、点）的字典键。
- 筛选：``characters[slot=1]``，在列表上按键值匹配；作为路径终点时返回
  全部匹配项，路径继续时要求恰好一个匹配。

示例：

``team.characters[slot=1].current_hp``
``attributes["character:slot_1"]["stat.atk.total"]``
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

_SEGMENT_PATTERN = re.compile(
    r"^(?:(?P<name>[A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\[(?P<bracket>[^\[\]]*)\])?$"
)
_FILTER_PATTERN = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.+)$")


class StatePathError(RuntimeError):
    """路径解析或取值错误基类。"""


@dataclass(frozen=True, slots=True)
class KeyAccess:
    """按字典键取值。"""

    key: str


@dataclass(frozen=True, slots=True)
class FilterAccess:
    """在列表上按键值筛选。"""

    key: str
    value: object


PathSegment = KeyAccess | FilterAccess


def parse_state_path(path: str) -> tuple[PathSegment, ...]:
    """解析路径字符串为取值段序列。"""

    if not isinstance(path, str) or not path.strip():
        raise StatePathError("路径必须是非空字符串")
    raw_segments = _split_segments(path)
    if not raw_segments or any(not segment for segment in raw_segments):
        raise StatePathError(f"非法路径：{path!r}")
    segments: list[PathSegment] = []
    for raw in raw_segments:
        match = _SEGMENT_PATTERN.fullmatch(raw)
        if match is None:
            raise StatePathError(f"非法路径段：{raw!r}")
        name = match.group("name")
        bracket = match.group("bracket")
        if bracket is None:
            if name is None:
                raise StatePathError(f"非法路径段：{raw!r}")
            segments.append(KeyAccess(name))
            continue
        if name is not None:
            segments.append(KeyAccess(name))
        if bracket.startswith('"') and bracket.endswith('"') and len(bracket) >= 2:
            segments.append(KeyAccess(bracket[1:-1]))
            continue
        if name is None:
            raise StatePathError(f"非法筛选段：{raw!r}")
        filter_match = _FILTER_PATTERN.fullmatch(bracket)
        if filter_match is None:
            raise StatePathError(f"非法筛选段：{raw!r}")
        segments.append(
            FilterAccess(
                key=filter_match.group("key"),
                value=_parse_filter_value(filter_match.group("value")),
            )
        )
    return tuple(segments)


def resolve_state_path(data: Mapping[str, object], path: str) -> object:
    """在状态树/事件载荷上按路径取值；路径终点可以是字段或节点。"""

    segments = parse_state_path(path)
    current: object = data
    for index, segment in enumerate(segments):
        terminal = index == len(segments) - 1
        if isinstance(segment, KeyAccess):
            current = _key_access(current, segment.key)
        else:
            current = _filter_access(current, segment, terminal)
    return current


def _key_access(current: object, key: str) -> object:
    if not isinstance(current, Mapping):
        raise StatePathError(f"路径段 {key!r} 的目标不是映射")
    try:
        return current[key]
    except KeyError as exc:
        raise StatePathError(f"路径键不存在：{key}") from exc


def _filter_access(
    current: object,
    segment: FilterAccess,
    terminal: bool,
) -> object:
    if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
        raise StatePathError(f"筛选段 {segment.key}={segment.value} 的目标不是列表")
    matched = [
        item
        for item in current
        if isinstance(item, Mapping) and _filter_matches(item, segment.key, segment.value)
    ]
    if terminal:
        return tuple(matched)
    if len(matched) != 1:
        raise StatePathError(
            f"筛选段 {segment.key}={segment.value} 匹配 {len(matched)} 项，路径继续要求恰好 1 项"
        )
    return matched[0]


def _filter_matches(item: Mapping[str, object], key: str, expected: object) -> bool:
    raw = item.get(key)
    if raw == expected:
        return True
    return str(raw) == str(expected)


def _parse_filter_value(value: str) -> object:
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _split_segments(path: str) -> list[str]:
    """按点切分段，忽略引号键内的点与方括号内的点。"""

    segments: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote = False
    had_bracket = False
    for char in path:
        if char == '"' and depth > 0:
            in_quote = not in_quote
            current.append(char)
            continue
        if not in_quote:
            if char == "[":
                if depth == 0 and current and had_bracket:
                    segments.append("".join(current))
                    current = []
                    had_bracket = False
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    had_bracket = True
            elif char == "." and depth == 0:
                segments.append("".join(current))
                current = []
                had_bracket = False
                continue
        current.append(char)
    segments.append("".join(current))
    return segments


def path_accessor(path: str) -> Any:
    """返回绑定到具体数据的取值函数（供查询执行器复用）。"""

    segments = parse_state_path(path)

    def access(data: Mapping[str, object]) -> object:
        current: object = data
        for index, segment in enumerate(segments):
            terminal = index == len(segments) - 1
            if isinstance(segment, KeyAccess):
                current = _key_access(current, segment.key)
            else:
                current = _filter_access(current, segment, terminal)
        return current

    return cast(Any, access)
