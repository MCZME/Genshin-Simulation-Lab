"""元素共鸣领域的稳定值对象。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from genshin_sim.core.attributes import (
    AttributeKey,
    ModifierStage,
    validate_finite_float,
)
from genshin_sim.core.attributes.errors import AttributeValidationError
from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.resonance.errors import ResonanceValidationError


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ResonanceValidationError(f"{name} 必须是非空字符串")


class ResonanceRequirementKind(StrEnum):
    """共鸣激活条件的两种形状。"""

    ELEMENT_COUNT = "element_count"
    DISTINCT_ELEMENTS = "distinct_elements"


@dataclass(frozen=True, slots=True)
class ResonanceRequirement:
    """一条共鸣的激活条件。"""

    kind: ResonanceRequirementKind
    element: Element | None = None
    count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResonanceRequirementKind):
            raise ResonanceValidationError("共鸣条件类型不受支持")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 2:
            raise ResonanceValidationError("共鸣条件人数必须是不小于 2 的整数")
        if self.kind is ResonanceRequirementKind.ELEMENT_COUNT:
            if not isinstance(self.element, Element) or self.element is Element.PHYSICAL:
                raise ResonanceValidationError("同元素共鸣必须指定非物理元素")
        elif self.element is not None:
            raise ResonanceValidationError("异元素共鸣不能携带元素")

    @classmethod
    def element_count(cls, element: Element, count: int = 2) -> ResonanceRequirement:
        return cls(ResonanceRequirementKind.ELEMENT_COUNT, element, count)

    @classmethod
    def distinct_elements(cls, count: int = 4) -> ResonanceRequirement:
        return cls(ResonanceRequirementKind.DISTINCT_ELEMENTS, None, count)


@dataclass(frozen=True, slots=True)
class ResonanceStaticModifier:
    """共鸣激活后对每个角色产生的静态属性修饰。"""

    target_key: AttributeKey
    stage: ModifierStage
    value: float
    audit_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_key, AttributeKey):
            raise ResonanceValidationError("共鸣静态修饰必须使用 AttributeKey")
        if not isinstance(self.stage, ModifierStage):
            raise ResonanceValidationError("共鸣静态修饰 stage 不受支持")
        object.__setattr__(
            self,
            "value",
            self._validate_value(),
        )
        tags = tuple(self.audit_tags)
        for tag in tags:
            _require_text(tag, "共鸣静态修饰审计标签")
        object.__setattr__(self, "audit_tags", tags)

    def _validate_value(self) -> float:
        try:
            return validate_finite_float(self.value, "共鸣静态修饰值")
        except AttributeValidationError as exc:
            raise ResonanceValidationError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ResonanceAuraDurationRule:
    """共鸣对角色主体指定 Aura 的附着时长倍率。"""

    aura_kind: AuraKind
    multiplier: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.aura_kind, AuraKind):
            raise ResonanceValidationError("共鸣附着时长规则必须指定 AuraKind")
        if self.aura_kind not in {
            AuraKind.PYRO,
            AuraKind.HYDRO,
            AuraKind.ELECTRO,
            AuraKind.CRYO,
        }:
            raise ResonanceValidationError("共鸣附着时长规则只支持四种普通元素 Aura")
        if not isinstance(self.multiplier, Fraction) or self.multiplier <= 0:
            raise ResonanceValidationError("共鸣附着时长倍率必须是正有理数")


@dataclass(frozen=True, slots=True)
class ResonanceDefinition:
    """一条共鸣的领域定义：激活条件与静态属性贡献。"""

    key: str
    requirement: ResonanceRequirement
    static_modifiers: tuple[ResonanceStaticModifier, ...] = ()
    aura_duration_rules: tuple[ResonanceAuraDurationRule, ...] = ()
    cooldown_duration_multiplier: Fraction | None = None

    def __post_init__(self) -> None:
        _require_text(self.key, "共鸣 key")
        if not isinstance(self.requirement, ResonanceRequirement):
            raise ResonanceValidationError("共鸣定义必须携带 ResonanceRequirement")
        modifiers = tuple(self.static_modifiers)
        for modifier in modifiers:
            if not isinstance(modifier, ResonanceStaticModifier):
                raise ResonanceValidationError("共鸣静态修饰必须是 ResonanceStaticModifier")
        seen: set[tuple[str, ModifierStage]] = set()
        for modifier in modifiers:
            pair = (str(modifier.target_key), modifier.stage)
            if pair in seen:
                raise ResonanceValidationError(f"共鸣 {self.key!r} 存在重复静态修饰：{pair[0]}")
            seen.add(pair)
        object.__setattr__(self, "static_modifiers", modifiers)
        rules = tuple(self.aura_duration_rules)
        for rule in rules:
            if not isinstance(rule, ResonanceAuraDurationRule):
                raise ResonanceValidationError("共鸣附着时长规则必须是 ResonanceAuraDurationRule")
        seen_kinds: set[AuraKind] = set()
        for rule in rules:
            if rule.aura_kind in seen_kinds:
                raise ResonanceValidationError(
                    f"共鸣 {self.key!r} 重复声明附着时长规则：{rule.aura_kind.value}"
                )
            seen_kinds.add(rule.aura_kind)
        object.__setattr__(self, "aura_duration_rules", rules)
        if self.cooldown_duration_multiplier is not None and (
            not isinstance(self.cooldown_duration_multiplier, Fraction)
            or self.cooldown_duration_multiplier <= 0
        ):
            raise ResonanceValidationError("共鸣冷却时长倍率必须是正有理数")


@dataclass(frozen=True, slots=True)
class TeamElementComposition:
    """队伍元素构成：只统计真实元素，允许无元素角色存在。"""

    team_size: int
    element_counts: tuple[tuple[Element, int], ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.team_size, bool)
            or not isinstance(self.team_size, int)
            or self.team_size < 0
        ):
            raise ResonanceValidationError("队伍人数必须是非负整数")
        counts = tuple(sorted(self.element_counts, key=lambda item: item[0].value))
        total = 0
        seen: set[Element] = set()
        for element, count in counts:
            if not isinstance(element, Element) or element is Element.PHYSICAL:
                raise ResonanceValidationError("元素构成只能包含七种元素")
            if element in seen:
                raise ResonanceValidationError(f"元素构成重复：{element.value}")
            seen.add(element)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ResonanceValidationError("元素构成计数必须是正整数")
            total += count
        if total > self.team_size:
            raise ResonanceValidationError("元素构成合计不能超过队伍人数")
        object.__setattr__(self, "element_counts", counts)

    @classmethod
    def from_counts(
        cls,
        team_size: int,
        counts: Mapping[Element, int],
    ) -> TeamElementComposition:
        pairs = tuple((element, count) for element, count in counts.items() if count > 0)
        return cls(team_size, pairs)

    def element_count(self, element: Element) -> int:
        for candidate, count in self.element_counts:
            if candidate is element:
                return count
        return 0

    @property
    def distinct_element_count(self) -> int:
        return len(self.element_counts)


@dataclass(frozen=True, slots=True)
class ResonanceActivation:
    """一次组装确定的活跃共鸣集合，固定为已排序去重 key。"""

    active_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        keys = tuple(self.active_keys)
        for key in keys:
            _require_text(key, "共鸣 key")
        if len(keys) != len(set(keys)):
            raise ResonanceValidationError("共鸣激活集合不能包含重复 key")
        if keys != tuple(sorted(keys)):
            raise ResonanceValidationError("共鸣激活集合必须按 key 稳定排序")
        object.__setattr__(self, "active_keys", keys)

    @classmethod
    def empty(cls) -> ResonanceActivation:
        return cls(())

    @property
    def is_empty(self) -> bool:
        return not self.active_keys
