from __future__ import annotations

from dataclasses import replace

import pytest

from genshin_sim.core.attributes import (
    STAT_DEF_TOTAL,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.simulation import TeamRuntimeState
from genshin_sim.core.systems.shield import (
    ShieldCapacityError,
    ShieldCapacityFormula,
    ShieldGrantPolicy,
    ShieldNativeMultiplierTerm,
    ShieldResolver,
    ShieldRuntime,
    ShieldScalingTerm,
    ShieldStore,
)


class MutableHpPercentProvider:
    def __init__(self, subject_ref: AttributeSubjectRef) -> None:
        self.subject_ref = subject_ref
        self.value = 0.0
        self.provider_spec = ModifierProviderSpec(
            provider_key="test.mutable_hp",
            writes=frozenset({STAT_HP_MAX}),
            owner_ref=subject_ref,
        )

    def contribute(self, query, session):
        del session
        if query.subject_ref != self.subject_ref or query.attribute_key != STAT_HP_MAX:
            return ()
        return (
            ModifierTerm(
                target_key=STAT_HP_MAX,
                stage=ModifierStage.PERCENT_ADD,
                value=self.value,
                provider_key=self.provider_spec.provider_key,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.mutable_hp"),
            ),
        )


def test_resolver_calculates_components_native_multipliers_and_capacity_limit(
    shield_rig,
    make_grant,
):
    request = make_grant(
        grant_policy=ShieldGrantPolicy.ADD_CAPPED_REFRESH,
        capacity_limit=1,
    )
    request = replace(
        request,
        grant_formula=ShieldCapacityFormula(
            scaling_terms=(
                ShieldScalingTerm("hp", STAT_HP_MAX, 0.1),
                ShieldScalingTerm("def", STAT_DEF_TOTAL, 0.2),
            ),
            flat_absorption=100,
            native_multipliers=(
                ShieldNativeMultiplierTerm(
                    "z_mode",
                    2.0,
                    request.source_context,
                ),
                ShieldNativeMultiplierTerm(
                    "a_constellation",
                    0.5,
                    request.source_context,
                ),
            ),
        ),
        capacity_limit_formula=ShieldCapacityFormula(
            scaling_terms=(ShieldScalingTerm("hp_cap", STAT_HP_MAX, 0.5),),
        ),
    )

    result = shield_rig.runtime.resolver.resolve(request)

    assert [item.component_key for item in result.component_results] == ["def", "hp"]
    assert result.granted_absorption == pytest.approx(1_300)
    assert [item.multiplier_key for item in result.native_multiplier_results] == [
        "a_constellation",
        "z_mode",
    ]
    assert result.capacity_limit == pytest.approx(5_000)
    assert len(result.attribute_trace) == 3
    assert result.to_dict()["granted_absorption"] == pytest.approx(1_300)


@pytest.mark.parametrize("flat_absorption", [0.0, -0.0])
def test_resolver_rejects_non_positive_formula_result(
    shield_rig,
    make_grant,
    flat_absorption,
):
    request = make_grant(flat_absorption=flat_absorption)

    with pytest.raises(ShieldCapacityError):
        shield_rig.runtime.resolver.resolve(request)


def test_creator_attribute_changes_do_not_retroactively_change_existing_native_capacity(
    make_grant,
):
    character_ref = AttributeSubjectRef.character("character:slot_1")
    source = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.base")
    registry = create_public_attribute_registry()
    provider = MutableHpPercentProvider(character_ref)
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    character_ref,
                    BaseAttributeContribution(STAT_HP_BASE, 1_000, source),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )
    from genshin_sim.core.entity_states import CharacterRuntimeState, HealthState

    character = CharacterRuntimeState(1, "character:test", 90, health=HealthState(1_000))
    team_state = TeamRuntimeState((character,))
    events = EventEngine()
    shield_store = ShieldStore()
    resolver = ShieldResolver(attribute_resolver)
    runtime = ShieldRuntime(
        resolver=resolver,
        shield_store=shield_store,
        attribute_resolver=attribute_resolver,
        event_engine=events,
        team_state=team_state,
    )
    request = replace(
        make_grant(flat_absorption=1),
        grant_formula=ShieldCapacityFormula(
            scaling_terms=(ShieldScalingTerm("hp", STAT_HP_MAX, 1.0),),
        ),
    )

    grant = runtime.grant(request)
    provider.value = 1.0
    later_resolution = resolver.resolve(replace(request, grant_id="grant:later", frame=2))

    assert grant.resolution.granted_absorption == 1_000
    assert later_resolution.granted_absorption == 2_000
    assert shield_store.require(grant.instance_ref).state.remaining_native_absorption == 1_000
