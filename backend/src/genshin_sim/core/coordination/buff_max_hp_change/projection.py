"""Buff 计划投影视图与动态最大生命投影解析。"""

from __future__ import annotations

from dataclasses import replace

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQuery,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSubjectRef,
    TraceLevel,
)
from genshin_sim.core.attributes.indexes import ModifierProviderIndex
from genshin_sim.core.coordination.buff_max_hp_change.models import BuffProjectionMode
from genshin_sim.core.systems.buff.models import BuffMutationPlan, BuffRecord
from genshin_sim.core.systems.buff.providers import BuffAttributeModifierProvider
from genshin_sim.core.systems.buff.store import BuffStore


class ProjectedBuffReader:
    """以未提交 Buff 计划为叠加层的 `BuffReader` 只读投影。

    视图不推进状态、不提交计划、不发布事件；`BEFORE` 模式把计划
    `expected_records` 视为在边界帧仍然活动，`AFTER` 模式叠加计划
    `replacement_records`。两种模式都按真实半开区间规则过滤其余记录。
    """

    def __init__(
        self,
        store: BuffStore,
        plan: BuffMutationPlan,
        mode: BuffProjectionMode,
    ) -> None:
        self._store = store
        self._plan = plan
        self._mode = mode

    def active(
        self,
        frame: int,
        target_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[BuffRecord, ...]:
        records = {record.instance_ref: record for record in self._store.records}
        if self._mode is BuffProjectionMode.AFTER:
            for replacement in self._plan.replacement_records:
                records[replacement.instance_ref] = replacement
        boundary_refs = frozenset(record.instance_ref for record in self._plan.expected_records)
        return tuple(
            sorted(
                (
                    record
                    for record in records.values()
                    if (
                        record.is_active_at(frame)
                        or (
                            self._mode is BuffProjectionMode.BEFORE
                            and record.instance_ref in boundary_refs
                        )
                    )
                    and (target_ref is None or record.state.target_ref == target_ref)
                    and (
                        definition_key is None or record.definition.definition_key == definition_key
                    )
                    and (mechanic_key is None or record.definition.mechanic_key == mechanic_key)
                ),
                key=lambda item: item.instance_ref,
            )
        )


class ProjectedBuffMaxHpResolver:
    """用计划投影视图解析 `stat.hp.max` 旧值与新值的窄解析入口。

    投影解析复用真实解析器的定义、基础属性与全部非 Buff provider，
    仅把读取 Buff 记录的 `BuffAttributeModifierProvider` 换成以投影
    视图为 reader 的等价实例，保证新旧两侧走同一确定性算法。
    """

    def __init__(self, attribute_resolver: AttributeResolver, buff_store: BuffStore) -> None:
        self._resolver = attribute_resolver
        self._store = buff_store
        providers = attribute_resolver.modifier_index.providers
        self._buff_providers = tuple(
            provider
            for provider in providers
            if isinstance(provider, BuffAttributeModifierProvider)
        )
        self._other_providers = tuple(
            provider
            for provider in providers
            if not isinstance(provider, BuffAttributeModifierProvider)
        )

    def resolve_max_hp_pair(
        self,
        subject_ref: AttributeSubjectRef,
        frame: int,
        plan: BuffMutationPlan,
    ) -> tuple[float, float]:
        before = self._resolve(subject_ref, frame, plan, BuffProjectionMode.BEFORE)
        after = self._resolve(subject_ref, frame, plan, BuffProjectionMode.AFTER)
        return (before, after)

    def _resolve(
        self,
        subject_ref: AttributeSubjectRef,
        frame: int,
        plan: BuffMutationPlan,
        mode: BuffProjectionMode,
    ) -> float:
        resolver = self._resolver
        if self._buff_providers:
            reader = ProjectedBuffReader(self._store, plan, mode)
            projected_providers = tuple(
                BuffAttributeModifierProvider(provider.definition, reader)
                for provider in self._buff_providers
            )
            resolver = replace(
                self._resolver,
                modifier_index=ModifierProviderIndex(
                    (*self._other_providers, *projected_providers),
                    registry=self._resolver.definitions,
                ),
            )
        resolution = resolver.resolve(
            AttributeQuery(subject_ref, STAT_HP_MAX, frame=frame),
            options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
        )
        return resolution.final_value
