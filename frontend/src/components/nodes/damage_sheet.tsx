/** 伤害结算单：乘法链 + 公式区/修饰项抽屉（伤害详情节点卡内容区）。 */

import { useState } from "react";
import type { EventDetailResponse } from "../../api/client";
import { COLORS } from "../../theme/tokens";
import { attributeLabel } from "./attributeLabels";

/** 元素显示名；键与后端 Element 枚举值对应，未知值显示原样。 */
const ELEMENT_LABELS: Record<string, string> = {
  physical: "物理",
  pyro: "火",
  hydro: "水",
  electro: "雷",
  cryo: "冰",
  anemo: "风",
  geo: "岩",
  dendro: "草",
};

/** 伤害公式显示名；键与后端 formula_key 常量对应。 */
const FORMULA_KEY_LABELS: Record<string, string> = {
  "damage_formula.general": "直伤",
  "damage_formula.transformative_reaction": "剧变",
  "damage_formula.lunar_reaction": "月曜反应",
  "damage_formula.stellar_reaction": "星烁反应",
};

/** 反应族显示名；键取 reaction_profile.<family> 的第二段，未知族回退完整 profile key。 */
const REACTION_LABELS: Record<string, string> = {
  vaporize: "蒸发",
  melt: "融化",
  overloaded: "超载",
  electro_charged: "感电",
  superconduct: "超导",
  swirl: "扩散",
  burning: "燃烧",
  frozen: "冻结",
  shattered: "碎冰",
  crystallize: "结晶",
  bloom: "绽放",
  bloom_explosion: "绽放爆炸",
  hyperbloom: "超绽放",
  burgeon: "烈绽放",
  quicken: "原激化",
  aggravate: "超激化",
  spread: "蔓激化",
  lunar_electro_charged: "月曜感电",
  lunar_crystallize: "月曜结晶",
  lunar_bloom: "月曜绽放",
  stellar_conduct: "星超导",
  stellar_swirl: "星扩散",
};

type ChainSegmentId =
  | "base"
  | "bonus"
  | "crit"
  | "reaction"
  | "defense"
  | "resistance"
  | "ascension"
  | "debug";

interface ChainSegment {
  id: ChainSegmentId;
  label: string;
  valueLabel: string;
  tone?: "crit" | "dim";
  /** hover 提示：该步的累计轨迹（前值 × 乘数 = 后值）。 */
  title: string;
}

interface ReactionBadge {
  label: string;
  key: string;
}

/**
 * 星烁伤害没有 reaction_profile_key：反应身份由主攻击标签承载，取值与后端
 * application/assembly/damage_profiles.py 的星烁 DamageProfile 注册一致。
 * 反应复合（星扩散）与角色直伤（星超导/星扩散）共用同一套标签。
 */
const STELLAR_ATTACK_TAG_FAMILIES: Record<string, string> = {
  "星超导冰": "stellar_conduct",
  "星超导雷": "stellar_conduct",
  "星扩散风": "stellar_swirl",
  "星扩散冰": "stellar_swirl",
};

/** 从 reaction_profile.<family>.* 提取反应族名。 */
function reactionProfileFamily(profileKey: string): string | null {
  const parts = profileKey.split(".");
  return parts.length >= 2 ? parts[1] : null;
}

/** 星烁反应族 profile key：按主攻击标签反查；无星烁载荷或标签未知时返回 null。 */
function stellarReactionProfileKey(summary: Record<string, unknown>): string | null {
  if (!isRecord(summary.stellar_reaction)) {
    return null;
  }
  const tag = readString(summary, "main_attack_tag");
  const family = tag === null ? undefined : STELLAR_ATTACK_TAG_FAMILIES[tag];
  return family === undefined ? null : `reaction_profile.${family}`;
}

/** 反应显示名：按族映射，未知族回退完整 profile key。 */
function reactionLabel(profileKey: string | null): string | null {
  if (profileKey === null) {
    return null;
  }
  const family = reactionProfileFamily(profileKey);
  return family !== null && REACTION_LABELS[family] !== undefined
    ? REACTION_LABELS[family]
    : profileKey;
}

/** 从摘要收集本次伤害发生的反应徽标：激化 → 月曜 → 星烁 → 主反应（增幅/剧变）+ 二次增幅。 */
function collectReactionBadges(summary: Record<string, unknown>): ReactionBadge[] {
  const catalyze = isRecord(summary.catalyze_reaction) ? summary.catalyze_reaction : null;
  const catalyzeKey = readString(catalyze ?? {}, "reaction_profile_key");
  if (catalyzeKey !== null) {
    return [{ label: reactionLabel(catalyzeKey) ?? catalyzeKey, key: catalyzeKey }];
  }
  const lunar = isRecord(summary.lunar_reaction)
    ? readRecord(summary.lunar_reaction, "reaction")
    : null;
  const lunarKey = readString(lunar ?? {}, "reaction_profile_key");
  if (lunarKey !== null) {
    return [{ label: reactionLabel(lunarKey) ?? lunarKey, key: lunarKey }];
  }
  const stellarKey = stellarReactionProfileKey(summary);
  if (stellarKey !== null) {
    return [{ label: reactionLabel(stellarKey) ?? stellarKey, key: stellarKey }];
  }
  const reaction = isRecord(summary.reaction) ? summary.reaction : null;
  const badges: ReactionBadge[] = [];
  const reactionKey = readString(reaction ?? {}, "reaction_profile_key");
  if (reactionKey !== null) {
    badges.push({ label: reactionLabel(reactionKey) ?? reactionKey, key: reactionKey });
  }
  const secondary = isRecord(summary.secondary_amplifying_reaction)
    ? summary.secondary_amplifying_reaction
    : null;
  const secondaryKey = readString(secondary ?? {}, "reaction_profile_key");
  if (secondaryKey !== null && !badges.some((badge) => badge.key === secondaryKey)) {
    badges.push({ label: reactionLabel(secondaryKey) ?? secondaryKey, key: secondaryKey });
  }
  return badges;
}

/** 按运行输入快照组装的会话实体表解析实体引用；未知引用回退原 entity_id。 */
function resolveEntityName(event: EventDetailResponse, ref: string | null): string | null {
  if (ref === null) {
    return null;
  }
  if (ref.startsWith("character:slot_")) {
    const slot = Number(ref.slice("character:slot_".length));
    const found = event.entities?.characters?.find((item) => item.slot === slot);
    if (found !== undefined && found.name !== "") {
      return found.name;
    }
    return Number.isFinite(slot) ? `${slot} 号位角色` : ref;
  }
  if (ref.startsWith("target:")) {
    const id = ref.slice("target:".length);
    const found = event.entities?.targets?.find((item) => item.id === id);
    if (found !== undefined && found.label !== "") {
      return found.label;
    }
    return id || ref;
  }
  return ref;
}

