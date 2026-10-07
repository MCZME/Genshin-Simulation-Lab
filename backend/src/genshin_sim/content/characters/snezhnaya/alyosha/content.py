"""阿罗夏内容单元编译入口。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.alyosha.actions import (
    AlyoshaActionInterpreter,
    create_alyosha_actions,
)
from genshin_sim.content.characters.snezhnaya.alyosha.buffs import (
    build_hunters_mark_definition,
    build_hunters_precision_definition,
    build_hunters_precision_mastery_definition,
)
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY,
    ALYOSHA_BURST_ICD_RESET_FRAMES,
    ALYOSHA_BURST_ICD_SEQUENCE_KEY,
    ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY,
    ALYOSHA_C4_HEAL_COMPONENT_KEY,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_CONTENT_VERSION,
    ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    ALYOSHA_FIELD_FIRST_TICK_FRAME_OFFSET,
    ALYOSHA_FULGURITE_OBJECT_KEY,
    ALYOSHA_HIT_IMPACT_KEYS,
    ALYOSHA_P4_HEAL_COMPONENT_KEY,
    ALYOSHA_TUGARIN_FIRST_BITE_FRAME_OFFSET,
    FRAMES_PER_SECOND,
)
from genshin_sim.content.characters.snezhnaya.alyosha.effects import (
    read_c2_extension_seconds,
    read_c4_heal_ratio,
    read_c6_asset_values,
    read_p4_heal_ratio,
)
from genshin_sim.content.characters.snezhnaya.alyosha.fulgurite import (
    AlyoshaFulguriteFieldType,
    FulguriteHealChannel,
)
from genshin_sim.content.characters.snezhnaya.alyosha.hooks import (
    AlyoshaMarkApplicationHook,
    AlyoshaParticleHook,
    AlyoshaPrecisionGrantHook,
)
from genshin_sim.content.characters.snezhnaya.alyosha.impacts import (
    AlyoshaActionImpactFactory,
    AlyoshaBurstSummonPlan,
    compile_burst_damage_specs,
    compile_charged_attack_damage_specs,
    compile_elemental_skill_damage_specs,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.chain_state import chain_state_schema
from genshin_sim.content.generic.talents import (
    ScalingCompiler,
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

_TALENT_KEYS = ("normal_attack", "elemental_skill", "elemental_burst")

# 猎者之准机制相关资产倍率条目标签（E 天赋区）。
_MARK_DURATION_LABEL = "弋猎印记持续时间"
_PRECISION_ATK_LABEL = "猎者之准攻击力提升"
_PRECISION_DURATION_LABEL = "猎者之准持续时间"
# Q 场域持续时间的资产倍率条目标签（Q 天赋区）。
_FIELD_DURATION_LABEL = "持续时间"


def _cooldown_frames_from_entry(
    entries_by_key: Mapping[tuple[str, str, str], TalentScalingEntry],
    character_key: str,
    talent_key: str,
    talent_level: int,
    *,
    purpose: str,
) -> int:
    """从资产倍率表「冷却时间」条目编译冷却帧数（秒 × 60，四舍五入）。"""

    entry = entries_by_key.get((character_key, talent_key, "冷却时间"))
    if entry is None:
        raise ContentUnitValidationError(f"阿罗夏{purpose}缺少资产倍率条目：冷却时间")
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    seconds = compiled.components[0].value
    if seconds <= 0:
        raise ContentUnitValidationError(f"阿罗夏{purpose}冷却时间必须为正数秒")
    return round(seconds * FRAMES_PER_SECOND)


def _talent_value(
    entries_by_key: Mapping[tuple[str, str, str], TalentScalingEntry],
    character_key: str,
    talent_key: str,
    label: str,
    talent_level: int,
    *,
    purpose: str,
    component_index: int = 0,
) -> float:
    """从资产倍率条目取指定分量的编译值（等级越界或分量缺失在组装期报错）。"""

    entry = entries_by_key.get((character_key, talent_key, label))
    if entry is None:
        raise ContentUnitValidationError(f"阿罗夏{purpose}缺少资产倍率条目：{label}")
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    if len(compiled.components) <= component_index:
        raise ContentUnitValidationError(f"阿罗夏{purpose}倍率条目缺少分量：{label}")
    return compiled.components[component_index].value


def _required_effect_params(
    request: CharacterContentUnitRequest,
    unlock_key: str,
) -> Mapping[str, object]:
    """取角色名下指定 unlock_key 的资产效果行参数，缺失即组装期报错。"""

    params = request.effect_params.get(unlock_key)
    if params is None:
        raise ContentUnitValidationError(f"阿罗夏已解锁但缺少资产效果行：{unlock_key}")
    return params


def create_alyosha_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """阿罗夏内容单元工厂（动作状态机 + 全量命中契约 + Q 创建实体 + 印记链）。"""

    talent_levels = {key: request.talent_levels.get(key, 1) for key in _TALENT_KEYS}
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
        compile_charged_attack_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    # 下落攻击取普攻天赋等级（游戏内下落倍率挂在普攻天赋区）。
    damage_specs.update(
        compile_plunge_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    damage_specs.update(
        compile_burst_damage_specs(
            request.character_key,
            entries_by_key,
            burst_talent_level,
        )
    )
    owner_ref = f"character:slot_{request.slot}"
    constellation = request.constellation

    # ------------------------------------------------------------------
    # 印记与猎者之准数值（资产倍率条目）与 Q 场域时长。
    # ------------------------------------------------------------------
    mark_duration_frames = _frames_from_seconds(
        _talent_value(
            entries_by_key,
            request.character_key,
            "elemental_skill",
            _MARK_DURATION_LABEL,
            skill_talent_level,
            purpose="元素战技",
        ),
        purpose="弋猎印记持续时间",
    )
    precision_atk_per_stack = _talent_value(
        entries_by_key,
        request.character_key,
        "elemental_skill",
        _PRECISION_ATK_LABEL,
        skill_talent_level,
        purpose="元素战技",
    )
    precision_duration_frames = _frames_from_seconds(
        _talent_value(
            entries_by_key,
            request.character_key,
            "elemental_skill",
            _PRECISION_DURATION_LABEL,
            skill_talent_level,
            purpose="元素战技",
        ),
        purpose="猎者之准持续时间",
    )
    field_duration_frames = _frames_from_seconds(
        _talent_value(
            entries_by_key,
            request.character_key,
            "elemental_burst",
            _FIELD_DURATION_LABEL,
            burst_talent_level,
            purpose="元素爆发",
        ),
        purpose="元素爆发持续时间",
    )

    # C2：Q 持续延长 + 图加林攻击前施加印记（不激活已有）。
    c2_apply_mark = False
    if constellation >= 2:
        c2_params = _required_effect_params(request, "c2")
        field_duration_frames += _frames_from_seconds(
            read_c2_extension_seconds(c2_params),
            purpose="C2 元素爆发延长",
        )
        c2_apply_mark = True

    # C6：猎者之准可叠 2 层，叠满伴生元素精通。
    precision_max_stacks = 1
    mastery_bonus: float | None = None
    if constellation >= 6:
        c6_params = _required_effect_params(request, "c6")
        c6_values = read_c6_asset_values(c6_params)
        precision_max_stacks = c6_values.max_stacks
        mastery_bonus = c6_values.mastery_bonus

    # P4/C4：与图加林攻击动作同步的周期回血通道（数值取资产效果行）。
    p4_heal: FulguriteHealChannel | None = None
    if request.ascension_phase >= 1:
        p4_params = _required_effect_params(request, "passive:4")
        p4_heal = FulguriteHealChannel(
            impact_key="alyosha.p4_heal",
            component_key=ALYOSHA_P4_HEAL_COMPONENT_KEY,
            atk_ratio=read_p4_heal_ratio(p4_params),
        )
    c4_heal: FulguriteHealChannel | None = None
    if constellation >= 4:
        c4_params = _required_effect_params(request, "c4")
        c4_heal = FulguriteHealChannel(
            impact_key="alyosha.c4_heal",
            component_key=ALYOSHA_C4_HEAL_COMPONENT_KEY,
            atk_ratio=read_c4_heal_ratio(c4_params),
        )

    # ------------------------------------------------------------------
    # Buff 定义、印记链 hook 与轰霆猎场创建实体类型。
    # ------------------------------------------------------------------
    buff_definitions = [
        build_hunters_mark_definition(),
        build_hunters_precision_definition(max_stacks=precision_max_stacks),
    ]
    if mastery_bonus is not None:
        buff_definitions.append(build_hunters_precision_mastery_definition())
    mark_hook = AlyoshaMarkApplicationHook(
        owner_ref=owner_ref,
        slot=request.slot,
        mark_duration_frames=mark_duration_frames,
    )
    precision_hook = AlyoshaPrecisionGrantHook(
        owner_ref=owner_ref,
        atk_bonus_per_stack=precision_atk_per_stack,
        precision_duration_frames=precision_duration_frames,
        precision_max_stacks=precision_max_stacks,
        mastery_bonus=mastery_bonus,
    )
    particle_hook = AlyoshaParticleHook(owner_ref=owner_ref, slot=request.slot)
    fulgurite_type = AlyoshaFulguriteFieldType(
        slot=request.slot,
        field_spec=damage_specs[ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY],
        bite_spec=damage_specs[ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY],
        c2_apply_mark=c2_apply_mark,
        mark_duration_frames=mark_duration_frames,
        p4_heal=p4_heal,
        c4_heal=c4_heal,
    )
    summon_plan = AlyoshaBurstSummonPlan(
        type_key=ALYOSHA_FULGURITE_OBJECT_KEY,
        duration_frames=field_duration_frames,
        field_first_tick_frame_offset=ALYOSHA_FIELD_FIRST_TICK_FRAME_OFFSET,
        tugarin_first_bite_frame_offset=ALYOSHA_TUGARIN_FIRST_BITE_FRAME_OFFSET,
    )
    impact_factory = AlyoshaActionImpactFactory(damage_specs, burst_summon=summon_plan)
    skill_cooldown_frames = _cooldown_frames_from_entry(
        entries_by_key,
        request.character_key,
        "elemental_skill",
        skill_talent_level,
        purpose="元素战技",
    )
    burst_cooldown_frames = _cooldown_frames_from_entry(
        entries_by_key,
        request.character_key,
        "elemental_burst",
        burst_talent_level,
        purpose="元素爆发",
    )
    cooldown_terms_by_ability = _cooldown_terms_for_actions(request)
    skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=skill_cooldown_frames,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=ALYOSHA_CHARACTER_HANDLER_KEY,
        tags=("elemental_skill",),
    )
    burst_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_BURST,
        base_duration_frames=burst_cooldown_frames,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=ALYOSHA_CHARACTER_HANDLER_KEY,
        tags=("elemental_burst",),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=ALYOSHA_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=AlyoshaActionInterpreter(),
        actions=create_alyosha_actions(
            cooldown_duration_terms=cooldown_terms_by_ability,
        ),
        state_schema=chain_state_schema(owner_ref),
        impact_factories={
            impact_key: impact_factory
            for impact_key in (
                *ALYOSHA_HIT_IMPACT_KEYS,
                ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
                ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY,
            )
        },
        event_hooks=(mark_hook, precision_hook, particle_hook),
        buff_definitions=tuple(buff_definitions),
        created_object_types={ALYOSHA_FULGURITE_OBJECT_KEY: fulgurite_type},
        cooldown_definitions=(skill_cooldown_definition, burst_cooldown_definition),
        aura_icd_definitions=(
            IcdDefinition(
                sequence_key=ALYOSHA_BURST_ICD_SEQUENCE_KEY,
                reset_interval_frames=ALYOSHA_BURST_ICD_RESET_FRAMES,
                application_sequence=(AuraAmount.one(), AuraAmount.zero()),
            ),
        ),
        metadata={"purpose": "alyosha_content_package"},
    )


def _frames_from_seconds(seconds: float, *, purpose: str) -> int:
    if seconds <= 0:
        raise ContentUnitValidationError(f"阿罗夏{purpose}必须为正数秒")
    return round(seconds * FRAMES_PER_SECOND)


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。"""

    owner_ref = f"character:slot_{request.slot}"
    supported = {
        ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    }
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"阿罗夏冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        if key.ability_key not in supported:
            raise ContentUnitValidationError(f"阿罗夏不支持冷却能力键：{key.ability_key}")
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
