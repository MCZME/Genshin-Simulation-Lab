import { AssetPicker } from "../common/AssetPicker";
import { FieldRow, InlineError, NumberField } from "../common/fields";
import type { NodeEditorProps } from "./common";
import { asNumber, asString, firstError, isPlainObject } from "./common";
const CHARACTER_LEVELS = [...Array.from({ length: 90 }, (_, index) => index + 1), 95, 100];
const ARTIFACT_PIECE_OPTIONS = [1, 2, 4];

interface ArtifactSetRow {
  asset_key: string;
  pieces: number;
}

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

export function ArtifactEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const rows = artifactSetRows(params);

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
    if (rows.length <= 1) {
      return;
    }
    updateRows(rows.filter((_, rowIndex) => rowIndex !== index));
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
      <div className="node-editor-group">
        <span className="node-editor-group-title">套装效果</span>
        {rows.map((row, index) => (
          <div className="artifact-set-row" key={index}>
            <div className="artifact-set-row-fields">
              <FieldRow
                label={`套装 ${index + 1}`}
                error={firstError(fieldErrors, `sets[${index}].asset_key`)}
              >
                <AssetPicker
                  assetType="artifact-sets"
                  value={row.asset_key}
                  onChange={(asset) => updateRow(index, { asset_key: asset })}
                />
              </FieldRow>
              <FieldRow
                label="件数"
                error={firstError(fieldErrors, `sets[${index}].pieces`)}
              >
                <NumberField
                  value={row.pieces}
                  options={ARTIFACT_PIECE_OPTIONS}
                  onChange={(value) => updateRow(index, { pieces: value ?? 4 })}
                />
              </FieldRow>
            </div>
            {rows.length > 1 && (
              <button
                type="button"
                className="icon-button danger artifact-set-remove"
                title={`删除套装 ${index + 1}`}
                onClick={() => removeSetRow(index)}
              >
                ×
              </button>
            )}
          </div>
        ))}
        {rows.length < 2 && (
          <button type="button" className="node-add-row" onClick={addSetRow}>
            + 添加套装
          </button>
        )}
      </div>
      {firstError(fieldErrors, "sets") !== undefined && (
        <InlineError message={firstError(fieldErrors, "sets")!} />
      )}
      <p className="node-note">圣遗物属性：暂不影响仿真</p>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}
