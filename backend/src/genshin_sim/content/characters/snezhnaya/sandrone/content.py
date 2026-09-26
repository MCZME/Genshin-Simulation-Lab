"""桑多涅内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，构造冷却定义、自定义 ICD 与法洁欧状态机 hook，最后组装
``ContentUnit``。普攻/战技/爆发/下落/重击伤害、冷却、解算模式与辉映星烁
直伤通道为已接入范围；产球、命座与被动随后续切片接入。
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
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_CONTENT_VERSION,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    SANDRONE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    SANDRONE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SANDRONE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
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
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    compile_stellar_attack_channels,
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
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CAPABILITY_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_CAPABILITY_KEY,
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
    stellar_channels = compile_stellar_attack_channels(
        request.character_key,
        entries_by_key,
        {
            "normal_attack": talent_level,
            "elemental_skill": skill_talent_level,
            "elemental_burst": burst_talent_level,
        },
        normal_specs={
            SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY: charged_specs[
                SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY
            ],
            SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY: damage_specs[
                SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY
            ],
            SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY: damage_specs[
                SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY
            ],
        },
    )
    impact_factory = SandroneActionImpactFactory(
        damage_specs,
        stellar_channels={
            SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY: stellar_channels[
                SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY
            ],
            SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY: stellar_channels[
                SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY
            ],
        },
    )
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
                stellar_channel=stellar_channels[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY],
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
        # 星耀祝礼·唯理为光（passive:6）是固定天赋：capability 随内容单元静态
        # 声明，无解锁过滤（规划讨论待定项 4；assembly 静态端口零改动）。
        # 星扩散 capability 由维护者确认（2026-09-26）：桑多涅在队伍即可触发
        # 星扩散反应（风命中冰排他替代普通扩散），辉映·星扩散 Buff 以其资格
        # 证据为发放目标；命中判定数据 3.4 星扩散变体行为佐证。
        reaction_capabilities=(
            STELLAR_CONDUCT_CAPABILITY_KEY,
            STELLAR_SWIRL_CAPABILITY_KEY,
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
