"""砂糖命座 C1–C6 的纵向集成：命座门控、静态切片落地与运行期减冷却。

锁定六层各一件可观测的事：

- C1：战技冷却的充能数变为 2 且恢复模式改为独立——端到端表现为**连续两次施放
  元素战技都成功**（单充能下第二次会被冷却拒绝）；
- C2：爆发窗口延长 2 秒——端到端表现为风灵按拍 **3 拍变 4 拍**；
- C3 / C5：天赋等级提升单元按命座挂载（等级上限由天赋框架承担）；
- C4：普攻 / 重击累计命中 7 次后战技冷却被减——端到端表现为冷却的
  ``active_ready_frame`` 前移 60–420 帧（整数秒）；
- C6：爆发染色后全队（含砂糖）挂上对应元素伤害加成，魔导·秘仪激活时魔导角色
  再挂一条魔导增强。

C4 是本包第一条走**运行期冷却意图**的机制（减冷却的数值只能在触发帧决定），
因此这里的端到端断言同时也是那条通道的验收。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES,
    SUCROSE_SPIRIT_OBJECT_KEY,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.cooldown import (
    CooldownQuery,
    CooldownRecoveryMode,
    CooldownRuntime,
)
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import sucrose as sucrose_helpers
from tests.helpers.reactions import apply_aura

_SKILL_TRACE = sucrose_helpers.press_release(1, "keyboard.e")
_BURST_TRACE = sucrose_helpers.press_release(1, "keyboard.q")
# E 起手 2、持续 57（到 58），普攻最早衔接 59；命中帧 = 起手 + 42。
_SECOND_SKILL_TRACE = [
    *sucrose_helpers.press_release(1, "keyboard.e"),
    *sucrose_helpers.press_release(60, "keyboard.e"),
]
_SLOT_1 = AttributeSubjectRef.character("character:slot_1")
_SLOT_2 = AttributeSubjectRef.character("character:slot_2")
_SLOT_3 = AttributeSubjectRef.character("character:slot_3")
_C6_MAIN_KEY = "sucrose.constellation.c6.elemental_damage_bonus.buff"
_C6_MAGE_KEY = "sucrose.constellation.c6.mage_enhancement.buff"


def _assemble(
    tmp_path: Path,
    *,
    constellation: int = 0,
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 120,
    full_energy: bool = False,
    mage_teammate_slots: tuple[int, ...] = (),
    teammate_elements: tuple[str, ...] = ("pyro", "hydro"),
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
        constellation=constellation,
    )
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        content_unit_registry=sucrose_helpers.sucrose_test_registry(),
    ).assemble(SimulationInput.from_mapping(payload))


@pytest.fixture
def constellation_assembled(tmp_path: Path) -> Callable[..., AssembledSimulation]:
    def _build(**kwargs: Any) -> AssembledSimulation:
        return _assemble(tmp_path, **kwargs)

    return _build


def _skill_ready_frame(assembled: AssembledSimulation, frame: int) -> int | None:
    """战技冷却「最早到期在途恢复项」的到期帧（无在途项时为 ``None``）。"""

    runtime = assembled.context.get_system(CooldownRuntime)
    assert isinstance(runtime, CooldownRuntime)
    key = next(
        record.key
        for record in runtime.store.records
        if record.key.ability_key == SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY
    )
    view = runtime.query_condition(CooldownQuery(key, frame)).view
    return view.active_ready_frame


def _active_records(assembled: AssembledSimulation, frame: int, subject, definition_key: str):
    return tuple(
        assembled.buff_store.active(frame, target_ref=subject, definition_key=definition_key)
    )


# --- 挂载与门控 -------------------------------------------------------------


def test_constellation_units_mount_by_constellation(constellation_assembled):
    assembled = constellation_assembled(constellation=6, max_frames=10, input_trace=[])

    handler_keys = {unit.handler_key for unit in assembled.content_bundle.content_units}
    assert handler_keys >= {
        SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
        SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
        SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
        SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
        SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    }
    hook_keys = {hook.hook_key for hook in assembled.content_bundle.event_hooks}
    assert "sucrose.constellation.c4:character:slot_1" in hook_keys
    assert "sucrose.constellation.c6:character:slot_1" in hook_keys
    definition_keys = {
        definition.definition_key for definition in assembled.content_bundle.buff_definitions
    }
    assert {_C6_MAIN_KEY, _C6_MAGE_KEY} <= definition_keys


def test_constellation_below_threshold_keeps_slices_gated(constellation_assembled):
    """未达到层号时：天赋提升等静态切片被剥离，命座 hook 不启用。

    命座单元本身始终挂载（事件 hook 由 HookDispatcher 按解锁条件在第 0 帧
    求值启用），门控的可观测面是「静态切片为空 + hook 不在启用集合」。
    """

    assembled = constellation_assembled(constellation=2, max_frames=10, input_trace=[])

    boosts_by_handler = {
        unit.handler_key: dict(unit.talent_level_boosts)
        for unit in assembled.content_bundle.content_units
    }
    assert boosts_by_handler.get(SUCROSE_CONSTELLATION_C3_HANDLER_KEY) == {}
    assert boosts_by_handler.get(SUCROSE_CONSTELLATION_C5_HANDLER_KEY) == {}

    from genshin_sim.content.hooks import HookDispatcher

    dispatcher = assembled.context.get_system(HookDispatcher)
    enabled = dispatcher._enabled_hook_keys
    assert enabled is not None
    assert "sucrose.constellation.c4:character:slot_1" not in enabled
    assert "sucrose.constellation.c6:character:slot_1" not in enabled


# --- C1：双充能独立恢复 -----------------------------------------------------


def test_c1_definition_uses_two_charges_and_independent_recovery(constellation_assembled):
    assembled = constellation_assembled(constellation=1, max_frames=10, input_trace=[])

    definitions = {
        definition.key.ability_key: definition
        for definition in assembled.content_bundle.cooldown_definitions
    }
    skill = definitions[SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY]
    assert skill.max_charges == 2
    assert skill.recovery_mode is CooldownRecoveryMode.INDEPENDENT
    # 爆发冷却不受 C1 影响。
    assert definitions["elemental_burst"].max_charges == 1
    assert definitions["elemental_burst"].recovery_mode is CooldownRecoveryMode.SERIAL


def test_c1_allows_two_consecutive_elemental_skills(constellation_assembled):
    """端到端：两次施放都在冷却窗口内成功（第二次不再被拒）。"""

    assembled = constellation_assembled(
        constellation=1, input_trace=_SECOND_SKILL_TRACE, max_frames=120
    )
    assembled.simulator.run()

    skill_hits = [
        record
        for record in assembled.damage_handler.records
        if record.result.main_attack_tag == "元素战技"
    ]
    # 命中帧 = 起手帧 + 42（起手 2 / 61 → 命中 44 / 103）。
    assert [record.result.frame for record in skill_hits] == [44, 103]


def test_single_charge_rejects_second_cast(constellation_assembled):
    """对照组：未点 C1 时第二次施放被冷却拒绝。"""

    assembled = constellation_assembled(
        constellation=0, input_trace=_SECOND_SKILL_TRACE, max_frames=120
    )
    assembled.simulator.run()

    skill_hits = [
        record
        for record in assembled.damage_handler.records
        if record.result.main_attack_tag == "元素战技"
    ]
    assert len(skill_hits) == 1


# --- C2：爆发窗口 8s / 4 拍 -------------------------------------------------


def test_c2_extends_burst_window_to_four_ticks(constellation_assembled):
    assembled = constellation_assembled(
        constellation=2, input_trace=_BURST_TRACE, max_frames=560, full_energy=True
    )
    assembled.simulator.run()

    frames = [
        record.result.frame
        for record in assembled.damage_handler.records
        if record.result.damage_name == "持续伤害"
    ]
    assert frames == [139, 259, 379, 499]


def test_burst_keeps_three_ticks_without_c2(constellation_assembled):
    assembled = constellation_assembled(
        constellation=0, input_trace=_BURST_TRACE, max_frames=560, full_energy=True
    )
    assembled.simulator.run()

    frames = [
        record.result.frame
        for record in assembled.damage_handler.records
        if record.result.damage_name == "持续伤害"
    ]
    assert frames == [139, 259, 379]


def test_spirit_lifetime_follows_c2(constellation_assembled):
    assembled = constellation_assembled(constellation=2, max_frames=10, input_trace=[])

    spirit = assembled.content_bundle.created_object_types[SUCROSE_SPIRIT_OBJECT_KEY]
    assert spirit.duration_frames == 481
    assert spirit.tick_count == 4


# --- C4：累计命中随机减冷却 -------------------------------------------------


def _seven_normal_attacks() -> list[dict[str, object]]:
    """七次普攻（每段一次命中）：起手间隔 25 帧 > 计次间隔 6 帧。"""

    trace: list[dict[str, object]] = []
    for index in range(7):
        trace.extend(sucrose_helpers.press_release(60 + index * 25))
    return trace


def test_c4_reduces_skill_cooldown_after_seven_hits(constellation_assembled):
    """实验组与对照组成对：C4 命中 7 次后到期帧前移 60–420 帧（整数秒）。"""

    trace = [*_SKILL_TRACE, *_seven_normal_attacks()]
    # 查询帧不得早于运行时已归一化的帧（max_frames 即仿真终点）。
    baseline_run = constellation_assembled(constellation=3, input_trace=trace, max_frames=320)
    baseline_run.simulator.run()
    reduced_run = constellation_assembled(constellation=4, input_trace=trace, max_frames=320)
    reduced_run.simulator.run()
    baseline = _skill_ready_frame(baseline_run, 320)
    reduced_ready = _skill_ready_frame(reduced_run, 320)

    assert baseline is not None
    assert reduced_ready is not None
    reduction = baseline - reduced_ready
    assert reduction > 0
    assert reduction % 60 == 0
    assert 60 <= reduction <= 420


def test_c4_is_inactive_below_threshold(constellation_assembled):
    """对照组：未点 C4 时冷却到期帧保持基线（满 7 次命中也不减）。"""

    trace = [*_SKILL_TRACE, *_seven_normal_attacks()]
    assembled = constellation_assembled(constellation=3, input_trace=trace, max_frames=320)
    assembled.simulator.run()

    # 冷却起始帧 = 施放帧 2 + 起始偏移 9（§4.4「CD」列）→ ready = 11 + 900。
    assert _skill_ready_frame(assembled, 320) == 11 + SUCROSE_ELEMENTAL_SKILL_COOLDOWN_FRAMES


# --- C6：染色增伤与魔导增强 -------------------------------------------------


def test_c6_grants_whole_team_after_absorption(constellation_assembled):
    assembled = constellation_assembled(
        constellation=6,
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
        mage_teammate_slots=(2,),
        teammate_elements=("pyro", "hydro"),
    )
    apply_aura(assembled, Element.PYRO, "sucrose:c6:pyro", frame=0)
    assembled.simulator.run()

    # 首拍（139）带出染色伤害，C6 由此触发；全队（含砂糖自己）都挂上。
    for subject in (_SLOT_1, _SLOT_2, _SLOT_3):
        records = _active_records(assembled, 140, subject, _C6_MAIN_KEY)
        assert len(records) == 1
    # 魔导·秘仪激活（砂糖 + 槽位 2 的魔导夹具）→ 魔导角色再挂一条增强。
    for subject in (_SLOT_1, _SLOT_2):
        assert len(_active_records(assembled, 140, subject, _C6_MAGE_KEY)) == 1
    assert _active_records(assembled, 140, _SLOT_3, _C6_MAGE_KEY) == ()


def test_c6_is_absent_without_absorption(constellation_assembled):
    """对照组：没有可染色附着时（纯风伤）C6 不触发。"""

    assembled = constellation_assembled(
        constellation=6,
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
        mage_teammate_slots=(2,),
    )
    assembled.simulator.run()

    records = assembled.damage_handler.records
    assert not [r for r in records if r.result.damage_name == "附加元素伤害"]
    for subject in (_SLOT_1, _SLOT_2, _SLOT_3):
        assert _active_records(assembled, 140, subject, _C6_MAIN_KEY) == ()


def test_c6_duration_follows_burst_window(constellation_assembled):
    """C2 延长后 C6 时长同步为 8s（爆发生命周期 481 帧）。"""

    assembled = constellation_assembled(
        constellation=6,
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
        mage_teammate_slots=(2,),
    )
    apply_aura(assembled, Element.PYRO, "sucrose:c6:pyro", frame=0)
    assembled.simulator.run()

    records = _active_records(assembled, 140, _SLOT_1, _C6_MAIN_KEY)
    assert len(records) == 1
    # 触发帧 139 + 481 → 过期帧 620（过期判据不含端点帧：619 在窗内、620 不在）。
    assert records[0].expires_at_frame == 139 + 481
    assert _active_records(assembled, 619, _SLOT_1, _C6_MAIN_KEY)
    assert _active_records(assembled, 620, _SLOT_1, _C6_MAIN_KEY) == ()
