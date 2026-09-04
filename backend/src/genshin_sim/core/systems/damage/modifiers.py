"""伤害专用 modifier provider 协议、声明和稳定索引。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from genshin_sim.core.attributes import (
    AttributeKey,
    AttributeSubjectRef,
    ProviderAttributeSubjectScope,
)
from genshin_sim.core.systems.damage.enums import (
    DamageModifierStackingPolicy,
    DamageModifierStage,
)
from genshin_sim.core.systems.damage.errors import (
    ConflictingDamageModifierError,
    DamageProviderViolationError,
    DamageValidationError,
)
from genshin_sim.core.systems.damage.models import DamageModifierTerm, DamageQuery

if TYPE_CHECKING:
    from genshin_sim.core.systems.damage.resolver import DamageResolutionSession


@dataclass(frozen=True, slots=True)
class DamageAttributeRead:
    """伤害 provider 声明的一项属性读取权限。"""

    attribute_key: AttributeKey
    subject_scope: ProviderAttributeSubjectScope = ProviderAttributeSubjectScope.QUERY_SUBJECT

    def __post_init__(self) -> None:
        """校验读取主体范围属于属性系统的受支持枚举。"""

        if not isinstance(self.subject_scope, ProviderAttributeSubjectScope):
            raise DamageValidationError("damage attribute read scope 不受支持")


@dataclass(frozen=True, slots=True)
class DamageModifierProviderSpec:
    """伤害 modifier provider 在组装和运行时使用的能力声明。"""

    provider_key: str
    reads: tuple[DamageAttributeRead, ...] = ()
    writes: frozenset[DamageModifierStage] = frozenset()
    owner_ref: AttributeSubjectRef | None = None
    # provider 显示名；由内容层提供，收集器注入返回 term 的审计。
    display_name: str | None = None

    def __post_init__(self) -> None:
        """冻结声明集合，并校验 provider key、读取和写入阶段。"""

        if not isinstance(self.provider_key, str) or not self.provider_key.strip():
            raise DamageValidationError("damage provider_key 必须是非空字符串")
        if not self.writes:
            raise DamageValidationError("damage provider writes 不能为空")
        if any(not isinstance(read, DamageAttributeRead) for read in self.reads):
            raise DamageValidationError("damage provider reads 包含非法声明")
        if any(not isinstance(stage, DamageModifierStage) for stage in self.writes):
            raise DamageValidationError("damage provider writes 包含非法阶段")
        if self.display_name is not None and (
            not isinstance(self.display_name, str) or not self.display_name.strip()
        ):
            raise DamageValidationError("damage provider display_name 必须是非空字符串")
        object.__setattr__(self, "reads", tuple(self.reads))
        object.__setattr__(self, "writes", frozenset(self.writes))


class DamageModifierProvider(Protocol):
    """无副作用地为一次伤害查询贡献专用修饰项的协议。"""

    @property
    def provider_spec(self) -> DamageModifierProviderSpec:
        """返回 provider 的稳定身份、读取权限和写入阶段声明。"""

        ...

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> Sequence[DamageModifierTerm]:
        """根据当前伤害查询返回候选修饰项。"""

        ...


class StaticDamageModifierProvider:
    """测试和静态效果使用的固定伤害修饰 provider。"""

    def __init__(
        self,
        provider_spec: DamageModifierProviderSpec,
        terms: Sequence[DamageModifierTerm],
    ) -> None:
        """保存 provider 声明和固定返回的修饰项。"""

        self._provider_spec = provider_spec
        self._terms = tuple(terms)

    @property
    def provider_spec(self) -> DamageModifierProviderSpec:
        """返回固定 provider 的能力声明。"""

        return self._provider_spec

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        """忽略查询上下文，返回构造时提供的固定修饰项。"""

        del query, session
        return self._terms


@dataclass(frozen=True, slots=True)
class DamageModifierStackingGroupDefinition:
    """定义同一 stacking group 中候选修饰项的选择规则。"""

    group_key: str
    stage: DamageModifierStage
    policy: DamageModifierStackingPolicy

    def __post_init__(self) -> None:
        """校验叠加组身份、阶段和选择策略。"""

        if not isinstance(self.group_key, str) or not self.group_key.strip():
            raise DamageValidationError("damage stacking group_key 必须是非空字符串")
        if not isinstance(self.stage, DamageModifierStage):
            raise DamageValidationError("damage stacking group stage 不受支持")
        if not isinstance(self.policy, DamageModifierStackingPolicy):
            raise DamageValidationError("damage stacking group policy 不受支持")


@dataclass(frozen=True, slots=True)
class DamageModifierCollection:
    """一次收集后已生效与被叠加规则拒绝的修饰项集合。"""

    applied_terms: tuple[DamageModifierTerm, ...]
    rejected_terms: tuple[DamageModifierTerm, ...]


class DamageModifierIndex:
    """按稳定 provider 顺序收集伤害修饰项并应用叠加规则。"""

    def __init__(
        self,
        providers: Sequence[DamageModifierProvider] = (),
        stacking_groups: Sequence[DamageModifierStackingGroupDefinition] = (),
    ) -> None:
        """注册 provider 和 stacking group，并拒绝重复稳定 key。"""

        self._providers: dict[str, DamageModifierProvider] = {}
        self._stacking_groups: dict[str, DamageModifierStackingGroupDefinition] = {}
        for group in stacking_groups:
            if group.group_key in self._stacking_groups:
                raise DamageValidationError(f"重复 damage stacking group：{group.group_key}")
            self._stacking_groups[group.group_key] = group
        for provider in providers:
            provider_key = provider.provider_spec.provider_key
            if provider_key in self._providers:
                raise DamageValidationError(f"重复 damage provider：{provider_key}")
            self._providers[provider_key] = provider

    @property
    def provider_keys(self) -> tuple[str, ...]:
        """按稳定字典序返回当前注册的 provider key。"""

        return tuple(sorted(self._providers))

    def collect(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> DamageModifierCollection:
        """调用所有 provider，校验返回值并产出生效/拒绝集合。"""

        terms: list[DamageModifierTerm] = []
        for provider_key in self.provider_keys:
            provider = self._providers[provider_key]
            spec = provider.provider_spec
            session.begin_provider(spec)
            try:
                provided = tuple(provider.contribute(query, session))
            finally:
                session.end_provider(spec)
            for term in provided:
                if not isinstance(term, DamageModifierTerm):
                    raise DamageProviderViolationError(
                        f"provider {spec.provider_key} 返回了非法 damage modifier term"
                    )
                self._validate_term(spec, term, query)
                if spec.display_name is not None and term.provider_display_name is None:
                    term = replace(term, provider_display_name=spec.display_name)
                terms.append(term)
        return self._apply_stacking(tuple(sorted(terms, key=_term_sort_key)))

    def _validate_term(
        self,
        spec: DamageModifierProviderSpec,
        term: DamageModifierTerm,
        query: DamageQuery,
    ) -> None:
        """校验 provider 返回的 term 没有越过自身声明。"""

        if term.provider_key != spec.provider_key:
            raise DamageProviderViolationError(
                f"provider {spec.provider_key} 返回了其他 provider_key：{term.provider_key}"
            )
        if term.stage not in spec.writes:
            raise DamageProviderViolationError(
                f"provider {spec.provider_key} 未声明写入阶段：{term.stage.value}"
            )
        if term.component_key is not None and term.component_key not in {
            item.component_key for item in query.request.scaling_terms
        }:
            raise DamageProviderViolationError(
                f"provider {spec.provider_key} 引用了未知 component：{term.component_key}"
            )

    def _apply_stacking(
        self,
        terms: tuple[DamageModifierTerm, ...],
    ) -> DamageModifierCollection:
        """对已排序的候选 term 应用 stacking group 选择规则。"""

        applied: list[DamageModifierTerm] = []
        rejected: list[DamageModifierTerm] = []
        grouped: dict[str, list[DamageModifierTerm]] = {}
        for term in terms:
            if term.stacking_group is None:
                applied.append(term)
                continue
            grouped.setdefault(term.stacking_group, []).append(term)

        for group_key in sorted(grouped):
            definition = self._stacking_groups.get(group_key)
            if definition is None:
                raise ConflictingDamageModifierError(
                    f"damage modifier 引用了未定义 stacking group：{group_key}"
                )
            candidates = grouped[group_key]
            if any(term.stage is not definition.stage for term in candidates):
                raise ConflictingDamageModifierError(
                    f"damage stacking group {group_key} 的 stage 不一致"
                )
            selector = max if definition.policy is DamageModifierStackingPolicy.HIGHEST else min
            selected_value = selector(term.value for term in candidates)
            selected = next(term for term in candidates if term.value == selected_value)
            applied.append(selected)
            rejected.extend(term for term in candidates if term is not selected)

        return DamageModifierCollection(
            tuple(sorted(applied, key=_term_sort_key)),
            tuple(sorted(rejected, key=_term_sort_key)),
        )


def _term_sort_key(term: DamageModifierTerm) -> tuple[object, ...]:
    """返回伤害修饰项跨 provider 的确定性排序键。"""

    return (
        term.stage.value,
        term.component_key or "",
        term.provider_key,
        term.source_ref.kind.value,
        term.source_ref.source_key,
        term.source_ref.instance_id or "",
        term.stacking_group or "",
        term.audit_tags,
        term.value,
    )
