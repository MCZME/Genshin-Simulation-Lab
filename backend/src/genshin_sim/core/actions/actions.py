"""通用定时动作与切人动作实现。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from genshin_sim.core.actions.enums import (
    ActionInterpretationTrigger,
    ActionLifecycleDirective,
)
from genshin_sim.core.actions.helpers import _validate_non_empty_text
from genshin_sim.core.actions.models import (
    ActionAdmissionPolicy,
    ActionExecutionContext,
    ActionExecutionResult,
    ActionImpactPoint,
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterruptPolicy,
    ActionOwnerRef,
    ControlActionRequest,
    InputSessionView,
    PreparedAction,
    TargetingSpec,
)
from genshin_sim.core.actions.protocols import ActiveActionLinkPort
from genshin_sim.core.events import EventType, GameEvent, TeamSwitchedPayload
from genshin_sim.core.movement import MovementFact, MovementRuntime
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.cooldown import (
    CooldownDurationTerm,
    CooldownDurationTermPort,
    CooldownKey,
    CooldownRuntime,
    CooldownSubjectRef,
    StartCooldownRequest,
)

if TYPE_CHECKING:
    pass


TEAM_SWITCH_ACTION_KEY = "team.switch"
TEAM_SWITCH_TARGET_SLOT_PARAM = "target_slot"
# 切人的中断身份：既作为 ``PreparedAction.interrupt_kind``，也作为切人打断旧角色
# 动作实例与旧角色输入会话的统一原因文案。
TEAM_SWITCH_INTERRUPT_KIND = "character_switch"


@dataclass(frozen=True, slots=True)
class TimedImpactAction:
    """通用定时动作：注册期固定的时长与影响帧时间线。"""

    action_key: str
    duration_frames: int = 1
    impact_keys: tuple[str, ...] = ()
    impact_frame_offsets: Mapping[str, int] = field(default_factory=dict)
    impact_targeting: Mapping[str, TargetingSpec | None] = field(default_factory=dict)
    create_default_impact_point: bool = False
    targeting: TargetingSpec | None = None
    cooldown_start_frame: int | None = None
    cooldown_ability_key: str | None = None
    cooldown_duration_terms: tuple[CooldownDurationTerm, ...] = ()
    cooldown_duration_term_port: CooldownDurationTermPort | None = None
    admission_policy: ActionAdmissionPolicy = field(default_factory=ActionAdmissionPolicy)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.action_key, "action_key")
        if self.duration_frames <= 0:
            msg = "duration_frames 必须是正整数"
            raise ValueError(msg)
        object.__setattr__(self, "impact_keys", tuple(self.impact_keys))
        object.__setattr__(self, "impact_frame_offsets", dict(self.impact_frame_offsets))
        impact_targeting = dict(self.impact_targeting)
        for impact_key, targeting in impact_targeting.items():
            if not isinstance(impact_key, str) or not impact_key.strip():
                msg = "impact_targeting 键必须是非空字符串"
                raise ValueError(msg)
            if targeting is not None and not isinstance(targeting, TargetingSpec):
                msg = "impact_targeting 值必须是 TargetingSpec 或 None"
                raise ValueError(msg)
        object.__setattr__(self, "impact_targeting", impact_targeting)
        if (self.cooldown_start_frame is None) != (self.cooldown_ability_key is None):
            msg = "cooldown_start_frame 与 cooldown_ability_key 必须同时提供或同时省略"
            raise ValueError(msg)
        if self.cooldown_start_frame is not None and self.cooldown_start_frame < 0:
            msg = "cooldown_start_frame 不能为负数"
            raise ValueError(msg)
        if self.cooldown_ability_key is not None:
            _validate_non_empty_text(self.cooldown_ability_key, "cooldown_ability_key")
        terms = tuple(self.cooldown_duration_terms)
        if any(not isinstance(term, CooldownDurationTerm) for term in terms):
            msg = "cooldown_duration_terms 成员必须是 CooldownDurationTerm"
            raise ValueError(msg)
        object.__setattr__(self, "cooldown_duration_terms", terms)

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        state: dict[str, object] = {"params": dict(params)}
        if self.cooldown_start_frame is not None:
            state["cooldown_started"] = False
        return state

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        impact_keys = self.impact_keys
        if not impact_keys and self.create_default_impact_point:
            impact_keys = (self.action_key,)
        impacts = tuple(
            ActionImpactPoint(
                impact_point_id=f"action:{context.instance_id}:{impact_key}",
                source_instance_id=context.instance_id,
                owner=context.owner,
                action_key=self.action_key,
                impact_key=impact_key,
                scheduled_frame=(
                    context.start_frame + self.impact_frame_offsets.get(impact_key, 0)
                ),
                targeting=self.impact_targeting.get(impact_key, self.targeting),
                params=context.params,
            )
            for impact_key in impact_keys
        )
        return ActionExecutionResult(emitted_impacts=impacts)

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.elapsed_frames >= self.duration_frames:
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        if self.cooldown_start_frame is None:
            return ActionExecutionResult()
        state = dict(context.action_state)
        if state.get("cooldown_started") is True:
            return ActionExecutionResult()
        if context.elapsed_frames < self.cooldown_start_frame:
            return ActionExecutionResult()
        self._start_cooldown(context)
        state["cooldown_started"] = True
        return ActionExecutionResult(next_state=state)

    def _start_cooldown(self, context: ActionExecutionContext) -> None:
        if context.owner.slot is None:
            msg = f"动作 {self.action_key} 开始冷却需要角色归属槽位"
            raise RuntimeError(msg)
        assert self.cooldown_start_frame is not None
        assert self.cooldown_ability_key is not None
        runtime = context.simulation_context.get_system(CooldownRuntime)
        if not isinstance(runtime, CooldownRuntime):
            msg = f"缺少 CooldownRuntime，无法开始 {self.action_key} 冷却"
            raise RuntimeError(msg)
        frame = context.start_frame + self.cooldown_start_frame
        key = CooldownKey(
            CooldownSubjectRef.character(f"character:slot_{context.owner.slot}"),
            self.cooldown_ability_key,
        )
        duration_terms = self.cooldown_duration_terms
        if self.cooldown_duration_term_port is not None:
            duration_terms = (*duration_terms, *self.cooldown_duration_term_port.terms_for(key))
        request = StartCooldownRequest(
            request_id=(f"cooldown:{context.instance_id}:{self.cooldown_ability_key}:{frame}"),
            key=key,
            frame=frame,
            source_ref=f"action:{self.action_key}",
            duration_terms=duration_terms,
        )
        runtime.start(request)

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        del context
        return ActionExecutionResult(records=({"type": "action_canceled", "reason": reason},))

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        del context
        if command.command == "finish":
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        if command.command == "cancel":
            return ActionExecutionResult(
                lifecycle_directive=ActionLifecycleDirective.CANCEL,
                cancel_reason="command_cancel",
            )
        return ActionExecutionResult()


@dataclass(frozen=True, slots=True)
class FallPlungeAction:
    """事件驱动下落动作：按位移设施事实在碰撞/落地帧当场发出影响点。

    动作本身不写位移，也不预排影响帧；垂直运动由 ``core/movement`` 每帧
    推进。``on_update`` 读取该设施当前帧事实：``COLLIDED`` 发出下坠碰撞
    影响点（每个下落过程一次），``LANDED`` 发出落地影响点并结束动作。
    """

    action_key: str
    collision_impact_key: str
    landing_impact_key: str
    movement_entity_id: str = ACTIVE_CHARACTER_ENTITY_ID
    admission_policy: ActionAdmissionPolicy = field(default_factory=ActionAdmissionPolicy)

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        return {"params": dict(params), "collision_emitted": False}

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        movement = context.simulation_context.get_system(MovementRuntime)
        facts = (
            movement.facts_for(self.movement_entity_id, context.frame)
            if isinstance(movement, MovementRuntime)
            else frozenset()
        )
        collision_emitted = context.action_state.get("collision_emitted") is True
        emitted: list[ActionImpactPoint] = []
        if not collision_emitted and MovementFact.COLLIDED in facts:
            collision_emitted = True
            emitted.append(self._impact_point(context, self.collision_impact_key))
        if MovementFact.LANDED in facts:
            emitted.append(self._impact_point(context, self.landing_impact_key))
            return ActionExecutionResult(
                next_state={
                    "params": dict(context.params),
                    "collision_emitted": collision_emitted,
                },
                emitted_impacts=tuple(emitted),
                lifecycle_directive=ActionLifecycleDirective.FINISH,
            )
        if collision_emitted:
            return ActionExecutionResult(
                next_state={
                    "params": dict(context.params),
                    "collision_emitted": True,
                },
                emitted_impacts=tuple(emitted),
            )
        return ActionExecutionResult(emitted_impacts=tuple(emitted))

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        del context
        if command.command == "finish":
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        if command.command == "cancel":
            return ActionExecutionResult(
                lifecycle_directive=ActionLifecycleDirective.CANCEL,
                cancel_reason="command_cancel",
            )
        return ActionExecutionResult()

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        del context
        return ActionExecutionResult(records=({"type": "action_canceled", "reason": reason},))

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()

    def _impact_point(
        self,
        context: ActionExecutionContext,
        impact_key: str,
    ) -> ActionImpactPoint:
        return ActionImpactPoint(
            impact_point_id=f"action:{context.instance_id}:{impact_key}",
            source_instance_id=context.instance_id,
            owner=context.owner,
            action_key=self.action_key,
            impact_key=impact_key,
            scheduled_frame=context.frame,
            params=context.params,
        )


@dataclass(frozen=True, slots=True)
class TeamSwitchAction:
    """队伍切人动作实现。

    准入策略声明 ``cancel_policy=queue_new``：切人锁冲突且不可中断时把新请求
    挂起排队（连按两次切人键，第二次在第一次完成后自动起手）。
    """

    action_key: str = TEAM_SWITCH_ACTION_KEY
    duration_frames: int = 1
    admission_policy: ActionAdmissionPolicy = field(
        default_factory=lambda: ActionAdmissionPolicy(
            required_locks=("team.control",),
            interrupt_policy=ActionInterruptPolicy(cancel_policy="queue_new"),
        )
    )

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        target_slot = params.get(TEAM_SWITCH_TARGET_SLOT_PARAM)
        if isinstance(target_slot, bool) or not isinstance(target_slot, int):
            msg = f"{TEAM_SWITCH_ACTION_KEY}.params.{TEAM_SWITCH_TARGET_SLOT_PARAM} 必须是整数"
            raise ValueError(msg)
        return {TEAM_SWITCH_TARGET_SLOT_PARAM: target_slot}

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.simulation_context.space_runtime is None:
            return ActionExecutionResult(
                lifecycle_directive=ActionLifecycleDirective.CANCEL,
                cancel_reason="missing_space_runtime",
            )
        space_runtime = context.simulation_context.space_runtime
        target_slot = context.action_state[TEAM_SWITCH_TARGET_SLOT_PARAM]
        if not isinstance(target_slot, int):
            msg = f"{TEAM_SWITCH_ACTION_KEY}.state.{TEAM_SWITCH_TARGET_SLOT_PARAM} 必须是整数"
            raise ValueError(msg)
        result = space_runtime.team_state.switch_to(target_slot, context.frame)
        if result.accepted and space_runtime.get_entity("player:active") is not None:
            space_runtime.update_active_character_slot(result.active_slot)
        context.simulation_context.events.publish(
            GameEvent(
                EventType.TEAM_SWITCHED,
                frame=context.frame,
                source=self,
                payload=TeamSwitchedPayload(
                    requested_slot=result.requested_slot,
                    previous_slot=result.previous_slot,
                    active_slot=result.active_slot,
                    accepted=result.accepted,
                    status=result.status.value,
                ),
            )
        )
        return ActionExecutionResult(
            records=(
                {
                    "type": "team_switch",
                    "status": result.status.value,
                    "accepted": result.accepted,
                    "requested_slot": result.requested_slot,
                    "previous_slot": result.previous_slot,
                    "active_slot": result.active_slot,
                },
            )
        )

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        if context.elapsed_frames >= self.duration_frames:
            return ActionExecutionResult(lifecycle_directive=ActionLifecycleDirective.FINISH)
        return ActionExecutionResult()

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        del context, command
        return ActionExecutionResult()

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        del context
        return ActionExecutionResult(records=({"type": "team_switch_canceled", "reason": reason},))

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        del context
        return ActionExecutionResult()


class TeamActionInterpreter:
    """队伍级数字键解释器。

    切人遵循当前场上角色「在进行的动作」的衔接数据，与其它输入同一原则：

    - 没有在进行的动作、或该动作未声明可切人帧：立即可切；
    - 已到可切人帧：起手切人；
    - 未到可切人帧：``defer``（动作请求已产生但时间结构条件未满足），由管理器
      缓冲逐帧重评，到帧自动起手，语义与角色动作的衔接缓冲一致。
    """

    supported_action_keys = (TEAM_SWITCH_ACTION_KEY,)

    def __init__(self, action_link_port: ActiveActionLinkPort | None = None) -> None:
        # 只读衔接端口未接线时不限制切换（既有单元测试只构造队伍解释器；真实
        # 装配必须提供端口，见 runtime_assembler）。
        self._action_link_port = action_link_port

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        if session.trigger is not ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        target_slot = _switch_slot_from_key(session.key)
        if target_slot is None:
            return ActionInterpretationResult.reject(f"队伍解释器不支持输入：{session.key}")
        pending_reason = self._pending_link_reason(context, session.current_frame)
        if pending_reason is not None:
            return ActionInterpretationResult.defer(pending_reason)
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=TEAM_SWITCH_ACTION_KEY,
                owner=ActionOwnerRef.team(),
                requested_start_frame=session.current_frame,
                params={TEAM_SWITCH_TARGET_SLOT_PARAM: target_slot},
                source_session_id=session.session_id,
                interrupt_kind=TEAM_SWITCH_INTERRUPT_KIND,
            )
        )

    def _pending_link_reason(
        self,
        context: ActionInterpretationContext,
        frame: int,
    ) -> str | None:
        """未到可切人帧时返回推迟原因；可以切换时返回 ``None``。

        只读当前场上角色的在进行的动作衔接视图，不读冷却 / 能量等资源条件：
        资源类条件不因当前动作结束而满足，故不进入缓冲。
        """

        port = self._action_link_port
        if port is None:
            return None
        view = port.read(context.simulation)
        earliest = view.earliest_switch_frame
        if earliest is None or frame >= earliest:
            return None
        return f"当前动作 {view.action_key} 最早可在第 {earliest} 帧切换"


def _switch_slot_from_key(key: str) -> int | None:
    if key not in {"keyboard.1", "keyboard.2", "keyboard.3", "keyboard.4"}:
        return None
    return int(key.removeprefix("keyboard."))