function ContextBar({
  event,
  summary,
}: {
  event: EventDetailResponse;
  summary: Record<string, unknown>;
}) {
  const element = readString(summary, "element");
  const formulaKey = readString(summary, "formula_key");
  const damageName = readString(summary, "damage_name");
  const elementLabel = element === null ? null : ELEMENT_LABELS[element] ?? element;
  const elementColor =
    element === null
      ? COLORS.textMuted
      : COLORS.element[element as keyof typeof COLORS.element] ?? COLORS.textMuted;
  const sourceRef = readString(summary, "source_ref") ?? "—";
  const targetRef = readString(summary, "target_ref") ?? "—";
  const sourceName = resolveEntityName(event, readString(summary, "source_ref")) ?? sourceRef;
  const targetName = resolveEntityName(event, readString(summary, "target_ref")) ?? targetRef;
  const reactionBadges = collectReactionBadges(summary);
  return (
    <div className="damage-sheet-context">
      {elementLabel !== null && (
        <span
          className="damage-sheet-element-badge"
          style={{ background: elementColor }}
          title={element ?? undefined}
        >
          {elementLabel}
        </span>
      )}
      <span
        className="damage-sheet-context-name"
        style={{ color: elementColor }}
        title={formulaKey !== null ? FORMULA_KEY_LABELS[formulaKey] ?? formulaKey : undefined}
      >
        {damageName ?? "伤害"}
      </span>
      {reactionBadges.map((badge) => (
        <span className="damage-sheet-reaction-badge" key={badge.key} title={badge.key}>
          {badge.label}
        </span>
      ))}
      <span className="damage-sheet-context-frame">帧 {event.frame}</span>
      <span className="damage-sheet-context-refs" title={`${sourceRef} → ${targetRef}`}>
        {sourceName} → {targetName}
      </span>
    </div>
  );
}

/** 按结算摘要动态生成乘法链段；缺失或不适用的乘区整段省略，乘数为 1 的乘区无信息量同样省略（剧变/月曜路径恒为 1）。 */
function buildChainSegments(summary: Record<string, unknown>): ChainSegment[] {
  const segments: ChainSegment[] = [];
  const base = readNumber(summary, "base_damage");
  let running = base ?? 0;
  if (base !== null) {
    segments.push({
      id: "base",
      label: "基础",
      valueLabel: formatDamage(base),
      title: `基础伤害 ${formatDamage(base)}`,
    });
  }

  const bonus = readNumber(summary, "damage_bonus_multiplier");
  if (bonus !== null && bonus !== 1) {
    running = running * bonus;
    segments.push(multiplierSegment("bonus", "增伤", bonus, running));
  }

  const critOutcome = readString(summary, "crit_outcome");
  const critMultiplier = readNumber(summary, "crit_multiplier");
  if (critOutcome !== "not_applicable" && critMultiplier !== null && critMultiplier !== 1) {
    running = running * critMultiplier;
    segments.push(
      multiplierSegment("crit", "暴击", critMultiplier, running, "crit"),
    );
  }

  const reactionMultiplier = readNumber(summary, "reaction_multiplier");
  if (reactionMultiplier !== null && reactionMultiplier !== 1) {
    running = running * reactionMultiplier;
    segments.push(
      multiplierSegment("reaction", "反应", reactionMultiplier, running),
    );
  }

  const defense = readNumber(summary, "defense_multiplier");
  if (defense !== null && defense !== 1) {
    running = running * defense;
    segments.push(multiplierSegment("defense", "防御", defense, running, "dim"));
  }

  const resistance = readNumber(summary, "resistance_multiplier");
  if (resistance !== null && resistance !== 1) {
    running = running * resistance;
    segments.push(
      multiplierSegment("resistance", "抗性", resistance, running, "dim"),
    );
  }

  const ascension = ascensionMultiplier(summary);
  if (ascension !== 1) {
    running = running * ascension;
    segments.push(multiplierSegment("ascension", "擢升", ascension, running));
  }

  const debug = readNumber(summary, "debug_multiplier");
  if (debug !== null && debug !== 1) {
    running = running * debug;
    segments.push(multiplierSegment("debug", "调试", debug, running));
  }
  return segments;
}

function multiplierSegment(
  id: ChainSegmentId,
  label: string,
  multiplier: number,
  afterValue: number,
  tone?: "crit" | "dim",
): ChainSegment {
  return {
    id,
    label,
    valueLabel: formatFactor(multiplier),
    tone,
    title: `${formatDamage(afterValue / multiplier)} × ${formatFactor(multiplier)} = ${formatDamage(afterValue)}`,
  };
}

