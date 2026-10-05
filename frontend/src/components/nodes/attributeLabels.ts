/** 属性键显示名：与后端 core/attributes/keys.py 的公共属性键稳定契约对应；未知键回退原样。 */

export const ATTRIBUTE_LABELS: Record<string, string> = {
  "stat.hp.base": "基础生命值",
  "stat.hp.max": "生命值上限",
  "stat.atk.base": "基础攻击力",
  "stat.atk.total": "攻击力",
  "stat.def.base": "基础防御力",
  "stat.def.total": "防御力",
  "stat.crit_rate": "暴击率",
  "stat.crit_damage": "暴击伤害",
  "stat.elemental_mastery": "元素精通",
  "stat.energy_recharge": "元素充能效率",
  "bonus.healing.outgoing": "治疗加成",
  "bonus.healing.incoming": "受治疗加成",
  "bonus.shield.strength": "护盾强效",
  "bonus.damage.physical": "物理伤害加成",
  "bonus.damage.pyro": "火元素伤害加成",
  "bonus.damage.hydro": "水元素伤害加成",
  "bonus.damage.electro": "雷元素伤害加成",
  "bonus.damage.cryo": "冰元素伤害加成",
  "bonus.damage.anemo": "风元素伤害加成",
  "bonus.damage.geo": "岩元素伤害加成",
  "bonus.damage.dendro": "草元素伤害加成",
  "resistance.physical": "物理抗性",
  "resistance.pyro": "火元素抗性",
  "resistance.hydro": "水元素抗性",
  "resistance.electro": "雷元素抗性",
  "resistance.cryo": "冰元素抗性",
  "resistance.anemo": "风元素抗性",
  "resistance.geo": "岩元素抗性",
  "resistance.dendro": "草元素抗性",
};

/** 属性修饰阶段显示名：与后端 ModifierStage 枚举对应。 */
export const ATTRIBUTE_STAGE_LABELS: Record<string, string> = {
  base_add: "基础值加成",
  percent_add: "百分比加成",
  flat_add: "固定值加成",
  final_multiplier: "最终乘区",
  override: "覆盖",
};

/** 属性键显示名；未收录键返回原键名。 */
export function attributeLabel(key: string): string {
  return ATTRIBUTE_LABELS[key] ?? key;
}
