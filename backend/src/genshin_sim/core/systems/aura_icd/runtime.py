"""元素附着 ICD 的精确窗口和批量原子提交。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.aura_icd.enums import IcdOutcome
from genshin_sim.core.systems.aura_icd.models import (
    IcdCommitReceipt,
    IcdDefinition,
    IcdDefinitionRegistry,
    IcdImpactRequest,
    IcdKey,
    IcdMutationPlan,
    IcdRecord,
    IcdResolution,
    IcdSnapshot,
)


class IcdStoreConflictError(RuntimeError):
    """ICD 计划与当前 Store 不一致时抛出的错误。"""


class AuraIcdBatchPlanner:
    """同一元素交互批次中的虚拟 ICD 视图。"""

    def __init__(self, runtime: AuraIcdRuntime, frame: int, batch_id: str) -> None:
        self._runtime = runtime
        self.frame = frame
        self.batch_id = batch_id
        self._records = dict(runtime._records)
        self._expected_store_version = runtime.version
        self._request_ids: set[str] = set()
        self._orders: set[int] = set()
        self._resolutions: list[IcdResolution] = []
        self._sealed = False

    def prepare(self, request: IcdImpactRequest) -> IcdResolution:
        self._assert_open()
        if request.frame != self.frame:
            raise ValueError("ICD 请求帧与所属批次不一致")
        if request.request_id in self._request_ids:
            raise ValueError(f"重复的 ICD request_id：{request.request_id}")
        if request.order in self._orders:
            raise ValueError(f"重复的 ICD order：{request.order}")
        resolution = self._resolve(request)
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        self._resolutions.append(resolution)
        return resolution

    def seal(self) -> IcdMutationPlan:
        self._assert_open()
        self._sealed = True
        current_keys = set(self._runtime._records)
        planned_keys = set(self._records)
        return IcdMutationPlan(
            operation_id=f"aura-icd:{self.batch_id}",
            frame=self.frame,
            request_ids=tuple(sorted(self._request_ids)),
            expected_store_version=self._expected_store_version,
            replacements=tuple(sorted(self._records.values(), key=_record_sort_key)),
            removed_keys=tuple(sorted(current_keys - planned_keys, key=_key_sort_key)),
            resolutions=tuple(sorted(self._resolutions, key=lambda item: item.order)),
        )

    def _resolve(self, request: IcdImpactRequest) -> IcdResolution:
        binding = request.binding
        if binding is None:
            return IcdResolution(
                request.request_id,
                request.impact_ref,
                request.frame,
                request.order,
                request.attacker_ref,
                request.defender_ref,
                None,
                None,
                IcdOutcome.NO_COOLDOWN,
                None,
                AuraAmount.one(),
                None,
                None,
                None,
                None,
            )
        definition = self._runtime.definition_registry.require(binding.sequence_key)
        key = IcdKey(
            request.attacker_ref,
            request.defender_ref,
            binding.tag_key,
            binding.sequence_key,
        )
        record = self._records.get(key)
        if record is None:
            sequence_index = 0
            outcome = IcdOutcome.WINDOW_STARTED
            window_started_frame = request.frame
            resets_at_frame = request.frame + definition.reset_interval_frames
        else:
            sequence_index = min(
                record.next_sequence_index,
                len(definition.application_sequence) - 1,
            )
            outcome = IcdOutcome.SEQUENCE_RESOLVED
            window_started_frame = record.window_started_frame
            resets_at_frame = record.resets_at_frame
        coefficient = definition.application_sequence[sequence_index]
        next_index = min(sequence_index + 1, len(definition.application_sequence))
        after = IcdRecord(
            key,
            window_started_frame,
            resets_at_frame,
            next_index,
            request.frame,
            0 if record is None else record.revision + 1,
        )
        self._records[key] = after
        return IcdResolution(
            request.request_id,
            request.impact_ref,
            request.frame,
            request.order,
            request.attacker_ref,
            request.defender_ref,
            binding.tag_key,
            binding.sequence_key,
            outcome,
            sequence_index,
            coefficient,
            window_started_frame,
            resets_at_frame,
            record,
            after,
        )

    def _assert_open(self) -> None:
        if self._sealed:
            raise RuntimeError("AuraIcdBatchPlanner 已封存")


class AuraIcdRuntime:
    def __init__(self, definition_registry: IcdDefinitionRegistry | None = None) -> None:
        self.definition_registry = definition_registry or IcdDefinitionRegistry(
            (
                standard_icd_definition(),
                default_sequence_definition(),
                no_cooldown_definition(),
            )
        )
        self._records: dict[IcdKey, IcdRecord] = {}
        self._version = 0
        self._normalized_through_frame = 0
        self._committed_operation_ids: set[str] = set()
        self._committed_request_ids: set[str] = set()

    @property
    def version(self) -> int:
        return self._version

    @property
    def normalized_through_frame(self) -> int:
        return self._normalized_through_frame

    def begin_batch(self, frame: int, batch_id: str) -> AuraIcdBatchPlanner:
        if frame != self._normalized_through_frame:
            raise ValueError("ICD 批次要求所在帧已经完成规范化")
        return AuraIcdBatchPlanner(self, frame, batch_id)

    def prepare_impacts(self, requests: tuple[IcdImpactRequest, ...]) -> IcdMutationPlan:
        if not requests:
            return IcdMutationPlan(
                "aura-icd:empty",
                self._normalized_through_frame,
                (),
                self.version,
                (),
                (),
                (),
            )
        planner = self.begin_batch(requests[0].frame, "impacts:" + requests[0].request_id)
        for request in sorted(requests, key=lambda item: item.order):
            planner.prepare(request)
        return planner.seal()

    def validate(self, plan: IcdMutationPlan) -> None:
        if plan.expected_store_version != self.version:
            raise IcdStoreConflictError("ICD 变更计划已经过期")
        if plan.operation_id in self._committed_operation_ids:
            raise IcdStoreConflictError("重复的 ICD 操作")
        duplicates = set(plan.request_ids) & self._committed_request_ids
        if duplicates:
            raise IcdStoreConflictError(f"重复的 ICD 请求：{sorted(duplicates)!r}")
        if plan.frame != self._normalized_through_frame:
            raise IcdStoreConflictError("ICD 计划帧尚未规范化")

    def commit_prevalidated(self, plan: IcdMutationPlan) -> IcdCommitReceipt:
        self.validate(plan)
        next_records = {record.key: record for record in plan.replacements}
        if next_records != self._records:
            self._records = next_records
            self._version += 1
        self._committed_operation_ids.add(plan.operation_id)
        self._committed_request_ids.update(plan.request_ids)
        return IcdCommitReceipt(plan, self.version)

    def resolve(self, request: IcdImpactRequest) -> IcdResolution:
        plan = self.prepare_impacts((request,))
        self.commit_prevalidated(plan)
        return plan.resolutions[0]

    def update_frame(self, context, frame: int) -> None:
        del context
        if frame < self._normalized_through_frame:
            raise ValueError("ICD 帧不能回退")
        if frame == self._normalized_through_frame:
            return
        active = {
            key: record for key, record in self._records.items() if record.resets_at_frame > frame
        }
        if active != self._records:
            self._records = active
            self._version += 1
        self._normalized_through_frame = frame

    def snapshot(self) -> IcdSnapshot:
        return IcdSnapshot(
            self._normalized_through_frame,
            self._normalized_through_frame,
            tuple(sorted(self._records.values(), key=_record_sort_key)),
        )

    def is_idle(self) -> bool:
        return True


def standard_icd_definition() -> IcdDefinition:
    """返回标准 3 命中附着组的有限窗口序列。"""

    sequence = _standard_sequence()
    return IcdDefinition("icd.standard", 150, sequence)


def default_sequence_definition() -> IcdDefinition:
    """返回资料“衰减序列=默认”对应的标准 ICD 序列。"""

    return IcdDefinition("默认", 150, _standard_sequence())


def _standard_sequence() -> tuple[AuraAmount, ...]:
    return tuple(AuraAmount.one() if index % 3 == 0 else AuraAmount.zero() for index in range(24))


def no_cooldown_definition() -> IcdDefinition:
    """返回可显式绑定的无冷却组。"""

    return IcdDefinition("icd.none", 1, (AuraAmount.one(),))


def _key_sort_key(key: IcdKey) -> tuple[str, str, str, str, str]:
    return (
        key.attacker_ref.scope_key,
        key.defender_ref.kind.value,
        key.defender_ref.entity_id,
        key.tag_key,
        key.sequence_key,
    )


def _record_sort_key(record: IcdRecord) -> tuple[str, str, str, str, str]:
    return _key_sort_key(record.key)
