from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

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
    EffectPayload,
    WeaponAsset,
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
    TEAM_SWITCH_ACTION_KEY,
    ActionManager,
    CharacterActionInterpreter,
    TeamActionController,
)
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import ImpactDispatcher, ImpactFactory, ImpactRuntime
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    SimulationContext,
    Simulator,
    TeamRuntimeState,
    TraceInputSystem,
)
from genshin_sim.core.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    CreatedObjectBehavior,
    CreatedObjectRuntime,
    Space,
    SpatialEntity,
    SpatialEntityKind,
    Vector3,
)
from genshin_sim.core.space.runtime import SpaceRuntime, TeamSwitchActionConsumer


@dataclass(frozen=True, slots=True)
class RuntimeAssetBundle:
    slot: int
    character: CharacterAsset
    weapon: WeaponAsset | None
    artifact_sets: tuple[ArtifactSetAsset, ...]
    artifact_bonuses: tuple[ArtifactSetBonus, ...]
    effect_payloads: tuple[EffectPayload, ...]


@dataclass(frozen=True, slots=True)
class RuntimeContentBundle:
    contributions: tuple[ContentRuntimeContribution, ...]
    content_state_store: ContentStateStore
    action_interpreters: dict[int, CharacterActionInterpreter]
    impact_factories: dict[str, ImpactFactory]
    created_object_behaviors: dict[str, CreatedObjectBehavior]
    event_hooks: tuple[EventHook, ...]
    modifiers: tuple[Modifier, ...]


@dataclass(frozen=True, slots=True)
class _TeamActiveSlotProvider:
    team_state: TeamRuntimeState

    @property
    def active_slot(self) -> int:
        return self.team_state.active_slot


@dataclass(slots=True)
class AssembledSimulation:
    config: SimulationConfig
    context: SimulationContext
    simulator: Simulator
    action_manager: ActionManager
    team_action_controller: TeamActionController
    impact_dispatcher: ImpactDispatcher
    space_runtime: SpaceRuntime
    impact_runtime: ImpactRuntime
    team_switch_consumer: TeamSwitchActionConsumer
    content_bundle: RuntimeContentBundle
    input_system: TraceInputSystem
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

        context = SimulationContext()
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

        team_state = TeamRuntimeState(
            (
                CharacterRuntimeState(
                    slot=slot.slot,
                    character_key=slot.character.asset_key,
                    level=slot.character.level,
                    constellation=slot.character.constellation,
                    talent_levels=slot.character.talents,
                )
                for slot in config.team
            ),
            active_slot=1,
        )
        action_manager = ActionManager()
        team_action_controller = TeamActionController(
            _TeamActiveSlotProvider(team_state),
            action_manager,
            interpreters=content_bundle.action_interpreters,
        )
        impact_dispatcher = ImpactDispatcher(content_bundle.impact_factories)
        team_switch_consumer = TeamSwitchActionConsumer(
            on_switch_accepted=team_action_controller.cancel_pending_sessions_for_slot,
        )
        created_object_runtime = CreatedObjectRuntime(content_bundle.created_object_behaviors)
        space_runtime = SpaceRuntime(
            space=space,
            team_state=team_state,
            targets=target_states,
            created_object_runtime=created_object_runtime,
            action_manager=action_manager,
        )
        space_runtime.register_consumer(
            ACTIVE_CHARACTER_ENTITY_ID,
            TEAM_SWITCH_ACTION_KEY,
            team_switch_consumer,
        )
        context.space_runtime = space_runtime
        impact_runtime = ImpactRuntime(
            action_manager,
            impact_dispatcher,
        )
        input_system = TraceInputSystem(config.to_core_input_frames(), team_action_controller)
        runtime_world = BasicRuntimeWorld(
            [team_action_controller, action_manager, space_runtime, impact_runtime]
        )
        simulator = Simulator(
            context,
            input_system=input_system,
            runtime_world=runtime_world,
            max_frames=config.run_options.max_frames,
        )

        return AssembledSimulation(
            config=config,
            context=context,
            simulator=simulator,
            action_manager=action_manager,
            team_action_controller=team_action_controller,
            impact_dispatcher=impact_dispatcher,
            space_runtime=space_runtime,
            impact_runtime=impact_runtime,
            team_switch_consumer=team_switch_consumer,
            content_bundle=content_bundle,
            input_system=input_system,
            runtime_world=runtime_world,
            assets=assets,
        )

    def _load_slot_assets(self, slot: TeamSlotConfig) -> RuntimeAssetBundle:
        try:
            character = self.asset_repository.get_character(slot.character.asset_key)
            self.asset_repository.get_character_level_stats(
                character.asset_key,
                slot.character.level,
            )

            weapon = None
            if slot.weapon is not None:
                weapon = self.asset_repository.get_weapon(slot.weapon.asset_key)
                self.asset_repository.get_weapon_level_stats(weapon.asset_key, slot.weapon.level)

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
            weapon=weapon,
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
        action_interpreters: dict[int, CharacterActionInterpreter] = {}
        impact_factories: dict[str, ImpactFactory] = {}
        created_object_behaviors: dict[str, CreatedObjectBehavior] = {}
        event_hooks: list[EventHook] = []
        modifiers: list[Modifier] = []

        for contribution in contributions:
            self._register_content_state(state_store, contribution)
            self._register_action_interpreter(action_interpreters, contribution)
            self._register_impact_factories(impact_factories, contribution)
            self._register_created_object_behaviors(created_object_behaviors, contribution)
            event_hooks.extend(contribution.event_hooks)
            modifiers.extend(contribution.modifiers)

        return RuntimeContentBundle(
            contributions=contributions,
            content_state_store=state_store,
            action_interpreters=action_interpreters,
            impact_factories=impact_factories,
            created_object_behaviors=created_object_behaviors,
            event_hooks=tuple(event_hooks),
            modifiers=tuple(modifiers),
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
        action_interpreters: dict[int, CharacterActionInterpreter],
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
            CharacterActionInterpreter,
            contribution.action_interpreter,
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
