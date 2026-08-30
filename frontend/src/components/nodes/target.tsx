import type { CSSProperties } from "react";
import { ELEMENT_COLORS, ELEMENT_LABELS } from "../../theme/elements";
import { RESISTANCE_ELEMENT_KEYS } from "../../workflow/registry";
import { FieldRow, InlineError, NumberField, TextField } from "../common/fields";
import type { NodeEditorProps } from "./common";
import { asNumber, asString, firstError, isPlainObject } from "./common";
export function TargetEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const position = isPlainObject(params.position) ? params.position : {};
  const resistance = isPlainObject(params.resistance) ? params.resistance : {};
  function updatePosition(axis: "x" | "y" | "z", value: number) {
    onChange({ ...params, position: { ...position, [axis]: value } });
  }
  function updateResistance(key: string, value: number) {
    onChange({ ...params, resistance: { ...resistance, [key]: value } });
  }
  return (
    <div className="node-editor">
      <FieldRow label="索引" error={firstError(fieldErrors, "index")}>
        <NumberField
          value={asNumber(params.index)}
          min={0}
          onChange={(value) => onChange({ ...params, index: value ?? 0 })}
        />
      </FieldRow>
      <FieldRow label="目标名称" error={firstError(fieldErrors, "label")}>
        <TextField
          value={asString(params.label) ?? "遗迹守卫"}
          onChange={(value) => onChange({ ...params, label: value })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          min={1}
          max={100}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <div className="node-editor-group">
        <span className="node-editor-group-title">位置</span>
        <div className="target-position-row">
          {POSITION_AXES.map((axis) => (
            <div key={axis.key} className="target-position-axis">
              <div className="target-position-field">
                <span className="target-position-label">{axis.label}</span>
                <NumberField
                  value={asNumber(position[axis.key]) ?? axis.default}
                  onChange={(value) => updatePosition(axis.key, value ?? axis.default)}
                />
              </div>
              {firstError(fieldErrors, `position.${axis.key}`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `position.${axis.key}`)!} />
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="node-editor-group">
        <span className="node-editor-group-title">目标抗性</span>
        <div className="target-resistance-grid">
          {RESISTANCE_ELEMENT_KEYS.map((key) => (
            <div key={key} className="target-resistance-cell">
              <div
                className="target-resistance-field"
                style={
                  {
                    "--element-color": ELEMENT_COLORS[key] ?? "#64748b",
                  } as CSSProperties
                }
              >
                <span className="target-resistance-badge">
                  {ELEMENT_LABELS[key] ?? key}
                </span>
                <NumberField
                  value={asNumber(resistance[key]) ?? 10}
                  onChange={(value) => updateResistance(key, value ?? 10)}
                  format={(value) => `${value}%`}
                />
              </div>
              {firstError(fieldErrors, `resistance.${key}`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `resistance.${key}`)!} />
              )}
            </div>
          ))}
        </div>
      </div>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

const POSITION_AXES = [
  { key: "x", label: "X", default: 0 },
  { key: "y", label: "Y", default: 0 },
  { key: "z", label: "Z", default: 5 },
] as const;
