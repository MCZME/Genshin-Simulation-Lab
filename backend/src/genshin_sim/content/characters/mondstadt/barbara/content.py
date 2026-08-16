"""芭芭拉内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，构造冷却/ICD 定义与持续效果行为，最后组装 ``ContentUnit``。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.mondstadt.barbara.actions import (
    BarbaraActionInterpreter,
    create_barbara_actions,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_CONTENT_VERSION,
    BARBARA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    BARBARA_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_HIT_IMPACT_KEYS,
    BARBARA_RING_OBJECT_KEY,
    BARBARA_RING_WET_ICD_APPLICATION_SEQUENCE,
    BARBARA_RING_WET_ICD_RESET_INTERVAL_FRAMES,
    BARBARA_RING_WET_ICD_SEQUENCE_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.hooks import (
    BarbaraRingOnHitHealHook,
)
from genshin_sim.content.characters.mondstadt.barbara.impacts import (
    BarbaraActionImpactFactory,
    compile_burst_heal_payload,
    compile_charged_attack_damage_spec,
    compile_elemental_skill_damage_spec,
    compile_normal_attack_damage_specs,
    compile_on_hit_heal_payload,
    compile_plunge_damage_specs,
    compile_ring_create_params,
    compile_ring_heal_payload,
    compile_ring_wet_spec,
    compile_self_wet_spec,
)
from genshin_sim.content.characters.mondstadt.barbara.ring import (
    BarbaraRingHealBehavior,
    BarbaraRingWetBehavior,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.generic.talents import (
    TalentLevelResolver,
    index_talent_scalings,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.aura_icd import IcdDefinition
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationTerm,
    CooldownKey,
    CooldownSubjectRef,
)


def create_barbara_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """新模型内容单元工厂（芭芭拉动作状态机 + 普攻/重击/战技/爆发契约）。"""

    talent_levels = {
        key: request.talent_levels.get(key, 1)
        for key in ("normal_attack", "elemental_skill", "elemental_burst")
    }
    resolved = TalentLevelResolver.resolve(
        talent_levels,
        request.talent_boosts,
    )
    talent_level = resolved.levels["normal_attack"]
    skill_talent_level = resolved.levels["elemental_skill"]
    burst_talent_level = resolved.levels["elemental_burst"]
    entries_by_key = index_talent_scalings(
        request.character_key,
        request.talent_scalings,
    )
    damage_specs = compile_normal_attack_damage_specs(
        request.character_key,
        entries_by_key,
        talent_level,
    )
    damage_specs[BARBARA_CHARGED_ATTACK_IMPACT_KEY] = compile_charged_attack_damage_spec(
        request.character_key,
        entries_by_key,
        talent_level,
    )
    damage_specs.update(
        compile_plunge_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    damage_specs[BARBARA_ELEMENTAL_SKILL_IMPACT_KEY] = compile_elemental_skill_damage_spec(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    ring_heal_payload = compile_ring_heal_payload(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    on_hit_heal_payload = compile_on_hit_heal_payload(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    burst_heal_payload = compile_burst_heal_payload(
        request.character_key,
        entries_by_key,
        burst_talent_level,
    )
    self_wet_spec = compile_self_wet_spec()
    ring_wet_spec = compile_ring_wet_spec()
    ring_create_params = compile_ring_create_params(request.slot)
    impact_factory = BarbaraActionImpactFactory(
        damage_specs,
        self_wet_spec=self_wet_spec,
        ring_create_params=ring_create_params,
        burst_heal_payload=burst_heal_payload,
    )
    owner_ref = f"character:slot_{request.slot}"
    cooldown_terms_by_ability = _cooldown_terms_for_actions(request)
    cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=BARBARA_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=BARBARA_CHARACTER_HANDLER_KEY,
        tags=("elemental_skill",),
    )
    burst_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            BARBARA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_BURST,
        base_duration_frames=BARBARA_ELEMENTAL_BURST_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=BARBARA_CHARACTER_HANDLER_KEY,
        tags=("elemental_burst",),
    )
    ring_icd_definition = IcdDefinition(
        BARBARA_RING_WET_ICD_SEQUENCE_KEY,
        BARBARA_RING_WET_ICD_RESET_INTERVAL_FRAMES,
        tuple(AuraAmount(value) for value in BARBARA_RING_WET_ICD_APPLICATION_SEQUENCE),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=BARBARA_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=BarbaraActionInterpreter(),
        actions=create_barbara_actions(
            cooldown_duration_terms=cooldown_terms_by_ability,
        ),
        state_schema=chain_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in BARBARA_HIT_IMPACT_KEYS},
        created_object_behaviors={
            f"{BARBARA_RING_OBJECT_KEY}.heal": BarbaraRingHealBehavior(ring_heal_payload),
            f"{BARBARA_RING_OBJECT_KEY}.wet": BarbaraRingWetBehavior(ring_wet_spec),
        },
        event_hooks=(
            BarbaraRingOnHitHealHook(
                owner_ref=owner_ref,
                slot=request.slot,
                heal_payload=on_hit_heal_payload,
            ),
        ),
        cooldown_definitions=(cooldown_definition, burst_cooldown_definition),
        aura_icd_definitions=(ring_icd_definition,),
        metadata={"purpose": "barbara_action_state_machine"},
    )


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。"""

    owner_ref = f"character:slot_{request.slot}"
    supported = {
        BARBARA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        BARBARA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    }
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"芭芭拉冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        if key.ability_key not in supported:
            raise ContentUnitValidationError(f"芭芭拉不支持冷却能力键：{key.ability_key}")
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
