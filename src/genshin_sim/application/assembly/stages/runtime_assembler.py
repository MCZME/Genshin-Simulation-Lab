"""运行时装配阶段：内容定义 -> 可运行世界。"""

from __future__ import annotations

from genshin_sim.application.assembly.attributes import (
    AttributeRuntimeBundle,
    build_attribute_runtime,
)
from genshin_sim.application.assembly.buffs import (
    build_buff_attribute_providers,
    build_buff_definition_registry,
    validate_buff_definitions_for_assembly,
)
from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.assembly.models import (
    AssembledSimulation,
    RuntimeAssetBundle,
    RuntimeContentBundle,
    energy_element_from_asset,
)
from genshin_sim.application.assembly.reaction_capabilities import (
    build_static_reaction_eligibility_port,
)
from genshin_sim.application.config import SimulationConfig, TeamSlotConfig
from genshin_sim.content.hooks import HookDispatcher, build_hook_unlock_specs
from genshin_sim.content.state_container import StatePatchIntentHandler
from genshin_sim.core.actions import (
    ActionInterpreterRegistry,
    ActionManager,
    ActionRegistry,
    ActiveCharacterInterpreterSelector,
    TeamActionInterpreter,
    TeamInterpreterSelector,
    TeamSwitchAction,
)
from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQuery,
    AttributeResolveOptions,
    AttributeSubjectRef,
    AttributeSystemError,
    TraceLevel,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.character_ability_condition.coordinator import (
    CharacterAbilityConditionCoordinator,
)
from genshin_sim.core.coordination.character_damage_taken import (
    CharacterDamageTakenCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction import (
    BloomCoreTriggerCoordinator,
    CrystallizeShardPickupCoordinator,
    DendroCoreExpiryCoordinator,
    ElementalInteractionCoordinator,
    ElementalSettlementCoordinator,
    ElementalStateFrameCoordinator,
    LunarCageExpiryCoordinator,
    LunarStormCloudExpiryCoordinator,
    ReactionBoundEntityExpiryCoordinator,
    ReactionSpatialPlanningAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterCrystallizeSourceObserver,
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    ReactionStatusBuffAdapter,
    superconduct_buff_definition,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    ContentStateMount,
    HealthState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import (
    ImpactDispatcher,
    ImpactRequestDispatcher,
    ImpactRuntime,
)
from genshin_sim.core.simulation import (
    FramePipeline,
    InputSessionTrace,
    InputTraceCompiler,
    SimulationContext,
    Simulator,
    TeamRuntimeState,
)
from genshin_sim.core.simulation.intent_handlers import (
    BuffIntentHandler,
    ImpactIntentHandler,
)
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.settlement import IntentSettlementRuntime
from genshin_sim.core.snapshots.runtime import SnapshotRuntime
from genshin_sim.core.space import (
    CreatedObjectRuntime,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import (
    AuraApplicationProfileRegistry,
    AuraRuntime,
    CharacterAuraImpactRequestHandler,
)
from genshin_sim.core.systems.aura_icd import (
    AuraIcdRuntime,
    IcdDefinitionRegistry,
    default_sequence_definition,
    no_cooldown_definition,
    standard_icd_definition,
)
from genshin_sim.core.systems.buff import (
    BuffImpactRequestHandler,
    BuffResolver,
    BuffRuntime,
    BuffStore,
    BuffSystemError,
)
from genshin_sim.core.systems.cooldown import (
    CooldownError,
    CooldownRuntime,
    CooldownStore,
)
from genshin_sim.core.systems.damage import (
    DamageFormulaRegistry,
    DamageModifierIndex,
    DamageProfile,
    DamageProfileRegistry,
    DamageRequestHandler,
    DamageResolver,
    DamageSystemError,
    DamageType,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.energy import (
    CharacterEnergyProfile,
    CharacterEnergyStore,
    EnergyImpactRequestHandler,
    EnergyRuntime,
    EnergySystemError,
    EnergyTransitQueue,
)
from genshin_sim.core.systems.healing import (
    HealingImpactRequestHandler,
    HealingRequestHandler,
    HealingResolver,
    HealingSystemError,
)
from genshin_sim.core.systems.health import (
    CharacterHealthStore,
    HealthRuntime,
    HealthSystemError,
    validate_health_float,
)
from genshin_sim.core.systems.movement import (
    MovementImpactRequestHandler,
    MovementRuntime,
)
from genshin_sim.core.systems.reaction import create_default_reaction_bootstrap
from genshin_sim.core.systems.reaction.mechanics.bloom import bloom_damage_profiles
from genshin_sim.core.systems.reaction.mechanics.burning import (
    burning_damage_profile,
    burning_pyro_aura_application_profile,
)
from genshin_sim.core.systems.reaction.mechanics.catalyze import catalyze_damage_profile
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom import (
    lunar_bloom_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize import (
    lunar_crystallize_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged import (
    lunar_electro_charged_damage_profiles,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import (
    SwirlGeneratedImpactDamageInputAdapter,
    swirl_aura_application_profile,
    swirl_damage_profile,
)
from genshin_sim.core.systems.shield import (
    ShieldImpactRequestHandler,
    ShieldResolver,
    ShieldRuntime,
    ShieldStore,
)


class _CooldownFrameAdapter:
    """把冷却 Runtime 的逐帧归一化适配为 FrameUpdatable。"""

    def __init__(self, runtime: CooldownRuntime) -> None:
        self._runtime = runtime

    def update_frame(self, context, frame: int) -> None:
        self._runtime.update_frame(context, frame)

    def is_idle(self) -> bool:
        return self._runtime.is_idle()


TEAM_INPUT_KEYS = ("keyboard.1", "keyboard.2", "keyboard.3", "keyboard.4")
ACTION_BUTTON_KEYS = (
    "keyboard.e",
    "keyboard.q",
    "keyboard.space",
    "mouse.left",
    "mouse.right",
)


class RuntimeAssembler:
    """运行时装配阶段：把内容定义注入领域运行时，产出可运行世界。"""

    def __init__(
        self,
        *,
        damage_formula_registry: DamageFormulaRegistry | None = None,
    ) -> None:
        self.damage_formula_registry = damage_formula_registry

    def assemble(
        self,
        config: SimulationConfig,
        assets: tuple[RuntimeAssetBundle, ...],
        content_bundle: RuntimeContentBundle,
    ) -> AssembledSimulation:
        assets_by_slot = {bundle.slot: bundle for bundle in assets}
        reaction_eligibility_port = build_static_reaction_eligibility_port(
            content_bundle.content_units
        )
        buff_registry = build_buff_definition_registry(
            (*content_bundle.buff_definitions, superconduct_buff_definition())
        )
        attribute_runtime_without_buffs = build_attribute_runtime(
            config=config,
            assets=assets,
            content_units=content_bundle.content_units,
        )
        buff_store = BuffStore()
        validate_buff_definitions_for_assembly(
            definitions=buff_registry.definitions,
            attribute_definitions=attribute_runtime_without_buffs.definitions,
            modifier_providers=attribute_runtime_without_buffs.modifier_index.providers,
        )
        buff_attribute_providers = build_buff_attribute_providers(buff_registry, buff_store)
        attribute_runtime = (
            build_attribute_runtime(
                config=config,
                assets=assets,
                content_units=content_bundle.content_units,
                extra_providers=buff_attribute_providers,
            )
            if buff_attribute_providers
            else attribute_runtime_without_buffs
        )

        context = SimulationContext()
        context.register_system(attribute_runtime.resolver)
        mounts_by_owner: dict[str, dict[str, ContentStateMount]] = {}
        for mount in content_bundle.content_state_mounts:
            mounts_by_owner.setdefault(mount.owner, {})[mount.state_key] = mount
        team_state = TeamRuntimeState(
            (
                self._build_character_runtime_state(
                    slot,
                    ascension_phase=(
                        assets_by_slot[slot.slot].character_level_stats.ascension_phase
                    ),
                    attribute_runtime=attribute_runtime,
                    content_states=mounts_by_owner.get(f"character:slot_{slot.slot}", {}),
                )
                for slot in config.team
            ),
            active_slot=1,
        )
        health_store = CharacterHealthStore(
            (
                AttributeSubjectRef.character(character.combat_entity_id),
                character.health,
            )
            for character in team_state.characters
        )
        health_runtime = HealthRuntime(
            attribute_runtime.resolver,
            health_store,
            context.events,
        )
        context.register_system(health_runtime)
        try:
            energy_entries = []
            for character in team_state.characters:
                asset_bundle = assets_by_slot[character.slot]
                burst_energy_cost = asset_bundle.character.burst_energy_cost
                if burst_energy_cost is None:
                    raise InvalidRuntimePayloadError(
                        f"槽位 {character.slot} 角色资产缺少 burst_energy_cost"
                    )
                energy_entries.append(
                    (
                        CharacterEnergyProfile(
                            AttributeSubjectRef.character(character.combat_entity_id),
                            asset_bundle.character.asset_key,
                            energy_element_from_asset(asset_bundle.character.element),
                            burst_energy_cost,
                        ),
                        character.energy,
                    )
                )
            energy_store = CharacterEnergyStore(energy_entries)
            energy_transit_queue = EnergyTransitQueue()
            energy_runtime = EnergyRuntime(
                attribute_runtime.resolver,
                team_state,
                energy_store,
                energy_transit_queue,
                context.events,
            )
            energy_handler = EnergyImpactRequestHandler(energy_runtime)
        except EnergySystemError as exc:
            raise InvalidRuntimePayloadError(f"元素能量组装失败：{exc}") from exc
        context.register_system(energy_runtime)
        context.register_system(energy_handler)
        try:
            cooldown_runtime = CooldownRuntime(CooldownStore(content_bundle.cooldown_definitions))
        except CooldownError as exc:
            raise InvalidRuntimePayloadError(f"冷却组装失败：{exc}") from exc
        ability_condition_coordinator = CharacterAbilityConditionCoordinator(
            cooldown_runtime,
            energy_runtime,
        )
        context.register_system(cooldown_runtime)
        context.register_system(ability_condition_coordinator)
        target_states = TargetRuntimeCollection(
            TargetRuntimeState(
                target_id=target.target_id,
                level=target.level,
                resistance=target.resistance,
            )
            for target in config.scene.targets
        )
        space = Space(
            [
                SpatialEntity(
                    entity_id="player:active",
                    kind=SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(
                        config.scene.player.position.x,
                        config.scene.player.position.y,
                        config.scene.player.position.z,
                    ),
                    facing=Vector3(
                        config.scene.player.facing.x,
                        config.scene.player.facing.y,
                        config.scene.player.facing.z,
                    ),
                    active_slot=1,
                ),
                *(
                    SpatialEntity(
                        entity_id=f"target:{target.target_id}",
                        kind=SpatialEntityKind.TARGET,
                        position=Vector3(
                            target.position.x,
                            target.position.y,
                            target.position.z,
                        ),
                    )
                    for target in config.scene.targets
                ),
            ]
        )
        input_trace = InputTraceCompiler().compile(config.to_core_input_frames())
        created_object_runtime = CreatedObjectRuntime(content_bundle.created_object_behaviors)
        self._bind_attribute_provider_ports(
            content_bundle,
            team_state=team_state,
            created_object_runtime=created_object_runtime,
        )
        space_runtime = SpaceRuntime(
            space=space,
            team_state=team_state,
            targets=target_states,
            created_object_runtime=created_object_runtime,
        )
        context.space_runtime = space_runtime

        action_interpreter_registry = ActionInterpreterRegistry()
        team_selector = TeamInterpreterSelector(TeamActionInterpreter())
        for key in TEAM_INPUT_KEYS:
            action_interpreter_registry.register(key, team_selector)
        character_selector = ActiveCharacterInterpreterSelector(content_bundle.action_interpreters)
        for key in ACTION_BUTTON_KEYS:
            action_interpreter_registry.register(key, character_selector)
        self._validate_input_interpreters(input_trace, config.team, content_bundle)

        try:
            action_registry = ActionRegistry((TeamSwitchAction(), *content_bundle.actions))
        except ValueError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        self._validate_action_bindings(content_bundle, action_registry)

        action_manager = ActionManager(
            input_trace=input_trace,
            interpreter_registry=action_interpreter_registry,
            action_registry=action_registry,
            ability_condition_port=ability_condition_coordinator,
        )
        impact_dispatcher = ImpactDispatcher(content_bundle.impact_factories)
        try:
            damage_modifier_index = DamageModifierIndex(
                content_bundle.damage_modifier_providers,
                content_bundle.damage_modifier_stacking_groups,
            )
            damage_handler = DamageRequestHandler(
                DamageResolver(
                    attribute_resolver=attribute_runtime.resolver,
                    modifier_index=damage_modifier_index,
                    formula_registry=(
                        self.damage_formula_registry
                        if self.damage_formula_registry is not None
                        else create_default_damage_formula_registry()
                    ),
                ),
                profile_registry=DamageProfileRegistry(
                    (
                        DamageProfile(
                            "damage_profile.character.barbara",
                            DamageType.GENERAL,
                            frozenset(
                                {
                                    "普通攻击1",
                                    "普通攻击2",
                                    "普通攻击3",
                                    "普通攻击4",
                                    "重击",
                                    "元素战技",
                                    "下落攻击",
                                }
                            ),
                        ),
                        DamageProfile(
                            "damage_profile.testing.runtime_probe",
                            DamageType.GENERAL,
                            frozenset({"testing.runtime_probe.direct"}),
                        ),
                        DamageProfile(
                            "damage_profile.reaction.overloaded",
                            DamageType.TRANSFORMATIVE_REACTION,
                            frozenset({"reaction.overloaded"}),
                        ),
                        DamageProfile(
                            "damage_profile.reaction.superconduct",
                            DamageType.TRANSFORMATIVE_REACTION,
                            frozenset({"reaction.superconduct"}),
                        ),
                        DamageProfile(
                            "damage_profile.reaction.shattered",
                            DamageType.TRANSFORMATIVE_REACTION,
                            frozenset({"reaction.shattered"}),
                        ),
                        DamageProfile(
                            "damage_profile.reaction.electro_charged",
                            DamageType.TRANSFORMATIVE_REACTION,
                            frozenset({"reaction.electro_charged"}),
                        ),
                        swirl_damage_profile(),
                        burning_damage_profile(),
                        catalyze_damage_profile(),
                        *bloom_damage_profiles(),
                        *lunar_bloom_damage_profiles(),
                        *lunar_electro_charged_damage_profiles(),
                        *lunar_crystallize_damage_profiles(),
                    )
                ),
            )
        except DamageSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        context.register_system(damage_handler)
        try:
            healing_handler = HealingRequestHandler(
                HealingResolver(attribute_runtime.resolver),
                health_runtime,
            )
        except HealingSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        context.register_system(healing_handler)
        healing_impact_handler = HealingImpactRequestHandler(healing_handler)
        context.register_system(healing_impact_handler)
        try:
            buff_resolver = BuffResolver()
            buff_runtime = BuffRuntime(
                definition_registry=buff_registry,
                resolver=buff_resolver,
                buff_store=buff_store,
                event_engine=context.events,
            )
            buff_handler = BuffImpactRequestHandler(buff_runtime)
        except BuffSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        shield_store = ShieldStore()
        shield_resolver = ShieldResolver(attribute_runtime.resolver)
        shield_runtime = ShieldRuntime(
            resolver=shield_resolver,
            shield_store=shield_store,
            attribute_resolver=attribute_runtime.resolver,
            event_engine=context.events,
            team_state=team_state,
        )
        shield_handler = ShieldImpactRequestHandler(shield_runtime)
        character_damage_taken_coordinator = CharacterDamageTakenCoordinator(
            shield_runtime,
            health_runtime,
            context.events,
        )
        context.register_system(buff_runtime)
        context.register_system(buff_handler)
        context.register_system(shield_runtime)
        context.register_system(shield_handler)
        context.register_system(character_damage_taken_coordinator)
        movement_runtime = MovementRuntime()
        movement_handler = MovementImpactRequestHandler(movement_runtime)
        context.register_system(movement_runtime)
        aura_runtime = AuraRuntime()
        aura_icd_runtime = AuraIcdRuntime(
            IcdDefinitionRegistry(
                (
                    standard_icd_definition(),
                    default_sequence_definition(),
                    no_cooldown_definition(),
                    *content_bundle.aura_icd_definitions,
                )
            )
        )
        character_aura_handler = CharacterAuraImpactRequestHandler(
            aura_runtime,
            aura_icd_runtime,
            context.events,
        )
        context.register_system(character_aura_handler)
        reaction_bootstrap = create_default_reaction_bootstrap()
        reaction_runtime = reaction_bootstrap.create_runtime()
        reaction_spatial_planning_port = ReactionSpatialPlanningAdapter(space)
        crystallize_shard_pickup_coordinator = CrystallizeShardPickupCoordinator(
            reaction_state_port=reaction_runtime,
            spatial_planning_port=reaction_spatial_planning_port,
            shield_grant_port=shield_runtime,
        )
        elemental_state_frame_coordinator = ElementalStateFrameCoordinator(
            aura_runtime,
            aura_icd_runtime,
            reaction_runtime,
            ReactionBoundEntityExpiryCoordinator(
                reaction_state_port=reaction_runtime,
                spatial_planning_port=reaction_spatial_planning_port,
            ),
            DendroCoreExpiryCoordinator(
                reaction_state_port=reaction_runtime,
                spatial_planning_port=reaction_spatial_planning_port,
            ),
            LunarStormCloudExpiryCoordinator(
                reaction_state_port=reaction_runtime,
                spatial_planning_port=reaction_spatial_planning_port,
            ),
            lunar_cage_expiry_coordinator=LunarCageExpiryCoordinator(
                reaction_state_port=reaction_runtime,
                spatial_planning_port=reaction_spatial_planning_port,
            ),
        )
        elemental_interaction_coordinator = ElementalInteractionCoordinator(
            aura_runtime=aura_runtime,
            icd_runtime=aura_icd_runtime,
            reaction_runtime=reaction_runtime,
            damage_handler=damage_handler,
            frame_coordinator=elemental_state_frame_coordinator,
            transformative_source_observer=CharacterTransformativeSourceObserver(
                attribute_runtime.resolver
            ),
            crystallize_source_observer=CharacterCrystallizeSourceObserver(
                attribute_runtime.resolver
            ),
            reaction_eligibility_port=reaction_eligibility_port,
            spatial_planning_port=reaction_spatial_planning_port,
        )
        bloom_core_trigger_coordinator = BloomCoreTriggerCoordinator(
            reaction_state_port=reaction_runtime,
            spatial_planning_port=reaction_spatial_planning_port,
            impact_evidence_port=elemental_interaction_coordinator,
        )
        elemental_settlement_coordinator = ElementalSettlementCoordinator(
            elemental_interaction_coordinator,
            reaction_runtime=reaction_runtime,
            aura_runtime=aura_runtime,
            frame_coordinator=elemental_state_frame_coordinator,
            damage_handler=damage_handler,
            generated_impact_damage_input_adapter=SwirlGeneratedImpactDamageInputAdapter(),
            buff_runtime=buff_runtime,
            status_adapter=ReactionStatusBuffAdapter(),
            dynamic_transformative_source_observer=CharacterTransformativeSourceObserver(
                attribute_runtime.resolver
            ),
            bloom_core_trigger_coordinator=bloom_core_trigger_coordinator,
            character_damage_taken_coordinator=character_damage_taken_coordinator,
            aura_application_profile_registry=AuraApplicationProfileRegistry(
                (
                    swirl_aura_application_profile(),
                    burning_pyro_aura_application_profile(),
                )
            ),
        )
        reaction_runtime.set_external_write_guard(
            lambda: (
                elemental_settlement_coordinator.is_publishing_facts
                or crystallize_shard_pickup_coordinator.is_publishing_facts
            )
        )
        space.set_external_write_guard(
            lambda: (
                elemental_settlement_coordinator.is_publishing_facts
                or crystallize_shard_pickup_coordinator.is_publishing_facts
            )
        )
        damage_handler.set_external_write_guard(
            lambda: elemental_settlement_coordinator.is_publishing_facts
        )
        shield_runtime.set_external_write_guard(
            lambda: (
                elemental_settlement_coordinator.is_publishing_facts
                or crystallize_shard_pickup_coordinator.is_publishing_facts
            )
        )
        context.register_system(aura_runtime)
        context.register_system(aura_icd_runtime)
        context.register_system(reaction_runtime)
        context.register_system(elemental_state_frame_coordinator)
        context.register_system(elemental_interaction_coordinator)
        context.register_system(elemental_settlement_coordinator)
        impact_request_dispatcher = ImpactRequestDispatcher(
            damage_handler=damage_handler,
            shield_handler=shield_handler,
            buff_handler=buff_handler,
            healing_handler=healing_impact_handler,
            character_aura_handler=character_aura_handler,
            energy_handler=energy_handler,
            movement_handler=movement_handler,
            elemental_settlement_coordinator=elemental_settlement_coordinator,
        )
        impact_runtime = ImpactRuntime(
            action_manager,
            impact_dispatcher,
            impact_request_dispatcher,
        )
        intent_queue = IntentQueue()
        context.register_system(intent_queue)
        settlement_runtime = IntentSettlementRuntime(intent_queue)
        settlement_runtime.register(
            IntentKind.IMPACT,
            ImpactIntentHandler(impact_request_dispatcher),
        )
        settlement_runtime.register(IntentKind.BUFF, BuffIntentHandler(buff_runtime))
        settlement_runtime.register(
            IntentKind.STATE_PATCH,
            StatePatchIntentHandler(team_state),
        )
        snapshot_runtime = SnapshotRuntime()
        snapshot_runtime.register(
            "energy",
            lambda frame: energy_runtime.snapshot(frame).to_dict(),
        )
        snapshot_runtime.register(
            "buff",
            lambda frame: buff_runtime.snapshot(frame).to_dict(),
        )
        snapshot_runtime.register(
            "content_state",
            lambda frame: _content_state_snapshots(team_state, frame),
        )
        hook_dispatcher = HookDispatcher(
            content_bundle.event_hooks,
            intent_queue,
            team_state=team_state,
            unlock_specs=build_hook_unlock_specs(content_bundle.content_units),
        )
        context.register_system(hook_dispatcher)
        runtime_world = FramePipeline(
            settlement_runtime=settlement_runtime,
            snapshot_runtime=snapshot_runtime,
        )
        runtime_world.add(FramePhase.TIME_ADVANCE, "buff", buff_runtime)
        runtime_world.add(FramePhase.TIME_ADVANCE, "shield", shield_runtime)
        runtime_world.add(
            FramePhase.TIME_ADVANCE,
            "elemental_settlement",
            elemental_settlement_coordinator,
        )
        cooldown_frame_adapter = _CooldownFrameAdapter(cooldown_runtime)
        runtime_world.add(FramePhase.TIME_ADVANCE, "cooldown", cooldown_frame_adapter)
        runtime_world.add(FramePhase.TIME_ADVANCE, "movement", movement_runtime)
        runtime_world.add(FramePhase.ACTION_ADVANCE, "action_manager", action_manager)
        runtime_world.add(FramePhase.SETTLEMENT, "impact", impact_runtime)
        runtime_world.add(FramePhase.SETTLEMENT, "energy", energy_runtime)
        runtime_world.add(FramePhase.SETTLEMENT, "space", space_runtime)
        runtime_world.add(FramePhase.FACT_RESPONSE, "content_hooks", hook_dispatcher)
        simulator = Simulator(
            context,
            runtime_world=runtime_world,
            max_frames=config.run_options.max_frames,
        )

        return AssembledSimulation(
            config=config,
            context=context,
            simulator=simulator,
            action_manager=action_manager,
            action_interpreter_registry=action_interpreter_registry,
            action_registry=action_registry,
            impact_dispatcher=impact_dispatcher,
            impact_request_dispatcher=impact_request_dispatcher,
            damage_handler=damage_handler,
            aura_runtime=aura_runtime,
            aura_icd_runtime=aura_icd_runtime,
            reaction_runtime=reaction_runtime,
            bloom_core_trigger_coordinator=bloom_core_trigger_coordinator,
            crystallize_shard_pickup_coordinator=crystallize_shard_pickup_coordinator,
            elemental_state_frame_coordinator=elemental_state_frame_coordinator,
            elemental_interaction_coordinator=elemental_interaction_coordinator,
            elemental_settlement_coordinator=elemental_settlement_coordinator,
            healing_handler=healing_handler,
            health_runtime=health_runtime,
            energy_store=energy_store,
            energy_transit_queue=energy_transit_queue,
            energy_runtime=energy_runtime,
            energy_handler=energy_handler,
            cooldown_runtime=cooldown_runtime,
            cooldown_frame_adapter=cooldown_frame_adapter,
            movement_runtime=movement_runtime,
            buff_definitions=content_bundle.buff_definitions,
            buff_store=buff_store,
            buff_resolver=buff_resolver,
            buff_runtime=buff_runtime,
            buff_handler=buff_handler,
            shield_store=shield_store,
            shield_resolver=shield_resolver,
            shield_runtime=shield_runtime,
            shield_handler=shield_handler,
            character_damage_taken_coordinator=character_damage_taken_coordinator,
            space_runtime=space_runtime,
            impact_runtime=impact_runtime,
            content_bundle=content_bundle,
            hook_dispatcher=hook_dispatcher,
            reaction_eligibility_port=reaction_eligibility_port,
            attribute_runtime=attribute_runtime,
            intent_queue=intent_queue,
            settlement_runtime=settlement_runtime,
            snapshot_runtime=snapshot_runtime,
            runtime_world=runtime_world,
            assets=assets,
        )

    @staticmethod
    def _bind_attribute_provider_ports(
        content_bundle: RuntimeContentBundle,
        *,
        team_state: TeamRuntimeState,
        created_object_runtime: CreatedObjectRuntime,
    ) -> None:
        """为声明了 ``bind_runtime_ports`` 的属性 provider 注入只读运行端口。

        绑定只发生在装配期；未绑定时 provider 的 ``contribute`` 必须返回空，
        因此初始最大生命解析（早于绑定）不受条件 provider 影响。
        """

        for unit in content_bundle.content_units:
            for provider in unit.attribute_providers:
                binder = getattr(provider, "bind_runtime_ports", None)
                if binder is None:
                    continue
                try:
                    binder(
                        created_object_runtime=created_object_runtime,
                        team_state=team_state,
                    )
                except Exception as exc:
                    raise InvalidRuntimePayloadError(
                        f"属性 provider 运行时端口绑定失败：{exc}"
                    ) from exc

    def _build_character_runtime_state(
        self,
        slot: TeamSlotConfig,
        *,
        ascension_phase: int,
        attribute_runtime: AttributeRuntimeBundle,
        content_states: dict[str, ContentStateMount],
    ) -> CharacterRuntimeState:
        subject_ref = AttributeSubjectRef.character(f"character:slot_{slot.slot}")
        max_hp = self._resolve_initial_max_hp(
            attribute_runtime=attribute_runtime,
            subject_ref=subject_ref,
            slot=slot.slot,
        )
        return CharacterRuntimeState(
            slot=slot.slot,
            character_key=slot.character.asset_key,
            level=slot.character.level,
            ascension_phase=ascension_phase,
            constellation=slot.character.constellation,
            talent_levels=slot.character.talents,
            health=HealthState(max_hp),
            content_states=content_states,
        )

    @staticmethod
    def _resolve_initial_max_hp(
        *,
        attribute_runtime: AttributeRuntimeBundle,
        subject_ref: AttributeSubjectRef,
        slot: int,
    ) -> float:
        try:
            resolution = attribute_runtime.resolver.resolve(
                AttributeQuery(subject_ref, STAT_HP_MAX, frame=0),
                options=AttributeResolveOptions(trace_level=TraceLevel.NONE),
            )
        except AttributeSystemError as exc:
            raise InvalidRuntimePayloadError(f"槽位 {slot} 最大生命解析失败：{exc}") from exc
        try:
            max_hp = validate_health_float(resolution.final_value, f"槽位 {slot} 最大生命")
        except HealthSystemError as exc:
            raise InvalidRuntimePayloadError(f"槽位 {slot} 最大生命非法：{exc}") from exc
        if max_hp <= 0:
            raise InvalidRuntimePayloadError(f"槽位 {slot} 最大生命必须是正数")
        return max_hp

    def _validate_input_interpreters(
        self,
        input_trace: InputSessionTrace,
        team_slots: tuple[TeamSlotConfig, ...],
        content_bundle: RuntimeContentBundle,
    ) -> None:
        input_keys = {session.key for session in input_trace.sessions}
        if not input_keys.intersection(ACTION_BUTTON_KEYS):
            return

        missing_slots = [
            slot.slot for slot in team_slots if slot.slot not in content_bundle.action_interpreters
        ]
        if missing_slots:
            slots = ", ".join(str(slot) for slot in missing_slots)
            raise InvalidRuntimePayloadError(f"动作输入需要队伍槽位提供动作解释器：{slots}")

    def _validate_action_bindings(
        self,
        content_bundle: RuntimeContentBundle,
        action_registry: ActionRegistry,
    ) -> None:
        for slot, interpreter in content_bundle.action_interpreters.items():
            for action_key in interpreter.supported_action_keys:
                if not action_registry.contains(action_key):
                    raise InvalidRuntimePayloadError(
                        f"槽位 {slot} 的动作解释器声明了未注册 action：{action_key}"
                    )


def _content_state_snapshots(
    team_state: TeamRuntimeState,
    frame: int,
) -> dict[str, object]:
    """按角色遍历导出内容状态快照，供快照 provider 使用。"""

    result: dict[str, object] = {}
    for character in team_state.characters:
        for state_key in sorted(character.content_states):
            mount = character.content_states[state_key]
            result[mount.owner] = _content_state_snapshot_dict(mount, frame)
    return result


def _content_state_snapshot_dict(mount: ContentStateMount, frame: int) -> dict[str, object]:
    """把内容状态挂载转成 JSON 兼容快照字典。"""

    return {
        "owner_ref": mount.owner,
        "handler_key": mount.state_key,
        "schema_version": 1,
        "frame": frame,
        "payload": dict(mount.values),
    }
