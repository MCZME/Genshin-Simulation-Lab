"""砂糖「魔女的前夜礼·七循之理」的纵向集成：激活门槛、投放范围、覆盖刷新与增伤落地。

锁定五件事：① ``passive:9`` 资产效果行经效果工厂挂出两个 hook、两个标记 Buff
定义与两个伤害 provider；② 魔导名录在装配期收集并注册为只读系统，队伍只有
砂糖一名魔导角色时**两档都不生效**；③ 第二名魔导角色进场后，小型风灵档在
**E 施放帧**投给全队、大型风灵档在 **Q 创建帧**只投给魔导角色；④ 重复施放是
覆盖刷新（不叠数值）；⑤ 两档数值作为伤害加成进入伤害账单（不在属性面板里）。

「第二名魔导角色」由测试夹具提供（与需求一致：本期只有砂糖一名角色会声明
魔导标记）——夹具队友与普通队友同形，只在内容单元 metadata 上多一个魔导标记。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_SPIRIT_OBJECT_KEY,
    SUCROSE_WITCHES_EVE_LARGE_BONUS,
    SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES,
    SUCROSE_WITCHES_EVE_SMALL_BONUS,
    SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES,
)
from genshin_sim.content.team.mage import MageRoster
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import (
    ActionStartedPayload,
    EventType,
    GameEvent,
    SpaceEntityCreatedPayload,
)
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import sucrose as sucrose_helpers

# 施放帧：press 1 / release 2 -> 起手帧 2（与 test_elemental_burst 同口径）。
_SKILL_TRACE = sucrose_helpers.press_release(1, "keyboard.e")
_BURST_TRACE = sucrose_helpers.press_release(1, "keyboard.q")
# E 动作起手 2、持续 57（到 58），普攻最早衔接 59；这里在 70 起手，命中 85。
_SKILL_THEN_ATTACK_TRACE = [*_SKILL_TRACE, *sucrose_helpers.press_release(70)]
_ATTACK_HIT_FRAME = 85

_SLOT_1 = AttributeSubjectRef.character("character:slot_1")
_SLOT_2 = AttributeSubjectRef.character("character:slot_2")
_SLOT_3 = AttributeSubjectRef.character("character:slot_3")


def _assemble(
    tmp_path: Path,
    *,
    mage_teammate_slots: tuple[int, ...] = (),
    teammate_elements: tuple[str, ...] = ("pyro", "hydro"),
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 120,
    full_energy: bool = False,
) -> AssembledSimulation:
    asset_db = sucrose_helpers.write_sucrose_asset_database(
        tmp_path / "assets.db",
        teammate_elements=teammate_elements,
        mage_teammate_slots=mage_teammate_slots,
    )
    payload = sucrose_helpers.sucrose_input_payload(
        input_trace=input_trace,
        max_frames=max_frames,
        teammate_elements=teammate_elements,
        full_energy=full_energy,
    )
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=sucrose_helpers.sucrose_test_registry(),
    ).assemble(SimulationInput.from_mapping(payload))


@pytest.fixture
def witches_eve_assembled(tmp_path: Path) -> Callable[..., AssembledSimulation]:
    def _build(**kwargs: Any) -> AssembledSimulation:
        return _assemble(tmp_path, **kwargs)

    return _build


def _active_records(assembled: AssembledSimulation, frame: int, subject, definition_key: str):
    return tuple(
        assembled.buff_store.active(frame, target_ref=subject, definition_key=definition_key)
    )


# --- 挂载与名录 -------------------------------------------------------------


def test_effect_row_mounts_hooks_definitions_and_providers(witches_eve_assembled):
    assembled = witches_eve_assembled(max_frames=10, input_trace=[])

    handler_keys = {unit.handler_key for unit in assembled.content_bundle.content_units}
    assert SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY in handler_keys
    hook_keys = {hook.hook_key for hook in assembled.content_bundle.event_hooks}
    assert hook_keys >= {
        "sucrose.passive.witches_eve.small:character:slot_1",
        "sucrose.passive.witches_eve.large:character:slot_1",
    }
    definition_keys = {
        definition.definition_key for definition in assembled.content_bundle.buff_definitions
    }
    assert definition_keys >= {
        SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
        SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
    }
    provider_keys = assembled.damage_handler.resolver.modifier_index.provider_keys
    assert any("witches_eve_rite.small" in key for key in provider_keys)
    assert any("witches_eve_rite.large" in key for key in provider_keys)


def test_mage_roster_collects_only_marked_characters(witches_eve_assembled):
    assembled = witches_eve_assembled(max_frames=10, input_trace=[], mage_teammate_slots=(2,))

    roster = assembled.context.get_system(MageRoster)
    assert isinstance(roster, MageRoster)
    # 砂糖（槽位 1）+ 魔导夹具队友（槽位 2）；普通夹具队友（槽位 3）不在名录里。
    assert roster.slots == (1, 2)
    assert roster.is_active is True


def test_single_mage_team_never_activates_windows(witches_eve_assembled):
    """只有砂糖一名魔导角色：两档都不投放（能力正确、数据不足）。"""

    assembled = witches_eve_assembled(
        input_trace=_SKILL_TRACE, max_frames=120, mage_teammate_slots=()
    )
    assembled.simulator.run()

    roster = assembled.context.get_system(MageRoster)
    assert isinstance(roster, MageRoster)
    assert roster.slots == (1,)
    assert roster.is_active is False
    for subject in (_SLOT_1, _SLOT_2, _SLOT_3):
        assert (
            _active_records(assembled, 10, subject, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY)
            == ()
        )


# --- 两档投放范围 -----------------------------------------------------------


def test_small_spirit_window_covers_whole_team(witches_eve_assembled):
    assembled = witches_eve_assembled(
        input_trace=_SKILL_TRACE,
        max_frames=120,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro", "hydro"),
    )
    assembled.simulator.run()

    for subject in (_SLOT_1, _SLOT_2, _SLOT_3):
        records = _active_records(
            assembled, 10, subject, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
        )
        assert len(records) == 1
        # 施放帧 2 起算，持续 900 帧：帧 10 在窗内、帧 902 已过期。
        assert _active_records(
            assembled, 901, subject, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
        )
        assert (
            _active_records(assembled, 902, subject, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY)
            == ()
        )
    assert SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES == 900


def test_large_spirit_window_covers_mage_characters_only(witches_eve_assembled):
    assembled = witches_eve_assembled(
        input_trace=_BURST_TRACE,
        max_frames=120,
        full_energy=True,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro", "hydro"),
    )
    assembled.simulator.run()

    # 大型风灵创建帧 19：只投给魔导角色（槽位 1、2），普通队友（槽位 3）没有。
    for subject in (_SLOT_1, _SLOT_2):
        assert (
            len(
                _active_records(
                    assembled, 30, subject, SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY
                )
            )
            == 1
        )
    assert (
        _active_records(assembled, 30, _SLOT_3, SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY) == ()
    )
    # 爆发不是战技：小型档不投放。
    assert (
        _active_records(assembled, 30, _SLOT_1, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY) == ()
    )
    assert SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES == 1200


def test_window_durations_follow_asset_rows(witches_eve_assembled):
    """两档窗口时长取资产效果行（15s / 20s），各自从自己的触发帧起算。

    时长直接读记录的 ``expires_at_frame``：长跑到窗口过期会把记录标记为已移除，
    ``buff_store.active`` 随后对任何帧都不再返回它，故不靠长跑断言过期时刻。
    """

    skill = witches_eve_assembled(
        input_trace=_SKILL_TRACE,
        max_frames=120,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro",),
    )
    skill.simulator.run()
    (record,) = _active_records(skill, 10, _SLOT_1, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY)
    # 施放帧 2 + 900。
    assert record.expires_at_frame == 2 + SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES

    burst = witches_eve_assembled(
        input_trace=_BURST_TRACE,
        max_frames=120,
        full_energy=True,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro",),
    )
    burst.simulator.run()
    (record,) = _active_records(burst, 30, _SLOT_1, SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY)
    # 大型风灵创建帧 19 + 1200。
    assert record.expires_at_frame == 19 + SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES


# --- 覆盖刷新 ---------------------------------------------------------------


def _publish(assembled: AssembledSimulation, event) -> None:
    """把事实注入当前帧并在同轮分发（hook 产出下一轮意图，故再推一帧）。"""

    frame = assembled.context.advance_frame()
    assembled.context.events.publish(event)
    assembled.runtime_world.update_frame(assembled.context, frame)
    frame = assembled.context.advance_frame()
    assembled.runtime_world.update_frame(assembled.context, frame)


def _skill_start_event(frame: int) -> GameEvent:
    return GameEvent(
        EventType.ACTION_STARTED,
        frame,
        ActionStartedPayload(
            instance_id=frame,
            frame=frame,
            action_key="character.sucrose.astable_anemohypostasis_creation_6308",
            owner_slot=1,
            ability_key="elemental_skill",
        ),
    )


def _spirit_created_event(frame: int) -> GameEvent:
    return GameEvent(
        EventType.SPACE_ENTITY_CREATED,
        frame,
        SpaceEntityCreatedPayload(
            frame,
            SpatialEntity(
                entity_id="created_object:sucrose.large_wind_spirit:1",
                kind=SpatialEntityKind.CREATED_OBJECT,
                position=Vector3(),
                owner_key="character:slot_1",
                tags=(SUCROSE_SPIRIT_OBJECT_KEY,),
            ),
        ),
    )


def test_repeated_skill_cast_refreshes_small_window(witches_eve_assembled):
    """同一窗口内再次触发：时长刷新、层数不叠（REFRESH + max_stacks=1）。

    E 的冷却与窗口都是 15s，实战里无法在窗内二次施放；这里手动注入第二次施放
    事实来锁定刷新语义（与 A1 的手动注入反应事实同口径）。
    """

    assembled = witches_eve_assembled(
        input_trace=[], max_frames=60, mage_teammate_slots=(2,), teammate_elements=("pyro",)
    )
    _publish(assembled, _skill_start_event(10))
    first = _active_records(assembled, 20, _SLOT_1, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY)
    assert len(first) == 1
    assert first[0].expires_at_frame == 10 + SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES

    _publish(assembled, _skill_start_event(20))
    second = _active_records(assembled, 30, _SLOT_1, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY)
    assert len(second) == 1
    assert second[0].instance_ref == first[0].instance_ref
    assert second[0].expires_at_frame == 20 + SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES
    assert second[0].state.stack_count == 1


def test_repeated_spirit_creation_refreshes_large_window(witches_eve_assembled):
    assembled = witches_eve_assembled(
        input_trace=[], max_frames=60, mage_teammate_slots=(2,), teammate_elements=("pyro",)
    )
    _publish(assembled, _spirit_created_event(10))
    _publish(assembled, _spirit_created_event(20))

    records = _active_records(assembled, 30, _SLOT_1, SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY)
    assert len(records) == 1
    assert records[0].expires_at_frame == 20 + SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES
    assert records[0].state.stack_count == 1


# --- 增伤落地 ---------------------------------------------------------------


def test_small_spirit_bonus_enters_damage_bonus_zone(witches_eve_assembled):
    """两档数值进伤害账单的伤害加成区，不进属性面板。"""

    assembled = witches_eve_assembled(
        input_trace=_SKILL_THEN_ATTACK_TRACE,
        max_frames=200,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro",),
    )
    assembled.simulator.run()

    results = [record.result for record in assembled.damage_handler.records]
    normal = [result for result in results if result.main_attack_tag == "普通攻击1"]
    assert len(normal) == 1
    assert normal[0].frame == _ATTACK_HIT_FRAME
    assert normal[0].damage_bonus_multiplier == pytest.approx(1.0 + SUCROSE_WITCHES_EVE_SMALL_BONUS)
    assert any("witches_eve_rite.small" in term.provider_key for term in normal[0].applied_terms)
    # 战技本体伤害同在窗内，也吃到同一加成。
    skill = [result for result in results if result.main_attack_tag == "元素战技"]
    assert len(skill) == 1
    assert skill[0].damage_bonus_multiplier == pytest.approx(1.0 + SUCROSE_WITCHES_EVE_SMALL_BONUS)


def test_bonus_is_absent_without_two_mages(witches_eve_assembled):
    """对照组：只有一名魔导角色时，同一段普攻的伤害加成区不受影响。"""

    assembled = witches_eve_assembled(
        input_trace=_SKILL_THEN_ATTACK_TRACE,
        max_frames=200,
        mage_teammate_slots=(),
        teammate_elements=("pyro",),
    )
    assembled.simulator.run()

    results = [record.result for record in assembled.damage_handler.records]
    normal = [result for result in results if result.main_attack_tag == "普通攻击1"]
    assert len(normal) == 1
    assert normal[0].damage_bonus_multiplier == pytest.approx(1.0)
    assert not any(
        "witches_eve_rite" in key for key in (term.provider_key for term in normal[0].applied_terms)
    )


def test_both_windows_stack_additively(witches_eve_assembled):
    """两档独立计时：同帧并存时各自贡献、在伤害加成区加算。

    先施放战技（小型档 15s）再施放爆发（大型档 20s），随后的一次普攻同时吃到
    两档——用「先 E 后 Q」的短序列把两条窗叠在同一帧上。
    """

    trace = [
        *_SKILL_TRACE,
        *sucrose_helpers.press_release(60, "keyboard.q"),
    ]
    assembled = witches_eve_assembled(
        input_trace=trace,
        max_frames=200,
        full_energy=True,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro",),
    )
    assembled.simulator.run()

    for subject in (_SLOT_1, _SLOT_2):
        assert (
            len(
                _active_records(
                    assembled, 80, subject, SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY
                )
            )
            == 1
        )
        assert (
            len(
                _active_records(
                    assembled, 80, subject, SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY
                )
            )
            == 1
        )

    results = [record.result for record in assembled.damage_handler.records]
    # 爆发按拍输出的三拍都落在窗内，取其中一拍核对加成区。
    burst = [result for result in results if result.main_attack_tag == "元素爆发"]
    assert burst
    expected = 1.0 + SUCROSE_WITCHES_EVE_SMALL_BONUS + SUCROSE_WITCHES_EVE_LARGE_BONUS
    for result in burst:
        assert result.damage_bonus_multiplier == pytest.approx(expected)
