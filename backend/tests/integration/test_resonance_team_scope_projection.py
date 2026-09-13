"""双草队伍作用域共鸣 Buff 的装配与属性投影集成用例。

验证能力：共鸣阶段消费绽放事实后，双草动态 Buff 以队伍作用域主体挂载一份，
经属性 provider 投影到队伍内前台与后台角色的属性解析，且不投影到 Target 主体。
输入与数据：合成角色资产与合成绽放事实，不依赖真实资产库数值。
不覆盖：双草静态/动态共鸣的数值基线（见 `tests/golden/resonance/`）与 Buff 领域
自身的主体语义（见 `tests/unit/core/systems/buff/`）。
"""

from __future__ import annotations

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content import PLAYER_TEAM_SCOPE
from genshin_sim.content.team.resonance import RESONANCE_DENDRO_EM_30_BUFF_KEY
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolution,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType, GameEvent, ReactionOccurredPayload
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import BLOOM_REACTION_KEY
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    ReactionOccurrence,
)
from tests.helpers.assembly import minimal_input
from tests.helpers.asset_repository import FakeAssetRepository
from tests.helpers.team_assets import make_character_asset


class _DendroTeamRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__(
            characters=(
                make_character_asset(1, "dendro"),
                make_character_asset(2, "dendro"),
                make_character_asset(3, "hydro"),
                make_character_asset(4, "pyro"),
            ),
            effect_payloads=(),
        )


def test_resonance_team_scope_buff_projects_onto_every_character():
    assembled = SimulationAssembler(_DendroTeamRepository()).assemble(
        SimulationInput.from_mapping(_dendro_team_input_payload())
    )
    assert assembled.resonance_store.active_keys == ("resonance.dendro",)

    # 绽放事实由元素结算在帧内发布；这里手动推帧以在 clear 之后、世界更新之前
    # 注入同构事实，确保共鸣阶段能读到它，意图在下一结算轮次落库。
    frame = assembled.context.advance_frame()
    assembled.context.events.publish(
        GameEvent(
            EventType.REACTION_OCCURRED,
            frame,
            ReactionOccurredPayload(_bloom_occurrence()),
        )
    )
    assembled.runtime_world.update_frame(assembled.context, frame)
    frame = assembled.context.advance_frame()
    assembled.runtime_world.update_frame(assembled.context, frame)

    team_records = assembled.buff_store.active(
        frame,
        target_ref=AttributeSubjectRef.team(PLAYER_TEAM_SCOPE),
        definition_key=RESONANCE_DENDRO_EM_30_BUFF_KEY,
    )
    assert len(team_records) == 1
    instance_id = team_records[0].instance_ref.to_key()

    # 队伍作用域词条投影到队伍内每个角色：前台与后台都能读到同一份实例词条。
    for slot in (1, 2, 3, 4):
        resolution = _resolve_elemental_mastery(assembled, frame, slot)
        assert any(term.source_ref.instance_id == instance_id for term in resolution.applied_terms)

    # Target 主体不属于队伍作用域，读不到该词条。
    target_resolution = assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(
            AttributeSubjectRef.target("target:1"),
            STAT_ELEMENTAL_MASTERY,
            frame,
        )
    )
    assert not any(
        term.source_ref.instance_id == instance_id for term in target_resolution.applied_terms
    )


def _resolve_elemental_mastery(assembled, frame: int, slot: int) -> AttributeResolution:
    return assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(
            AttributeSubjectRef.character(f"character:slot_{slot}"),
            STAT_ELEMENTAL_MASTERY,
            frame,
        )
    )


def _bloom_occurrence() -> ReactionOccurrence:
    return ReactionOccurrence(
        occurrence_ref="occurrence:resonance.bloom",
        interaction_id="interaction:resonance.bloom",
        reaction_key=BLOOM_REACTION_KEY,
        direction_key="dendro+hydro",
        profile_key="profile:bloom",
        source_ref=ElementalSourceRef("character:slot_1"),
        subject_ref=ElementalSubjectRef.character("character:slot_1"),
        transition=ElementalTransitionEffect(
            aura_kind=AuraKind.HYDRO,
            incoming_before=AuraAmount.one(),
            incoming_consumed=AuraAmount.one(),
            incoming_remaining=AuraAmount.zero(),
            aura_before=AuraAmount.one(),
            aura_consumed=AuraAmount.one(),
            aura_remaining=AuraAmount.zero(),
        ),
    )


def _dendro_team_input_payload() -> dict[str, object]:
    payload = minimal_input().to_dict()
    payload["team"] = [
        {
            "slot": slot,
            "character": {
                "asset_key": f"character:{element}_{slot}",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        }
        for slot, element in (
            (1, "dendro"),
            (2, "dendro"),
            (3, "hydro"),
            (4, "pyro"),
        )
    ]
    return payload
