"""砂糖内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，最后组装 ``ContentUnit``。S1 覆盖普攻四段、重击与下落攻击；S2
追加元素战技（单次范围风伤、15s 冷却、战技命中产 4 风微粒），并声明冷却
定义与产球钩子；S3 追加元素爆发（大型风灵创建物、持续风伤、染色伤害、
20s 冷却、能量花费）；S7 在单元 metadata 上声明魔导资格标记（装配期收集为
魔导名录，供「魔女的前夜礼」判定激活）。
"""

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
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
    SUCROSE_HIT_IMPACT_KEYS,
    SUCROSE_SPIRIT_OBJECT_KEY,
    SUCROSE_STATE_LAST_PARTICLE_FRAME,
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
from genshin_sim.content.characters.mondstadt.sucrose.spirit import SucroseSpiritType
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
from genshin_sim.content.team.witches_eve import MAGE_MARKER_KEY
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
    impact_factory = SucroseActionImpactFactory(damage_specs)
    owner_ref = f"character:slot_{request.slot}"
    skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
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
            # 魔导资格：完成「魔女的课业·仙境花之题」后砂糖成为魔导角色。本期
            # 裁定默认已完成、不作为仿真输入项，故标记为角色的静态属性；
            # 装配期收集为魔导名录（content/team/witches_eve.py）。
            MAGE_MARKER_KEY: True,
        },
    )


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。

    S2 / S3 各有一条冷却能力（元素战技、元素爆发）；未登记的冷却能力键在此
    直接失败，避免静默丢弃。
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