function FinalRow({ summary }: { summary: Record<string, unknown> }) {
  const finalDamage = readNumber(summary, "final_damage");
  if (finalDamage === null) {
    return null;
  }
  const isCritical = readString(summary, "crit_outcome") === "critical";
  const debugMultiplier = readNumber(summary, "debug_multiplier");
  const official = readNumber(summary, "official_damage");
  return (
    <div className="damage-sheet-total">
      <span className="damage-sheet-total-eq">=</span>
      <span
        className={`damage-sheet-total-value ${isCritical ? "damage-sheet-total-value--crit" : ""}`}
      >
        {formatDamage(finalDamage)}
      </span>
      {isCritical && <span className="damage-sheet-total-badge">暴击</span>}
      {debugMultiplier !== null && debugMultiplier !== 1 && official !== null && (
        <span className="damage-sheet-total-official" title="不含调试倍率的正式公式伤害">
          正式公式 {formatDamage(official)}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 链段详情：公式区（骨架 + 可修饰槽位）与修饰项抽屉
// ---------------------------------------------------------------------------

type FormulaToken =
  | { kind: "text"; text: string }
  | { kind: "muted"; text: string }
  | { kind: "slot"; slotId: string; label: string }
  | { kind: "result"; text: string };

interface SlotRow {
  label: string;
  value: string;
  rejected?: boolean;
  /** 基础值行：属性/请求来源的合成起点，与效果词条行视觉区分。 */
  base?: boolean;
  title?: string;
}

interface SlotDrawerData {
  id: string;
  title: string;
  total: string;
  rows: SlotRow[];
}

interface ZoneDetailModel {
  /** 乘区顶部显示名（如伤害名），可为空。 */
  title: string | null;
  lines: FormulaToken[][];
  drawers: SlotDrawerData[];
  note: string | null;
}

/** 固定值类伤害修饰阶段：显示数值而非百分比。 */
const FLAT_STAGES = new Set([
  "base_damage_flat_add",
  "component_coefficient_flat_add",
  "stellar_base_multiplier_add",
  "stellar_feather_addition_add",
  "lunar_additional_base_damage_add",
]);

/** 伤害修饰阶段是否为固定值类；固定值显示数值，其余按比例显示百分比。 */
function isFlatStage(stage: string): boolean {
  return FLAT_STAGES.has(stage);
}

/** 面板读取阶段：来自属性系统的面板值，作为槽位账单的基础贡献。 */
function isPanelStage(stage: string): boolean {
  return stage.startsWith("panel_");
}

interface SpecialtyDrawerSpec {
  id: string;
  title: string;
  stage: string;
}

/**
 * 基础区专属位置：月曜/星烁把基础系数、基础增伤、反应加成、大权区、羽毛区与附加伤害
 * 折进基础区括号值（`base_damage`），因此账单归入基础区抽屉呈现。
 */
const BASE_SPECIALTY_DRAWERS: readonly SpecialtyDrawerSpec[] = [
  { id: "base-stellar-base-multiplier", title: "星烁基础系数", stage: "stellar_base_multiplier_add" },
  { id: "base-stellar-base-bonus", title: "星烁基础增伤", stage: "stellar_base_bonus_add" },
  { id: "base-stellar-reaction-bonus", title: "星烁反应加成", stage: "stellar_reaction_bonus_add" },
  { id: "base-stellar-authority", title: "星烁大权区", stage: "stellar_authority_multiplier_add" },
  { id: "base-stellar-feather", title: "星烁羽毛区", stage: "stellar_feather_addition_add" },
  { id: "base-lunar-base-bonus", title: "月曜基础伤害提升", stage: "lunar_base_damage_bonus_add" },
  { id: "base-lunar-reaction-bonus", title: "月曜反应加成", stage: "lunar_reaction_bonus_add" },
  { id: "base-lunar-additional", title: "月曜附加基础伤害", stage: "lunar_additional_base_damage_add" },
];

/** 按阶段收集生效/未生效词条并生成抽屉；无词条时不生成空抽屉。 */
function specialtyDrawer(
  applied: Record<string, unknown>[],
  rejected: Record<string, unknown>[],
  spec: SpecialtyDrawerSpec,
): SlotDrawerData | null {
  const collected = collectSlotTerms(applied, rejected, spec.stage, null);
  const rows = [
    ...collected.rows,
    ...collected.rejectedRows.map((row) => ({ ...row, rejected: true })),
  ];
  if (rows.length === 0) {
    return null;
  }
  return {
    id: spec.id,
    title: spec.title,
    total: isFlatStage(spec.stage)
      ? formatNumber(collected.sum)
      : formatSignedPercent(collected.sum),
    rows,
  };
}

/**
 * 月曜/星烁的擢升乘区：扁平结果没有独立字段承载，从公式专属 resolution 取。
 * 复合模式的擢升逐组分不同、没有单一乘数，因此只在直伤模式返回。
 */
function ascensionMultiplier(summary: Record<string, unknown>): number {
  const stellar = readRecord(summary, "stellar_reaction");
  if (stellar !== null && readString(stellar, "mode") === "character_direct") {
    return 1 + (readNumber(stellar, "stellar_ascension_bonus") ?? 0);
  }
  const lunar = readRecord(summary, "lunar_reaction");
  if (lunar !== null) {
    const mode = readString(readRecord(lunar, "reaction") ?? {}, "mode");
    if (mode === "character_direct") {
      const components = readRecordList(lunar, "components");
      const multiplier =
        components.length > 0 ? readNumber(components[0], "ascension_multiplier") : null;
      if (multiplier !== null) {
        return multiplier;
      }
    }
  }
  return 1;
}

/** 面板读取词条的值显示：数值类按原值，增伤/爆伤沿用带符号百分比，率与抗性沿用普通百分比。 */
function panelValueText(stage: string, value: number): string {
  switch (stage) {
    case "panel_attribute_value":
    case "panel_elemental_mastery":
      return formatNumber(value);
    case "panel_element_bonus":
    case "panel_crit_damage":
      return formatSignedPercent(value);
    default:
      return formatPercent(value);
  }
}

/** 面板读取词条显示名；provider_key 形如 panel.<attribute_key>。 */
function panelStageLabel(
  stage: string,
  providerKey: string | null,
  componentKey: string | null,
): string {
  switch (stage) {
    case "panel_attribute_value": {
      const attributeKey = providerKey !== null ? providerKey.replace(/^panel\./, "") : "";
      return `${attributeLabel(attributeKey)}${componentKey !== null ? `（${componentKey}）` : ""}`;
    }
    case "panel_element_bonus":
      return "元素伤害加成";
    case "panel_crit_rate":
      return "面板暴击率";
    case "panel_crit_damage":
      return "面板暴击伤害";
    case "panel_resistance":
      return "目标基础抗性";
    case "panel_elemental_mastery":
      return "元素精通";
    default:
      return providerKey ?? "面板";
  }
}

interface CollectedTerms {
  rows: SlotRow[];
  rejectedRows: SlotRow[];
  sum: number;
}

/** 单条伤害修饰词条 → 抽屉行；面板读取词条渲染为基础值行。 */
function slotRowFromTerm(term: Record<string, unknown>): SlotRow {
  const stage = readString(term, "stage") ?? "";
  const providerKey = readString(term, "provider_key");
  const provider = readString(term, "provider_display_name") ?? providerKey ?? "未知来源";
  const comp = readString(term, "component_key");
  const value = readNumber(term, "value");
  const panel = isPanelStage(stage);
  return {
    label: panel
      ? panelStageLabel(stage, providerKey, comp)
      : comp !== null
        ? `${provider}（${comp}）`
        : provider,
    value:
      value === null
        ? "—"
        : panel
          ? panelValueText(stage, value)
          : isFlatStage(stage)
            ? formatNumber(value)
            : formatSignedPercent(value),
    base: panel || undefined,
    title: providerKey ?? undefined,
  };
}

/** 复合模式（月曜/星烁）单个参与者组分的账本抽屉。 */
interface CompositeComponentLedger {
  id: string;
  title: string;
  total: string;
  rows: SlotRow[];
}

/** 从槽位三段审计里取合并值；没有该槽位返回 null。 */
function slotMergedValue(slots: Record<string, unknown>[], slotKey: string): number | null {
  for (const slot of slots) {
    if (readString(slot, "slot_key") === slotKey) {
      return readNumber(slot, "merged");
    }
  }
  return null;
}

/**
 * 复合模式的逐参与者组分账本：顶层 `applied_terms` 为空，
 * 账单落在各组分审计内（决策 D-047）。每个组分列出基础区、乘区、
 * 组分伤害、权重与该组分自己的词条，使组分内的乘法链可以逐项对账；
 * 顶层扁平字段只取排名第一的组分，无法代表全部参与者。
 */
function compositeComponentLedgers(
  summary: Record<string, unknown>,
  resolveRef: (ref: string) => string,
): CompositeComponentLedger[] {
  const stellar = readRecord(summary, "stellar_reaction");
  const lunar = readRecord(summary, "lunar_reaction");
  const isStellarComposite =
    stellar !== null && readString(stellar, "mode") === "reaction_composite";
  const isLunarComposite =
    lunar !== null &&
    readString(readRecord(lunar, "reaction") ?? {}, "mode") === "reaction_composite";
  const components = isStellarComposite
    ? readRecordList(stellar ?? {}, "components")
    : isLunarComposite
      ? readRecordList(lunar ?? {}, "components")
      : [];
  if (components.length === 0) {
    return [];
  }
  return components.map((component, index) => {
    const rawRef = component.participant_ref;
    const ref =
      typeof rawRef === "string"
        ? rawRef
        : readString(isRecord(rawRef) ? rawRef : {}, "entity_id");
    const slots = readRecordList(component, "slots");
    // 星烁组分的擢升只有槽位三段审计，月曜组分直接带乘数。
    const ascension = isLunarComposite
      ? readNumber(component, "ascension_multiplier")
      : (() => {
          const bonus = slotMergedValue(slots, "stellar_ascension_bonus");
          return bonus === null ? null : 1 + bonus;
        })();
    const rows: SlotRow[] = [];
    const baseDamage = readNumber(
      component,
      isLunarComposite ? "base_damage_after_reaction" : "base_damage",
    );
    if (baseDamage !== null) {
      rows.push({ label: "组分基础区", value: formatDamage(baseDamage), base: true });
    }
    const crit = readNumber(component, "crit_multiplier");
    if (crit !== null && crit !== 1) {
      rows.push({ label: "暴击乘数", value: formatFactor(crit), base: true });
    }
    const resistance = readNumber(component, "resistance_multiplier");
    if (resistance !== null && resistance !== 1) {
      rows.push({ label: "抗性乘数", value: formatFactor(resistance), base: true });
    }
    if (ascension !== null && ascension !== 1) {
      rows.push({ label: "擢升乘数", value: formatFactor(ascension), base: true });
    }
    const componentDamage = readNumber(component, "component_damage");
    if (componentDamage !== null) {
      rows.push({ label: "组分伤害", value: formatDamage(componentDamage), base: true });
    }
    const weight = readNumber(component, "weight");
    if (weight !== null) {
      rows.push({ label: "权重", value: formatNumber(weight), base: true });
    }
    rows.push(
      ...readRecordList(component, "modifier_terms").map(slotRowFromTerm),
      ...readRecordList(component, "panel_terms").map(slotRowFromTerm),
    );
    const weightedDamage = readNumber(component, "weighted_damage");
    return {
      id: `component-${index}`,
      title: `组分 · ${ref === null ? `${index + 1} 号位` : resolveRef(ref)}`,
      total: weightedDamage !== null ? formatDamage(weightedDamage) : "—",
      rows,
    };
  });
}

/** 按阶段（可选按 component）收集生效与被拒词条并汇总生效值。 */
function collectSlotTerms(
  applied: Record<string, unknown>[],
  rejected: Record<string, unknown>[],
  stage: string,
  componentKey: string | null,
): CollectedTerms {
  const match = (term: Record<string, unknown>) =>
    readString(term, "stage") === stage &&
    (componentKey === null || readString(term, "component_key") === componentKey);
  const matchedApplied = applied.filter(match);
  const matchedRejected = rejected.filter(match);
  return {
    rows: matchedApplied.map(slotRowFromTerm),
    rejectedRows: matchedRejected.map(slotRowFromTerm),
    sum: matchedApplied.reduce(
      (total, term) => total + (readNumber(term, "value") ?? 0),
      0,
    ),
  };
}

function pushDrawer(
  drawers: SlotDrawerData[],
  id: string,
  title: string,
  total: string,
  rows: SlotRow[],
): void {
  if (rows.length > 0) {
    drawers.push({ id, title, total, rows });
  }
}

/** 槽位有内容（词条或非零基础值）时渲染为可点击胶囊，否则退化为公式中的普通数值。 */
function slotValue(id: string, label: string, hasContent: boolean): FormulaToken {
  return hasContent ? { kind: "slot", slotId: id, label } : { kind: "text", text: label };
}

function buildZoneModel(
  segmentId: ChainSegmentId,
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
  resolveRef: (ref: string) => string,
): ZoneDetailModel {
  switch (segmentId) {
    case "base":
      return buildBaseZone(summary, audit, resolveRef);
    case "bonus":
      return buildBonusZone(summary, audit);
    case "crit":
      return buildCritZone(summary, audit);
    case "reaction":
      return buildReactionZone(summary, audit);
    case "defense":
      return buildDefenseZone(summary, audit);
    case "resistance":
      return buildResistanceZone(summary, audit);
    case "ascension":
      return buildAscensionZone(summary, audit);
    case "debug":
      return { title: "调试区", lines: [], drawers: [], note: "调试倍率不属于正式公式；正式公式伤害见结果行小字" };
  }
}

function buildBaseZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
  resolveRef: (ref: string) => string,
): ZoneDetailModel {
  if (audit === null) {
    return { title: "基础区", lines: [], drawers: [], note: "无审计数据" };
  }
  const applied = readRecordList(audit, "applied_terms");
  const rejected = readRecordList(audit, "rejected_terms");
  const components = readRecordList(audit, "component_results");
  const additions = readRecordList(audit, "base_damage_additions");
  const lines: FormulaToken[][] = [];
  const drawers: SlotDrawerData[] = [];

  const percentRows: SlotRow[] = [];
  const percentSum = { value: 0 };
  const flatRows: SlotRow[] = [];
  const flatSum = { value: 0 };
  const attributeRows: SlotRow[] = [];

  for (const [index, component] of components.entries()) {
    const componentKey = readString(component, "component_key") ?? `#${index + 1}`;
    const attributeKey = readString(component, "attribute_key") ?? "";
    const attributeValue = readNumber(component, "attribute_value");
    const original = readNumber(component, "original_coefficient");
    const percent = collectSlotTerms(applied, rejected, "component_coefficient_percent_add", componentKey);
    const flat = collectSlotTerms(applied, rejected, "component_coefficient_flat_add", componentKey);
    const attributePanel = collectSlotTerms(applied, rejected, "panel_attribute_value", componentKey);
    percentSum.value += percent.sum;
    flatSum.value += flat.sum;
    percentRows.push(...percent.rows, ...percent.rejectedRows.map((row) => ({ ...row, rejected: true })));
    flatRows.push(...flat.rows, ...flat.rejectedRows.map((row) => ({ ...row, rejected: true })));
    if (attributePanel.rows.length > 0 && attributePanel.sum !== 0) {
      attributeRows.push(...attributePanel.rows);
    }

    const tokens: FormulaToken[] = [];
    const attributeSlotHas = attributePanel.rows.length > 0 && attributePanel.sum !== 0;
    if (attributeSlotHas && attributeValue !== null) {
      tokens.push({ kind: "text", text: `${attributeLabel(attributeKey)} ` });
      tokens.push(slotValue("base-attribute", formatNumber(attributeValue), true));
    } else {
      tokens.push({
        kind: "text",
        text: `${attributeLabel(attributeKey)}${attributeValue !== null ? ` ${formatNumber(attributeValue)}` : ""}`,
      });
    }
    if (original !== null) {
      const percentHas = percent.rows.length + percent.rejectedRows.length > 0;
      const flatHas = flat.rows.length + flat.rejectedRows.length > 0;
      tokens.push({ kind: "text", text: " × " });
      if (flatHas) {
        tokens.push({ kind: "text", text: "(" });
      }
      tokens.push({ kind: "text", text: formatPercent(original) });
      if (percentHas) {
        tokens.push({ kind: "text", text: " × (1 + " });
        tokens.push({ kind: "slot", slotId: "base-percent", label: formatPercent(percent.sum) });
        tokens.push({ kind: "text", text: ")" });
      }
      if (flatHas) {
        tokens.push({ kind: "text", text: " + " });
        tokens.push({ kind: "slot", slotId: "base-flat", label: formatNumber(flat.sum) });
        tokens.push({ kind: "text", text: ")" });
      }
    }
    const damage = readNumber(component, "damage");
    if (damage !== null) {
      tokens.push({ kind: "text", text: " =" });
      tokens.push({ kind: "result", text: ` ${formatDamage(damage)}` });
    }
    lines.push(tokens);
  }

  if (percentRows.length > 0) {
    pushDrawer(drawers, "base-percent", "倍率段加成", formatSignedPercent(percentSum.value), percentRows);
  }
  if (flatRows.length > 0) {
    pushDrawer(drawers, "base-flat", "倍率段加值", formatNumber(flatSum.value), flatRows);
  }
  if (attributeRows.length > 0) {
    // 面板属性值按组件分别有意义，跨组件没有可加总的单一值，抽屉头不显示合计。
    pushDrawer(drawers, "base-attribute", "倍率段属性", "—", attributeRows);
  }

  // 固定值加值行：非词条来源的加值（请求固定/激化等）作为基础行，词条加值来自 base_damage_flat_add。
  const termDerivedKeys = new Set(
    applied
      .filter((term) => readString(term, "stage") === "base_damage_flat_add")
      .map((term) => `${readString(term, "provider_key") ?? ""}.base_damage_flat_add`),
  );
  const additionTerms = collectSlotTerms(applied, rejected, "base_damage_flat_add", null);
  const baseAdditionRows: SlotRow[] = additions
    .filter((addition) => !termDerivedKeys.has(readString(addition, "addition_key") ?? ""))
    .map((addition) => {
      const key = readString(addition, "addition_key") ?? "未知加值";
      return {
        label: additionLabel(key),
        base: true,
        value: formatOptionalNumber(readNumber(addition, "value")),
        title: key,
      };
    });
  const additionRows = [
    ...baseAdditionRows,
    ...additionTerms.rows,
    ...additionTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
  ];
  const additionTotal = additions.reduce((total, addition) => total + (readNumber(addition, "value") ?? 0), 0);
  if (additionRows.length > 0) {
    lines.push([
      { kind: "text", text: "+ " },
      slotValue("base-addition", formatDamage(additionTotal), additionTerms.rows.length + additionTerms.rejectedRows.length > 0),
    ]);
    pushDrawer(drawers, "base-addition", "基础伤害加值", formatDamage(additionTotal), additionRows);
  }

  // 月曜/星烁把基础系数、基础增伤、反应加成、大权区、羽毛区与附加伤害折进基础区括号值；
  // 这些专属阶段不在通用公式骨架内，按文档"有账单时按槽位与抽屉规则渲染"落成抽屉。
  for (const spec of BASE_SPECIALTY_DRAWERS) {
    const drawer = specialtyDrawer(applied, rejected, spec);
    if (drawer !== null) {
      drawers.push(drawer);
    }
  }

  // 复合模式（月曜/星烁）的顶层账单为空，账本落在各组分审计内（决策 D-047）。
  for (const ledger of compositeComponentLedgers(summary, resolveRef)) {
    pushDrawer(drawers, ledger.id, ledger.title, ledger.total, ledger.rows);
  }

  // 合计行只在多组件求和或还有加值要加时有信息量；单组件且无加值时组件行结果就是基础伤害。
  if (components.length > 1 || additionRows.length > 0) {
    const base = readNumber(summary, "base_damage");
    if (base !== null && lines.length > 0) {
      lines.push([{ kind: "text", text: "=" }, { kind: "result", text: ` ${formatDamage(base)}` }]);
    }
  } else if (lines.length === 0) {
    // 无倍率组件：剧变按等级系数 × 基础倍率呈现，其余直接呈现基础伤害。
    const base = readNumber(summary, "base_damage");
    const reaction = readRecord(audit, "reaction");
    if (reaction !== null && readString(reaction, "kind") === "transformative" && base !== null) {
      const level = readNumber(reaction, "level_multiplier");
      const baseMultiplier = readNumber(reaction, "base_multiplier");
      lines.push([
        {
          kind: "text",
          text: `${formatOptionalNumber(level)} × ${formatOptionalNumber(baseMultiplier)}`,
        },
        { kind: "result", text: ` = ${formatDamage(base)}` },
      ]);
    } else if (base !== null) {
      lines.push([
        { kind: "text", text: "基础伤害" },
        { kind: "result", text: ` = ${formatDamage(base)}` },
      ]);
    }
  }

  return {
    title: "基础区",
    lines,
    drawers,
    note: null,
  };
}

function additionLabel(key: string): string {
  if (key === "request.flat_base_damage") {
    return "请求固定基础伤害";
  }
  if (key.startsWith("catalyze.")) {
    return "激化基础伤害增加";
  }
  return key;
}

function buildBonusZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = readNumber(summary, "damage_bonus_multiplier");
  const bonus = audit === null ? null : readRecord(audit, "damage_bonus");
  const elementBonus = readNumber(bonus ?? {}, "element_bonus") ?? 0;
  const appliedTerms = audit === null ? [] : readRecordList(audit, "applied_terms");
  const rejectedTerms = audit === null ? [] : readRecordList(audit, "rejected_terms");
  const terms = collectSlotTerms(appliedTerms, rejectedTerms, "damage_bonus_add", null);
  const panelBonus = collectSlotTerms(appliedTerms, rejectedTerms, "panel_element_bonus", null);
  const total = multiplier !== null ? multiplier - 1 : elementBonus + terms.sum;
  const hasContent = elementBonus !== 0 || terms.rows.length + terms.rejectedRows.length > 0;
  const rows: SlotRow[] = [];
  if (panelBonus.rows.length > 0 && panelBonus.sum !== 0) {
    rows.push(...panelBonus.rows);
  } else if (elementBonus !== 0) {
    rows.push({ label: "元素伤害加成", value: formatSignedPercent(elementBonus), base: true });
  }
  rows.push(...terms.rows, ...terms.rejectedRows.map((row) => ({ ...row, rejected: true })));
  const drawers: SlotDrawerData[] = [];
  pushDrawer(drawers, "bonus", "增伤加成", formatSignedPercent(total), rows);
  return {
    title: "增伤区",
    lines: [
      [
        { kind: "text", text: "1 + " },
        slotValue("bonus", formatPercent(total), hasContent),
        ...(multiplier !== null
          ? [{ kind: "result" as const, text: ` = ${formatFactor(multiplier)}` }]
          : []),
      ],
    ],
    drawers,
    note: null,
  };
}

function buildCritZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const critical = audit === null ? null : readRecord(audit, "critical");
  if (critical === null) {
    const multiplier = readNumber(summary, "crit_multiplier");
    const rate = readNumber(summary, "crit_rate");
    return {
      title: "暴击区",
      lines: [
        ...(multiplier !== null
          ? [[{ kind: "result" as const, text: formatFactor(multiplier) }]]
          : []),
        ...(rate !== null
          ? [[{ kind: "text" as const, text: `暴击率 = ${formatPercent(rate)}` }]]
          : []),
      ],
      drawers: [],
      note: null,
    };
  }
  const canCrit = readBoolean(critical, "can_crit");
  const outcome = readString(critical, "outcome");
  const multiplier = readNumber(critical, "multiplier");
  const critDamage = readNumber(critical, "crit_damage") ?? 0;
  const critRate = readNumber(critical, "crit_rate") ?? 0;
  const effectiveRate = readNumber(critical, "effective_crit_rate") ?? 0;
  const appliedTerms = readRecordList(audit ?? {}, "applied_terms");
  const rejectedTerms = readRecordList(audit ?? {}, "rejected_terms");

  const damageTerms = collectSlotTerms(appliedTerms, rejectedTerms, "crit_damage_add", null);
  const rateTerms = collectSlotTerms(appliedTerms, rejectedTerms, "crit_rate_add", null);
  const panelDamage = collectSlotTerms(appliedTerms, rejectedTerms, "panel_crit_damage", null);
  const panelRate = collectSlotTerms(appliedTerms, rejectedTerms, "panel_crit_rate", null);
  const damageBase = critDamage - damageTerms.sum;
  const rateBase = critRate - rateTerms.sum;

  const lines: FormulaToken[][] = [];
  lines.push([
    { kind: "text", text: "1 + " },
    slotValue(
      "crit-damage",
      formatPercent(critDamage),
      damageBase !== 0 || damageTerms.rows.length + damageTerms.rejectedRows.length > 0,
    ),
    ...(multiplier !== null
      ? [{ kind: "result" as const, text: ` = ${formatFactor(multiplier)}` }]
      : []),
    ...(outcome === "non_critical" ? [{ kind: "muted" as const, text: "（未暴击）" }] : []),
  ]);
  if (canCrit) {
    const rateHas = rateBase !== 0 || rateTerms.rows.length + rateTerms.rejectedRows.length > 0;
    lines.push([
      { kind: "text", text: "暴击率 = " },
      slotValue("crit-rate", formatPercent(critRate), rateHas),
      ...(effectiveRate !== critRate
        ? [{ kind: "text" as const, text: ` → 生效 ${formatPercent(effectiveRate)}` }]
        : []),
      ...(outcome !== null
        ? [{ kind: "muted" as const, text: ` · 判定：${formatCritOutcome(outcome)}` }]
        : []),
    ]);
  }

  const drawers: SlotDrawerData[] = [];
  const damageRows: SlotRow[] = [];
  if (panelDamage.rows.length > 0 && panelDamage.sum !== 0) {
    damageRows.push(...panelDamage.rows);
  } else if (damageBase !== 0) {
    damageRows.push({ label: "面板暴击伤害", value: formatSignedPercent(damageBase), base: true });
  }
  damageRows.push(
    ...damageTerms.rows,
    ...damageTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
  );
  pushDrawer(drawers, "crit-damage", "暴击伤害加成", formatSignedPercent(critDamage), damageRows);
  const rateRows: SlotRow[] = [];
  if (panelRate.rows.length > 0 && panelRate.sum !== 0) {
    rateRows.push(...panelRate.rows);
  } else if (rateBase !== 0) {
    rateRows.push({ label: "面板暴击率", value: formatPercent(rateBase), base: true });
  }
  if (effectiveRate !== critRate) {
    rateRows.push({ label: "生效暴击率", value: formatPercent(effectiveRate), base: true });
  }
  rateRows.push(
    ...rateTerms.rows,
    ...rateTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
  );
  pushDrawer(drawers, "crit-rate", "暴击率加成", formatPercent(critRate), rateRows);
  return { title: "暴击区", lines, drawers, note: null };
}

/** 反应区可渲染的乘数骨架类型：增幅与剧变；其余公式的反应明细不在反应乘区。 */
function isReactionMultiplierKind(record: Record<string, unknown> | null): boolean {
  if (record === null) {
    return false;
  }
  const kind = readString(record, "kind");
  return kind === "amplifying" || kind === "transformative";
}

function buildReactionZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = readNumber(summary, "reaction_multiplier");
  const auditReaction = audit === null ? null : readRecord(audit, "reaction");
  const summaryReaction = isRecord(summary.reaction) ? summary.reaction : null;
  // 反应区只渲染增幅/剧变的乘数骨架。审计反应被激化/月曜/星烁占用时，
  // 主反应的乘数载荷仍在摘要里，回退到摘要以免整段公式丢失。
  let record: Record<string, unknown> | null;
  if (auditReaction === null) {
    record = audit === null ? summaryReaction : null;
  } else if (isReactionMultiplierKind(auditReaction)) {
    record = auditReaction;
  } else {
    record = isReactionMultiplierKind(summaryReaction) ? summaryReaction : auditReaction;
  }
  const kind = record === null ? null : readString(record, "kind");
  const appliedTerms = readRecordList(audit ?? {}, "applied_terms");
  const rejectedTerms = readRecordList(audit ?? {}, "rejected_terms");
  const panelMastery = collectSlotTerms(appliedTerms, rejectedTerms, "panel_elemental_mastery", null);
  const lines: FormulaToken[][] = [];
  const drawers: SlotDrawerData[] = [];
  if (record !== null && multiplier !== null) {
    const masteryBonus = readNumber(record, "mastery_bonus");
    const reactionBonus = readNumber(record, "reaction_bonus");
    const elementalMastery = readNumber(record, "elemental_mastery");
    const hasPanelMastery = panelMastery.rows.length > 0 && panelMastery.sum !== 0;
    const masteryHasContent =
      hasPanelMastery || (elementalMastery !== null && elementalMastery !== 0);
    if (kind === "amplifying") {
      const baseMultiplier = readNumber(record, "base_multiplier");
      lines.push(
        reactionFormulaLine({
          prefix: null,
          baseMultiplier,
          masteryBonus,
          reactionBonus,
          reactionBonusSlotId: null,
          multiplier,
          masterySlotId: masteryHasContent ? "reaction-mastery" : null,
        }),
      );
      if (masteryHasContent && masteryBonus !== null && masteryBonus !== 0) {
        const rows: SlotRow[] = [];
        if (hasPanelMastery) {
          rows.push(...panelMastery.rows);
        } else if (elementalMastery !== null) {
          rows.push({ label: "元素精通", value: formatNumber(elementalMastery), base: true });
        }
        rows.push({
          label: "精通加成（由元素精通派生）",
          value: formatSignedPercent(masteryBonus),
          base: true,
        });
        pushDrawer(drawers, "reaction-mastery", "精通加成", formatSignedPercent(masteryBonus), rows);
      }
    } else if (kind === "transformative") {
      // 剧变的反应加成专属阶段（transformative_reaction_bonus_add）由公式在
      // 结算时加到反应乘数上；审计的 reaction_bonus 只是请求级原值，因此这里
      // 把账单合计并入显示值与公式，避免公式行与结尾乘数对不上账。
      const reactionBonusTerms = collectSlotTerms(
        appliedTerms,
        rejectedTerms,
        "transformative_reaction_bonus_add",
        null,
      );
      const reactionBonusTotal = (reactionBonus ?? 0) + reactionBonusTerms.sum;
      const reactionBonusHasSlot =
        reactionBonusTerms.rows.length + reactionBonusTerms.rejectedRows.length > 0;
      lines.push(
        reactionFormulaLine({
          prefix: null,
          baseMultiplier: null,
          masteryBonus,
          reactionBonus: reactionBonusTotal,
          reactionBonusSlotId: reactionBonusHasSlot ? "reaction-bonus" : null,
          multiplier,
          masterySlotId: null,
        }),
      );
      if (reactionBonusHasSlot) {
        const rows: SlotRow[] = [];
        if (reactionBonus !== null && reactionBonus !== 0) {
          rows.push({
            label: "反应加成基础值",
            value: formatSignedPercent(reactionBonus),
            base: true,
          });
        }
        rows.push(
          ...reactionBonusTerms.rows,
          ...reactionBonusTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
        );
        pushDrawer(
          drawers,
          "reaction-bonus",
          "反应加成",
          formatSignedPercent(reactionBonusTotal),
          rows,
        );
      }
      const secondary = readRecord(record, "secondary_amplifying");
      const secondaryMultiplier = secondary === null ? null : readNumber(secondary, "multiplier");
      if (secondary !== null && secondaryMultiplier !== null) {
        lines.push(
          reactionFormulaLine({
            prefix: "二次增幅 ",
            baseMultiplier: readNumber(secondary, "base_multiplier"),
            masteryBonus: readNumber(secondary, "mastery_bonus"),
            reactionBonus: readNumber(secondary, "reaction_bonus"),
            reactionBonusSlotId: null,
            multiplier: secondaryMultiplier,
            masterySlotId: null,
          }),
        );
      }
    }
  }
  if (lines.length === 0 && multiplier !== null) {
    lines.push([{ kind: "result", text: formatFactor(multiplier) }]);
  }
  return {
    title: "反应区",
    lines,
    drawers,
    note:
      record === null
        ? "无反应结算明细"
        : isReactionMultiplierKind(record)
          ? null
          : "该伤害的反应明细不在反应乘区（见基础区与组分账本）",
  };
}

