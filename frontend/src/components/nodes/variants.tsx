import type { EnumValue } from "../../workflow/types";
import {
  CollapsibleGroup,
  FieldRow,
  InlineError,
  NumberField,
  SelectField,
  TextField,
} from "../common/fields";
import type { NodeEditorProps } from "./common";
import { asNumber, asString, firstError, firstErrorPrefix } from "./common";
const ENUM_VALUE_TYPES = [
  { value: "asset", label: "资产" },
  { value: "number", label: "数值" },
  { value: "string", label: "文本" },
  { value: "json_fragment", label: "JSON 片段" },
] as const;


export function EnumEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const values = Array.isArray(params.values) ? (params.values as EnumValue[]) : [];
  const valueType = asString(params.value_type) ?? "asset";

  function updateValues(next: EnumValue[]) {
    onChange({ ...params, values: next });
  }

  return (
    <div className="node-editor">
      <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="值类型" error={firstError(fieldErrors, "value_type")}>
        <SelectField
          value={valueType}
          options={[...ENUM_VALUE_TYPES]}
          onChange={(value) => onChange({ ...params, value_type: value })}
        />
      </FieldRow>
      <CollapsibleGroup title="取值" summary={`${values.length} 个取值`}>
        {firstErrorPrefix(fieldErrors, "values") !== undefined && (
          <InlineError message={firstErrorPrefix(fieldErrors, "values")!} />
        )}
        <div className="enum-values">
          {values.map((item, index) => (
            <div className="enum-value-row" key={item.item_id}>
              <span className="enum-item-id">{item.item_id}</span>
              {valueType === "number" ? (
                <NumberField
                  value={typeof item.value === "number" ? item.value : Number(item.value)}
                  onChange={(value) => {
                    const next = [...values];
                    next[index] = { ...item, value: value ?? 0 };
                    updateValues(next);
                  }}
                />
              ) : (
                <TextField
                  value={String(item.value ?? "")}
                  mono
                  onChange={(value) => {
                    const next = [...values];
                    next[index] = { ...item, value };
                    updateValues(next);
                  }}
                />
              )}
              <TextField
                value={item.label ?? ""}
                placeholder="标签"
                onChange={(value) => {
                  const next = [...values];
                  next[index] = { ...item, label: value === "" ? null : value };
                  updateValues(next);
                }}
              />
              <button
                type="button"
                className="icon-button"
                title="删除取值"
                onClick={() => updateValues(values.filter((_, valueIndex) => valueIndex !== index))}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              updateValues([
                ...values,
                { item_id: nextEnumId(values), value: valueType === "number" ? 0 : "", label: null },
              ])
            }
          >
            + 添加取值
          </button>
        </div>
      </CollapsibleGroup>
    </div>
  );
}

export function RangeEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="起点" error={firstError(fieldErrors, "start")}>
        <NumberField
          value={asNumber(params.start)}
          onChange={(value) => onChange({ ...params, start: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="终点" error={firstError(fieldErrors, "end")}>
        <NumberField
          value={asNumber(params.end)}
          onChange={(value) => onChange({ ...params, end: value ?? 10 })}
        />
      </FieldRow>
      <FieldRow label="步长" error={firstError(fieldErrors, "step")}>
        <NumberField
          value={asNumber(params.step)}
          onChange={(value) => onChange({ ...params, step: value ?? 1 })}
        />
      </FieldRow>
    </div>
  );
}

function nextEnumId(values: EnumValue[]): string {
  const max = values.reduce((current, item) => {
    const suffix = Number(item.item_id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `e-${max + 1}`;
}
