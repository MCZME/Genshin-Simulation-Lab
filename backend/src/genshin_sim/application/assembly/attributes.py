from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.input import SimulationInput
from genshin_sim.assets.models import CharacterLevelStats, WeaponLevelStats
from genshin_sim.content.definitions.content_unit import ContentUnit
from genshin_sim.core.attributes import (
    BONUS_DAMAGE_ANEMO,
    BONUS_DAMAGE_CRYO,
    BONUS_DAMAGE_DENDRO,
    BONUS_DAMAGE_ELECTRO,
    BONUS_DAMAGE_GEO,
    BONUS_DAMAGE_HYDRO,
    BONUS_DAMAGE_PHYSICAL,
    BONUS_DAMAGE_PYRO,
    BONUS_HEALING_OUTGOING,
    BONUS_SHIELD_STRENGTH,
    RESISTANCE_KEYS_BY_ELEMENT,
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STAT_CRIT_DAMAGE,
    STAT_CRIT_RATE,
    STAT_DEF_BASE,
    STAT_DEF_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    STAT_ENERGY_RECHARGE,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeDefinitionRegistry,
    AttributeKey,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
    AttributeSystemError,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProvider,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStackingGroupDefinition,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
    create_public_attribute_registry,
    validate_finite_float,
)


class AttributeRuntimeAssetBundle(Protocol):
    @property
    def slot(self) -> int: ...

    @property
    def character_level_stats(self) -> CharacterLevelStats: ...

    @property
    def weapon_level_stats(self) -> WeaponLevelStats | None: ...


class _ContentAttributeModifier(Protocol):
    @property
    def modifier_key(self) -> str: ...

    @property
    def targets(self) -> Sequence[str]: ...

    def evaluate(self, query: object, context: object) -> Sequence[ModifierTerm]: ...


@dataclass(frozen=True, slots=True)
class AttributeRuntimeBundle:
    definitions: AttributeDefinitionRegistry
    base_attributes: BaseAttributeSet
    modifier_index: ModifierProviderIndex
    resolver: AttributeResolver


def build_attribute_runtime(
    *,
    config: SimulationInput,
    assets: Sequence[AttributeRuntimeAssetBundle],
    content_units: Sequence[ContentUnit],
    extra_providers: Sequence[ModifierProvider] = (),
) -> AttributeRuntimeBundle:
    try:
        definitions = create_public_attribute_registry()
        _register_content_attribute_definitions(definitions, content_units)
        _register_content_attribute_stacking_groups(definitions, content_units)
        base_contributions = tuple(_iter_base_contributions(config=config, assets=assets))
        static_providers = tuple(_iter_static_asset_modifier_providers(assets)) + tuple(
            _iter_config_artifact_modifier_providers(config)
        )
        content_providers = tuple(_iter_content_attribute_providers(content_units, definitions))
        base_attributes = BaseAttributeSet(base_contributions)
        modifier_index = ModifierProviderIndex(
            (*static_providers, *content_providers, *tuple(extra_providers)),
            registry=definitions,
        )
        resolver = AttributeResolver(
            definitions=definitions,
            base_attributes=base_attributes,
            modifier_index=modifier_index,
        )
    except AttributeSystemError as exc:
        raise InvalidRuntimePayloadError(str(exc)) from exc
    return AttributeRuntimeBundle(
        definitions=definitions,
        base_attributes=base_attributes,
        modifier_index=modifier_index,
        resolver=resolver,
    )


