"""砂糖固有天赋 A1 / A4 的纵向集成：挂载、投放范围与分桶观测。

锁定三件事：① 两支天赋由**资产效果行**（``passive:4`` / ``passive:5``）经效果
工厂挂出 hook 与 Buff 定义，突破阶段不足时不生效；② A1 只投放给「与被扩散元素
一致」的队友，A4 投放给除砂糖外的全体角色，两者都不含砂糖自己；③ A4 的产物在
属性解析里落进**不可转化**桶（``reconvertible=False``），A1 的产物留在可转化桶。

数值全部为合成数据（见测试规范 §3.2）：砂糖的精通来源是圣遗物面板词条
（``elemental_mastery``），队友不含精通来源，因此队友的精通读数只由天赋贡献。
A1 的反应事实由元素结算发布，这里手动注入同构事实（与队伍作用域共鸣用例同
口径），不重跑扩散反应链本身。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_BUFF_DEFINITION_KEY,
    SUCROSE_A1_MASTERY_FLAT,
    SUCROSE_A4_BUFF_DEFINITION_KEY,
    SUCROSE_A4_MASTERY_RATIO,
    SUCROSE_A4_MASTERY_TERM_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
)
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolution,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import AuraKind
from genshin_sim.core.events import EventType, GameEvent, ReactionOccurredPayload
from genshin_sim.core.systems.reaction.models import ReactionOccurrence
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import sucrose as sucrose_helpers

# 合成精通：A4 折算比例 0.2 -> 队友单次加成 40。
_SUCROSE_FIXTURE_MASTERY = 200.0
_SKILL_TRACE = sucrose_helpers.press_release(1, "keyboard.e")
_SLOT_1 = AttributeSubjectRef.character("character:slot_1")
_SLOT_2 = AttributeSubjectRef.character("character:slot_2")
_SLOT_3 = AttributeSubjectRef.character("character:slot_3")


def _resolve_mastery(
    assembled: AssembledSimulation,
    frame: int,
    subject: AttributeSubjectRef,
) -> AttributeResolution:
    return assembled.attribute_runtime.resolver.resolve(
        AttributeQuery(subject_ref=subject, attribute_key=STAT_ELEMENTAL_MASTERY, frame=frame)
    )


def _active_buff_count(
    assembled: AssembledSimulation,
    frame: int,
    subject: AttributeSubjectRef,
    definition_key: str,
) -> int:
    return len(
        assembled.buff_store.active(
            frame,
            target_ref=subject,
            definition_key=definition_key,
        )
    )


def _publish_reaction(
    assembled: AssembledSimulation,
    occurrence: ReactionOccurrence,
) -> int:
    """把反应事实注入当前帧并在同轮分发，返回可供断言的后续帧号。

    反应事实由元素结算在帧内发布；这里手动推帧以在 clear 之后、世界更新之前
    注入同构事实（与 ``test_resonance_team_scope_projection`` 同口径）。hook
    产出的是「下一结算轮次」的意图，因此再推一帧让其落库。
    """

    frame = assembled.context.advance_frame()
    assembled.context.events.publish(
        GameEvent(EventType.REACTION_OCCURRED, frame, ReactionOccurredPayload(occurrence))
    )
    assembled.runtime_world.update_frame(assembled.context, frame)
    frame = assembled.context.advance_frame()
    assembled.runtime_world.update_frame(assembled.context, frame)
    return frame


def _assemble(
    tmp_path: Path,
    *,
    teammate_elements: tuple[str, ...] = ("pyro", "hydro"),
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 240,
    mastery: float = _SUCROSE_FIXTURE_MASTERY,
    full_energy: bool = False,
    sucrose_ascension_phase: int = 6,
    payload: dict[str, object] | None = None,
) -> AssembledSimulation:
    asset_db = sucrose_helpers.write_sucrose_asset_database(
        tmp_path / "assets.db",
        teammate_elements=teammate_elements,
        sucrose_ascension_phase=sucrose_ascension_phase,
    )
    if payload is None:
        payload = sucrose_helpers.sucrose_input_payload(
            input_trace=input_trace,
            max_frames=max_frames,
            teammate_elements=teammate_elements,
            mastery=mastery,
            full_energy=full_energy,
        )
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=sucrose_helpers.sucrose_test_registry(),
    ).assemble(SimulationInput.from_mapping(payload))


@pytest.fixture
def sucrose_team_assembled(tmp_path: Path) -> Callable[..., AssembledSimulation]:
    def _build(**kwargs: Any) -> AssembledSimulation:
        return _assemble(tmp_path, **kwargs)

    return _build


# --- 挂载 -------------------------------------------------------------------


def test_passive_effect_rows_mount_hooks_and_buff_definitions(sucrose_team_assembled):
    assembled = sucrose_team_assembled(max_frames=10, input_trace=[])

    hook_keys = {hook.hook_key for hook in assembled.content_bundle.event_hooks}
    assert "sucrose.passive.a1:character:slot_1" in hook_keys
    assert "sucrose.passive.a4:character:slot_1" in hook_keys
    handler_keys = {unit.handler_key for unit in assembled.content_bundle.content_units}
    assert SUCROSE_PASSIVE_A1_HANDLER_KEY in handler_keys
    assert SUCROSE_PASSIVE_A4_HANDLER_KEY in handler_keys
    definition_keys = {
        definition.definition_key for definition in assembled.content_bundle.buff_definitions
    }
    assert SUCROSE_A1_BUFF_DEFINITION_KEY in definition_keys
    assert SUCROSE_A4_BUFF_DEFINITION_KEY in definition_keys


def test_a1_stays_locked_below_ascension_one(sucrose_team_assembled):
    """突破 0 阶：A1（1 阶解锁）不响应扩散事实。

    hook 仍在内容包里（解锁求值发生在第 0 帧的 hook 通道），被禁用后不产出
    任何 Buff；故这里断言「行为不存在」而不是「hook 不在包内」。
    """

    assembled = sucrose_team_assembled(
        max_frames=10,
        input_trace=[],
        teammate_elements=("pyro",),
        mastery=0.0,
        sucrose_ascension_phase=0,
    )
    frame = _publish_reaction(
        assembled,
        sucrose_helpers.make_swirl_occurrence(aura_kind=AuraKind.PYRO),
    )
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0
    assert _resolve_mastery(assembled, frame, _SLOT_2).final_value == 0.0


def test_a4_stays_locked_below_ascension_four(sucrose_team_assembled):
    """突破 3 阶：A4（4 阶解锁）不响应战技命中；突破 4 阶则生效。"""

    locked = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=_SKILL_TRACE,
        max_frames=120,
        sucrose_ascension_phase=3,
    )
    locked.simulator.run()
    assert _active_buff_count(locked, 60, _SLOT_2, SUCROSE_A4_BUFF_DEFINITION_KEY) == 0
    assert _resolve_mastery(locked, 60, _SLOT_2).final_value == 0.0

    unlocked = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=_SKILL_TRACE,
        max_frames=120,
        sucrose_ascension_phase=4,
    )
    unlocked.simulator.run()
    assert _active_buff_count(unlocked, 60, _SLOT_2, SUCROSE_A4_BUFF_DEFINITION_KEY) == 1


# --- A1 触媒置换术 ----------------------------------------------------------


def test_a1_grants_mastery_to_same_element_teammate_only(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro", "hydro"),
        max_frames=10,
        input_trace=[],
        mastery=0.0,
    )
    frame = _publish_reaction(
        assembled,
        sucrose_helpers.make_swirl_occurrence(aura_kind=AuraKind.PYRO),
    )

    # 火元素队友吃到 +50；水队友与砂糖自己被排除。
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A1_BUFF_DEFINITION_KEY) == 1
    assert _active_buff_count(assembled, frame, _SLOT_3, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0
    assert _active_buff_count(assembled, frame, _SLOT_1, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0

    resolution = _resolve_mastery(assembled, frame, _SLOT_2)
    assert resolution.final_value == SUCROSE_A1_MASTERY_FLAT
    # A1 是固定值来源，产物留在可转化桶。
    assert resolution.reconvertible_value == SUCROSE_A1_MASTERY_FLAT
    assert resolution.non_reconvertible_value == 0.0


def test_a1_requires_reactant_element_to_match(sucrose_team_assembled):
    """被扩散元素为冰（含 FROZEN 口径）时只有冰队友入选。"""

    assembled = sucrose_team_assembled(
        teammate_elements=("pyro", "cryo"),
        max_frames=10,
        input_trace=[],
        mastery=0.0,
    )
    frame = _publish_reaction(
        assembled,
        sucrose_helpers.make_swirl_occurrence(aura_kind=AuraKind.FROZEN),
    )

    assert _active_buff_count(assembled, frame, _SLOT_3, SUCROSE_A1_BUFF_DEFINITION_KEY) == 1
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0


def test_a1_skips_when_no_teammate_matches_the_element(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("hydro",),
        max_frames=10,
        input_trace=[],
        mastery=0.0,
    )
    frame = _publish_reaction(
        assembled,
        sucrose_helpers.make_swirl_occurrence(aura_kind=AuraKind.PYRO),
    )
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0
    assert _resolve_mastery(assembled, frame, _SLOT_2).final_value == 0.0


def test_a1_ignores_swirls_triggered_by_other_characters(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro",),
        max_frames=10,
        input_trace=[],
        mastery=0.0,
    )
    frame = _publish_reaction(
        assembled,
        sucrose_helpers.make_swirl_occurrence(
            aura_kind=AuraKind.PYRO,
            source_key="character:slot_2",
        ),
    )
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A1_BUFF_DEFINITION_KEY) == 0


# --- A4 小小的慧风 ----------------------------------------------------------


def test_a4_grants_snapshot_mastery_to_every_teammate_except_sucrose(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro", "hydro"),
        input_trace=_SKILL_TRACE,
        max_frames=200,
    )
    assembled.simulator.run()

    # 战技命中帧 44 -> Buff 意图在下一结算轮次落库；取 60 帧观测。
    frame = 60
    assert _active_buff_count(assembled, frame, _SLOT_2, SUCROSE_A4_BUFF_DEFINITION_KEY) == 1
    assert _active_buff_count(assembled, frame, _SLOT_3, SUCROSE_A4_BUFF_DEFINITION_KEY) == 1
    assert _active_buff_count(assembled, frame, _SLOT_1, SUCROSE_A4_BUFF_DEFINITION_KEY) == 0

    # 砂糖面板 200 精通 × 20% = 40；产物的数值来自「读精通再折算」。
    expected = _SUCROSE_FIXTURE_MASTERY * SUCROSE_A4_MASTERY_RATIO
    resolution = _resolve_mastery(assembled, frame, _SLOT_2)
    assert resolution.final_value == expected
    # A4 是转化效果：产物落进不可转化桶，可转化桶为空。
    assert resolution.reconvertible_value == 0.0
    assert resolution.non_reconvertible_value == expected


def test_a4_leaves_sucrose_panel_mastery_reconvertible(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=_SKILL_TRACE,
        max_frames=200,
    )
    assembled.simulator.run()

    # 砂糖自己保留面板精通（圣遗物词条，默认可转化），不吃自己的天赋。
    resolution = _resolve_mastery(assembled, 60, _SLOT_1)
    assert resolution.final_value == _SUCROSE_FIXTURE_MASTERY
    assert resolution.reconvertible_value == _SUCROSE_FIXTURE_MASTERY
    assert resolution.non_reconvertible_value == 0.0


def test_a4_buff_record_carries_term_key_and_snapshot_value(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=_SKILL_TRACE,
        max_frames=200,
    )
    assembled.simulator.run()

    records = assembled.buff_store.active(
        60,
        target_ref=_SLOT_2,
        definition_key=SUCROSE_A4_BUFF_DEFINITION_KEY,
    )
    assert len(records) == 1
    record = records[0]
    assert record.definition.handler_key == SUCROSE_PASSIVE_A4_HANDLER_KEY
    resolved = {item.term_key: item.value for item in record.state.resolved_modifiers}
    assert resolved == {
        SUCROSE_A4_MASTERY_TERM_KEY: _SUCROSE_FIXTURE_MASTERY * SUCROSE_A4_MASTERY_RATIO
    }


def test_a4_refreshes_instead_of_stacking_on_repeated_hits(sucrose_team_assembled):
    """战技与爆发各命中一次：覆盖刷新为单份实例，不叠数值也不叠层。"""

    assembled = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=[
            *sucrose_helpers.press_release(1, "keyboard.e"),
            {"frame": 62, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 63, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
        max_frames=320,
        full_energy=True,
    )
    damage_events = sucrose_helpers.sucrose_damage_events(assembled)
    assembled.simulator.run()

    # 至少两次触发（战技 + 爆发的风灵按拍）；实例始终只有一份。
    trigger_frames = sorted(
        event.frame
        for event in damage_events
        if event.payload.result.main_attack_tag in {"元素战技", "元素爆发"}
    )
    assert len(trigger_frames) >= 2
    records = assembled.buff_store.active(
        trigger_frames[-1] + 2,
        target_ref=_SLOT_2,
        definition_key=SUCROSE_A4_BUFF_DEFINITION_KEY,
    )
    assert len(records) == 1
    assert records[0].state.stack_count == 1
    assert records[0].state.resolved_modifiers[0].value == (
        _SUCROSE_FIXTURE_MASTERY * SUCROSE_A4_MASTERY_RATIO
    )


def test_a4_ignores_normal_attack_and_charged_attack_hits(sucrose_team_assembled):
    assembled = sucrose_team_assembled(
        teammate_elements=("pyro",),
        input_trace=sucrose_helpers.press_release(1, "mouse.left"),
        max_frames=200,
    )
    assembled.simulator.run()

    assert _active_buff_count(assembled, 60, _SLOT_2, SUCROSE_A4_BUFF_DEFINITION_KEY) == 0
