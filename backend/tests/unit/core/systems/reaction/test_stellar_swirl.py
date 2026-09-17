import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraRuntime,
    AuraStrength,
)
from genshin_sim.core.systems.aura.models import (
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraInstanceRef,
    AuraView,
)
from genshin_sim.core.systems.reaction import (
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionStateInstanceRef,
    create_default_reaction_bootstrap,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl import (
    STELLAR_SWIRL_CAPABILITY_KEY,
    STELLAR_SWIRL_INCOMING_CRYO_ON_ANEMO,
    STELLAR_SWIRL_REACTION_KEY,
    STELLAR_SWIRL_VORTEX_SCOPE,
    STELLAR_SWIRL_WIND_DAMAGE_TAG,
    STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY,
    StellarSwirlRule,
    stellar_swirl_definition,
    stellar_swirl_wind_participants,
)
from genshin_sim.core.systems.reaction.models import (
    AmplifyingReactionProfile,
    CurrentSubjectSelection,
    ReactionTriggerSignature,
    StateReactionProfile,
    StellarReactionDamageImpactEffect,
    StellarSwirlVortexStatePlanningIntent,
    TransformativeSourceObservation,
)

SOURCE = ElementalSourceRef("character:slot_1", "root:stellar-swirl")
SOURCE_B = ElementalSourceRef("character:slot_2", "root:stellar-swirl-b")
# 参与者集合按角色身份（source_key）规范化，不携带触发实例 instance_id。
CANONICAL_SOURCE = ElementalSourceRef("character:slot_1")
CANONICAL_SOURCE_B = ElementalSourceRef("character:slot_2")
CHARACTER_SOURCES = (SOURCE, SOURCE_B)
TARGET = ElementalSubjectRef.target("target:star")


def _apply_cryo_aura(source: ElementalSourceRef = SOURCE) -> AuraRuntime:
    runtime = AuraRuntime()
    runtime.apply(
        AuraApplicationRequest(
            f"aura:cryo:{source.source_key}",
            f"aura:cryo:{source.source_key}:application",
            "impact:aura:cryo",
            0,
            0,
            source,
            TARGET,
            Element.CRYO,
            AuraStrength.WEAK,
        )
    )
    return runtime


def _cryo_view_with_contributions(
    contributors: tuple[ElementalSourceRef, ...],
) -> AuraView:
    contributions = tuple(
        AuraContribution(
            AuraContributionRef(f"contrib:{index}"),
            contributor,
            AuraAmount("4/5"),
            contributor,
            0,
            0,
            0,
        )
        for index, contributor in enumerate(contributors)
    )
    component = AuraComponent(
        instance_ref=AuraInstanceRef("aura:cryo:view"),
        aura_kind=AuraKind.CRYO,
        contributions=contributions,
        decay_strength=AuraStrength.WEAK,
        decay_origin=contributors[0],
        created_frame=0,
        last_applied_frame=0,
        last_changed_frame=0,
    )
    return AuraView(subject_ref=TARGET, components=(component,))


def _observation() -> TransformativeSourceObservation:
    return TransformativeSourceObservation(
        source_ref=SOURCE,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=0.0,
        level_multiplier_table_key="transformative.level_multipliers",
        level_multiplier=1.0,
        source_observation_ref="obs:character:slot_1",
        source_owner_slot=1,
    )


def _request(
    observed_aura: AuraView,
    *,
    incoming: Element = Element.ANEMO,
    capability: bool = True,
) -> ReactionEvaluationRequest:
    return ReactionEvaluationRequest(
        "interaction:stellar-swirl",
        "impact:stellar-swirl",
        7,
        0,
        SOURCE,
        TARGET,
        incoming,
        AuraAmount.one(),
        observed_aura,
        transformative_source_observation=_observation(),
        character_source_refs=CHARACTER_SOURCES,
        reaction_capability_keys=(
            frozenset({STELLAR_SWIRL_CAPABILITY_KEY}) if capability else frozenset()
        ),
    )


def test_stellar_swirl_rule_declares_vortex_plan_and_wind_damage() -> None:
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(_request(_apply_cryo_aura().view(TARGET)))
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == STELLAR_SWIRL_REACTION_KEY
    assert result.occurrence.direction_key == "stellar_incoming_anemo_on_cryo"
    intent = result.occurrence.stellar_swirl_vortex_state_planning
    assert intent is not None
    assert intent.scope_ref == STELLAR_SWIRL_VORTEX_SCOPE
    assert intent.created_frame == 7
    assert intent.expires_at_frame == 7 + 180
    assert intent.reaction_participants == (CANONICAL_SOURCE,)
    assert intent.instance_ref.value == (
        "reaction-state:stellar-swirl-vortex:interaction:stellar-swirl:occurrence:0"
    )
    spatial = result.occurrence.spatial_entity_creation
    assert spatial is not None
    assert spatial.owner_key == STELLAR_SWIRL_VORTEX_SCOPE
    assert spatial.source_key == intent.instance_ref.value
    transition = result.occurrence.transition
    assert transition.aura_kind is AuraKind.CRYO
    # 消费与普通扩散一致：incoming 按上限匹配，aura 侧减半。
    assert transition.incoming_consumed == AuraAmount.one()
    assert transition.aura_consumed == AuraAmount("1/2")
    assert transition.aura_remaining == AuraAmount("3/10")
    # 星扩散·风单体即时伤害：CurrentSubjectSelection、去重 Gate、可暴击。
    assert len(result.occurrence.effect_groups) == 1
    group = result.occurrence.effect_groups[0]
    assert isinstance(group.target_selection, CurrentSubjectSelection)
    assert len(group.effects) == 1
    effect = group.effects[0]
    assert isinstance(effect, StellarReactionDamageImpactEffect)
    assert effect.main_attack_tag == STELLAR_SWIRL_WIND_DAMAGE_TAG
    assert effect.damage_element is Element.ANEMO
    assert effect.stellar_base_multiplier == pytest.approx(0.75)
    assert effect.trigger_source_ref == SOURCE
    assert effect.participant_refs == (CANONICAL_SOURCE,)
    assert effect.can_crit is True
    assert effect.gate_definition_key == STELLAR_SWIRL_WIND_GATE_DEFINITION_KEY
    assert effect.attached_aura_element is None


def test_stellar_swirl_participants_merge_trigger_and_cryo_contributors() -> None:
    view = _cryo_view_with_contributions((SOURCE_B, SOURCE))
    request = _request(view)

    assert stellar_swirl_wind_participants(request) == (CANONICAL_SOURCE, CANONICAL_SOURCE_B)
    intent = create_default_reaction_bootstrap().create_runtime().evaluate(request).occurrence
    assert intent is not None
    planning = intent.stellar_swirl_vortex_state_planning
    assert planning is not None
    assert planning.reaction_participants == (CANONICAL_SOURCE, CANONICAL_SOURCE_B)


def test_stellar_swirl_falls_back_to_swirl_without_capability() -> None:
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(_request(_apply_cryo_aura().view(TARGET), capability=False))
    )

    assert result.occurrence is not None
    assert result.occurrence.reaction_key == "reaction.swirl"
    assert result.occurrence.stellar_swirl_vortex_state_planning is None


