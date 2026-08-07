"""效果定义契约：静态解锁、声明式部件包装与命座定义。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from genshin_sim.content.definitions.components import GenericComponent
from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible


class EffectDefinitionError(Exception):
    """效果定义错误基类。"""


class EffectDefinitionValidationError(EffectDefinitionError, ValueError):
    """效果定义不合法。"""


class EffectKind(StrEnum):
    """效果类别，与资产 effect_kind 对齐。"""

    CONSTELLATION = "constellation"
    PASSIVE = "passive"
    PASSIVE_EXPLORATION = "passive_exploration"
    ALTERNATE_SPRINT = "alternate_sprint"
    SPECIAL_MOVEMENT = "special_movement"
    SPECIAL_TALENT = "special_talent"
    WEAPON_PASSIVE = "weapon_passive"
    SET_BONUS = "set_bonus"


class UnlockKind(StrEnum):
    """静态解锁条件类别。"""

    ALWAYS = "always"
    CONSTELLATION = "constellation"
    SET_PIECES = "set_pieces"
    REFINEMENT = "refinement"
    TALENT_LEVEL = "talent_level"


@dataclass(frozen=True, slots=True)
class UnlockValues:
    """内容编译期可用的静态解锁证据。"""

    constellation: int = 0
    set_pieces: int = 0
    refinement: int = 1
    talent_levels: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_bounded_int(self.constellation, 0, 6, "constellation")
        _require_non_negative_int(self.set_pieces, "set_pieces")
        _require_positive_int(self.refinement, "refinement")
        talent_levels = dict(self.talent_levels)
        for talent_key, level in talent_levels.items():
            if not isinstance(talent_key, str) or not talent_key.strip():
                raise EffectDefinitionValidationError("天赋键必须是非空字符串")
            _require_positive_int(level, f"talent_levels.{talent_key}")
        object.__setattr__(self, "talent_levels", talent_levels)


@dataclass(frozen=True, slots=True)
class UnlockSpec:
    """单个效果的静态解锁条件。"""

    kind: UnlockKind
    threshold: int
    talent_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, UnlockKind):
            raise TypeError("kind 必须是 UnlockKind")
        _require_non_negative_int(self.threshold, "threshold")
        if self.kind is UnlockKind.ALWAYS:
            if self.threshold != 0 or self.talent_key is not None:
                raise EffectDefinitionValidationError("ALWAYS 解锁不携带 threshold 或 talent_key")
        elif self.kind is UnlockKind.CONSTELLATION:
            _require_bounded_int(self.threshold, 1, 6, "threshold")
        elif self.kind in {
            UnlockKind.SET_PIECES,
            UnlockKind.REFINEMENT,
            UnlockKind.TALENT_LEVEL,
        }:
            _require_positive_int(self.threshold, "threshold")
            if self.kind is UnlockKind.TALENT_LEVEL and (
                not isinstance(self.talent_key, str) or not self.talent_key.strip()
            ):
                raise EffectDefinitionValidationError("TALENT_LEVEL 解锁必须提供 talent_key")
        if self.kind is not UnlockKind.TALENT_LEVEL and self.talent_key is not None:
            raise EffectDefinitionValidationError("只有 TALENT_LEVEL 解锁可以携带 talent_key")

    def evaluate(self, values: UnlockValues) -> bool:
        """按编译期证据判定是否解锁。"""

        if self.kind is UnlockKind.ALWAYS:
            return True
        if self.kind is UnlockKind.CONSTELLATION:
            return values.constellation >= self.threshold
        if self.kind is UnlockKind.SET_PIECES:
            return values.set_pieces >= self.threshold
        if self.kind is UnlockKind.REFINEMENT:
            return values.refinement >= self.threshold
        assert self.talent_key is not None
        return values.talent_levels.get(self.talent_key, 0) >= self.threshold


@dataclass(frozen=True, slots=True)
class EffectSpec:
    """一个效果的定义：键 + 类别 + 解锁 + 部件 + 参数/覆盖。"""

    effect_key: str
    kind: EffectKind
    unlock: UnlockSpec
    component: GenericComponent | None = None
    params: Mapping[str, JSONValue] = field(default_factory=dict)
    overrides: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.effect_key, str) or not self.effect_key.strip():
            raise EffectDefinitionValidationError("effect_key 必须是非空字符串")
        if not isinstance(self.kind, EffectKind):
            raise TypeError("kind 必须是 EffectKind")
        if not isinstance(self.unlock, UnlockSpec):
            raise TypeError("unlock 必须是 UnlockSpec")
        if self.component is not None and not isinstance(self.component, GenericComponent):
            raise TypeError("component 必须是 GenericComponent 或 None")
        validate_json_compatible(self.params, path="params")
        validate_json_compatible(self.overrides, path="overrides")
        object.__setattr__(self, "params", dict(self.params))
        object.__setattr__(self, "overrides", dict(self.overrides))


@dataclass(frozen=True, slots=True)
class ConstellationDefinition:
    """命座包装：角色键 + 解锁 + generic 部件 + 参数/覆盖。"""

    key: str
    unlock: UnlockSpec
    component: GenericComponent
    params: Mapping[str, JSONValue] = field(default_factory=dict)
    overrides: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise EffectDefinitionValidationError("key 必须是非空字符串")
        if not isinstance(self.unlock, UnlockSpec):
            raise TypeError("unlock 必须是 UnlockSpec")
        if self.unlock.kind is not UnlockKind.CONSTELLATION:
            raise EffectDefinitionValidationError("命座定义必须使用 CONSTELLATION 解锁")
        if not isinstance(self.component, GenericComponent):
            raise TypeError("component 必须是 GenericComponent")
        validate_json_compatible(self.params, path="params")
        validate_json_compatible(self.overrides, path="overrides")
        object.__setattr__(self, "params", dict(self.params))
        object.__setattr__(self, "overrides", dict(self.overrides))

    def as_effect_spec(self) -> EffectSpec:
        return EffectSpec(
            effect_key=self.key,
            kind=EffectKind.CONSTELLATION,
            unlock=self.unlock,
            component=self.component,
            params=self.params,
            overrides=self.overrides,
        )


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EffectDefinitionValidationError(f"{field_name} 必须是非负整数")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EffectDefinitionValidationError(f"{field_name} 必须是正整数")


def _require_bounded_int(value: int, minimum: int, maximum: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise EffectDefinitionValidationError(f"{field_name} 必须在 {minimum} 到 {maximum} 之间")
