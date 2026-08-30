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

/** 伤害类型显示名；键与后端 DamageType 枚举值对应。 */
const DAMAGE_TYPE_LABELS: Record<string, string> = {
  general: "直伤",
  catalyze_reaction: "激化",
  transformative_reaction: "剧变",
  lunar_reaction: "月曜反应",
};

type ChainSegmentId =
  | "base"
  | "bonus"
  | "crit"
  | "reaction"
  | "defense"
  | "resistance"
  | "debug";

interface ChainSegment {
  id: ChainSegmentId;
  label: string;
  valueLabel: string;
  tone?: "crit" | "dim";
  /** hover 提示：该步的累计轨迹（前值 × 乘数 = 后值）。 */
  title: string;
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
  const damageType = readString(summary, "damage_type");
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
        title={damageType !== null ? DAMAGE_TYPE_LABELS[damageType] ?? damageType : undefined}
      >
        {damageName ?? "伤害"}
      </span>
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

/** 伤害修饰阶段是否为固定值类；固定值显示数值，其余按比例显示百分比。 */
function isFlatStage(stage: string): boolean {
  return stage === "base_damage_flat_add" || stage === "component_coefficient_flat_add";
}

interface CollectedTerms {
  rows: SlotRow[];
  rejectedRows: SlotRow[];
  sum: number;
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
  const toRow = (term: Record<string, unknown>): SlotRow => {
    const provider =
      readString(term, "provider_display_name") ?? readString(term, "provider_key") ?? "未知来源";
    const comp = readString(term, "component_key");
    const value = readNumber(term, "value");
    return {
      label: comp !== null ? `${provider}（${comp}）` : provider,
      value: value === null ? "—" : isFlatStage(stage) ? formatNumber(value) : formatSignedPercent(value),
      title: readString(term, "provider_key") ?? undefined,
    };
  };
  const matchedApplied = applied.filter(match);
  const matchedRejected = rejected.filter(match);
  return {
    rows: matchedApplied.map(toRow),
    rejectedRows: matchedRejected.map(toRow),
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
): ZoneDetailModel {
  switch (segmentId) {
    case "base":
      return buildBaseZone(summary, audit);
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
    case "debug":
      return { title: "调试区", lines: [], drawers: [], note: "调试倍率不属于正式公式；正式公式伤害见结果行小字" };
  }
}

function buildBaseZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
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

