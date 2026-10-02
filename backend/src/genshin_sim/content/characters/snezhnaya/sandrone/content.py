"""桑多涅内容单元编译入口。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.snezhnaya.sandrone.actions import (
    SandroneActionInterpreter,
    create_sandrone_actions,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_POWER_RISE_PER_SECOND,
    FAGEOU_RAY_HIT_POWER_GAIN,
    FAGEOU_RAY_INDEX_FACT_KEY,
    SANDRONE_C6_UNLOCK_KEY,
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
    SANDRONE_P4_PRISM_BOOST_FACT_KEY,
    SANDRONE_P4_TACTICS_STACKS_FACT_KEY,
    SANDRONE_SWEEP_ICD_RESET_FRAMES,
    SANDRONE_SWEEP_ICD_SEQUENCE_KEY,
    SandroneP4AssetValues,
    sandrone_tactics_definition_key,
)
from genshin_sim.content.characters.snezhnaya.sandrone.effects import (
    SandroneC6AssetValues,
    read_c1_power_rate_reduction,
    read_c6_asset_values,
    read_p4_asset_values,
)
from genshin_sim.content.characters.snezhnaya.sandrone.fageou import (
    SandroneFageouHook,
    sandrone_state_schema,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneParticleHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.impacts import (
    SandroneActionImpactFactory,
    compile_c6_extra_normal_spec,
    compile_charged_attack_damage_specs,
    compile_elemental_burst_damage_specs,
    compile_elemental_skill_damage_specs,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    compile_c6_extra_stellar_channel,
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
    """桑多涅内容单元工厂（动作状态机 + 普攻/战技/爆发/下落契约）。

    命座等级在编译期已知：C1（功率提升减速）、C2（射线暴伤序号标签）、
    C6（集束型追加段与星烁擢升）按 ``request.constellation`` 直接
    折算进角色单元的机器参数与星烁通道；效果行单元（effects.py）只承载
    各自可独立成单元的切片。
    """

    constellation = request.constellation
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
    c6_unlocked = constellation >= 6
    c6_values: SandroneC6AssetValues | None = None
    if c6_unlocked:
        c6_params = request.effect_params.get(SANDRONE_C6_UNLOCK_KEY)
        if c6_params is None:
            raise ContentUnitValidationError(f"C6 已解锁但缺少资产效果行：{SANDRONE_C6_UNLOCK_KEY}")
        c6_values = read_c6_asset_values(c6_params)
    # C1：解算功率提升速度按资产行折算。功率自然上升与射线命中增量同属
    # 「功率提升」，二者按同一系数折算（0 命 20/s 与 +12/条，1 命 10/s 与
    # +6/条）。
    if constellation >= 1:
        c1_params = request.effect_params.get("c1")
        if c1_params is None:
            raise ContentUnitValidationError("C1 已解锁但缺少资产效果行：c1")
        power_rate_factor = 1.0 - read_c1_power_rate_reduction(c1_params)
    else:
        power_rate_factor = 1.0
    # P4 悠久的演算机关：突破 1 阶（20 级突破）解锁；行为随角色单元编译，
    # 锁定时排空不计层、棱晶弹不强化、爆发不结算光束加成。机器数值一律取自
    # 资产效果行（装配期经 request.effect_params 交给角色单元），内容代码不留
    # 第二份常量；已解锁却缺少该效果行时直接失败，不静默回落。
    p4_unlocked = request.ascension_phase >= 1
    p4_values: SandroneP4AssetValues | None = None
    if p4_unlocked:
        # P4 行在 effect_params 中按资产行的 unlock_key（"passive:4"）索引。
        p4_params = request.effect_params.get("passive:4")
        if p4_params is None:
            raise ContentUnitValidationError("P4 已解锁但缺少资产效果行：passive:4")
        p4_values = read_p4_asset_values(p4_params)
    if request.effect_params.get("passive:6") is None:
        raise ContentUnitValidationError("缺少 P6 资产效果行：passive:6")
    stellar_channels = compile_stellar_attack_channels(
        request.character_key,
        entries_by_key,
        {
            "normal_attack": talent_level,
            "elemental_skill": skill_talent_level,
            "elemental_burst": burst_talent_level,
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
    # 法洁欧 hook 发射射线时把会话序号绑定为请求级事实（key 见 data.py），
    # 随射线请求走结算，供 C2 伤害修饰读取。P4 已解锁时，hook 以改进战术
    # Buff 定义键申请叠层、解释器消费 Buff 派生光束倍率（键见 data.py）。
    tactics_definition_key = (
        sandrone_tactics_definition_key(request.slot) if p4_values is not None else None
    )
    fageou_hook = SandroneFageouHook(
        owner_ref=owner_ref,
        slot=request.slot,
        damage_specs=charged_specs,
        stellar_channel=stellar_channels[SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY],
        # C1：解算功率提升速度按资产行折算，功率上升与射线命中增量一并折算；
        # 其余机器参数直接用 hook 的同批默认值（data.py 帧表）。
        power_rise_per_second=FAGEOU_POWER_RISE_PER_SECOND * power_rate_factor,
        ray_hit_power_gain=FAGEOU_RAY_HIT_POWER_GAIN * power_rate_factor,
        p4=p4_values,
        tactics_definition_key=tactics_definition_key,
        c6_extra_normal_spec=(
            compile_c6_extra_normal_spec(c6_values.normal_ratio) if c6_values is not None else None
        ),
        c6_extra_stellar_channel=(
            compile_c6_extra_stellar_channel(
                talent_level,
                conduct_ratio=c6_values.conduct_ratio,
                swirl_ratio=c6_values.swirl_ratio,
            )
            if c6_values is not None
            else None
        ),
        c6_extra_segments=(c6_values.extra_segment_count if c6_values is not None else 0),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=SANDRONE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=SandroneActionInterpreter(
            p4=p4_values,
            tactics_definition_key=tactics_definition_key,
        ),
        actions=create_sandrone_actions(
            cooldown_duration_terms=cooldown_terms_by_ability,
        ),
        state_schema=sandrone_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in SANDRONE_HIT_IMPACT_KEYS},
        event_hooks=(
            fageou_hook,
            SandroneParticleHook(owner_ref=owner_ref, slot=request.slot),
        ),
        damage_request_fact_keys=(
            FAGEOU_RAY_INDEX_FACT_KEY,
            SANDRONE_P4_PRISM_BOOST_FACT_KEY,
            SANDRONE_P4_TACTICS_STACKS_FACT_KEY,
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
        # 声明，无解锁过滤，assembly 静态端口零改动。
        # 星扩散 capability：桑多涅在队伍即可触发星扩散反应（风命中冰排他
        # 替代普通扩散），辉映·星扩散 Buff 以其资格证据为发放目标；星扩散
        # 变体行为见命中判定资料。
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
