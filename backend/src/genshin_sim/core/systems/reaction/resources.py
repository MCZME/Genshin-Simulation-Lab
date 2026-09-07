"""Reaction 领域的队伍级资源状态与无回调提交计划。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Protocol

LUNAR_BLOOM_DEW_CAPACITY = Fraction(3)
LUNAR_BLOOM_DEW_RECOVERY_DURATION_FRAMES = 150
LUNAR_BLOOM_DEW_RECOVERY_RATE_PER_FRAME = Fraction(1, 150)


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _frame(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, slots=True)
class LunarBloomDewState:
    """队伍草露的连续恢复状态；当前帧值由规范化游标确定。"""

    team_ref: str
    current_value: Fraction
    capacity: Fraction
    recovery_rate_per_frame: Fraction
    recovery_expires_at_frame: int
    normalized_through_frame: int
    resource_revision: int = 1

    def __post_init__(self) -> None:
        _text(self.team_ref, "team_ref")
        for value, name in (
            (self.current_value, "current_value"),
            (self.capacity, "capacity"),
            (self.recovery_rate_per_frame, "recovery_rate_per_frame"),
        ):
            if not isinstance(value, Fraction):
                raise ValueError(f"{name} 必须是 Fraction")
        if self.capacity <= 0:
            raise ValueError("capacity 必须为正数")
        if self.current_value < 0 or self.current_value > self.capacity:
            raise ValueError("current_value 必须位于 [0, capacity]")
        if self.recovery_rate_per_frame <= 0:
            raise ValueError("recovery_rate_per_frame 必须为正数")
        _frame(self.recovery_expires_at_frame, "recovery_expires_at_frame")
        _frame(self.normalized_through_frame, "normalized_through_frame")
        if self.recovery_expires_at_frame < self.normalized_through_frame:
            raise ValueError("recovery_expires_at_frame 不能早于 normalized_through_frame")
        if (
            isinstance(self.resource_revision, bool)
            or not isinstance(self.resource_revision, int)
            or self.resource_revision <= 0
        ):
            raise ValueError("resource_revision 必须是正整数")

    def normalized_at(self, frame: int) -> LunarBloomDewState:
        """返回指定帧的只读投影，不修改当前 Store。"""

        _frame(frame, "frame")
        if frame < self.normalized_through_frame:
            raise ValueError("草露规范化帧不能回退")
        if frame == self.normalized_through_frame:
            return self
        recovery_end = min(frame, self.recovery_expires_at_frame)
        recovered_frames = max(0, recovery_end - self.normalized_through_frame)
        next_value = min(
            self.capacity,
            self.current_value + self.recovery_rate_per_frame * recovered_frames,
        )
        return replace(
            self,
            current_value=next_value,
            normalized_through_frame=frame,
            resource_revision=self.resource_revision + int(next_value != self.current_value),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "team_ref": self.team_ref,
            "current_value": {
                "numerator": self.current_value.numerator,
                "denominator": self.current_value.denominator,
            },
            "capacity": {
                "numerator": self.capacity.numerator,
                "denominator": self.capacity.denominator,
            },
            "recovery_rate_per_frame": {
                "numerator": self.recovery_rate_per_frame.numerator,
                "denominator": self.recovery_rate_per_frame.denominator,
            },
            "recovery_expires_at_frame": self.recovery_expires_at_frame,
            "normalized_through_frame": self.normalized_through_frame,
            "resource_revision": self.resource_revision,
        }


@dataclass(frozen=True, slots=True)
class ReactionResourceMutationPlan:
    operation_id: str
    frame: int
    expected_store_version: int
    expected_records: tuple[LunarBloomDewState, ...]
    replacement_records: tuple[LunarBloomDewState, ...]
    removed_team_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.operation_id, "operation_id")
        _frame(self.frame, "frame")
        _frame(self.expected_store_version, "expected_store_version")
        expected = tuple(self.expected_records)
        replacements = tuple(self.replacement_records)
        removed = tuple(self.removed_team_refs)
        if any(not isinstance(item, LunarBloomDewState) for item in (*expected, *replacements)):
            raise ValueError("Reaction resource records 类型不受支持")
        if len({item.team_ref for item in expected}) != len(expected):
            raise ValueError("Reaction resource expected team_ref 不能重复")
        if len({item.team_ref for item in replacements}) != len(replacements):
            raise ValueError("Reaction resource replacement team_ref 不能重复")
        if any(not isinstance(item, str) or not item.strip() for item in removed):
            raise ValueError("removed_team_refs 必须是非空字符串序列")
        if set(removed) & {item.team_ref for item in replacements}:
            raise ValueError("Reaction resource replacement 与 remove 不能重叠")
        object.__setattr__(
            self,
            "expected_records",
            tuple(sorted(expected, key=lambda item: item.team_ref)),
        )
        object.__setattr__(
            self,
            "replacement_records",
            tuple(sorted(replacements, key=lambda item: item.team_ref)),
        )
        object.__setattr__(self, "removed_team_refs", tuple(sorted(set(removed))))


@dataclass(frozen=True, slots=True)
class ReactionResourceCommitReceipt:
    plan: ReactionResourceMutationPlan
    version: int


class _ReactionResourceRuntime(Protocol):
    _lunar_bloom_dew_records: dict[str, LunarBloomDewState]
    _committed_resource_operation_ids: set[str]

    @property
    def version(self) -> int: ...

    @property
    def normalized_through_frame(self) -> int: ...


class ReactionResourcePlanner:
    """当前批次的队伍级 Reaction resource 纯计划器。"""

    def __init__(self, runtime: _ReactionResourceRuntime, frame: int, batch_id: str) -> None:
        _frame(frame, "frame")
        _text(batch_id, "batch_id")
        if frame != runtime.normalized_through_frame:
            raise ValueError("Reaction resource 批次要求所在帧已经完成规范化")
        self._runtime = runtime
        self.frame = frame
        self.batch_id = batch_id
        self._original = dict(runtime._lunar_bloom_dew_records)
        self._working = dict(runtime._lunar_bloom_dew_records)
        self._expected_store_version = runtime.version
        self._sealed = False

    def lunar_bloom_dew_for(self, team_ref: str) -> LunarBloomDewState | None:
        _text(team_ref, "team_ref")
        state = self._working.get(team_ref)
        return None if state is None else state.normalized_at(self.frame)

    def refresh_lunar_bloom_dew(self, *, team_ref: str) -> LunarBloomDewState:
        self._assert_open()
        _text(team_ref, "team_ref")
        before = self._working.get(team_ref)
        if before is None:
            state = LunarBloomDewState(
                team_ref=team_ref,
                current_value=Fraction(0),
                capacity=LUNAR_BLOOM_DEW_CAPACITY,
                recovery_rate_per_frame=LUNAR_BLOOM_DEW_RECOVERY_RATE_PER_FRAME,
                recovery_expires_at_frame=(self.frame + LUNAR_BLOOM_DEW_RECOVERY_DURATION_FRAMES),
                normalized_through_frame=self.frame,
            )
        else:
            normalized = before.normalized_at(self.frame)
            expires_at_frame = self.frame + LUNAR_BLOOM_DEW_RECOVERY_DURATION_FRAMES
            state = (
                normalized
                if normalized.recovery_expires_at_frame == expires_at_frame
                else replace(
                    normalized,
                    recovery_expires_at_frame=expires_at_frame,
                    resource_revision=normalized.resource_revision + 1,
                )
            )
        self._working[team_ref] = state
        return state

    def consume_lunar_bloom_dew(self, *, team_ref: str, amount: int) -> LunarBloomDewState:
        """角色技能消费整数草露；不足、非法或未生成时拒绝。"""

        self._assert_open()
        _text(team_ref, "team_ref")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError("草露消费量必须是正整数")
        state = self._working.get(team_ref)
        if state is None:
            raise ValueError("队伍草露状态尚未生成")
        normalized = state.normalized_at(self.frame)
        if normalized.current_value < amount:
            raise ValueError("草露不足")
        consumed = replace(
            normalized,
            current_value=normalized.current_value - amount,
            resource_revision=normalized.resource_revision + 1,
        )
        self._working[team_ref] = consumed
        return consumed

    def seal(self) -> ReactionResourceMutationPlan:
        self._assert_open()
        self._sealed = True
        return ReactionResourceMutationPlan(
            operation_id=f"reaction-resource:{self.batch_id}",
            frame=self.frame,
            expected_store_version=self._expected_store_version,
            expected_records=tuple(self._original.values()),
            replacement_records=tuple(self._working.values()),
        )

    def _assert_open(self) -> None:
        if self._sealed:
            raise RuntimeError("ReactionResourcePlanner 已封存")


def validate_resource_plan(
    runtime: _ReactionResourceRuntime,
    plan: ReactionResourceMutationPlan,
) -> None:
    if plan.expected_store_version != runtime.version:
        raise RuntimeError("Reaction resource 变更计划已经过期")
    if plan.operation_id in runtime._committed_resource_operation_ids:
        raise RuntimeError("重复的 Reaction resource 操作")
    if plan.frame != runtime.normalized_through_frame:
        raise RuntimeError("Reaction resource 计划帧尚未规范化")
    expected = {item.team_ref: item for item in plan.expected_records}
    if expected != runtime._lunar_bloom_dew_records:
        raise RuntimeError("Reaction resource 记录前值冲突")
