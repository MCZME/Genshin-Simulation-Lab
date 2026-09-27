"""桑多涅动作解释器：角色唯一动作表 + 唯一动作解释器。

桑多涅的全部已接入动作（普攻三段、元素战技、元素爆发、跳跃）统一声明在
``data.py`` 的 ``SANDRONE_ACTION_TABLE``，由本解释器独占消费；普攻推进与
跨输入衔接按表内 transitions 实现。重击为触发动作（规划结论 6/10）：无动作
实例与伤害命中点，按下/松开按法洁欧状态机分派 ``state_patch``（待机切入
解算、解算幂等吸收、过载恢复射击；松开退出解算/停火）；元素战技施放即触发
解算功率快速排空。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    CHARGED_ATTACK_INPUT,
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    FAGEOU_MODE_IDLE,
    FAGEOU_MODE_OVERLOAD,
    FAGEOU_MODE_SOLVE,
    FAGEOU_OVERLOAD_EXIT_POWER,
    FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
    FAGEOU_PRE_SWING_FRAMES,
    FAGEOU_RAY_FIRST_OFFSET_FRAMES,
    FAGEOU_STATE_BEAM_BONUS,
    FAGEOU_STATE_BEAM_EXTRAS_LEFT,
    FAGEOU_STATE_DRAIN_ACTIVE,
    FAGEOU_STATE_MODE,
    FAGEOU_STATE_NEXT_RAY_FRAME,
    FAGEOU_STATE_NEXT_SHOT_FRAME,
    FAGEOU_STATE_POWER,
    FAGEOU_STATE_PRISM2_BOOST_UNTIL,
    FAGEOU_STATE_RAY_COUNT,
    FAGEOU_STATE_SOLVE_START_FRAME,
    FAGEOU_STATE_TACTICS_EXPIRE_FRAME,
    FAGEOU_STATE_TACTICS_STACKS,
    INPUT_KIND_BY_KEY,
    JUMP_INPUT,
    NORMAL_ATTACK_INPUT,
    SANDRONE_ACTION_TABLE,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
    SANDRONE_JUMP_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_ACTION_KEYS,
    SANDRONE_P4_BEAM_BONUS_PER_STACK,
    SANDRONE_P4_PRISM_BOOST_POWER_THRESHOLD,
    SANDRONE_P4_PRISM_BOOST_WINDOW_FRAMES,
    SANDRONE_PLUNGE_ACTION_KEY,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import radiance_evidence
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
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
)
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.space.entities import SpatialEntity
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.cooldown import CooldownDurationTerm


class SandroneInterpreterError(RuntimeError):
    """桑多涅解释器运行期错误（接线缺失或状态不一致）。"""


class SandroneActionInterpreter:
    """按已确认帧表解释桑多涅动作输入。

    解释器无实例可变字段；上次动作与起始帧从宿主状态容器读取，推进结果经
    ``state_patch`` 意图提交。
    """

    def __init__(
        self,
        *,
        action_table: dict[str, TimedActionSpec] | None = None,
    ) -> None:
        self._action_table = dict(action_table or SANDRONE_ACTION_TABLE)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        input_kind = INPUT_KIND_BY_KEY.get(session.key)
        if input_kind == CHARGED_ATTACK_INPUT and session.owner.slot is not None:
            # 重击在按下/松开触发器上均需分派，先于普攻的 PRESS 等待。
            return self._interpret_charged_attack(
                context,
                session,
                session.owner.slot,
            )
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")

        if input_kind is None:
            return ActionInterpretationResult.reject(f"桑多涅不支持输入：{session.key}")
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("桑多涅动作需要角色归属槽位")

        slot = session.owner.slot
        height = self._current_height(context.simulation)
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if last_action_key == SANDRONE_PLUNGE_ACTION_KEY and height <= 0:
            last_action_key = ""

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

        rejection = self._transition_rejection(
            input_kind,
            session.release_frame,
            last_action_key,
            last_action_start_frame,
        )
        if rejection is not None:
            return ActionInterpretationResult.reject(rejection)

        action = self._select_action(input_kind, last_action_key, height)
        owner_ref = f"character:slot_{slot}"
        if input_kind == ELEMENTAL_SKILL_INPUT:
            self._queue_e_drain_patch(
                context.simulation,
                owner_ref=owner_ref,
                frame=session.current_frame,
                session_id=session.session_id,
            )
        if input_kind == ELEMENTAL_BURST_INPUT:
            self._queue_burst_cast_patch(
                context.simulation,
                owner_ref=owner_ref,
                frame=session.current_frame,
                session_id=session.session_id,
            )
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
                    **self._action_params(action, input_kind, height),
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
                ability_key="elemental_skill",
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "桑多涅元素战技冷却未就绪"

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
                ability_key="elemental_burst",
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "桑多涅元素爆发冷却或能量未就绪"

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SANDRONE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SandroneInterpreterError(f"缺少桑多涅状态挂载：{exc}") from exc
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
        action: TimedActionSpec,
        input_kind: str,
        height: float,
    ) -> dict[str, object]:
        params: dict[str, object] = {
            "content_handler_key": SANDRONE_CHARACTER_HANDLER_KEY,
            "sandrone_action_kind": input_kind,
            "sandrone_hit_frame": action.hit_frame,
        }
        if action.action_key != SANDRONE_PLUNGE_ACTION_KEY:
            return params
        params.update(
            {
                "sandrone_action_kind": "plunge",
                "plunge_start_height": height,
                "plunge_variant": ("high" if height >= PLUNGE_HIGH_AIR_HEIGHT else "low"),
            }
        )
        return params

    def _validate_known_state(self, last_action_key: str) -> None:
        """状态损坏时确定性报错，不允许静默重启。"""

        if last_action_key and last_action_key not in self._action_table:
            raise SandroneInterpreterError(f"未知桑多涅动作状态：{last_action_key}")

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
            raise SandroneInterpreterError("缺少 IntentQueue，无法提交桑多涅状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sandrone_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=SANDRONE_CHARACTER_HANDLER_KEY,
                    fields={
                        CHAIN_STATE_LAST_ACTION_KEY: action.action_key,
                        CHAIN_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )

    def _read_fageou_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, float]:
        """读取法洁欧模式机的当前模式与解算功率。"""

        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SANDRONE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SandroneInterpreterError(f"缺少桑多涅状态挂载：{exc}") from exc
        raw_mode = mount.values.get(FAGEOU_STATE_MODE)
        mode = raw_mode if isinstance(raw_mode, str) else FAGEOU_MODE_IDLE
        raw_power = mount.values.get(FAGEOU_STATE_POWER)
        power = (
            float(raw_power)
            if isinstance(raw_power, int | float) and not isinstance(raw_power, bool)
            else 0.0
        )
        return mode, power

    def _interpret_charged_attack(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
    ) -> ActionInterpretationResult:
        """重击按状态分派（规划结论 10）。

        待机重击 = 进入解算（前摇 36F 后开始射击与功率上升）；解算态重击
        幂等吸收（不重置会话状态）；过载态重击恢复射击（功率 ≥50）。
        松开退出解算；过载松开停火但模式保持。无动作实例与伤害命中点。
        """

        frame = session.current_frame
        mode, power = self._read_fageou_state(context.simulation, slot)
        if session.trigger is ActionInterpretationTrigger.PRESS:
            fields = self._charged_press_fields(mode, power, frame)
        elif session.trigger is ActionInterpretationTrigger.RELEASE:
            fields = self._charged_release_fields(mode)
        else:
            fields = None
        if fields is not None:
            self._queue_machine_patch(
                context.simulation,
                owner_ref=f"character:slot_{slot}",
                frame=frame,
                session_id=session.session_id,
                fields=fields,
            )
        return ActionInterpretationResult.wait()

    def _charged_press_fields(
        self,
        mode: str,
        power: float,
        frame: int,
    ) -> dict[str, JSONValue] | None:
        if mode == FAGEOU_MODE_SOLVE:
            return None
        if mode == FAGEOU_MODE_OVERLOAD and power >= FAGEOU_OVERLOAD_EXIT_POWER:
            # 功率 ≥50 期间重新按住：恢复过载射击节奏。
            return {
                FAGEOU_STATE_NEXT_SHOT_FRAME: frame + FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
            }
        solve_start = frame + FAGEOU_PRE_SWING_FRAMES
        return {
            FAGEOU_STATE_MODE: FAGEOU_MODE_SOLVE,
            FAGEOU_STATE_SOLVE_START_FRAME: solve_start,
            FAGEOU_STATE_NEXT_SHOT_FRAME: solve_start,
            FAGEOU_STATE_NEXT_RAY_FRAME: solve_start + FAGEOU_RAY_FIRST_OFFSET_FRAMES,
            # 射线会话序号与 C6 集束型额外段按重击会话重置（C2 每轮重击重新
            # 叠层；C6 第三次发射判定随新会话重新计数）。
            FAGEOU_STATE_RAY_COUNT: 0,
            FAGEOU_STATE_BEAM_EXTRAS_LEFT: 0,
        }

    def _charged_release_fields(self, mode: str) -> dict[str, JSONValue] | None:
        if mode == FAGEOU_MODE_SOLVE:
            return {
                FAGEOU_STATE_MODE: FAGEOU_MODE_IDLE,
                FAGEOU_STATE_SOLVE_START_FRAME: 0,
                FAGEOU_STATE_NEXT_SHOT_FRAME: 0,
                FAGEOU_STATE_NEXT_RAY_FRAME: 0,
            }
        if mode == FAGEOU_MODE_OVERLOAD:
            return {FAGEOU_STATE_NEXT_SHOT_FRAME: 0}
        return None

    def _queue_machine_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        fields: dict[str, JSONValue],
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise SandroneInterpreterError("缺少 IntentQueue，无法提交法洁欧状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sandrone_fageou:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=SANDRONE_CHARACTER_HANDLER_KEY,
                    fields=fields,
                ),
            )
        )

    def _queue_e_drain_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
    ) -> None:
        """E 排空：施放即退出解算/过载并快速排空功率（规划结论 4）。

        P4 强化条件在施放帧读取（规划 3.2：400% 条件读清空前的功率值）：
        解算功率超过 50 且施放时持有辉映状态时，写入有时间窗口的棱晶弹
        强化标记，由影响工厂在第二枚棱晶弹展开帧消费。
        """

        slot = int(owner_ref.removeprefix("character:slot_"))
        mode, power = self._read_fageou_state(context, slot)
        if mode == FAGEOU_MODE_IDLE and power <= 0.0:
            return
        fields: dict[str, JSONValue] = {
            FAGEOU_STATE_MODE: FAGEOU_MODE_IDLE,
            FAGEOU_STATE_SOLVE_START_FRAME: 0,
            FAGEOU_STATE_NEXT_SHOT_FRAME: 0,
            FAGEOU_STATE_NEXT_RAY_FRAME: 0,
            FAGEOU_STATE_DRAIN_ACTIVE: True,
        }
        if (
            power > SANDRONE_P4_PRISM_BOOST_POWER_THRESHOLD
            and radiance_evidence(context, owner_ref, frame) is not None
        ):
            fields[FAGEOU_STATE_PRISM2_BOOST_UNTIL] = frame + SANDRONE_P4_PRISM_BOOST_WINDOW_FRAMES
        self._queue_machine_patch(
            context,
            owner_ref=owner_ref,
            frame=frame,
            session_id=session_id,
            fields=fields,
        )

    def _queue_burst_cast_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
    ) -> None:
        """Q 施放：辉映下清空全部改进战术层数并快照光束加成（P4）。

        光束加成 = 0.1 × 清空层数，写入状态字段供聚能光束影响工厂在展开帧
        并入星烁输入的星烁增伤基线；非辉映施放不清层，光束加成写 0 覆盖
        旧值（星烁通道只在辉映下可达，普通光束不消费该字段）。
        """

        slot = int(owner_ref.removeprefix("character:slot_"))
        stacks, _ = self._read_tactics_state(context, slot)
        fields: dict[str, JSONValue] = {FAGEOU_STATE_BEAM_BONUS: 0.0}
        if stacks > 0 and radiance_evidence(context, owner_ref, frame) is not None:
            fields[FAGEOU_STATE_BEAM_BONUS] = min(
                SANDRONE_P4_BEAM_BONUS_PER_STACK * stacks,
                SANDRONE_P4_BEAM_BONUS_PER_STACK * 10,
            )
            fields[FAGEOU_STATE_TACTICS_STACKS] = 0
            fields[FAGEOU_STATE_TACTICS_EXPIRE_FRAME] = 0
        self._queue_machine_patch(
            context,
            owner_ref=owner_ref,
            frame=frame,
            session_id=session_id,
            fields=fields,
        )

    def _read_tactics_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[int, int]:
        """读取 P4 改进战术层数与过期帧。"""

        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SANDRONE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SandroneInterpreterError(f"缺少桑多涅状态挂载：{exc}") from exc
        raw_stacks = mount.values.get(FAGEOU_STATE_TACTICS_STACKS)
        stacks = (
            raw_stacks if isinstance(raw_stacks, int) and not isinstance(raw_stacks, bool) else 0
        )
        raw_expire = mount.values.get(FAGEOU_STATE_TACTICS_EXPIRE_FRAME)
        expire = (
            raw_expire if isinstance(raw_expire, int) and not isinstance(raw_expire, bool) else 0
        )
        return stacks, expire

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
            return f"桑多涅动作缺少 {previous.action_key} -> {input_kind} 的衔接数据"
        earliest_frame = last_action_start_frame + transition_frame
        if frame < earliest_frame:
            return (
                f"桑多涅动作 {previous.action_key} -> {input_kind} "
                f"最早可在第 {earliest_frame} 帧衔接"
            )
        return None

    def _select_action(
        self,
        input_kind: str,
        last_action_key: str,
        height: float,
    ) -> TimedActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            if height >= PLUNGE_LOW_AIR_HEIGHT and last_action_key != SANDRONE_PLUNGE_ACTION_KEY:
                return self._action_table[SANDRONE_PLUNGE_ACTION_KEY]
            return self._select_normal_attack_action(last_action_key)
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[SANDRONE_ELEMENTAL_BURST_ACTION_KEY]
        if input_kind == JUMP_INPUT:
            return self._action_table[SANDRONE_JUMP_ACTION_KEY]
        msg = f"未知桑多涅输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(self, last_action_key: str) -> TimedActionSpec:
        if last_action_key not in SANDRONE_NORMAL_ATTACK_ACTION_KEYS:
            return self._action_table[SANDRONE_NORMAL_ATTACK_ACTION_KEYS[0]]
        last_index = SANDRONE_NORMAL_ATTACK_ACTION_KEYS.index(last_action_key)
        next_index = (last_index + 1) % len(SANDRONE_NORMAL_ATTACK_ACTION_KEYS)
        return self._action_table[SANDRONE_NORMAL_ATTACK_ACTION_KEYS[next_index]]


def create_sandrone_actions(
    action_table: dict[str, TimedActionSpec] | None = None,
    *,
    cooldown_duration_terms: (Mapping[str, tuple[CooldownDurationTerm, ...]] | None) = None,
) -> tuple[Action, ...]:
    """把角色唯一动作表编译为可注册的定时动作。"""

    table = dict(action_table or SANDRONE_ACTION_TABLE)
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
        if action.action_key == SANDRONE_PLUNGE_ACTION_KEY:
            actions[index] = FallPlungeAction(
                action_key=SANDRONE_PLUNGE_ACTION_KEY,
                collision_impact_key=SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
                landing_impact_key=SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
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
