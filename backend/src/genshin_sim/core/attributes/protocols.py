from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from genshin_sim.core.attributes.definitions import AttributeDefinition
from genshin_sim.core.attributes.models import (
    AttributeQuery,
    AttributeResolution,
    AttributeSubjectRef,
    BaseAttributeContribution,
    ModifierProviderSpec,
    ModifierTerm,
)


class ModifierProvider(Protocol):
    @property
    def provider_spec(self) -> ModifierProviderSpec: ...

    def contribute(
        self,
        query: AttributeQuery,
        session: object,
    ) -> Sequence[ModifierTerm]: ...


class AttributeReader(Protocol):
    def resolve(self, query: AttributeQuery) -> object: ...


@dataclass(frozen=True, slots=True)
class StaticModifierProvider:
    provider_spec: ModifierProviderSpec
    terms: tuple[ModifierTerm, ...]
    subject_ref: AttributeSubjectRef | None

    def __init__(
        self,
        provider_spec: ModifierProviderSpec,
        terms: Iterable[ModifierTerm],
        *,
        subject_ref: AttributeSubjectRef | None = None,
    ) -> None:
        object.__setattr__(self, "provider_spec", provider_spec)
        object.__setattr__(self, "terms", tuple(terms))
        object.__setattr__(self, "subject_ref", subject_ref)

    def contribute(self, query: AttributeQuery, session: object) -> Sequence[ModifierTerm]:
        del session
        if self.subject_ref is not None and query.subject_ref != self.subject_ref:
            return ()
        return tuple(term for term in self.terms if term.target_key == query.attribute_key)


class ResolutionPolicy(Protocol):
    policy_key: str
    allowed_stages: frozenset[object]

    def resolve(
        self,
        definition: AttributeDefinition,
        base_contributions: tuple[BaseAttributeContribution, ...],
        terms: tuple[ModifierTerm, ...],
        dependencies: tuple[AttributeResolution, ...],
    ) -> tuple[float, float]: ...
