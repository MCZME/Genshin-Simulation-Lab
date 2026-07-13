from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from genshin_sim.application.assembly.attributes import (
    AttributeRuntimeBundle,
    build_attribute_runtime,
)
from genshin_sim.application.assembly.errors import (
    InvalidRuntimePayloadError,
    MissingRuntimeAssetError,
    MissingRuntimeHandlerError,
)
from genshin_sim.application.config import SimulationConfig, TeamSlotConfig
from genshin_sim.assets import AssetError, AssetRepository
from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.content import (
    ArtifactRuntimeRequest,
    CharacterRuntimeRequest,
    ContentRuntimeContribution,
    ContentStateStore,
    EventHook,
    HandlerNotFoundError,
    HandlerRegistry,
    ImpactRuntimeRequest,
    Modifier,
    WeaponRuntimeRequest,
)
from genshin_sim.core.actions import (
    Action,
    ActionInterpreter,
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
from genshin_sim.core.coordination.character_damage_taken import (
    CharacterDamageTakenCoordinator,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    HealthState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import (
    ImpactDispatcher,
    ImpactFactory,
    ImpactRequestDispatcher,
    ImpactRuntime,
)
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    InputSessionTrace,
    InputTraceCompiler,
    SimulationContext,
    Simulator,
    TeamRuntimeState,
)
from genshin_sim.core.space import (
    CreatedObjectBehavior,
    CreatedObjectRuntime,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import (
    DamageFormulaRegistry,
    DamageModifierIndex,
    DamageModifierProvider,
    DamageModifierStackingGroupDefinition,
    DamageRequestHandler,
    DamageResolver,
    DamageSystemError,
    GeneralDamageFormula,
)
from genshin_sim.core.systems.healing import (
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
from genshin_sim.core.systems.shield import (
    ShieldImpactRequestHandler,
    ShieldResolver,
    ShieldRuntime,
    ShieldStore,
)

TEAM_INPUT_KEYS = ("keyboard.1", "keyboard.2", "keyboard.3", "keyboard.4")
ACTION_BUTTON_KEYS = (
    "keyboard.e",
    "keyboard.q",
    "keyboard.space",
    "mouse.left",
    "mouse.right",
)


@dataclass(frozen=True, slots=True)
class RuntimeAssetBundle:
    slot: int
    character: CharacterAsset
    character_level_stats: CharacterLevelStats
    weapon: WeaponAsset | None
    weapon_level_stats: WeaponLevelStats | None
    artifact_sets: tuple[ArtifactSetAsset, ...]
    artifact_bonuses: tuple[ArtifactSetBonus, ...]
    effect_payloads: tuple[EffectPayload, ...]


@dataclass(frozen=True, slots=True)
class RuntimeContentBundle:
    contributions: tuple[ContentRuntimeContribution, ...]
    content_state_store: ContentStateStore
    action_interpreters: dict[int, ActionInterpreter]
    actions: tuple[Action, ...]
    impact_factories: dict[str, ImpactFactory]
    created_object_behaviors: dict[str, CreatedObjectBehavior]
    event_hooks: tuple[EventHook, ...]
    modifiers: tuple[Modifier, ...]
    damage_modifier_providers: tuple[DamageModifierProvider, ...]
    damage_modifier_stacking_groups: tuple[DamageModifierStackingGroupDefinition, ...]


@dataclass(slots=True)
class AssembledSimulation:
    config: SimulationConfig
    context: SimulationContext
    simulator: Simulator
    action_manager: ActionManager
    action_interpreter_registry: ActionInterpreterRegistry
    action_registry: ActionRegistry
    impact_dispatcher: ImpactDispatcher
    impact_request_dispatcher: ImpactRequestDispatcher
    damage_handler: DamageRequestHandler
    healing_handler: HealingRequestHandler
    health_runtime: HealthRuntime
    shield_store: ShieldStore
    shield_resolver: ShieldResolver
    shield_runtime: ShieldRuntime
    shield_handler: ShieldImpactRequestHandler
    character_damage_taken_coordinator: CharacterDamageTakenCoordinator
    space_runtime: SpaceRuntime
    impact_runtime: ImpactRuntime
    content_bundle: RuntimeContentBundle
    attribute_runtime: AttributeRuntimeBundle
    runtime_world: BasicRuntimeWorld
    assets: tuple[RuntimeAssetBundle, ...]


class SimulationAssembler:
    """基于已校验的 SimulationConfig 构建最小运行时对象图。"""

    def __init__(
        self,
        asset_repository: AssetRepository,
        handler_registry: HandlerRegistry,
    ) -> None:
        self.asset_repository = asset_repository
        self.handler_registry = handler_registry

    def assemble(self, config: SimulationConfig) -> AssembledSimulation:
        if not config.team:
            raise MissingRuntimeAssetError("仿真运行至少需要一个队伍槽位")

        assets = tuple(self._load_slot_assets(slot) for slot in config.team)
        contributions = self._prepare_handlers(assets)
        content_bundle = self._build_content_bundle(contributions)
        attribute_runtime = build_attribute_runtime(
            config=config,
            assets=assets,
            contributions=contributions,
        )

        context = SimulationContext()
        context.register_system(attribute_runtime.resolver)
        team_state = TeamRuntimeState(
            (
                self._build_character_runtime_state(
                    slot,
                    attribute_runtime=attribute_runtime,
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
                    formula_registry=DamageFormulaRegistry((GeneralDamageFormula(),)),
                )
            )
        except DamageSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        try:
            healing_handler = HealingRequestHandler(
                HealingResolver(attribute_runtime.resolver),
                health_runtime,
            )
        except HealingSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        context.register_system(healing_handler)
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
        context.register_system(shield_runtime)
        context.register_system(shield_handler)
        context.register_system(character_damage_taken_coordinator)
        impact_request_dispatcher = ImpactRequestDispatcher(
            damage_handler,
            shield_handler,
        )
        impact_runtime = ImpactRuntime(
            action_manager,
            impact_dispatcher,
            impact_request_dispatcher,
        )
        runtime_world = BasicRuntimeWorld(
            [shield_runtime, action_manager, impact_runtime, space_runtime]
        )
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
            healing_handler=healing_handler,
            health_runtime=health_runtime,
            shield_store=shield_store,
            shield_resolver=shield_resolver,
            shield_runtime=shield_runtime,
            shield_handler=shield_handler,
            character_damage_taken_coordinator=character_damage_taken_coordinator,
            space_runtime=space_runtime,
            impact_runtime=impact_runtime,
            content_bundle=content_bundle,
            attribute_runtime=attribute_runtime,
            runtime_world=runtime_world,
            assets=assets,
        )

    def _build_character_runtime_state(
        self,
        slot: TeamSlotConfig,
        *,
        attribute_runtime: AttributeRuntimeBundle,
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
            constellation=slot.character.constellation,
            talent_levels=slot.character.talents,
            health=HealthState(max_hp),
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

    def _load_slot_assets(self, slot: TeamSlotConfig) -> RuntimeAssetBundle:
        try:
            character = self.asset_repository.get_character(slot.character.asset_key)
            character_level_stats = self.asset_repository.get_character_level_stats(
                character.asset_key,
                slot.character.level,
            )

            weapon = None
            weapon_level_stats = None
            if slot.weapon is not None:
                weapon = self.asset_repository.get_weapon(slot.weapon.asset_key)
                weapon_level_stats = self.asset_repository.get_weapon_level_stats(
                    weapon.asset_key,
                    slot.weapon.level,
                )

            artifact_sets: list[ArtifactSetAsset] = []
            artifact_bonuses: list[ArtifactSetBonus] = []
            for artifact_set in slot.artifacts.sets:
                asset = self.asset_repository.get_artifact_set(artifact_set.asset_key)
                artifact_sets.append(asset)
                artifact_bonuses.extend(
                    self.asset_repository.get_artifact_set_bonuses(
                        artifact_set.asset_key,
                        artifact_set.pieces,
                    )
                )

            effect_payloads = list(self.asset_repository.get_effect_payloads(character.asset_key))
            if weapon is not None:
                effect_payloads.extend(self.asset_repository.get_effect_payloads(weapon.asset_key))
            for artifact_set in artifact_sets:
                effect_payloads.extend(
                    self.asset_repository.get_effect_payloads(artifact_set.asset_key)
                )
        except (AssetError, LookupError) as exc:
            raise MissingRuntimeAssetError(f"加载队伍槽位 {slot.slot} 的资产失败：{exc}") from exc

        return RuntimeAssetBundle(
            slot=slot.slot,
            character=character,
            character_level_stats=character_level_stats,
            weapon=weapon,
            weapon_level_stats=weapon_level_stats,
            artifact_sets=tuple(artifact_sets),
            artifact_bonuses=tuple(artifact_bonuses),
            effect_payloads=tuple(effect_payloads),
        )

    def _prepare_handlers(
        self,
        bundles: tuple[RuntimeAssetBundle, ...],
    ) -> tuple[ContentRuntimeContribution, ...]:
        contributions: list[ContentRuntimeContribution] = []
        for bundle in bundles:
            contribution = self._prepare_character_handler(bundle)
            if contribution is not None:
                contributions.append(contribution)
            if bundle.weapon is not None:
                contribution = self._prepare_weapon_handler(bundle)
                if contribution is not None:
                    contributions.append(contribution)
            for artifact_set in bundle.artifact_sets:
                contribution = self._prepare_artifact_handler(
                    handler_key=artifact_set.handler_key,
                    artifact_key=artifact_set.asset_key,
                    artifact_kind="artifact_set",
                    slot=bundle.slot,
                    asset=artifact_set,
                )
                if contribution is not None:
                    contributions.append(contribution)
            for bonus in bundle.artifact_bonuses:
                contribution = self._prepare_artifact_handler(
                    handler_key=bonus.handler_key,
                    artifact_key=bonus.artifact_set_key,
                    artifact_kind="artifact_set_bonus",
                    slot=bundle.slot,
                    piece_count=bonus.piece_count,
                    params=bonus.params,
                )
                if contribution is not None:
                    contributions.append(contribution)
            for payload in bundle.effect_payloads:
                contribution = self._prepare_impact_handler(
                    payload.handler_key,
                    owner_type=payload.owner_type,
                    owner_key=payload.owner_key,
                    slot=bundle.slot,
                    impact_key=payload.effect_key,
                    impact_kind=payload.effect_kind,
                    params=payload.params,
                )
                if contribution is not None:
                    contributions.append(contribution)
        return tuple(contributions)

    def _prepare_character_handler(
        self,
        bundle: RuntimeAssetBundle,
    ) -> ContentRuntimeContribution | None:
        handler_key = bundle.character.handler_key
        if handler_key is None:
            return None
        return self._invoke_character_handler(
            handler_key,
            CharacterRuntimeRequest(
                handler_key=handler_key,
                character_key=bundle.character.asset_key,
                slot=bundle.slot,
                asset=bundle.character,
            ),
        )

    def _prepare_weapon_handler(
        self,
        bundle: RuntimeAssetBundle,
    ) -> ContentRuntimeContribution | None:
        if bundle.weapon is None:
            return None
        handler_key = bundle.weapon.handler_key
        if handler_key is None:
            return None
        return self._invoke_weapon_handler(
            handler_key,
            WeaponRuntimeRequest(
                handler_key=handler_key,
                weapon_key=bundle.weapon.asset_key,
                slot=bundle.slot,
                asset=bundle.weapon,
            ),
        )

    def _prepare_artifact_handler(
        self,
        handler_key: str | None,
        *,
        artifact_key: str,
        artifact_kind: str,
        slot: int,
        piece_count: int | None = None,
        params: dict[str, Any] | None = None,
        asset: Any | None = None,
    ) -> ContentRuntimeContribution | None:
        if handler_key is None:
            return None
        params = params or {}
        self._validate_payload_params(handler_key, params)
        return self._invoke_artifact_handler(
            handler_key,
            ArtifactRuntimeRequest(
                handler_key=handler_key,
                artifact_key=artifact_key,
                slot=slot,
                artifact_kind=artifact_kind,
                piece_count=piece_count,
                params=params,
                asset=asset,
            ),
        )

    def _prepare_impact_handler(
        self,
        handler_key: str,
        *,
        owner_type: str,
        owner_key: str,
        slot: int,
        impact_key: str,
        impact_kind: str,
        params: dict[str, Any],
    ) -> ContentRuntimeContribution | None:
        self._validate_payload_params(handler_key, params)
        return self._invoke_impact_handler(
            handler_key,
            ImpactRuntimeRequest(
                handler_key=handler_key,
                owner_type=owner_type,
                owner_key=owner_key,
                slot=slot,
                impact_key=impact_key,
                impact_kind=impact_kind,
                params=params,
            ),
        )

    def _invoke_character_handler(
        self,
        handler_key: str,
        request: CharacterRuntimeRequest,
    ) -> ContentRuntimeContribution | None:
        try:
            return self.handler_registry.create_character(request)
        except (HandlerNotFoundError, LookupError) as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少 handler：{handler_key}") from exc

    def _invoke_weapon_handler(
        self,
        handler_key: str,
        request: WeaponRuntimeRequest,
    ) -> ContentRuntimeContribution | None:
        try:
            return self.handler_registry.create_weapon(request)
        except (HandlerNotFoundError, LookupError) as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少 handler：{handler_key}") from exc

    def _invoke_artifact_handler(
        self,
        handler_key: str,
        request: ArtifactRuntimeRequest,
    ) -> ContentRuntimeContribution | None:
        try:
            return self.handler_registry.create_artifact(request)
        except (HandlerNotFoundError, LookupError) as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少 handler：{handler_key}") from exc

    def _invoke_impact_handler(
        self,
        handler_key: str,
        request: ImpactRuntimeRequest,
    ) -> ContentRuntimeContribution | None:
        try:
            return self.handler_registry.create_impact(request)
        except (HandlerNotFoundError, LookupError) as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少 handler：{handler_key}") from exc

    def _build_content_bundle(
        self,
        contributions: tuple[ContentRuntimeContribution, ...],
    ) -> RuntimeContentBundle:
        state_store = ContentStateStore()
        action_interpreters: dict[int, ActionInterpreter] = {}
        actions: list[Action] = []
        impact_factories: dict[str, ImpactFactory] = {}
        created_object_behaviors: dict[str, CreatedObjectBehavior] = {}
        event_hooks: list[EventHook] = []
        modifiers: list[Modifier] = []
        damage_modifier_providers: list[DamageModifierProvider] = []
        damage_modifier_stacking_groups: list[DamageModifierStackingGroupDefinition] = []

        for contribution in contributions:
            self._register_content_state(state_store, contribution)
            self._register_action_interpreter(action_interpreters, contribution)
            self._register_actions(actions, contribution)
            self._register_impact_factories(impact_factories, contribution)
            self._register_created_object_behaviors(created_object_behaviors, contribution)
            event_hooks.extend(contribution.event_hooks)
            modifiers.extend(contribution.modifiers)
            damage_modifier_providers.extend(contribution.damage_modifier_providers)
            damage_modifier_stacking_groups.extend(contribution.damage_modifier_stacking_groups)

        return RuntimeContentBundle(
            contributions=contributions,
            content_state_store=state_store,
            action_interpreters=action_interpreters,
            actions=tuple(actions),
            impact_factories=impact_factories,
            created_object_behaviors=created_object_behaviors,
            event_hooks=tuple(event_hooks),
            modifiers=tuple(modifiers),
            damage_modifier_providers=tuple(damage_modifier_providers),
            damage_modifier_stacking_groups=tuple(damage_modifier_stacking_groups),
        )

    def _register_content_state(
        self,
        state_store: ContentStateStore,
        contribution: ContentRuntimeContribution,
    ) -> None:
        state = contribution.state_extension
        if state is None:
            return

        if contribution.owner_type == "character":
            state_store.set_character_state(
                slot=contribution.slot,
                handler_key=contribution.handler_key,
                state=state,
            )
            return
        if contribution.owner_type == "weapon":
            state_store.set_weapon_state(
                slot=contribution.slot,
                handler_key=contribution.handler_key,
                state=state,
            )
            return
        if contribution.owner_type in {"artifact", "artifact_set", "artifact_set_bonus"}:
            state_store.set_artifact_state(
                slot=contribution.slot,
                handler_key=contribution.handler_key,
                state=state,
            )
            return

        state_store.set_generic_state(
            owner_ref=f"{contribution.owner_type}:{contribution.owner_key}",
            handler_key=contribution.handler_key,
            state=state,
        )

    def _register_action_interpreter(
        self,
        action_interpreters: dict[int, ActionInterpreter],
        contribution: ContentRuntimeContribution,
    ) -> None:
        if contribution.action_interpreter is None:
            return
        if contribution.owner_type != "character":
            raise InvalidRuntimePayloadError("只有角色内容可以贡献动作解释器")
        if contribution.slot is None:
            raise InvalidRuntimePayloadError("角色动作解释器必须绑定队伍槽位")
        if contribution.slot in action_interpreters:
            raise InvalidRuntimePayloadError(f"队伍槽位 {contribution.slot} 重复贡献动作解释器")
        action_interpreters[contribution.slot] = cast(
            ActionInterpreter,
            contribution.action_interpreter,
        )

    def _register_actions(
        self,
        actions: list[Action],
        contribution: ContentRuntimeContribution,
    ) -> None:
        for action in contribution.actions:
            actions.append(cast(Action, action))

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

    def _register_impact_factories(
        self,
        impact_factories: dict[str, ImpactFactory],
        contribution: ContentRuntimeContribution,
    ) -> None:
        for impact_key, factory in contribution.impact_factories.items():
            if impact_key in impact_factories:
                raise InvalidRuntimePayloadError(f"重复 impact factory：{impact_key}")
            impact_factories[impact_key] = cast(ImpactFactory, factory)

    def _register_created_object_behaviors(
        self,
        created_object_behaviors: dict[str, CreatedObjectBehavior],
        contribution: ContentRuntimeContribution,
    ) -> None:
        if contribution.created_object_behaviors and contribution.owner_type != "character":
            raise InvalidRuntimePayloadError("只有角色内容可以贡献内容创建对象行为")
        for behavior_key, behavior in contribution.created_object_behaviors.items():
            if behavior_key in created_object_behaviors:
                raise InvalidRuntimePayloadError(f"重复内容创建对象行为：{behavior_key}")
            created_object_behaviors[behavior_key] = cast(CreatedObjectBehavior, behavior)

    @staticmethod
    def _validate_payload_params(handler_key: str, params: dict[str, Any]) -> None:
        if not isinstance(params, dict):
            raise InvalidRuntimePayloadError(f"{handler_key} 的 params 必须是对象")
        schema_version = params.get("schema_version")
        if schema_version is not None and not isinstance(schema_version, int):
            raise InvalidRuntimePayloadError(f"{handler_key} 的 params.schema_version 必须是整数")
