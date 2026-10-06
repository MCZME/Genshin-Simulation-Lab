"""阿罗夏动作解释器：角色唯一动作表 + 唯一动作解释器。

阿罗夏的全部已接入动作（普攻四段、E 点按、E 长按、重击、Q 施放、下落攻击）
统一声明在 ``data.py`` 的 ``ALYOSHA_ACTION_TABLE``，由本解释器独占消费；
普攻 N1→N4 循环推进与跨输入衔接按表内 transitions 实现。左键与 keyboard.e
均为点按/长按双语义输入：按住阶段（瞄准/蓄势）无仿真效果，解释器在松开帧
按按住时长分派——未达输入分界按点按/普攻解释，达到分界按 E 长按释放阶段/
重击链起手；E 持续按住越过实测上限（250 帧）在 HOLD 触发器上自动起手释放
阶段。
左键另有空中语义：实体基座高度达到通用资料的空中阈值时改判下落攻击（游戏
内空中不可重击，故先于按住分界判定），由通用 ``FallPlungeAction`` 接管。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ACTION_TABLE,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_CHARGED_ATTACK_ACTION_KEY,
    ALYOSHA_ELEMENTAL_BURST_ACTION_KEY,
    ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY,
    ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES,
    ALYOSHA_HOLD_INPUT_MIN_FRAMES,
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS,
    ALYOSHA_PLUNGE_ACTION_KEY,
    ALYOSHA_PLUNGE_COLLISION_IMPACT_KEY,
    ALYOSHA_PLUNGE_LANDING_IMPACT_KEY,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    INPUT_KIND_BY_KEY,
    NORMAL_ATTACK_INPUT,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
)
from genshin_sim.content.generic.plunge import (
    PLUNGE_HIGH_AIR_HEIGHT,
    PLUNGE_LOW_AIR_HEIGHT,
)
from genshin_sim.content.generic.timed_action import (
    TimedActionSpec,
    build_timed_actions,
)
from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.actions import (
    Action,
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    FallPlungeAction,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
)
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.space.entities import SpatialEntity
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.cooldown import CooldownDurationTerm


class AlyoshaInterpreterError(RuntimeError):
    """阿罗夏解释器运行期错误（接线缺失或状态不一致）。"""


class AlyoshaActionInterpreter:
    """按已确认帧表解释阿罗夏动作输入。"""

    def __init__(
        self,
        *,
        action_table: dict[str, TimedActionSpec] | None = None,
    ) -> None:
        self._action_table = dict(action_table or ALYOSHA_ACTION_TABLE)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        input_kind = INPUT_KIND_BY_KEY.get(session.key)
        if session.trigger is ActionInterpretationTrigger.HOLD:
            return self._interpret_hold(context, session, input_kind)
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        if input_kind is None:
            return ActionInterpretationResult.reject(f"阿罗夏不支持输入：{session.key}")
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("阿罗夏动作需要角色归属槽位")

        slot = session.owner.slot
        height = self._current_height(context.simulation)
        if input_kind == ELEMENTAL_SKILL_INPUT:
            rejection = self._elemental_skill_rejection(
                context,
                slot,
                session.current_frame,
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)
        if input_kind == ELEMENTAL_BURST_INPUT:
            rejection = self._elemental_burst_rejection(
                context,
                slot,
                session.current_frame,
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)

        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        # 下落动作以落地结束，落地即高度归零；此时连段状态里的下落键不再代表
        # 空中，重置为空串，使下一次输入按正常连段判定（否则会因下落动作没有
        # 衔接表而被判「缺少衔接数据」）。
        if last_action_key == ALYOSHA_PLUNGE_ACTION_KEY and height <= 0:
            last_action_key = ""
        rejection = self._transition_rejection(
            input_kind,
            session.release_frame,
            last_action_key,
            last_action_start_frame,
        )
        if rejection is not None:
            return ActionInterpretationResult.reject(rejection)

        action = self._select_action(input_kind, last_action_key, session.held_frames, height)
        owner_ref = f"character:slot_{slot}"
        self._queue_state_patch(
            context.simulation,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.release_frame,
        )
        return self._start_result(action, slot, session, height=height)

    def _interpret_hold(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        input_kind: str | None,
    ) -> ActionInterpretationResult:
        """按住触发：E 越过实测最长按住上限时自动进入释放阶段。

        长按的按住阶段（瞄准）无仿真效果，伤害发生在释放阶段；玩家持续按住
        越过 250 帧上限时由本路径起手 E 长按动作（起手帧 = 按下 + 上限帧），
        起手成功即脱离会话，后续物理松开不再重复解释。冷却或衔接条件未就绪
        时保持等待（下一帧重试，物理松开仍可正常解释）。
        """

        if input_kind != ELEMENTAL_SKILL_INPUT:
            return ActionInterpretationResult.wait()
        if session.held_frames < ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES:
            return ActionInterpretationResult.wait()
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("阿罗夏动作需要角色归属槽位")
        slot = session.owner.slot
        if self._elemental_skill_rejection(context, slot, session.current_frame) is not None:
            return ActionInterpretationResult.wait()
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if (
            self._transition_rejection(
                ELEMENTAL_SKILL_INPUT,
                session.current_frame,
                last_action_key,
                last_action_start_frame,
            )
            is not None
        ):
            return ActionInterpretationResult.wait()
        action = self._action_table[ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY]
        self._queue_state_patch(
            context.simulation,
            owner_ref=f"character:slot_{slot}",
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.current_frame,
        )
        return self._start_result(
            action,
            slot,
            session,
            height=self._current_height(context.simulation),
        )

    def _start_result(
        self,
        action: TimedActionSpec,
        slot: int,
        session: InputSessionView,
        *,
        height: float,
    ) -> ActionInterpretationResult:
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params=self._action_params(action, session.key, height),
                source_session_id=session.session_id,
            )
        )

    def _action_params(
        self,
        action: TimedActionSpec,
        input_key: str,
        height: float,
    ) -> dict[str, object]:
        """构造动作参数；下落攻击额外携带起落高度与低空/高空分档。"""

        params: dict[str, object] = {
            "content_handler_key": ALYOSHA_CHARACTER_HANDLER_KEY,
            "alyosha_action_kind": INPUT_KIND_BY_KEY.get(input_key),
            "alyosha_hit_frame": action.hit_frame,
        }
        if action.action_key != ALYOSHA_PLUNGE_ACTION_KEY:
            return params
        params.update(
            {
                "alyosha_action_kind": "plunge",
                "plunge_start_height": height,
                "plunge_variant": ("high" if height >= PLUNGE_HIGH_AIR_HEIGHT else "low"),
            }
        )
        return params

    def _elemental_skill_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
    ) -> str | None:
        """公共条件端口未接线时不阻断，真实装配必须提供端口。"""

        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key=ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "阿罗夏元素战技冷却未就绪"

    def _elemental_burst_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
    ) -> str | None:
        """公共条件端口未接线时不阻断，真实装配必须提供端口。"""

        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key=ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "阿罗夏元素爆发冷却或能量未就绪"

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=ALYOSHA_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise AlyoshaInterpreterError(f"缺少阿罗夏状态挂载：{exc}") from exc
        raw_key = mount.values.get(CHAIN_STATE_LAST_ACTION_KEY)
        last_key = raw_key if isinstance(raw_key, str) else ""
        raw_start = mount.values.get(CHAIN_STATE_LAST_START_FRAME)
        last_start = (
            raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
        )
        return last_key, last_start

    def _current_height(self, context: SimulationContext) -> float:
        """空中事实以 ``player:active.position.y`` 为唯一真值。

        离地与否由位移设施独占判定（内容不自行推断高度场），解释器只读实体
        基座高度，用于分派下落攻击与低空/高空分档。
        """

        entity = self._active_entity(context)
        if entity is None:
            return 0.0
        return float(entity.position.y)

    def _active_entity(self, context: SimulationContext) -> SpatialEntity | None:
        if context.space_runtime is None:
            return None
        return context.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)

    def _validate_known_state(self, last_action_key: str) -> None:
        """状态损坏时确定性报错，不允许静默重启。"""

        if last_action_key and last_action_key not in self._action_table:
            raise AlyoshaInterpreterError(f"未知阿罗夏动作状态：{last_action_key}")

    def _queue_state_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        action: TimedActionSpec,
        start_frame: int,
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise AlyoshaInterpreterError("缺少 IntentQueue，无法提交阿罗夏状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"alyosha_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=ALYOSHA_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=ALYOSHA_CHARACTER_HANDLER_KEY,
                    fields={
                        CHAIN_STATE_LAST_ACTION_KEY: action.action_key,
                        CHAIN_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )

    def _transition_rejection(
        self,
        input_kind: str,
        frame: int,
        last_action_key: str,
        last_action_start_frame: int,
    ) -> str | None:
        if not last_action_key:
            return None
        previous = self._action_table[last_action_key]
        transition_frame = previous.transitions.get(input_kind)
        if transition_frame is None:
            return f"阿罗夏动作缺少 {previous.action_key} -> {input_kind} 的衔接数据"
        earliest_frame = last_action_start_frame + transition_frame
        if frame < earliest_frame:
            return (
                f"阿罗夏动作 {previous.action_key} -> {input_kind} "
                f"最早可在第 {earliest_frame} 帧衔接"
            )
        return None

    def _select_action(
        self,
        input_kind: str,
        last_action_key: str,
        held_frames: int,
        height: float,
    ) -> TimedActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            # 空中左键改判下落攻击（游戏内空中不可重击，故先于按住分界判定）；
            # 已在下落中不重复起手——回落过程由同一次下落动作承载。
            if height >= PLUNGE_LOW_AIR_HEIGHT and last_action_key != ALYOSHA_PLUNGE_ACTION_KEY:
                return self._action_table[ALYOSHA_PLUNGE_ACTION_KEY]
            return self._select_normal_attack_action(last_action_key, held_frames)
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._select_elemental_skill_action(held_frames)
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[ALYOSHA_ELEMENTAL_BURST_ACTION_KEY]
        msg = f"未知阿罗夏输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_elemental_skill_action(self, held_frames: int) -> TimedActionSpec:
        """E 点按/长按按按住时长分派：达到输入分界按长按释放阶段起手。"""

        if held_frames >= ALYOSHA_HOLD_INPUT_MIN_FRAMES:
            return self._action_table[ALYOSHA_ELEMENTAL_SKILL_HOLD_ACTION_KEY]
        return self._action_table[ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY]

    def _select_normal_attack_action(
        self,
        last_action_key: str,
        held_frames: int,
    ) -> TimedActionSpec:
        """左键点按/长按双语义：达到输入分界按重击链起手（不接普攻连段）。

        重击链自带一段普攻前段；重击不改变普攻连段位置，重击后下一次点按
        从一段普攻重新起手（``last_action_key`` 为重击键时不在普攻序列内）。
        """

        if held_frames >= ALYOSHA_HOLD_INPUT_MIN_FRAMES:
            return self._action_table[ALYOSHA_CHARGED_ATTACK_ACTION_KEY]
        if last_action_key not in ALYOSHA_NORMAL_ATTACK_ACTION_KEYS:
            return self._action_table[ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[0]]
        last_index = ALYOSHA_NORMAL_ATTACK_ACTION_KEYS.index(last_action_key)
        next_index = (last_index + 1) % len(ALYOSHA_NORMAL_ATTACK_ACTION_KEYS)
        return self._action_table[ALYOSHA_NORMAL_ATTACK_ACTION_KEYS[next_index]]


def create_alyosha_actions(
    action_table: dict[str, TimedActionSpec] | None = None,
    *,
    cooldown_duration_terms: (Mapping[str, tuple[CooldownDurationTerm, ...]] | None) = None,
) -> tuple[Action, ...]:
    """把角色唯一动作表编译为可注册的定时动作。

    下落攻击不使用固定时间线（时长由位移设施的碰撞/落地事实决定），因此把
    表内占位条目替换为通用 ``FallPlungeAction``：碰撞事实发出下坠碰撞影响点、
    落地事实发出落地影响点并结束动作。
    """

    table = dict(action_table or ALYOSHA_ACTION_TABLE)
    terms_by_ability = dict(cooldown_duration_terms or {})
    actions: list[Action] = list(build_timed_actions(tuple(table.values())))
    cooldown_abilities = {
        action.cooldown_ability_key
        for action in actions
        if isinstance(action, TimedImpactAction) and action.cooldown_ability_key is not None
    }
    unmatched = set(terms_by_ability) - cooldown_abilities
    if unmatched:
        keys = ", ".join(sorted(unmatched))
        raise ValueError(f"冷却时长 term 没有对应的定时动作冷却能力：{keys}")
    for index, action in enumerate(actions):
        if action.action_key == ALYOSHA_PLUNGE_ACTION_KEY:
            actions[index] = FallPlungeAction(
                action_key=ALYOSHA_PLUNGE_ACTION_KEY,
                collision_impact_key=ALYOSHA_PLUNGE_COLLISION_IMPACT_KEY,
                landing_impact_key=ALYOSHA_PLUNGE_LANDING_IMPACT_KEY,
            )
            continue
        if not isinstance(action, TimedImpactAction):
            continue
        ability_key = action.cooldown_ability_key
        if ability_key is None or ability_key not in terms_by_ability:
            continue
        actions[index] = replace(
            action,
            cooldown_duration_terms=terms_by_ability[ability_key],
        )
    return tuple(actions)
