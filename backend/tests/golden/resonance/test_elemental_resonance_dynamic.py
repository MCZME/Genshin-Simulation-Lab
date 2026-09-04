"""元素共鸣动态效果 golden 基线。

验证能力：四系附着时长修正（-40%）、双风冷却 -5%、双雷 5 秒微粒冷却、
双草反应触发全队精通 Buff（+30/+20，独立 6 秒）。
资料来源及适用版本：原神 BWIKI《队伍加成》页（2026-07-02 更新，覆盖月之八
版本；双草 6.0 适配月绽放已包含；双雷触发清单不含星超导）。
旧项目参考：`resonance_system.py` 的冷却、掉球与精通行为线索。
完整输入条件：见各用例内联数据。
预期输出与允许误差：帧数与精确元素量精确匹配。
不覆盖的行为：双风体力/移速、双雷触发清单中的星超导。
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import cast

from genshin_sim.content.team.resonance import (
    DENDRO_EM_20_TRIGGER_KEYS,
    DENDRO_EM_30_TRIGGER_KEYS,
    ELECTRO_PARTICLE_TRIGGER_KEYS,
    RESONANCE_DENDRO_EM_20_BUFF_KEY,
    RESONANCE_DENDRO_EM_30_BUFF_KEY,
    RESONANCE_GEO_RES_SHRED_BUFF_KEY,
    create_resonance_definitions,
)
from genshin_sim.core.contracts.intents import IntentKind
from genshin_sim.core.coordination.resonance_reaction import ResonanceReactionStage
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.impacts import ImpactRequest
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.aura.profiles import (
    apply_aura_duration_terms,
    profile_for,
)
from genshin_sim.core.systems.buff.models import ApplyBuffRequest
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationResolver,
    CooldownKey,
    CooldownSubjectRef,
)
from genshin_sim.core.systems.damage import DamageModifierStage
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceAuraDurationTermProvider,
    ResonanceCooldownDurationTermProvider,
    ResonanceCryoCritDamageProvider,
    ResonanceGeoDamageProvider,
    ResonanceRuntime,
    ResonanceStore,
    TeamElementComposition,
)
from tests.helpers.events import (
    make_damage_resolved_event,
    make_event_context,
    make_reaction_occurrence_event,
)
from tests.helpers.resonance_ports import (
    FakeAuraFrozenPort,
    FakeLunarCagePresencePort,
    FakeShieldPresencePort,
    make_damage_modifier_query,
)


def test_pyro_resonance_reduces_cryo_aura_duration_to_342_frames():
    definitions = create_resonance_definitions()
    provider = ResonanceAuraDurationTermProvider(
        ResonanceActivation(("resonance.pyro",)),
        definitions,
    )
    terms = provider.duration_terms_for(
        ElementalSubjectRef.character("character:slot_1"),
        AuraKind.CRYO,
    )
    scaled = apply_aura_duration_terms(profile_for(AuraStrength.WEAK), terms)

    assert scaled.decay_for_frames(342) == AuraAmount(Fraction(4, 5))
    assert scaled.decay_for_frames(341) < AuraAmount(Fraction(4, 5))


def test_anemo_resonance_reduces_skill_cooldown_to_95_percent():
    definitions = create_resonance_definitions()
    provider = ResonanceCooldownDurationTermProvider(
        ResonanceActivation(("resonance.anemo",)),
        definitions,
    )
    key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_skill",
    )
    definition = CooldownDefinition(
        key=key,
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=100,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref="golden.resonance",
    )

    resolution = CooldownDurationResolver().resolve(
        definition,
        None,
        provider.terms_for(key),
    )

    assert resolution.resolved_duration_frames == 95
    assert resolution.stage_totals[-1][1] == Decimal("95")


def test_electro_resonance_drops_one_particle_per_300_frames():
    stage, queue = _stage(("resonance.electro",))
    stage.update_frame(
        make_event_context(
            10, (make_reaction_occurrence_event(10, "reaction.electro_charged", "occ:1"),)
        ),
        10,
    )
    stage.update_frame(
        make_event_context(
            10, (make_reaction_occurrence_event(10, "reaction.electro_charged", "occ:2"),)
        ),
        10,
    )
    stage.update_frame(
        make_event_context(
            310, (make_reaction_occurrence_event(310, "reaction.electro_charged", "occ:3"),)
        ),
        310,
    )

    intents = queue.drain_sorted()
    assert len(intents) == 2
    assert all(intent.kind is IntentKind.IMPACT for intent in intents)
    assert all(
        cast(dict, cast(ImpactRequest, intent.payload).params["energy"])["operation"]
        == "spawn_pickup"
        and cast(dict, cast(ImpactRequest, intent.payload).params["energy"])["element"] == "electro"
        for intent in intents
    )


def test_dendro_resonance_em_buffs_use_30_and_20_independent_definitions():
    stage, queue = _stage(("resonance.dendro",))
    stage.update_frame(
        make_event_context(
            20,
            (
                make_reaction_occurrence_event(20, "reaction.bloom", "occ:bloom"),
                make_reaction_occurrence_event(20, "reaction.aggravate", "occ:aggravate"),
            ),
        ),
        20,
    )

    intents = queue.drain_sorted()
    assert len(intents) == 8
    requests = [cast(ApplyBuffRequest, intent.payload) for intent in intents]
    em_30 = [
        request for request in requests if request.definition_key == RESONANCE_DENDRO_EM_30_BUFF_KEY
    ]
    em_20 = [
        request for request in requests if request.definition_key == RESONANCE_DENDRO_EM_20_BUFF_KEY
    ]
    assert len(em_30) == 4
    assert len(em_20) == 4
    assert all(
        request.modifier_values[0].value == 30.0 and request.duration_frames == 360
        for request in em_30
    )
    assert all(
        request.modifier_values[0].value == 20.0 and request.duration_frames == 360
        for request in em_20
    )


def test_geo_resonance_res_shred_uses_15s_geo_res_reduction():
    stage, queue = _stage(("resonance.geo",), shield_present=True)
    stage.update_frame(make_event_context(60, (make_damage_resolved_event(60, "dmg:golden"),)), 60)

    intents = queue.drain_sorted()
    assert len(intents) == 1
    request = cast(ApplyBuffRequest, intents[0].payload)
    assert request.definition_key == RESONANCE_GEO_RES_SHRED_BUFF_KEY
    assert request.duration_frames == 900
    assert request.modifier_values[0].term_key == "resistance_geo"
    assert request.modifier_values[0].value == -0.2


def test_cryo_and_geo_resonance_damage_modifier_values():
    cryo = ResonanceCryoCritDamageProvider(active=True)
    cryo.bind_runtime_ports(aura_frozen_port=FakeAuraFrozenPort(True))
    cryo_terms = cryo.contribute(make_damage_modifier_query(), None)
    assert len(cryo_terms) == 1
    assert cryo_terms[0].stage is DamageModifierStage.CRIT_RATE_ADD
    assert cryo_terms[0].value == 0.15

    geo = ResonanceGeoDamageProvider(active=True)
    geo.bind_runtime_ports(
        shield_port=FakeShieldPresencePort(True),
        lunar_cage_port=FakeLunarCagePresencePort(False),
    )
    geo_terms = geo.contribute(make_damage_modifier_query(), None)
    assert len(geo_terms) == 1
    assert geo_terms[0].stage is DamageModifierStage.DAMAGE_BONUS_ADD
    assert geo_terms[0].value == 0.15


def _stage(
    active_keys: tuple[str, ...],
    *,
    shield_present: bool = False,
    lunar_cage_present: bool = False,
):
    queue = IntentQueue()
    store = ResonanceStore(
        ResonanceActivation(active_keys),
        TeamElementComposition.from_counts(4, {}),
    )
    runtime = ResonanceRuntime(store, EventEngine())
    stage = ResonanceReactionStage(
        resonance_runtime=runtime,
        intent_queue=queue,
        team_slots=(1, 2, 3, 4),
        electro_particle_triggers=ELECTRO_PARTICLE_TRIGGER_KEYS,
        dendro_em_30_triggers=DENDRO_EM_30_TRIGGER_KEYS,
        dendro_em_20_triggers=DENDRO_EM_20_TRIGGER_KEYS,
        dendro_em_30_definition_key=RESONANCE_DENDRO_EM_30_BUFF_KEY,
        dendro_em_20_definition_key=RESONANCE_DENDRO_EM_20_BUFF_KEY,
        geo_res_shred_definition_key=RESONANCE_GEO_RES_SHRED_BUFF_KEY,
        shield_presence_port=FakeShieldPresencePort(shield_present),
        lunar_cage_presence_port=FakeLunarCagePresencePort(lunar_cage_present),
    )
    return stage, queue