/** 反应区公式行：与其他乘区一致的纯算术骨架；零值加成项省略，括号组为 1 时一并省略。 */
function reactionFormulaLine({
  prefix,
  baseMultiplier,
  masteryBonus,
  reactionBonus,
  reactionBonusSlotId,
  multiplier,
  masterySlotId,
}: {
  prefix: string | null;
  baseMultiplier: number | null;
  masteryBonus: number | null;
  reactionBonus: number | null;
  reactionBonusSlotId: string | null;
  multiplier: number;
  masterySlotId: string | null;
}): FormulaToken[] {
  const hasMastery = masteryBonus !== null && masteryBonus !== 0;
  const hasReaction = reactionBonus !== null && reactionBonus !== 0;
  const hasAdditive = hasMastery || hasReaction;
  const tokens: FormulaToken[] = [];
  if (prefix !== null) {
    tokens.push({ kind: "text", text: prefix });
  }
  if (baseMultiplier !== null) {
    tokens.push({ kind: "text", text: formatNumber(baseMultiplier) });
    if (hasAdditive) {
      tokens.push({ kind: "text", text: " × (1" });
      if (hasMastery) {
        tokens.push({ kind: "text", text: " + " });
        tokens.push(
          masterySlotId !== null
            ? slotValue(masterySlotId, formatPercent(Math.abs(masteryBonus)), true)
            : { kind: "text", text: formatPercent(Math.abs(masteryBonus)) },
        );
      }
      if (hasReaction) {
        tokens.push({ kind: "text", text: reactionBonus < 0 ? " − " : " + " });
        tokens.push(reactionSlot(reactionBonus, reactionBonusSlotId));
      }
      tokens.push({ kind: "text", text: ")" });
    }
  } else if (hasAdditive) {
    tokens.push({ kind: "text", text: "1" });
    if (hasMastery) {
      tokens.push({ kind: "text", text: " + " });
      tokens.push({ kind: "text", text: formatPercent(Math.abs(masteryBonus)) });
    }
    if (hasReaction) {
      tokens.push({ kind: "text", text: reactionBonus < 0 ? " − " : " + " });
      tokens.push(reactionSlot(reactionBonus, reactionBonusSlotId));
    }
  }
  tokens.push({ kind: "result", text: ` = ${formatFactor(multiplier)}` });
  return tokens;
}