  for (const [index, component] of components.entries()) {
    const componentKey = readString(component, "component_key") ?? `#${index + 1}`;
    const attributeKey = readString(component, "attribute_key") ?? "";
    const attributeValue = readNumber(component, "attribute_value");
    const original = readNumber(component, "original_coefficient");
    const percent = collectSlotTerms(applied, rejected, "component_coefficient_percent_add", componentKey);
    const flat = collectSlotTerms(applied, rejected, "component_coefficient_flat_add", componentKey);
    percentSum.value += percent.sum;
    flatSum.value += flat.sum;
    percentRows.push(...percent.rows, ...percent.rejectedRows.map((row) => ({ ...row, rejected: true })));
    flatRows.push(...flat.rows, ...flat.rejectedRows.map((row) => ({ ...row, rejected: true })));

    const tokens: FormulaToken[] = [];
    tokens.push({
      kind: "text",
      text: `${attributeLabel(attributeKey)}${attributeValue !== null ? ` ${formatNumber(attributeValue)}` : ""}`,
    });
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
          text: `基础伤害 = 等级系数 ${formatOptionalNumber(level)} × 基础倍率 ${formatOptionalNumber(baseMultiplier)}`,
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

  const hasTermSlots = percentRows.length + flatRows.length + additionRows.length > 0;
  return {
    title: "基础区",
    lines,
    drawers,
    note: hasTermSlots || components.length > 0 ? null : "无伤害词条修饰项",
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
  const terms =
    audit === null
      ? { rows: [], rejectedRows: [], sum: 0 }
      : collectSlotTerms(
          readRecordList(audit, "applied_terms"),
          readRecordList(audit, "rejected_terms"),
          "damage_bonus_add",
          null,
        );
  const total = multiplier !== null ? multiplier - 1 : elementBonus + terms.sum;
  const hasContent = elementBonus !== 0 || terms.rows.length + terms.rejectedRows.length > 0;
  const rows: SlotRow[] = [];
  if (elementBonus !== 0) {
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

  const damageTerms = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "crit_damage_add",
    null,
  );
  const rateTerms = collectSlotTerms(
    readRecordList(audit ?? {}, "applied_terms"),
    readRecordList(audit ?? {}, "rejected_terms"),
    "crit_rate_add",
    null,
  );
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
  if (damageBase !== 0) {
    damageRows.push({ label: "面板暴击伤害", value: formatSignedPercent(damageBase), base: true });
  }
  damageRows.push(
    ...damageTerms.rows,
    ...damageTerms.rejectedRows.map((row) => ({ ...row, rejected: true })),
  );
  pushDrawer(drawers, "crit-damage", "暴击伤害加成", formatSignedPercent(critDamage), damageRows);
  const rateRows: SlotRow[] = [];
  if (rateBase !== 0) {
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

function buildReactionZone(
  summary: Record<string, unknown>,
  audit: Record<string, unknown> | null,
): ZoneDetailModel {
  const multiplier = readNumber(summary, "reaction_multiplier");
  const record =
    audit !== null
      ? readRecord(audit, "reaction")
      : isRecord(summary.reaction)
        ? summary.reaction
        : null;
  const kind = record === null ? null : readString(record, "kind");
  const lines: FormulaToken[][] = [];
  if (record !== null && multiplier !== null) {
    const masteryBonus = readNumber(record, "mastery_bonus");
    const reactionBonus = readNumber(record, "reaction_bonus");
    if (kind === "amplifying") {
      const baseMultiplier = readNumber(record, "base_multiplier");
      lines.push([
        {
          kind: "text",
          text: `${formatOptionalNumber(baseMultiplier)} × (1 + 精通加成 ${formatOptionalPercent(masteryBonus)} + 反应加成 ${formatOptionalSignedPercent(reactionBonus)})`,
        },
        { kind: "result", text: ` = ${formatFactor(multiplier)}` },
      ]);
    } else if (kind === "transformative") {
      lines.push([
        {
          kind: "text",
          text: `1 + 精通加成 ${formatOptionalPercent(masteryBonus)} + 反应加成 ${formatOptionalSignedPercent(reactionBonus)}`,
        },
        { kind: "result", text: ` = ${formatFactor(multiplier)}` },
      ]);
      const secondary = readRecord(record, "secondary_amplifying");
      const secondaryMultiplier = secondary === null ? null : readNumber(secondary, "multiplier");
      if (secondary !== null && secondaryMultiplier !== null) {
        lines.push([
          {
            kind: "text",
            text: `二次增幅 = 基础倍率 ${formatOptionalNumber(readNumber(secondary, "base_multiplier"))} × (1 + 精通加成 ${formatOptionalPercent(readNumber(secondary, "mastery_bonus"))} + 反应加成 ${formatOptionalSignedPercent(readNumber(secondary, "reaction_bonus"))})`,
          },
          { kind: "result", text: ` = ${formatFactor(secondaryMultiplier)}` },
        ]);
      }
    }
  }
  if (lines.length === 0 && multiplier !== null) {
    lines.push([{ kind: "result", text: formatFactor(multiplier) }]);
  }
  return {
    title: "反应区",
    lines,
    drawers: [],
    note: record === null ? "无反应结算明细" : "无伤害词条修饰项",
  };
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
  let line: FormulaToken[];
  if (value !== null) {
    // 公式直接代入抗性值，不重复标注符号名；负抗是增益（1 + |R|÷2），另行标注原值避免歧义。
    line = [
      {
        kind: "text",
        text:
          value < 0
            ? `1 + ${formatPercent(-value / 2)}`
            : value > 0.75
              ? `1 ÷ (1 + 4×${formatPercent(value)})`
              : `1 − ${formatPercent(value)}`,
      },
      ...(value < 0
        ? [{ kind: "muted" as const, text: ` · 抗性 ${formatPercent(value)}` }]
        : []),
      ...(multiplier !== null
        ? [{ kind: "result" as const, text: ` = ${formatFactor(multiplier)}` }]
        : []),
    ];
  } else if (multiplier !== null) {
    line = [{ kind: "result", text: formatFactor(multiplier) }];
  } else {
    line = [];
  }
  return {
    title: "抗性区",
    lines: line.length > 0 ? [line] : [],
    drawers: [],
    note: "无伤害词条修饰项（抗性来自目标属性）",
  };
}

/** 链段详情：上部公式区，下部按可修饰位置分类的抽屉；槽位胶囊与抽屉头点击均可折叠。 */
function SegmentDetail({
  segmentId,
  summary,
  audit,
}: {
  segmentId: ChainSegmentId;
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const model = buildZoneModel(segmentId, summary, audit);
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

function formatOptionalPercent(value: number | null): string {
  return value === null ? "—" : formatPercent(value);
}

function formatOptionalSignedPercent(value: number | null): string {
  return value === null ? "—" : formatSignedPercent(value);
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
          <SegmentDetail key={selectedId} segmentId={selectedId} summary={summary} audit={audit} />
        )}
      </div>
    </div>
  );
}
