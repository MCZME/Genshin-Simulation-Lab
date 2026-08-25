"""分析取数 schema 的事件类型目录。

事件类型清单以 core 的 EVENT_SPECS 为唯一真值源聚合，不在基础设施层重复维护；
payload 可提取字段只在已有明确分析消费需求的事件类型上登记，其余类型字段为空，
编辑器允许手动填写载荷路径，映射随视图需求登记。
"""

from __future__ import annotations

from genshin_sim.application.models import (
    AnalysisEventField,
    AnalysisEventTypeSchema,
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
