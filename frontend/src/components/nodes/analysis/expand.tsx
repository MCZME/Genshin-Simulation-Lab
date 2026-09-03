/** 展开行节点：输入行与常量值列表做笛卡尔积（行级构造）。 */

import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
} from "./context";
import { ImeSafeInput } from "./imeInput";

const EXPAND_TYPES = ["string", "int", "float", "bool"] as const;

interface ExpandRow {
  name?: string;
  type?: string;
  values?: unknown[];
  values_text?: string;
}

function parseValues(text: string, type: string): unknown[] {
  const raw = text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
  if (type === "int") {
    return raw
      .map((item) => Number(item))
      .filter((value) => Number.isInteger(value));
  }
  if (type === "float") {
    return raw
      .map((item) => Number(item))
      .filter((value) => Number.isFinite(value));
  }
  if (type === "bool") {
    return raw.map((item) => item === "true");
  }
  return raw;
}

export function ExpandEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const rows = Array.isArray(node.params.columns)
    ? (node.params.columns as ExpandRow[])
    : [];
  const taken = new Set(shape.map((column) => column.name));

  const updateRow = (index: number, patch: Partial<ExpandRow>) => {
    onChange({
      ...node.params,
      columns: rows.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  };

  const errors: string[] = [];
  let total = 1;
  rows.forEach((row, index) => {
    const name = row.name?.trim() ?? "";
    if (name === "") {
      errors.push(`第 ${index + 1} 行：请填写列名`);
    } else if (!COLUMN_NAME_PATTERN.test(name)) {
      errors.push(`第 ${index + 1} 行：列名不合法`);
    } else if (taken.has(name)) {
      errors.push(`第 ${index + 1} 行：与输入列或前列重名`);
    }
    if (
      row.type !== "string" &&
      row.type !== "int" &&
      row.type !== "float" &&
      row.type !== "bool"
    ) {
      errors.push(`第 ${index + 1} 行：请选择类型`);
      return;
    }
    const values = Array.isArray(row.values) ? row.values : [];
    if (values.length === 0) {
      errors.push(`第 ${index + 1} 行：至少一个值`);
      return;
    }
    if (values.length > 64) {
      errors.push(`第 ${index + 1} 行：单列最多 64 个值`);
      return;
    }
    total *= values.length;
  });
  if (total > 10_000) {
    errors.push("展开组合数超过 10000 行上限");
  }

  return (
    <div className="expand-inline">
      {rows.length === 0 && (
        <p className="analysis-editor-empty">至少添加一个展开维度列</p>
      )}
      {rows.map((row, index) => (
        <div className="expand-row" key={index}>
          <ImeSafeInput
            aria-label={`展开列名 ${index + 1}`}
            placeholder="列名"
            value={row.name ?? ""}
            onChange={(value) => updateRow(index, { name: value.trim() })}
          />
          <select
            aria-label={`展开列类型 ${index + 1}`}
            value={row.type ?? ""}
            onChange={(event) => {
              const type = event.target.value;
              updateRow(index, {
                type,
                values: type === "bool" ? [false] : [],
                values_text: type === "bool" ? "false" : "",
              });
            }}
          >
            <option value="">类型…</option>
            {EXPAND_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <ImeSafeInput
            aria-label={`展开值 ${index + 1}`}
            placeholder="逗号分隔的值，如 600,1200"
            value={row.values_text ?? (row.values ?? []).join(",")}
            onChange={(value) =>
              updateRow(index, {
                values_text: value,
                values: parseValues(value, row.type ?? "string"),
              })
            }
          />
          <button
            type="button"
            className="filter-row-remove"
            title="移除展开维度"
            onClick={() =>
              onChange({
                ...node.params,
                columns: rows.filter((_, i) => i !== index),
              })
            }
          >
            ×
          </button>
        </div>
      ))}
      {errors.map((message) => (
        <p key={message} className="filter-row-error">
          {message}
        </p>
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() =>
          onChange({
            ...node.params,
            columns: [...rows, { name: "", type: "string", values: [""], values_text: "" }],
          })
        }
      >
        ＋ 添加展开维度
      </button>
    </div>
  );
}
