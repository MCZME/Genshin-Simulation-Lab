"""内容编译阶段：配置 + 资产数据 -> 内容单元与运行时 bundle。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from genshin_sim.application.assembly.errors import (
    InvalidRuntimePayloadError,
    MissingRuntimeHandlerError,
)
from genshin_sim.application.assembly.models import (
    RuntimeAssetBundle,
    RuntimeContentBundle,
)
from genshin_sim.application.config import SimulationConfig, TeamSlotConfig
from genshin_sim.assets.models import ArtifactSetAsset, ArtifactSetBonus
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.definitions.effects import UnlockValues
from genshin_sim.content.models import EventHook, Modifier
from genshin_sim.content.registries import (
    ArtifactContentUnitRequest,
    CharacterContentUnitRequest,
    ContentUnitFactoryNotFoundError,
    ContentUnitRegistry,
    EffectContentUnitRequest,
    WeaponContentUnitRequest,
)
from genshin_sim.core.actions import Action, ActionInterpreter
from genshin_sim.core.attributes import ModifierStackingGroupDefinition
from genshin_sim.core.entity_states.content_state import ContentStateMount
from genshin_sim.core.impacts import ImpactFactory
from genshin_sim.core.space import CreatedObjectBehavior
from genshin_sim.core.systems.aura_icd import IcdDefinition
from genshin_sim.core.systems.buff import BuffDefinition, BuffSystemError
from genshin_sim.core.systems.cooldown import (
    CooldownDefinition,
    CooldownDurationTerm,
    CooldownKey,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProvider,
    DamageModifierStackingGroupDefinition,
)
from genshin_sim.core.systems.infusion import InfusionDefinition


class ContentCompiler:
    """把资产数据与配置编译为内容单元并聚合成运行时 bundle。"""

    def __init__(self, content_unit_registry: ContentUnitRegistry) -> None:
        self.content_unit_registry = content_unit_registry

    def compile(
        self,
        config: SimulationConfig,
        assets: tuple[RuntimeAssetBundle, ...],
    ) -> RuntimeContentBundle:
        slot_configs = {slot.slot: slot for slot in config.team}
        try:
            units = self._prepare_units(assets, slot_configs)
        except BuffSystemError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc
        return self._build_content_bundle(units)

    def _prepare_units(
        self,
        bundles: tuple[RuntimeAssetBundle, ...],
        slot_configs: dict[int, TeamSlotConfig],
    ) -> tuple[ContentUnit, ...]:
        units: list[ContentUnit] = []
        for bundle in bundles:
            slot_config = slot_configs[bundle.slot]
            raw_effect_units = [
                self._prepare_effect(payload, slot=bundle.slot)
                for payload in bundle.effect_payloads
            ]
            effect_units = tuple(unit for unit in raw_effect_units if unit is not None)
            effect_units = tuple(
                self._gate_static_slices(unit, bundle, slot_config) for unit in effect_units
            )
            talent_boosts = self._collect_talent_boosts(effect_units)
            cooldown_duration_terms = self._collect_cooldown_duration_terms(
                effect_units,
                slot=bundle.slot,
            )
            unit = self._prepare_character(
                bundle,
                slot_config,
                talent_boosts=talent_boosts,
                cooldown_duration_terms=cooldown_duration_terms,
            )
            if unit is not None:
                units.append(unit)
            if bundle.weapon is not None:
                unit = self._prepare_weapon(bundle, slot_config)
                if unit is not None:
                    units.append(unit)
            for artifact_set in bundle.artifact_sets:
                unit = self._prepare_artifact_set(
                    artifact_set,
                    bundle.slot,
                    slot_config,
                )
                if unit is not None:
                    units.append(unit)
            for bonus in bundle.artifact_bonuses:
                unit = self._prepare_artifact_bonus(
                    bonus,
                    bundle.slot,
                )
                if unit is not None:
                    units.append(unit)
            units.extend(effect_units)
        return tuple(units)

    def _prepare_character(
        self,
        bundle: RuntimeAssetBundle,
        slot_config: TeamSlotConfig,
        *,
        talent_boosts: Mapping[str, int],
        cooldown_duration_terms: Mapping[
            CooldownKey,
            tuple[CooldownDurationTerm, ...],
        ],
    ) -> ContentUnit | None:
        handler_key = bundle.character.handler_key
        if handler_key is None:
            return None
        if not self.content_unit_registry.has_character_handler(handler_key):
            raise MissingRuntimeHandlerError(f"组装阶段缺少角色 handler：{handler_key}")
        request = CharacterContentUnitRequest(
            handler_key=handler_key,
            character_key=bundle.character.asset_key,
            slot=bundle.slot,
            constellation=slot_config.character.constellation,
            talent_levels=slot_config.character.talents,
            talent_boosts=dict(talent_boosts),
            cooldown_duration_terms=cooldown_duration_terms,
            talent_scalings=bundle.talent_scalings,
            asset=bundle.character,
        )
        try:
            return self.content_unit_registry.create_character(request)
        except ContentUnitFactoryNotFoundError as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少角色 handler：{handler_key}") from exc
        except ContentUnitValidationError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc

    @staticmethod
    def _gate_static_slices(
        unit: ContentUnit,
        bundle: RuntimeAssetBundle,
        slot_config: TeamSlotConfig,
    ) -> ContentUnit:
        """按静态解锁条件过滤效果单元的静态贡献切片。

        事件 hook 保留在单元内，仍由 HookDispatcher 在第 0 帧按解锁求值；
        ``talent_level_boosts`` / ``cooldown_duration_terms`` / 属性 provider
        在编译期按配置命座过滤，避免锁定效果影响倍率、冷却或属性解析。
        """

        if len(unit.effects) != 1:
            return unit
        unlock = unit.effects[0].unlock
        values = UnlockValues(
            constellation=slot_config.character.constellation,
            ascension_phase=bundle.character_level_stats.ascension_phase,
            talent_levels=slot_config.character.talents,
        )
        if unlock.evaluate(values):
            return unit
        if not (
            unit.talent_level_boosts or unit.cooldown_duration_terms or unit.attribute_providers
        ):
            return unit
        return replace(
            unit,
            talent_level_boosts={},
            cooldown_duration_terms={},
            attribute_providers=(),
        )

    @staticmethod
    def _collect_talent_boosts(
        units: tuple[ContentUnit, ...],
    ) -> dict[str, int]:
        boosts: dict[str, int] = {}
        for unit in units:
            for talent_key, boost in unit.talent_level_boosts.items():
                if talent_key in boosts:
                    raise InvalidRuntimePayloadError(f"天赋 {talent_key} 存在多个等级提升来源")
                boosts[talent_key] = boost
        return boosts

    @staticmethod
    def _collect_cooldown_duration_terms(
        units: tuple[ContentUnit, ...],
        *,
        slot: int,
    ) -> dict[CooldownKey, tuple[CooldownDurationTerm, ...]]:
        owner_ref = f"character:slot_{slot}"
        collected: dict[CooldownKey, dict[tuple[str, str], CooldownDurationTerm]] = {}
        for unit in units:
            for key, terms in unit.cooldown_duration_terms.items():
                if key.subject.subject_id != owner_ref:
                    raise InvalidRuntimePayloadError(
                        f"冷却时长 term 归属不符：{key.subject.subject_id}"
                    )
                bucket = collected.setdefault(key, {})
                for term in terms:
                    marker = (term.term_key, term.source_ref)
                    if marker in bucket:
                        raise InvalidRuntimePayloadError(
                            f"冷却 {key.ability_key} 重复 duration term：{marker}"
                        )
                    bucket[marker] = term
        return {key: tuple(bucket.values()) for key, bucket in collected.items()}

    def _prepare_weapon(
        self,
        bundle: RuntimeAssetBundle,
        slot_config: TeamSlotConfig,
    ) -> ContentUnit | None:
        if bundle.weapon is None:
            return None
        handler_key = bundle.weapon.handler_key
        if handler_key is None:
            return None
        if not self.content_unit_registry.has_weapon_handler(handler_key):
            raise MissingRuntimeHandlerError(f"组装阶段缺少武器 handler：{handler_key}")
        assert bundle.weapon is not None
        assert slot_config.weapon is not None
        request = WeaponContentUnitRequest(
            handler_key=handler_key,
            weapon_key=bundle.weapon.asset_key,
            slot=bundle.slot,
            refinement=slot_config.weapon.refinement,
            asset=bundle.weapon,
        )
        try:
            return self.content_unit_registry.create_weapon(request)
        except ContentUnitFactoryNotFoundError as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少武器 handler：{handler_key}") from exc
        except ContentUnitValidationError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc

    def _prepare_artifact_set(
        self,
        artifact_set: ArtifactSetAsset,
        slot: int,
        slot_config: TeamSlotConfig,
    ) -> ContentUnit | None:
        handler_key = artifact_set.handler_key
        if handler_key is None:
            return None
        if not self.content_unit_registry.has_artifact_handler(handler_key):
            raise MissingRuntimeHandlerError(f"组装阶段缺少圣遗物 handler：{handler_key}")
        request = ArtifactContentUnitRequest(
            handler_key=handler_key,
            artifact_key=artifact_set.asset_key,
            slot=slot,
            artifact_kind="artifact_set",
            asset=artifact_set,
        )
        try:
            return self.content_unit_registry.create_artifact(request)
        except ContentUnitFactoryNotFoundError as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少圣遗物 handler：{handler_key}") from exc
        except ContentUnitValidationError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc

    def _prepare_artifact_bonus(
        self,
        bonus: ArtifactSetBonus,
        slot: int,
    ) -> ContentUnit | None:
        handler_key = bonus.handler_key
        if handler_key is None:
            return None
        if not self.content_unit_registry.has_artifact_handler(handler_key):
            raise MissingRuntimeHandlerError(f"组装阶段缺少圣遗物 handler：{handler_key}")
        request = ArtifactContentUnitRequest(
            handler_key=handler_key,
            artifact_key=bonus.artifact_set_key,
            slot=slot,
            artifact_kind="artifact_set_bonus",
            piece_count=bonus.piece_count,
            params=bonus.params,
        )
        try:
            return self.content_unit_registry.create_artifact(request)
        except ContentUnitFactoryNotFoundError as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少圣遗物 handler：{handler_key}") from exc
        except ContentUnitValidationError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc

    def _prepare_effect(
        self,
        payload: object,
        *,
        slot: int,
    ) -> ContentUnit | None:
        from genshin_sim.assets.models import EffectPayload

        if not isinstance(payload, EffectPayload):
            raise InvalidRuntimePayloadError("效果 payload 必须是 EffectPayload")
        handler_key = payload.handler_key
        self._validate_payload_params(handler_key, payload.params)
        if not self.content_unit_registry.has_effect_handler(handler_key):
            raise MissingRuntimeHandlerError(f"组装阶段缺少效果 handler：{handler_key}")
        request = EffectContentUnitRequest(
            handler_key=handler_key,
            effect_key=payload.effect_key,
            effect_kind=payload.effect_kind,
            owner_type=payload.owner_type,
            owner_key=payload.owner_key,
            slot=slot,
            params=payload.params,
            unlock_key=payload.unlock_key,
        )
        try:
            return self.content_unit_registry.create_effect(request)
        except ContentUnitFactoryNotFoundError as exc:
            raise MissingRuntimeHandlerError(f"组装阶段缺少效果 handler：{handler_key}") from exc
        except ContentUnitValidationError as exc:
            raise InvalidRuntimePayloadError(str(exc)) from exc

    def _build_content_bundle(
        self,
        units: tuple[ContentUnit, ...],
    ) -> RuntimeContentBundle:
        content_state_mounts: list[ContentStateMount] = []
        action_interpreters: dict[int, ActionInterpreter] = {}
        actions: list[Action] = []
        impact_factories: dict[str, ImpactFactory] = {}
        created_object_behaviors: dict[str, CreatedObjectBehavior] = {}
        event_hooks: list[EventHook] = []
        modifiers: list[Modifier] = []
        damage_modifier_providers: list[DamageModifierProvider] = []
        damage_modifier_stacking_groups: list[DamageModifierStackingGroupDefinition] = []
        attribute_stacking_groups: list[ModifierStackingGroupDefinition] = []
        buff_definitions: list[BuffDefinition] = []
        infusion_definitions: list[InfusionDefinition] = []
        aura_icd_definitions: list[IcdDefinition] = []
        cooldown_definitions: list[CooldownDefinition] = []

        for unit in units:
            self._register_state_schema(content_state_mounts, unit)
            self._register_action_interpreter(action_interpreters, unit)
            actions.extend(unit.actions)
            self._register_impact_factories(impact_factories, unit)
            self._register_created_object_behaviors(
                created_object_behaviors,
                unit,
            )
            event_hooks.extend(unit.event_hooks)
            modifiers.extend(unit.modifiers)
            attribute_stacking_groups.extend(unit.attribute_stacking_groups)
            self._register_buff_definitions(buff_definitions, unit)
            self._register_infusion_definitions(infusion_definitions, unit)
            aura_icd_definitions.extend(unit.aura_icd_definitions)
            cooldown_definitions.extend(unit.cooldown_definitions)
            damage_modifier_providers.extend(unit.damage_modifier_providers)
            damage_modifier_stacking_groups.extend(unit.damage_modifier_stacking_groups)

        return RuntimeContentBundle(
            content_units=units,
            content_state_mounts=tuple(content_state_mounts),
            action_interpreters=action_interpreters,
            actions=tuple(actions),
            impact_factories=impact_factories,
            created_object_behaviors=created_object_behaviors,
            event_hooks=tuple(event_hooks),
            modifiers=tuple(modifiers),
            attribute_stacking_groups=tuple(attribute_stacking_groups),
            buff_definitions=tuple(buff_definitions),
            infusion_definitions=tuple(infusion_definitions),
            aura_icd_definitions=tuple(aura_icd_definitions),
            cooldown_definitions=tuple(cooldown_definitions),
            damage_modifier_providers=tuple(damage_modifier_providers),
            damage_modifier_stacking_groups=tuple(damage_modifier_stacking_groups),
        )

    def _register_state_schema(
        self,
        content_state_mounts: list[ContentStateMount],
        unit: ContentUnit,
    ) -> None:
        schema = unit.state_schema
        if schema is None:
            return
        if any(mount.owner == schema.owner_ref for mount in content_state_mounts):
            raise InvalidRuntimePayloadError(f"宿主 {schema.owner_ref!r} 重复声明状态 schema")
        content_state_mounts.append(
            ContentStateMount(
                state_key=unit.handler_key,
                schema=schema,
            )
        )

    def _register_action_interpreter(
        self,
        action_interpreters: dict[int, ActionInterpreter],
        unit: ContentUnit,
    ) -> None:
        if unit.action_interpreter is None:
            return
        if unit.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise InvalidRuntimePayloadError("只有角色内容可以贡献动作解释器")
        if unit.slot is None:
            raise InvalidRuntimePayloadError("角色动作解释器必须绑定队伍槽位")
        if unit.slot in action_interpreters:
            raise InvalidRuntimePayloadError(f"队伍槽位 {unit.slot} 重复贡献动作解释器")
        action_interpreters[unit.slot] = cast(
            ActionInterpreter,
            unit.action_interpreter,
        )

    def _register_impact_factories(
        self,
        impact_factories: dict[str, ImpactFactory],
        unit: ContentUnit,
    ) -> None:
        for impact_key, factory in unit.impact_factories.items():
            if impact_key in impact_factories:
                raise InvalidRuntimePayloadError(f"重复 impact factory：{impact_key}")
            impact_factories[impact_key] = cast(ImpactFactory, factory)

    def _register_created_object_behaviors(
        self,
        created_object_behaviors: dict[str, CreatedObjectBehavior],
        unit: ContentUnit,
    ) -> None:
        if unit.created_object_behaviors and unit.owner_type is not ContentUnitOwnerType.CHARACTER:
            raise InvalidRuntimePayloadError("只有角色内容可以贡献内容创建对象行为")
        for behavior_key, behavior in unit.created_object_behaviors.items():
            if behavior_key in created_object_behaviors:
                raise InvalidRuntimePayloadError(f"重复内容创建对象行为：{behavior_key}")
            created_object_behaviors[behavior_key] = cast(
                CreatedObjectBehavior,
                behavior,
            )

    def _register_buff_definitions(
        self,
        buff_definitions: list[BuffDefinition],
        unit: ContentUnit,
    ) -> None:
        for definition in unit.buff_definitions:
            if definition.handler_key != unit.handler_key:
                raise InvalidRuntimePayloadError(
                    f"content {unit.handler_key!r} 不能贡献 handler_key "
                    f"{definition.handler_key!r} 的 BuffDefinition"
                )
            buff_definitions.append(definition)

    def _register_infusion_definitions(
        self,
        infusion_definitions: list[InfusionDefinition],
        unit: ContentUnit,
    ) -> None:
        for definition in unit.infusion_definitions:
            if definition.handler_key != unit.handler_key:
                raise InvalidRuntimePayloadError(
                    f"content {unit.handler_key!r} 不能贡献 handler_key "
                    f"{definition.handler_key!r} 的 InfusionDefinition"
                )
            infusion_definitions.append(definition)

    @staticmethod
    def _validate_payload_params(handler_key: str, params: dict[str, Any]) -> None:
        if not isinstance(params, dict):
            raise InvalidRuntimePayloadError(f"{handler_key} 的 params 必须是对象")
        schema_version = params.get("schema_version")
        if schema_version is not None and not isinstance(schema_version, int):
            raise InvalidRuntimePayloadError(f"{handler_key} 的 params.schema_version 必须是整数")
