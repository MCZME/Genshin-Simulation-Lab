import { useState } from "react";
import { AssetPicker } from "../common/AssetPicker";
import { CollapsibleGroup, FieldRow, InlineError, NumberField } from "../common/fields";
import { ARTIFACT_RAW_STAT_KEYS, ARTIFACT_STAT_KEYS } from "../../workflow/registry";
import type { NodeEditorProps } from "./common";
import { asNumber, asString, firstError, isPlainObject } from "./common";
const CHARACTER_LEVELS = [...Array.from({ length: 90 }, (_, index) => index + 1), 95, 100];
const ARTIFACT_PIECE_OPTIONS = [1, 2, 4];

interface ArtifactSetRow {
  asset_key: string;
  pieces: number;
}

interface ArtifactStatRow {
  key: string;
  value: number;
}

const ARTIFACT_STAT_LABELS: Record<string, string> = {
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

const ARTIFACT_STAT_GROUPS: ReadonlyArray<{ label: string; keys: readonly string[] }> = [
  {
    label: "基础",
    keys: ["hp_percent", "atk_percent", "def_percent", "flat_hp", "flat_atk", "flat_def"],
  },
  {
    label: "暴击与精通",
    keys: ["crit_rate", "crit_damage", "elemental_mastery"],
  },
  {
    label: "充能与治疗",
    keys: ["energy_recharge", "healing_bonus"],
  },
  {
    label: "元素伤害",
    keys: [
      "physical_damage_bonus",
      "pyro_damage_bonus",
      "hydro_damage_bonus",
      "electro_damage_bonus",
      "cryo_damage_bonus",
      "anemo_damage_bonus",
      "geo_damage_bonus",
      "dendro_damage_bonus",
    ],
  },
];

export function CharacterEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const talents = isPlainObject(params.talents) ? params.talents : {};
  function updateTalent(key: string, level: number) {
    onChange({ ...params, talents: { ...talents, [key]: level } });
  }
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          max={4}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="角色" error={firstError(fieldErrors, "asset")}>
        <AssetPicker
          assetType="characters"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          options={CHARACTER_LEVELS}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="命座" error={firstError(fieldErrors, "constellation")}>
        <NumberField
          value={asNumber(params.constellation)}
          min={0}
          max={6}
          onChange={(value) => onChange({ ...params, constellation: value ?? 0 })}
        />
      </FieldRow>
      <div className="node-editor-group">
        <span className="node-editor-group-title">天赋</span>
        <FieldRow label="普通攻击" error={firstError(fieldErrors, "talents.normal_attack")}>
          <NumberField
            value={asNumber(talents.normal_attack) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("normal_attack", value ?? 1)}
          />
        </FieldRow>
        <FieldRow label="元素战技" error={firstError(fieldErrors, "talents.elemental_skill")}>
          <NumberField
            value={asNumber(talents.elemental_skill) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("elemental_skill", value ?? 1)}
          />
        </FieldRow>
        <FieldRow label="元素爆发" error={firstError(fieldErrors, "talents.elemental_burst")}>
          <NumberField
            value={asNumber(talents.elemental_burst) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("elemental_burst", value ?? 1)}
          />
        </FieldRow>
      </div>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function WeaponEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          max={4}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="武器" error={firstError(fieldErrors, "asset")}>
        <AssetPicker
          assetType="weapons"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          min={1}
          max={90}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="精炼" error={firstError(fieldErrors, "refinement")}>
        <NumberField
          value={asNumber(params.refinement)}
          min={1}
          max={5}
          onChange={(value) => onChange({ ...params, refinement: value ?? 1 })}
        />
      </FieldRow>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

function artifactSetRows(params: Record<string, unknown>): ArtifactSetRow[] {
  const raw = params.sets;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter((item): item is Record<string, unknown> => isPlainObject(item))
    .map((item) => ({
      asset_key: asString(item.asset_key) ?? "",
      pieces: asNumber(item.pieces) ?? 4,
    }));
}

function artifactStatRows(params: Record<string, unknown>): ArtifactStatRow[] {
  const stats = isPlainObject(params.stats) ? params.stats : {};
  return Object.entries(stats)
    .filter(
      ([key, value]) =>
        ARTIFACT_STAT_KEYS.includes(key) &&
        typeof value === "number" &&
        Number.isFinite(value),
    )
    .map(([key, value]) => ({ key, value: value as number }));
}

/** 百分比词条界面按百分比显示，存储使用小数倍率。 */
function statDisplayValue(key: string, stored: number): number {
  return ARTIFACT_RAW_STAT_KEYS.includes(key) ? stored : Math.round(stored * 10000) / 100;
}

function statStoreValue(key: string, display: number): number {
  return ARTIFACT_RAW_STAT_KEYS.includes(key) ? display : display / 100;
}

export function ArtifactEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const rows = artifactSetRows(params);
  const statRows = artifactStatRows(params);
  const usedStatKeys = new Set(statRows.map((row) => row.key));
  const availableStatGroups = ARTIFACT_STAT_GROUPS.map((group) => ({
    label: group.label,
    keys: group.keys.filter((key) => !usedStatKeys.has(key)),
  })).filter((group) => group.keys.length > 0);
  const [addingStat, setAddingStat] = useState(false);

  function updateRows(next: ArtifactSetRow[]) {
    onChange({ ...params, sets: next });
  }

  function updateRow(index: number, patch: Partial<ArtifactSetRow>) {
    updateRows(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function addSetRow() {
    if (rows.length >= 2) {
      return;
    }
    updateRows([...rows, { asset_key: "", pieces: 4 }]);
  }

  function removeSetRow(index: number) {
    if (rows.length <= 0) {
      return;
    }
    updateRows(rows.filter((_, rowIndex) => rowIndex !== index));
  }

  function updateStats(next: Record<string, unknown>) {
    onChange({ ...params, stats: next });
  }

  function addStatRow(key: string) {
    updateStats({ ...(isPlainObject(params.stats) ? params.stats : {}), [key]: 0 });
  }

  function updateStatValue(key: string, display: number) {
    const stats = { ...(isPlainObject(params.stats) ? params.stats : {}) };
    stats[key] = statStoreValue(key, display);
    updateStats(stats);
  }

  function removeStatRow(key: string) {
    const stats = { ...(isPlainObject(params.stats) ? params.stats : {}) };
    delete stats[key];
    updateStats(stats);
  }

  return (
    <div className="node-editor artifact-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          max={4}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <CollapsibleGroup
        title="套装效果"
        summary={rows.length === 0 ? "未配置" : `${rows.length} 套`}
      >
        {rows.map((row, index) => (
          <div className="artifact-set-row" key={index}>
            <div className="artifact-set-row-main">
              <AssetPicker
                assetType="artifact-sets"
                value={row.asset_key}
                ariaLabel={`套装 ${index + 1}`}
                onChange={(asset) => updateRow(index, { asset_key: asset })}
              />
              {firstError(fieldErrors, `sets[${index}].asset_key`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `sets[${index}].asset_key`)!} />
              )}
              {firstError(fieldErrors, `sets[${index}].pieces`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `sets[${index}].pieces`)!} />
              )}
            </div>
            <div
              className="artifact-piece-toggle"
              role="group"
              aria-label={`套装 ${index + 1} 件数`}
            >
              {ARTIFACT_PIECE_OPTIONS.map((piece) => (
                <button
                  key={piece}
                  type="button"
                  className={`artifact-piece-option ${row.pieces === piece ? "active" : ""}`}
                  aria-pressed={row.pieces === piece}
                  onClick={() => updateRow(index, { pieces: piece })}
                >
                  {piece}件
                </button>
              ))}
            </div>
            <button
              type="button"
              className="icon-button danger artifact-set-remove"
              title={`删除套装 ${index + 1}`}
              onClick={() => removeSetRow(index)}
            >
              ×
            </button>
          </div>
        ))}
        {rows.length < 2 && (
          <button type="button" className="node-add-row" onClick={addSetRow}>
            + 添加套装
          </button>
        )}
        {firstError(fieldErrors, "sets") !== undefined && (
          <InlineError message={firstError(fieldErrors, "sets")!} />
        )}
      </CollapsibleGroup>
      <CollapsibleGroup
        title="属性词条"
        summary={statRows.length === 0 ? "未配置" : `${statRows.length} 词条`}
      >
        {(statRows.length > 0 || availableStatGroups.length > 0) && (
          <div className="artifact-stat-grid">
            {statRows.map((row) => {
              const label = ARTIFACT_STAT_LABELS[row.key] ?? row.key;
              const isPercent = !ARTIFACT_RAW_STAT_KEYS.includes(row.key);
              return (
                <div className="artifact-stat-cell" key={row.key}>
                  <span className="artifact-stat-label" title={label}>
                    {label}
                  </span>
                  <div className="artifact-stat-value">
                    <NumberField
                      value={statDisplayValue(row.key, row.value)}
                      min={0}
                      ariaLabel={label}
                      format={(value) => (isPercent ? `${value}%` : String(value))}
                      onChange={(value) => {
                        if (value !== null) {
                          updateStatValue(row.key, value);
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="icon-button danger artifact-stat-remove"
                      title={`删除词条 ${label}`}
                      onClick={() => removeStatRow(row.key)}
                    >
                      ×
                    </button>
                  </div>
                  {firstError(fieldErrors, `stats.${row.key}`) !== undefined && (
                    <InlineError message={firstError(fieldErrors, `stats.${row.key}`)!} />
                  )}
                </div>
              );
            })}
            {availableStatGroups.length > 0 && (
              <div className="artifact-stat-add">
                {addingStat ? (
                  <select
                    className="field artifact-stat-add-select"
                    autoFocus
                    value=""
                    aria-label="选择要添加的词条"
                    onBlur={() => setAddingStat(false)}
                    onChange={(event) => {
                      const key = event.target.value;
                      if (key !== "") {
                        addStatRow(key);
                        setAddingStat(false);
                      }
                    }}
                  >
                    <option value="" disabled>
                      选择词条…
                    </option>
                    {availableStatGroups.map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.keys.map((key) => (
                          <option key={key} value={key}>
                            {ARTIFACT_STAT_LABELS[key] ?? key}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                ) : (
                  <button
                    type="button"
                    className="artifact-stat-add-button"
                    onClick={() => setAddingStat(true)}
                  >
                    + 添加词条
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        {firstError(fieldErrors, "stats") !== undefined && (
          <InlineError message={firstError(fieldErrors, "stats")!} />
        )}
      </CollapsibleGroup>
      <p className="node-note">套装效果与属性至少配置一项；百分比词条按百分比输入</p>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}