/** 反应加成项：有专属阶段账单时呈现为可折叠槽位，否则为普通数值。 */
function reactionSlot(value: number, slotId: string | null): FormulaToken {
  const label = formatPercent(Math.abs(value));
  return slotId !== null ? slotValue(slotId, label, true) : { kind: "text", text: label };
}

function buildDefenseZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = readNumber(summary, "defense_multiplier");
  const defense = audit === null ? null : readRecord(audit, "defense");
  if (defense === null) {
    return {
      title: "防御区",
      lines:
        multiplier !== null
          ? [[{ kind: "result", text: formatFactor(multiplier) }]]
          : [],
      drawers: [],
      note: null,
    };
  }
  const reduction = readNumber(defense, "defense_reduction") ?? 0;
  const ignore = readNumber(defense, "defense_ignore") ?? 0;
  const sourceLevel = readNumber(defense, "source_level");
  const targetLevel = readNumber(defense, "target_level");
  const reductionTerms = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "defense_reduction",
    null,
  );
  const ignoreTerms = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "defense_ignore",
    null,
  );
  const sourceFactor = `${formatOptionalNumber(sourceLevel)}+100`;
  const showIgnore = ignoreTerms.rows.length + ignoreTerms.rejectedRows.length > 0;
  const showReduction = reductionTerms.rows.length + reductionTerms.rejectedRows.length > 0;
  const lines: FormulaToken[][] = [
    [
      { kind: "text", text: `(${sourceFactor}) ÷ ((${sourceFactor}) + (${formatOptionalNumber(targetLevel)}+100)` },
      ...(showIgnore
        ? ([
            { kind: "text", text: " × (1 − " },
            { kind: "slot", slotId: "defense-ignore", label: formatPercent(ignore) },
            { kind: "text", text: ")" },
          ] as FormulaToken[])
        : []),
      ...(showReduction
        ? ([
            { kind: "text", text: " × (1 − " },
            { kind: "slot", slotId: "defense-reduction", label: formatPercent(reduction) },
            { kind: "text", text: ")" },
          ] as FormulaToken[])
        : []),
      { kind: "text", text: ")" },
      ...(multiplier !== null
        ? [{ kind: "result" as const, text: ` = ${formatFactor(multiplier)}` }]
        : []),
    ],
  ];
  const drawers: SlotDrawerData[] = [];
  pushDrawer(
    drawers,
    "defense-ignore",
    "无视防御",
    formatSignedPercent(ignore),
    [...ignoreTerms.rows, ...ignoreTerms.rejectedRows.map((row) => ({ ...row, rejected: true }))],
  );
  pushDrawer(
    drawers,
    "defense-reduction",
    "减防",
    formatSignedPercent(reduction),
    [
      ...reductionTerms.rows,
      ...reductionTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
    ],
  );
  return { title: "防御区", lines, drawers, note: null };
}

function buildResistanceZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = readNumber(summary, "resistance_multiplier");
  const resistance = audit === null ? null : readRecord(audit, "resistance");
  const value = resistance === null ? null : readNumber(resistance, "resistance");
  const addTerms = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "resistance_add",
    null,
  );
  const panelResistance = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "panel_resistance",
    null,
  );
  const hasTerms = addTerms.rows.length + addTerms.rejectedRows.length > 0;
  const hasPanelResistance = panelResistance.rows.length > 0 && panelResistance.sum !== 0;
  const hasSlotContent = hasTerms || hasPanelResistance;
  const base =
    resistance === null
      ? null
      : readNumber(resistance, "base_resistance") ??
        (value !== null ? value - addTerms.sum : null);
  const lines: FormulaToken[][] = [];
  if (value !== null) {
    if (hasSlotContent) {
      // 与其他乘区一致：槽位显示该位置合计值（基础抗性 + 生效词条），直接嵌入分段公式骨架；
      // 无 resistance_add 词条时面板抗性读取本身也作为基础贡献呈现为槽位。
      const slot = slotValue("resistance-add", formatPercent(value), true);
      const tokens: FormulaToken[] = [];
      if (value < 0) {
        tokens.push({ kind: "text", text: "1 + |" }, slot, { kind: "text", text: "| ÷ 2" });
      } else if (value > 0.75) {
        tokens.push({ kind: "text", text: "1 ÷ (1 + 4×" }, slot, { kind: "text", text: ")" });
      } else {
        tokens.push({ kind: "text", text: "1 − " }, slot);
      }
      if (multiplier !== null) {
        tokens.push({ kind: "result", text: ` = ${formatFactor(multiplier)}` });
      }
      lines.push(tokens);
    } else {
      // 公式直接代入抗性值，与正抗分支一致；负抗为增益（1 + |R|÷2），原值直接进入公式。
      lines.push([
        {
          kind: "text",
          text:
            value < 0
              ? `1 + |${formatPercent(value)}| ÷ 2`
              : value > 0.75
                ? `1 ÷ (1 + 4×${formatPercent(value)})`
                : `1 − ${formatPercent(value)}`,
        },
        ...(multiplier !== null
          ? [{ kind: "result" as const, text: ` = ${formatFactor(multiplier)}` }]
          : []),
      ]);
    }
  } else if (multiplier !== null) {
    lines.push([{ kind: "result", text: formatFactor(multiplier) }]);
  }
  const drawers: SlotDrawerData[] = [];
  if (hasSlotContent) {
    const rows: SlotRow[] = [];
    if (hasPanelResistance) {
      rows.push(...panelResistance.rows);
    } else if (base !== null) {
      rows.push({ label: "目标基础抗性", value: formatPercent(base), base: true });
    }
    rows.push(
      ...addTerms.rows,
      ...addTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
    );
    pushDrawer(
      drawers,
      "resistance-add",
      "抗性调整",
      formatSignedPercent(value ?? addTerms.sum),
      rows,
    );
  }
  return {
    title: "抗性区",
    lines,
    drawers,
    note: null,
  };
}