def _iter_base_contributions(
    *,
    config: SimulationInput,
    assets: Sequence[AttributeRuntimeAssetBundle],
) -> Iterable[tuple[AttributeSubjectRef, BaseAttributeContribution]]:
    for bundle in assets:
        subject_ref = AttributeSubjectRef.character(_character_entity_id(bundle.slot))
        source_ref = RuntimeSourceRef(
            RuntimeSourceKind.ASSET,
            (
                f"{bundle.character_level_stats.character_key}:level:"
                f"{bundle.character_level_stats.level}"
            ),
        )
        yield (
            subject_ref,
            BaseAttributeContribution(
                attribute_key=STAT_HP_BASE,
                value=bundle.character_level_stats.base_hp,
                source_ref=source_ref,
            ),
        )
        yield (
            subject_ref,
            BaseAttributeContribution(
                attribute_key=STAT_ATK_BASE,
                value=bundle.character_level_stats.base_atk,
                source_ref=source_ref,
            ),
        )
        yield (
            subject_ref,
            BaseAttributeContribution(
                attribute_key=STAT_DEF_BASE,
                value=bundle.character_level_stats.base_def,
                source_ref=source_ref,
            ),
        )
        if bundle.weapon_level_stats is not None:
            weapon_source_ref = RuntimeSourceRef(
                RuntimeSourceKind.ASSET,
                f"{bundle.weapon_level_stats.weapon_key}:level:{bundle.weapon_level_stats.level}",
            )
            yield (
                subject_ref,
                BaseAttributeContribution(
                    attribute_key=STAT_ATK_BASE,
                    value=bundle.weapon_level_stats.base_atk,
                    source_ref=weapon_source_ref,
                ),
            )

    for target in config.scene.targets:
        subject_ref = AttributeSubjectRef.target(f"target:{target.target_id}")
        for resistance_name, resistance_value in target.resistance.items():
            try:
                attribute_key = RESISTANCE_KEYS_BY_ELEMENT[resistance_name]
            except KeyError as exc:
                raise InvalidRuntimePayloadError(
                    f"目标 {target.target_id!r} 包含不支持的抗性：{resistance_name}"
                ) from exc
            yield (
                subject_ref,
                BaseAttributeContribution(
                    attribute_key=attribute_key,
                    value=validate_finite_float(
                        cast(float | int, resistance_value),
                        f"scene.targets.{target.target_id}.resistance.{resistance_name}",
                    ),
                    source_ref=RuntimeSourceRef(
                        RuntimeSourceKind.CONFIG,
                        f"scene.target:{target.target_id}.resistance.{resistance_name}",
                    ),
                ),
            )


def _iter_static_asset_modifier_providers(
    assets: Sequence[AttributeRuntimeAssetBundle],
) -> Iterable[StaticModifierProvider]:
    for bundle in assets:
        subject_ref = AttributeSubjectRef.character(_character_entity_id(bundle.slot))
        terms: list[ModifierTerm] = []
        character_source_ref = RuntimeSourceRef(
            RuntimeSourceKind.ASSET,
            f"{bundle.character_level_stats.character_key}:ascension_stat",
        )
        character_provider_key = f"assembly.asset.character_ascension.{bundle.slot}"
        _append_asset_stat_modifier(
            terms,
            stat_name=bundle.character_level_stats.ascension_stat,
            value=bundle.character_level_stats.ascension_value,
            provider_key=character_provider_key,
            source_ref=character_source_ref,
        )
        if bundle.weapon_level_stats is not None:
            weapon_provider_key = f"assembly.asset.weapon_secondary.{bundle.slot}"
            weapon_source_ref = RuntimeSourceRef(
                RuntimeSourceKind.ASSET,
                f"{bundle.weapon_level_stats.weapon_key}:secondary_stat",
            )
            _append_asset_stat_modifier(
                terms,
                stat_name=bundle.weapon_level_stats.secondary_stat,
                value=bundle.weapon_level_stats.secondary_value,
                provider_key=weapon_provider_key,
                source_ref=weapon_source_ref,
            )
        if not terms:
            continue
        provider_key = f"assembly.asset.static_modifiers.{bundle.slot}"
        normalized_terms = tuple(
            ModifierTerm(
                target_key=term.target_key,
                stage=term.stage,
                value=term.value,
                provider_key=provider_key,
                source_ref=term.source_ref,
                audit_tags=term.audit_tags,
            )
            for term in terms
        )
        yield StaticModifierProvider(
            ModifierProviderSpec(
                provider_key=provider_key,
                writes=frozenset(term.target_key for term in normalized_terms),
                owner_ref=subject_ref,
            ),
            normalized_terms,
            subject_ref=subject_ref,
        )


