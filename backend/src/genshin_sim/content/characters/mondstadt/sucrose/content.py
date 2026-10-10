"""砂糖内容单元编译入口。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.mondstadt.sucrose.actions import (
    SucroseActionInterpreter,
    create_sucrose_actions,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    SUCROSE_ELEMENTAL_SKILL_BASE_CHARGES,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
    SUCROSE_HIT_IMPACT_KEYS,
    SUCROSE_SPIRIT_OBJECT_KEY,
    SUCROSE_STATE_LAST_PARTICLE_FRAME,
)
from genshin_sim.content.characters.mondstadt.sucrose.effects import (
    read_constellation_components,
)
from genshin_sim.content.characters.mondstadt.sucrose.hooks import SucroseParticleHook
from genshin_sim.content.characters.mondstadt.sucrose.impacts import (
    SucroseActionImpactFactory,
    compile_charged_attack_damage_spec,
    compile_elemental_skill_damage_spec,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
    compile_spirit_absorbed_damage_channel,
    compile_spirit_anemo_damage_spec,
)
from genshin_sim.content.characters.mondstadt.sucrose.spirit import (
    SucroseSpiritType,
    resolve_spirit_timing,
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
from genshin_sim.content.team.mage import MAGE_MARKER_KEY
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
from genshin_sim.core.systems.cooldown import (
    AbilityKind,
    CooldownDefinition,
    CooldownDurationMode,
    CooldownDurationTerm,
    CooldownKey,
    CooldownRecoveryMode,
    CooldownSubjectRef,
)


def sucrose_state_schema(owner_ref: str) -> StateSchema:
    """连段状态 + 产球审计的合并 schema。"""

    chain = chain_state_schema(owner_ref)
    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            *tuple(chain.fields),
            StateField(
                name=SUCROSE_STATE_LAST_PARTICLE_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
        ),
    )


def create_sucrose_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """新模型内容单元工厂（砂糖动作状态机 + 普攻/重击/战技/下落契约）。"""

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
    damage_specs[SUCROSE_CHARGED_ATTACK_IMPACT_KEY] = compile_charged_attack_damage_spec(
        request.character_key,
        entries_by_key,
        talent_level,
    )
    damage_specs[SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY] = compile_elemental_skill_damage_spec(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    damage_specs.update(
        compile_plunge_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    # C1 堆叠真空域：E 的可使用次数 +1（资产 c1 的 number_1）。充能数只能由
    # 冷却定义承载（内容侧没有「充能 term」这类动态通道），故按命座在编译期
    # 取值。
    extra_charges = _constellation_value(
        request,
        threshold=1,
        unlock_key="c1",
        purpose="C1 堆叠真空域",
    )
    skill_charges, skill_recovery_mode = _skill_charge_profile(extra_charges)
    # C2 不羁型贝特：爆发窗口延长 2 秒（资产 c2 的 number_1）；窗口 / 生命周期
    # / 拍数三者由 resolve_spirit_timing 同源派生，避免「窗口 8s 却只打 3 拍」。
    burst_extra_seconds = _constellation_value(
        request,
        threshold=2,
        unlock_key="c2",
        purpose="C2 不羁型贝特",
    )
    (
        _spirit_window_frames,
        spirit_duration_frames,
        spirit_tick_count,
    ) = resolve_spirit_timing(burst_extra_seconds)
    impact_factory = SucroseActionImpactFactory(
        damage_specs,
        spirit_duration_frames=spirit_duration_frames,
    )
    owner_ref = f"character:slot_{request.slot}"
    skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
        max_charges=skill_charges,
        duration_mode=CooldownDurationMode.FIXED,
        recovery_mode=skill_recovery_mode,
        source_ref=SUCROSE_CHARACTER_HANDLER_KEY,
        tags=("elemental_skill",),
    )
    burst_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_BURST,
        base_duration_frames=SUCROSE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=SUCROSE_CHARACTER_HANDLER_KEY,
        tags=("elemental_burst",),
    )
    # 大型风灵的伤害由创建物 tick 产出（不是动作影响点），故两个伤害契约直接
    # 交给创建实体类型持有，不进影响工厂的 damage_specs。
    spirit_type = SucroseSpiritType(
        slot=request.slot,
        anemo_spec=compile_spirit_anemo_damage_spec(
            request.character_key,
            entries_by_key,
            burst_talent_level,
        ),
        absorbed_channel=compile_spirit_absorbed_damage_channel(
            request.character_key,
            entries_by_key,
            burst_talent_level,
        ),
        duration_frames=spirit_duration_frames,
        tick_count=spirit_tick_count,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=SUCROSE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=SucroseActionInterpreter(),
        actions=create_sucrose_actions(
            cooldown_duration_terms=_cooldown_terms_for_actions(request),
        ),
        state_schema=sucrose_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in SUCROSE_HIT_IMPACT_KEYS},
        event_hooks=(SucroseParticleHook(owner_ref=owner_ref, slot=request.slot),),
        created_object_types={SUCROSE_SPIRIT_OBJECT_KEY: spirit_type},
        cooldown_definitions=(skill_cooldown_definition, burst_cooldown_definition),
        metadata={
            "purpose": "sucrose_action_state_machine",
            MAGE_MARKER_KEY: True,
        },
    )


def _constellation_value(
    request: CharacterContentUnitRequest,
    *,
    threshold: int,
    unlock_key: str,
    purpose: str,
) -> int:
    """按命座取该层的资产数值（未解锁时为 0；已解锁却缺效果行则直接失败）。

    C1 的充能数与 C2 的延长秒数都作用在**角色单元编译出的静态切片**上（冷却
    定义与创建物时长），没有动态通道可走，只能在这里按命座读资产行取值。
    """

    if request.constellation < threshold:
        return 0
    params = request.effect_params.get(unlock_key)
    if params is None:
        raise ContentUnitValidationError(f"{purpose} 已解锁但缺少资产效果行：{unlock_key}")
    values = read_constellation_components(params, purpose=purpose)
    value = round(values[0])
    if value <= 0:
        raise ContentUnitValidationError(f"{purpose} 资产数值必须为正数")
    return value


def _skill_charge_profile(
    extra_charges: int,
) -> tuple[int, CooldownRecoveryMode]:
    """E 的充能数与恢复模式：C1 的**成对**落点。

    充能数与恢复模式是并列的两个落点，在此成对给出，而不是让
    「恢复模式」由「充能数 > 1」推导出来——两者是独立维度，将来若出现只加
    充能而不改恢复模式（或反之）的来源，只需改这里，不会牵连。
    """

    if extra_charges:
        return (
            SUCROSE_ELEMENTAL_SKILL_BASE_CHARGES + extra_charges,
            CooldownRecoveryMode.INDEPENDENT,
        )
    return SUCROSE_ELEMENTAL_SKILL_BASE_CHARGES, CooldownRecoveryMode.SERIAL


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。

    元素战技与元素爆发各有一条冷却能力；未登记的冷却能力键在此直接失败，
    避免静默丢弃。
    """

    owner_ref = f"character:slot_{request.slot}"
    supported = {
        SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    }
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"砂糖冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        if key.ability_key not in supported:
            raise ContentUnitValidationError(f"砂糖不支持冷却能力键：{key.ability_key}")
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
