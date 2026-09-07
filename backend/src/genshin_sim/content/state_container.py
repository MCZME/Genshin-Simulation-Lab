"""内容状态挂载与 ``state_patch`` 意图处理。

M6 起，内容状态由 ``ContentStateMount`` 挂载在
``CharacterRuntimeState.content_states`` 下，解释器经 ``resolve_mount``
读取宿主挂载；写入唯一通道是 ``STATE_PATCH`` 意图，由
``StatePatchIntentHandler`` 按 (owner_ref, state_key) 落盘。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from genshin_sim.core.contracts.intents import IntentEnvelope
from genshin_sim.core.contracts.json import JSONValue, validate_json_compatible
from genshin_sim.core.entity_states.content_state import (
    ContentStateMount,
    ContentStateMountError,
)
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.events.payloads import ContentStateChangedPayload
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.team import TeamRuntimeState


class StateContainerError(Exception):
    """内容状态容器错误基类。"""


class StatePatchError(StateContainerError, ValueError):
    """状态补丁不合法。"""


class StateContainerNotFoundError(StateContainerError, LookupError):
    """请求的宿主或状态段不存在。"""


@dataclass(frozen=True, slots=True)
class StatePatchRequest:
    """一次 ``state_patch`` 意图的载荷。"""

    owner_ref: str
    fields: Mapping[str, JSONValue] = field(default_factory=dict)
    state_key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.owner_ref, str) or not self.owner_ref.strip():
            raise StatePatchError("owner_ref 必须是非空字符串")
        if not isinstance(self.state_key, str) or not self.state_key.strip():
            raise StatePatchError("state_key 必须是非空字符串")
        if not isinstance(self.fields, Mapping):
            raise StatePatchError("fields 必须是映射")
        for name in self.fields:
            if not isinstance(name, str) or not name.strip():
                raise StatePatchError("状态字段名必须是非空字符串")
        validate_json_compatible(dict(self.fields), path="fields")
        object.__setattr__(self, "fields", dict(self.fields))


def resolve_mount(
    context: SimulationContext,
    *,
    slot: int,
    state_key: str,
) -> ContentStateMount:
    """从宿主角色运行态解析内容状态挂载（解释器读取入口）。"""

    space_runtime = context.space_runtime
    if space_runtime is None:
        raise StateContainerNotFoundError("当前仿真没有注册战场空间运行态")
    character = space_runtime.team_state.get_character(slot)
    if character is None:
        raise StateContainerNotFoundError(f"缺少角色运行态：slot {slot}")
    mount = character.content_states.get(state_key)
    if mount is None:
        raise StateContainerNotFoundError(
            f"宿主 {character.combat_entity_id!r} 缺少内容状态段：{state_key}"
        )
    return mount


class StatePatchIntentHandler:
    """把 ``STATE_PATCH`` 意图按 (owner_ref, state_key) 写入宿主挂载。"""

    def __init__(self, team_state: TeamRuntimeState) -> None:
        self.team_state = team_state
        self._publishing_facts = False

    def handle(self, context: object, intent: IntentEnvelope) -> None:
        request = intent.payload
        if not isinstance(request, StatePatchRequest):
            raise TypeError(
                f"STATE_PATCH 意图载荷必须是 StatePatchRequest，实际 {type(request).__name__}"
            )
        if self._publishing_facts:
            raise StatePatchError("内容状态事实发布期间不允许再次写入内容状态")
        mount = self._find_mount(request.owner_ref, request.state_key)
        before = dict(mount.values)
        try:
            mount.apply_patch(request.fields)
        except ContentStateMountError as exc:
            raise StatePatchError(str(exc)) from exc
        if dict(mount.values) != before:
            self._publish_changed(context, request, mount, before)

    def _find_mount(self, owner_ref: str, state_key: str) -> ContentStateMount:
        for character in self.team_state.characters:
            if character.combat_entity_id == owner_ref:
                mount = character.content_states.get(state_key)
                if mount is None:
                    raise StateContainerNotFoundError(
                        f"宿主 {owner_ref!r} 缺少内容状态段：{state_key}"
                    )
                return mount
        raise StateContainerNotFoundError(f"缺少宿主状态容器：{owner_ref}")

    def _publish_changed(
        self,
        context: object,
        request: StatePatchRequest,
        mount: ContentStateMount,
        before: Mapping[str, object],
    ) -> None:
        events = getattr(context, "events", None)
        if events is None:
            return
        frame = getattr(context, "current_frame", 0)
        self._publishing_facts = True
        try:
            events.publish(
                GameEvent(
                    EventType.CONTENT_STATE_CHANGED,
                    frame,
                    ContentStateChangedPayload(
                        frame=frame,
                        owner_ref=request.owner_ref,
                        state_key=request.state_key,
                        fields=tuple(request.fields),
                        before=before,
                        after=dict(mount.values),
                    ),
                )
            )
        finally:
            self._publishing_facts = False
