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
    AnalysisSchemaNode,
)
from genshin_sim.core.events.specs import EVENT_SPECS

_KNOWN_PAYLOAD_FIELDS: dict[str, tuple[AnalysisEventField, ...]] = {
    "DAMAGE_RESOLVED": (
        AnalysisEventField("result.final_damage", "float", "结算伤害值"),
        AnalysisEventField("result.source_ref", "string", "伤害来源引用（字符串形态）"),
        AnalysisEventField("result.source_ref.entity_id", "string", "伤害来源实体（对象形态）"),
        AnalysisEventField("result.damage_type", "string", "伤害类型", "enum:damage_type"),
        AnalysisEventField("result.element", "string", "伤害元素", "enum:element"),
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


def build_snapshot_tree() -> AnalysisSchemaNode:
    """输入快照结构树（镜像《模拟输入契约》第一版字段）。

    列表节点（队伍 / 圣遗物套装 / 目标）不枚举位置——目标等集合可能是变长；
    列表叶子的 default_name_template 用 {0}/{1}... 按列表祖先顺序占位，
    由前端在用户输入位置后替换（显示 1 基，路径 0 基）。
    """

    def scalar(
        key: str,
        label: str,
        type_: str,
        *,
        default_name: str | None = None,
        template: str | None = None,
        value_kind: str = "",
    ) -> AnalysisSchemaNode:
        return AnalysisSchemaNode(
            key=key,
            label=label,
            kind="scalar",
            type=type_,
            default_name=default_name,
            default_name_template=template,
            value_kind=value_kind,
        )

    def object_(
        key: str, label: str, children: tuple[AnalysisSchemaNode, ...]
    ) -> AnalysisSchemaNode:
        return AnalysisSchemaNode(key=key, label=label, kind="object", children=children)

    def list_(
        key: str, label: str, children: tuple[AnalysisSchemaNode, ...]
    ) -> AnalysisSchemaNode:
        return AnalysisSchemaNode(key=key, label=label, kind="list", children=children)

    character = object_(
        "character",
        "角色",
        (
            scalar(
                "asset_key",
                "资产",
                "string",
                template="char_{0}_key",
                value_kind="asset:characters",
            ),
            scalar("level", "等级", "int", template="char_{0}_level"),
            scalar("constellation", "命座", "int", template="char_{0}_constellation"),
            object_(
                "talents",
                "天赋",
                (
                    scalar(
                        "normal_attack",
                        "普通攻击天赋",
                        "int",
                        template="char_{0}_talent_normal",
                    ),
                    scalar(
                        "elemental_skill",
                        "元素战技天赋",
                        "int",
                        template="char_{0}_talent_skill",
                    ),
                    scalar(
                        "elemental_burst",
                        "元素爆发天赋",
                        "int",
                        template="char_{0}_talent_burst",
                    ),
                ),
            ),
        ),
    )
    weapon = object_(
        "weapon",
        "武器",
        (
            scalar(
                "asset_key",
                "资产",
                "string",
                template="weapon_{0}_key",
                value_kind="asset:weapons",
            ),
            scalar("level", "等级", "int", template="weapon_{0}_level"),
            scalar("refinement", "精炼", "int", template="weapon_{0}_refinement"),
        ),
    )
    sets = list_(
        "sets",
        "套装",
        (
            scalar(
                "asset_key",
                "套装",
                "string",
                template="set_{0}_{1}_key",
                value_kind="asset:artifact-sets",
            ),
            scalar("pieces", "件数", "int", template="set_{0}_{1}_pieces"),
        ),
    )
    team = list_(
        "team",
        "队伍",
        (character, weapon, object_("artifacts", "圣遗物", (sets,))),
    )
    target = object_(
        "target",
        "目标",
        (
            scalar("id", "ID", "string", template="target_{0}_id"),
            scalar("label", "展示名", "string", template="target_{0}_label"),
            scalar("level", "等级", "int", template="target_{0}_level"),
            object_(
                "resistance",
                "抗性",
                tuple(
                    scalar(
                        element,
                        element_label,
                        "int",
                        template=f"target_{{{0}}}_res_{element}",
                        value_kind="enum:element",
                    )
                    for element, element_label in _ELEMENT_LABELS.items()
                ),
            ),
        ),
    )
    scene = object_(
        "scene",
        "场景",
        (
            list_("targets", "目标", (target,)),
            object_(
                "player",
                "玩家",
                (
                    object_(
                        "position",
                        "位置",
                        (
                            scalar("x", "X", "float", default_name="player_pos_x"),
                            scalar("y", "Y", "float", default_name="player_pos_y"),
                            scalar("z", "Z", "float", default_name="player_pos_z"),
                        ),
                    ),
                ),
            ),
        ),
    )
    meta = object_(
        "meta",
        "元信息",
        (
            scalar("name", "名称", "string", default_name="meta_name"),
            scalar("description", "描述", "string", default_name="meta_description"),
        ),
    )
    run_options = object_(
        "run_options",
        "运行选项",
        (scalar("max_frames", "最大帧数", "int", default_name="max_frames"),),
    )
    return object_("root", "输入快照", (meta, team, scene, run_options))
