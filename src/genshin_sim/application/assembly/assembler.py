from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from genshin_sim.content import HandlerNotFoundError, HandlerRegistry, RuntimeHandlerRequest
from genshin_sim.core.actions import ActionManager
from genshin_sim.core.simulation import (
    BasicRuntimeWorld,
    BasicTeamController,
    SimulationContext,
    Simulator,
    TeamRuntimeState,
    TraceInputSystem,
)
from genshin_sim.core.space import SceneTarget, Space, Vector3


@dataclass(frozen=True, slots=True)
class RuntimeAssetBundle:
    slot: int
    character: CharacterAsset
    weapon: WeaponAsset | None
    artifact_sets: tuple[ArtifactSetAsset, ...]
    artifact_bonuses: tuple[ArtifactSetBonus, ...]
    effect_payloads: tuple[EffectPayload, ...]


@dataclass(slots=True)
class AssembledSimulation:
    config: SimulationConfig
    context: SimulationContext
    simulator: Simulator
    action_manager: ActionManager
    team_controller: BasicTeamController
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
        self._prepare_handlers(assets)

        context = SimulationContext()
        context.space = Space(
            SceneTarget(
                target.target_id,
                position=Vector3(
                    target.position.x,
                    target.position.y,
                    target.position.z,
                ),
                level=target.level,
            )
            for target in config.scene.targets
        )

        action_manager = ActionManager()
        team_state = TeamRuntimeState(team_size=len(config.team), active_slot=1)
        team_controller = BasicTeamController(
            team_state,
            action_manager=action_manager,
        )
        input_system = TraceInputSystem(config.to_core_input_frames(), team_controller)
        runtime_world = BasicRuntimeWorld([action_manager])
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
            team_controller=team_controller,
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
            raise MissingRuntimeAssetError(
                f"加载队伍槽位 {slot.slot} 的资产失败：{exc}"
            ) from exc

        return RuntimeAssetBundle(
            slot=slot.slot,
            character=character,
            weapon=weapon,
            artifact_sets=tuple(artifact_sets),
            artifact_bonuses=tuple(artifact_bonuses),
            effect_payloads=tuple(effect_payloads),
        )

    def _prepare_handlers(self, bundles: tuple[RuntimeAssetBundle, ...]) -> None:
        for bundle in bundles:
            self._prepare_asset_handler(
                bundle.character.handler_key,
                owner_type="character",
                owner_key=bundle.character.asset_key,
                slot=bundle.slot,
                asset=bundle.character,
            )
            if bundle.weapon is not None:
                self._prepare_asset_handler(
                    bundle.weapon.handler_key,
                    owner_type="weapon",
                    owner_key=bundle.weapon.asset_key,
                    slot=bundle.slot,
                    asset=bundle.weapon,
                )
            for artifact_set in bundle.artifact_sets:
                self._prepare_asset_handler(
                    artifact_set.handler_key,
                    owner_type="artifact_set",
                    owner_key=artifact_set.asset_key,
                    slot=bundle.slot,
                    asset=artifact_set,
                )
            for bonus in bundle.artifact_bonuses:
                self._prepare_payload_handler(
                    bonus.handler_key,
                    owner_type="artifact_set_bonus",
                    owner_key=bonus.artifact_set_key,
                    slot=bundle.slot,
                    params=bonus.params,
                )
            for payload in bundle.effect_payloads:
                self._prepare_payload_handler(
                    payload.handler_key,
                    owner_type=payload.owner_type,
                    owner_key=payload.owner_key,
                    slot=bundle.slot,
                    params=payload.params,
                )

    def _prepare_asset_handler(
        self,
        handler_key: str | None,
        *,
        owner_type: str,
        owner_key: str,
        slot: int,
        asset: Any,
    ) -> None:
        if handler_key is None:
            return
        self._invoke_handler(
            handler_key,
            RuntimeHandlerRequest(
                handler_key=handler_key,
                owner_type=owner_type,
                owner_key=owner_key,
                slot=slot,
                asset=asset,
            ),
        )

    def _prepare_payload_handler(
        self,
        handler_key: str,
        *,
        owner_type: str,
        owner_key: str,
        slot: int,
        params: dict[str, Any],
    ) -> None:
        self._validate_payload_params(handler_key, params)
        self._invoke_handler(
            handler_key,
            RuntimeHandlerRequest(
                handler_key=handler_key,
                owner_type=owner_type,
                owner_key=owner_key,
                slot=slot,
                params=params,
            ),
        )

    def _invoke_handler(self, handler_key: str, request: RuntimeHandlerRequest) -> None:
        try:
            self.handler_registry.create(request)
        except (HandlerNotFoundError, LookupError) as exc:
            raise MissingRuntimeHandlerError(
                f"组装阶段缺少 handler：{handler_key}"
            ) from exc

    @staticmethod
    def _validate_payload_params(handler_key: str, params: dict[str, Any]) -> None:
        if not isinstance(params, dict):
            raise InvalidRuntimePayloadError(f"{handler_key} 的 params 必须是对象")
        schema_version = params.get("schema_version")
        if schema_version is not None and not isinstance(schema_version, int):
            raise InvalidRuntimePayloadError(
                f"{handler_key} 的 params.schema_version 必须是整数"
            )
