"""已展开批次的应用层模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from genshin_sim.application.input import SimulationInput

type BatchInput = SimulationInput | Mapping[str, Any]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class BatchMemberState(StrEnum):
    """批次成员对外展示的状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchRunState(StrEnum):
    """由成员状态派生的批次状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SingleBatchResult:
    """单成员批的同步等待结果；只保留结果身份与错误，不暴露 job。"""

    session_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class BatchMember:
    """一个已展开、拥有稳定 ``item_id`` 的仿真输入成员。"""

    item_id: str
    input: BatchInput


@dataclass(frozen=True, slots=True)
class BatchDiagnostic:
    """面向输入校验调用方的结构化诊断。"""

    code: str
    message: str
    item_id: str | None = None
    path: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "item_id": self.item_id,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class BatchMemberValidation:
    """单个批次成员的校验结果。"""

    item_id: str
    ok: bool
    details: tuple[BatchDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "ok": self.ok,
            "details": [detail.to_dict() for detail in self.details],
        }


@dataclass(frozen=True, slots=True)
class BatchValidationResult:
    """整批输入校验结果。"""

    ok: bool
    members: tuple[BatchMemberValidation, ...]
    normalized_members: tuple[BatchMember, ...] = field(
        default=(),
        repr=False,
        compare=False,
    )

    @property
    def diagnostics(self) -> tuple[BatchDiagnostic, ...]:
        return tuple(detail for member in self.members for detail in member.details)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "members": [member.to_dict() for member in self.members],
        }


@dataclass(frozen=True, slots=True)
class BatchMemberStatus:
    """批次状态视图中的成员记录。"""

    item_id: str
    state: BatchMemberState
    session_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "state": self.state.value,
            "session_id": self.session_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True, slots=True)
class BatchRunStatus:
    """批次状态视图；成员顺序与提交顺序保持一致。"""

    run_id: str
    name: str
    state: BatchRunState
    concurrency: int
    cancel_requested: bool
    member_count: int
    members: tuple[BatchMemberStatus, ...]

    @property
    def terminal(self) -> bool:
        return self.state in {
            BatchRunState.COMPLETED,
            BatchRunState.PARTIAL,
            BatchRunState.FAILED,
            BatchRunState.CANCELLED,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "state": self.state.value,
            "concurrency": self.concurrency,
            "cancel_requested": self.cancel_requested,
            "member_count": self.member_count,
            "members": [member.to_dict() for member in self.members],
        }


# 这些别名让应用代码和 HTTP DTO 可以复用同一套模型词汇。
BatchInputDiagnostic = BatchDiagnostic
BatchMemberValidationResult = BatchMemberValidation
BatchValidationReport = BatchValidationResult
BatchMemberView = BatchMemberStatus
BatchRunView = BatchRunStatus


__all__ = [
    "BatchDiagnostic",
    "BatchInput",
    "BatchInputDiagnostic",
    "BatchMember",
    "BatchMemberState",
    "BatchMemberStatus",
    "BatchMemberValidation",
    "BatchMemberValidationResult",
    "BatchMemberView",
    "BatchRunState",
    "BatchRunStatus",
    "BatchRunView",
    "BatchValidationReport",
    "BatchValidationResult",
]
