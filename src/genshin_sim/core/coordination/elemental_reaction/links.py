"""Aura 与 ReactionState 的中立 Link 不变量。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraInteractionPort,
    ReactionStateInteractionPort,
)
from genshin_sim.core.elements import AuraKind, ElementalStateLinkRef, ElementalSubjectRef
from genshin_sim.core.systems.aura import (
    AuraCommitReceipt,
    AuraComponent,
    AuraDecayMode,
    AuraMutationPlan,
    AuraTargetRecord,
)
from genshin_sim.core.systems.reaction import (
    BurningState,
    FrozenState,
    QuickenState,
    ReactionStateCommitReceipt,
    ReactionStateMutationPlan,
    ReactionStateRecord,
)


class ElementalStateLinkConflictError(ValueError):
    """Aura Component 与 ReactionState 的 Link 不变量被破坏时抛出。"""


class BurningStateLinkConflictError(ElementalStateLinkConflictError):
    """燃元素、类草 Aura 与 BurningState 的 Link 投影不完整时抛出。"""


class QuickenStateLinkConflictError(ElementalStateLinkConflictError):
    """激元素、QuickenState 与 Quicken Link 投影不完整时抛出。"""


@dataclass(frozen=True, slots=True)
class FrozenStateLinkBatchReceipt:
    aura_receipt: AuraCommitReceipt
    reaction_state_receipt: ReactionStateCommitReceipt


class ElementalStateLinkBatchCoordinator:
    """提交一对 Aura / ReactionState 计划的共享原子提交骨架。"""

    def __init__(
        self,
        aura_runtime: AuraInteractionPort,
        reaction_runtime: ReactionStateInteractionPort,
        link_validator: Callable[
            [Iterable[AuraTargetRecord], Iterable[ReactionStateRecord]], None
        ],
    ) -> None:
        self.aura_runtime = aura_runtime
        self.reaction_runtime = reaction_runtime
        self._link_validator = link_validator

    def commit_prevalidated(
        self,
        aura_plan: AuraMutationPlan,
        state_plan: ReactionStateMutationPlan,
    ) -> FrozenStateLinkBatchReceipt:
        self.validate(aura_plan, state_plan)
        aura_receipt = self.aura_runtime.commit_prevalidated(aura_plan)
        state_receipt = self.reaction_runtime.commit_prevalidated_state_plan(state_plan)
        return FrozenStateLinkBatchReceipt(aura_receipt, state_receipt)

    def validate(
        self,
        aura_plan: AuraMutationPlan,
        state_plan: ReactionStateMutationPlan,
    ) -> None:
        """在跨 Store 写入前校验 Aura/ReactionState Link 的完整性。"""

        if aura_plan.frame != state_plan.frame:
            raise ElementalStateLinkConflictError("Aura 与 ReactionState Link 计划帧不一致")
        self.aura_runtime.validate(aura_plan)
        self.reaction_runtime.validate_state_plan(state_plan)
        self._link_validator(
            aura_plan.replacements,
            _state_records_after(self.reaction_runtime.state_records, state_plan),
        )


class FrozenStateLinkBatchCoordinator(ElementalStateLinkBatchCoordinator):
    """冻结使用共享提交骨架与其强类型 Link validator。"""

    def __init__(
        self,
        aura_runtime: AuraInteractionPort,
        reaction_runtime: ReactionStateInteractionPort,
    ) -> None:
        super().__init__(aura_runtime, reaction_runtime, validate_frozen_state_links)


class BurningStateLinkBatchCoordinator(ElementalStateLinkBatchCoordinator):
    """燃烧使用共享提交骨架和全部元素状态 Link validator。"""

    def __init__(
        self,
        aura_runtime: AuraInteractionPort,
        reaction_runtime: ReactionStateInteractionPort,
    ) -> None:
        super().__init__(aura_runtime, reaction_runtime, validate_elemental_state_links)


class QuickenStateLinkBatchCoordinator(ElementalStateLinkBatchCoordinator):
    """激元素使用共享提交骨架和全部元素状态 Link validator。"""

    def __init__(
        self,
        aura_runtime: AuraInteractionPort,
        reaction_runtime: ReactionStateInteractionPort,
    ) -> None:
        super().__init__(aura_runtime, reaction_runtime, validate_elemental_state_links)


def validate_frozen_state_links(
    aura_records: Iterable[AuraTargetRecord],
    state_records: Iterable[ReactionStateRecord],
) -> None:
    """验证同一主体上的一条派生冻元素与一条 FrozenState 完整配对。"""

    aura_by_link: dict[ElementalStateLinkRef, AuraTargetRecord] = {}
    for record in aura_records:
        for component in record.components:
            if component.aura_kind is not AuraKind.FROZEN:
                continue
            if len(component.state_link_refs) != 1:
                raise ElementalStateLinkConflictError("冻元素 Aura 必须恰好携带一条 Link")
            link_ref = component.state_link_refs[0]
            if link_ref in aura_by_link:
                raise ElementalStateLinkConflictError("同一 Link 不能指向多个冻元素 Component")
            aura_by_link[link_ref] = record

    state_by_link: dict[ElementalStateLinkRef, FrozenState] = {}
    for record in state_records:
        if not isinstance(record, FrozenState):
            continue
        if record.state_link_ref in state_by_link:
            raise ElementalStateLinkConflictError("同一 Link 不能指向多个 FrozenState")
        state_by_link[record.state_link_ref] = record

    if set(aura_by_link) != set(state_by_link):
        raise ElementalStateLinkConflictError("Aura 与 ReactionState 存在悬空 Link")
    for link_ref, aura_record in aura_by_link.items():
        state = state_by_link[link_ref]
        if aura_record.subject_ref != state.subject_ref:
            raise ElementalStateLinkConflictError("Aura 与 FrozenState Link 主体不一致")


def validate_burning_state_links(
    aura_records: Iterable[AuraTargetRecord],
    state_records: Iterable[ReactionStateRecord],
) -> None:
    """验证燃元素、普通草和/或激元素与 BurningState 的完整 Link 投影。"""

    aura_by_subject = {record.subject_ref: record for record in aura_records}
    states = tuple(record for record in state_records if isinstance(record, BurningState))
    seen_subjects: set[object] = set()
    for state in states:
        if state.subject_ref in seen_subjects:
            raise ElementalStateLinkConflictError("同一主体不能有多个 BurningState")
        seen_subjects.add(state.subject_ref)
        aura_record = aura_by_subject.get(state.subject_ref)
        if aura_record is None:
            raise BurningStateLinkConflictError("BurningState 缺少同主体 Aura Record")
        burning = aura_record.component_for(AuraKind.BURNING)
        dendro_like = tuple(
            component
            for component in aura_record.components
            if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
            and state.burning_aura_link_ref in component.state_link_refs
        )
        if burning is None or not dendro_like:
            raise BurningStateLinkConflictError("BurningState 缺少燃元素或类草 Aura")
        if burning.state_link_refs != (state.burning_aura_link_ref,):
            raise BurningStateLinkConflictError("燃元素 Aura Link 与 BurningState 不一致")
        linked_refs = tuple(
            sorted(
                {
                    link_ref
                    for component in dendro_like
                    for link_ref in component.state_link_refs
                },
                key=lambda item: item.link_key,
            )
        )
        if state.dendro_like_link_refs != linked_refs:
            raise BurningStateLinkConflictError("BurningState 的类草 Link 与 Aura 不一致")
        if any(
            component.decay_mode is not AuraDecayMode.REACTION_MANAGED
            for component in dendro_like
        ):
            raise BurningStateLinkConflictError("类草 Aura 必须由 BurningState 管理消耗")

    burning_aura_subjects = {
        record.subject_ref
        for record in aura_records
        if record.component_for(AuraKind.BURNING) is not None
    }
    state_subjects = {state.subject_ref for state in states}
    if burning_aura_subjects != state_subjects:
        raise BurningStateLinkConflictError("Aura 与 BurningState 存在悬空 Link")


def validate_quicken_state_links(
    aura_records: Iterable[AuraTargetRecord],
    state_records: Iterable[ReactionStateRecord],
) -> None:
    """验证每个活动激元素与 QuickenState 的唯一同主体 Link。"""

    quicken_components: dict[ElementalSubjectRef, tuple[AuraTargetRecord, AuraComponent]] = {}
    for record in aura_records:
        component = record.component_for(AuraKind.QUICKEN)
        if component is not None:
            quicken_components[record.subject_ref] = (record, component)

    states = tuple(record for record in state_records if isinstance(record, QuickenState))
    state_by_subject = {state.subject_ref: state for state in states}
    if len(state_by_subject) != len(states):
        raise QuickenStateLinkConflictError("同一主体不能有多个 QuickenState")
    if set(quicken_components) != set(state_by_subject):
        raise QuickenStateLinkConflictError("激元素 Aura 与 QuickenState 存在悬空 Link")

    quicken_links = {state.quicken_aura_link_ref for state in states}
    for subject_ref, (_, component) in quicken_components.items():
        state = state_by_subject[subject_ref]
        if state.quicken_aura_link_ref not in component.state_link_refs:
            raise QuickenStateLinkConflictError("激元素 Aura 缺少 QuickenState Link")
        if len(component.contributions) != 1:
            raise QuickenStateLinkConflictError("激元素 Aura 必须恰好保留一条派生贡献")

    for record in aura_records:
        for component in record.components:
            if component.aura_kind is AuraKind.QUICKEN:
                continue
            if set(component.state_link_refs) & quicken_links:
                raise QuickenStateLinkConflictError("普通 Aura 不能携带 QuickenState Link")


def validate_elemental_state_links(
    aura_records: Iterable[AuraTargetRecord],
    state_records: Iterable[ReactionStateRecord],
) -> None:
    """组合当前所有已注册 Aura/ReactionState Link 不变量。"""

    aura_records = tuple(aura_records)
    state_records = tuple(state_records)
    validate_frozen_state_links(aura_records, state_records)
    validate_burning_state_links(aura_records, state_records)
    validate_quicken_state_links(aura_records, state_records)


def _state_records_after(
    current_records: Iterable[ReactionStateRecord],
    plan: ReactionStateMutationPlan,
) -> tuple[ReactionStateRecord, ...]:
    records = {record.slot_key: record for record in current_records}
    for slot_key in plan.removed_slot_keys:
        records.pop(slot_key, None)
    for record in plan.replacement_records:
        records[record.slot_key] = record
    return tuple(records.values())
