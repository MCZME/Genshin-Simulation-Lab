"""阿罗夏内容单元编译入口。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.alyosha.actions import (
    AlyoshaActionInterpreter,
    create_alyosha_actions,
)
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_BURST_ICD_RESET_FRAMES,
    ALYOSHA_BURST_ICD_SEQUENCE_KEY,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_CONTENT_VERSION,
    ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    ALYOSHA_HIT_IMPACT_KEYS,
    FRAMES_PER_SECOND,
)
from genshin_sim.content.characters.snezhnaya.alyosha.impacts import (
    AlyoshaActionImpactFactory,
    compile_elemental_skill_damage_specs,
    compile_normal_attack_damage_specs,
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


def create_alyosha_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """阿罗夏内容单元工厂（动作状态机 + 普攻/E 点按契约 + Q 施放）。

    骨架阶段（``dev-skeleton``）：普攻四段（N3 双判定）与 E 点按直伤经标准
    影响管线接入；Q 只承载施放动作与能量消耗，轰霆猎场/图加林创建实体与
    印记/猎者之准等机制随 §7-4 核心机制切片接入。Q 的专属 ICD 序列
    「阿罗夏元素爆发」为资料完整数据，随单元一并声明。
    """

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
    impact_factory = AlyoshaActionImpactFactory(damage_specs)
    owner_ref = f"character:slot_{request.slot}"
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
            )
        },
        cooldown_definitions=(skill_cooldown_definition, burst_cooldown_definition),
        # Q 专属 ICD 序列「阿罗夏元素爆发」（资料：重置 1.6s、序列 [1,0]、每窗口
        # 首下附着）；轰霆猎场与图加林共享该组，伤害随创建实体接入后按 defender
        # 分窗共用同一实例。
        aura_icd_definitions=(
            IcdDefinition(
                sequence_key=ALYOSHA_BURST_ICD_SEQUENCE_KEY,
                reset_interval_frames=ALYOSHA_BURST_ICD_RESET_FRAMES,
                application_sequence=(AuraAmount.one(), AuraAmount.zero()),
            ),
        ),
        metadata={"purpose": "alyosha_content_skeleton"},
    )


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
