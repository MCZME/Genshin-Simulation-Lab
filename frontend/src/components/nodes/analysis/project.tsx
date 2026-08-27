/** 投影节点：卡片直编。 */

import type { TableShape } from "../../../workflow/templates";
import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
  type EditorRow,
} from "./context";

function normalizeProjectRow(row: EditorRow): EditorRow {
  const next = { ...row };
  const name = typeof next.name === "string" ? next.name : "";
  if (typeof next.as !== "string" || next.as.trim() === "" || next.as.trim() === name) {
    delete next.as;
  }
  return next;
}

function projectOutputName(row: EditorRow): string {
  const name = typeof row.name === "string" ? row.name : "";
  if (typeof row.as === "string" && row.as.trim() !== "") {
    return row.as.trim();
  }
  return name;
}

function projectErrors(rows: EditorRow[], shape: TableShape[]): (string | null)[] {
  const types = new Map(shape.map((column) => [column.name, column.type]));
  const seen = new Set<string>();
  return rows.map((row, index) => {
    const prefix = `第 ${index + 1} 列：`;
    const name = typeof row.name === "string" ? row.name : "";
    if (name === "" || !types.has(name)) {
      return `${prefix}请选择列`;
    }
    const output = projectOutputName(row);
    if (!COLUMN_NAME_PATTERN.test(output)) {
      return `${prefix}输出列名不合法（中文/字母/数字/下划线，≤64 位）`;
    }
    if (seen.has(output)) {
      return `${prefix}输出列名重复：${output}`;
    }
    seen.add(output);
    return null;
  });
}

export function ProjectEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const rows = Array.isArray(node.params.columns)
    ? (node.params.columns as EditorRow[])
    : [];
  const updateRow = (index: number, patch: Partial<EditorRow>) => {
    const row = rows[index] ?? {};
    const merged = { ...row, ...patch };
    if (patch.name !== undefined) {
      const oldName = typeof row.name === "string" ? row.name : "";
      const oldAs = typeof row.as === "string" ? row.as : "";
      if (oldAs === "" || oldAs === oldName) {
        delete merged.as;
      }
    }
    onChange({
      ...node.params,
      columns: rows.map((item, i) =>
        i === index ? normalizeProjectRow(merged) : item,
      ),
    });
  };
  const errors = projectErrors(rows, shape);
  return (
    <div className="project-inline">
      {rows.length === 0 && <p className="analysis-editor-empty">至少选择一列</p>}
      {rows.map((row, index) => (
        <ProjectRow
          key={index}
          row={row}
          shape={shape}
          error={errors[index]}
          onChange={(patch) => updateRow(index, patch)}
          onRemove={() =>
            onChange({
              ...node.params,
              columns: rows.filter((_, i) => i !== index),
            })
          }
        />
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() => onChange({ ...node.params, columns: [...rows, {}] })}
      >
        ＋ 添加列
      </button>
    </div>
  );
}

function ProjectRow({
  row,
  shape,
  error,
  onChange,
  onRemove,
}: {
  row: EditorRow;
  shape: TableShape[];
  error: string | null;
  onChange: (patch: Partial<EditorRow>) => void;
  onRemove: () => void;
}) {
  const name = typeof row.name === "string" ? row.name : "";
  const as = typeof row.as === "string" ? row.as : "";
  return (
    <div className="project-row">
      <div className="project-line">
        <select value={name} onChange={(event) => onChange({ name: event.target.value })}>
          <option value="">选择列…</option>
          {shape.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}（{column.type}）
            </option>
          ))}
        </select>
        <input
          value={as}
          placeholder={name === "" ? "输出列名" : `默认：${name}`}
          onChange={(event) => onChange({ as: event.target.value })}
        />
        <button type="button" className="filter-row-remove" title="移除列" onClick={onRemove}>
          ×
        </button>
      </div>
      {error !== null && <p className="filter-row-error">{error}</p>}
    </div>
  );
}
