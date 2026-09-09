/**
 * 与后端对齐的输入词汇表：圣遗物词条、目标抗性元素、角色天赋键。
 * 词汇表是 registry 校验与扫描维度注册表的共同事实源，单独成模块避免循环依赖。
 */

/** 角色天赋键；与后端天赋字段保持一致。 */
export const TALENT_KEYS: readonly string[] = [
  "normal_attack",
  "elemental_skill",
  "elemental_burst",
];

export const TALENT_KEY_LABELS: Record<string, string> = {
  normal_attack: "普通攻击",
  elemental_skill: "元素战技",
  elemental_burst: "元素爆发",
};

/** 目标抗性支持的 8 个元素键；与后端 RESISTANCE_KEYS_BY_ELEMENT 保持一致。 */
export const RESISTANCE_ELEMENT_KEYS: readonly string[] = [
  "physical",
  "pyro",
  "hydro",
  "electro",
  "cryo",
  "anemo",
  "geo",
  "dendro",
];

/** 圣遗物总词条配置词汇表；与后端 ARTIFACT_STAT_KEYS 保持一致。 */
export const ARTIFACT_STAT_KEYS: readonly string[] = [
  "hp_percent",
  "atk_percent",
  "def_percent",
  "flat_hp",
  "flat_atk",
  "flat_def",
  "crit_rate",
  "crit_damage",
  "elemental_mastery",
  "energy_recharge",
  "healing_bonus",
  "physical_damage_bonus",
  "pyro_damage_bonus",
  "hydro_damage_bonus",
  "electro_damage_bonus",
  "cryo_damage_bonus",
  "anemo_damage_bonus",
  "geo_damage_bonus",
  "dendro_damage_bonus",
];

/** 按原值输入、不做百分比换算的圣遗物词条。 */
export const ARTIFACT_RAW_STAT_KEYS: readonly string[] = [
  "flat_hp",
  "flat_atk",
  "flat_def",
  "elemental_mastery",
];

/** 圣遗物词条中文标签。 */
export const ARTIFACT_STAT_LABELS: Record<string, string> = {
  hp_percent: "生命值%",
  atk_percent: "攻击力%",
  def_percent: "防御力%",
  flat_hp: "固定生命值",
  flat_atk: "固定攻击力",
  flat_def: "固定防御力",
  crit_rate: "暴击率",
  crit_damage: "暴击伤害",
  elemental_mastery: "元素精通",
  energy_recharge: "元素充能效率",
  healing_bonus: "治疗加成",
  physical_damage_bonus: "物理伤害加成",
  pyro_damage_bonus: "火元素伤害加成",
  hydro_damage_bonus: "水元素伤害加成",
  electro_damage_bonus: "雷元素伤害加成",
  cryo_damage_bonus: "冰元素伤害加成",
  anemo_damage_bonus: "风元素伤害加成",
  geo_damage_bonus: "岩元素伤害加成",
  dendro_damage_bonus: "草元素伤害加成",
};
