/** 角色状态详情：消费帧状态里的单个角色，展示生命/能量、活动 Buff 与属性面板。 */

import { useState } from "react";
import type { FrameCharacterState, FrameStateResponse } from "../../api/client";
import { ATTRIBUTE_STAGE_LABELS, attributeLabel } from "./attributeLabels";

const FRAMES_PER_SECOND = 60;

/** item 提供的角色/属性定位；缺省角色时由调用方按当前场上角色解析。 */
export interface CharacterLocator {
  slot?: number;
  entityId?: string;
  characterKey?: string;
  attributeKey?: string;
}

/** 按定位在帧状态里找角色；没有显式定位时返回当前场上角色。 */
export function locateCharacter(
  frameState: FrameStateResponse,
  locator: CharacterLocator,
): FrameCharacterState | null {
  const characters = frameState.characters ?? [];
  const hasLocator =
    locator.entityId !== undefined ||
    locator.slot !== undefined ||
    locator.characterKey !== undefined;
  if (locator.entityId !== undefined) {
    const found = characters.find((item) => item.combat_entity_id === locator.entityId);
    if (found !== undefined) {
      return found;
    }
  }
  if (locator.slot !== undefined) {
    const found = characters.find((item) => item.slot === locator.slot);
    if (found !== undefined) {
      return found;
    }
  }
  if (locator.characterKey !== undefined) {
    const found = characters.find((item) => item.character_key === locator.characterKey);
    if (found !== undefined) {
      return found;
    }
  }
  if (hasLocator) {
    return null;
  }
  const activeSlot = frameState.team?.active_slot;
  if (activeSlot !== null && activeSlot !== undefined) {
    const active = characters.find((item) => item.slot === activeSlot);
    if (active !== undefined) {
      return active;
    }
  }
  return characters.find((item) => item.active) ?? null;
}

export function CharacterStateSheet({
  frameState,
  character,
  focusAttributeKey = null,
}: {
  frameState: FrameStateResponse;
  character: FrameCharacterState;
  focusAttributeKey?: string | null;
}) {
  const attributes = isRecord(character.attributes) ? character.attributes : {};
  const sections = buildAttributeSections(attributes);
  const visibleSections =
    focusAttributeKey === null
      ? sections
      : sections
          .map((section) => ({
            ...section,
            entries: section.entries.filter((entry) => entry.key === focusAttributeKey),
          }))
          .filter((section) => section.entries.length > 0);
  const focusMissing =
    focusAttributeKey !== null && visibleSections.every((section) => section.entries.length === 0);
  const [openAttributes, setOpenAttributes] = useState<ReadonlySet<string>>(
    () => new Set(focusAttributeKey === null ? [] : [focusAttributeKey]),
  );
  const [openBuffs, setOpenBuffs] = useState<ReadonlySet<string>>(new Set());

  function toggleAttribute(key: string) {
    setOpenAttributes((current) => toggleKey(current, key));
  }

  function toggleBuff(key: string) {
    setOpenBuffs((current) => toggleKey(current, key));
  }

  return (
    <div className="state-sheet">
      <CharacterContext frameState={frameState} character={character} />
      <section className="state-sheet-section">
        <h3 className="state-sheet-section-title">当前状态</h3>
        <HealthEnergyRows character={character} />
      </section>
      <BuffSection
        frameState={frameState}
        character={character}
        openBuffs={openBuffs}
        onToggle={toggleBuff}
      />
      <section className="state-sheet-section">
        <h3 className="state-sheet-section-title">属性</h3>
        {focusMissing ? (
          <div className="state-sheet-empty">
            帧状态中不存在属性 {focusAttributeKey ?? ""}
          </div>
        ) : visibleSections.length === 0 ? (
          <div className="state-sheet-empty">无属性数据</div>
        ) : (
          visibleSections.map((section) => (
            <AttributeGroup
              key={section.title}
              title={section.title}
              entries={section.entries}
              openKeys={openAttributes}
              onToggle={toggleAttribute}
            />
          ))
        )}
      </section>
    </div>
  );
}

function CharacterContext({
  frameState,
  character,
}: {
  frameState: FrameStateResponse;
  character: FrameCharacterState;
}) {
  return (
    <div className="state-sheet-context">
      <span className="state-sheet-context-frame">
        帧 {frameState.frame}（{frameState.time_seconds.toFixed(2)} 秒）
      </span>
      <span className="state-sheet-context-char">
        {character.slot}. {character.character_key}
      </span>
      {character.active && <span className="state-sheet-context-badge">场上</span>}
    </div>
  );
}

