/** 设置列值节点：为列写入固定值；列名与上游相同则整列替换，否则新增一列。 */

import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
} from "./context";
import { ImeSafeInput, ImeSafeTextarea } from "./imeInput";

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

  const rowErrors: string[][] = [];
  const seenAppended = new Set<string>();
  const overridden = new Set<string>();
  rows.forEach((row) => {
    const messages: string[] = [];
    const name = row.name?.trim() ?? "";
    const sourceType = inputTypes.get(name);
    if (name === "") {
      messages.push("请填写列名");
    } else if (!COLUMN_NAME_PATTERN.test(name)) {
      messages.push("列名不合法（中文/字母/数字/下划线，≤64 位）");
    } else if (sourceType !== undefined) {
      if (overridden.has(name)) {
        messages.push(`输入列 ${name} 不能重复覆盖`);
      } else {
        overridden.add(name);
      }
    } else if (seenAppended.has(name)) {
      messages.push(`新列名重复：${name}`);
    } else {
      seenAppended.add(name);
    }
    if (row.type !== "string" && row.type !== "int" && row.type !== "float" && row.type !== "bool") {
      messages.push("请选择类型");
    } else if (row.type === "string" && typeof row.value !== "string") {
      messages.push("字符串需要文本值");
    } else if (row.type === "int" && !Number.isInteger(row.value)) {
      messages.push("整数需要整数值");
    } else if (row.type === "float" && typeof row.value !== "number") {
      messages.push("浮点数需要数值");
    } else if (row.type === "bool" && typeof row.value !== "boolean") {
      messages.push("布尔需要 true/false");
    }
    if (sourceType !== undefined && row.type !== undefined && row.type !== sourceType) {
      messages.push(`覆盖列类型须与输入列一致（${sourceType}）`);
    }
    rowErrors.push(messages);
  });

  return (
    <div className="derive-inline">
      {rows.length === 0 && (
        <p className="analysis-editor-empty">至少添加一个列设置</p>
      )}
      {rows.map((row, index) => (
        <div className="derive-row" key={index}>
          <div className="derive-line">
            <ImeSafeInput
              aria-label={`设置列名 ${index + 1}`}
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
              aria-label={`设置列类型 ${index + 1}`}
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
                aria-label={`设置列值 ${index + 1}`}
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
            ) : null}
            <button
              type="button"
              className="analysis-row-remove"
              title="移除该设置"
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
          {row.type !== "bool" && (
            <div className="derive-value">
              {row.type === "int" || row.type === "float" ? (
                <input
                  aria-label={`设置列值 ${index + 1}`}
                  placeholder="0"
                  type="number"
                  step={row.type === "int" ? 1 : "any"}
                  value={
                    typeof row.value === "number" && Number.isFinite(row.value)
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
                    } else {
                      const parsed = Number(raw);
                      updateRow(index, { value: raw === "" ? "" : parsed });
                    }
                  }}
                />
              ) : (
                <ImeSafeTextarea
                  aria-label={`设置列值 ${index + 1}`}
                  placeholder="值"
                  value={typeof row.value === "string" ? row.value : ""}
                  onChange={(value) => updateRow(index, { value })}
                />
              )}
            </div>
          )}
          {rowErrors[index].map((message) => (
            <p key={message} className="analysis-row-error">
              {message}
            </p>
          ))}
        </div>
      ))}
      <button
        type="button"
        className="analysis-add-button"
        onClick={() =>
          onChange({
            ...node.params,
            columns: [...rows, { name: "", type: "string", value: "" }],
          })
        }
      >
        ＋ 添加列设置
      </button>
    </div>
  );
}
