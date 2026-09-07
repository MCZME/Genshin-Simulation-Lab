"""generic 谓词库：只读纯谓词（动态条件的内嵌形状）。

谓词按设计文档第 5 节作为行为切片的内置只读条件：输入是已提交领域状态
（经窄端口）、事实载荷与 owner 自己的内容状态；求值禁止写任何东西。
谓词工厂不带键，由内容包包装时传参数。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.core.contracts.json import JSONValue


class PredicateError(Exception):
    """谓词求值错误基类。"""


class InvalidPredicateParameterError(PredicateError, ValueError):
    """谓词工厂参数不合法。"""


@dataclass(frozen=True, slots=True)
class PredicateContext:
    """谓词求值的只读输入。"""

    frame: int
    owner_ref: str
    state: Mapping[str, JSONValue]
    owner_slot: int | None = None
    facts: tuple[object, ...] = ()
    simulation: object | None = None
    buff_lookup: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.owner_ref, str) or not self.owner_ref.strip():
            raise ValueError("owner_ref 必须是非空字符串")
        if self.owner_slot is not None and (
            isinstance(self.owner_slot, bool) or self.owner_slot <= 0
        ):
            raise ValueError("owner_slot 提供时必须为正整数")
        object.__setattr__(self, "facts", tuple(self.facts))


type Predicate = Callable[[PredicateContext], bool]


def stacks_at_least(field_name: str, threshold: int) -> Predicate:
    """内容状态层数不小于阈值。"""

    _validate_field_name(field_name)
    _validate_non_negative_int(threshold, "threshold")

    def predicate(context: PredicateContext) -> bool:
        value = _read_numeric(context, field_name)
        return value >= threshold

    return predicate


def stacks_above(field_name: str, threshold: int) -> Predicate:
    """内容状态层数严格大于阈值。"""

    _validate_field_name(field_name)
    _validate_non_negative_int(threshold, "threshold")

    def predicate(context: PredicateContext) -> bool:
        value = _read_numeric(context, field_name)
        return value > threshold

    return predicate


def field_equals(field_name: str, expected: JSONValue) -> Predicate:
    """内容状态字段等于给定值。"""

    _validate_field_name(field_name)

    def predicate(context: PredicateContext) -> bool:
        value = context.state.get(field_name)
        if field_name not in context.state:
            raise PredicateError(f"状态字段 {field_name!r} 缺失（owner {context.owner_ref}）")
        return value == expected

    return predicate


def hp_ratio_above(ratio: float) -> Predicate:
    """内容状态 ``hp_ratio`` 字段不小于给定比例。"""

    return _hp_ratio_predicate(ratio, at_least=True)


def hp_ratio_below(ratio: float) -> Predicate:
    """内容状态 ``hp_ratio`` 字段小于给定比例。"""

    return _hp_ratio_predicate(ratio, at_least=False)


def is_active_character() -> Predicate:
    """owner 是当前场上角色（通过仿真空间的窄端口判定）。"""

    def predicate(context: PredicateContext) -> bool:
        if context.owner_slot is None:
            return False
        team_state = _active_team_state(context)
        return getattr(team_state, "active_slot", None) == context.owner_slot

    return predicate


def has_buff(buff_key: str) -> Predicate:
    """owner 当前持有指定 Buff（通过注入的只读查询端口）。"""

    if not isinstance(buff_key, str) or not buff_key.strip():
        raise InvalidPredicateParameterError("buff_key 必须是非空字符串")

    def predicate(context: PredicateContext) -> bool:
        if context.buff_lookup is None:
            raise PredicateError("谓词 has_buff 缺少 buff 查询端口")
        return context.buff_lookup(buff_key)

    return predicate


def all_of(*predicates: Predicate) -> Predicate:
    """全部谓词成立。"""

    _validate_predicates(predicates)

    def predicate(context: PredicateContext) -> bool:
        return all(item(context) for item in predicates)

    return predicate


def any_of(*predicates: Predicate) -> Predicate:
    """任一谓词成立。"""

    _validate_predicates(predicates)

    def predicate(context: PredicateContext) -> bool:
        return any(item(context) for item in predicates)

    return predicate


def negate(predicate: Predicate) -> Predicate:
    """谓词取反。"""

    if not callable(predicate):
        raise InvalidPredicateParameterError("predicate 必须可调用")

    def wrapped(context: PredicateContext) -> bool:
        return not predicate(context)

    return wrapped


def _hp_ratio_predicate(ratio: float, *, at_least: bool) -> Predicate:
    if isinstance(ratio, bool) or not isinstance(ratio, int | float) or not 0 <= ratio <= 1:
        raise InvalidPredicateParameterError("hp_ratio 必须在 0 到 1 之间")

    def predicate(context: PredicateContext) -> bool:
        value = _read_numeric(context, "hp_ratio")
        if not 0 <= value <= 1:
            raise PredicateError(
                f"状态字段 hp_ratio 超出 [0, 1]：{value}（owner {context.owner_ref}）"
            )
        return value >= ratio if at_least else value < ratio

    return predicate


def _read_numeric(context: PredicateContext, field_name: str) -> float:
    if field_name not in context.state:
        raise PredicateError(f"状态字段 {field_name!r} 缺失（owner {context.owner_ref}）")
    value = context.state[field_name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PredicateError(f"状态字段 {field_name!r} 必须是数字，实际 {type(value).__name__}")
    return float(value)


def _active_team_state(context: PredicateContext) -> object:
    if context.simulation is None:
        raise PredicateError("谓词 is_active_character 缺少仿真上下文")
    space_runtime = getattr(context.simulation, "space_runtime", None)
    if space_runtime is None:
        raise PredicateError("谓词 is_active_character 缺少 space_runtime")
    team_state = getattr(space_runtime, "team_state", None)
    if team_state is None:
        raise PredicateError("谓词 is_active_character 缺少 team_state")
    return team_state


def _validate_field_name(field_name: str) -> None:
    if not isinstance(field_name, str) or not field_name.strip():
        raise InvalidPredicateParameterError("field_name 必须是非空字符串")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidPredicateParameterError(f"{field_name} 必须是非负整数")


def _validate_predicates(predicates: Sequence[Predicate]) -> None:
    if not predicates:
        raise InvalidPredicateParameterError("至少需要一个谓词")
    if any(not callable(item) for item in predicates):
        raise InvalidPredicateParameterError("谓词必须可调用")
