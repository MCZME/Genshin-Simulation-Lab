from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.mechanics.commands import (
    CreateMechanicInstanceCommand,
    RefreshMechanicExpiryCommand,
    RemoveMechanicInstanceCommand,
)
from genshin_sim.core.mechanics.errors import (
    MechanicInstanceNotFoundError,
    MechanicValidationError,
)
from genshin_sim.core.mechanics.models import (
    MechanicInstance,
    MechanicLifecycleState,
    MechanicRemovalRecord,
    validate_frame,
)


class MechanicInstanceStore:
    """保存机制实例身份和活动索引，不暴露任意组件写入口。"""

    __slots__ = ("_active_ids", "_instances", "_next_instance_id", "_version")

    def __init__(self, instances: Iterable[MechanicInstance] = ()) -> None:
        self._instances: dict[int, MechanicInstance] = {}
        self._active_ids: set[int] = set()
        self._next_instance_id = 1
        self._version = 0
        for instance in instances:
            if instance.instance_id in self._instances:
                raise MechanicValidationError(f"机制实例 id 重复：{instance.instance_id}")
            self._instances[instance.instance_id] = instance
            self._next_instance_id = max(self._next_instance_id, instance.instance_id + 1)
            if instance.lifecycle_state is MechanicLifecycleState.ACTIVE:
                self._active_ids.add(instance.instance_id)

    @property
    def version(self) -> int:
        return self._version

    def get(self, instance_id: int) -> MechanicInstance | None:
        return self._instances.get(instance_id)

    def require(self, instance_id: int) -> MechanicInstance:
        instance = self.get(instance_id)
        if instance is None:
            raise MechanicInstanceNotFoundError(f"机制实例不存在：{instance_id}")
        return instance

    def require_active(
        self,
        instance_id: int,
        *,
        frame: int | None = None,
    ) -> MechanicInstance:
        instance = self.require(instance_id)
        if instance.instance_id not in self._active_ids:
            raise MechanicInstanceNotFoundError(f"机制实例不处于活动状态：{instance_id}")
        if frame is not None and not instance.is_active_at(frame):
            raise MechanicInstanceNotFoundError(
                f"机制实例在 frame={frame} 不处于活动状态：{instance_id}"
            )
        return instance

    def create(self, command: CreateMechanicInstanceCommand) -> MechanicInstance:
        instance_id = self._next_instance_id
        self._next_instance_id += 1
        instance = MechanicInstance(
            instance_id=instance_id,
            capability_key=command.capability_key,
            mechanic_key=command.mechanic_key,
            handler_key=command.handler_key,
            owner_ref=command.owner_ref,
            created_frame=command.frame,
            expires_at_frame=command.expires_at_frame,
        )
        self._instances[instance_id] = instance
        self._active_ids.add(instance_id)
        self._version += 1
        return instance

    def refresh_expiry(self, command: RefreshMechanicExpiryCommand) -> MechanicInstance:
        instance = self.require_active(command.instance_id, frame=command.frame)
        refreshed = instance.with_expiry(command.expires_at_frame)
        self._instances[command.instance_id] = refreshed
        self._version += 1
        return refreshed

    def remove(
        self,
        command: RemoveMechanicInstanceCommand,
        *,
        state: MechanicLifecycleState = MechanicLifecycleState.REMOVED,
    ) -> MechanicRemovalRecord:
        instance = self.require_active(command.instance_id)
        if state is not MechanicLifecycleState.EXPIRED and not instance.is_active_at(command.frame):
            raise MechanicInstanceNotFoundError(
                f"机制实例在 frame={command.frame} 不处于活动状态：{command.instance_id}"
            )
        removed = instance.mark_removed(
            frame=command.frame,
            reason=command.reason,
            state=state,
        )
        self._instances[command.instance_id] = removed
        self._active_ids.remove(command.instance_id)
        self._version += 1
        return MechanicRemovalRecord(
            frame=command.frame,
            instance=removed,
            reason=command.reason,
        )

    def expire_due(self, frame: int) -> tuple[MechanicRemovalRecord, ...]:
        validate_frame(frame)
        due = tuple(
            sorted(
                (
                    self._instances[instance_id]
                    for instance_id in self._active_ids
                    if self._instances[instance_id].expires_at_frame <= frame
                ),
                key=lambda instance: instance.instance_id,
            )
        )
        records: list[MechanicRemovalRecord] = []
        for instance in due:
            command = RemoveMechanicInstanceCommand(
                instance_id=instance.instance_id,
                frame=frame,
                reason="expired",
            )
            records.append(self.remove(command, state=MechanicLifecycleState.EXPIRED))
        return tuple(records)

    def active_instances(
        self,
        *,
        frame: int | None = None,
        owner_ref: str | None = None,
        capability_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[MechanicInstance, ...]:
        if frame is not None:
            validate_frame(frame)
        instances = []
        for instance_id in self._active_ids:
            instance = self._instances[instance_id]
            if frame is not None and not instance.is_active_at(frame):
                continue
            if owner_ref is not None and instance.owner_ref != owner_ref:
                continue
            if capability_key is not None and instance.capability_key != capability_key:
                continue
            if mechanic_key is not None and instance.mechanic_key != mechanic_key:
                continue
            instances.append(instance)
        return tuple(sorted(instances, key=lambda instance: instance.instance_id))
