from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.cooldown.models import CooldownRecord


@dataclass(frozen=True, slots=True)
class CooldownRecordSnapshot:
    subject_type: str
    subject_id: str
    ability_key: str
    ability_kind: str
    max_charges: int
    available_charges: int
    active_started_frame: int | None
    active_ready_frame: int | None
    interval_frames: int | None
    queued_recoveries: int
    chain_id: str | None
    revision: int

    @classmethod
    def from_record(cls, record: CooldownRecord) -> CooldownRecordSnapshot:
        active = record.active_recovery
        return cls(
            subject_type=record.key.subject.subject_type.value,
            subject_id=record.key.subject.subject_id,
            ability_key=record.key.ability_key,
            ability_kind=record.ability_kind.value,
            max_charges=record.max_charges,
            available_charges=record.available_charges,
            active_started_frame=None if active is None else active.started_frame,
            active_ready_frame=None if active is None else active.ready_frame,
            interval_frames=None if active is None else active.interval_frames,
            queued_recoveries=record.queued_recoveries,
            chain_id=None if active is None else active.chain_id,
            revision=record.revision,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "ability_key": self.ability_key,
            "ability_kind": self.ability_kind,
            "max_charges": self.max_charges,
            "available_charges": self.available_charges,
            "active_started_frame": self.active_started_frame,
            "active_ready_frame": self.active_ready_frame,
            "interval_frames": self.interval_frames,
            "queued_recoveries": self.queued_recoveries,
            "chain_id": self.chain_id,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class CooldownSnapshot:
    schema_version: int
    frame: int
    normalized_through_frame: int
    records: tuple[CooldownRecordSnapshot, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "frame": self.frame,
            "normalized_through_frame": self.normalized_through_frame,
            "records": tuple(item.to_dict() for item in self.records),
        }
