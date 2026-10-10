from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.cooldown.models import ActiveRecovery, CooldownRecord


@dataclass(frozen=True, slots=True)
class CooldownRecoverySnapshot:
    started_frame: int
    ready_frame: int
    interval_frames: int
    chain_id: str
    start_source_ref: str

    @classmethod
    def from_recovery(cls, recovery: ActiveRecovery) -> CooldownRecoverySnapshot:
        return cls(
            started_frame=recovery.started_frame,
            ready_frame=recovery.ready_frame,
            interval_frames=recovery.interval_frames,
            chain_id=recovery.chain_id,
            start_source_ref=recovery.start_source_ref,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "started_frame": self.started_frame,
            "ready_frame": self.ready_frame,
            "interval_frames": self.interval_frames,
            "chain_id": self.chain_id,
            "start_source_ref": self.start_source_ref,
        }


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
    recovery_mode: str = "serial"
    recoveries: tuple[CooldownRecoverySnapshot, ...] = ()

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
            recovery_mode=record.recovery_mode.value,
            recoveries=tuple(
                CooldownRecoverySnapshot.from_recovery(item) for item in record.recoveries
            ),
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
            "recovery_mode": self.recovery_mode,
            "recoveries": [item.to_dict() for item in self.recoveries],
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
