"""砂糖内容单元编译入口。

本文件只负责内容单元编排：读取资产倍率，调用 ``impacts.py`` 的影响契约
编译函数，最后组装 ``ContentUnit``。S1 覆盖普攻四段、重击与下落攻击，尚不
声明冷却 / ICD / 创建物；这些切片随 S2（元素战技）、S3（元素爆发）接入。
"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.content.characters.mondstadt.sucrose.actions import (
    SucroseActionInterpreter,
    create_sucrose_actions,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
    SUCROSE_CONTENT_VERSION,
    SUCROSE_HIT_IMPACT_KEYS,
)
from genshin_sim.content.characters.mondstadt.sucrose.impacts import (
    SucroseActionImpactFactory,
    compile_charged_attack_damage_spec,
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
    TalentLevelResolver,
    index_talent_scalings,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.systems.cooldown import CooldownDurationTerm


def create_sucrose_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """新模型内容单元工厂（砂糖动作状态机 + 普攻/重击/下落契约）。"""

    talent_levels = {
        key: request.talent_levels.get(key, 1)
        for key in ("normal_attack", "elemental_skill", "elemental_burst")
    }
    resolved = TalentLevelResolver.resolve(
        talent_levels,
        request.talent_boosts,
    )
    talent_level = resolved.levels["normal_attack"]
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
    damage_specs.update(
        compile_plunge_damage_specs(
            request.character_key,
            entries_by_key,
            talent_level,
        )
    )
    impact_factory = SucroseActionImpactFactory(damage_specs)
    owner_ref = f"character:slot_{request.slot}"
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
        state_schema=chain_state_schema(owner_ref),
        impact_factories={impact_key: impact_factory for impact_key in SUCROSE_HIT_IMPACT_KEYS},
        metadata={"purpose": "sucrose_action_state_machine"},
    )


def _cooldown_terms_for_actions(
    request: CharacterContentUnitRequest,
) -> Mapping[str, tuple[CooldownDurationTerm, ...]]:
    """把内容贡献的冷却时长 term 按能力键分组并校验归属。

    S1 尚无冷却能力动作，任何非空 term 都会在 ``create_sucrose_actions`` 的
    归属校验中被拒绝，避免静默丢弃（S2 / S3 接入冷却能力后自然放行）。
    """

    owner_ref = f"character:slot_{request.slot}"
    grouped: dict[str, list[CooldownDurationTerm]] = {}
    for key, terms in request.cooldown_duration_terms.items():
        if key.subject.subject_id != owner_ref:
            raise ContentUnitValidationError(
                f"砂糖冷却时长 term 归属不符：{key.subject.subject_id}"
            )
        grouped.setdefault(key.ability_key, []).extend(terms)
    for ability_key, terms in grouped.items():
        markers = [(term.term_key, term.source_ref) for term in terms]
        if len(markers) != len(set(markers)):
            raise ContentUnitValidationError(
                f"{ability_key} 冷却时长 term 重复（term_key, source_ref）"
            )
    return {ability_key: tuple(terms) for ability_key, terms in grouped.items()}
