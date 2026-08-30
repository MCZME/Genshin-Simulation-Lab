/** 伤害结算单：乘法链 + 链段详情（伤害详情节点卡内容区）。 */

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

/** 伤害修饰词条阶段显示名；键与后端 DamageModifierStage 枚举值对应。 */
const STAGE_LABELS: Record<string, string> = {
  component_coefficient_percent_add: "倍率段加成",
  component_coefficient_flat_add: "倍率段加值",
  base_damage_flat_add: "基础伤害加值",
  damage_bonus_add: "增伤加成",
  defense_reduction: "减防",
  defense_ignore: "无视防御",
  crit_rate_add: "暴击率加成",
  crit_damage_add: "暴伤加成",
};

type ChainSegmentId =
  | "base"
  | "bonus"
  | "crit"
  | "reaction"
  | "defense"
  | "resistance"
  | "debug";

/** 词条阶段 -> 乘法链段归属；按后端 DamageModifierStage 静态确定。 */
const SEGMENT_OF_STAGE: Record<string, ChainSegmentId> = {
  component_coefficient_percent_add: "base",
  component_coefficient_flat_add: "base",
  base_damage_flat_add: "base",
  damage_bonus_add: "bonus",
  crit_rate_add: "crit",
  crit_damage_add: "crit",
  defense_reduction: "defense",
  defense_ignore: "defense",
};

interface ChainSegment {
  id: ChainSegmentId;
  label: string;
  valueLabel: string;
  tone?: "crit" | "dim";
  /** hover 提示：该步的累计轨迹（前值 × 乘数 = 后值）。 */
  title: string;
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
              {index > 0 && <span className="damage-sheet-op">*</span>}
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
          <SegmentDetail segmentId={selectedId} summary={summary} audit={audit} />
        )}
      </div>
    </div>
  );
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
      <span className="damage-sheet-context-title">
        {damageName ?? "伤害"} #{event.ordinal} · 帧 {event.frame}
      </span>
      {elementLabel !== null && (
        <span className="damage-sheet-context-tag" title={element ?? undefined}>
          <span className="damage-sheet-element-dot" style={{ background: elementColor }} />
          {elementLabel}
        </span>
      )}
      {damageType !== null && (
        <span className="damage-sheet-context-tag">
          {DAMAGE_TYPE_LABELS[damageType] ?? damageType}
        </span>
      )}
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
    valueLabel: formatMultiplier(multiplier),
    tone,
    title: `${formatDamage(afterValue / multiplier)} × ${formatMultiplier(multiplier)} = ${formatDamage(afterValue)}`,
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

