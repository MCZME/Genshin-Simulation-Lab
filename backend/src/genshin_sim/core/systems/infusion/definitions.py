from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import AttributeSubjectKind
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.systems.infusion.enums import InfusionMode, RefreshPolicy
from genshin_sim.core.systems.infusion.errors import (
    InfusionDefinitionConflictError,
    InfusionDefinitionNotFoundError,
    InfusionValidationError,
)


def validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InfusionValidationError(f"{field_name} 必须是非空字符串")


def validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InfusionValidationError(f"{field_name} 必须是非负整数")


def validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InfusionValidationError(f"{field_name} 必须是正整数")


def normalize_tags(tags: frozenset[str], field_name: str) -> frozenset[str]:
    normalized = frozenset(tags)
    for tag in normalized:
        validate_non_empty_text(tag, field_name)
    return normalized


@dataclass(frozen=True, slots=True)
class InfusionDefinition:
    """组装期编译、运行时只读的附魔/转化来源定义。"""

    definition_key: str
    mechanic_key: str
    handler_key: str
    mode: InfusionMode
    element: Element
    applicable_attack_tags: frozenset[str]
    refresh_policy: RefreshPolicy
    duration_frames: int
    weapon_gauge: AuraAmount
    period_frames: int | None = None
    target_kinds: frozenset[AttributeSubjectKind] = frozenset({AttributeSubjectKind.CHARACTER})

    def __post_init__(self) -> None:
        for value, name in (
            (self.definition_key, "definition_key"),
            (self.mechanic_key, "mechanic_key"),
            (self.handler_key, "handler_key"),
        ):
            validate_non_empty_text(value, name)
        if not isinstance(self.mode, InfusionMode):
            raise InfusionValidationError("mode 不受支持")
        if not isinstance(self.element, Element):
            raise InfusionValidationError("element 不受支持")
        if self.element is Element.PHYSICAL:
            raise InfusionValidationError("附魔/转化元素不允许是物理")
        tags = normalize_tags(self.applicable_attack_tags, "applicable_attack_tags")
        if not tags:
            raise InfusionValidationError("applicable_attack_tags 不能为空")
        if not isinstance(self.refresh_policy, RefreshPolicy):
            raise InfusionValidationError("refresh_policy 不受支持")
        validate_positive_int(self.duration_frames, "duration_frames")
        if not isinstance(self.weapon_gauge, AuraAmount) or self.weapon_gauge.is_zero:
            raise InfusionValidationError("weapon_gauge 必须是正 AuraAmount")
        if self.refresh_policy is RefreshPolicy.PERIODIC:
            if self.period_frames is None:
                raise InfusionValidationError("PERIODIC 定义必须提供 period_frames")
            validate_positive_int(self.period_frames, "period_frames")
            if self.period_frames > self.duration_frames:
                raise InfusionValidationError("PERIODIC 定义要求 period_frames <= duration_frames")
        elif self.period_frames is not None:
            raise InfusionValidationError("ONCE 定义不能提供 period_frames")
        target_kinds = frozenset(self.target_kinds)
        allowed = {AttributeSubjectKind.CHARACTER}
        if not target_kinds or not target_kinds.issubset(allowed):
            raise InfusionValidationError("第一版只支持角色主体")
        object.__setattr__(self, "applicable_attack_tags", tags)
        object.__setattr__(self, "target_kinds", target_kinds)

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "handler_key": self.handler_key,
            "mode": self.mode.value,
            "element": self.element.value,
            "applicable_attack_tags": tuple(sorted(self.applicable_attack_tags)),
            "refresh_policy": self.refresh_policy.value,
            "duration_frames": self.duration_frames,
            "weapon_gauge": self.weapon_gauge.to_dict(),
            "period_frames": self.period_frames,
            "target_kinds": tuple(sorted(kind.value for kind in self.target_kinds)),
        }


class InfusionDefinitionRegistry:
    def __init__(self, definitions: tuple[InfusionDefinition, ...] = ()) -> None:
        self._definitions: dict[str, InfusionDefinition] = {}
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[InfusionDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def register(self, definition: InfusionDefinition) -> InfusionDefinition:
        if definition.definition_key in self._definitions:
            raise InfusionDefinitionConflictError(
                f"重复 Infusion definition_key：{definition.definition_key}"
            )
        self._definitions[definition.definition_key] = definition
        return definition

    def get(self, definition_key: str) -> InfusionDefinition:
        try:
            return self._definitions[definition_key]
        except KeyError as exc:
            raise InfusionDefinitionNotFoundError(
                f"未知 Infusion definition_key：{definition_key}"
            ) from exc

    def contains(self, definition_key: str) -> bool:
        return definition_key in self._definitions
