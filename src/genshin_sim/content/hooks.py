"""内容事实订阅分发：消费已发布事实，产出下一轮统一意图。

``HookDispatcher`` 是内容层挂在 ``FACT_RESPONSE`` 阶段的运行时对象：
它只读取当前帧已发布事实的增量，按订阅与优先级调用 ``EventHook``，
把 ``HookResult`` 转为 impact / state_patch 意图入队，由下一轮结算消费。
hook 自身不能直接修改世界。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genshin_sim.content.models import EventHook, HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts.models import ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.team import TeamRuntimeState


class HookDispatcherError(Exception):
    """内容 hook 分发错误基类。"""


class HookSubscriptionError(HookDispatcherError, ValueError):
    """hook 订阅了不存在的事件类型。"""


class UnsupportedHookOutputError(HookDispatcherError, TypeError):
    """hook 产出了尚未接线的结果类型。"""


@dataclass(frozen=True, slots=True)
class HookContext:
    """传给 ``EventHook.handle`` 的只读求值上下文。"""

    frame: int
    round: int
    simulation: SimulationContext
    states: TeamRuntimeState | None

    def state(self, owner_ref: str) -> Mapping[str, JSONValue]:
        return self._state(owner_ref, state_key=None)

    def _state(
        self,
        owner_ref: str,
        state_key: str | None,
    ) -> Mapping[str, JSONValue]:
        if self.states is None:
            raise HookDispatcherError("当前仿真没有注册队伍运行态")
        for character in self.states.characters:
            if character.combat_entity_id != owner_ref:
                continue
            if state_key is None:
                if not character.content_states:
                    raise HookDispatcherError(f"宿主 {owner_ref!r} 没有内容状态")
                if len(character.content_states) > 1:
                    raise HookDispatcherError(
                        f"宿主 {owner_ref!r} 有多个内容状态段，必须指定 state_key"
                    )
                return next(iter(character.content_states.values())).values
            mount = character.content_states.get(state_key)
            if mount is None:
                raise HookDispatcherError(f"宿主 {owner_ref!r} 缺少内容状态段：{state_key}")
            return mount.values
        raise HookDispatcherError(f"缺少宿主角色运行态：{owner_ref}")


class HookDispatcher:
    """按事实订阅分发内容 hook，并把结果转为下一轮意图。"""

    def __init__(
        self,
        hooks: Sequence[EventHook],
        intent_queue: IntentQueue,
        *,
        team_state: TeamRuntimeState | None = None,
    ) -> None:
        self._queue = intent_queue
        self._team_state = team_state
        self._subscriptions: dict[EventType, list[EventHook]] = {}
        for hook in hooks:
            for name in hook.subscriptions:
                try:
                    event_type = EventType[name]
                except KeyError as exc:
                    raise HookSubscriptionError(
                        f"hook {hook.hook_key!r} 订阅了未知事件类型：{name}"
                    ) from exc
                self._subscriptions.setdefault(event_type, []).append(hook)
        for event_type in self._subscriptions:
            self._subscriptions[event_type].sort(key=lambda hook: (hook.priority, hook.hook_key))
        self._processed_frame = -1
        self._processed_count = 0

    @property
    def subscriptions(self) -> dict[EventType, tuple[str, ...]]:
        return {
            event_type: tuple(hook.hook_key for hook in hooks)
            for event_type, hooks in self._subscriptions.items()
        }

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        if self._processed_frame != frame:
            self._processed_frame = frame
            self._processed_count = 0
        events = context.events.frame_events
        for event_index in range(self._processed_count, len(events)):
            self._processed_count += 1
            event = events[event_index]
            hooks = self._subscriptions.get(event.event_type, ())
            if not hooks:
                continue
            hook_context = HookContext(
                frame=frame,
                round=context.settlement_round,
                simulation=context,
                states=self._team_state,
            )
            for hook in hooks:
                result = hook.handle(event, hook_context)
                self._enqueue_result(
                    hook,
                    result,
                    frame=frame,
                    round=context.settlement_round,
                    event_type=event.event_type,
                    event_index=event_index,
                )

    def is_idle(self) -> bool:
        return True

    def _enqueue_result(
        self,
        hook: EventHook,
        result: HookResult,
        *,
        frame: int,
        round: int,
        event_type: EventType,
        event_index: int,
    ) -> None:
        if result.modifier_commands:
            raise UnsupportedHookOutputError(
                f"hook {hook.hook_key!r} 产出了尚未接线的 modifier_commands"
            )
        next_round = round + 1
        for index, request in enumerate(result.impact_requests):
            if not isinstance(request, ImpactRequest):
                raise UnsupportedHookOutputError(
                    f"hook {hook.hook_key!r} 的 impact_requests 必须是 "
                    f"ImpactRequest，实际 {type(request).__name__}"
                )
            self._queue.enqueue(
                IntentEnvelope(
                    intent_id=(
                        f"hook:{hook.hook_key}:{frame}:{next_round}:"
                        f"{event_type.name}:{event_index}:impact:{index}"
                    ),
                    kind=IntentKind.IMPACT,
                    frame=frame,
                    phase=FramePhase.SETTLEMENT,
                    round=next_round,
                    source_ref=hook.hook_key,
                    payload=request,
                )
            )
        for index, patch in enumerate(result.state_patches):
            if not isinstance(patch, StatePatchRequest):
                raise UnsupportedHookOutputError(
                    f"hook {hook.hook_key!r} 的 state_patches 必须是 "
                    f"StatePatchRequest，实际 {type(patch).__name__}"
                )
            if patch.state_key != hook.state_key:
                raise HookDispatcherError(
                    f"hook {hook.hook_key!r} 不能写状态段 "
                    f"{patch.state_key!r}（自身归属 {hook.state_key!r}）"
                )
            if patch.owner_ref != hook.owner_ref:
                raise HookDispatcherError(
                    f"hook {hook.hook_key!r} 不能写宿主 "
                    f"{patch.owner_ref!r} 的状态（自身归属 {hook.owner_ref!r}）"
                )
            self._queue.enqueue(
                IntentEnvelope(
                    intent_id=(
                        f"hook:{hook.hook_key}:{frame}:{next_round}:"
                        f"{event_type.name}:{event_index}:state_patch:{index}"
                    ),
                    kind=IntentKind.STATE_PATCH,
                    frame=frame,
                    phase=FramePhase.SETTLEMENT,
                    round=next_round,
                    source_ref=hook.hook_key,
                    payload=patch,
                )
            )
