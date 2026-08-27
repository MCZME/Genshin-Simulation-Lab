export const ELEMENT_LABELS: Record<string, string> = {
  anemo: "风",
  cryo: "冰",
  dendro: "草",
  electro: "雷",
  geo: "岩",
  hydro: "水",
  physical: "物理",
  pyro: "火",
};

export const ELEMENT_COLORS: Record<string, string> = {
  anemo: "#10b981",
  cryo: "#22d3ee",
  dendro: "#84cc16",
  electro: "#a855f7",
  geo: "#f59e0b",
  hydro: "#3b82f6",
  physical: "#cbd5e1",
  pyro: "#ef4444",
};

export const WEAPON_LABELS: Record<string, string> = {
  bow: "弓",
  catalyst: "法器",
  claymore: "双手剑",
  polearm: "长柄",
  sword: "单手剑",
};

export const RUN_STATE_LABELS: Record<string, string> = {
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  SIMULATION_STARTED: "模拟开始",
  SIMULATION_ENDED: "模拟结束",
  FRAME_STARTED: "帧开始",
  FRAME_ENDED: "帧结束",
  INPUT_KEY_RECEIVED: "收到按键",
  INPUT_SESSION_BOUNDARY_REACHED: "输入会话边界",
  DAMAGE_RESOLVED: "伤害结算",
  HEALING_RESOLVED: "治疗结算",
  CHARACTER_HEALTH_CHANGED: "生命值变化",
  CHARACTER_MAX_HP_CHANGED: "最大生命值变化",
  SHIELD_GRANTED: "护盾施加",
  SHIELD_CAPACITY_CHANGED: "护盾量变化",
  SHIELD_REMOVED: "护盾移除",
  SHIELD_ABSORPTION_RESOLVED: "护盾吸收结算",
  DAMAGE_APPLIED: "承伤结算",
  BUFF_APPLIED: "Buff 施加",
  BUFF_REMOVED: "Buff 移除",
  INFUSION_APPLIED: "附魔施加",
  INFUSION_REMOVED: "附魔移除",
  ENERGY_PICKUP_SPAWNED: "能量微粒生成",
  ENERGY_PICKUP_SETTLED: "能量微粒结算",
  DIRECT_ENERGY_CHANGE_RESOLVED: "直接能量变化结算",
  CHARACTER_ENERGY_CHANGED: "能量变化",
  AURA_ICD_RESOLVED: "附着 ICD 结算",
  AURA_APPLIED: "元素附着",
  AURA_DEPLETED: "附着耗尽",
  AURA_INTERACTION_RESOLVED: "附着交互结算",
  REACTION_STATE_CHANGED: "反应状态变化",
  REACTION_OCCURRED: "反应发生",
  ELEMENTAL_INTERACTION_RESOLVED: "元素交互结算",
  MOVEMENT_COLLIDED: "碰撞",
  MOVEMENT_LANDED: "落地",
  RESONANCE_ACTIVATED: "元素共鸣激活",
  ACTION_STARTED: "动作开始",
  MOONSIGN_LEVEL_SET: "月曜等级设置",
  MOONSIGN_BONUS_APPLIED: "月曜加成施加",
  MOONSIGN_BONUS_EXPIRED: "月曜加成到期",
  TEAM_SWITCHED: "切换角色",
  COOLDOWN_CHANGED: "冷却变化",
  CONTENT_STATE_CHANGED: "内容状态变化",
  SPACE_ENTITY_CREATED: "空间实体创建",
  SPACE_ENTITY_REMOVED: "空间实体移除",
  ATTRIBUTE_PANEL_CHANGED: "属性面板变化",
};

export const DAMAGE_TYPE_LABELS: Record<string, string> = {
  general: "常规伤害",
  catalyze_reaction: "激化反应",
  transformative_reaction: "剧变反应",
  lunar_reaction: "月曜反应",
};
