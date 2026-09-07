"""帧状态投影：第 0 帧初始快照基线 + 状态变化事件折叠。

第一版折叠范围与 ``coverage`` 语义见结果存储系统设计第 8 节；
各领域证据事件见结果库契约第 5.1 节核对表。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from genshin_sim.application.execution.models import RecordedEvent

# 与 core FrameClock 的默认帧率保持一致；投影层只做展示换算。
FRAMES_PER_SECOND = 60

_MAX_HP_ATTRIBUTE_KEY = "stat.hp.max"

_COVERAGE_FOLDED = (
    "team",
    "characters.health",
    "characters.energy",
    "characters.attributes",
    "characters.buffs",
    "characters.shields",
    "characters.infusion",
    "characters.cooldowns",
    "characters.content_states",
)
_COVERAGE_BASELINE_ONLY = ("aura", "aura_icd", "reaction", "space")


def coverage_dict() -> dict[str, str]:
    """返回帧状态响应的固定 coverage 标注。"""

    coverage = {key: "folded" for key in _COVERAGE_FOLDED}
    coverage.update({key: "baseline_only" for key in _COVERAGE_BASELINE_ONLY})
    return coverage


def _instance_key(instance_ref: object) -> str | None:
    if not isinstance(instance_ref, dict):
        return None
    domain_key = instance_ref.get("domain_key")
    sequence = instance_ref.get("sequence")
    if (
        not isinstance(domain_key, str)
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
    ):
        return None
    return f"{domain_key}:{sequence}"


def _ref_entity_id(ref: object) -> str | None:
    if not isinstance(ref, dict):
        return None
    entity_id = ref.get("entity_id")
    return entity_id if isinstance(entity_id, str) else None


def _payload_result(data: dict[str, Any]) -> dict[str, Any]:
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def _number_or(value: object, default: float | None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _shield_entity_id(instance: dict[str, Any]) -> str | None:
    protection_ref = instance.get("protection_ref")
    if not isinstance(protection_ref, dict):
        return None
    if protection_ref.get("kind") == "character":
        protection_id = protection_ref.get("protection_id")
        return protection_id if isinstance(protection_id, str) else None
    return None


class _InstanceGroup:
    """按稳定实例 id 折叠的一组实例，并记录每条实例归属的实体。"""

    def __init__(self, entity_id_of: Callable[[dict[str, Any]], str | None]) -> None:
        self.entity_id_of = entity_id_of
        self.instances: dict[str, dict[str, Any]] = {}
        self.owners: dict[str, str | None] = {}

    def upsert(self, instance: object) -> None:
        if not isinstance(instance, dict):
            return
        key = _instance_key(instance.get("instance_ref"))
        if key is None:
            return
        self.instances[key] = instance
        self.owners[key] = self.entity_id_of(instance)

    def remove(self, refs: object) -> None:
        if not isinstance(refs, tuple | list):
            return
        for ref in refs:
            key = _instance_key(ref)
            if key is not None:
                self.instances.pop(key, None)
                self.owners.pop(key, None)

    def update_fields(self, ref: object, fields: dict[str, object]) -> None:
        key = _instance_key(ref)
        instance = self.instances.get(key) if key is not None else None
        if instance is None:
            return
        for field, value in fields.items():
            normalized = _number_or(value, None)
            if normalized is not None:
                instance[field] = normalized

    def entries_for(
        self,
        entity_id: str,
        fallback_owner: str | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key, instance in sorted(
            self.instances.items(), key=lambda item: _instance_sort_key(item[0])
        ):
            owner = self.owners.get(key)
            if owner is None:
                owner = fallback_owner
            if owner == entity_id:
                result.append(dict(instance))
        return result


def _instance_sort_key(key: str) -> tuple[str, int]:
    domain, _, sequence = key.partition(":")
    return (domain, int(sequence) if sequence.isdigit() else 0)


class _FoldState:
    """折叠期间的中间状态。"""

    def __init__(self) -> None:
        self.active_slot: int | None = None
        self.characters: dict[str, dict[str, Any]] = {}
        self.health: dict[str, dict[str, Any]] = {}
        self.energy: dict[str, dict[str, Any]] = {}
        self.attributes: dict[str, dict[str, Any]] = {}
        self.buffs = _InstanceGroup(_buff_entity_id)
        self.shields = _InstanceGroup(_shield_entity_id)
        self.infusions = _InstanceGroup(_infusion_entity_id)
        self.cooldowns: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.content_states: dict[tuple[str, str], dict[str, Any]] = {}


def _buff_entity_id(instance: dict[str, Any]) -> str | None:
    return _ref_entity_id(instance.get("target_ref"))


def _infusion_entity_id(instance: dict[str, Any]) -> str | None:
    return _ref_entity_id(instance.get("character_ref"))


def _cooldown_key(record: object) -> tuple[str, str, str] | None:
    if not isinstance(record, dict):
        return None
    subject_type = record.get("subject_type")
    subject_id = record.get("subject_id")
    ability_key = record.get("ability_key")
    if (
        isinstance(subject_type, str)
        and isinstance(subject_id, str)
        and isinstance(ability_key, str)
    ):
        return (subject_type, subject_id, ability_key)
    return None


def fold_frame_state(
    *,
    session_id: str,
    frame: int,
    initial_snapshot: dict[str, Any],
    events: tuple[RecordedEvent, ...],
) -> dict[str, Any]:
    """把初始快照与 ``frame <= N`` 的事件折叠成帧末状态响应。"""

    providers = initial_snapshot.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("初始快照缺少 providers 基线，无法执行帧状态投影")

    state = _FoldState()
    _load_team_baseline(state, providers.get("team"))
    _load_attributes_baseline(state, providers.get("attributes"))
    _load_instance_baselines(state, providers)

    for event in events:
        if event.frame > frame:
            # 事件按 ordinal 有序且 frame 单调不减，越过目标帧即可停止。
            break
        _apply_event(state, event)

    return _build_response(
        session_id=session_id,
        frame=frame,
        providers=providers,
        state=state,
    )


def _load_team_baseline(state: _FoldState, team: object) -> None:
    if not isinstance(team, dict):
        return
    active_slot = team.get("active_slot")
    if isinstance(active_slot, int) and not isinstance(active_slot, bool):
        state.active_slot = active_slot
    characters = team.get("characters")
    if not isinstance(characters, list):
        return
    for character in characters:
        if not isinstance(character, dict):
            continue
        entity_id = character.get("combat_entity_id")
        if not isinstance(entity_id, str):
            continue
        state.characters[entity_id] = character
        state.health[entity_id] = {
            "current_hp": _number_or(character.get("current_hp"), 0.0),
            "max_hp": None,
        }
        state.energy[entity_id] = {
            "current_energy": _number_or(character.get("current_energy"), 0.0),
            "capacity": None,
        }


def _load_attributes_baseline(state: _FoldState, attributes: object) -> None:
    if not isinstance(attributes, dict):
        return
    subjects = attributes.get("subjects")
    if not isinstance(subjects, dict):
        return
    for entity_id, entries in subjects.items():
        if not isinstance(entity_id, str) or not isinstance(entries, dict):
            continue
        panel: dict[str, Any] = {}
        for key, entry in entries.items():
            if isinstance(key, str) and isinstance(entry, dict):
                panel[key] = {
                    "value": entry.get("value"),
                    "applied_terms": entry.get("applied_terms", ()),
                }
        state.attributes[entity_id] = panel
        max_hp_entry = panel.get(_MAX_HP_ATTRIBUTE_KEY)
        if entity_id in state.health and isinstance(max_hp_entry, dict):
            max_hp = _number_or(max_hp_entry.get("value"), None)
            if max_hp is not None:
                state.health[entity_id]["max_hp"] = max_hp


def _load_instance_baselines(state: _FoldState, providers: dict[str, Any]) -> None:
    """第 0 帧实例基线；正常为空，仅防御启动即有实例的内容。"""

    buff = providers.get("buff")
    if isinstance(buff, dict) and isinstance(buff.get("instances"), list):
        for instance in buff["instances"]:
            state.buffs.upsert(instance)
    shield = providers.get("shield")
    if isinstance(shield, dict) and isinstance(shield.get("instances"), list):
        for instance in shield["instances"]:
            state.shields.upsert(instance)
    infusion = providers.get("infusion")
    if isinstance(infusion, dict) and isinstance(infusion.get("instances"), list):
        for instance in infusion["instances"]:
            state.infusions.upsert(instance)
    cooldown = providers.get("cooldown")
    if isinstance(cooldown, dict) and isinstance(cooldown.get("records"), list):
        for record in cooldown["records"]:
            key = _cooldown_key(record)
            if key is not None:
                state.cooldowns[key] = record
    content_state = providers.get("content_state")
    if isinstance(content_state, dict):
        for owner_ref, entry in content_state.items():
            if not isinstance(owner_ref, str) or not isinstance(entry, dict):
                continue
            state.content_states[(owner_ref, str(entry.get("handler_key")))] = {
                "owner_ref": owner_ref,
                "state_key": entry.get("handler_key"),
                "payload": entry.get("payload"),
            }


def _apply_event(state: _FoldState, event: RecordedEvent) -> None:
    data = event.data
    event_type = event.event_type
    if event_type == "TEAM_SWITCHED":
        active_slot = data.get("active_slot")
        if (
            data.get("accepted") is True
            and isinstance(active_slot, int)
            and not isinstance(active_slot, bool)
        ):
            state.active_slot = active_slot
    elif event_type == "CHARACTER_HEALTH_CHANGED":
        result = _payload_result(data)
        entity_id = _ref_entity_id(result.get("target_ref"))
        health = state.health.get(entity_id) if entity_id is not None else None
        if health is not None:
            hp_after = _number_or(result.get("hp_after"), None)
            if hp_after is not None:
                health["current_hp"] = hp_after
            max_hp = _number_or(result.get("max_hp"), None)
            if max_hp is not None:
                health["max_hp"] = max_hp
    elif event_type == "CHARACTER_MAX_HP_CHANGED":
        result = _payload_result(data)
        entity_id = _ref_entity_id(result.get("target_ref"))
        health = state.health.get(entity_id) if entity_id is not None else None
        if health is not None:
            new_max_hp = _number_or(result.get("new_max_hp"), None)
            if new_max_hp is not None:
                health["max_hp"] = new_max_hp
            hp_after = _number_or(result.get("hp_after"), None)
            if hp_after is not None:
                health["current_hp"] = hp_after
    elif event_type == "CHARACTER_ENERGY_CHANGED":
        result = _payload_result(data)
        entity_id = _ref_entity_id(result.get("target_ref"))
        energy = state.energy.get(entity_id) if entity_id is not None else None
        if energy is not None:
            energy_after = _number_or(result.get("energy_after"), None)
            if energy_after is not None:
                energy["current_energy"] = energy_after
            capacity = _number_or(result.get("capacity"), None)
            if capacity is not None:
                energy["capacity"] = capacity
    elif event_type == "ATTRIBUTE_PANEL_CHANGED":
        entity_id = _ref_entity_id(data.get("subject_ref"))
        panel = state.attributes.get(entity_id) if entity_id is not None else None
        changes = data.get("changes")
        if panel is not None and isinstance(changes, list):
            for change in changes:
                if not isinstance(change, dict):
                    continue
                key = change.get("attribute_key")
                if isinstance(key, str):
                    panel[key] = {
                        "value": change.get("after_value"),
                        "applied_terms": change.get("after_terms", ()),
                    }
    elif event_type == "BUFF_APPLIED":
        result = _payload_result(data)
        state.buffs.remove(result.get("replaced_instance_refs"))
        state.buffs.upsert(result.get("instance_after"))
    elif event_type == "BUFF_REMOVED":
        state.buffs.remove((_payload_result(data).get("instance_ref"),))
    elif event_type == "SHIELD_GRANTED":
        result = _payload_result(data)
        replaced = result.get("replaced_instance_ref")
        if replaced is not None:
            state.shields.remove((replaced,))
        state.shields.upsert(result.get("instance_after"))
    elif event_type == "SHIELD_CAPACITY_CHANGED":
        result = _payload_result(data)
        state.shields.update_fields(
            result.get("instance_ref"),
            {
                "remaining_native_absorption": result.get("native_after"),
                "maximum_native_absorption": result.get("maximum_after"),
            },
        )
    elif event_type == "SHIELD_REMOVED":
        state.shields.remove((_payload_result(data).get("instance_ref"),))
    elif event_type == "INFUSION_APPLIED":
        result = _payload_result(data)
        state.infusions.remove(result.get("replaced_instance_refs"))
        state.infusions.upsert(result.get("instance_after"))
    elif event_type == "INFUSION_REMOVED":
        state.infusions.remove((_payload_result(data).get("instance_ref"),))
    elif event_type == "COOLDOWN_CHANGED":
        record = data.get("after_record")
        key = _cooldown_key(record)
        if key is not None and isinstance(record, dict):
            state.cooldowns[key] = record
    elif event_type == "CONTENT_STATE_CHANGED":
        owner_ref = data.get("owner_ref")
        state_key = data.get("state_key")
        if isinstance(owner_ref, str) and isinstance(state_key, str):
            state.content_states[(owner_ref, state_key)] = {
                "owner_ref": owner_ref,
                "state_key": state_key,
                "payload": data.get("after"),
            }


def _build_response(
    *,
    session_id: str,
    frame: int,
    providers: dict[str, Any],
    state: _FoldState,
) -> dict[str, Any]:
    active_slot = state.active_slot
    active_entity_id = next(
        (
            entity_id
            for entity_id, character in state.characters.items()
            if character.get("slot") == active_slot
        ),
        None,
    )
    identity = sorted(state.characters.values(), key=lambda item: item.get("slot") or 0)

    team_characters = [
        {
            "slot": character.get("slot"),
            "character_key": character.get("character_key"),
            "combat_entity_id": character.get("combat_entity_id"),
        }
        for character in identity
    ]

    characters: list[dict[str, Any]] = []
    for character in identity:
        entity_id = str(character.get("combat_entity_id"))
        slot = character.get("slot")
        health = state.health.get(entity_id, {})
        max_hp = health.get("max_hp")
        current_hp = health.get("current_hp", 0.0)
        hp_ratio = None if not isinstance(max_hp, float) or max_hp <= 0 else current_hp / max_hp
        energy = state.energy.get(entity_id, {})
        capacity = energy.get("capacity")
        current_energy = energy.get("current_energy", 0.0)
        characters.append(
            {
                "slot": slot,
                "character_key": character.get("character_key"),
                "combat_entity_id": entity_id,
                "active": slot == active_slot,
                "health": {
                    "current_hp": current_hp,
                    "max_hp": max_hp,
                    "hp_ratio": hp_ratio,
                },
                "energy": {
                    "current_energy": current_energy,
                    "capacity": capacity,
                    "burst_ready": (
                        isinstance(capacity, float) and capacity > 0 and current_energy >= capacity
                    ),
                },
                "attributes": dict(state.attributes.get(entity_id, {})),
                "buffs": state.buffs.entries_for(entity_id),
                "shields": state.shields.entries_for(entity_id, fallback_owner=active_entity_id),
                "infusion": state.infusions.entries_for(entity_id),
                "cooldowns": [
                    dict(record)
                    for (subject_type, subject_id, _), record in sorted(
                        state.cooldowns.items(), key=lambda item: item[0]
                    )
                    if subject_type == "character" and subject_id == entity_id
                ],
                "content_states": [
                    dict(entry)
                    for (owner_ref, _), entry in sorted(
                        state.content_states.items(), key=lambda item: item[0]
                    )
                    if owner_ref == entity_id
                ],
            }
        )

    resonance = providers.get("resonance")
    moonsign = providers.get("moonsign")

    return {
        "session_id": session_id,
        "frame": frame,
        "time_seconds": frame / FRAMES_PER_SECOND,
        "team": {
            "active_slot": active_slot,
            "slots": [character.get("slot") for character in identity],
            "characters": team_characters,
        },
        "characters": characters,
        "resonance": {
            "active_keys": list(resonance.get("active_keys", ()))
            if isinstance(resonance, dict)
            else []
        },
        "moonsign": {
            "level": moonsign.get("level", "") if isinstance(moonsign, dict) else "",
            "moonsign_character_refs": (
                list(moonsign.get("moonsign_character_refs", ()))
                if isinstance(moonsign, dict)
                else []
            ),
        },
        "coverage": coverage_dict(),
    }