function SegmentDetail({
  segmentId,
  summary,
  audit,
}: {
  segmentId: ChainSegmentId;
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  switch (segmentId) {
    case "base":
      return <BaseDetail summary={summary} audit={audit} />;
    case "bonus":
      return <BonusDetail summary={summary} audit={audit} />;
    case "crit":
      return <CritDetail summary={summary} audit={audit} />;
    case "reaction":
      return <ReactionDetail summary={summary} audit={audit} />;
    case "defense":
      return <DefenseDetail summary={summary} audit={audit} />;
    case "resistance":
      return <ResistanceDetail summary={summary} audit={audit} />;
    case "debug":
      return (
        <div className="analysis-view-state">
          调试倍率不属于正式公式；正式公式伤害见结果行小字
        </div>
      );
  }
}

function BaseDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  if (audit === null) {
    return <div className="analysis-view-state">无审计数据</div>;
  }
  const components = readRecordList(audit, "component_results");
  const additions = readRecordList(audit, "base_damage_additions");
  const damageName = readString(summary, "damage_name");
  return (
    <>
      <div className="damage-sheet-damage-name">{damageName ?? "基础伤害"}</div>
      {components.length > 0 ? (
        <DetailGroup title="倍率段明细 · 倍率 × (1+倍率修改) × 属性值">
          <table className="damage-sheet-table">
            <thead>
              <tr>
                <th>属性</th>
                <th>倍率</th>
                <th>贡献</th>
              </tr>
            </thead>
            <tbody>
              {components.map((component, index) => (
                <tr
                  key={index}
                  title={readString(component, "component_key") ?? undefined}
                >
                  <td>
                    {attributeLabel(readString(component, "attribute_key") ?? "")}
                    {readNumber(component, "attribute_value") !== null &&
                      ` ${formatNumber(readNumber(component, "attribute_value") as number)}`}
                  </td>
                  <td>
                    {formatCoefficientRange(
                      readNumber(component, "original_coefficient"),
                      readNumber(component, "final_coefficient"),
                    )}
                  </td>
                  <td>{formatOptionalDamage(readNumber(component, "damage"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DetailGroup>
      ) : (
        <div className="analysis-view-state">无倍率段</div>
      )}
      {additions.length > 0 && (
        <DetailGroup title="固定值加值">
          {additions.map((addition, index) => (
            <div className="damage-sheet-row" key={index}>
              <span className="damage-sheet-row-label">
                {readString(addition, "addition_key") ?? `加值 #${index + 1}`}
              </span>
              <span className="damage-sheet-row-value">
                {formatOptionalDamage(readNumber(addition, "value"))}
              </span>
            </div>
          ))}
        </DetailGroup>
      )}
      <TermsSection audit={audit} segmentId="base" />
      <AttributeTraceSection audit={audit} />
    </>
  );
}

function BonusDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const bonus = audit === null ? null : readRecord(audit, "damage_bonus");
  return (
    <>
      {bonus === null ? (
        <DetailRows
          rows={[
            {
              label: "合计乘数",
              value: formatOptionalMultiplier(readNumber(summary, "damage_bonus_multiplier")),
            },
          ]}
        />
      ) : (
        <DetailRows
          rows={[
            { label: "元素伤加成", value: formatOptionalSignedPercent(readNumber(bonus, "element_bonus")) },
            { label: "通用伤加成", value: formatOptionalSignedPercent(readNumber(bonus, "modifier_bonus")) },
            { label: "合计乘数", value: formatOptionalMultiplier(readNumber(bonus, "multiplier")) },
          ]}
        />
      )}
      {audit !== null && <TermsSection audit={audit} segmentId="bonus" />}
    </>
  );
}

function CritDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const critical = audit === null ? null : readRecord(audit, "critical");
  const outcome = readString(critical ?? summary, "outcome") ?? readString(summary, "crit_outcome");
  const rows = critical === null
    ? [
        {
          label: "判定结果",
          value: formatCritOutcome(outcome),
        },
        {
          label: "面板暴击率",
          value: formatOptionalPercent(readNumber(summary, "crit_rate")),
        },
        {
          label: "暴击伤害乘数",
          value: formatOptionalMultiplier(readNumber(summary, "crit_damage")),
        },
        {
          label: "实际乘数",
          value: formatOptionalMultiplier(readNumber(summary, "crit_multiplier")),
        },
      ]
    : [
        { label: "可否暴击", value: readBoolean(critical, "can_crit") ? "是" : "否" },
        {
          label: "判定结果",
          value: formatCritOutcome(readString(critical, "outcome")),
        },
        {
          label: "面板暴击率",
          value: formatOptionalPercent(readNumber(critical, "crit_rate")),
        },
        {
          label: "生效暴击率",
          value: formatOptionalPercent(readNumber(critical, "effective_crit_rate")),
        },
        {
          label: "暴击伤害乘数",
          value: formatOptionalMultiplier(readNumber(critical, "crit_damage")),
        },
        {
          label: "实际乘数",
          value: formatOptionalMultiplier(readNumber(critical, "multiplier")),
        },
      ];
  return (
    <>
      <DetailRows rows={rows} />
      {audit !== null && <TermsSection audit={audit} segmentId="crit" />}
    </>
  );
}

function ReactionDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const reaction = (audit !== null ? readRecord(audit, "reaction") : null)
    ?? (isRecord(summary.reaction) ? summary.reaction : null);
  return (
    <>
      <DetailRows
        rows={[
          {
            label: "反应乘数",
            value: formatOptionalMultiplier(readNumber(summary, "reaction_multiplier")),
          },
        ]}
      />
      {reaction === null ? (
        <div className="analysis-view-state">无反应结算明细</div>
      ) : (
        <DetailGroup title="反应结算明细">
          <GenericRecordRows record={reaction} />
        </DetailGroup>
      )}
    </>
  );
}

function DefenseDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const defense = audit === null ? null : readRecord(audit, "defense");
  return (
    <>
      {defense === null ? (
        <DetailRows
          rows={[
            {
              label: "合计乘数",
              value: formatOptionalMultiplier(readNumber(summary, "defense_multiplier")),
            },
          ]}
        />
      ) : (
        <DetailRows
          rows={[
            { label: "攻方等级", value: formatOptionalNumber(readNumber(defense, "source_level")) },
            { label: "守方等级", value: formatOptionalNumber(readNumber(defense, "target_level")) },
            { label: "减防", value: formatOptionalSignedPercent(readNumber(defense, "defense_reduction")) },
            { label: "无视防御", value: formatOptionalSignedPercent(readNumber(defense, "defense_ignore")) },
            { label: "合计乘数", value: formatOptionalMultiplier(readNumber(defense, "multiplier")) },
          ]}
        />
      )}
      {audit !== null && <TermsSection audit={audit} segmentId="defense" />}
    </>
  );
}

function ResistanceDetail({
  summary,
  audit,
}: {
  summary: Record<string, unknown>;
  audit: Record<string, unknown> | null;
}) {
  const resistance = audit === null ? null : readRecord(audit, "resistance");
  return resistance === null ? (
    <DetailRows
      rows={[
        {
          label: "合计乘数",
          value: formatOptionalMultiplier(readNumber(summary, "resistance_multiplier")),
        },
      ]}
    />
  ) : (
    <DetailRows
      rows={[
        { label: "目标抗性", value: formatOptionalSignedPercent(readNumber(resistance, "resistance")) },
        { label: "合计乘数", value: formatOptionalMultiplier(readNumber(resistance, "multiplier")) },
      ]}
    />
  );
}

/** 词条段：按链段归属过滤 applied/rejected 词条。 */
function TermsSection({
  audit,
  segmentId,
}: {
  audit: Record<string, unknown>;
  segmentId: ChainSegmentId;
}) {
  const applied = readRecordList(audit, "applied_terms").filter((term) =>
    termBelongsToSegment(term, segmentId),
  );
  const rejected = readRecordList(audit, "rejected_terms").filter((term) =>
    termBelongsToSegment(term, segmentId),
  );
  if (applied.length === 0 && rejected.length === 0) {
    return null;
  }
  return (
    <DetailGroup title={`词条 · 生效 ${applied.length} · 未生效 ${rejected.length}`}>
      {applied.map((term, index) => (
        <TermRow term={term} key={`applied-${index}`} />
      ))}
      {rejected.map((term, index) => (
        <TermRow term={term} rejected key={`rejected-${index}`} />
      ))}
    </DetailGroup>
  );
}

function termBelongsToSegment(term: Record<string, unknown>, segmentId: ChainSegmentId): boolean {
  const stage = readString(term, "stage");
  return stage !== null && SEGMENT_OF_STAGE[stage] === segmentId;
}

function TermRow({ term, rejected = false }: { term: Record<string, unknown>; rejected?: boolean }) {
  // 显示名优先（来自 ModifierProviderSpec.display_name），未提供时回退 provider 原键。
  const provider =
    readString(term, "provider_display_name") ?? readString(term, "provider_key") ?? "未知来源";
  const stage = readString(term, "stage");
  const value = readNumber(term, "value");
  return (
    <div className={`damage-sheet-row ${rejected ? "damage-sheet-row--rejected" : ""}`}>
      <span
        className="damage-sheet-row-label"
        title={readString(term, "provider_key") ?? undefined}
      >
        {provider}
        {stage !== null && ` · ${STAGE_LABELS[stage] ?? stage}`}
      </span>
      <span className="damage-sheet-row-value">{formatTermValue(stage, value)}</span>
    </div>
  );
}

function AttributeTraceSection({ audit }: { audit: Record<string, unknown> | null }) {
  if (audit === null) {
    return null;
  }
  const source = readRecordList(audit, "source_attribute_trace");
  const target = readRecordList(audit, "target_attribute_trace");
  if (source.length === 0 && target.length === 0) {
    return null;
  }
  return (
    <DetailGroup title="属性追踪">
      {source.map((resolution, index) => (
        <TraceRow resolution={resolution} label={`攻方 #${index + 1}`} key={`source-${index}`} />
      ))}
      {target.map((resolution, index) => (
        <TraceRow resolution={resolution} label={`守方 #${index + 1}`} key={`target-${index}`} />
      ))}
    </DetailGroup>
  );
}

function TraceRow({
  resolution,
  label,
}: {
  resolution: Record<string, unknown>;
  label: string;
}) {
  const key = readString(resolution, "attribute_key") ?? "?";
  const finalValue = readNumber(resolution, "final_value");
  const baseValue = readNumber(resolution, "base_value");
  return (
    <div className="damage-sheet-row" title="属性解析结果；依赖属性递归不展开">
      <span className="damage-sheet-row-label" title={key}>
        {label} · {attributeLabel(key)}
      </span>
      <span className="damage-sheet-row-value">
        {formatOptionalNumber(finalValue)}
        {baseValue !== null && `（基 ${formatNumber(baseValue)}）`}
      </span>
    </div>
  );
}

function DetailGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="damage-sheet-group">
      <div className="damage-sheet-group-title">{title}</div>
      {children}
    </div>
  );
}

