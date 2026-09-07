"""已展开批次的提交、调度、取消和状态派生。"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import RLock
from time import monotonic, sleep
from typing import Protocol, cast

from genshin_sim.application.batch.errors import BatchRunNotFoundError, BatchValidationError
from genshin_sim.application.batch.models import (
    BatchMember,
    BatchMemberState,
    BatchMemberStatus,
    BatchRunState,
    BatchRunStatus,
    BatchValidationResult,
    SingleBatchResult,
)
from genshin_sim.application.errors_kinds import scheduling_error_code
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.jobs import (
    SimulationJobRunner,
    SimulationJobState,
    SimulationJobStatus,
)
from genshin_sim.application.services.input_validation import BatchInputValidationService

MAX_BATCH_MEMBERS = 200
MIN_BATCH_CONCURRENCY = 1
MAX_BATCH_CONCURRENCY = 16
DEFAULT_BATCH_CONCURRENCY = min(4, os.cpu_count() or 1)
TERMINAL_BATCH_RETENTION_SECONDS = 60.0

_TERMINAL_MEMBER_STATES = {
    BatchMemberState.COMPLETED,
    BatchMemberState.FAILED,
    BatchMemberState.CANCELLED,
}
_ACTIVE_MEMBER_STATES = {
    BatchMemberState.QUEUED,
    BatchMemberState.RUNNING,
}


class BatchMemberValidator(Protocol):
    """批次成员校验器的窄协议。"""

    def validate_members(self, members: Sequence[BatchMember]) -> BatchValidationResult: ...


@dataclass(slots=True)
class _BatchMemberRecord:
    member: BatchMember
    created_at: str
    state: BatchMemberState = BatchMemberState.QUEUED
    job_id: str | None = None
    session_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    cancel_after_completion: bool = False


@dataclass(slots=True)
class _BatchRecord:
    run_id: str
    name: str
    concurrency: int
    members: list[_BatchMemberRecord]
    cancel_requested: bool = False
    terminal_at: float | None = None


class BatchRunService:
    """接收已展开成员并复用单任务 runner 执行批次。

    该服务不解析工作流图，也不拥有仿真运行态；它只保存批次与单任务的
    映射，并在查询时派生批次状态。
    """

    def __init__(
        self,
        runner: SimulationJobRunner,
        *,
        validator: BatchMemberValidator | None = None,
        max_members: int = MAX_BATCH_MEMBERS,
        default_concurrency: int = DEFAULT_BATCH_CONCURRENCY,
        run_id_factory: Callable[[], str] | None = None,
        now_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_members <= 0:
            raise ValueError("max_members 必须大于 0")
        self.runner = runner
        # 默认校验器在缺少资产仓库时返回 VALIDATION_UNAVAILABLE，
        # 避免结构校验通过后把依赖错误延迟到仿真运行期。
        self.validator = validator or BatchInputValidationService()
        self.max_members = max_members
        self.default_concurrency = self._validate_concurrency(default_concurrency)
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)
        self._now_factory = now_factory or _utc_now
        self._monotonic_factory = monotonic
        self._runs: dict[str, _BatchRecord] = {}
        self._lock = RLock()

        limit_setter = getattr(self.runner, "set_concurrency_limit", None)
        if limit_setter is not None:
            limit_setter(self.default_concurrency)

    def validate_members(self, members: Sequence[BatchMember]) -> BatchValidationResult:
        """校验已展开成员，不创建任务。"""

        with self._lock:
            self._expire_terminal_runs()
            normalized_members = self._normalize_request_members(members)
            return self.validator.validate_members(normalized_members)

    def submit(
        self,
        members: Sequence[BatchMember],
        *,
        name: str = "",
        concurrency: int | None = None,
    ) -> BatchRunStatus:
        """校验并提交一个批次。"""

        with self._lock:
            self._expire_terminal_runs()
            request_members = self._normalize_request_members(members)
            report = self.validator.validate_members(request_members)
            if not report.ok:
                raise BatchValidationError(
                    "validation_failed",
                    "批次输入校验失败",
                    tuple(detail.to_dict() for detail in report.diagnostics),
                )

            normalized_members = report.normalized_members or tuple(
                _normalize_member(member) for member in request_members
            )
            resolved_concurrency = self._resolve_concurrency(concurrency)
            run_id = self._new_run_id()
            record = _BatchRecord(
                run_id=run_id,
                name=name,
                concurrency=resolved_concurrency,
                members=[
                    _BatchMemberRecord(member=member, created_at=self._now_factory())
                    for member in normalized_members
                ],
            )
            self._runs[run_id] = record
            self._pump(record)
            return self._view(record)

    def get(self, run_id: str) -> BatchRunStatus:
        """查询批次并推进可见状态。"""

        with self._lock:
            self._expire_terminal_runs()
            record = self._require_run(run_id)
            self._pump(record)
            return self._view(record)

    def cancel(self, run_id: str) -> BatchRunStatus:
        """请求整批取消；运行中的单任务由 runner 自己完成收尾。"""

        with self._lock:
            self._expire_terminal_runs()
            record = self._require_run(run_id)
            self._refresh_members(record)
            if self._view(record).terminal:
                return self._view(record)

            record.cancel_requested = True
            for member in record.members:
                if member.state in _TERMINAL_MEMBER_STATES:
                    continue
                if member.job_id is None:
                    member.state = BatchMemberState.CANCELLED
                    member.error_code = None
                    member.finished_at = self._now_factory()
                    continue

                member.cancel_after_completion = True
                try:
                    status = self.runner.cancel(member.job_id)
                except Exception as exc:
                    member.state = BatchMemberState.STOPPING
                    member.error_code = scheduling_error_code(exc)
                    member.error_message = str(exc) or exc.__class__.__name__
                    continue
                self._apply_job_status(member, status)

            self._refresh_members(record)
            self._mark_terminal_if_done(record)
            return self._view(record)

    def run_single_and_wait(
        self,
        member: BatchMember,
        *,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float | None = None,
    ) -> SingleBatchResult:
        """提交单成员批并同步等待终态；这是 CLI 的单任务入口。"""

        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds 不能为负数")
        if timeout_seconds is not None and timeout_seconds < 0:
            raise ValueError("timeout_seconds 不能为负数")
        status = self.submit((member,), concurrency=1)
        deadline = None if timeout_seconds is None else monotonic() + timeout_seconds
        while True:
            status = self.get(status.run_id)
            if status.terminal:
                break
            if deadline is not None and monotonic() >= deadline:
                raise BatchValidationError("timeout", "等待批次结果超时")
            sleep(poll_interval_seconds)
        member_status = status.members[0]
        return SingleBatchResult(
            session_id=member_status.session_id,
            error_code=member_status.error_code,
            error_message=member_status.error_message,
        )

    # 命名别名方便应用适配层调用，同时保持服务核心词汇简短。
    submit_batch = submit
    get_status = get
    cancel_batch = cancel

    def _normalize_request_members(
        self,
        members: Sequence[BatchMember],
    ) -> tuple[BatchMember, ...]:
        try:
            request_members = tuple(members)
        except TypeError as exc:
            raise BatchValidationError(
                "invalid_members",
                "members 必须是有序成员列表",
            ) from exc

        if not request_members:
            raise BatchValidationError("batch_empty", "批次至少需要一个成员")
        if len(request_members) > self.max_members:
            raise BatchValidationError(
                "batch_too_large",
                f"批次成员数不能超过 {self.max_members}",
                ({"max_members": self.max_members},),
            )

        seen: set[str] = set()
        for member in request_members:
            if not isinstance(member, BatchMember):
                raise BatchValidationError(
                    "invalid_member",
                    "批次成员必须是 BatchMember",
                )
            if not isinstance(member.item_id, str) or not member.item_id.strip():
                raise BatchValidationError(
                    "invalid_item_id",
                    "item_id 必须是非空字符串",
                )
            if member.item_id in seen:
                raise BatchValidationError(
                    "duplicate_item_id",
                    f"批次内 item_id 不能重复：{member.item_id}",
                    ({"item_id": member.item_id},),
                )
            seen.add(member.item_id)
        return request_members

    def _resolve_concurrency(self, value: int | None) -> int:
        return self.default_concurrency if value is None else self._validate_concurrency(value)

    @staticmethod
    def _validate_concurrency(value: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not MIN_BATCH_CONCURRENCY <= value <= MAX_BATCH_CONCURRENCY
        ):
            raise BatchValidationError(
                "invalid_concurrency",
                f"concurrency 必须在 {MIN_BATCH_CONCURRENCY} 到 {MAX_BATCH_CONCURRENCY} 之间",
            )
        return value

    def _new_run_id(self) -> str:
        run_id = self._run_id_factory()
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id_factory 必须返回非空字符串")
        if run_id in self._runs:
            raise ValueError(f"批次 run_id 已存在：{run_id}")
        return run_id

    def _pump(self, record: _BatchRecord) -> None:
        self._refresh_members(record)
        self._mark_terminal_if_done(record)
        if record.cancel_requested:
            return

        while True:
            self._refresh_members(record)
            active_count = sum(
                member.state in _ACTIVE_MEMBER_STATES
                for member in record.members
                if member.job_id is not None
            )
            next_member = next(
                (
                    member
                    for member in record.members
                    if member.job_id is None and member.state is BatchMemberState.QUEUED
                ),
                None,
            )
            if next_member is None or active_count >= record.concurrency:
                break
            self._submit_member(next_member)

        self._refresh_members(record)
        self._mark_terminal_if_done(record)

    def _submit_member(self, member: _BatchMemberRecord) -> None:
        config = cast(SimulationInput, member.member.input)
        try:
            member.job_id = self.runner.submit_input(config)
        except Exception as exc:
            self._mark_failed(member, exc)

    def _refresh_members(self, record: _BatchRecord) -> None:
        for member in record.members:
            if member.job_id is None or member.state in _TERMINAL_MEMBER_STATES:
                continue
            try:
                status = self.runner.get_status(member.job_id)
            except Exception as exc:
                if member.cancel_after_completion:
                    self._mark_cancelled(member)
                else:
                    self._mark_failed(member, exc)
                continue
            self._apply_job_status(member, status)

    def _apply_job_status(
        self,
        member: _BatchMemberRecord,
        status: SimulationJobStatus,
    ) -> None:
        member.started_at = status.started_at
        member.finished_at = status.finished_at
        if member.cancel_after_completion:
            if status.state in {
                SimulationJobState.QUEUED,
                SimulationJobState.RUNNING,
            }:
                member.state = BatchMemberState.STOPPING
                member.session_id = None
            else:
                self._mark_cancelled(member, finished_at=status.finished_at)
            return

        member.state = BatchMemberState(status.state.value)
        member.session_id = status.session_id
        member.error_code = status.error_code
        member.error_message = status.error_message

    def _mark_failed(self, member: _BatchMemberRecord, exc: BaseException) -> None:
        member.state = BatchMemberState.FAILED
        member.error_code = scheduling_error_code(exc)
        member.error_message = str(exc) or exc.__class__.__name__
        member.session_id = None
        member.finished_at = member.finished_at or self._now_factory()

    def _mark_cancelled(
        self,
        member: _BatchMemberRecord,
        *,
        finished_at: str | None = None,
    ) -> None:
        member.state = BatchMemberState.CANCELLED
        member.session_id = None
        member.error_code = None
        member.error_message = None
        member.finished_at = finished_at or member.finished_at or self._now_factory()

    def _view(self, record: _BatchRecord) -> BatchRunStatus:
        members = tuple(
            BatchMemberStatus(
                item_id=member.member.item_id,
                state=member.state,
                session_id=member.session_id,
                error_code=member.error_code,
                error_message=member.error_message,
                created_at=member.created_at,
                started_at=member.started_at,
                finished_at=member.finished_at,
            )
            for member in record.members
        )
        return BatchRunStatus(
            run_id=record.run_id,
            name=record.name,
            state=self._derive_state(record.members, record.cancel_requested),
            concurrency=record.concurrency,
            cancel_requested=record.cancel_requested,
            member_count=len(members),
            members=members,
        )

    def _mark_terminal_if_done(self, record: _BatchRecord) -> None:
        if record.terminal_at is not None:
            return
        if self._view(record).terminal:
            record.terminal_at = self._monotonic_factory() + TERMINAL_BATCH_RETENTION_SECONDS

    def _expire_terminal_runs(self) -> None:
        now = self._monotonic_factory()
        expired = [
            run_id
            for run_id, record in self._runs.items()
            if record.terminal_at is not None and record.terminal_at <= now
        ]
        for run_id in expired:
            del self._runs[run_id]

    @staticmethod
    def _derive_state(
        members: Sequence[_BatchMemberRecord],
        cancel_requested: bool,
    ) -> BatchRunState:
        states = tuple(member.state for member in members)
        if cancel_requested:
            return (
                BatchRunState.CANCELLED
                if all(state in _TERMINAL_MEMBER_STATES for state in states)
                else BatchRunState.STOPPING
            )
        if all(state is BatchMemberState.COMPLETED for state in states):
            return BatchRunState.COMPLETED
        if all(state in _TERMINAL_MEMBER_STATES for state in states):
            if all(state is BatchMemberState.FAILED for state in states):
                return BatchRunState.FAILED
            return BatchRunState.PARTIAL
        if all(state is BatchMemberState.QUEUED for state in states):
            return BatchRunState.QUEUED
        return BatchRunState.RUNNING

    def _require_run(self, run_id: str) -> _BatchRecord:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise BatchRunNotFoundError(run_id) from exc


def _normalize_member(member: BatchMember) -> BatchMember:
    if isinstance(member.input, SimulationInput):
        return member
    return BatchMember(
        item_id=member.item_id,
        input=SimulationInput.from_mapping(member.input),
    )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


__all__ = [
    "BatchRunService",
    "DEFAULT_BATCH_CONCURRENCY",
    "MAX_BATCH_CONCURRENCY",
    "MAX_BATCH_MEMBERS",
    "MIN_BATCH_CONCURRENCY",
]
