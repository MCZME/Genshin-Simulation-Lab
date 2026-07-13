from __future__ import annotations

from collections.abc import Callable

from genshin_sim.core.mechanics.commands import (
    CreateMechanicInstanceCommand,
    RefreshMechanicExpiryCommand,
    RemoveMechanicInstanceCommand,
)
from genshin_sim.core.mechanics.models import (
    MechanicInstance,
    MechanicRemovalRecord,
    validate_frame,
)
from genshin_sim.core.mechanics.store import MechanicInstanceStore
from genshin_sim.core.protocols import FrameUpdatable

MechanicRemovalSubscriber = Callable[[MechanicRemovalRecord], None]


class MechanicRuntime(FrameUpdatable):
    """机制实例身份、生命周期和过期提交入口。"""

    def __init__(self, instance_store: MechanicInstanceStore | None = None) -> None:
        self.instance_store = instance_store or MechanicInstanceStore()
        self._removal_subscribers: list[MechanicRemovalSubscriber] = []

    def subscribe_removal(self, subscriber: MechanicRemovalSubscriber) -> None:
        self._removal_subscribers.append(subscriber)

    def create_instance(
        self,
        command: CreateMechanicInstanceCommand,
    ) -> MechanicInstance:
        return self.instance_store.create(command)

    def refresh_expiry(
        self,
        command: RefreshMechanicExpiryCommand,
    ) -> MechanicInstance:
        return self.instance_store.refresh_expiry(command)

    def remove_instance(
        self,
        command: RemoveMechanicInstanceCommand,
    ) -> MechanicRemovalRecord:
        record = self.instance_store.remove(command)
        self._publish_removal(record)
        return record

    def expire_due(self, frame: int) -> tuple[MechanicRemovalRecord, ...]:
        validate_frame(frame)
        records = self.instance_store.expire_due(frame)
        for record in records:
            self._publish_removal(record)
        return records

    def update_frame(self, context, frame: int) -> None:
        del context
        self.expire_due(frame)

    def is_idle(self) -> bool:
        return True

    def _publish_removal(self, record: MechanicRemovalRecord) -> None:
        for subscriber in tuple(self._removal_subscribers):
            subscriber(record)
