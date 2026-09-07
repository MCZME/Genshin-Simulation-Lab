from __future__ import annotations

from genshin_sim.core.systems.energy.errors import (
    DuplicateEnergyRequestError,
    EnergyPickupNotFoundError,
    EnergyPlanConflictError,
)
from genshin_sim.core.systems.energy.models import EnergyPickupRecord


class EnergyTransitQueue:
    """按稳定顺序保存尚未结算的元素微粒和晶球。"""

    __slots__ = ("_records", "_request_ids", "_version")

    def __init__(self) -> None:
        self._records: dict[str, EnergyPickupRecord] = {}
        self._request_ids: set[str] = set()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    @property
    def records(self) -> tuple[EnergyPickupRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.sort_key))

    def is_empty(self) -> bool:
        return not self._records

    def enqueue(self, record: EnergyPickupRecord) -> None:
        if record.request_id in self._request_ids:
            raise DuplicateEnergyRequestError(f"元素能量 request 已提交：{record.request_id}")
        if record.pickup_id in self._records:
            raise DuplicateEnergyRequestError(f"元素能量 pickup 重复：{record.pickup_id}")
        self._records[record.pickup_id] = record
        self._request_ids.add(record.request_id)
        self._version += 1

    def due(self, frame: int) -> tuple[EnergyPickupRecord, ...]:
        return tuple(record for record in self.records if record.settle_frame <= frame)

    def assert_current(self, record: EnergyPickupRecord, expected_version: int) -> None:
        if self._version != expected_version:
            raise EnergyPlanConflictError(
                f"元素能量队列版本冲突：expected={expected_version}, actual={self._version}"
            )
        if self._records.get(record.pickup_id) != record:
            raise EnergyPickupNotFoundError(f"元素能量 pickup 不存在或已结算：{record.pickup_id}")

    def remove_prevalidated(self, record: EnergyPickupRecord) -> None:
        if record.pickup_id not in self._records:
            raise EnergyPickupNotFoundError(f"元素能量 pickup 不存在：{record.pickup_id}")
        del self._records[record.pickup_id]
        self._version += 1
