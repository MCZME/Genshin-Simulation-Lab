"""奥黛塔内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，构造冷却/ICD 定义，最后组装 ``ContentUnit``。星耀祝礼·银晓之舞
（P6）的星反应转换 capability 随内容单元静态声明；其基础增伤 provider 与
其余被动/命座行为在后续切片落地。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.snezhnaya.odette.actions import (
    OdetteActionInterpreter,
    create_odette_actions,
)
from genshin_sim.content.characters.snezhnaya.odette.dance import OdetteDanceHook
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CHARGED_ATTACK_IMPACT_KEY,
    ODETTE_CONTENT_VERSION,
    ODETTE_DANCE_DURATION_FRAMES,
    ODETTE_DANCE_STEP_PLUME,
    ODETTE_DANCE_STEP_WING,
    ODETTE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    ODETTE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
    ODETTE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    ODETTE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
    ODETTE_HIT_IMPACT_KEYS,
    ODETTE_SPECIAL_END_IMPACT_KEY,
    ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY,
    ODETTE_SPECIAL_SKILL_COOLDOWN_FRAMES,
    ODETTE_SPECIAL_SKILL_ICD_APPLICATION_SEQUENCE,
    ODETTE_SPECIAL_SKILL_ICD_RESET_FRAMES,
    ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY,
    ODETTE_SPLENDOR_ATK_TERM_KEY,
    ODETTE_STATE_LAST_PARTICLE_FRAME,
    ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME,
    ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME,
    ODETTE_STATE_SPLENDOR_TICK_PARITY,
    ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME,
    ODETTE_STATE_SUMMON_NEXT_STEP,
    odette_splendor_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.effects import (
    read_c1_splendor_values,
    read_c2_atk_per_stack,
    read_p4_splendor_values,
)
from genshin_sim.content.characters.snezhnaya.odette.hooks import OdetteParticleHook
from genshin_sim.content.characters.snezhnaya.odette.impacts import (
    OdetteActionImpactFactory,
    compile_charged_attack_damage_spec,
    compile_dance_damage_specs,
    compile_elemental_burst_damage_specs,
    compile_elemental_skill_damage_spec,
    compile_normal_attack_damage_specs,
    compile_plunge_damage_specs,
    compile_special_dot_damage_specs,
    compile_stellar_channels,
)
from genshin_sim.content.characters.snezhnaya.odette.splendor import (
    OdetteSplendorDecayHook,
    SplendorGrantConfig,
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
from genshin_sim.core.contracts.state_schema import (
    StateField,
    StateFieldType,
    StateSchema,
)
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


def odette_state_schema(owner_ref: str) -> StateSchema:
    """连段状态 + 特殊战技窗口锚点 + 独舞倒影轮换 + 产球审计的合并 schema。"""

    chain = chain_state_schema(owner_ref)
    return StateSchema(
        owner_ref=owner_ref,
        fields=(
            *tuple(chain.fields),
            StateField(
                name=ODETTE_STATE_SKILL_WINDOW_ANCHOR_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
            StateField(
                name=ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
            StateField(
                name=ODETTE_STATE_SUMMON_NEXT_STEP,
                field_type=StateFieldType.ENUM,
                default=ODETTE_DANCE_STEP_PLUME,
                allowed_values=(ODETTE_DANCE_STEP_PLUME, ODETTE_DANCE_STEP_WING),
            ),
            StateField(
                name=ODETTE_STATE_LAST_PARTICLE_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
            StateField(
                name=ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
            StateField(
                name=ODETTE_STATE_SPLENDOR_TICK_PARITY,
                field_type=StateFieldType.INT,
                default=0,
                non_negative=True,
            ),
        ),
    )


def create_odette_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """奥黛塔内容单元工厂（动作状态机 + 普攻/重击/战技/特殊战技/爆发契约）。"""

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
    damage_specs[ODETTE_CHARGED_ATTACK_IMPACT_KEY] = compile_charged_attack_damage_spec(
        request.character_key,
        entries_by_key,
        talent_level,
    )
    damage_specs[ODETTE_ELEMENTAL_SKILL_IMPACT_KEY] = compile_elemental_skill_damage_spec(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    damage_specs.update(
        compile_special_dot_damage_specs(
            request.character_key,
            entries_by_key,
            skill_talent_level,
        )
    )
    stellar_channels = compile_stellar_channels(
        request.character_key,
        entries_by_key,
        skill_talent_level,
    )
    dance_cryo_specs = compile_dance_damage_specs(
        request.character_key,
        entries_by_key,
        skill_talent_level,
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
    # P4 获选者的春祭（华彩）：突破 1 阶解锁；发放层数取 P4 行，C1 强化
    # （额外叠层 + 后台清除提速）与 C6 强化（转交不减层）按命座取值接入，
    # C2 攻击力词条值随发放/转交申请携带（Buff 定义由 P4 效果单元按命座
    # 门控编译，两侧必须一致）。已解锁却缺效果行时直接失败，不静默回落。
    owner_ref = f"character:slot_{request.slot}"
    splendor_grant_config: SplendorGrantConfig | None = None
    splendor_hook: OdetteSplendorDecayHook | None = None
    if request.ascension_phase >= 1:
        p4_params = request.effect_params.get("passive:4")
        if p4_params is None:
            raise ContentUnitValidationError("P4 已解锁但缺少资产效果行：passive:4")
        grant_stacks = read_p4_splendor_values(p4_params)
        layers_per_tick = 1
        keep_own_stacks = False
        if request.constellation >= 1:
            c1_params = request.effect_params.get("c1")
            if c1_params is None:
                raise ContentUnitValidationError("C1 已解锁但缺少资产效果行：c1")
            extra_stacks, layers_per_tick = read_c1_splendor_values(c1_params)
            grant_stacks += extra_stacks
        splendor_modifier_values: tuple[dict[str, object], ...] = ()
        if request.constellation >= 2:
            c2_params = request.effect_params.get("c2")
            if c2_params is None:
                raise ContentUnitValidationError("C2 已解锁但缺少资产效果行：c2")
            splendor_modifier_values = (
                {
                    "term_key": ODETTE_SPLENDOR_ATK_TERM_KEY,
                    "value": read_c2_atk_per_stack(c2_params),
                },
            )
        keep_own_stacks = request.constellation >= 6
        splendor_definition_key = odette_splendor_definition_key(request.slot)
        splendor_grant_config = SplendorGrantConfig(
            definition_key=splendor_definition_key,
            grant_stacks=grant_stacks,
            duration_frames=ODETTE_DANCE_DURATION_FRAMES,
            modifier_values=splendor_modifier_values,
        )
        splendor_hook = OdetteSplendorDecayHook(
            owner_ref=owner_ref,
            slot=request.slot,
            definition_key=splendor_definition_key,
            layers_per_tick=layers_per_tick,
            keep_own_stacks=keep_own_stacks,
            modifier_values=splendor_modifier_values,
        )
    impact_factory = OdetteActionImpactFactory(
        damage_specs,
        stellar_channels={
            ODETTE_SPECIAL_END_IMPACT_KEY: stellar_channels[ODETTE_SPECIAL_END_IMPACT_KEY],
        },
        splendor_grant=splendor_grant_config,
    )
    dance_hook = OdetteDanceHook(
        owner_ref=owner_ref,
        slot=request.slot,
        cryo_specs=dance_cryo_specs,
        stellar_channels={
            ODETTE_DANCE_STEP_PLUME: stellar_channels[ODETTE_DANCE_STEP_PLUME],
            ODETTE_DANCE_STEP_WING: stellar_channels[ODETTE_DANCE_STEP_WING],
        },
    )
    event_hooks: tuple = (dance_hook,)
    if splendor_hook is not None:
        event_hooks += (splendor_hook,)
    cooldown_terms_by_ability = _cooldown_terms_for_actions(request)
    skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            ODETTE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=ODETTE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=ODETTE_CHARACTER_HANDLER_KEY,
        tags=("elemental_skill",),
    )
    special_skill_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_SKILL,
        base_duration_frames=ODETTE_SPECIAL_SKILL_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=ODETTE_CHARACTER_HANDLER_KEY,
        tags=("special_elemental_skill",),
    )
    burst_cooldown_definition = CooldownDefinition(
        key=CooldownKey(
            CooldownSubjectRef.character(owner_ref),
            ODETTE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
        ),
        ability_kind=AbilityKind.ELEMENTAL_BURST,
        base_duration_frames=ODETTE_ELEMENTAL_BURST_COOLDOWN_FRAMES,
        max_charges=1,
        duration_mode=CooldownDurationMode.FIXED,
        source_ref=ODETTE_CHARACTER_HANDLER_KEY,
        tags=("elemental_burst",),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version=ODETTE_CONTENT_VERSION,
        slot=request.slot,
        action_interpreter=OdetteActionInterpreter(),
        actions=create_odette_actions(
            cooldown_duration_terms=cooldown_terms_by_ability,
        ),
        state_schema=odette_state_schema(owner_ref),
        impact_factories={
            # 爆发能量花费/召唤创建影响点由工厂的 ENERGY/CREATE 分支处理，
            # 与伤害影响点共用工厂。
            key: impact_factory
            for key in ODETTE_HIT_IMPACT_KEYS
        },
        event_hooks=(
            *event_hooks,
            OdetteParticleHook(owner_ref=owner_ref, slot=request.slot),
        ),
        cooldown_definitions=(
            skill_cooldown_definition,
            special_skill_cooldown_definition,
            burst_cooldown_definition,
        ),
        # 破晓终奏持续段的专属衰减序列（重置时限 3s、序列 1,0,0,0），由
        # DoT 三段命中消费。
        aura_icd_definitions=(
            IcdDefinition(
                sequence_key=ODETTE_SPECIAL_SKILL_ICD_SEQUENCE_KEY,
                reset_interval_frames=ODETTE_SPECIAL_SKILL_ICD_RESET_FRAMES,
                application_sequence=tuple(
                    AuraAmount(value) for value in ODETTE_SPECIAL_SKILL_ICD_APPLICATION_SEQUENCE
                ),
            ),
        ),
        # 星耀祝礼·银晓之舞（passive:6）是固定天赋：星超导/星扩散转换
        # capability 随内容单元静态声明，无解锁过滤，assembly 静态端口零改动
        # （队伍在场即转换模型，与桑多涅「星耀祝礼·唯理为光」同款）。
        # 星扩散 capability：奥黛塔在队伍即可触发星扩散反应（风命中冰排他
        # 替代普通扩散），辉映·星扩散 Buff 以其资格证据为发放目标。
        reaction_capabilities=(
            STELLAR_CONDUCT_CAPABILITY_KEY,
            STELLAR_SWIRL_CAPABILITY_KEY,
        ),
        metadata={"purpose": "odette_content_basic_kit_and_summon"},
    )


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。"""

    owner_ref = f"character:slot_{request.slot}"
    supported = {
        ODETTE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
        ODETTE_SPECIAL_SKILL_COOLDOWN_ABILITY_KEY,
        ODETTE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    }
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"奥黛塔冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        if key.ability_key not in supported:
            raise ContentUnitValidationError(f"奥黛塔不支持冷却能力键：{key.ability_key}")
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