function HealthEnergyRows({ character }: { character: FrameCharacterState }) {
  const health = character.health;
  const energy = character.energy;
  const maxHp = health.max_hp ?? null;
  const hpRatio = health.hp_ratio ?? null;
  const capacity = energy.capacity ?? null;
  const energyRatio =
    typeof capacity === "number" && Number.isFinite(capacity) && capacity > 0
      ? Math.min(1, Math.max(0, energy.current_energy / capacity))
      : null;
  return (
    <div className="state-sheet-status-list">
      <StatusLine
        label="生命"
        value={`${formatNumber(health.current_hp)}${maxHp === null ? "" : ` / ${formatNumber(maxHp)}`}`}
        ratio={hpRatio}
      />
      <StatusLine
        label="能量"
        value={`${formatNumber(energy.current_energy)}${capacity === null ? "" : ` / ${formatNumber(capacity)}`}`}
        ratio={energyRatio}
        hint={
          capacity === null
            ? undefined
            : energy.burst_ready
              ? "大招就绪"
              : "大招未就绪"
        }
      />
    </div>
  );
}

function StatusLine({
  label,
  value,
  ratio,
  hint,
}: {
  label: string;
  value: string;
  ratio: number | null;
  hint?: string;
}) {
  return (
    <div className="state-sheet-status-line">
      <span className="state-sheet-status-label">{label}</span>
      <div className="state-sheet-status-main">
        <div className="state-sheet-status-text">
          <span>{value}</span>
          {ratio !== null && (
            <span className="state-sheet-status-ratio">{formatPercent(ratio)}</span>
          )}
          {hint !== undefined && <span className="state-sheet-status-hint">{hint}</span>}
        </div>
        <div className="state-sheet-bar" aria-hidden="true">
          <div
            className="state-sheet-bar-fill"
            style={{
              width: ratio === null ? "0%" : `${Math.min(100, Math.max(0, ratio * 100))}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
}

function BuffSection({
  frameState,
  character,
  openBuffs,
  onToggle,
}: {
  frameState: FrameStateResponse;
  character: FrameCharacterState;
  openBuffs: ReadonlySet<string>;
  onToggle: (key: string) => void;
}) {
  const buffs = Array.isArray(character.buffs) ? character.buffs.filter(isRecord) : [];
  return (
    <section className="state-sheet-section">
      <h3 className="state-sheet-section-title">
        Buff{buffs.length > 0 ? `（${buffs.length}）` : ""}
      </h3>
      {buffs.length === 0 ? (
        <div className="state-sheet-empty">无活动 Buff</div>
      ) : (
        buffs.map((buff, index) => {
          const key = buffInstanceKey(buff, index);
          const open = openBuffs.has(key);
          return (
            <div className="state-sheet-buff" key={key}>
              <button
                type="button"
                className="state-sheet-buff-head"
                aria-expanded={open}
                onClick={() => onToggle(key)}
              >
                <span className="state-sheet-buff-arrow">{open ? "▾" : "▸"}</span>
                <span className="state-sheet-buff-name" title={buffTitle(buff)}>
                  {buffDefinitionKey(buff)}
                </span>
                {buffStackCount(buff) !== null && buffStackCount(buff)! > 1 && (
                  <span className="state-sheet-buff-stacks">×{buffStackCount(buff)}</span>
                )}
                <span className="state-sheet-buff-remaining">
                  {formatRemaining(buffExpiresAtFrame(buff), frameState.frame)}
                </span>
              </button>
              {open && <BuffModifiers buff={buff} />}
            </div>
          );
        })
      )}
    </section>
  );
}

function BuffModifiers({ buff }: { buff: Record<string, unknown> }) {
  const modifiers = readBuffModifiers(buff);
  if (modifiers.length === 0) {
    return <div className="state-sheet-buff-body state-sheet-empty">纯标记状态，无属性修饰</div>;
  }
  return (
    <div className="state-sheet-buff-body">
      {modifiers.map((modifier, index) => (
        <div className="state-sheet-buff-modifier" key={`${modifier.targetKey}-${index}`}>
          <span className="state-sheet-buff-modifier-label">
            {attributeLabel(modifier.targetKey)}（
            {ATTRIBUTE_STAGE_LABELS[modifier.stage] ?? modifier.stage}）
          </span>
          <span className="state-sheet-buff-modifier-value">
            {formatModifierValue(modifier.targetKey, modifier.stage, modifier.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function AttributeGroup({
  title,
  entries,
  openKeys,
  onToggle,
}: {
  title: string;
  entries: AttributeEntry[];
  openKeys: ReadonlySet<string>;
  onToggle: (key: string) => void;
}) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="state-sheet-attr-group">
      <div className="state-sheet-attr-group-title">{title}</div>
      {entries.map((entry) => {
        const open = openKeys.has(entry.key);
        return (
          <div className="state-sheet-attr" key={entry.key}>
            <button
              type="button"
              className="state-sheet-attr-head"
              aria-expanded={open}
              onClick={() => onToggle(entry.key)}
            >
              <span className="state-sheet-attr-arrow">{open ? "▾" : "▸"}</span>
              <span className="state-sheet-attr-name">{attributeLabel(entry.key)}</span>
              {entry.terms.length > 0 && (
                <span className="state-sheet-attr-count">{entry.terms.length}</span>
              )}
              <span className="state-sheet-attr-value">
                {formatAttributeValue(entry.key, entry.value)}
              </span>
            </button>
            {open && <AttributeTerms attributeKey={entry.key} terms={entry.terms} />}
          </div>
        );
      })}
    </div>
  );
}

function AttributeTerms({
  attributeKey,
  terms,
}: {
  attributeKey: string;
  terms: Record<string, unknown>[];
}) {
  const byStage = new Map<string, Record<string, unknown>[]>();
  for (const term of terms) {
    const stage = readString(term, "stage") ?? "other";
    const list = byStage.get(stage) ?? [];
    list.push(term);
    byStage.set(stage, list);
  }
  const stages = STAGE_ORDER.filter((stage) => byStage.has(stage)).concat(
    Array.from(byStage.keys()).filter((stage) => !STAGE_ORDER.includes(stage)),
  );
  if (stages.length === 0) {
    return <div className="state-sheet-empty">无生效修饰词条</div>;
  }
  return (
    <div className="state-sheet-attr-terms">
      {stages.map((stage) => {
        const rows = byStage.get(stage) ?? [];
        return (
          <div className="state-sheet-term-group" key={stage}>
            <div className="state-sheet-term-group-title">
              {ATTRIBUTE_STAGE_LABELS[stage] ?? stage}
            </div>
            {rows.map((term, index) => (
              <TermRow
                key={`${readString(term, "provider_key") ?? "term"}-${index}`}
                attributeKey={attributeKey}
                term={term}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function TermRow({
  attributeKey,
  term,
}: {
  attributeKey: string;
  term: Record<string, unknown>;
}) {
  const providerKey = readString(term, "provider_key");
  const providerName =
    readString(term, "provider_display_name") ?? providerKey ?? "未知来源";
  const stage = readString(term, "stage") ?? "other";
  const value = readNumber(term, "value");
  const targetKey = readString(term, "target_key") ?? attributeKey;
  return (
    <div className="state-sheet-term-row" title={termTitle(term)}>
      <span className="state-sheet-term-label">{providerName}</span>
      <span className="state-sheet-term-value">
        {value === null ? "—" : formatModifierValue(targetKey, stage, value)}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 数据解析与格式化
// ---------------------------------------------------------------------------

interface AttributeEntry {
  key: string;
  value: number | null;
  terms: Record<string, unknown>[];
}

const STAT_ORDER = [
  "stat.hp.base",
  "stat.hp.max",
  "stat.atk.base",
  "stat.atk.total",
  "stat.def.base",
  "stat.def.total",
];

const COMBAT_ORDER = [
  "stat.crit_rate",
  "stat.crit_damage",
  "stat.elemental_mastery",
  "stat.energy_recharge",
];

const BONUS_ORDER = [
  "bonus.damage.physical",
  "bonus.damage.pyro",
  "bonus.damage.hydro",
  "bonus.damage.electro",
  "bonus.damage.cryo",
  "bonus.damage.anemo",
  "bonus.damage.geo",
  "bonus.damage.dendro",
  "bonus.healing.outgoing",
  "bonus.healing.incoming",
  "bonus.shield.strength",
];

const RESISTANCE_ORDER = [
  "resistance.physical",
  "resistance.pyro",
  "resistance.hydro",
  "resistance.electro",
  "resistance.cryo",
  "resistance.anemo",
  "resistance.geo",
  "resistance.dendro",
];

const STAGE_ORDER = [
  "base_add",
  "percent_add",
  "flat_add",
  "final_multiplier",
  "override",
];

function buildAttributeSections(
  attributes: Record<string, unknown>,
): { title: string; entries: AttributeEntry[] }[] {
  const keys = Object.keys(attributes).sort(
    (left, right) => attributeRank(left) - attributeRank(right),
  );
  const sections = new Map<string, AttributeEntry[]>();
  for (const key of keys) {
    const entry = readRecord(attributes, key);
    if (entry === null) {
      continue;
    }
    const item: AttributeEntry = {
      key,
      value: readNumber(entry, "value"),
      terms: readRecordList(entry, "applied_terms"),
    };
    const title = attributeSectionTitle(key);
    const list = sections.get(title) ?? [];
    list.push(item);
    sections.set(title, list);
  }
  return [
    { title: "生命/攻击/防御", entries: sections.get("生命/攻击/防御") ?? [] },
    { title: "战斗属性", entries: sections.get("战斗属性") ?? [] },
    { title: "加成", entries: sections.get("加成") ?? [] },
    { title: "抗性", entries: sections.get("抗性") ?? [] },
    { title: "其他", entries: sections.get("其他") ?? [] },
  ].filter((section) => section.entries.length > 0);
}

function attributeRank(key: string): number {
  const order = [
    ...STAT_ORDER,
    ...COMBAT_ORDER,
    ...BONUS_ORDER,
    ...RESISTANCE_ORDER,
  ];
  const index = order.indexOf(key);
  return index === -1 ? order.length : index;
}

function attributeSectionTitle(key: string): string {
  if (STAT_ORDER.includes(key)) {
    return "生命/攻击/防御";
  }
  if (COMBAT_ORDER.includes(key)) {
    return "战斗属性";
  }
  if (key.startsWith("bonus.")) {
    return "加成";
  }
  if (key.startsWith("resistance.")) {
    return "抗性";
  }
  return "其他";
}

function buffInstanceKey(buff: Record<string, unknown>, index: number): string {
  const instanceRef = readRecord(buff, "instance_ref");
  if (instanceRef !== null) {
    const domain = readString(instanceRef, "domain_key") ?? "buff";
    const sequence = readNumber(instanceRef, "sequence");
    if (sequence !== null) {
      return `${domain}:${sequence}`;
    }
  }
  return `${buffDefinitionKey(buff) ?? "buff"}#${index}`;
}

function buffDefinitionKey(buff: Record<string, unknown>): string {
  const definition = readRecord(buff, "definition");
  return (
    readString(buff, "definition_key") ??
    (definition === null ? null : readString(definition, "definition_key")) ??
    "buff"
  );
}

function buffStackCount(buff: Record<string, unknown>): number | null {
  const top = readNumber(buff, "stack_count");
  if (top !== null) {
    return top;
  }
  const state = readRecord(buff, "state");
  return state === null ? null : readNumber(state, "stack_count");
}

function buffExpiresAtFrame(buff: Record<string, unknown>): number | null {
  return readNumber(buff, "expires_at_frame");
}

function buffTitle(buff: Record<string, unknown>): string {
  const parts: string[] = [];
  const definition = readRecord(buff, "definition");
  const instanceRef = readRecord(buff, "instance_ref");
  if (instanceRef !== null) {
    parts.push(`instance=${readString(instanceRef, "domain_key") ?? "buff"}:${readNumber(instanceRef, "sequence") ?? "?"}`);
  }
  const definitionKey =
    readString(buff, "definition_key") ??
    (definition === null ? null : readString(definition, "definition_key"));
  if (definitionKey !== null) {
    parts.push(`definition=${definitionKey}`);
  }
  const mechanicKey =
    readString(buff, "mechanic_key") ??
    (definition === null ? null : readString(definition, "mechanic_key"));
  if (mechanicKey !== null) {
    parts.push(`mechanic=${mechanicKey}`);
  }
  const handlerKey =
    readString(buff, "handler_key") ??
    (definition === null ? null : readString(definition, "handler_key"));
  if (handlerKey !== null) {
    parts.push(`handler=${handlerKey}`);
  }
  return parts.join(" · ");
}

function readBuffModifiers(buff: Record<string, unknown>): {
  targetKey: string;
  stage: string;
  value: number | null;
}[] {
  const raw = readRecordList(buff, "resolved_modifiers");
  const nested = readRecord(buff, "state");
  const list =
    raw.length > 0
      ? raw
      : nested === null
        ? []
        : readRecordList(nested, "resolved_modifiers");
  const result: { targetKey: string; stage: string; value: number | null }[] = [];
  for (const item of list) {
    const template = readRecord(item, "template") ?? item;
    const targetKey = readString(template, "target_key") ?? readString(item, "target_key");
    const stage = readString(template, "stage") ?? readString(item, "stage");
    const value = readNumber(item, "value");
    if (targetKey !== null && stage !== null) {
      result.push({ targetKey, stage, value });
    }
  }
  return result;
}

function formatRemaining(expiresAtFrame: number | null, currentFrame: number): string {
  if (expiresAtFrame === null) {
    return "剩余 —";
  }
  const remaining = Math.max(0, expiresAtFrame - currentFrame);
  return `剩余 ${remaining} 帧（${(remaining / FRAMES_PER_SECOND).toFixed(2)} 秒）`;
}

function isPercentAttribute(key: string): boolean {
  return (
    key.startsWith("bonus.") ||
    key.startsWith("resistance.") ||
    key === "stat.crit_rate" ||
    key === "stat.crit_damage" ||
    key === "stat.energy_recharge"
  );
}

function formatAttributeValue(key: string, value: number | null): string {
  if (value === null) {
    return "—";
  }
  return isPercentAttribute(key) ? formatPercent(value) : formatNumber(value);
}

function formatModifierValue(targetKey: string, stage: string, value: number | null): string {
  if (value === null) {
    return "—";
  }
  const percent =
    stage === "percent_add" ||
    stage === "final_multiplier" ||
    (stage === "flat_add" && isPercentAttribute(targetKey)) ||
    (stage === "override" && isPercentAttribute(targetKey)) ||
    (stage === "base_add" && isPercentAttribute(targetKey));
  return percent ? formatSignedPercent(value) : formatSignedNumber(value);
}

function termTitle(term: Record<string, unknown>): string {
  const parts: string[] = [];
  const providerKey = readString(term, "provider_key");
  if (providerKey !== null) {
    parts.push(`provider=${providerKey}`);
  }
  const targetKey = readString(term, "target_key");
  if (targetKey !== null) {
    parts.push(`target=${targetKey}`);
  }
  const sourceRef = readRecord(term, "source_ref");
  if (sourceRef !== null) {
    const kind = readString(sourceRef, "kind");
    const sourceKey = readString(sourceRef, "source_key");
    const instanceId = readString(sourceRef, "instance_id");
    parts.push(`source=${kind ?? "?"}:${sourceKey ?? "?"}${instanceId === null ? "" : `#${instanceId}`}`);
  }
  const stackingGroup = readString(term, "stacking_group");
  if (stackingGroup !== null) {
    parts.push(`stacking=${stackingGroup}`);
  }
  return parts.join(" · ");
}

function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : Number(value.toFixed(3)).toLocaleString("en-US");
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatSignedNumber(value: number): string {
  const formatted = formatNumber(value);
  return value >= 0 ? `+${formatted}` : formatted;
}

function toggleKey(current: ReadonlySet<string>, key: string): ReadonlySet<string> {
  const next = new Set(current);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

function readRecordList(record: unknown, key: string): Record<string, unknown>[] {
  const value = isRecord(record) ? record[key] : undefined;
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function readRecord(record: unknown, key: string): Record<string, unknown> | null {
  if (!isRecord(record)) {
    return null;
  }
  const value = record[key];
  return isRecord(value) ? value : null;
}

function readString(record: Record<string, unknown> | null, key: string): string | null {
  if (record === null) {
    return null;
  }
  const value = record[key];
  return typeof value === "string" && value !== "" ? value : null;
}

function readNumber(record: Record<string, unknown> | null, key: string): number | null {
  if (record === null) {
    return null;
  }
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