/**
 * 擢升区：月曜/星烁把擢升按乘性括号 (1 + Σ) 施加在基础区之后。
 * 扁平结果模型没有独立字段承载它，因此从公式专属 resolution 取值；
 * 复合模式的擢升逐组分不同、没有单一乘数，此时不生成链段。
 */
function buildAscensionZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = ascensionMultiplier(summary);
  const applied = readRecordList(audit ?? {}, "applied_terms");
  const rejected = readRecordList(audit ?? {}, "rejected_terms");
  const stellar = collectSlotTerms(applied, rejected, "stellar_ascension_bonus_add", null);
  const lunar = collectSlotTerms(applied, rejected, "lunar_ascension_bonus_add", null);
  const rows: SlotRow[] = [
    ...stellar.rows,
    ...stellar.rejectedRows.map((row) => ({ ...row, rejected: true })),
    ...lunar.rows,
    ...lunar.rejectedRows.map((row) => ({ ...row, rejected: true })),
  ];
  const termSum = stellar.sum + lunar.sum;
  const drawers: SlotDrawerData[] = [];
  if (rows.length > 0) {
    pushDrawer(drawers, "ascension", "擢升", formatSignedPercent(termSum), rows);
  }
  const lines: FormulaToken[][] = [];
  if (rows.length > 0) {
    const baseline = multiplier - 1 - termSum;
    lines.push([
      { kind: "text", text: "1 + " },
      slotValue("ascension", formatSignedPercent(termSum), true),
      ...(baseline !== 0
        ? [{ kind: "muted" as const, text: `（机制基线 ${formatSignedPercent(baseline)}）` }]
        : []),
      { kind: "result", text: ` = ${formatFactor(multiplier)}` },
    ]);
  } else if (multiplier !== 1) {
    lines.push([
      { kind: "text", text: "机制基线" },
      { kind: "result", text: ` = ${formatFactor(multiplier)}` },
    ]);
  }
  return {
    title: "擢升区",
    lines,
    drawers,
    note: rows.length > 0 || multiplier !== 1 ? null : "无擢升修饰词条",
  };
}

