"""普通燃烧的帧内草特殊消费与周期根物化。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from genshin_sim.core.coordination.elemental_reaction.links import (
    BurningStateLinkBatchCoordinator,
    BurningStateLinkConflictError,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraFramePort,
    ReactionStateInteractionPort,
)
from genshin_sim.core.elements import AuraAmount, AuraKind
from genshin_sim.core.systems.reaction.states import (
    BurningCycleRootWork,
    BurningState,
)

DENDRO_DEPLETION_PER_FRAME = AuraAmount(Fraction(1, 150))
DAMAGE_TICK_INTERVAL_FRAMES = 15
PYRO_APPLICATION_INTERVAL_FRAMES = 120


@dataclass(frozen=True, slots=True)
class BurningStateFrameNormalization:
    """单帧燃烧状态适配的已提交 Aura 调整与待结算根工作。"""

    reaction_managed_aura_adjustment_refs: tuple[str, ...] = ()
    scheduled_roots: tuple[BurningCycleRootWork, ...] = ()


class BurningStateFrameAdapter:
    """以 Aura/ReactionState 原子计划执行燃烧的帧内规则。"""

    def __init__(
        self,
        aura_runtime: AuraFramePort,
        reaction_runtime: ReactionStateInteractionPort,
    ) -> None:
        self.aura_runtime = aura_runtime
        self.reaction_runtime = reaction_runtime

    def normalize(
        self,
        context,
        *,
        frame: int,
        elapsed_frames: int,
        root_order_start: int = 0,
    ) -> BurningStateFrameNormalization:
        if elapsed_frames < 0:
            raise ValueError("燃烧帧规范化的 elapsed_frames 不能为负数")
        states = tuple(
            record
            for record in self.reaction_runtime.state_records
            if isinstance(record, BurningState)
        )
        if not states:
            return BurningStateFrameNormalization()

        batch_id = f"burning-frame:{frame}"
        aura_planner = self.aura_runtime.begin_batch(frame, batch_id)
        state_planner = self.reaction_runtime.begin_state_batch(frame, batch_id)
        adjustment_refs: list[str] = []
        roots: list[BurningCycleRootWork] = []

        for state in states:
            burning, dendro_like = self._linked_components(aura_planner, state)
            if elapsed_frames:
                planned_consumption = DENDRO_DEPLETION_PER_FRAME * elapsed_frames
                depleted_kinds = {
                    component.aura_kind
                    for component in dendro_like
                    if component.current_amount <= planned_consumption
                }
                if len(depleted_kinds) == len(dendro_like):
                    cleanup_ref = (
                        f"reaction-state:{state.instance_ref.value}:frame:{frame}:"
                        "burning:burning-cleanup"
                    )
                    aura_planner.consume(
                        interaction_id=cleanup_ref,
                        subject_ref=state.subject_ref,
                        aura_kind=AuraKind.BURNING,
                        amount=burning.current_amount,
                    )
                    adjustment_refs.append(cleanup_ref)
                for component in dendro_like:
                    consumption_ref = (
                        f"reaction-state:{state.instance_ref.value}:frame:{frame}:"
                        f"burning:{component.aura_kind.value}-consumption"
                    )
                    aura_planner.consume(
                        interaction_id=consumption_ref,
                        subject_ref=state.subject_ref,
                        aura_kind=component.aura_kind,
                        amount=component.current_amount.minimum(planned_consumption),
                    )
                    adjustment_refs.append(consumption_ref)
                    if (
                        component.aura_kind is AuraKind.QUICKEN
                        and component.aura_kind in depleted_kinds
                    ):
                        quicken = state_planner.quicken_for(state.subject_ref)
                        if quicken is not None:
                            state_planner.remove_quicken(
                                subject_ref=state.subject_ref,
                                expected_instance_ref=quicken.instance_ref,
                            )

                remaining_dendro_like = self._linked_components_or_empty(aura_planner, state)
                if not remaining_dendro_like:
                    state_planner.remove_burning(
                        subject_ref=state.subject_ref,
                        expected_instance_ref=state.instance_ref,
                    )
                    continue

                if depleted_kinds:
                    state = replace(
                        state,
                        dendro_like_link_refs=self._link_refs_for(remaining_dendro_like),
                        next_dendro_like_depletion_frame=(
                            frame
                            + self._depletion_frames(
                                min(
                                    component.current_amount
                                    for component in remaining_dendro_like
                                )
                            )
                        ),
                        revision=state.revision + 1,
                    )
                    state_planner.replace_burning(state)

            damage_due = state.next_damage_tick_frame == frame
            pyro_due = state.next_pyro_application_frame == frame
            if not damage_due and not pyro_due:
                continue
            root = BurningCycleRootWork(
                work_id=(
                    f"reaction-state:{state.instance_ref.value}:frame:{frame}:"
                    f"burning:damage:{state.next_damage_tick_index if damage_due else 0}:"
                    f"pyro_application:{state.next_pyro_application_index if pyro_due else 0}"
                ),
                frame=frame,
                root_order=root_order_start + len(roots),
                state_instance_ref=state.instance_ref,
                subject_ref=state.subject_ref,
                damage_tick_index=(state.next_damage_tick_index if damage_due else None),
                pyro_application_index=(
                    state.next_pyro_application_index if pyro_due else None
                ),
            )
            roots.append(root)
            state_planner.replace_burning(
                replace(
                    state,
                    next_damage_tick_frame=(
                        frame + DAMAGE_TICK_INTERVAL_FRAMES
                        if damage_due
                        else state.next_damage_tick_frame
                    ),
                    next_damage_tick_index=(
                        state.next_damage_tick_index + 1
                        if damage_due
                        else state.next_damage_tick_index
                    ),
                    next_pyro_application_frame=(
                        frame + PYRO_APPLICATION_INTERVAL_FRAMES
                        if pyro_due
                        else state.next_pyro_application_frame
                    ),
                    next_pyro_application_index=(
                        state.next_pyro_application_index + 1
                        if pyro_due
                        else state.next_pyro_application_index
                    ),
                    revision=state.revision + 1,
                )
            )

        aura_plan = aura_planner.seal()
        state_plan = state_planner.seal()
        receipt = BurningStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        ).commit_prevalidated(aura_plan, state_plan)
        if context is not None and state_plan.changes:
            with self.aura_runtime.event_publication_guard():
                self.reaction_runtime.publish_committed_state_facts(
                    context,
                    receipt.reaction_state_receipt,
                )
        return BurningStateFrameNormalization(tuple(adjustment_refs), tuple(roots))

    @staticmethod
    def _linked_components(aura_planner, state: BurningState):
        view = aura_planner.view(state.subject_ref)
        burning = view.component_for(AuraKind.BURNING)
        dendro_like = BurningStateFrameAdapter._linked_components_or_empty(aura_planner, state)
        if (
            burning is None
            or burning.state_link_refs != (state.burning_aura_link_ref,)
            or not dendro_like
            or BurningStateFrameAdapter._link_refs_for(dendro_like)
            != state.dendro_like_link_refs
        ):
            raise BurningStateLinkConflictError("燃烧帧缺少完整的燃元素、类草 Aura 与 Link 投影")
        return burning, dendro_like

    @staticmethod
    def _linked_components_or_empty(aura_planner, state: BurningState):
        return tuple(
            component
            for component in aura_planner.view(state.subject_ref).components
            if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
            and state.burning_aura_link_ref in component.state_link_refs
            and component.decay_mode.value == "reaction_managed"
        )

    @staticmethod
    def _link_refs_for(components):
        return tuple(
            sorted(
                {
                    link_ref
                    for component in components
                    for link_ref in component.state_link_refs
                },
                key=lambda item: item.link_key,
            )
        )

    @staticmethod
    def _depletion_frames(amount: AuraAmount) -> int:
        return int(-(-amount.value // DENDRO_DEPLETION_PER_FRAME.value))
