"""构建阶段的类型化契约模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.core.systems.energy import EnergyElement

if TYPE_CHECKING:
    from genshin_sim.application.assembly.attributes import AttributeRuntimeBundle
    from genshin_sim.application.config import SimulationConfig
    from genshin_sim.assets.models import (
        ArtifactSetAsset,
        ArtifactSetBonus,
        CharacterAsset,
        CharacterLevelStats,
        EffectPayload,
        TalentScalingEntry,
        WeaponAsset,
        WeaponLevelStats,
    )
    from genshin_sim.content.definitions.content_unit import ContentUnit
    from genshin_sim.content.hooks import HookDispatcher
    from genshin_sim.content.models import EventHook, Modifier
    from genshin_sim.core.actions import (
        Action,
        ActionInterpreter,
        ActionInterpreterRegistry,
        ActionManager,
        ActionRegistry,
    )
    from genshin_sim.core.attributes import ModifierStackingGroupDefinition
    from genshin_sim.core.coordination.character_damage_taken import (
        CharacterDamageTakenCoordinator,
    )
    from genshin_sim.core.coordination.elemental_reaction import (
        BloomCoreTriggerCoordinator,
        CrystallizeShardPickupCoordinator,
        ElementalInteractionCoordinator,
        ElementalSettlementCoordinator,
        ElementalStateFrameCoordinator,
        ReactionEligibilityReadPort,
    )
    from genshin_sim.core.entity_states.content_state import ContentStateMount
    from genshin_sim.core.impacts import (
        ImpactDispatcher,
        ImpactFactory,
        ImpactRequestDispatcher,
        ImpactRuntime,
    )
    from genshin_sim.core.simulation import (
        FramePipeline,
        IntentQueue,
        IntentSettlementRuntime,
        SimulationContext,
        Simulator,
    )
    from genshin_sim.core.snapshots import SnapshotRuntime
    from genshin_sim.core.space import CreatedObjectBehavior
    from genshin_sim.core.space.runtime import SpaceRuntime
    from genshin_sim.core.systems.aura import AuraRuntime
    from genshin_sim.core.systems.aura_icd import AuraIcdRuntime
    from genshin_sim.core.systems.buff import (
        BuffDefinition,
        BuffImpactRequestHandler,
        BuffResolver,
        BuffRuntime,
        BuffStore,
    )
    from genshin_sim.core.systems.damage import (
        DamageModifierProvider,
        DamageModifierStackingGroupDefinition,
        DamageRequestHandler,
    )
    from genshin_sim.core.systems.energy import (
        CharacterEnergyStore,
        EnergyImpactRequestHandler,
        EnergyRuntime,
        EnergyTransitQueue,
    )
    from genshin_sim.core.systems.healing import HealingRequestHandler
    from genshin_sim.core.systems.health import HealthRuntime
    from genshin_sim.core.systems.movement import MovementRuntime
    from genshin_sim.core.systems.reaction import ReactionRuntime
    from genshin_sim.core.systems.shield import (
        ShieldImpactRequestHandler,
        ShieldResolver,
        ShieldRuntime,
        ShieldStore,
    )


def energy_element_from_asset(value: str) -> EnergyElement:
    try:
        return EnergyElement(value)
    except ValueError as exc:
        raise InvalidRuntimePayloadError(f"角色元素不支持标准元素能量：{value}") from exc


@dataclass(frozen=True, slots=True)
class RuntimeAssetBundle:
    """数据查询阶段产出的单个槽位资产数据包。"""

    slot: int
    character: CharacterAsset
    character_level_stats: CharacterLevelStats
    weapon: WeaponAsset | None
    weapon_level_stats: WeaponLevelStats | None
    artifact_sets: tuple[ArtifactSetAsset, ...]
    artifact_bonuses: tuple[ArtifactSetBonus, ...]
    effect_payloads: tuple[EffectPayload, ...]
    talent_scalings: tuple[TalentScalingEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeContentBundle:
    """内容编译阶段产出的内容运行时贡献集合。"""

    content_units: tuple[ContentUnit, ...]
    content_state_mounts: tuple[ContentStateMount, ...]
    action_interpreters: dict[int, ActionInterpreter]
    actions: tuple[Action, ...]
    impact_factories: dict[str, ImpactFactory]
    created_object_behaviors: dict[str, CreatedObjectBehavior]
    event_hooks: tuple[EventHook, ...]
    modifiers: tuple[Modifier, ...]
    attribute_stacking_groups: tuple[ModifierStackingGroupDefinition, ...]
    buff_definitions: tuple[BuffDefinition, ...]
    damage_modifier_providers: tuple[DamageModifierProvider, ...]
    damage_modifier_stacking_groups: tuple[DamageModifierStackingGroupDefinition, ...]


@dataclass(slots=True)
class AssembledSimulation:
    """运行时装配阶段产出的可运行世界。"""

    config: SimulationConfig
    context: SimulationContext
    simulator: Simulator
    action_manager: ActionManager
    action_interpreter_registry: ActionInterpreterRegistry
    action_registry: ActionRegistry
    impact_dispatcher: ImpactDispatcher
    impact_request_dispatcher: ImpactRequestDispatcher
    damage_handler: DamageRequestHandler
    aura_runtime: AuraRuntime
    aura_icd_runtime: AuraIcdRuntime
    reaction_runtime: ReactionRuntime
    bloom_core_trigger_coordinator: BloomCoreTriggerCoordinator
    crystallize_shard_pickup_coordinator: CrystallizeShardPickupCoordinator
    elemental_state_frame_coordinator: ElementalStateFrameCoordinator
    elemental_interaction_coordinator: ElementalInteractionCoordinator
    elemental_settlement_coordinator: ElementalSettlementCoordinator
    healing_handler: HealingRequestHandler
    health_runtime: HealthRuntime
    energy_store: CharacterEnergyStore
    energy_transit_queue: EnergyTransitQueue
    energy_runtime: EnergyRuntime
    energy_handler: EnergyImpactRequestHandler
    movement_runtime: MovementRuntime
    buff_definitions: tuple[BuffDefinition, ...]
    buff_store: BuffStore
    buff_resolver: BuffResolver
    buff_runtime: BuffRuntime
    buff_handler: BuffImpactRequestHandler
    shield_store: ShieldStore
    shield_resolver: ShieldResolver
    shield_runtime: ShieldRuntime
    shield_handler: ShieldImpactRequestHandler
    character_damage_taken_coordinator: CharacterDamageTakenCoordinator
    space_runtime: SpaceRuntime
    impact_runtime: ImpactRuntime
    content_bundle: RuntimeContentBundle
    hook_dispatcher: HookDispatcher
    reaction_eligibility_port: ReactionEligibilityReadPort
    attribute_runtime: AttributeRuntimeBundle
    intent_queue: IntentQueue
    settlement_runtime: IntentSettlementRuntime
    snapshot_runtime: SnapshotRuntime
    runtime_world: FramePipeline
    assets: tuple[RuntimeAssetBundle, ...]
