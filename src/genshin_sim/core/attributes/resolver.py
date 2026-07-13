from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.attributes.definitions import (
    AttributeDefinitionRegistry,
    ModifierStackingPolicy,
    OverridePolicy,
)
from genshin_sim.core.attributes.errors import (
    AttributeValidationError,
    ConflictingOverrideError,
    InvalidModifierStageError,
    ProviderDependencyViolationError,
    UnsupportedOwnerError,
)
from genshin_sim.core.attributes.indexes import (
    BaseAttributeSet,
    ModifierProviderIndex,
    validate_definition_policy_stages,
)
from genshin_sim.core.attributes.models import (
    AttributeQuery,
    AttributeResolution,
    AttributeResolveOptions,
    AttributeSnapshot,
    AttributeSnapshotEntry,
    ModifierStage,
    ModifierTerm,
    ProviderAttributeSubjectScope,
    TraceLevel,
    normalize_zero,
)
from genshin_sim.core.attributes.policies import POLICIES
from genshin_sim.core.attributes.session import AttributeResolutionSession


@dataclass(frozen=True, slots=True)
class AttributeResolver:
    definitions: AttributeDefinitionRegistry
    base_attributes: BaseAttributeSet
    modifier_index: ModifierProviderIndex

    def __post_init__(self) -> None:
        validate_definition_policy_stages(
            self.definitions,
            {key: policy.allowed_stages for key, policy in POLICIES.items()},
        )

    def new_session(self) -> AttributeResolutionSession:
        return AttributeResolutionSession(resolver=self)

    def resolve(
        self,
        query: AttributeQuery,
        *,
        options: AttributeResolveOptions | None = None,
        session: AttributeResolutionSession | None = None,
    ) -> AttributeResolution:
        options = options or AttributeResolveOptions()
        if session is None:
            session = self.new_session()
        resolution = self._resolve_full(query, session=session)
        return _project_resolution(resolution, options.trace_level)

    def _resolve_full(
        self,
        query: AttributeQuery,
        *,
        session: AttributeResolutionSession,
    ) -> AttributeResolution:
        cached = session.memoized_results.get(query)
        if cached is not None:
            return cached
        definition = self.definitions.get(query.attribute_key)
        if query.subject_ref.kind not in definition.owner_kinds:
            raise UnsupportedOwnerError(
                f"属性 {query.attribute_key} 不支持主体类型 {query.subject_ref.kind.value}"
            )
        session.enter(query)
        try:
            dependency_resolutions = tuple(
                self._resolve_full(
                    AttributeQuery(
                        subject_ref=query.subject_ref,
                        attribute_key=dependency_key,
                        frame=query.frame,
                        context=query.context,
                    ),
                    session=session,
                )
                for dependency_key in definition.dependencies
            )
            base_contributions = self.base_attributes.get(query.subject_ref, query.attribute_key)
            raw_terms = self._collect_terms(query, session)
            applied_terms, rejected_terms = self._select_terms(query, raw_terms)
            try:
                policy = POLICIES[definition.policy_key]
            except KeyError as exc:
                raise AttributeValidationError(
                    f"未知属性解析策略：{definition.policy_key}"
                ) from exc
            for term in applied_terms:
                if term.stage is ModifierStage.OVERRIDE:
                    if definition.override_policy is OverridePolicy.FORBIDDEN:
                        raise InvalidModifierStageError(
                            f"属性 {query.attribute_key} 禁止 override modifier"
                        )
                    continue
                if term.stage not in policy.allowed_stages:
                    raise InvalidModifierStageError(
                        f"属性 {query.attribute_key} 不允许 modifier 阶段 {term.stage.value}"
                    )
            non_override_terms = tuple(
                term for term in applied_terms if term.stage is not ModifierStage.OVERRIDE
            )
            base_value, final_value = policy.resolve(
                definition,
                base_contributions,
                non_override_terms,
                dependency_resolutions,
            )
            override_terms = [
                term for term in applied_terms if term.stage is ModifierStage.OVERRIDE
            ]
            if override_terms:
                if len(override_terms) > 1:
                    raise ConflictingOverrideError(f"属性 {query.attribute_key} 存在多个 override")
                final_value = normalize_zero(
                    policy.apply_bounds(definition, override_terms[0].value)
                )
            resolution = AttributeResolution(
                attribute_key=query.attribute_key,
                subject_ref=query.subject_ref,
                final_value=final_value,
                base_value=base_value,
                applied_terms=applied_terms,
                rejected_terms=rejected_terms,
                dependency_resolutions=dependency_resolutions,
                policy_key=definition.policy_key,
                trace_metadata={"memoized": False},
            )
            session.memoized_results[query] = resolution
            return resolution
        finally:
            session.exit(query)

    def assert_provider_can_read(
        self,
        provider_key: str,
        attribute_key: object,
        scope: ProviderAttributeSubjectScope,
    ) -> None:
        self.modifier_index.assert_can_read(provider_key, attribute_key, scope)  # type: ignore[arg-type]

    def snapshot(
        self,
        *,
        snapshot_id: str,
        queries: tuple[AttributeQuery, ...],
        trace_level: TraceLevel = TraceLevel.APPLIED,
    ) -> AttributeSnapshot:
        if not queries:
            raise AttributeValidationError("属性快照至少需要一个查询")
        frame = queries[0].frame
        subject_ref = queries[0].subject_ref
        if any(query.frame != frame for query in queries):
            raise AttributeValidationError("同一属性快照的查询 frame 必须一致")
        if any(query.subject_ref != subject_ref for query in queries):
            raise AttributeValidationError("同一属性快照的查询 subject_ref 必须一致")
        session = self.new_session()
        entries: list[AttributeSnapshotEntry] = []
        for query in queries:
            resolution = self.resolve(
                query,
                options=AttributeResolveOptions(trace_level=trace_level),
                session=session,
            )
            entries.append(
                AttributeSnapshotEntry(
                    attribute_key=resolution.attribute_key,
                    context=query.context,
                    value=resolution.final_value,
                    applied_terms=(
                        () if trace_level is TraceLevel.NONE else resolution.applied_terms
                    ),
                    rejected_terms=(
                        () if trace_level is not TraceLevel.FULL else resolution.rejected_terms
                    ),
                    dependency_trace=(
                        () if trace_level is TraceLevel.NONE else resolution.dependency_resolutions
                    ),
                )
            )
        return AttributeSnapshot(
            snapshot_id=snapshot_id,
            frame=frame,
            subject_ref=subject_ref,
            entries=tuple(entries),
            trace_level=trace_level,
        )

    def _collect_terms(
        self,
        query: AttributeQuery,
        session: AttributeResolutionSession,
    ) -> tuple[ModifierTerm, ...]:
        terms: list[ModifierTerm] = []
        for provider in self.modifier_index.get(query.attribute_key):
            spec = provider.provider_spec
            previous_provider = session.active_provider_key
            session.active_provider_key = spec.provider_key
            try:
                provider_terms = tuple(provider.contribute(query, session))
            finally:
                session.active_provider_key = previous_provider
            for term in provider_terms:
                if term.provider_key != spec.provider_key:
                    raise ProviderDependencyViolationError(
                        f"provider {spec.provider_key!r} 返回了不匹配的 provider_key"
                    )
                self.modifier_index.validate_term(spec.provider_key, term)
                if term.target_key == query.attribute_key:
                    terms.append(term)
        return tuple(sorted(terms, key=_term_sort_key))

    def _select_terms(
        self,
        query: AttributeQuery,
        terms: tuple[ModifierTerm, ...],
    ) -> tuple[tuple[ModifierTerm, ...], tuple[ModifierTerm, ...]]:
        del query
        selected: list[ModifierTerm] = []
        rejected: list[ModifierTerm] = []
        grouped: dict[str, list[ModifierTerm]] = {}
        for term in terms:
            if term.stacking_group is None:
                selected.append(term)
                continue
            grouped.setdefault(term.stacking_group, []).append(term)
        for group_key, group_terms in sorted(grouped.items()):
            group_definition = self.definitions.get_stacking_group(group_key)
            if group_definition is None:
                raise AttributeValidationError(f"未知 stacking group：{group_key}")
            for term in group_terms:
                if (
                    term.target_key != group_definition.target_key
                    or term.stage is not group_definition.stage
                ):
                    raise AttributeValidationError(
                        f"stacking group {group_key!r} 的属性或阶段与定义不一致"
                    )
            if group_definition.policy is ModifierStackingPolicy.HIGHEST:
                winner = max(group_terms, key=lambda term: (term.value, _term_sort_key(term)))
            else:
                winner = min(group_terms, key=lambda term: (term.value, _term_sort_key(term)))
            selected.append(winner)
            rejected.extend(term for term in group_terms if term is not winner)
        return (
            tuple(sorted(selected, key=_term_sort_key)),
            tuple(sorted(rejected, key=_term_sort_key)),
        )


def _term_sort_key(term: ModifierTerm) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        str(term.target_key),
        term.stage.value,
        term.provider_key,
        term.source_ref.kind.value,
        term.source_ref.source_key,
        term.source_ref.instance_id or "",
        "|".join(term.audit_tags),
        repr(term.value),
    )


def _project_resolution(
    resolution: AttributeResolution,
    trace_level: TraceLevel,
) -> AttributeResolution:
    if trace_level is TraceLevel.FULL:
        return resolution
    if trace_level is TraceLevel.NONE:
        applied_terms: tuple[ModifierTerm, ...] = ()
        dependency_resolutions: tuple[AttributeResolution, ...] = ()
    else:
        applied_terms = resolution.applied_terms
        dependency_resolutions = tuple(
            _project_resolution(dependency, TraceLevel.APPLIED)
            for dependency in resolution.dependency_resolutions
        )
    return AttributeResolution(
        attribute_key=resolution.attribute_key,
        subject_ref=resolution.subject_ref,
        final_value=resolution.final_value,
        base_value=resolution.base_value,
        applied_terms=applied_terms,
        rejected_terms=(),
        dependency_resolutions=dependency_resolutions,
        policy_key=resolution.policy_key,
        trace_metadata=resolution.trace_metadata,
    )
