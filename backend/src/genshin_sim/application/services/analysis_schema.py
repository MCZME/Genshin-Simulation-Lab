"""分析取数 schema 目录：事件类型与输入快照路径。

事件类型清单以 core 的 EVENT_SPECS 为唯一真值源聚合，不在基础设施层重复维护；
payload 可提取字段只在已有明确分析消费需求的事件类型上登记，其余类型字段为空，
编辑器允许手动填写载荷路径，映射随视图需求登记。
输入快照路径目录镜像《模拟输入契约》第一版字段，作为「获取数据」节点结构路径
选择器的单一真值源，不另立第二份前端拷贝。
"""

from __future__ import annotations

from genshin_sim.application.models import (
    AnalysisEventField,
    AnalysisEventTypeSchema,
    AnalysisSnapshotPath,
)
from genshin_sim.core.events.specs import EVENT_SPECS

_KNOWN_PAYLOAD_FIELDS: dict[str, tuple[AnalysisEventField, ...]] = {
    "DAMAGE_RESOLVED": (
        AnalysisEventField("result.final_damage", "float", "结算伤害值"),
        AnalysisEventField("result.source_ref", "string", "伤害来源引用（字符串形态）"),
        AnalysisEventField("result.source_ref.entity_id", "string", "伤害来源实体（对象形态）"),
        AnalysisEventField("result.damage_type", "string", "伤害类型"),
        AnalysisEventField("result.element", "string", "伤害元素"),
    ),
    "HEALING_RESOLVED": (
        AnalysisEventField("result.final_healing", "float", "结算治疗值"),
        AnalysisEventField("result.source_ref", "string", "治疗来源引用（字符串形态）"),
        AnalysisEventField("result.source_ref.entity_id", "string", "治疗来源实体（对象形态）"),
    ),
    "BUFF_APPLIED": (
        AnalysisEventField("result.instance_ref", "string", "Buff 实例引用"),
        AnalysisEventField("result.definition_key", "string", "Buff 定义 key"),
    ),
    "BUFF_REMOVED": (
        AnalysisEventField("result.instance_ref", "string", "Buff 实例引用"),
    ),
}


def build_event_type_schema() -> tuple[AnalysisEventTypeSchema, ...]:
    """按 EVENT_SPECS 顺序返回全部已实现事件类型的可读 schema。"""

    return tuple(
        AnalysisEventTypeSchema(
            name=event_type.name,
            fields=_KNOWN_PAYLOAD_FIELDS.get(event_type.name, ()),
        )
        for event_type in EVENT_SPECS
    )


_CHARACTER_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("asset_key", "string", "key"),
    ("level", "int", "level"),
    ("constellation", "int", "constellation"),
    ("talents.normal_attack", "int", "talent_normal"),
    ("talents.elemental_skill", "int", "talent_skill"),
    ("talents.elemental_burst", "int", "talent_burst"),
)

_WEAPON_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("asset_key", "string", "key"),
    ("level", "int", "level"),
    ("refinement", "int", "refinement"),
)

_ARTIFACT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("asset_key", "string", "key"),
    ("pieces", "int", "pieces"),
)

_TARGET_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("id", "string", "id"),
    ("label", "string", "label"),
    ("level", "int", "level"),
)

_FIELD_LABELS: dict[str, str] = {
    "asset_key": "资产",
    "level": "等级",
    "constellation": "命座",
    "talents.normal_attack": "普通攻击天赋",
    "talents.elemental_skill": "元素战技天赋",
    "talents.elemental_burst": "元素爆发天赋",
    "refinement": "精炼",
    "pieces": "件数",
    "id": "ID",
    "label": "展示名",
}

_ELEMENT_LABELS: dict[str, str] = {
    "physical": "物理",
    "pyro": "火元素",
    "hydro": "水元素",
    "electro": "雷元素",
    "cryo": "冰元素",
    "anemo": "风元素",
    "geo": "岩元素",
    "dendro": "草元素",
}


def build_snapshot_path_schema() -> tuple[AnalysisSnapshotPath, ...]:
    """输入快照可提取路径目录（镜像模拟输入契约第一版字段）。"""

    entries: list[AnalysisSnapshotPath] = []
    entries.append(
        AnalysisSnapshotPath("meta.name", "string", "meta_name", ("元信息", "名称"))
    )
    entries.append(
        AnalysisSnapshotPath(
            "meta.description", "string", "meta_description", ("元信息", "描述")
        )
    )
    for slot in range(4):
        slot_label = f"槽位 {slot + 1}"
        for field, type_, short in _CHARACTER_FIELDS:
            entries.append(
                AnalysisSnapshotPath(
                    f"team.{slot}.character.{field}",
                    type_,
                    f"char_{slot + 1}_{short}",
                    ("队伍", slot_label, "角色", _FIELD_LABELS[field]),
                )
            )
        for field, type_, short in _WEAPON_FIELDS:
            entries.append(
                AnalysisSnapshotPath(
                    f"team.{slot}.weapon.{field}",
                    type_,
                    f"weapon_{slot + 1}_{short}",
                    ("队伍", slot_label, "武器", _FIELD_LABELS[field]),
                )
            )
        for set_index in range(2):
            for field, type_, short in _ARTIFACT_FIELDS:
                entries.append(
                    AnalysisSnapshotPath(
                        f"team.{slot}.artifacts.sets.{set_index}.{field}",
                        type_,
                        f"set_{slot + 1}_{set_index + 1}_{short}",
                        (
                            "队伍",
                            slot_label,
                            "圣遗物套装",
                            f"第 {set_index + 1} 套",
                            _FIELD_LABELS[field],
                        ),
                    )
                )
    for target_index in range(4):
        target_label = f"目标 {target_index + 1}"
        for field, type_, short in _TARGET_FIELDS:
            entries.append(
                AnalysisSnapshotPath(
                    f"scene.targets.{target_index}.{field}",
                    type_,
                    f"target_{target_index + 1}_{short}",
                    ("场景", target_label, _FIELD_LABELS[field]),
                )
            )
        for element, element_label in _ELEMENT_LABELS.items():
            entries.append(
                AnalysisSnapshotPath(
                    f"scene.targets.{target_index}.resistance.{element}",
                    "int",
                    f"target_{target_index + 1}_res_{element}",
                    ("场景", target_label, "抗性", element_label),
                )
            )
    for axis, label in (("x", "X"), ("y", "Y"), ("z", "Z")):
        entries.append(
            AnalysisSnapshotPath(
                f"scene.player.position.{axis}",
                "float",
                f"player_pos_{axis}",
                ("场景", "玩家", "位置", label),
            )
        )
    entries.append(
        AnalysisSnapshotPath(
            "run_options.max_frames", "int", "max_frames", ("运行选项", "最大帧数")
        )
    )
    return tuple(entries)
