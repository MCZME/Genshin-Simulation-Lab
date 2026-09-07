from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationPolicy,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.errors import (
    BuffDefinitionConflictError,
    BuffDefinitionNotFoundError,
    BuffValidationError,
)


def validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BuffValidationError(f"{field_name} 必须是非空字符串")


def validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BuffValidationError(f"{field_name} 必须是非负整数")


def validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BuffValidationError(f"{field_name} 必须是正整数")


def normalize_tags(tags: frozenset[str], field_name: str) -> frozenset[str]:
    normalized = frozenset(tags)
    for tag in normalized:
        validate_non_empty_text(tag, field_name)
    return normalized


@dataclass(frozen=True, slots=True)
class BuffAttributeModifierTemplate:
    term_key: str
    target_key: AttributeKey
    stage: ModifierStage
    stack_scaling: BuffStackScaling = BuffStackScaling.CONSTANT
    stacking_group: str | None = None
    required_query_tags: frozenset[str] = frozenset()
    excluded_query_tags: frozenset[str] = frozenset()
    audit_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_non_empty_text(self.term_key, "term_key")
        if not isinstance(self.target_key, AttributeKey):
            raise BuffValidationError("target_key 必须是 AttributeKey")
        if not isinstance(self.stage, ModifierStage):
            raise BuffValidationError("modifier stage 不受支持")
        if not isinstance(self.stack_scaling, BuffStackScaling):
            raise BuffValidationError("stack_scaling 不受支持")
        if self.stacking_group is not None:
            validate_non_empty_text(self.stacking_group, "stacking_group")
        required = normalize_tags(self.required_query_tags, "required_query_tags")
        excluded = normalize_tags(self.excluded_query_tags, "excluded_query_tags")
        if required.intersection(excluded):
            raise BuffValidationError("required_query_tags 与 excluded_query_tags 不能相交")
        object.__setattr__(self, "required_query_tags", required)
        object.__setattr__(self, "excluded_query_tags", excluded)
        for tag in self.audit_tags:
            validate_non_empty_text(tag, "audit_tags")
        object.__setattr__(self, "audit_tags", tuple(self.audit_tags))

    def matches_tags(self, query_tags: frozenset[str]) -> bool:
        return self.required_query_tags.issubset(
            query_tags
        ) and not self.excluded_query_tags.intersection(query_tags)

    def to_dict(self) -> dict[str, object]:
        return {
            "term_key": self.term_key,
            "target_key": str(self.target_key),
            "stage": self.stage.value,
            "stack_scaling": self.stack_scaling.value,
            "stacking_group": self.stacking_group,
            "required_query_tags": tuple(sorted(self.required_query_tags)),
            "excluded_query_tags": tuple(sorted(self.excluded_query_tags)),
            "audit_tags": self.audit_tags,
        }


@dataclass(frozen=True, slots=True)
class BuffDefinition:
    definition_key: str
    mechanic_key: str
    handler_key: str
    conflict_key: str
    target_kinds: frozenset[AttributeSubjectKind]
    application_policy: BuffApplicationPolicy
    value_refresh_policy: BuffValueRefreshPolicy
    max_stacks: int
    attribute_modifiers: tuple[BuffAttributeModifierTemplate, ...] = ()
    marker_only: bool = False
    tags: frozenset[str] = frozenset()
    # Buff 显示名：内容层提供的可读名称，进入属性词条审计（provider_display_name）。
    display_name: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.definition_key, "definition_key"),
            (self.mechanic_key, "mechanic_key"),
            (self.handler_key, "handler_key"),
            (self.conflict_key, "conflict_key"),
        ):
            validate_non_empty_text(value, name)
        if self.display_name is not None and (
            not isinstance(self.display_name, str) or not self.display_name.strip()
        ):
            raise BuffValidationError("display_name 提供时必须是非空字符串")
        target_kinds = frozenset(self.target_kinds)
        if not target_kinds:
            raise BuffValidationError("target_kinds 不能为空")
        allowed = {AttributeSubjectKind.CHARACTER, AttributeSubjectKind.TARGET}
        for kind in target_kinds:
            if kind not in allowed:
                raise BuffValidationError(f"Buff target kind 不受支持：{kind!r}")
        if not isinstance(self.application_policy, BuffApplicationPolicy):
            raise BuffValidationError("application_policy 不受支持")
        if not isinstance(self.value_refresh_policy, BuffValueRefreshPolicy):
            raise BuffValidationError("value_refresh_policy 不受支持")
        validate_positive_int(self.max_stacks, "max_stacks")
        if (
            self.application_policy is not BuffApplicationPolicy.STACK_REFRESH
            and self.max_stacks != 1
        ):
            raise BuffValidationError("非 stack_refresh 策略要求 max_stacks == 1")
        modifiers = tuple(self.attribute_modifiers)
        if self.marker_only and modifiers:
            raise BuffValidationError("marker_only 定义不能声明 attribute_modifiers")
        if not self.marker_only and not modifiers:
            raise BuffValidationError("非 marker 定义必须声明 attribute_modifiers")
        term_keys = [template.term_key for template in modifiers]
        if len(term_keys) != len(set(term_keys)):
            raise BuffValidationError(f"BuffDefinition {self.definition_key!r} term_key 重复")
        object.__setattr__(self, "target_kinds", target_kinds)
        object.__setattr__(self, "attribute_modifiers", modifiers)
        object.__setattr__(self, "tags", normalize_tags(self.tags, "buff definition tags"))

    def template_by_key(self) -> dict[str, BuffAttributeModifierTemplate]:
        return {template.term_key: template for template in self.attribute_modifiers}

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_key": self.definition_key,
            "mechanic_key": self.mechanic_key,
            "handler_key": self.handler_key,
            "conflict_key": self.conflict_key,
            "target_kinds": tuple(sorted(kind.value for kind in self.target_kinds)),
            "application_policy": self.application_policy.value,
            "value_refresh_policy": self.value_refresh_policy.value,
            "max_stacks": self.max_stacks,
            "attribute_modifiers": tuple(
                template.to_dict() for template in self.attribute_modifiers
            ),
            "marker_only": self.marker_only,
            "tags": tuple(sorted(self.tags)),
        }


class BuffDefinitionRegistry:
    def __init__(self, definitions: tuple[BuffDefinition, ...] = ()) -> None:
        self._definitions: dict[str, BuffDefinition] = {}
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[BuffDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def register(self, definition: BuffDefinition) -> BuffDefinition:
        if definition.definition_key in self._definitions:
            raise BuffDefinitionConflictError(
                f"重复 Buff definition_key：{definition.definition_key}"
            )
        self._definitions[definition.definition_key] = definition
        return definition

    def get(self, definition_key: str) -> BuffDefinition:
        try:
            return self._definitions[definition_key]
        except KeyError as exc:
            raise BuffDefinitionNotFoundError(
                f"未知 Buff definition_key：{definition_key}"
            ) from exc

    def contains(self, definition_key: str) -> bool:
        return definition_key in self._definitions
