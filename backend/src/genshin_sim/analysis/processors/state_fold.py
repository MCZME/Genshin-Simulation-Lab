"""初始快照 + 事件流还原任意帧状态视图。

本模块是 analysis 读取侧的纯加工：输入是结果库给出的初始快照与有序事件，
输出是指定帧的状态视图与各 provider 的还原状态。不写库、不访问 SQLite。

第一版支持还原的领域（``fold_status = "folded"``）：

- ``team``：队伍场上角色、角色生命与能量（``TEAM_SWITCHED`` /
  ``CHARACTER_HEALTH_CHANGED`` / ``CHARACTER_ENERGY_CHANGED`` /
  ``CHARACTER_MAX_HP_CHANGED``）。
- ``cooldown``：冷却充能与就绪帧（``COOLDOWN_CHANGED``）。
- ``buff``：Buff 实例创建/替换/移除（``BUFF_APPLIED`` / ``BUFF_REMOVED``）。
- ``shield``：护盾实例授予/容量/移除（``SHIELD_GRANTED`` /
  ``SHIELD_CAPACITY_CHANGED`` / ``SHIELD_REMOVED``）。
- ``infusion``：附魔实例创建/替换/移除（``INFUSION_APPLIED`` /
  ``INFUSION_REMOVED``）。
- ``attributes``：属性面板差异（``ATTRIBUTE_PANEL_CHANGED``）。

未接入还原的 provider 保持初始快照基线并标记 ``baseline``；标记必须透传到
UI，不得当作精确结果使用。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol, cast


class RecordedEventLike(Protocol):
    """结果库事件行的最小读取形状。"""

    @property
    def frame(self) -> int: ...

    @property
    def event_type(self) -> str: ...

    @property
    def data(self) -> dict[str, Any]: ...


class StateFoldError(RuntimeError):
    """状态还原错误基类。"""


@dataclass(frozen=True, slots=True)
class FrameStateView:
    """指定帧的状态视图（派生层，不落库）。"""

    frame: int
    providers: Mapping[str, object]
    fold_status: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "providers": dict(self.providers),
            "fold_status": dict(self.fold_status),
        }


_Reducer = Callable[[dict[str, object], RecordedEventLike], None]
_REDUCERS: dict[str, _Reducer] = {}

_FOLDED_PROVIDERS = frozenset({"team", "cooldown", "buff", "shield", "infusion", "attributes"})


def fold_state(
    initial_snapshot: Mapping[str, object] | None,
    events: Iterable[RecordedEventLike],
    frame: int,
) -> FrameStateView:
    """从初始快照基线还原事件流，返回不超过 ``frame`` 的最新状态视图。"""

    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise StateFoldError("frame 必须是非负整数")
    providers = _baseline_providers(initial_snapshot)
    for event in events:
        if event.frame > frame:
            continue
        reducer = _REDUCERS.get(event.event_type)
        if reducer is None:
            continue
        reducer(providers, event)
    fold_status = {
        provider_key: ("folded" if provider_key in _FOLDED_PROVIDERS else "baseline")
        for provider_key in providers
    }
    return FrameStateView(frame, providers, fold_status)


def _baseline_providers(
    initial_snapshot: Mapping[str, object] | None,
) -> dict[str, object]:
    if initial_snapshot is None:
        return {}
    raw = initial_snapshot.get("providers")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise StateFoldError("初始快照 providers 必须是映射")
    return cast(dict[str, object], deepcopy(dict(raw)))


def _provider(providers: dict[str, object], key: str) -> dict[str, object]:
    raw = providers.get(key)
    if raw is None:
        result: dict[str, object] = {}
        providers[key] = result
        return result
    if not isinstance(raw, dict):
        raise StateFoldError(f"{key} provider 必须是映射")
    return raw


def _instance_list(providers: dict[str, object], provider_key: str) -> list[dict[str, object]]:
    container = _provider(providers, provider_key)
    raw = container.get("instances")
    if not isinstance(raw, list):
        raise StateFoldError(f"{provider_key} provider instances 必须是列表")
    return raw


def _instance_identity(instance: Mapping[str, object]) -> str:
    instance_ref = instance.get("instance_ref")
    if not isinstance(instance_ref, Mapping):
        raise StateFoldError("实例条目缺少 instance_ref")
    domain_key = instance_ref.get("domain_key")
    sequence = instance_ref.get("sequence")
    if not isinstance(domain_key, str) or not isinstance(sequence, int):
        raise StateFoldError("instance_ref 必须是 {domain_key, sequence} 形状")
    return f"{domain_key}:{sequence}"


def _upsert_instances(
    instances: list[dict[str, object]],
    after: Mapping[str, object],
) -> None:
    identity = _instance_identity(after)
    remaining = [item for item in instances if _instance_identity(item) != identity]
    remaining.append(deepcopy(dict(after)))
    instances[:] = remaining


def _remove_instances(
    instances: list[dict[str, object]],
    instance_ref: Mapping[str, object],
) -> None:
    identity = f"{instance_ref.get('domain_key')}:{instance_ref.get('sequence')}"
    remaining = [item for item in instances if _instance_identity(item) != identity]
    if len(remaining) == len(instances):
        raise StateFoldError(f"移除不存在的实例：{identity}")
    instances[:] = remaining


def _character(providers: dict[str, object], entity_id: str) -> dict[str, object]:
    team = _provider(providers, "team")
    raw_characters = team.get("characters")
    if not isinstance(raw_characters, list):
        raise StateFoldError("team provider characters 必须是列表")
    for raw in raw_characters:
        if not isinstance(raw, dict):
            raise StateFoldError("team provider character 必须是映射")
        if raw.get("combat_entity_id") == entity_id:
            return raw
    raise StateFoldError(f"还原目标角色不存在：{entity_id}")


def _reduce_team_switched(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    if not event.data.get("accepted"):
        return
    active_slot = event.data.get("active_slot")
    if not isinstance(active_slot, int):
        raise StateFoldError("TEAM_SWITCHED active_slot 必须是非负整数")
    _provider(providers, "team")["active_slot"] = active_slot


def _reduce_health_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("CHARACTER_HEALTH_CHANGED result 必须是映射")
    target = result.get("target_ref")
    if not isinstance(target, dict):
        raise StateFoldError("CHARACTER_HEALTH_CHANGED target_ref 必须是映射")
    _character(providers, str(target.get("entity_id")))["current_hp"] = result.get("hp_after")


def _reduce_energy_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("CHARACTER_ENERGY_CHANGED result 必须是映射")
    target = result.get("target_ref")
    if not isinstance(target, dict):
        raise StateFoldError("CHARACTER_ENERGY_CHANGED target_ref 必须是映射")
    _character(providers, str(target.get("entity_id")))["current_energy"] = result.get(
        "energy_after"
    )


def _reduce_cooldown_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    cooldown = _provider(providers, "cooldown")
    raw_records = cooldown.get("records")
    if not isinstance(raw_records, list):
        raise StateFoldError("cooldown provider records 必须是列表")
    data = event.data
    subject = data.get("subject_ref")
    if not isinstance(subject, dict):
        raise StateFoldError("COOLDOWN_CHANGED subject_ref 必须是映射")
    ability_key = data.get("ability_key")
    for record in raw_records:
        if not isinstance(record, dict):
            raise StateFoldError("cooldown provider record 必须是映射")
        if (
            record.get("subject_type") == subject.get("subject_type")
            and record.get("subject_id") == subject.get("subject_id")
            and record.get("ability_key") == ability_key
        ):
            after_record = data.get("after_record")
            if isinstance(after_record, dict):
                record.clear()
                record.update(after_record)
            else:
                record["available_charges"] = data.get("after_available_charges")
                record["active_ready_frame"] = data.get("active_ready_frame")
                record["queued_recoveries"] = data.get("queued_recoveries")
                record["chain_id"] = data.get("chain_id")
            return
    raise StateFoldError(f"冷却记录不存在：{subject} / {ability_key}")


def _reduce_max_hp_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("CHARACTER_MAX_HP_CHANGED result 必须是映射")
    target = result.get("target_ref")
    if not isinstance(target, dict):
        raise StateFoldError("CHARACTER_MAX_HP_CHANGED target_ref 必须是映射")
    _character(providers, str(target.get("entity_id")))["current_hp"] = result.get("hp_after")


def _reduce_buff_applied(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("BUFF_APPLIED result 必须是映射")
    instances = _instance_list(providers, "buff")
    for replaced_ref in result.get("replaced_instance_refs", ()):
        if isinstance(replaced_ref, dict):
            _remove_instances(instances, replaced_ref)
    instance_after = result.get("instance_after")
    if not isinstance(instance_after, dict):
        raise StateFoldError("BUFF_APPLIED 缺少 instance_after，无法精确还原")
    _upsert_instances(instances, instance_after)


def _reduce_buff_removed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("BUFF_REMOVED result 必须是映射")
    instance_ref = result.get("instance_ref")
    if not isinstance(instance_ref, dict):
        raise StateFoldError("BUFF_REMOVED instance_ref 必须是映射")
    _remove_instances(_instance_list(providers, "buff"), instance_ref)


def _reduce_shield_granted(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("SHIELD_GRANTED result 必须是映射")
    instances = _instance_list(providers, "shield")
    replaced = result.get("replaced_instance_ref")
    if isinstance(replaced, dict):
        _remove_instances(instances, replaced)
    instance_after = result.get("instance_after")
    if not isinstance(instance_after, dict):
        raise StateFoldError("SHIELD_GRANTED 缺少 instance_after，无法精确还原")
    _upsert_instances(instances, instance_after)


def _reduce_shield_capacity_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("SHIELD_CAPACITY_CHANGED result 必须是映射")
    instance_ref = result.get("instance_ref")
    if not isinstance(instance_ref, dict):
        raise StateFoldError("SHIELD_CAPACITY_CHANGED instance_ref 必须是映射")
    identity = f"{instance_ref.get('domain_key')}:{instance_ref.get('sequence')}"
    for instance in _instance_list(providers, "shield"):
        if _instance_identity(instance) == identity:
            instance["remaining_native_absorption"] = result.get("native_after")
            instance["maximum_native_absorption"] = result.get("maximum_after")
            return
    raise StateFoldError(f"护盾实例不存在：{identity}")


def _reduce_shield_removed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("SHIELD_REMOVED result 必须是映射")
    instance_ref = result.get("instance_ref")
    if not isinstance(instance_ref, dict):
        raise StateFoldError("SHIELD_REMOVED instance_ref 必须是映射")
    _remove_instances(_instance_list(providers, "shield"), instance_ref)


def _reduce_infusion_applied(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("INFUSION_APPLIED result 必须是映射")
    instances = _instance_list(providers, "infusion")
    for replaced_ref in result.get("replaced_instance_refs", ()):
        if isinstance(replaced_ref, dict):
            _remove_instances(instances, replaced_ref)
    instance_after = result.get("instance_after")
    if not isinstance(instance_after, dict):
        raise StateFoldError("INFUSION_APPLIED 缺少 instance_after，无法精确还原")
    _upsert_instances(instances, instance_after)


def _reduce_infusion_removed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    result = event.data.get("result")
    if not isinstance(result, dict):
        raise StateFoldError("INFUSION_REMOVED result 必须是映射")
    instance_ref = result.get("instance_ref")
    if not isinstance(instance_ref, dict):
        raise StateFoldError("INFUSION_REMOVED instance_ref 必须是映射")
    _remove_instances(_instance_list(providers, "infusion"), instance_ref)


def _reduce_attribute_panel_changed(
    providers: dict[str, object],
    event: RecordedEventLike,
) -> None:
    data = event.data
    subject_ref = data.get("subject_ref")
    if not isinstance(subject_ref, dict):
        raise StateFoldError("ATTRIBUTE_PANEL_CHANGED subject_ref 必须是映射")
    entity_id = subject_ref.get("entity_id")
    if not isinstance(entity_id, str):
        raise StateFoldError("ATTRIBUTE_PANEL_CHANGED entity_id 必须是字符串")
    attributes = _provider(providers, "attributes")
    subjects = attributes.get("subjects")
    if not isinstance(subjects, dict):
        raise StateFoldError("attributes provider subjects 必须是映射")
    panel = subjects.get(entity_id)
    if not isinstance(panel, dict):
        raise StateFoldError(f"属性面板主体不存在：{entity_id}")
    for change in data.get("changes", ()):
        if not isinstance(change, dict):
            raise StateFoldError("ATTRIBUTE_PANEL_CHANGED changes 项必须是映射")
        attribute_key = change.get("attribute_key")
        if not isinstance(attribute_key, str):
            raise StateFoldError("ATTRIBUTE_PANEL_CHANGED attribute_key 必须是字符串")
        panel[attribute_key] = {
            "value": change.get("after_value"),
            "applied_terms": tuple(change.get("after_terms", ())),
        }


_REDUCERS = {
    "TEAM_SWITCHED": _reduce_team_switched,
    "CHARACTER_HEALTH_CHANGED": _reduce_health_changed,
    "CHARACTER_MAX_HP_CHANGED": _reduce_max_hp_changed,
    "CHARACTER_ENERGY_CHANGED": _reduce_energy_changed,
    "COOLDOWN_CHANGED": _reduce_cooldown_changed,
    "BUFF_APPLIED": _reduce_buff_applied,
    "BUFF_REMOVED": _reduce_buff_removed,
    "SHIELD_GRANTED": _reduce_shield_granted,
    "SHIELD_CAPACITY_CHANGED": _reduce_shield_capacity_changed,
    "SHIELD_REMOVED": _reduce_shield_removed,
    "INFUSION_APPLIED": _reduce_infusion_applied,
    "INFUSION_REMOVED": _reduce_infusion_removed,
    "ATTRIBUTE_PANEL_CHANGED": _reduce_attribute_panel_changed,
}