def _append_asset_stat_modifier(
    terms: list[ModifierTerm],
    *,
    stat_name: str | None,
    value: float | None,
    provider_key: str,
    source_ref: RuntimeSourceRef,
) -> None:
    if stat_name is None or value is None:
        return
    try:
        target_key, stage = _ASSET_STAT_TO_MODIFIER[stat_name]
    except KeyError as exc:
        raise InvalidRuntimePayloadError(f"不支持的资产属性修饰：{stat_name}") from exc
    terms.append(
        ModifierTerm(
            target_key=target_key,
            stage=stage,
            value=value,
            provider_key=provider_key,
            source_ref=source_ref,
            audit_tags=(stat_name,),
        )
    )


def _iter_config_artifact_modifier_providers(
    config: SimulationInput,
) -> Iterable[StaticModifierProvider]:
    for team_index, slot in enumerate(config.team):
        terms: list[ModifierTerm] = []
        for stat_key, stat_value in slot.artifacts.stats.items():
            try:
                target_key, stage = _ARTIFACT_STAT_TO_MODIFIER[stat_key]
            except KeyError as exc:
                raise InvalidRuntimePayloadError(f"不支持的圣遗物词条：{stat_key}") from exc
            terms.append(
                ModifierTerm(
                    target_key=target_key,
                    stage=stage,
                    value=validate_finite_float(
                        cast(float | int, stat_value),
                        f"team[{team_index}].artifacts.stats.{stat_key}",
                    ),
                    provider_key=f"assembly.config.artifact_stats.{slot.slot}",
                    source_ref=RuntimeSourceRef(
                        RuntimeSourceKind.CONFIG,
                        f"config:team[{team_index}].artifacts.stats.{stat_key}",
                    ),
                    audit_tags=(stat_key,),
                )
            )
        if not terms:
            continue
        subject_ref = AttributeSubjectRef.character(_character_entity_id(slot.slot))
        provider_key = f"assembly.config.artifact_stats.{slot.slot}"
        yield StaticModifierProvider(
            ModifierProviderSpec(
                provider_key=provider_key,
                writes=frozenset(term.target_key for term in terms),
                owner_ref=subject_ref,
            ),
            tuple(terms),
            subject_ref=subject_ref,
        )


def _iter_content_attribute_providers(
    content_units: Sequence[ContentUnit],
    definitions: AttributeDefinitionRegistry,
) -> Iterable[ModifierProvider]:
    for unit in content_units:
        yield from unit.attribute_providers
        for modifier in unit.modifiers:
            writes = frozenset(
                attribute_key
                for target in modifier.targets
                if _is_registered_attribute_key(target, definitions)
                for attribute_key in (AttributeKey(target),)
            )
            if not writes:
                continue
            yield _ContentAttributeModifierProvider(
                modifier=modifier,
                provider_spec=ModifierProviderSpec(
                    provider_key=modifier.modifier_key,
                    writes=writes,
                    private_namespace=unit.handler_key,
                    owner_ref=_attribute_subject_ref(modifier.owner_ref),
                ),
                subject_ref=_attribute_subject_ref(modifier.owner_ref),
            )


def _register_content_attribute_definitions(
    definitions: AttributeDefinitionRegistry,
    content_units: Sequence[ContentUnit],
) -> None:
    for unit in content_units:
        for definition in unit.attribute_definitions:
            if definition.namespace_owner != unit.handler_key:
                raise InvalidRuntimePayloadError(
                    f"content {unit.handler_key!r} 不能注册命名空间 "
                    f"{definition.namespace_owner!r} 的私有属性"
                )
            definitions.register(definition)


def _register_content_attribute_stacking_groups(
    definitions: AttributeDefinitionRegistry,
    content_units: Sequence[ContentUnit],
) -> None:
    for unit in content_units:
        seen: set[str] = set()
        for group in unit.attribute_stacking_groups:
            if not isinstance(group, ModifierStackingGroupDefinition):
                raise InvalidRuntimePayloadError("attribute_stacking_groups 必须是属性叠加组定义")
            if group.group_key in seen:
                raise InvalidRuntimePayloadError(
                    f"content {unit.handler_key!r} 重复声明 stacking group：{group.group_key}"
                )
            seen.add(group.group_key)
            if not group.group_key.startswith(f"{unit.handler_key}."):
                raise InvalidRuntimePayloadError(
                    f"content {unit.handler_key!r} 不能注册越界 stacking group：{group.group_key}"
                )
            definitions.register_stacking_group(group)


