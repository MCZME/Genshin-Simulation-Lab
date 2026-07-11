from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from genshin_sim.core.attributes.definitions import AttributeDefinitionRegistry, AttributeVisibility
from genshin_sim.core.attributes.errors import (
    AttributeValidationError,
    InvalidModifierStageError,
    ProviderDependencyViolationError,
)
from genshin_sim.core.attributes.keys import AttributeKey
from genshin_sim.core.attributes.models import (
    AttributeSubjectRef,
    BaseAttributeContribution,
    ModifierProviderSpec,
    ModifierTerm,
    ProviderAttributeSubjectScope,
)
from genshin_sim.core.attributes.protocols import ModifierProvider


@dataclass(frozen=True, slots=True)
class BaseAttributeSet:
    _values: Mapping[
        tuple[AttributeSubjectRef, AttributeKey],
        tuple[BaseAttributeContribution, ...],
    ]

    def __init__(
        self,
        contributions: Iterable[tuple[AttributeSubjectRef, BaseAttributeContribution]],
    ) -> None:
        values: dict[tuple[AttributeSubjectRef, AttributeKey], list[BaseAttributeContribution]] = {}
        for subject_ref, contribution in contributions:
            values.setdefault((subject_ref, contribution.attribute_key), []).append(contribution)
        object.__setattr__(
            self,
            "_values",
            MappingProxyType({key: tuple(items) for key, items in values.items()}),
        )

    def get(
        self,
        subject_ref: AttributeSubjectRef,
        attribute_key: AttributeKey,
    ) -> tuple[BaseAttributeContribution, ...]:
        return self._values.get((subject_ref, attribute_key), ())


class ModifierProviderIndex:
    """按写入属性索引静态和动态 modifier provider。"""

    def __init__(
        self,
        providers: Iterable[ModifierProvider] = (),
        *,
        registry: AttributeDefinitionRegistry,
    ) -> None:
        self._registry = registry
        self._providers: tuple[ModifierProvider, ...] = tuple(providers)
        self._providers_by_write: dict[AttributeKey, tuple[ModifierProvider, ...]] = {}
        self._specs_by_key: dict[str, ModifierProviderSpec] = {}
        self._validate_and_index()

    @property
    def providers(self) -> tuple[ModifierProvider, ...]:
        return self._providers

    def get(self, attribute_key: AttributeKey) -> tuple[ModifierProvider, ...]:
        return self._providers_by_write.get(attribute_key, ())

    def spec_for(self, provider_key: str) -> ModifierProviderSpec:
        try:
            return self._specs_by_key[provider_key]
        except KeyError as exc:
            raise ProviderDependencyViolationError(f"未知 provider：{provider_key}") from exc

    def assert_can_read(
        self,
        provider_key: str,
        attribute_key: AttributeKey,
        scope: ProviderAttributeSubjectScope,
    ) -> None:
        spec = self.spec_for(provider_key)
        if any(
            read.attribute_key == attribute_key and read.subject_scope is scope
            for read in spec.reads
        ):
            return
        raise ProviderDependencyViolationError(
            f"provider {provider_key!r} 未声明读取 {scope.value}.{attribute_key}"
        )

    def validate_term(self, provider_key: str, term: ModifierTerm) -> None:
        spec = self.spec_for(provider_key)
        if term.target_key not in spec.writes:
            raise ProviderDependencyViolationError(
                f"provider {provider_key!r} 产生了未声明写入的属性 {term.target_key}"
            )

    def _validate_and_index(self) -> None:
        providers_by_write: dict[AttributeKey, list[ModifierProvider]] = {}
        for provider in self._providers:
            spec = provider.provider_spec
            if spec.provider_key in self._specs_by_key:
                raise AttributeValidationError(f"重复 provider_key：{spec.provider_key}")
            for read in spec.reads:
                self._registry.get(read.attribute_key)
                self._validate_private_access(spec, read.attribute_key)
            if not spec.writes:
                raise AttributeValidationError(f"provider {spec.provider_key!r} 必须声明 writes")
            for write_key in spec.writes:
                self._registry.get(write_key)
                self._validate_private_access(spec, write_key)
                providers_by_write.setdefault(write_key, []).append(provider)
            self._specs_by_key[spec.provider_key] = spec
        self._reject_static_query_subject_cycles()
        self._providers_by_write = {key: tuple(value) for key, value in providers_by_write.items()}

    def _validate_private_access(
        self,
        spec: ModifierProviderSpec,
        attribute_key: AttributeKey,
    ) -> None:
        definition = self._registry.get(attribute_key)
        if definition.visibility is not AttributeVisibility.CONTENT_PRIVATE:
            return
        if spec.private_namespace != definition.namespace_owner:
            raise ProviderDependencyViolationError(
                f"provider {spec.provider_key!r} 不能访问私有属性 {attribute_key}"
            )

    def _reject_static_query_subject_cycles(self) -> None:
        graph: dict[AttributeKey, set[AttributeKey]] = {}
        for definition in self._registry.definitions:
            graph.setdefault(definition.key, set()).update(definition.dependencies)
        for spec in self._specs_by_key.values():
            query_subject_reads = {
                read.attribute_key
                for read in spec.reads
                if read.subject_scope is ProviderAttributeSubjectScope.QUERY_SUBJECT
            }
            for write_key in spec.writes:
                graph.setdefault(write_key, set()).update(query_subject_reads)
        _assert_acyclic(graph)


def _assert_acyclic(graph: dict[AttributeKey, set[AttributeKey]]) -> None:
    visiting: set[AttributeKey] = set()
    visited: set[AttributeKey] = set()

    def visit(node: AttributeKey) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ProviderDependencyViolationError(f"属性依赖存在同主体循环：{node}")
        visiting.add(node)
        for dependency in graph.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def validate_definition_policy_stages(
    registry: AttributeDefinitionRegistry,
    allowed_stages_by_policy: dict[str, frozenset[object]],
) -> None:
    for definition in registry.definitions:
        if definition.policy_key not in allowed_stages_by_policy:
            raise AttributeValidationError(f"未知属性解析策略：{definition.policy_key}")
    for group in registry.stacking_groups:
        definition = registry.get(group.target_key)
        allowed = allowed_stages_by_policy[definition.policy_key]
        if group.stage not in allowed:
            raise InvalidModifierStageError(
                f"stacking group {group.group_key!r} 阶段不被属性 {group.target_key} 允许"
            )
