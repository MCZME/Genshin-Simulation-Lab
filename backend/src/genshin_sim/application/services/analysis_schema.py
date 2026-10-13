"""分析取数 schema 目录：事件类型与输入快照路径。

事件类型清单以 core 的 EVENT_SPECS 为唯一真值源聚合，不在基础设施层重复维护；
payload 可提取字段**覆盖全部会落库的事件类型**（`record_by_default=true`），
路径与类型由各 payload 的 `to_dict()` 推导，不凭记忆登记；纯排查用的内部关联 id
与数组型字段不登记，需要时编辑器仍允许手动填写载荷路径。
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
    # ── 结算边界 ──
    "SIMULATION_ENDED": (
        AnalysisEventField("stop_reason", "string", "结束原因"),
        AnalysisEventField("end_frame", "int", "结束帧"),
        AnalysisEventField("frames_run", "int", "运行帧数"),
    ),
    # ── 输入 ──（注意：session_id 是输入会话序号，与运行 session_id 同名不同义）
    "INPUT_KEY_RECEIVED": (
        AnalysisEventField("key", "string", "按键"),
        AnalysisEventField("phase", "string", "按键相位"),
        AnalysisEventField("order", "int", "顺序"),
        AnalysisEventField("session_id", "int", "输入会话序号（非运行 session_id）"),
    ),
    "INPUT_SESSION_BOUNDARY_REACHED": (
        AnalysisEventField("session_id", "int", "输入会话序号（非运行 session_id）"),
        AnalysisEventField("key", "string", "按键"),
        AnalysisEventField("phase", "string", "按键相位"),
        AnalysisEventField("order", "int", "顺序"),
        AnalysisEventField("press_frame", "int", "按下帧"),
        AnalysisEventField("held_frames", "int", "持续帧数"),
        AnalysisEventField("physical_state", "string", "物理状态"),
        AnalysisEventField("control_state", "string", "控制状态"),
        AnalysisEventField("owner_kind", "string", "归属类型"),
        AnalysisEventField("owner_slot", "int", "归属槽位"),
        AnalysisEventField("interpreter_id", "string", "解释器 id"),
        AnalysisEventField("binding_scope", "string", "绑定范围"),
        AnalysisEventField("will_interpret", "bool", "是否将解释"),
        AnalysisEventField("skip_reason", "string", "跳过原因"),
    ),
    "INPUT_SESSION_DEFERRED": (
        AnalysisEventField("session_id", "int", "输入会话序号（非运行 session_id）"),
        AnalysisEventField("key", "string", "按键"),
        AnalysisEventField("trigger", "string", "触发来源"),
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("reason", "string", "推迟原因"),
    ),
    "INPUT_SESSION_RESOLVED": (
        AnalysisEventField("session_id", "int", "输入会话序号（非运行 session_id）"),
        AnalysisEventField("key", "string", "按键"),
        AnalysisEventField("outcome", "string", "结算结果"),
        AnalysisEventField("frame", "int", "结算帧"),
        AnalysisEventField("buffered_at_frame", "int", "缓冲帧"),
        AnalysisEventField("reason", "string", "原因"),
        AnalysisEventField("instance_id", "int", "动作实例 id"),
    ),
    # ── 伤害与治疗 ──
    "DAMAGE_RESOLVED": (
        AnalysisEventField("result.final_damage", "float", "最终伤害"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.source_ref", "string", "伤害来源实体 id"),
        AnalysisEventField("result.target_ref", "string", "伤害目标实体 id"),
        AnalysisEventField("result.formula_key", "string", "伤害公式", "enum:formula_key"),
        AnalysisEventField("result.element", "string", "伤害元素", "enum:element"),
        AnalysisEventField("result.main_attack_tag", "string", "主攻击标签"),
        AnalysisEventField("result.damage_name", "string", "伤害名称"),
        AnalysisEventField("result.base_damage", "float", "基础伤害"),
        AnalysisEventField("result.crit_outcome", "string", "暴击结果"),
        AnalysisEventField("result.crit_rate", "float", "暴击率"),
        AnalysisEventField("result.crit_damage", "float", "暴击伤害"),
        AnalysisEventField("result.crit_multiplier", "float", "暴击倍率"),
        AnalysisEventField("result.damage_bonus_multiplier", "float", "增伤倍率"),
        AnalysisEventField("result.defense_multiplier", "float", "防御区倍率"),
        AnalysisEventField("result.resistance_multiplier", "float", "抗性区倍率"),
        AnalysisEventField("result.reaction_multiplier", "float", "反应倍率"),
        AnalysisEventField("result.final_multiplier", "float", "最终乘区"),
        AnalysisEventField("result.official_damage", "float", "官方口径伤害"),
        AnalysisEventField("result.reaction.kind", "string", "反应类型"),
        AnalysisEventField("result.reaction.multiplier", "float", "反应明细倍率"),
        AnalysisEventField("result.reaction.reaction_profile_key", "string", "反应档案 key"),
    ),
    "HEALING_RESOLVED": (
        AnalysisEventField("result.final_healing", "float", "结算治疗值"),
        AnalysisEventField("result.source_ref", "string", "治疗来源实体对象"),
        AnalysisEventField("result.source_ref.entity_id", "string", "治疗来源实体 id"),
        AnalysisEventField("result.healing_id", "string", "治疗 id"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.target_ref.entity_id", "string", "治疗目标实体 id"),
        AnalysisEventField("result.base_healing", "float", "基础治疗量"),
        AnalysisEventField("result.flat_healing", "float", "固定治疗量"),
        AnalysisEventField("result.outgoing_healing_bonus", "float", "治疗加成"),
        AnalysisEventField("result.incoming_healing_bonus", "float", "受治疗加成"),
        AnalysisEventField("result.healing_bonus_multiplier", "float", "治疗加成倍率"),
    ),
    "DAMAGE_APPLIED": (
        AnalysisEventField("record.incoming_damage.damage_id", "string", "伤害 id"),
        AnalysisEventField("record.incoming_damage.frame", "int", "结算帧"),
        AnalysisEventField("record.incoming_damage.amount", "float", "承伤量"),
        AnalysisEventField("record.incoming_damage.element", "string", "承伤元素", "enum:element"),
        AnalysisEventField("record.incoming_damage.target_ref.entity_id", "string", "承伤角色"),
        AnalysisEventField("record.incoming_damage.source_ref.entity_id", "string", "承伤来源"),
        AnalysisEventField("record.shield_result.protected_damage", "float", "护盾吸收量"),
        AnalysisEventField("record.shield_result.health_bound_damage", "float", "穿透护盾伤害"),
        AnalysisEventField(
            "record.shield_result.had_active_shield_before", "bool", "受伤前有无护盾"
        ),
        AnalysisEventField(
            "record.shield_result.has_active_shield_after", "bool", "受伤后有无护盾"
        ),
        AnalysisEventField("record.health_application.amount", "float", "提交给生命的伤害量"),
        AnalysisEventField("record.health_result.hp_before", "float", "生命前值"),
        AnalysisEventField("record.health_result.hp_after", "float", "生命后值"),
        AnalysisEventField("record.health_result.effective_amount", "float", "实际扣血"),
        AnalysisEventField("record.health_result.max_hp", "float", "最大生命"),
    ),
    # ── 生命与护盾 ──
    "CHARACTER_HEALTH_CHANGED": (
        AnalysisEventField("result.change_id", "string", "变更 id"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.change_kind", "string", "变更类型"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标角色"),
        AnalysisEventField("result.requested_amount", "float", "请求量"),
        AnalysisEventField("result.effective_amount", "float", "实际生效量"),
        AnalysisEventField("result.unapplied_amount", "float", "未生效量"),
        AnalysisEventField("result.hp_before", "float", "生命前值"),
        AnalysisEventField("result.hp_after", "float", "生命后值"),
        AnalysisEventField("result.max_hp", "float", "最大生命"),
        AnalysisEventField("result.minimum_remaining_hp", "float", "保底剩余生命"),
    ),
    "CHARACTER_MAX_HP_CHANGED": (
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标角色"),
        AnalysisEventField("result.old_max_hp", "float", "最大生命前值"),
        AnalysisEventField("result.new_max_hp", "float", "最大生命后值"),
        AnalysisEventField("result.hp_before", "float", "生命前值"),
        AnalysisEventField("result.hp_after", "float", "生命后值"),
    ),
    "SHIELD_GRANTED": (
        AnalysisEventField("result.instance_ref.sequence", "int", "护盾实例序号"),
        AnalysisEventField("result.outcome", "string", "授予结果"),
        AnalysisEventField("result.remaining_before", "float", "护盾量前值"),
        AnalysisEventField("result.remaining_after", "float", "护盾量后值"),
        AnalysisEventField("result.maximum_after", "float", "护盾上限"),
        AnalysisEventField("result.expires_at_before", "int", "到期帧前值"),
        AnalysisEventField("result.expires_at_after", "int", "到期帧后值"),
    ),
    "SHIELD_CAPACITY_CHANGED": (
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.instance_ref.sequence", "int", "护盾实例序号"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.reason", "string", "变更原因"),
        AnalysisEventField("result.native_before", "float", "原生吸收量前值"),
        AnalysisEventField("result.native_after", "float", "原生吸收量后值"),
        AnalysisEventField("result.maximum_before", "float", "上限前值"),
        AnalysisEventField("result.maximum_after", "float", "上限后值"),
    ),
    "SHIELD_REMOVED": (
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.instance_ref.sequence", "int", "护盾实例序号"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.reason", "string", "移除原因"),
        AnalysisEventField("result.native_remaining", "float", "剩余吸收量"),
    ),
    "SHIELD_ABSORPTION_RESOLVED": (
        AnalysisEventField("result.damage_id", "string", "对应伤害 id"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.target_ref.entity_id", "string", "承伤角色"),
        AnalysisEventField("result.incoming_amount", "float", "进入的伤害量"),
        AnalysisEventField("result.element", "string", "元素", "enum:element"),
        AnalysisEventField("result.active_character_shield_strength", "float", "场上角色护盾强度"),
        AnalysisEventField("result.protected_damage", "float", "护盾吸收量"),
        AnalysisEventField("result.health_bound_damage", "float", "穿透护盾伤害"),
        AnalysisEventField("result.had_active_shield_before", "bool", "吸收前有无护盾"),
        AnalysisEventField("result.has_active_shield_after", "bool", "吸收后有无护盾"),
    ),
    # ── 能量 ──
    "ENERGY_PICKUP_SPAWNED": (
        AnalysisEventField("record.pickup_id", "string", "能量球 id"),
        AnalysisEventField("record.created_frame", "int", "生成帧"),
        AnalysisEventField("record.settle_frame", "int", "计划结算帧"),
        AnalysisEventField("record.pickup_kind", "string", "能量球类型"),
        AnalysisEventField("record.element", "string", "元素", "enum:element"),
        AnalysisEventField("record.count", "int", "个数"),
        AnalysisEventField("record.source_ref.entity_id", "string", "生成来源"),
        AnalysisEventField("record.spawn_order", "int", "生成序"),
    ),
    "ENERGY_PICKUP_SETTLED": (
        AnalysisEventField("result.settled_frame", "int", "结算帧"),
        AnalysisEventField("result.active_slot", "int", "场上槽位"),
        AnalysisEventField("result.team_size", "int", "队伍人数"),
    ),
    "DIRECT_ENERGY_CHANGE_RESOLVED": (
        AnalysisEventField("result.change_id", "string", "变更 id"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.change_kind", "string", "变更类型"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标角色"),
        AnalysisEventField("result.requested_amount", "float", "请求量"),
        AnalysisEventField("result.effective_amount", "float", "实际生效量"),
        AnalysisEventField("result.unapplied_amount", "float", "未生效量"),
        AnalysisEventField("result.energy_before", "float", "能量前值"),
        AnalysisEventField("result.energy_after", "float", "能量后值"),
        AnalysisEventField("result.capacity", "float", "能量上限"),
        AnalysisEventField("result.delta", "float", "能量变化量"),
    ),
    "CHARACTER_ENERGY_CHANGED": (
        AnalysisEventField("result.change_id", "string", "变更 id"),
        AnalysisEventField("result.frame", "int", "结算帧"),
        AnalysisEventField("result.change_kind", "string", "变更类型"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标角色"),
        AnalysisEventField("result.requested_amount", "float", "请求量"),
        AnalysisEventField("result.effective_amount", "float", "实际生效量"),
        AnalysisEventField("result.unapplied_amount", "float", "未生效量"),
        AnalysisEventField("result.energy_before", "float", "能量前值"),
        AnalysisEventField("result.energy_after", "float", "能量后值"),
        AnalysisEventField("result.capacity", "float", "能量上限"),
        AnalysisEventField("result.delta", "float", "能量变化量"),
    ),
    # ── 状态效果 ──
    "BUFF_APPLIED": (
        AnalysisEventField("result.instance_ref", "string", "Buff 实例引用"),
        AnalysisEventField("result.definition_key", "string", "Buff 定义 key"),
        AnalysisEventField("result.instance_ref.sequence", "int", "Buff 实例序号"),
        AnalysisEventField("result.frame", "int", "施加帧"),
        AnalysisEventField("result.outcome", "string", "应用结果"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标主体"),
        AnalysisEventField("result.applier_ref.entity_id", "string", "施加者"),
        AnalysisEventField("result.stacks_before", "int", "层数前值"),
        AnalysisEventField("result.stacks_after", "int", "层数后值"),
        AnalysisEventField("result.expires_at_before", "int", "到期帧前值"),
        AnalysisEventField("result.expires_at_after", "int", "到期帧后值"),
    ),
    "BUFF_REMOVED": (
        AnalysisEventField("result.instance_ref", "string", "Buff 实例引用"),
        AnalysisEventField("result.definition_key", "string", "Buff 定义 key"),
        AnalysisEventField("result.instance_ref.sequence", "int", "Buff 实例序号"),
        AnalysisEventField("result.frame", "int", "移除帧"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.target_ref.entity_id", "string", "目标主体"),
        AnalysisEventField("result.applier_ref.entity_id", "string", "施加者"),
        AnalysisEventField("result.reason", "string", "移除原因"),
        AnalysisEventField("result.stack_count", "int", "移除时层数"),
        AnalysisEventField("result.scheduled_expires_at_frame", "int", "计划到期帧"),
    ),
    "INFUSION_APPLIED": (
        AnalysisEventField("result.instance_ref.sequence", "int", "附魔实例序号"),
        AnalysisEventField("result.definition_key", "string", "附魔定义 key"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.mode", "string", "附魔模式"),
        AnalysisEventField("result.element", "string", "附魔元素", "enum:element"),
        AnalysisEventField("result.character_ref.entity_id", "string", "附魔角色"),
        AnalysisEventField("result.frame", "int", "施加帧"),
        AnalysisEventField("result.outcome", "string", "应用结果"),
        AnalysisEventField("result.expires_at_before", "int", "到期帧前值"),
        AnalysisEventField("result.expires_at_after", "int", "到期帧后值"),
        AnalysisEventField("result.next_refresh_frame_after", "int", "下次刷新帧"),
    ),
    "INFUSION_REMOVED": (
        AnalysisEventField("result.instance_ref.sequence", "int", "附魔实例序号"),
        AnalysisEventField("result.definition_key", "string", "附魔定义 key"),
        AnalysisEventField("result.mechanic_key", "string", "机制 key"),
        AnalysisEventField("result.mode", "string", "附魔模式"),
        AnalysisEventField("result.element", "string", "附魔元素", "enum:element"),
        AnalysisEventField("result.character_ref.entity_id", "string", "附魔角色"),
        AnalysisEventField("result.frame", "int", "移除帧"),
        AnalysisEventField("result.reason", "string", "移除原因"),
        AnalysisEventField("result.scheduled_expires_at_frame", "int", "计划到期帧"),
    ),
    # ── 冷却与内容状态 ──
    "COOLDOWN_CHANGED": (
        AnalysisEventField("fact_id", "string", "冷却事实 id"),
        AnalysisEventField("fact_kind", "string", "事实类型"),
        AnalysisEventField("frame", "int", "变化帧"),
        AnalysisEventField("ability_key", "string", "能力 key"),
        AnalysisEventField("before_available_charges", "int", "可用次数前值"),
        AnalysisEventField("after_available_charges", "int", "可用次数后值"),
        AnalysisEventField("active_ready_frame", "int", "当前就绪帧"),
        AnalysisEventField("queued_recoveries", "int", "排队恢复数"),
        AnalysisEventField("subject_ref.subject_id", "string", "冷却主体"),
        AnalysisEventField("source_ref", "string", "来源"),
    ),
    "CONTENT_STATE_CHANGED": (
        AnalysisEventField("frame", "int", "变化帧"),
        AnalysisEventField("owner_ref", "string", "宿主"),
        AnalysisEventField("state_key", "string", "状态段 key"),
    ),
    # ── 元素与反应 ──
    "AURA_ICD_RESOLVED": (
        AnalysisEventField("request_id", "string", "请求 id"),
        AnalysisEventField("impact_ref", "string", "影响引用"),
        AnalysisEventField("order", "int", "顺序"),
        AnalysisEventField("outcome", "string", "ICD 结果"),
        AnalysisEventField("allows_application", "bool", "是否允许附着"),
        AnalysisEventField("tag_key", "string", "附着标签"),
        AnalysisEventField("sequence_key", "string", "序列 key"),
        AnalysisEventField("attacker_ref.scope_key", "string", "攻击方"),
        AnalysisEventField("defender_ref.entity_id", "string", "防守方"),
    ),
    "AURA_APPLIED": (
        AnalysisEventField("request_id", "string", "请求 id"),
        AnalysisEventField("application_id", "string", "附着 id"),
        AnalysisEventField("subject_ref", "string", "主体实体 id"),
        AnalysisEventField("aura_kind", "string", "元素类型", "enum:element"),
        AnalysisEventField("outcome", "string", "附着结果"),
        AnalysisEventField("amount_after.decimal", "float", "附着后元素量"),
    ),
    "AURA_DEPLETED": (
        AnalysisEventField("interaction_id", "string", "交互 id"),
        AnalysisEventField("subject_ref", "string", "主体实体 id"),
        AnalysisEventField("aura_kind", "string", "元素类型", "enum:element"),
        AnalysisEventField("amount_before.decimal", "float", "消耗前元素量"),
        AnalysisEventField("amount_after.decimal", "float", "消耗后元素量"),
    ),
    "AURA_INTERACTION_RESOLVED": (
        AnalysisEventField("interaction_id", "string", "交互 id"),
        AnalysisEventField("subject_ref", "string", "主体实体 id"),
        AnalysisEventField("aura_kind", "string", "元素类型", "enum:element"),
        AnalysisEventField("amount_before.decimal", "float", "交互前元素量"),
        AnalysisEventField("amount_consumed.decimal", "float", "消耗元素量"),
        AnalysisEventField("amount_after.decimal", "float", "交互后元素量"),
    ),
    "REACTION_STATE_CHANGED": (
        AnalysisEventField("slot", "string", "状态槽"),
        AnalysisEventField("scope_key", "string", "作用域 key"),
        AnalysisEventField("subject.kind", "string", "主体类型"),
        AnalysisEventField("subject.entity_id", "string", "主体实体 id"),
    ),
    "REACTION_OCCURRED": (
        AnalysisEventField("occurrence_ref", "string", "反应发生引用"),
        AnalysisEventField("parent_occurrence_ref", "string", "父反应引用"),
        AnalysisEventField("interaction_id", "string", "交互 id"),
        AnalysisEventField("reaction_key", "string", "反应 key"),
        AnalysisEventField("direction_key", "string", "反应方向 key"),
        AnalysisEventField("profile_key", "string", "反应档案 key"),
    ),
    # 该 payload 含 40+ 键与大量嵌套决策步骤，只登记批次级标量，其余保持手动路径。
    "ELEMENTAL_INTERACTION_RESOLVED": (
        AnalysisEventField("batch_id", "string", "批次 id"),
        AnalysisEventField("settlement_round", "int", "结算轮次"),
        AnalysisEventField("batch_kind", "string", "批次类型"),
        AnalysisEventField("scheduled_tick_index", "int", "计划 tick 序号"),
        AnalysisEventField("scheduled_root_outcome", "string", "计划根结果"),
    ),
    # ── 动作、队伍与场景 ──
    "ACTION_STARTED": (
        AnalysisEventField("instance_id", "int", "动作实例 id"),
        AnalysisEventField("frame", "int", "开始帧"),
        AnalysisEventField("action_key", "string", "动作 key"),
        AnalysisEventField("owner_slot", "int", "拥有者槽位"),
        AnalysisEventField("ability_key", "string", "能力 key"),
    ),
    "TEAM_SWITCHED": (
        AnalysisEventField("requested_slot", "int", "请求槽位"),
        AnalysisEventField("previous_slot", "int", "原槽位"),
        AnalysisEventField("active_slot", "int", "当前槽位"),
        AnalysisEventField("accepted", "bool", "是否接受"),
        AnalysisEventField("status", "string", "切换状态"),
    ),
    "RESONANCE_ACTIVATED": (
        AnalysisEventField("team_size", "int", "队伍人数"),
        AnalysisEventField("established_frame", "int", "成立帧"),
    ),
    "MOONSIGN_LEVEL_SET": (
        AnalysisEventField("level", "string", "月兆等级"),
        AnalysisEventField("established_frame", "int", "成立帧"),
    ),
    "MOONSIGN_BONUS_APPLIED": (
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("source_ref", "string", "来源"),
        AnalysisEventField("value", "float", "增伤值"),
        AnalysisEventField("expires_at_frame", "int", "到期帧"),
    ),
    "MOONSIGN_BONUS_EXPIRED": (
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("source_ref", "string", "来源"),
        AnalysisEventField("value", "float", "增伤值"),
    ),
    "MOVEMENT_COLLIDED": (
        AnalysisEventField("entity_id", "string", "实体 id"),
        AnalysisEventField("frame", "int", "帧"),
    ),
    "MOVEMENT_LANDED": (
        AnalysisEventField("entity_id", "string", "实体 id"),
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("fall_start_frame", "int", "下落起始帧"),
        AnalysisEventField("fall_height", "float", "下落高度"),
    ),
    "SPACE_ENTITY_CREATED": (
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("entity.entity_id", "string", "实体 id"),
        AnalysisEventField("entity.kind", "string", "实体类型"),
        AnalysisEventField("entity.active_slot", "int", "归属槽位"),
        AnalysisEventField("entity.owner_key", "string", "拥有者 key"),
        AnalysisEventField("entity.source_key", "string", "来源 key"),
        AnalysisEventField("entity.position.x", "float", "位置 X"),
        AnalysisEventField("entity.position.y", "float", "位置 Y"),
        AnalysisEventField("entity.position.z", "float", "位置 Z"),
    ),
    "SPACE_ENTITY_REMOVED": (
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("entity.entity_id", "string", "实体 id"),
        AnalysisEventField("entity.kind", "string", "实体类型"),
        AnalysisEventField("entity.active_slot", "int", "归属槽位"),
        AnalysisEventField("entity.owner_key", "string", "拥有者 key"),
        AnalysisEventField("entity.source_key", "string", "来源 key"),
        AnalysisEventField("entity.position.x", "float", "位置 X"),
        AnalysisEventField("entity.position.y", "float", "位置 Y"),
        AnalysisEventField("entity.position.z", "float", "位置 Z"),
    ),
    "ATTRIBUTE_PANEL_CHANGED": (
        AnalysisEventField("frame", "int", "帧"),
        AnalysisEventField("subject_ref.entity_id", "string", "主体实体 id"),
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

_ARTIFACT_STAT_LABELS: dict[str, str] = {
    "hp_percent": "生命值%",
    "atk_percent": "攻击力%",
    "def_percent": "防御力%",
    "flat_hp": "固定生命值",
    "flat_atk": "固定攻击力",
    "flat_def": "固定防御力",
    "crit_rate": "暴击率",
    "crit_damage": "暴击伤害",
    "elemental_mastery": "元素精通",
    "energy_recharge": "元素充能效率",
    "healing_bonus": "治疗加成",
    "physical_damage_bonus": "物理伤害加成",
    "pyro_damage_bonus": "火元素伤害加成",
    "hydro_damage_bonus": "水元素伤害加成",
    "electro_damage_bonus": "雷元素伤害加成",
    "cryo_damage_bonus": "冰元素伤害加成",
    "anemo_damage_bonus": "风元素伤害加成",
    "geo_damage_bonus": "岩元素伤害加成",
    "dendro_damage_bonus": "草元素伤害加成",
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

    def list_(key: str, label: str, children: tuple[AnalysisSchemaNode, ...]) -> AnalysisSchemaNode:
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
    stats = object_(
        "stats",
        "属性",
        tuple(
            scalar(
                stat_key,
                stat_label,
                "float",
                template=f"artifact_{{{0}}}_{stat_key}",
            )
            for stat_key, stat_label in _ARTIFACT_STAT_LABELS.items()
        ),
    )
    team = list_(
        "team",
        "队伍",
        (character, weapon, object_("artifacts", "圣遗物", (sets, stats))),
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