function DetailRows({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div className="damage-sheet-rows">
      {rows.map((row) => (
        <div className="damage-sheet-row" key={row.label}>
          <span className="damage-sheet-row-label">{row.label}</span>
          <span className="damage-sheet-row-value">{row.value}</span>
        </div>
      ))}
    </div>
  );
}

/** 反应结算结构按伤害类型差异较大，用一层通用键值渲染兜底。 */
function GenericRecordRows({ record }: { record: Record<string, unknown> }) {
  const rows = Object.entries(record).filter(([, value]) => isScalar(value));
  if (rows.length === 0) {
    return <div className="analysis-view-state">无可显示字段</div>;
  }
  return (
    <>
      {rows.map(([key, value]) => (
        <div className="damage-sheet-row" key={key} title={key}>
          <span className="damage-sheet-row-label">{key}</span>
          <span className="damage-sheet-row-value">{formatScalar(value)}</span>
        </div>
      ))}
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

function formatTermValue(stage: string | null, value: number | null): string {
  if (value === null) {
    return "—";
  }
  // 固定值类阶段显示伤害数值，其余阶段按比例显示百分比。
  if (stage === "base_damage_flat_add" || stage === "component_coefficient_flat_add") {
    return formatNumber(value);
  }
  return formatSignedPercent(value);
}

function formatDamage(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

function formatOptionalDamage(value: number | null): string {
  return value === null ? "—" : formatDamage(value);
}

function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : Number(value.toFixed(3)).toLocaleString("en-US");
}

function formatOptionalNumber(value: number | null): string {
  return value === null ? "—" : formatNumber(value);
}

function formatMultiplier(value: number): string {
  return `×${value.toFixed(3)}`;
}

function formatOptionalMultiplier(value: number | null): string {
  return value === null ? "—" : formatMultiplier(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatOptionalPercent(value: number | null): string {
  return value === null ? "—" : formatPercent(value);
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatOptionalSignedPercent(value: number | null): string {
  return value === null ? "—" : formatSignedPercent(value);
}

function formatCoefficientRange(original: number | null, final: number | null): string {
  if (original === null && final === null) {
    return "—";
  }
  const originalText = original === null ? null : formatPercent(original);
  const finalText = final === null ? null : formatPercent(final);
  if (originalText === null) {
    return finalText ?? "—";
  }
  if (finalText === null || originalText === finalText) {
    return originalText;
  }
  return `${originalText} → ${finalText}`;
}

function formatScalar(value: unknown): string {
  if (typeof value === "number") {
    return formatNumber(value);
  }
  return String(value);
}

function isScalar(value: unknown): boolean {
  return (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
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
