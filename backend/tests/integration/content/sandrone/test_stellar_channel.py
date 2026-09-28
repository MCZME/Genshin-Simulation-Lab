"""桑多涅辉映星烁直伤通道的纵向集成。

链路对齐星超导反应契约 §8："辉映 Buff 属性证据 -> ``StellarReactionDamageInput``
组装 -> 伤害请求"：辉映·星烁 Buff 由真实 BuffRuntime 按星超导协调的申请
计划直接注入（反应触发链路已由 core 测试覆盖），随后验证射线/第二枚棱晶
弹的发射时查表分派与星烁公式结算；聚能光束在本文件经内容工厂展开验证
（聚焦展开分派），完整 Q 施放链路见 test_elemental_burst。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.content import (
    create_sandrone_content_unit,
)
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.actions import ActionOwnerRef, CandidateTargetRef
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    plan_radiance_buff_requests,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ActionImpactContext,
)
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
)
from tests.helpers import sandrone as sandrone_helpers

RAY_STELLAR_DISPLAY_NAME = "重击冷凝射线星超导伤害"
RAY_STELLAR_SWIRL_DISPLAY_NAME = "重击冷凝射线星扩散伤害"
SWEEP_DISPLAY_NAME = "重击扫射伤害"
PRISM_DISPLAY_NAME = "棱晶弹伤害"
PRISM_STELLAR_DISPLAY_NAME = "棱晶弹星超导伤害"
BEAM_STELLAR_DISPLAY_NAME = "聚能光束星超导伤害"


def _damage_events(assembled) -> list:
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def _apply_radiance_buff(assembled, *, settled_stacks: int = 3) -> None:
    """按星超导协调的申请计划注入辉映·星烁 Buff（属性证据侧入口）。"""

    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    runtime.commit_prevalidated(
        runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=0,
                occurrence_ref="integration:stellar:radiance",
                character_refs=(AttributeSubjectRef.character("character:slot_1"),),
                settled_stacks=settled_stacks,
                field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
    )


def _resolved_atk(assembled) -> float:
    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref=AttributeSubjectRef.character("character:slot_1"),
            attribute_key=STAT_ATK_TOTAL,
            frame=1,
        )
    )
    return float(resolution.final_value)


def _line_target_payload(
    max_frames: int, press: int, release: int, *, constellation: int = 0
) -> dict[str, object]:
    return sandrone_helpers.sandrone_input_payload(
        max_frames=max_frames,
        constellation=constellation,
        input_trace=[
            {"frame": press, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": release, "events": [{"key": "mouse.right", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )


def test_radiance_buff_switches_rays_to_stellar_conduct_channel(sandrone_assembled):
    # 射线在发射时查表分派：持辉映·星烁（3 层快照 → 系数 1.55）后走星超导冰
    # 通道，专用倍率条目组装 scaling_value = ATK × 星超导倍率；功率动力学与
    # 帧表不受变体影响（射线命中仍 +12 功率）。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376))
    _apply_radiance_buff(assembled)
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in damage_events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert [e.frame for e in rays] == [128, 188, 248]
    atk = _resolved_atk(assembled)
    for event in rays:
        result = event.payload.result
        assert result.main_attack_tag == "星超导冰"
        stellar = result.stellar_reaction_resolution
        assert stellar is not None
        assert stellar.input.mode == "character_direct"
        assert stellar.input.scaling_value == pytest.approx(atk)
        assert stellar.input.stellar_base_multiplier == pytest.approx(1.55)
    # 扫射不携带星变体：辉映下仍走普通重击通道，解算期间按 21F 节奏持续到
    # 过载翻转（射击轨换 30F 节奏，294 起为过载伤害）。
    sweeps = [e for e in damage_events if e.payload.result.damage_name == SWEEP_DISPLAY_NAME]
    assert [e.frame for e in sweeps] == [42, 63, 84, 105, 126, 147, 168, 189, 210, 231, 252]
    assert all(e.payload.result.main_attack_tag == "重击" for e in sweeps)


def test_radiance_buff_switches_second_prism_only(sandrone_assembled):
    # 第二枚棱晶弹切星超导冰通道，第一枚保持普通战技伤害（3.1 分支清单）。
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=60)
    _apply_radiance_buff(assembled)
    damage_events = _damage_events(assembled)

    assembled.simulator.run()

    # 帧表：动作自释放帧（2）起算，棱晶弹 +16/+32。
    assert [(e.frame, e.payload.result.damage_name) for e in damage_events] == [
        (18, PRISM_DISPLAY_NAME),
        (34, PRISM_STELLAR_DISPLAY_NAME),
    ]
    atk = _resolved_atk(assembled)
    first, second = damage_events
    assert first.payload.result.main_attack_tag == "元素战技"
    assert second.payload.result.main_attack_tag == "星超导冰"
    stellar = second.payload.result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.scaling_value == pytest.approx(atk)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.55)


def test_radiance_buff_switches_beam_contract_at_factory_dispatch(sandrone_assembled):
    # 聚能光束在影响点展开时查表分派；爆发能量来源接入前无法经完整 Q 施放
    # 链路出伤，此处直接驱动内容工厂验证契约切换与星烁输入组装。
    assembled = sandrone_assembled(input_key="keyboard.e", max_frames=40)
    _apply_radiance_buff(assembled)
    unit = create_sandrone_content_unit(
        CharacterContentUnitRequest(
            handler_key=sandrone_helpers.SANDRONE_CHARACTER_HANDLER_KEY,
            character_key=sandrone_helpers.SANDRONE_CHARACTER_KEY,
            slot=1,
            talent_levels={"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
            talent_scalings=sandrone_helpers.minimal_sandrone_scaling_entries(),
        )
    )
    factory = unit.impact_factories[SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY]
    requests = factory.create_requests(
        ActionImpactContext(
            frame=10,
            impact_point_id="integration:beam:1",
            source_instance_id=1,
            owner=ActionOwnerRef.character(1),
            action_key=SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
            impact_key=SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
            target_refs=(
                CandidateTargetRef(spatial_entity_id="target:target_1", target_id="target_1"),
            ),
            simulation=assembled.context,
        )
    )

    assert len(requests) == 1
    spec = requests[0].damage_spec
    assert spec is not None
    assert spec.main_attack_tag == "星超导冰"
    assert spec.display_name == BEAM_STELLAR_DISPLAY_NAME
    assert spec.stellar_reaction is not None
    atk = _resolved_atk(assembled)
    assert spec.stellar_reaction.mode == "character_direct"
    assert spec.stellar_reaction.scaling_value == pytest.approx(atk)
    assert spec.stellar_reaction.stellar_base_multiplier == pytest.approx(1.55)


def test_stellar_swirl_trigger_activates_swirl_channel(sandrone_assembled):
    # 全链路：桑多涅声明星扩散 capability → 风命中冰排他
    # 替代普通扩散触发星扩散 → 辉映·星扩散 Buff 发放给 capability 提供者
    # （桑多涅）→ 重击射线查表切到星扩散冰通道（系数证据固定 1.0）。
    # 冰/风附着经注册的元素结算协调器在仿真前种入；"附着触发反应"链路本身
    # 由 core 星扩散测试覆盖，此处验证内容侧 capability 声明到直伤分派。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376))
    damage_events = _damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.CRYO, "target:target_1", "test:swirl:cryo"
        ),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.ANEMO, "target:target_1", "test:swirl:anemo"
        ),
    )

    buff_runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(buff_runtime, BuffRuntime)
    swirl_buffs = buff_runtime.reader.active(
        0, definition_key=STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY
    )
    assert [record.state.target_ref.entity_id for record in swirl_buffs] == ["character:slot_1"]

    assembled.simulator.run()

    rays = [
        e for e in damage_events if e.payload.result.damage_name == RAY_STELLAR_SWIRL_DISPLAY_NAME
    ]
    assert [e.frame for e in rays] == [128, 188, 248]
    atk = _resolved_atk(assembled)
    for event in rays:
        result = event.payload.result
        assert result.main_attack_tag == "星扩散冰"
        stellar = result.stellar_reaction_resolution
        assert stellar is not None
        assert stellar.input.mode == "character_direct"
        # 星扩散系数证据固定 1.0；倍率分量以普通变体占位（合成条目 1.0）。
        assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)
        assert stellar.input.scaling_value == pytest.approx(atk)
    # 星超导未触发（无雷冰反应）：射线不得走星超导通道。
    assert not [
        e for e in damage_events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME
    ]


def test_c1_bonus_covers_stellar_swirl_damage(sandrone_assembled):
    # C1 增伤为星烁反应通用增伤：星扩散冰标签同样
    # 命中增伤区。星扩散触发链与上一用例相同，仅 C1 生效。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=1))
    damage_events = _damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.CRYO, "target:target_1", "test:swirl:cryo"
        ),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.ANEMO, "target:target_1", "test:swirl:anemo"
        ),
    )

    assembled.simulator.run()

    rays = [
        e for e in damage_events if e.payload.result.damage_name == RAY_STELLAR_SWIRL_DISPLAY_NAME
    ]
    # C1 功率提升速度减半（上升与射线命中增量一并折算）：0 命 3 次涌现为
    # 1 命 6 次，380 帧窗口内可见前 5 次（128/188/248/308/368）。
    assert [e.frame for e in rays] == [128, 188, 248, 308, 368]
    for event in rays:
        stellar = event.payload.result.stellar_reaction_resolution
        assert stellar is not None
        assert event.payload.result.main_attack_tag == "星扩散冰"
        # C1 的 +30% 并入星烁输入的增伤位（星烁路径不产出槽位账单）。
        assert stellar.input.stellar_bonus == pytest.approx(0.3)
