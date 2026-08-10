"""月兆领域的稳定值对象。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.moonsign.errors import MoonsignValidationError


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MoonsignValidationError(f"{name} 必须是非空字符串")


def _validate_finite(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MoonsignValidationError(f"{name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise MoonsignValidationError(f"{name} 必须是有限数字")
    return result


def _validate_non_negative(value: float | int, name: str) -> float:
    result = _validate_finite(value, name)
    if result < 0:
        raise MoonsignValidationError(f"{name} 不能为负数")
    return result


class MoonsignLevel(StrEnum):
    """月兆等级：无 / 初辉 / 满辉。"""

    NONE = "none"
    NASCENT = "nascent"
    ASCENDANT = "ascendant"

    @property
    def rank(self) -> int:
        return {"none": 0, "nascent": 1, "ascendant": 2}[self.value]

    @classmethod
    def from_count(cls, count: int) -> MoonsignLevel:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise MoonsignValidationError("月兆角色数量必须是非负整数")
        if count >= 2:
            return cls.ASCENDANT
        if count == 1:
            return cls.NASCENT
        return cls.NONE


@dataclass(frozen=True, slots=True)
class MoonsignScaling:
    """非月兆角色月曜增伤的元素缩放参数。"""

    divisor: float
    ratio: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "divisor", _validate_finite(self.divisor, "divisor"))
        object.__setattr__(self, "ratio", _validate_finite(self.ratio, "ratio"))
        if self.divisor <= 0:
            raise MoonsignValidationError("divisor 必须为正数")
        if self.ratio <= 0:
            raise MoonsignValidationError("ratio 必须为正数")


@dataclass(frozen=True, slots=True)
class MoonsignStatSnapshot:
    """非月兆角色施放 E/Q 时用于月曜增伤公式的属性快照。"""

    atk: float
    hp_max: float
    def_total: float
    elemental_mastery: float

    def __post_init__(self) -> None:
        for name in ("atk", "hp_max", "def_total", "elemental_mastery"):
            object.__setattr__(
                self,
                name,
                _validate_non_negative(getattr(self, name), name),
            )


@dataclass(frozen=True, slots=True)
class MoonsignBonusRecord:
    """当前生效的非月兆角色月曜增伤记录（单条、覆盖式）。"""

    source_ref: AttributeSubjectRef
    value: float
    applied_frame: int
    expires_at_frame: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_ref, AttributeSubjectRef):
            raise MoonsignValidationError("source_ref 必须是 AttributeSubjectRef")
        object.__setattr__(self, "value", _validate_non_negative(self.value, "value"))
        for name in ("applied_frame", "expires_at_frame"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MoonsignValidationError(f"{name} 必须是非负整数")
        if self.expires_at_frame <= self.applied_frame:
            raise MoonsignValidationError("expires_at_frame 必须晚于 applied_frame")

    def is_active_at(self, frame: int) -> bool:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise MoonsignValidationError("frame 必须是非负整数")
        return self.applied_frame <= frame < self.expires_at_frame


MOONSIGN_ELEMENT_STAT_KEY: dict[Element, str] = {
    Element.PYRO: "atk",
    Element.ELECTRO: "atk",
    Element.CRYO: "atk",
    Element.HYDRO: "hp_max",
    Element.GEO: "def_total",
    Element.ANEMO: "elemental_mastery",
    Element.DENDRO: "elemental_mastery",
}