def _is_registered_attribute_key(
    value: str,
    definitions: AttributeDefinitionRegistry,
) -> bool:
    try:
        key = AttributeKey(value)
    except Exception:
        return False
    return definitions.contains(key)


@dataclass(frozen=True, slots=True)
class _ContentAttributeModifierProvider:
    modifier: _ContentAttributeModifier
    provider_spec: ModifierProviderSpec
    subject_ref: AttributeSubjectRef

    def contribute(self, query: AttributeQuery, session: object) -> Sequence[ModifierTerm]:
        if query.subject_ref != self.subject_ref:
            return ()
        raw_terms = self.modifier.evaluate(query, session)
        terms: list[ModifierTerm] = []
        for raw_term in raw_terms:
            if not isinstance(raw_term, ModifierTerm):
                raise InvalidRuntimePayloadError("content modifier 必须返回 core ModifierTerm")
            if raw_term.target_key == query.attribute_key:
                terms.append(raw_term)
        return tuple(terms)


def _character_entity_id(slot: int) -> str:
    return f"character:slot_{slot}"


def _attribute_subject_ref(owner_ref: str) -> AttributeSubjectRef:
    if owner_ref.startswith("character:"):
        return AttributeSubjectRef.character(owner_ref)
    if owner_ref.startswith("target:"):
        return AttributeSubjectRef.target(owner_ref)
    raise InvalidRuntimePayloadError(f"content attribute modifier owner_ref 不支持：{owner_ref!r}")


_ASSET_STAT_TO_MODIFIER: Mapping[str, tuple[AttributeKey, ModifierStage]] = {
    "hp_percent": (STAT_HP_MAX, ModifierStage.PERCENT_ADD),
    "atk_percent": (STAT_ATK_TOTAL, ModifierStage.PERCENT_ADD),
    "def_percent": (STAT_DEF_TOTAL, ModifierStage.PERCENT_ADD),
    "crit_rate": (STAT_CRIT_RATE, ModifierStage.FLAT_ADD),
    "crit_damage": (STAT_CRIT_DAMAGE, ModifierStage.FLAT_ADD),
    "elemental_mastery": (STAT_ELEMENTAL_MASTERY, ModifierStage.FLAT_ADD),
    "energy_recharge": (STAT_ENERGY_RECHARGE, ModifierStage.FLAT_ADD),
    "healing_bonus": (BONUS_HEALING_OUTGOING, ModifierStage.FLAT_ADD),
    "shield_strength": (BONUS_SHIELD_STRENGTH, ModifierStage.FLAT_ADD),
    "physical_damage_bonus": (BONUS_DAMAGE_PHYSICAL, ModifierStage.FLAT_ADD),
    "pyro_damage_bonus": (BONUS_DAMAGE_PYRO, ModifierStage.FLAT_ADD),
    "hydro_damage_bonus": (BONUS_DAMAGE_HYDRO, ModifierStage.FLAT_ADD),
    "electro_damage_bonus": (BONUS_DAMAGE_ELECTRO, ModifierStage.FLAT_ADD),
    "cryo_damage_bonus": (BONUS_DAMAGE_CRYO, ModifierStage.FLAT_ADD),
    "anemo_damage_bonus": (BONUS_DAMAGE_ANEMO, ModifierStage.FLAT_ADD),
    "geo_damage_bonus": (BONUS_DAMAGE_GEO, ModifierStage.FLAT_ADD),
    "dendro_damage_bonus": (BONUS_DAMAGE_DENDRO, ModifierStage.FLAT_ADD),
}

_ARTIFACT_STAT_TO_MODIFIER: Mapping[str, tuple[AttributeKey, ModifierStage]] = {
    **_ASSET_STAT_TO_MODIFIER,
    "flat_hp": (STAT_HP_MAX, ModifierStage.FLAT_ADD),
    "flat_atk": (STAT_ATK_TOTAL, ModifierStage.FLAT_ADD),
    "flat_def": (STAT_DEF_TOTAL, ModifierStage.FLAT_ADD),
}
