/** 构造列节点：为输入表追加类型化常量列（描述符构造的最小原语）。 */

import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
} from "./context";
import { ImeSafeInput } from "./imeInput";

const DERIVE_TYPES = ["string", "int", "float", "bool"] as const;

interface DeriveRow {
  name?: string;
  type?: string;
  value?: unknown;
}

export function DeriveEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const rows = Array.isArray(node.params.columns)
    ? (node.params.columns as DeriveRow[])
    : [];
  const inputTypes = new Map(shape.map((column) => [column.name, column.type]));

  const updateRow = (index: number, patch: Partial<DeriveRow>) => {
    onChange({
      ...node.params,
      columns: rows.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  };

  const errors: string[] = [];
  const seenAppended = new Set<string>();
  rows.forEach((row, index) => {
    const messages: string[] = [];
    const name = row.name?.trim() ?? "";
    if (name === "") {
      messages.push(`第 ${index + 1} 行：请填写列名`);
    } else if (!COLUMN_NAME_PATTERN.test(name)) {
      messages.push(`第 ${index + 1} 行：列名不合法`);
    } else if (!inputTypes.has(name) && seenAppended.has(name)) {
      messages.push(`第 ${index + 1} 行：新列名重复`);
    } else if (!inputTypes.has(name)) {
      seenAppended.add(name);
    }
    if (row.type !== "string" && row.type !== "int" && row.type !== "float" && row.type !== "bool") {
      messages.push(`第 ${index + 1} 行：请选择类型`);
    } else if (row.type === "string" && typeof row.value !== "string") {
      messages.push(`第 ${index + 1} 行：字符串需要文本值`);
    } else if (row.type === "int" && !Number.isInteger(row.value)) {
      messages.push(`第 ${index + 1} 行：整数需要整数值`);
    } else if (row.type === "float" && typeof row.value !== "number") {
      messages.push(`第 ${index + 1} 行：浮点数需要数值`);
    } else if (row.type === "bool" && typeof row.value !== "boolean") {
      messages.push(`第 ${index + 1} 行：布尔需要 true/false`);
    }
    if (inputTypes.has(name) && row.type !== undefined && row.type !== inputTypes.get(name)) {
      messages.push(`第 ${index + 1} 行：覆盖列类型须与输入列一致`);
    }
    errors.push(...messages);
  });

  return (
    <div className="derive-inline">
      {rows.length === 0 && (
        <p className="analysis-editor-empty">至少添加一个构造列</p>
      )}
      {rows.map((row, index) => (
        <div className="derive-row" key={index}>
          <ImeSafeInput
            aria-label={`构造列名 ${index + 1}`}
            placeholder="列名"
            value={row.name ?? ""}
            onChange={(value) => {
              const name = value.trim();
              const sourceType = inputTypes.get(name);
              updateRow(index, {
                name,
                type: sourceType ?? row.type,
                ...(sourceType === "bool"
                  ? { value: false }
                  : sourceType === "int" || sourceType === "float"
                    ? { value: 0 }
                    : sourceType === "string"
                      ? { value: "" }
                      : {}),
              });
            }}
          />
          <select
            aria-label={`构造列类型 ${index + 1}`}
            value={row.type ?? ""}
            onChange={(event) => {
              const type = event.target.value as DeriveRow["type"];
              const value =
                type === "string"
                  ? ""
                  : type === "bool"
                    ? false
                    : type === "int" || type === "float"
                      ? 0
                      : row.value;
              updateRow(index, { type, value });
            }}
          >
            <option value="">类型…</option>
            {DERIVE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          {row.type === "bool" ? (
            <select
              aria-label={`构造列值 ${index + 1}`}
              value={row.value === true ? "true" : row.value === false ? "false" : ""}
              onChange={(event) =>
                updateRow(index, {
                  value: event.target.value === "true",
                })
              }
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              aria-label={`构造列值 ${index + 1}`}
              placeholder={row.type === "int" || row.type === "float" ? "0" : "值"}
              type={row.type === "int" || row.type === "float" ? "number" : "text"}
              value={
                typeof row.value === "string" || typeof row.value === "number"
                  ? String(row.value)
                  : ""
              }
              onChange={(event) => {
                const raw = event.target.value;
                if (row.type === "int") {
                  const parsed = Number(raw);
                  updateRow(index, {
                    value: raw === "" || !Number.isInteger(parsed) ? "" : parsed,
                  });
                } else if (row.type === "float") {
                  const parsed = Number(raw);
                  updateRow(index, { value: raw === "" ? "" : parsed });
                } else {
                  updateRow(index, { value: raw });
                }
              }}
            />
          )}
          <button
            type="button"
            className="filter-row-remove"
            title="移除构造列"
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
            columns: [...rows, { name: "", type: "string", value: "" }],
          })
        }
      >
        ＋ 添加构造列
      </button>
    </div>
  );
}
