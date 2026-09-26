"""桑多涅星烁通道单元：辉映属性证据 → 星烁输入组装 → 星变体契约分派。

对齐星超导反应契约 §8 的"辉映 Buff 属性证据 -> ``StellarReactionDamageInput``
组装 -> 伤害请求"链路（星超导反应设计 §7 当前测试驱动方式）：辉映·星烁/
辉映·星扩散 Buff 经真实 BuffRuntime 与属性 provider 投影为角色属性证据，
``resolve_stellar_attack_spec`` 按证据分派星超导/星扩散分支并组装
``mode=character_direct`` 的星烁输入。数值全部为合成数据（见测试规范 §3.2）。
"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly.reaction_capabilities import (
    build_static_reaction_eligibility_port,
)
from genshin_sim.content.characters.snezhnaya.sandrone.content import (
    create_sandrone_content_unit,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    compile_stellar_attack_channels,
    resolve_stellar_attack_spec,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import index_talent_scalings
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    plan_radiance_buff_requests,
    stellar_radiance_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    plan_stellar_swirl_radiance_buff_requests,
    stellar_swirl_radiance_buff_definition,
)
from genshin_sim.core.elements import Element, ElementalSubjectRef
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import DamageImpactSpec
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.systems.buff import (
    BuffAttributeModifierProvider,
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_CAPABILITY_KEY,
)
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
)
from tests.helpers import sandrone as sandrone_helpers

OWNER_REF = "character:slot_1"
OWNER_SUBJECT = AttributeSubjectRef.character(OWNER_REF)
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sandrone.stellar")
FRAME = 120


def _normal_specs() -> dict[str, DamageImpactSpec]:
    """三路星烁通道各自的普通契约替身（仅为星扩散占位倍率提供分量）。"""

    def _spec(impact_key: str, coefficient: float) -> DamageImpactSpec:
        return DamageImpactSpec(
            impact_ref=f"{impact_key}:1",
            main_attack_tag="重击",
            element=Element.CRYO,
            scaling_terms=(DamageScalingTerm(impact_key, STAT_ATK_TOTAL, coefficient),),
        )

    return {
        SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY: _spec(SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY, 0.7),
        SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY: _spec(
            SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY, 0.5
        ),
        SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY: _spec(
            SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY, 0.6
        ),
    }


def _channel() -> object:
    entries = index_talent_scalings(
        sandrone_helpers.SANDRONE_CHARACTER_KEY,
        sandrone_helpers._minimal_sandrone_scaling_entries(),
    )
    channels = compile_stellar_attack_channels(
        sandrone_helpers.SANDRONE_CHARACTER_KEY,
        entries,
        {"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
        normal_specs=_normal_specs(),
    )
    return channels[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY]


def _context_with_radiance(
    *,
    conduct_stacks: int | None = None,
    swirl: bool = False,
) -> SimulationContext:
    buff_runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry(
            (stellar_radiance_buff_definition(), stellar_swirl_radiance_buff_definition())
        ),
        resolver=BuffResolver(),
        buff_store=BuffStore(),
        event_engine=EventEngine(),
    )
    if conduct_stacks is not None:
        buff_runtime.commit_prevalidated(
            buff_runtime.prepare_apply(
                plan_radiance_buff_requests(
                    frame=0,
                    occurrence_ref="unit:conduct",
                    character_refs=(OWNER_SUBJECT,),
                    settled_stacks=conduct_stacks,
                    field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
                )
            )
        )
    if swirl:
        buff_runtime.commit_prevalidated(
            buff_runtime.prepare_apply(
                plan_stellar_swirl_radiance_buff_requests(
                    frame=0,
                    occurrence_ref="unit:swirl",
                    character_refs=(OWNER_SUBJECT,),
                )
            )
        )
    registry = create_public_attribute_registry()
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((OWNER_SUBJECT, BaseAttributeContribution(STAT_ATK_BASE, 300.0, SOURCE_CONTEXT)),)
        ),
        modifier_index=ModifierProviderIndex(
            (
                BuffAttributeModifierProvider(
                    stellar_radiance_buff_definition(), buff_runtime.reader
                ),
                BuffAttributeModifierProvider(
                    stellar_swirl_radiance_buff_definition(), buff_runtime.reader
                ),
            ),
            registry=registry,
        ),
    )
    context = SimulationContext()
    context.register_system(resolver)
    return context


def test_without_radiance_evidence_channel_falls_back_to_normal() -> None:
    spec = resolve_stellar_attack_spec(
        _channel(),  # type: ignore[arg-type]
        simulation=_context_with_radiance(),
        owner_ref=OWNER_REF,
        frame=FRAME,
    )
    assert spec is None


def test_conduct_radiance_assembles_character_direct_stellar_input() -> None:
    context = _context_with_radiance(conduct_stacks=3)
    spec = resolve_stellar_attack_spec(
        _channel(),  # type: ignore[arg-type]
        simulation=context,
        owner_ref=OWNER_REF,
        frame=FRAME,
    )
    assert spec is not None
    assert spec.main_attack_tag == "星超导冰"
    assert spec.scaling_terms == ()
    assert spec.stellar_reaction is not None
    assert spec.stellar_reaction.mode == "character_direct"
    # 直伤倍率 = 攻击力 × 星超导倍率分量（合成星超导条目值 1.0），星烁基础
    # 系数取辉映 Buff 投影的层数快照（3 层 → 1.4 + 0.05×3）。
    assert spec.stellar_reaction.scaling_value == pytest.approx(300.0)
    assert spec.stellar_reaction.stellar_base_multiplier == pytest.approx(1.55)


def test_swirl_radiance_uses_swirl_branch_with_placeholder_ratio() -> None:
    context = _context_with_radiance(swirl=True)
    spec = resolve_stellar_attack_spec(
        _channel(),  # type: ignore[arg-type]
        simulation=context,
        owner_ref=OWNER_REF,
        frame=FRAME,
    )
    assert spec is not None
    assert spec.main_attack_tag == "星扩散冰"
    assert spec.stellar_reaction is not None
    assert spec.stellar_reaction.mode == "character_direct"
    # 星扩散系数证据固定 1.0；倍率分量以普通变体倍率占位（0.7，来源待补）。
    assert spec.stellar_reaction.stellar_base_multiplier == pytest.approx(1.0)
    assert spec.stellar_reaction.scaling_value == pytest.approx(300.0 * 0.7)


def test_conduct_radiance_takes_priority_over_swirl() -> None:
    context = _context_with_radiance(conduct_stacks=3, swirl=True)
    spec = resolve_stellar_attack_spec(
        _channel(),  # type: ignore[arg-type]
        simulation=context,
        owner_ref=OWNER_REF,
        frame=FRAME,
    )
    assert spec is not None
    assert spec.main_attack_tag == "星超导冰"
    assert spec.stellar_reaction is not None
    assert spec.stellar_reaction.stellar_base_multiplier == pytest.approx(1.55)


def test_compile_rejects_missing_stellar_scaling_entry() -> None:
    entries = index_talent_scalings(
        sandrone_helpers.SANDRONE_CHARACTER_KEY,
        sandrone_helpers._minimal_sandrone_scaling_entries(),
    )
    entries.pop(("character:10000133", "normal_attack", "重击冷凝射线星超导伤害"))
    with pytest.raises(ContentUnitValidationError, match="重击冷凝射线星超导伤害"):
        compile_stellar_attack_channels(
            sandrone_helpers.SANDRONE_CHARACTER_KEY,
            entries,
            {"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
            normal_specs=_normal_specs(),
        )


def test_content_unit_declares_both_stellar_capabilities() -> None:
    """桑多涅随内容单元静态声明星超导与星扩散 capability（维护者确认口径）。

    星扩散 capability 使队伍风命中冰排他替代普通扩散，且辉映·星扩散 Buff
    以 capability 提供者为发放目标——桑多涅因此持有辉映·星扩散状态。
    """

    unit = create_sandrone_content_unit(
        CharacterContentUnitRequest(
            handler_key=sandrone_helpers.SANDRONE_CHARACTER_HANDLER_KEY,
            character_key=sandrone_helpers.SANDRONE_CHARACTER_KEY,
            slot=1,
            talent_levels={"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
            talent_scalings=sandrone_helpers._minimal_sandrone_scaling_entries(),
        )
    )
    assert unit.reaction_capabilities == (
        STELLAR_CONDUCT_CAPABILITY_KEY,
        STELLAR_SWIRL_CAPABILITY_KEY,
    )
    port = build_static_reaction_eligibility_port((unit,))
    provider = ElementalSubjectRef.character("character:slot_1")
    for capability_key in (STELLAR_CONDUCT_CAPABILITY_KEY, STELLAR_SWIRL_CAPABILITY_KEY):
        assert port.evidence_for(frame=0, team_ref="team:assembly").providers_for(
            capability_key
        ) == (provider,)
