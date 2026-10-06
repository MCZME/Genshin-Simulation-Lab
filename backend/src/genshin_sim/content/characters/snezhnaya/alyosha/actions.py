"""阿罗夏动作解释器：角色唯一动作表 + 唯一动作解释器。

阿罗夏的全部已接入动作（普攻四段、E 点按、Q 施放）统一声明在 ``data.py``
的 ``ALYOSHA_ACTION_TABLE``，由本解释器独占消费；普攻 N1→N4 循环推进与
跨输入衔接按表内 transitions 实现。E 长按（按住/释放阶段）与重击的输入
语义待后续切片接入，当前 keyboard.e 统一按点按在松开帧起手。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ACTION_TABLE,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_ELEMENTAL_BURST_ACTION_KEY,
    ALYOSHA_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY,
    ALYOSHA_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    ALYOSHA_NORMAL_ATTACK_ACTION_KEYS,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    INPUT_KIND_BY_KEY,
    NORMAL_ATTACK_INPUT,
)
from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
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
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        if input_kind is None:
            return ActionInterpretationResult.reject(f"阿罗夏不支持输入：{session.key}")
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("阿罗夏动作需要角色归属槽位")

        slot = session.owner.slot
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
        rejection = self._transition_rejection(
            input_kind,
            session.release_frame,
            last_action_key,
            last_action_start_frame,
        )
        if rejection is not None:
            return ActionInterpretationResult.reject(rejection)

        action = self._select_action(input_kind, last_action_key)
        owner_ref = f"character:slot_{slot}"
        self._queue_state_patch(
            context.simulation,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.release_frame,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params={
                    "content_handler_key": ALYOSHA_CHARACTER_HANDLER_KEY,
                    "alyosha_action_kind": input_kind,
                    "alyosha_hit_frame": action.hit_frame,
                },
                source_session_id=session.session_id,
            )
        )

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
    ) -> TimedActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            return self._select_normal_attack_action(last_action_key)
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[ALYOSHA_ELEMENTAL_SKILL_ACTION_KEY]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[ALYOSHA_ELEMENTAL_BURST_ACTION_KEY]
        msg = f"未知阿罗夏输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(self, last_action_key: str) -> TimedActionSpec:
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
    """把角色唯一动作表编译为可注册的定时动作。"""

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