/** 链段详情：上部公式区，下部按可修饰位置分类的抽屉；槽位胶囊与抽屉头点击均可折叠。 */
function SegmentDetail({
  segmentId,
  summary,
  audit,
  resolveRef,
}: {
  segmentId: ChainSegmentId;
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
  resolveRef: (ref: string) => string;
}) {
  const model = buildZoneModel(segmentId, summary, audit, resolveRef);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  function toggle(id: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }
  return (
    <>
      {model.title !== null && <div className="damage-sheet-zone-title">{model.title}</div>}
      {model.lines.map((line, lineIndex) => (
        <div className="damage-sheet-formula" key={lineIndex}>
          {line.map((token, tokenIndex) => {
            if (token.kind === "slot") {
              return (
                <button
                  type="button"
                  key={tokenIndex}
                  className={`damage-sheet-slot${collapsed.has(token.slotId) ? " damage-sheet-slot--collapsed" : ""}`}
                  title="点击展开或收起该位置的修饰明细"
                  onClick={() => toggle(token.slotId)}
                >
                  {token.label}
                </button>
              );
            }
            const className =
              token.kind === "muted"
                ? "damage-sheet-formula-muted"
                : token.kind === "result"
                  ? "damage-sheet-formula-result"
                  : "damage-sheet-formula-text";
            return (
              <span className={className} key={tokenIndex}>
                {token.text}
              </span>
            );
          })}
        </div>
      ))}
      {model.drawers.map((drawer) => {
        const isCollapsed = collapsed.has(drawer.id);
        return (
          <div
            className={`damage-sheet-drawer${isCollapsed ? " damage-sheet-drawer--collapsed" : ""}`}
            key={drawer.id}
          >
            <button
              type="button"
              className="damage-sheet-drawer-head"
              onClick={() => toggle(drawer.id)}
            >
              <span className="damage-sheet-drawer-arrow">{isCollapsed ? "▸" : "▾"}</span>
              <span className="damage-sheet-drawer-title">{drawer.title}</span>
              <span className="damage-sheet-drawer-total">{drawer.total}</span>
            </button>
            {!isCollapsed && (
              <div className="damage-sheet-drawer-body">
                {drawer.rows.map((row, rowIndex) => (
                  <div
                    className={`damage-sheet-row${row.rejected ? " damage-sheet-row--rejected" : ""}${row.base ? " damage-sheet-row--base" : ""}`}
                    key={rowIndex}
                    title={row.title}
                  >
                    <span className="damage-sheet-row-label">{row.label}</span>
                    <span className="damage-sheet-row-value">{row.value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
      {model.note !== null && <div className="analysis-view-state">{model.note}</div>}
    </>
  );
}

function formatCritOutcome(outcome: string | null): string {
  if (outcome === "critical") {
    return "暴击";
  }
  if (outcome === "non_critical") {
    return "未暴击";
  }
  if (outcome === "not_applicable") {
    return "不适用";
  }
  return "—";
}

function formatDamage(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : Number(value.toFixed(3)).toLocaleString("en-US");
}

/** 公式区结果的乘数显示：三位小数，不带乘号。 */
function formatFactor(value: number): string {
  return value.toFixed(3);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatOptionalNumber(value: number | null): string {
  return value === null ? "—" : formatNumber(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value !== "" ? value : null;
}

function readNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readBoolean(record: Record<string, unknown>, key: string): boolean {
  return record[key] === true;
}

function readRecord(
  record: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = record[key];
  return isRecord(value) ? value : null;
}

function readRecordList(
  record: Record<string, unknown>,
  key: string,
): Record<string, unknown>[] {
  const value = record[key];
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function DamageSheet({ event }: { event: EventDetailResponse }) {
  const [selectedId, setSelectedId] = useState<ChainSegmentId | null>("base");
  const damage = event.damage;
  if (damage === null || damage === undefined) {
    return (
      <div className="analysis-view-state">该事件不是伤害事件（{event.event_type}）</div>
    );
  }
  const summary = isRecord(damage.summary) ? damage.summary : {};
  const audit = isRecord(damage.audit) ? damage.audit : null;
  const segments = buildChainSegments(summary);
  const resolveRef = (ref: string) => resolveEntityName(event, ref) ?? ref;

  function toggle(id: ChainSegmentId) {
    setSelectedId((current) => (current === id ? null : id));
  }

  return (
    <div className="damage-sheet">
      <ContextBar event={event} summary={summary} />
      {segments.length > 0 && (
        <div className="damage-sheet-chain">
          {segments.map((segment, index) => (
            <span className="damage-sheet-step" key={segment.id}>
              {index > 0 && <span className="damage-sheet-op">x</span>}
              <button
                type="button"
                className={`damage-sheet-seg ${selectedId === segment.id ? "selected" : ""}`}
                title={segment.title}
                onClick={() => toggle(segment.id)}
              >
                <span className="damage-sheet-seg-label">{segment.label}</span>
                <span
                  className={segment.tone === undefined ? "damage-sheet-seg-value" : `damage-sheet-seg-value damage-sheet-seg-value--${segment.tone}`}
                >
                  {segment.valueLabel}
                </span>
              </button>
            </span>
          ))}
        </div>
      )}
      <FinalRow summary={summary} />
      <div className="damage-sheet-detail">
        {selectedId === null ? (
          <div className="analysis-view-state">点击乘区查看明细</div>
        ) : (
          <SegmentDetail
            key={selectedId}
            segmentId={selectedId}
            summary={summary}
            audit={audit}
            resolveRef={resolveRef}
          />
        )}
      </div>
    </div>
  );
}
