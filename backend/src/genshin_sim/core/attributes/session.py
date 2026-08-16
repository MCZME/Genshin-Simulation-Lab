from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from genshin_sim.core.attributes.errors import CircularDependencyError, MissingQueryTargetError
from genshin_sim.core.attributes.models import (
    AttributeQuery,
    AttributeResolution,
    AttributeSubjectRef,
    ProviderAttributeSubjectScope,
)


class _SessionResolver(Protocol):
    def assert_provider_can_read(
        self,
        provider_key: str,
        attribute_key: object,
        scope: ProviderAttributeSubjectScope,
    ) -> None: ...

    def resolve(
        self,
        query: AttributeQuery,
        *,
        session: AttributeResolutionSession,
    ) -> AttributeResolution: ...


@dataclass(slots=True)
class AttributeResolutionSession:
    resolver: _SessionResolver
    dependency_stack: list[AttributeQuery] = field(default_factory=list)
    memoized_results: dict[AttributeQuery, AttributeResolution] = field(default_factory=dict)
    active_provider_key: str | None = None

    def enter(self, query: AttributeQuery) -> None:
        if query in self.dependency_stack:
            chain = " -> ".join(str(item.attribute_key) for item in (*self.dependency_stack, query))
            raise CircularDependencyError(f"属性解析存在循环依赖：{chain}")
        self.dependency_stack.append(query)

    def exit(self, query: AttributeQuery) -> None:
        popped = self.dependency_stack.pop()
        if popped != query:
            raise CircularDependencyError("属性解析依赖栈状态不一致")

    def resolve_dependency(
        self,
        query: AttributeQuery,
        *,
        provider_key: str | None = None,
        scope: ProviderAttributeSubjectScope | None = None,
    ) -> AttributeResolution:
        effective_provider_key = provider_key or self.active_provider_key
        effective_scope = scope or ProviderAttributeSubjectScope.QUERY_SUBJECT
        if effective_provider_key is not None:
            self.resolver.assert_provider_can_read(
                effective_provider_key,
                query.attribute_key,
                effective_scope,
            )
        return self.resolver.resolve(query, session=self)

    def resolve_query_target(
        self,
        query: AttributeQuery,
        *,
        provider_key: str | None = None,
    ) -> AttributeResolution:
        if query.context.target_ref is None:
            raise MissingQueryTargetError("属性查询上下文缺少 target_ref")
        target_query = AttributeQuery(
            subject_ref=query.context.target_ref,
            attribute_key=query.attribute_key,
            frame=query.frame,
            context=query.context,
        )
        return self.resolve_dependency(
            target_query,
            provider_key=provider_key,
            scope=ProviderAttributeSubjectScope.QUERY_TARGET,
        )

    def resolve_provider_owner(
        self,
        query: AttributeQuery,
        owner_ref: AttributeSubjectRef,
        *,
        provider_key: str,
    ) -> AttributeResolution:
        owner_query = AttributeQuery(
            subject_ref=owner_ref,
            attribute_key=query.attribute_key,
            frame=query.frame,
            context=query.context,
        )
        return self.resolve_dependency(
            owner_query,
            provider_key=provider_key,
            scope=ProviderAttributeSubjectScope.PROVIDER_OWNER,
        )
