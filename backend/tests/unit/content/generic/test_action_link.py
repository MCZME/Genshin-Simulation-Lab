"""切人衔接只读视图单测：可切人帧派生、按槽位读取与无能力解释器兜底。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ACTION_TABLE,
    ALYOSHA_ELEMENTAL_BURST_ACTION_KEY,
)
from genshin_sim.content.generic.action_link import SlotActionLinkPort
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
    chain_state_schema,
)
from genshin_sim.content.generic.character_actions import (
    CHARGED_ATTACK_INPUT,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    NORMAL_ATTACK_INPUT,
    SWITCH_INPUT,
    GenericCharacterActionInterpreter,
    GenericCharacterActionSpec,
    switch_offset_frames,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActiveActionLinkView,
    InputSessionView,
)
from genshin_sim.core.entity_states import CharacterRuntimeState, ContentStateMount
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime

_HANDLER_1 = "character.link_one"
_HANDLER_2 = "character.link_two"

_NA1 = "character.link_one.na1"
_SKILL1 = "character.link_one.skill"
_BURST1 = "character.link_one.burst"
_JUMP1 = "character.link_one.jump"
_PLUNGE1 = "character.link_one.plunge"

_NA1_DURATION = 20
_SKILL1_DURATION = 40

_SKILL2 = "character.link_two.skill"
_PLUNGE2 = "character.link_two.plunge"

_TABLE_1: dict[str, TimedActionSpec] = {
    _NA1: TimedActionSpec(
        action_key=_NA1,
        duration_frames=_NA1_DURATION,
        hit_frame=6,
        impact_key=f"{_NA1}.hit",
        transitions={NORMAL_ATTACK_INPUT: _NA1_DURATION, CHARGED_ATTACK_INPUT: 18},
    ),
    _SKILL1: TimedActionSpec(
        action_key=_SKILL1,
        duration_frames=_SKILL1_DURATION,
        hit_frame=12,
        impact_key=f"{_SKILL1}.hit",
        transitions={SWITCH_INPUT: 12, NORMAL_ATTACK_INPUT: _SKILL1_DURATION},
    ),
    _BURST1: TimedActionSpec(
        action_key=_BURST1,
        duration_frames=50,
        transitions={NORMAL_ATTACK_INPUT: 50},
    ),
    _JUMP1: TimedActionSpec(action_key=_JUMP1, duration_frames=30, transitions={}),
    _PLUNGE1: TimedActionSpec(action_key=_PLUNGE1, duration_frames=1, transitions={}),
}

_TABLE_2: dict[str, TimedActionSpec] = {
    _SKILL2: TimedActionSpec(
        action_key=_SKILL2,
        duration_frames=30,
        transitions={SWITCH_INPUT: 5},
    ),
    _PLUNGE2: TimedActionSpec(action_key=_PLUNGE2, duration_frames=1, transitions={}),
}


def _build_spec(
    handler_key: str,
    table: dict[str, TimedActionSpec],
    *,
    normal_attack_keys: tuple[str, ...],
    skill_key: str,
    burst_key: str,
    plunge_key: str,
    jump_key: str | None = None,
) -> GenericCharacterActionSpec:
    return GenericCharacterActionSpec(
        display_name=handler_key,
        character_handler_key=handler_key,
        input_kind_by_session_key={"mouse.left": NORMAL_ATTACK_INPUT},
        action_table=table,
        normal_attack_action_keys=normal_attack_keys,
        plunge_action_key=plunge_key,
        plunge_collision_impact_key=f"{plunge_key}.collision",
        plunge_landing_impact_key=f"{plunge_key}.landing",
        elemental_skill_action_key=skill_key,
        elemental_burst_action_key=burst_key,
        jump_action_key=jump_key,
    )


_SPEC_1 = _build_spec(
    _HANDLER_1,
    _TABLE_1,
    normal_attack_keys=(_NA1,),
    skill_key=_SKILL1,
    burst_key=_BURST1,
    plunge_key=_PLUNGE1,
    jump_key=_JUMP1,
)
_SPEC_2 = _build_spec(
    _HANDLER_2,
    _TABLE_2,
    normal_attack_keys=(_SKILL2,),
    skill_key=_SKILL2,
    burst_key=_SKILL2,
    plunge_key=_PLUNGE2,
)


@dataclass(slots=True)
class _TablelessInterpreter:
    """不使用衔接表的解释器（只满足 ActionInterpreter 协议，验证端口兜底）。"""

    supported_action_keys: tuple[str, ...] = ("character.probe.skill",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context, session
        return ActionInterpretationResult.wait()


def _mount(spec: GenericCharacterActionSpec, owner_ref: str, last_key: str, start: int):
    return ContentStateMount(
        spec.character_handler_key,
        chain_state_schema(owner_ref),
        initial_values={
            CHAIN_STATE_LAST_ACTION_KEY: last_key,
            CHAIN_STATE_LAST_START_FRAME: start,
        },
    )


def _context(
    *,
    active_slot: int = 1,
    slot1: tuple[str, int] = ("", 0),
    slot2: tuple[str, int] = ("", 0),
    height: float = 0.0,
) -> SimulationContext:
    team_state = TeamRuntimeState(
        (
            CharacterRuntimeState(
                slot=1,
                character_key="character:link_one",
                level=90,
                content_states={
                    _SPEC_1.character_handler_key: _mount(_SPEC_1, "character:slot_1", *slot1)
                },
            ),
            CharacterRuntimeState(
                slot=2,
                character_key="character:link_two",
                level=90,
                content_states={
                    _SPEC_2.character_handler_key: _mount(_SPEC_2, "character:slot_2", *slot2)
                },
            ),
        ),
        active_slot=active_slot,
    )
    context = SimulationContext()
    context.space_runtime = SpaceRuntime(
        space=Space(
            [
                SpatialEntity(
                    "player:active",
                    SpatialEntityKind.ACTIVE_CHARACTER,
                    position=Vector3(0.0, height, 0.0),
                    active_slot=active_slot,
                )
            ]
        ),
        team_state=team_state,
    )
    return context


def _port() -> SlotActionLinkPort:
    return SlotActionLinkPort(
        {
            1: GenericCharacterActionInterpreter(_SPEC_1),
            2: GenericCharacterActionInterpreter(_SPEC_2),
        }
    )


# --- 可切人帧派生 -------------------------------------------------------------


def test_switch_offset_derives_earliest_link_frame():
    """未声明切人列：取该动作各衔接列的最早帧，不引入新的时间口径。"""

    assert switch_offset_frames(_TABLE_1[_NA1]) == 18


def test_switch_offset_prefers_explicit_switch_column():
    """显式声明切人列时以声明值为准（后续可按来源逐条覆盖派生值）。"""

    assert switch_offset_frames(_TABLE_1[_SKILL1]) == 12


def test_switch_offset_is_none_without_transition_data():
    """整表无衔接数据（跳跃 / 下落）：无可派生帧。"""

    assert switch_offset_frames(_TABLE_1[_JUMP1]) is None
    assert switch_offset_frames(_TABLE_1[_PLUNGE1]) is None


# --- 按槽位读取衔接视图 -------------------------------------------------------


def test_link_view_is_empty_without_live_action():
    """链状态没有在进行的动作：切人视图为空，不限制切换。"""

    view = _port().read(_context())

    assert view == ActiveActionLinkView(active_slot=1)


def test_link_view_reports_live_action_and_switch_offset():
    """在进行的动作：给出动作键、起手帧与派生的可切人帧。"""

    context = _context(slot1=(_NA1, 100))
    context.clock.advance(105)

    view = _port().read(context)

    assert view.action_key == _NA1
    assert view.start_frame == 100
    assert view.switch_offset_frames == 18
    assert view.earliest_switch_frame == 118


def test_link_view_ignores_action_past_its_duration():
    """动作结束后按「无前置动作」处理（与输入衔接的存活判定同源）。"""

    context = _context(slot1=(_NA1, 100))
    context.clock.advance(100 + _NA1_DURATION)

    view = _port().read(context)

    assert view.action_key is None


def test_link_view_ignores_plunge_after_landing_and_reports_it_in_air():
    """下落按高度存活：落地后不构成在进行的动作，空中则报下落且不限制切换。"""

    landed = _context(slot1=(_PLUNGE1, 10), height=0.0)
    landed.clock.advance(40)
    assert _port().read(landed).action_key is None

    airborne = _context(slot1=(_PLUNGE1, 10), height=5.0)
    airborne.clock.advance(40)
    view = _port().read(airborne)
    assert view.action_key == _PLUNGE1
    assert view.earliest_switch_frame is None


def test_link_view_reads_the_active_slot():
    """端口按当前场上槽位读取：切到槽位 2 后读到槽位 2 的动作表与链状态。"""

    context = _context(active_slot=2, slot1=(_NA1, 100), slot2=(_SKILL2, 200))
    context.clock.advance(203)

    view = _port().read(context)

    assert view.active_slot == 2
    assert view.action_key == _SKILL2
    assert view.earliest_switch_frame == 205


def test_link_view_is_permissive_without_transition_capable_interpreter():
    """解释器不提供衔接能力（只满足 ActionInterpreter）：按无在进行的动作回答。"""

    port = SlotActionLinkPort({1: _TablelessInterpreter()})
    context = _context(slot1=(_NA1, 100))
    context.clock.advance(105)

    assert port.read(context) == ActiveActionLinkView(active_slot=1)


def test_link_view_is_empty_without_space_runtime():
    """没有战场空间运行态时给出空视图（不猜测当前场上角色）。"""

    assert SlotActionLinkPort({}).read(SimulationContext()) == ActiveActionLinkView()


# --- 真实内容包的切人衔接列 ---------------------------------------------------


def test_alyosha_burst_declares_measured_switch_link_frame():
    """阿罗夏 Q 最快衔接帧实测 76：普攻 / 战技 / 切人列声明 76，Q→Q 维持兜底。"""

    burst = ALYOSHA_ACTION_TABLE[ALYOSHA_ELEMENTAL_BURST_ACTION_KEY]

    assert burst.duration_frames == 148
    assert switch_offset_frames(burst) == 76
    assert burst.transitions[NORMAL_ATTACK_INPUT] == 76
    assert burst.transitions[ELEMENTAL_SKILL_INPUT] == 76
    assert burst.transitions[ELEMENTAL_BURST_INPUT] == 149
