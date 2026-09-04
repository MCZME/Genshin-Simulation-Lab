"""元素附魔 Damage 结算帧接入的核心层闭环测试。

归类说明：本用例验证 core 内 Damage Impact 分发、Infusion 适配与伤害结算的
跨模块闭环并断言最终数值，但只手动组合核心对象，不经过资产/装配层；
按测试规范 §2 的纵向数值闭环定位。若后续接入资产装配闭环，
应迁移到 tests/integration/ 而不是在本文件继续扩展。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_PHYSICAL,
    BONUS_DAMAGE_PYRO,
    RESISTANCE_PHYSICAL,
    RESISTANCE_PYRO,
    STAT_ATK_BASE,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
    ImpactRequestDispatcher,
)
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import (
    DamageProfile,
    DamageProfileRegistry,
    DamageRequestHandler,
    DamageResolver,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.infusion import (
    InfusionDamageElementAdapter,
    InfusionDefinitionRegistry,
    InfusionImpactRequestHandler,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
)

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.target("target:target_1")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.config")


def test_infusion_damage_integration_changes_element_and_recovers_physical():
    infusion_runtime = _infusion_runtime()
    adapter = InfusionDamageElementAdapter(infusion_runtime)
    handler = InfusionImpactRequestHandler(infusion_runtime)
    damage_handler = DamageRequestHandler(
        DamageResolver(_attribute_resolver()),
        profile_registry=DamageProfileRegistry(
            (
                DamageProfile(
                    FORMULA_KEY_GENERAL,
                    frozenset({"普通攻击1", "元素战技"}),
                ),
            )
        ),
    )
    dispatcher = ImpactRequestDispatcher(
        damage_handler=damage_handler,
        infusion_handler=handler,
        infusion_element_adapter=adapter,
    )
    context = _context()

    dispatcher.dispatch_requests(context, (_damage_request(0, "impact:physical"),))
    physical = damage_handler.records[-1]
    assert physical.result.element is Element.PHYSICAL
    assert physical.result.final_damage == pytest.approx(675.0)
    assert dispatcher.infusion_element_resolutions[-1].applied is False

    dispatcher.dispatch_requests(
        context,
        (
            ImpactRequest(
                frame=1,
                kind=ImpactKind.APPLY_INFUSION,
                impact_key="impact.melee.skill",
                owner_slot=1,
                request_id="impact:skill:1",
                source_impact_point_id="impact-point:skill",
                target_refs=("character:slot_1",),
                params={"infusion": {"definition_key": "infusion.test.pyro"}},
            ),
            _damage_request(1, "impact:infused"),
        ),
    )
    infused = damage_handler.records[-1]
    assert infused.result.element is Element.PYRO
    assert infused.result.final_damage == pytest.approx(540.0)
    assert infused.impact_request.damage_spec is not None
    assert infused.impact_request.damage_spec.elemental_strength is AuraStrength.WEAK
    assert infused.impact_request.damage_spec.elemental_amount == AuraAmount(1)
    assert infused.impact_request.damage_spec.icd_tag_key == "普攻"
    assert infused.impact_request.damage_spec.icd_sequence_key == "默认"
    assert dispatcher.infusion_element_resolutions[-1].applied is True
    assert len(dispatcher.infusion_records) == 1

    dispatcher.dispatch_requests(
        context,
        (
            ImpactRequest(
                frame=1,
                kind=ImpactKind.DAMAGE,
                impact_key="impact.melee.skill",
                owner_slot=1,
                request_id="impact:skill-hit",
                target_refs=("target_1",),
                damage_spec=DamageImpactSpec(
                    impact_ref="impact:skill-hit",
                    main_attack_tag="元素战技",
                    element=Element.PHYSICAL,
                    scaling_terms=(DamageScalingTerm("atk", STAT_ATK_BASE, 1.0),),
                    can_crit=False,
                ),
            ),
        ),
    )
    skill_hit = damage_handler.records[-1]
    assert skill_hit.result.element is Element.PHYSICAL

    infusion_runtime.update_frame(None, 3)
    dispatcher.dispatch_requests(context, (_damage_request(3, "impact:expired"),))
    expired = damage_handler.records[-1]
    assert expired.result.element is Element.PHYSICAL
    assert expired.result.final_damage == pytest.approx(675.0)
    assert dispatcher.infusion_element_resolutions[-1].applied is False


def _attribute_resolver() -> AttributeResolver:
    contributions = (
        (SOURCE, BaseAttributeContribution(STAT_ATK_BASE, 1000.0, CONFIG_SOURCE)),
        (SOURCE, BaseAttributeContribution(BONUS_DAMAGE_PHYSICAL, 0.5, CONFIG_SOURCE)),
        (SOURCE, BaseAttributeContribution(BONUS_DAMAGE_PYRO, 0.2, CONFIG_SOURCE)),
        (TARGET_REF, BaseAttributeContribution(RESISTANCE_PHYSICAL, 0.1, CONFIG_SOURCE)),
        (TARGET_REF, BaseAttributeContribution(RESISTANCE_PYRO, 0.1, CONFIG_SOURCE)),
    )
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(contributions),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _infusion_runtime() -> InfusionRuntime:
    definition = InfusionDefinitionRegistry((_pyro_definition(),)).get("infusion.test.pyro")
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry((definition,)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )


def _pyro_definition():
    from tests.helpers.infusion import make_definition

    return make_definition(
        definition_key="infusion.test.pyro",
        element=Element.PYRO,
        duration_frames=2,
        applicable_attack_tags=frozenset({"普通攻击1"}),
    )


def _context() -> SimulationContext:
    context = SimulationContext()
    context.space_runtime = SpaceRuntime(
        team_state=TeamRuntimeState(
            (CharacterRuntimeState(slot=1, character_key="character:test", level=90),)
        ),
        targets=TargetRuntimeCollection((TargetRuntimeState(target_id="target_1", level=90),)),
    )
    return context


def _damage_request(frame: int, request_id: str) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="impact.melee.normal",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=f"{request_id}:damage",
            main_attack_tag="普通攻击1",
            element=Element.PHYSICAL,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_BASE, 1.0),),
            can_crit=False,
            icd_tag_key="普攻",
            icd_sequence_key="默认",
        ),
    )
