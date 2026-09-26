"""桑多涅内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，构造冷却定义、自定义 ICD 与法洁欧状态机 hook，最后组装
``ContentUnit``。普攻/战技/爆发/下落/重击伤害、冷却与解算模式为已接入
范围；星超导直伤通道、产球、命座与被动随后续切片接入。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.snezhnaya.sandrone.actions import (
    SandroneActionInterpreter,
    create_sandrone_actions,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_BULLET_SPEED_M_PER_S,
    FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
    FAGEOU_POWER_DECAY_PER_SECOND,
    FAGEOU_POWER_MAX,
    FAGEOU_POWER_RISE_PER_SECOND,
    FAGEOU_PRE_SWING_FRAMES,
    FAGEOU_RAY_FIRST_OFFSET_FRAMES,
    FAGEOU_RAY_HIT_POWER_GAIN,
    FAGEOU_RAY_INTERVAL_FRAMES,
    FAGEOU_RAY_LENGTH,
    FAGEOU_RAY_WIDTH,
    FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    SANDRONE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SANDRONE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SANDRONE_HIT_IMPACT_KEYS,
    SANDRONE_SWEEP_ICD_RESET_FRAMES,
    SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.fageou import (
    SandroneFageouHook,
    sandrone_state_schema,
)
from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
    SandroneActionImpactFactory,
    compile_charged_attack_damage_specs,
    compile_elemental_burst_damage_specs,
    compile_elemental_skill_damage_specs,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
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


def create_sandrone_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """桑多涅内容单元工厂（动作状态机 + 普攻/战技/爆发/下落契约）。"""

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
    damage_specs.update(
        compile_elemental_skill_damage_specs(
            request.character_key,
            entries_by_key,
            skill_talent_level,
        )
    )
    damage_specs.update(
        compile_elemental_burst_damage_specs(
            request.character_key,
            entries_by_key,
            burst_talent_level,
        )
    )
    damage_specs.update(
        compile_plunge_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    charged_specs = compile_charged_attack_damage_specs(
        request.character_key,
        entries_by_key,
        talent_level,
    )
    impact_factory = SandroneActionImpactFactory(damage_specs)
    owner_ref = f"character:slot_{request.slot}"
    cooldown_terms_by_ability = _cooldown_terms_for_actions(request)
    skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=SANDRONE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
        tags=("elemental_skill",),
    )
    burst_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_BURST,
        base_duration_frames=SANDRONE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
        tags=("elemental_burst",),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=SANDRONE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=SandroneActionInterpreter(),
        actions=create_sandrone_actions(
            cooldown_duration_terms=cooldown_terms_by_ability,
        ),
        state_schema=sandrone_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in SANDRONE_HIT_IMPACT_KEYS},
        event_hooks=(
            SandroneFageouHook(
                owner_ref=owner_ref,
                slot=request.slot,
                damage_specs=charged_specs,
                pre_swing_frames=FAGEOU_PRE_SWING_FRAMES,
                solve_shot_interval_frames=FAGEOU_SOLVE_SHOT_INTERVAL_FRAMES,
                overload_shot_interval_frames=FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
                ray_first_offset_frames=FAGEOU_RAY_FIRST_OFFSET_FRAMES,
                ray_interval_frames=FAGEOU_RAY_INTERVAL_FRAMES,
                power_rise_per_second=FAGEOU_POWER_RISE_PER_SECOND,
                ray_hit_power_gain=FAGEOU_RAY_HIT_POWER_GAIN,
                power_decay_per_second=FAGEOU_POWER_DECAY_PER_SECOND,
                power_max=FAGEOU_POWER_MAX,
                ray_length=FAGEOU_RAY_LENGTH,
                ray_width=FAGEOU_RAY_WIDTH,
                bullet_speed_m_per_s=FAGEOU_BULLET_SPEED_M_PER_S,
            ),
        ),
        cooldown_definitions=(skill_cooldown_definition, burst_cooldown_definition),
        aura_icd_definitions=(
            IcdDefinition(
                sequence_key=SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
                reset_interval_frames=SANDRONE_SWEEP_ICD_RESET_FRAMES,
                application_sequence=(AuraAmount.one(), AuraAmount.zero()),
            ),
        ),
        metadata={"purpose": "sandrone_content_skeleton"},
    )


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。"""

    owner_ref = f"character:slot_{request.slot}"
    supported = {
        SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    }
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"桑多涅冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        if key.ability_key not in supported:
            raise ContentUnitValidationError(f"桑多涅不支持冷却能力键：{key.ability_key}")
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