def test_stellar_swirl_requires_anemo_incoming() -> None:
    result = (
        create_default_reaction_bootstrap()
        .create_runtime()
        .evaluate(_request(_apply_cryo_aura().view(TARGET), incoming=Element.CRYO))
    )

    assert result.occurrence is None


def test_stellar_swirl_definition_registers_single_direction_with_priority() -> None:
    definition = stellar_swirl_definition()
    assert definition.selection_priority == 110
    assert len(definition.trigger_signatures) == 1
    signature = definition.trigger_signatures[0]
    assert signature.direction_key == "stellar_incoming_anemo_on_cryo"
    assert isinstance(definition.profile_for(signature.direction_key), StateReactionProfile)
    # 反向方向仅预留 key，不注册触发签名。
    assert STELLAR_SWIRL_INCOMING_CRYO_ON_ANEMO not in {
        item.direction_key for item in definition.trigger_signatures
    }


def test_stellar_swirl_rule_rejects_non_state_profile() -> None:
    request = _request(_cryo_view_with_contributions((SOURCE,)))
    broken = ReactionDefinition(
        STELLAR_SWIRL_REACTION_KEY,
        "reaction_handler.stellar_swirl",
        (ReactionTriggerSignature(Element.ANEMO, AuraKind.CRYO, "stellar_incoming_anemo_on_cryo"),),
        (
            AmplifyingReactionProfile(
                "reaction_profile.stellar_swirl.incoming_anemo_on_cryo",
                STELLAR_SWIRL_REACTION_KEY,
                "stellar_incoming_anemo_on_cryo",
                Element.ANEMO,
                1.0,
            ),
        ),
        StellarSwirlRule(),
        selection_priority=110,
    )

    with pytest.raises(ValueError, match="ReactionStateProfile"):
        broken.rule.evaluate(request, broken)


def test_stellar_swirl_intent_rejects_participants_without_trigger() -> None:
    with pytest.raises(ValueError, match="触发者"):
        StellarSwirlVortexStatePlanningIntent(
            intent_ref="occurrence:1:stellar-swirl-vortex-plan",
            parent_occurrence_ref="occurrence:1",
            instance_ref=ReactionStateInstanceRef(
                "reaction-state:stellar-swirl-vortex:occurrence:1"
            ),
            subject_ref=TARGET,
            space_entity_ref="reaction_object:stellar_swirl_vortex:occurrence:1",
            trigger_source_ref=SOURCE,
            scope_ref=STELLAR_SWIRL_VORTEX_SCOPE,
            created_frame=0,
            expires_at_frame=180,
            reaction_participants=(SOURCE_B,),
        )
