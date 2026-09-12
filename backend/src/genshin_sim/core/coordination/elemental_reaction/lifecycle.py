"""结晶晶片的绑定 State/Space 生命周期协调。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from genshin_sim.core.attributes import (
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    CrystallizeShieldGrantPort,
    ReactionSpatialPlanningPort,
    ReactionStateInteractionPort,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    publish_space_entity_facts,
    validate_dendro_core_space_terminalizations,
    validate_lunar_cage_space_terminalizations,
    validate_lunar_storm_cloud_space_terminalizations,
    validate_polestar_field_space_terminalizations,
    validate_reaction_state_space_terminalizations,
    validate_stellar_swirl_vortex_space_terminalizations,
)
from genshin_sim.core.elements import Element, ElementalSourceRef
from genshin_sim.core.systems.reaction import (
    CapturedCrystallizeShieldBasis,
    CrystallizeShardLifecycleState,
    CrystallizeShardState,
    DendroCoreState,
    DendroCoreTerminationReason,
    LunarCageState,
    LunarStormCloudState,
    PolestarFieldState,
    ReactionStateInstanceRef,
    ReactionStateLifecycleOperation,
    ReactionStateLifecycleWork,
    StellarSwirlVortexState,
)
from genshin_sim.core.systems.reaction.mechanics.bloom import (
    bloom_explosion_terminal_reaction,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl import (
    stellar_swirl_explosion_effect_group,
)
from genshin_sim.core.systems.reaction.models import ReactionEffectGroup, ReactionOccurrence
from genshin_sim.core.systems.shield import (
    ShieldCapacityFormula,
    ShieldElement,
    ShieldGrantPolicy,
    ShieldGrantRequest,
    ShieldGrantResult,
    ShieldProtectionRef,
)

CRYSTALLIZE_SHIELD_DURATION_FRAMES = 900
CRYSTALLIZE_SHIELD_MECHANIC_KEY = "reaction.crystallize.shield"
CRYSTALLIZE_SHIELD_HANDLER_KEY = "reaction_handler.crystallize.shield"
CRYSTALLIZE_SHIELD_CONFLICT_KEY = "reaction.crystallize.shield"


class ReactionBoundEntityLifecycleError(RuntimeError):
    """绑定 Reaction State 和 Space 实体的生命周期不能完成。"""


class CrystallizeShardNotFoundError(ReactionBoundEntityLifecycleError):
    """请求的晶片 State 不存在。"""


class CrystallizeShardAlreadyPickedError(ReactionBoundEntityLifecycleError):
    """请求的晶片已经被拾取。"""


class CrystallizeShardExpiredError(ReactionBoundEntityLifecycleError):
    """请求的晶片已经到期。"""


class CrystallizeShardOperationConflictError(ReactionBoundEntityLifecycleError):
    """同一操作标识被用于不同的拾取请求。"""


@dataclass(frozen=True, slots=True)
class CrystallizeShardPickupRequest:
    operation_id: str
    frame: int
    shard_ref: ReactionStateInstanceRef
    protection_ref: ShieldProtectionRef = ShieldProtectionRef.active_team()

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("operation_id 必须是非空字符串")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.shard_ref, ReactionStateInstanceRef):
            raise TypeError("shard_ref 必须是 ReactionStateInstanceRef")
        if not isinstance(self.protection_ref, ShieldProtectionRef):
            raise TypeError("protection_ref 必须是 ShieldProtectionRef")


@dataclass(frozen=True, slots=True)
class CrystallizeShardPickupResult:
    shard_ref: ReactionStateInstanceRef
    element: Element
    trigger_source: ElementalSourceRef
    captured_shield_basis: CapturedCrystallizeShieldBasis
    created_frame: int
    expires_at_frame: int
    picked_frame: int
    shield_grant: ShieldGrantResult


@dataclass(frozen=True, slots=True)
class DendroCoreExpiryResult:
    """到期核心的已提交生命周期工作及其下一轮爆炸声明。"""

    works: tuple[ReactionStateLifecycleWork, ...]
    effect_groups: tuple[ReactionEffectGroup, ...]
    occurrences: tuple[ReactionOccurrence, ...] = ()


class DendroCoreExpiryCoordinator:
    """在到期帧原子移除活动草原核，并冻结爆炸中心位置。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> DendroCoreExpiryResult:
        if not works:
            return DendroCoreExpiryResult((), ())
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"dendro-core-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"dendro-core-expiry:{frame}",
            frame=frame,
        )
        effect_groups: list[ReactionEffectGroup] = []
        occurrences: list[ReactionOccurrence] = []
        for state in states:
            state_planner.remove_dendro_core(instance_ref=state.instance_ref)
            entity = space_planner.prepare_remove(state.space_entity_ref)
            terminal = bloom_explosion_terminal_reaction(
                core=state,
                center=entity.position,
                effect_group_ref=(f"dendro-core-expiry:{state.instance_ref.value}:frame:{frame}"),
                reason=DendroCoreTerminationReason.EXPIRED,
            )
            occurrences.append(terminal.occurrence)
            assert terminal.effect_group is not None
            effect_groups.append(terminal.effect_group)
        state_plan = state_planner.seal()
        space_plan = space_planner.seal()
        self.reaction_state_port.validate_state_plan(state_plan)
        self.spatial_planning_port.validate(space_plan)
        validate_dendro_core_space_terminalizations(state_plan, space_plan)
        state_receipt = self.reaction_state_port.commit_prevalidated_state_plan(state_plan)
        self.spatial_planning_port.commit_prevalidated(space_plan)
        if context is not None:
            with self.spatial_planning_port.event_publication_guard():
                self.reaction_state_port.publish_committed_state_facts(context, state_receipt)
                publish_space_entity_facts(context, space_plan)
        return DendroCoreExpiryResult(tuple(works), tuple(effect_groups), tuple(occurrences))

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[DendroCoreState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[DendroCoreState] = []
        for work in works:
            if (
                work.frame != frame
                or work.operation is not ReactionStateLifecycleOperation.EXPIRE
                or work.state_slot.value != "dendro_core"
            ):
                raise ReactionBoundEntityLifecycleError("草原核到期 work 不一致")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("草原核到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.dendro_core_state_for(work.state_instance_ref)
            if state is None:
                raise ReactionBoundEntityLifecycleError("到期草原核 State 不存在")
            if (
                state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError("到期草原核 State 与 lifecycle work 不一致")
            states.append(state)
        return tuple(states)


class ReactionBoundEntityExpiryCoordinator:
    """只终结到期绑定 State 并移除对应 Space 实体。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        if not works:
            return ()
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"reaction-bound-entity-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"reaction-bound-entity-expiry:{frame}",
            frame=frame,
        )
        for state in states:
            state_planner.terminalize_crystallize_shard(
                instance_ref=state.instance_ref,
                lifecycle_state=CrystallizeShardLifecycleState.EXPIRED,
            )
            space_planner.prepare_remove(state.space_entity_ref)
        _commit_bound_entity_terminalization(
            self.reaction_state_port,
            self.spatial_planning_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
        )
        return works

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[CrystallizeShardState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[CrystallizeShardState] = []
        for work in works:
            if work.frame != frame:
                raise ReactionBoundEntityLifecycleError("到期 work frame 与批次不一致")
            if work.operation is not ReactionStateLifecycleOperation.EXPIRE:
                raise ReactionBoundEntityLifecycleError("不支持的绑定实体生命周期操作")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.crystallize_shard_state_for(work.state_instance_ref)
            if state is None:
                raise CrystallizeShardNotFoundError("到期晶片 State 不存在")
            if (
                state.lifecycle_state is not CrystallizeShardLifecycleState.ACTIVE
                or state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError("到期晶片 State 与 lifecycle work 不一致")
            states.append(state)
        return tuple(states)


class LunarStormCloudExpiryCoordinator:
    """在到期帧原子移除雷暴云 State 与对应 Space 实体。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        if not works:
            return ()
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"lunar-storm-cloud-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"lunar-storm-cloud-expiry:{frame}",
            frame=frame,
        )
        for state in states:
            state_planner.remove_lunar_storm_cloud(instance_ref=state.instance_ref)
            space_planner.prepare_remove(state.space_entity_ref)
        _commit_lunar_storm_cloud_expiry(
            self.reaction_state_port,
            self.spatial_planning_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
        )
        return works

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[LunarStormCloudState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[LunarStormCloudState] = []
        for work in works:
            if (
                work.frame != frame
                or work.operation is not ReactionStateLifecycleOperation.EXPIRE
                or work.state_slot.value != "lunar_storm_cloud"
            ):
                raise ReactionBoundEntityLifecycleError("雷暴云到期 work 不一致")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("雷暴云到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.lunar_storm_cloud_state_for(work.state_instance_ref)
            if state is None:
                raise ReactionBoundEntityLifecycleError("到期雷暴云 State 不存在")
            if (
                state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError("到期雷暴云 State 与 lifecycle work 不一致")
            states.append(state)
        return tuple(states)


class PolestarFieldExpiryCoordinator:
    """在到期帧原子移除极星辉域 State、Space 实体与队伍共享计数。

    领域到期意味着星超导共享会话结束：辉映·星超导 Buff 的统一移除
    由后续 Buff 系统接线承担，此处先终结 Reaction 侧共享状态。
    """

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        if not works:
            return ()
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"polestar-field-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"polestar-field-expiry:{frame}",
            frame=frame,
        )
        removed_team_refs: set[str] = set()
        for state in states:
            state_planner.remove_polestar_field(instance_ref=state.instance_ref)
            space_planner.prepare_remove(state.space_entity_ref)
            removed_team_refs.add(state.team_ref)
        for team_ref in sorted(removed_team_refs):
            if state_planner.stellar_conduct_counter_for(team_ref) is not None:
                state_planner.remove_stellar_conduct_counter(team_ref=team_ref)
        _commit_polestar_field_expiry(
            self.reaction_state_port,
            self.spatial_planning_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
        )
        return works

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[PolestarFieldState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[PolestarFieldState] = []
        for work in works:
            if (
                work.frame != frame
                or work.operation is not ReactionStateLifecycleOperation.EXPIRE
                or work.state_slot.value != "stellar_conduct_field"
            ):
                raise ReactionBoundEntityLifecycleError("极星辉域到期 work 不一致")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("极星辉域到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.polestar_field_state_for(work.state_instance_ref)
            if state is None:
                raise ReactionBoundEntityLifecycleError("到期极星辉域 State 不存在")
            if (
                state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError(
                    "到期极星辉域 State 与 lifecycle work 不一致"
                )
            states.append(state)
        return tuple(states)


@dataclass(frozen=True, slots=True)
class StellarSwirlVortexExpiryResult:
    """到期风旋的已提交生命周期工作及其下一轮爆炸声明。"""

    works: tuple[ReactionStateLifecycleWork, ...]
    effect_groups: tuple[ReactionEffectGroup, ...] = ()


class StellarSwirlVortexExpiryCoordinator:
    """在到期帧原子移除星辉风旋 State 与 Space 实体并声明冰爆炸。

    风旋爆炸不被视为触发反应：Effect group 以生命周期内最后一次星扩散·风
    的 occurrence 为因果锚点，伤害源与参与者来自风旋账本，无跨风旋继承。
    """

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> StellarSwirlVortexExpiryResult:
        if not works:
            return StellarSwirlVortexExpiryResult((), ())
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"stellar-swirl-vortex-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"stellar-swirl-vortex-expiry:{frame}",
            frame=frame,
        )
        effect_groups: list[ReactionEffectGroup] = []
        for state in states:
            state_planner.remove_stellar_swirl_vortex(instance_ref=state.instance_ref)
            removed_entity = space_planner.prepare_remove(state.space_entity_ref)
            effect_groups.append(
                stellar_swirl_explosion_effect_group(
                    effect_group_ref=(
                        f"stellar-swirl-vortex-expiry:{state.instance_ref.value}:frame:{frame}"
                    ),
                    parent_occurrence_ref=state.last_reaction_occurrence_ref,
                    anchor_position=removed_entity.position,
                    level=state.level,
                    trigger_source_ref=state.last_reaction_source_ref,
                    participant_refs=tuple(entry.participant_ref for entry in state.participants),
                )
            )
        _commit_stellar_swirl_vortex_expiry(
            self.reaction_state_port,
            self.spatial_planning_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
        )
        return StellarSwirlVortexExpiryResult(tuple(works), tuple(effect_groups))

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[StellarSwirlVortexState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[StellarSwirlVortexState] = []
        for work in works:
            if (
                work.frame != frame
                or work.operation is not ReactionStateLifecycleOperation.EXPIRE
                or work.state_slot.value != "stellar_swirl_vortex"
            ):
                raise ReactionBoundEntityLifecycleError("星辉风旋到期 work 不一致")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("星辉风旋到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.stellar_swirl_vortex_state_for(work.state_instance_ref)
            if state is None:
                raise ReactionBoundEntityLifecycleError("到期星辉风旋 State 不存在")
            if (
                state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError(
                    "到期星辉风旋 State 与 lifecycle work 不一致"
                )
            states.append(state)
        return tuple(states)


class LunarCageExpiryCoordinator:
    """在到期帧原子移除月笼 State 与对应 Space 实体。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port

    def expire(
        self,
        context: object,
        *,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        if not works:
            return ()
        states = self._active_states_for_expiry(frame, works)
        state_planner = self.reaction_state_port.begin_state_batch(
            frame,
            f"lunar-cage-expiry:{frame}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"lunar-cage-expiry:{frame}",
            frame=frame,
        )
        for state in states:
            state_planner.remove_lunar_cage(instance_ref=state.instance_ref)
            space_planner.prepare_remove(state.space_entity_ref)
        _commit_lunar_cage_expiry(
            self.reaction_state_port,
            self.spatial_planning_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
        )
        return works

    def _active_states_for_expiry(
        self,
        frame: int,
        works: tuple[ReactionStateLifecycleWork, ...],
    ) -> tuple[LunarCageState, ...]:
        seen_work_refs: set[str] = set()
        seen_state_refs: set[ReactionStateInstanceRef] = set()
        states: list[LunarCageState] = []
        for work in works:
            if (
                work.frame != frame
                or work.operation is not ReactionStateLifecycleOperation.EXPIRE
                or work.state_slot.value != "lunar_cage"
            ):
                raise ReactionBoundEntityLifecycleError("月笼到期 work 不一致")
            if work.work_ref in seen_work_refs or work.state_instance_ref in seen_state_refs:
                raise ReactionBoundEntityLifecycleError("月笼到期 work 重复")
            seen_work_refs.add(work.work_ref)
            seen_state_refs.add(work.state_instance_ref)
            state = self.reaction_state_port.lunar_cage_state_for(work.state_instance_ref)
            if state is None:
                raise ReactionBoundEntityLifecycleError("到期月笼 State 不存在")
            if (
                state.expires_at_frame != frame
                or state.slot_key.slot is not work.state_slot
                or state.slot_key.scope_key != work.scope_key
            ):
                raise ReactionBoundEntityLifecycleError("到期月笼 State 与 lifecycle work 不一致")
            states.append(state)
        return tuple(states)


class CrystallizeShardPickupCoordinator:
    """以 operation_id 幂等地拾取活动晶片，并原子授予结晶护盾。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
        shield_grant_port: CrystallizeShieldGrantPort,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port
        self.shield_grant_port = shield_grant_port
        self._results_by_operation_id: dict[
            str, tuple[CrystallizeShardPickupRequest, CrystallizeShardPickupResult]
        ] = {}
        self._publishing_facts = False

    @property
    def is_publishing_facts(self) -> bool:
        return self._publishing_facts

    def pickup(
        self,
        context: object,
        request: CrystallizeShardPickupRequest,
    ) -> CrystallizeShardPickupResult:
        committed = self._results_by_operation_id.get(request.operation_id)
        if committed is not None:
            committed_request, result = committed
            if committed_request == request:
                return result
            raise CrystallizeShardOperationConflictError("同一晶片拾取 operation_id 对应不同请求")
        state = self.reaction_state_port.crystallize_shard_state_for(request.shard_ref)
        self._validate_pickup_state(state, request)
        assert state is not None
        state_planner = self.reaction_state_port.begin_state_batch(
            request.frame,
            f"reaction-bound-entity-pickup:{request.operation_id}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"reaction-bound-entity-pickup:{request.operation_id}",
            frame=request.frame,
        )
        state_planner.terminalize_crystallize_shard(
            instance_ref=state.instance_ref,
            lifecycle_state=CrystallizeShardLifecycleState.PICKED,
        )
        space_planner.prepare_remove(state.space_entity_ref)
        shield_request = _shield_grant_request_for_crystallize_pickup(state, request)
        shield_plan = self.shield_grant_port.prepare_grant(shield_request)
        state_receipt, shield_receipt = _commit_crystallize_pickup_with_shield(
            self.reaction_state_port,
            self.spatial_planning_port,
            self.shield_grant_port,
            context,
            state_planner.seal(),
            space_planner.seal(),
            shield_plan,
            publishing_owner=self,
        )
        del state_receipt
        result = CrystallizeShardPickupResult(
            shard_ref=state.instance_ref,
            element=state.element,
            trigger_source=state.trigger_source,
            captured_shield_basis=state.captured_shield_basis,
            created_frame=state.created_frame,
            expires_at_frame=state.expires_at_frame,
            picked_frame=request.frame,
            shield_grant=shield_receipt.plan.result,
        )
        self._results_by_operation_id[request.operation_id] = (request, result)
        return result

    @staticmethod
    def _validate_pickup_state(
        state: CrystallizeShardState | None,
        request: CrystallizeShardPickupRequest,
    ) -> None:
        if state is None:
            raise CrystallizeShardNotFoundError("晶片 State 不存在")
        if state.lifecycle_state is CrystallizeShardLifecycleState.PICKED:
            raise CrystallizeShardAlreadyPickedError("晶片已经被拾取")
        if (
            state.lifecycle_state is CrystallizeShardLifecycleState.EXPIRED
            or request.frame >= state.expires_at_frame
        ):
            raise CrystallizeShardExpiredError("晶片已经到期")
        if state.lifecycle_state is not CrystallizeShardLifecycleState.ACTIVE:
            raise ReactionBoundEntityLifecycleError("未知的晶片生命周期状态")


def _commit_bound_entity_terminalization(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    context: object,
    state_plan,
    space_plan,
) -> None:
    """验证两个领域的完整前值后，提交终态 State 与 Space 删除。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    validate_reaction_state_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    if context is not None:
        with spatial_planning_port.event_publication_guard():
            reaction_state_port.publish_committed_state_facts(context, state_receipt)
            publish_space_entity_facts(context, space_plan)


def _commit_lunar_storm_cloud_expiry(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    context: object,
    state_plan,
    space_plan,
) -> None:
    """验证两个领域的完整前值后，提交雷暴云终态与 Space 删除。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    validate_lunar_storm_cloud_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    if context is not None:
        with spatial_planning_port.event_publication_guard():
            reaction_state_port.publish_committed_state_facts(context, state_receipt)
            publish_space_entity_facts(context, space_plan)


def _commit_polestar_field_expiry(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    context: object,
    state_plan,
    space_plan,
) -> None:
    """验证两个领域的完整前值后，提交极星辉域终态、共享计数移除与 Space 删除。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    validate_polestar_field_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    if context is not None:
        with spatial_planning_port.event_publication_guard():
            reaction_state_port.publish_committed_state_facts(context, state_receipt)
            publish_space_entity_facts(context, space_plan)


def _commit_stellar_swirl_vortex_expiry(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    context: object,
    state_plan,
    space_plan,
) -> None:
    """验证两个领域的完整前值后，提交风旋终态与 Space 删除。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    validate_stellar_swirl_vortex_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    if context is not None:
        with spatial_planning_port.event_publication_guard():
            reaction_state_port.publish_committed_state_facts(context, state_receipt)
            publish_space_entity_facts(context, space_plan)


def _commit_lunar_cage_expiry(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    context: object,
    state_plan,
    space_plan,
) -> None:
    """验证两个领域的完整前值后，提交月笼终态与 Space 删除。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    validate_lunar_cage_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    if context is not None:
        with spatial_planning_port.event_publication_guard():
            reaction_state_port.publish_committed_state_facts(context, state_receipt)
            publish_space_entity_facts(context, space_plan)


def _shield_grant_request_for_crystallize_pickup(
    state: CrystallizeShardState,
    request: CrystallizeShardPickupRequest,
) -> ShieldGrantRequest:
    source_key = state.trigger_source.source_key
    if not source_key.startswith("character:"):
        raise ReactionBoundEntityLifecycleError("结晶护盾创建来源必须是 character:* 的触发来源")
    element = {
        Element.PYRO: ShieldElement.PYRO,
        Element.HYDRO: ShieldElement.HYDRO,
        Element.ELECTRO: ShieldElement.ELECTRO,
        Element.CRYO: ShieldElement.CRYO,
    }.get(state.element)
    if element is None:
        raise ReactionBoundEntityLifecycleError("结晶晶片元素不能转换为护盾元素")
    basis = state.captured_shield_basis
    return ShieldGrantRequest(
        grant_id=f"crystallize-shard-shield:{request.operation_id}",
        frame=request.frame,
        mechanic_key=CRYSTALLIZE_SHIELD_MECHANIC_KEY,
        handler_key=CRYSTALLIZE_SHIELD_HANDLER_KEY,
        protection_ref=request.protection_ref,
        creator_ref=AttributeSubjectRef.character(source_key),
        source_context=RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            CRYSTALLIZE_SHIELD_MECHANIC_KEY,
            state.instance_ref.value,
        ),
        element=element,
        duration_frames=CRYSTALLIZE_SHIELD_DURATION_FRAMES,
        grant_formula=ShieldCapacityFormula(flat_absorption=basis.native_absorption),
        grant_policy=ShieldGrantPolicy.REPLACE,
        conflict_key=CRYSTALLIZE_SHIELD_CONFLICT_KEY,
        tags=frozenset({"reaction", "crystallize", "crystallize_shield"}),
    )


def _commit_crystallize_pickup_with_shield(
    reaction_state_port: ReactionStateInteractionPort,
    spatial_planning_port: ReactionSpatialPlanningPort,
    shield_grant_port: CrystallizeShieldGrantPort,
    context: object,
    state_plan,
    space_plan,
    shield_plan,
    *,
    publishing_owner: CrystallizeShardPickupCoordinator,
):
    """预校验并提交晶片 State、Space 删除与 Shield 授予。"""

    reaction_state_port.validate_state_plan(state_plan)
    spatial_planning_port.validate(space_plan)
    shield_grant_port.validate(shield_plan)
    validate_reaction_state_space_terminalizations(state_plan, space_plan)
    state_receipt = reaction_state_port.commit_prevalidated_state_plan(state_plan)
    spatial_planning_port.commit_prevalidated(space_plan)
    shield_receipt = shield_grant_port.commit_prevalidated(shield_plan)
    if context is not None:
        publishing_owner._publishing_facts = True
        try:
            with (
                spatial_planning_port.event_publication_guard(),
                shield_grant_port.event_publication_guard(),
            ):
                reaction_state_port.publish_committed_state_facts(context, state_receipt)
                publish_space_entity_facts(context, space_plan)
                for event in shield_grant_port.events_for(shield_receipt):
                    cast(Any, context).events.publish(event)
        finally:
            publishing_owner._publishing_facts = False
    return state_receipt, shield_receipt
