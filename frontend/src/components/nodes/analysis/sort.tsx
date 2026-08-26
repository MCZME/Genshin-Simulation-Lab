/** 排序节点：卡片直编。 */

import type { TableShape } from "../../../workflow/templates";
import { upstreamShape, type EditorProps, type EditorRow } from "./context";

const SORT_DIRECTION_LABELS: Record<string, string> = {
  asc: "升序",
  desc: "降序",
};

const SORT_ORDER_SYMBOLS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];

function sortErrors(keys: EditorRow[], shape: TableShape[]): (string | null)[] {
  const types = new Map(shape.map((column) => [column.name, column.type]));
  const seen = new Set<string>();
  return keys.map((row, index) => {
    const prefix = `第 ${index + 1} 个排序键：`;
    const column = typeof row.column === "string" ? row.column : "";
    if (column === "" || !types.has(column)) {
      return `${prefix}请选择列`;
    }
    if (seen.has(column)) {
      return `${prefix}列重复：${column}`;
    }
    seen.add(column);
    const direction = typeof row.direction === "string" ? row.direction : "";
    if (direction !== "asc" && direction !== "desc") {
      return `${prefix}请选择排序方向`;
    }
    return null;
  });
}

export function SortEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const keys = Array.isArray(node.params.keys) ? (node.params.keys as EditorRow[]) : [];
  const updateKey = (index: number, patch: Partial<EditorRow>) => {
    const row = keys[index] ?? {};
    const merged = { ...row, ...patch };
    if (
      patch.column !== undefined &&
      (merged.direction === undefined || merged.direction === "")
    ) {
      merged.direction = "desc";
    }
    onChange({
      ...node.params,
      keys: keys.map((item, i) => (i === index ? merged : item)),
    });
  };
  const moveKey = (index: number, offset: -1 | 1) => {
    const target = index + offset;
    if (target < 0 || target >= keys.length) {
      return;
    }
    const next = [...keys];
    [next[index], next[target]] = [next[target], next[index]];
    onChange({ ...node.params, keys: next });
  };
  const errors = sortErrors(keys, shape);
  return (
    <div className="sort-inline">
      {keys.length === 0 && <p className="analysis-editor-empty">至少添加一个排序键</p>}
      {keys.map((row, index) => (
        <SortKeyRow
          key={index}
          row={row}
          shape={shape}
          index={index}
          total={keys.length}
          error={errors[index]}
          onChange={(patch) => updateKey(index, patch)}
          onRemove={() =>
            onChange({
              ...node.params,
              keys: keys.filter((_, i) => i !== index),
            })
          }
          onMove={(offset) => moveKey(index, offset)}
        />
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() =>
          onChange({
            ...node.params,
            keys: [...keys, { column: "", direction: "desc" }],
          })
        }
      >
        ＋ 添加排序键
      </button>
    </div>
  );
}

function SortKeyRow({
  row,
  shape,
  index,
  total,
  error,
  onChange,
  onRemove,
  onMove,
}: {
  row: EditorRow;
  shape: TableShape[];
  index: number;
  total: number;
  error: string | null;
  onChange: (patch: Partial<EditorRow>) => void;
  onRemove: () => void;
  onMove: (offset: -1 | 1) => void;
}) {
  const column = typeof row.column === "string" ? row.column : "";
  const direction = typeof row.direction === "string" ? row.direction : "";
  return (
    <div className="sort-key-row">
      <div className="sort-key-line">
        <span className="sort-key-index">
          {SORT_ORDER_SYMBOLS[index] ?? String(index + 1)}
        </span>
        <select value={column} onChange={(event) => onChange({ column: event.target.value })}>
          <option value="">选择列…</option>
          {shape.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}（{item.type}）
            </option>
          ))}
        </select>
        <select
          value={direction}
          onChange={(event) => onChange({ direction: event.target.value })}
        >
          <option value="">方向…</option>
          {(["asc", "desc"] as const).map((item) => (
            <option key={item} value={item}>
              {SORT_DIRECTION_LABELS[item]}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="sort-move-button"
          title="上移"
          disabled={index === 0}
          onClick={() => onMove(-1)}
        >
          ↑
        </button>
        <button
          type="button"
          className="sort-move-button"
          title="下移"
          disabled={index === total - 1}
          onClick={() => onMove(1)}
        >
          ↓
        </button>
        <button type="button" className="filter-row-remove" title="移除排序键" onClick={onRemove}>
          ×
        </button>
      </div>
      {error !== null && <p className="filter-row-error">{error}</p>}
    </div>
  );
}
