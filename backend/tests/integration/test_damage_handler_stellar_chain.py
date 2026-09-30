"""星烁直伤经 Impact 请求到伤害结果的纵向链路。

锁定的是跨模块装配闭环而非数值正确性：Impact 侧声明倍率与星烁输入后，
``DamageRequestHandler`` 通过 profile 映射选中星烁公式，走属性解析与修饰收集，
最终把扁平结果与审计载荷一起交回。合成输入、错误时机与装配接线属于本层；
公式自身的分支与边界由 ``tests/unit`` 下的星烁公式用例承担。
"""

from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageProfile,
    DamageProfileRegistry,
    DamageRequestHandler,
    DamageResolver,
    DamageScalingTerm,
    FixedCriticalDecisionProvider,
    StellarReactionDamageInput,
    create_default_damage_formula_registry,
)
from tests.helpers import damage

SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar")


def test_damage_handler_resolves_stellar_reactions_mapping() -> None:
    """Impact 侧声明倍率后，星烁直伤可以完整走到扁平结果与审计载荷。"""

    attribute_resolver = damage.make_attribute_resolver(
        (damage.SOURCE,),
        target=damage.TARGET,
        source_context=SOURCE_CONTEXT,
        elemental_mastery=200.0,
        base_hp=damage.BASE_HP,
        electro_resistance=0.0,
    )
    profile_registry = DamageProfileRegistry(
        (DamageProfile(FORMULA_KEY_STELLAR_REACTION, frozenset({"星超导雷"})),)
    )
    handler = DamageRequestHandler(
        DamageResolver(
            attribute_resolver=attribute_resolver,
            formula_registry=create_default_damage_formula_registry(
                critical_decision_provider=FixedCriticalDecisionProvider()
            ),
        ),
        profile_registry=profile_registry,
    )
    target = TargetRuntimeState("star", level=90, spatial_entity_id="target:star")
    context = SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        "target:star",
                        SpatialEntityKind.TARGET,
                        Vector3(0.0, 0.0, 0.0),
                    ),
                )
            ),
            team_state=TeamRuntimeState(
                (
                    CharacterRuntimeState(
                        1, "character:test", 90, combat_entity_id="character:slot_1"
                    ),
                )
            ),
            targets=TargetRuntimeCollection((target,)),
        )
    )
    request = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="action.stellar_direct",
        owner_slot=1,
        request_id="root:stellar-direct:1",
        target_refs=("star",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:stellar-direct:1",
            main_attack_tag="星超导雷",
            element=Element.ELECTRO,
            scaling_terms=(DamageScalingTerm(damage.DIRECT_COMPONENT_KEY, STAT_HP_MAX, 1.0),),
        ),
    )

    results = handler.handle_impact_request(
        context,
        request,
        stellar_reactions={
            "star": StellarReactionDamageInput(
                mode="character_direct",
                stellar_base_multiplier=1.45,
            )
        },
    )

    assert len(results) == 1
    result = results[0]
    assert result.formula_key == FORMULA_KEY_STELLAR_REACTION
    assert result.stellar_reaction_resolution is not None
    mastery_bonus = 6 * 200 / 2200
    expected = damage.BASE_HP * 1.0 * 1.45 * (1 + mastery_bonus)
    assert result.stellar_reaction_resolution.official_damage == pytest.approx(expected)
    assert result.final_damage == pytest.approx(expected)
    payload = result.to_dict()
    stellar_payload = cast(dict[str, object], payload["stellar_reaction"])
    assert stellar_payload is not None
    assert stellar_payload["mode"] == "character_direct"

    audit = result.to_audit_dict()
    reaction_audit = cast(dict[str, object], audit["reaction"])
    assert reaction_audit["kind"] == "stellar"
    assert reaction_audit["elemental_mastery"] == pytest.approx(200.0)
    assert reaction_audit["mastery_bonus"] == pytest.approx(mastery_bonus)
    assert reaction_audit["stellar_base_multiplier"] == pytest.approx(1.45)
    assert reaction_audit["crit_outcome"] == "non_critical"
    assert reaction_audit["crit_multiplier"] == pytest.approx(1.0)
    assert reaction_audit["resistance_multiplier"] is not None
    assert reaction_audit["official_damage"] == pytest.approx(expected)
    assert reaction_audit["final_damage"] == pytest.approx(expected)
    assert isinstance(audit["critical"], dict)
    assert isinstance(audit["resistance"], dict)
