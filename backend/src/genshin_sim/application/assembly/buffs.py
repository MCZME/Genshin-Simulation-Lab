from __future__ import annotations

from collections.abc import Iterable, Sequence

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeDefinitionRegistry,
    AttributeKey,
    AttributeSystemError,
    AttributeVisibility,
    ModifierProvider,
)
from genshin_sim.core.attributes.policies import POLICIES
from genshin_sim.core.systems.buff import (
    BuffAttributeModifierProvider,
    BuffDefinition,
    BuffDefinitionRegistry,
    BuffModifierBindingError,
    BuffStore,
    BuffStoreReader,
    BuffSystemError,
)


def build_buff_definition_registry(
    definitions: Sequence[BuffDefinition],
) -> BuffDefinitionRegistry:
    try:
        return BuffDefinitionRegistry(tuple(definitions))
    except BuffSystemError as exc:
        raise InvalidRuntimePayloadError(str(exc)) from exc


def build_buff_attribute_providers(
    registry: BuffDefinitionRegistry,
    store: BuffStore,
) -> tuple[ModifierProvider, ...]:
    reader = BuffStoreReader(store)
    return tuple(
        BuffAttributeModifierProvider(definition, reader)
        for definition in registry.definitions
        if definition.attribute_modifiers
    )


def validate_buff_definitions_for_assembly(
    *,
    definitions: Iterable[BuffDefinition],
    attribute_definitions: AttributeDefinitionRegistry,
    modifier_providers: Iterable[ModifierProvider] = (),
) -> None:
    try:
        max_hp_upstream = _dependency_closure(
            attribute_definitions,
            STAT_HP_MAX,
            modifier_providers=modifier_providers,
        )
    except AttributeSystemError as exc:
        raise InvalidRuntimePayloadError(str(exc)) from exc
    for definition in definitions:
        for template in definition.attribute_modifiers:
            try:
                attribute_definition = attribute_definitions.get(template.target_key)
            except Exception as exc:
                raise InvalidRuntimePayloadError(
                    f"Buff {definition.definition_key!r} 写入未知属性：{template.target_key}"
                ) from exc
            if template.stage not in POLICIES[attribute_definition.policy_key].allowed_stages:
                raise InvalidRuntimePayloadError(
                    f"Buff {definition.definition_key!r} 写入 {template.target_key} 的阶段 "
                    f"{template.stage.value} 不被策略允许"
                )
            if not definition.target_kinds.issubset(attribute_definition.owner_kinds):
                raise InvalidRuntimePayloadError(
                    f"Buff {definition.definition_key!r} target_kinds 超出属性 "
                    f"{template.target_key} 支持的主体类型"
                )
            if (
                attribute_definition.visibility is AttributeVisibility.CONTENT_PRIVATE
                and attribute_definition.namespace_owner != definition.handler_key
            ):
                raise InvalidRuntimePayloadError(
                    f"Buff {definition.definition_key!r} 不能写入其他 handler 的私有属性 "
                    f"{template.target_key}"
                )
            if template.stacking_group is not None:
                group = attribute_definitions.get_stacking_group(template.stacking_group)
                if group is None:
                    raise InvalidRuntimePayloadError(
                        f"Buff {definition.definition_key!r} 引用了未知 stacking group："
                        f"{template.stacking_group}"
                    )
                if group.target_key != template.target_key or group.stage is not template.stage:
                    raise InvalidRuntimePayloadError(
                        f"Buff {definition.definition_key!r} stacking group 与模板属性或阶段不一致"
                    )
            if template.target_key in max_hp_upstream:
                raise InvalidRuntimePayloadError(
                    f"Buff {definition.definition_key!r} 第一版不能动态影响 stat.hp.max"
                )
        try:
            _assert_definition_modifier_contract(definition)
        except BuffModifierBindingError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc


def _assert_definition_modifier_contract(definition: BuffDefinition) -> None:
    keys = [template.term_key for template in definition.attribute_modifiers]
    if len(keys) != len(set(keys)):
        raise BuffModifierBindingError(f"Buff {definition.definition_key!r} modifier term_key 重复")


def _dependency_closure(
    registry: AttributeDefinitionRegistry,
    root: AttributeKey,
    *,
    modifier_providers: Iterable[ModifierProvider] = (),
) -> frozenset[AttributeKey]:
    provider_specs = tuple(provider.provider_spec for provider in modifier_providers)
    closure: set[AttributeKey] = {root}
    pending = [root]
    while pending:
        key = pending.pop()
        definition = registry.get(key)
        dependencies = list(definition.dependencies)
        for spec in provider_specs:
            if key in spec.writes:
                dependencies.extend(read.attribute_key for read in spec.reads)
        for dependency in dependencies:
            if dependency in closure:
                continue
            closure.add(dependency)
            pending.append(dependency)
    return frozenset(closure)
