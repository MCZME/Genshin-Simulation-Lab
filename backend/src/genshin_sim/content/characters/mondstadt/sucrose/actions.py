"""砂糖动作解释器：角色唯一动作表 + 唯一动作解释器。

砂糖的全部动作（普攻四段、重击、元素战技、元素爆发、跳跃、下落攻击）统一
声明在 ``data.py`` 的 ``SUCROSE_ACTION_TABLE``，由本解释器独占消费；普攻推进
与跨输入衔接按表内 transitions 实现。帧表数据使用 generic ``TimedActionSpec``，
动作编译复用 ``build_timed_actions``，宿主状态使用 generic 连段状态 schema。

分期口径（实施规划 §10）：S1 开放普攻 / 重击 / 跳跃；S2 追加元素战技输入与
冷却门槛；S3 追加元素爆发输入与冷却 / 能量门槛（门槛统一走公共条件端口，爆发
的能量门槛由端口按冷却定义的 ``ELEMENTAL_BURST`` 能力类型自动带出）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    CHARGED_ATTACK_INPUT,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    JUMP_INPUT,
    NORMAL_ATTACK_INPUT,
    SUCROSE_ACTION_TABLE,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CHARGED_ATTACK_ACTION_KEY,
    SUCROSE_ELEMENTAL_BURST_ACTION_KEY,
    SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
    SUCROSE_ELEMENTAL_SKILL_ACTION_KEY,
    SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
    SUCROSE_INPUT_KIND_BY_KEY,
    SUCROSE_JUMP_ACTION_KEY,
    SUCROSE_NORMAL_ATTACK_ACTION_KEYS,
    SUCROSE_PLUNGE_ACTION_KEY,
    SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
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
from genshin_sim.content.generic.transitions import (
    TransitionVerdict,
    evaluate_transition,
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


class SucroseInterpreterError(RuntimeError):
    """砂糖解释器运行期错误（接线缺失或状态不一致）。"""


class SucroseActionInterpreter:
    """按已确认帧表解释砂糖动作输入。

    解释器无实例可变字段；上次动作与起始帧从宿主状态容器读取，推进结果经
    ``state_patch`` 意图提交。
    """

    def __init__(
        self,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
    ) -> None:
        self._action_table = dict(action_table or SUCROSE_ACTION_TABLE)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")

        input_kind = SUCROSE_INPUT_KIND_BY_KEY.get(session.key)
        if input_kind is None:
            return ActionInterpretationResult.reject(f"砂糖不支持输入：{session.key}")
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("砂糖动作需要角色归属槽位")

        slot = session.owner.slot
        height = self._current_height(context.simulation)
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if last_action_key == SUCROSE_PLUNGE_ACTION_KEY and height <= 0:
            last_action_key = ""

        if input_kind == ELEMENTAL_SKILL_INPUT:
            rejection = self._ability_rejection(
                context,
                slot,
                session.current_frame,
                ability_key=SUCROSE_ELEMENTAL_SKILL_COOLDOWN_ABILITY_KEY,
                blocked_message="砂糖元素战技冷却未就绪",
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)
        if input_kind == ELEMENTAL_BURST_INPUT:
            rejection = self._ability_rejection(
                context,
                slot,
                session.current_frame,
                ability_key=SUCROSE_ELEMENTAL_BURST_COOLDOWN_ABILITY_KEY,
                blocked_message="砂糖元素爆发冷却或能量未就绪",
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)

        # 衔接判定用当前解释帧（重评路径即为重评帧）：未到最早衔接帧由解释器
        # 交管理器缓冲，查无衔接数据仍为终局拒绝。
        verdict = self._transition_verdict(
            input_kind,
            session.current_frame,
            last_action_key,
            last_action_start_frame,
        )
        if verdict.before_earliest:
            return ActionInterpretationResult.defer(verdict.reject_message())
        if verdict.missing_data:
            return ActionInterpretationResult.reject(verdict.reject_message())

        action = self._select_action(input_kind, last_action_key, height)
        owner_ref = f"character:slot_{slot}"
        self._queue_state_patch(
            context.simulation,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.current_frame,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params={
                    **self._action_params(context, action, input_kind, height),
                },
                source_session_id=session.session_id,
            )
        )

    def _ability_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
        *,
        ability_key: str,
        blocked_message: str,
    ) -> str | None:
        """能力门槛（冷却 / 爆发能量）：公共条件端口未接线时不阻断，真实装配必须提供端口。

        爆发能量门槛由端口按冷却定义的 ``ELEMENTAL_BURST`` 能力类型自动带出，
        内容侧只声明能力键与失败文案。
        """

        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key=ability_key,
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return blocked_message

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SUCROSE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SucroseInterpreterError(f"缺少砂糖状态挂载：{exc}") from exc
        raw_key = mount.values.get(CHAIN_STATE_LAST_ACTION_KEY)
        last_key = raw_key if isinstance(raw_key, str) else ""
        raw_start = mount.values.get(CHAIN_STATE_LAST_START_FRAME)
        last_start = (
            raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
        )
        return last_key, last_start

    def _current_height(self, context: SimulationContext) -> float:
        """空中事实以 ``player:active.position.y`` 为唯一真值。"""

        entity = self._active_entity(context)
        if entity is None:
            return 0.0
        return float(entity.position.y)

    def _active_entity(self, context: SimulationContext) -> SpatialEntity | None:
        if context.space_runtime is None:
            return None
        return context.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)

    def _action_params(
        self,
        context: ActionInterpretationContext,
        action: TimedActionSpec,
        input_kind: str,
        height: float,
    ) -> Mapping[str, object]:
        params: dict[str, object] = {
            "content_handler_key": SUCROSE_CHARACTER_HANDLER_KEY,
            "sucrose_action_kind": input_kind,
            "sucrose_hit_frame": action.hit_frame,
        }
        if action.action_key != SUCROSE_PLUNGE_ACTION_KEY:
            return params
        params.update(
            {
                "sucrose_action_kind": "plunge",
                "plunge_start_height": height,
                "plunge_variant": ("high" if height >= PLUNGE_HIGH_AIR_HEIGHT else "low"),
            }
        )
        return params

    def _validate_known_state(self, last_action_key: str) -> None:
        """状态损坏时确定性报错，不允许静默重启。"""

        if last_action_key and last_action_key not in self._action_table:
            raise SucroseInterpreterError(f"未知砂糖动作状态：{last_action_key}")

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
            raise SucroseInterpreterError("缺少 IntentQueue，无法提交砂糖状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sucrose_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SUCROSE_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=SUCROSE_CHARACTER_HANDLER_KEY,
                    fields={
                        CHAIN_STATE_LAST_ACTION_KEY: action.action_key,
                        CHAIN_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )

    def _transition_verdict(
        self,
        input_kind: str,
        frame: int,
        last_action_key: str,
        last_action_start_frame: int,
    ) -> TransitionVerdict:
        """按砂糖动作表判定衔接三态（共享 generic 判定）。"""

        return evaluate_transition(
            action_table=self._action_table,
            display_name="砂糖",
            prev_action_key=last_action_key,
            input_kind=input_kind,
            frame=frame,
            prev_start_frame=last_action_start_frame,
        )

    def _select_action(
        self,
        input_kind: str,
        last_action_key: str,
        height: float,
    ) -> TimedActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            if height >= PLUNGE_LOW_AIR_HEIGHT and last_action_key != SUCROSE_PLUNGE_ACTION_KEY:
                return self._action_table[SUCROSE_PLUNGE_ACTION_KEY]
            return self._select_normal_attack_action(last_action_key)
        if input_kind == CHARGED_ATTACK_INPUT:
            return self._action_table[SUCROSE_CHARGED_ATTACK_ACTION_KEY]
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[SUCROSE_ELEMENTAL_SKILL_ACTION_KEY]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[SUCROSE_ELEMENTAL_BURST_ACTION_KEY]
        if input_kind == JUMP_INPUT:
            return self._action_table[SUCROSE_JUMP_ACTION_KEY]
        msg = f"未知砂糖输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(self, last_action_key: str) -> TimedActionSpec:
        if last_action_key not in SUCROSE_NORMAL_ATTACK_ACTION_KEYS:
            return self._action_table[SUCROSE_NORMAL_ATTACK_ACTION_KEYS[0]]
        last_index = SUCROSE_NORMAL_ATTACK_ACTION_KEYS.index(last_action_key)
        next_index = (last_index + 1) % len(SUCROSE_NORMAL_ATTACK_ACTION_KEYS)
        return self._action_table[SUCROSE_NORMAL_ATTACK_ACTION_KEYS[next_index]]


def create_sucrose_actions(
    action_table: Mapping[str, TimedActionSpec] | None = None,
    *,
    cooldown_duration_terms: Mapping[str, tuple[CooldownDurationTerm, ...]] | None = None,
) -> tuple[Action, ...]:
    """把角色唯一动作表编译为可注册的定时动作。

    ``cooldown_duration_terms`` 按能力键（``elemental_skill`` / ``elemental_burst``）
    挂到对应定时动作上；没有对应定时动作的能力键在此确定性失败。
    """

    table = dict(action_table or SUCROSE_ACTION_TABLE)
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
        if action.action_key == SUCROSE_PLUNGE_ACTION_KEY:
            actions[index] = FallPlungeAction(
                action_key=SUCROSE_PLUNGE_ACTION_KEY,
                collision_impact_key=SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
                landing_impact_key=SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
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
