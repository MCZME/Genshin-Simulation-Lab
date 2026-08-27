/** 分组聚合节点：卡片直编。 */

import { AGGREGATE_FUNCTIONS } from "../../../workflow/templates";
import type { TableShape } from "../../../workflow/templates";
import {
  COLUMN_NAME_PATTERN,
  upstreamShape,
  type EditorProps,
  type EditorRow,
} from "./context";

const AGGREGATE_FUNCTION_LABELS: Record<string, string> = {
  sum: "求和",
  count: "计数",
  avg: "平均",
  max: "最大",
  min: "最小",
  stddev: "标准差",
  p95: "95% 分位",
};

function aggregateFunctionsForType(type: string, currentFn: string): string[] {
  const base = type === "int" || type === "float" ? [...AGGREGATE_FUNCTIONS] : ["count"];
  return base.includes(currentFn) ? base : [...base, currentFn];
}

function aggregateDefaultName(fn: string, column: string): string {
  return `${fn}_${column}`;
}

function normalizeAggregateRow(row: EditorRow): EditorRow {
  const next = { ...row };
  if (typeof next.as !== "string" || next.as.trim() === "") {
    delete next.as;
  }
  return next;
}

function aggregateErrors(
  groupBy: string[],
  aggregates: EditorRow[],
  shape: TableShape[],
): (string | null)[] {
  const types = new Map(shape.map((column) => [column.name, column.type]));
  const seen = new Set(groupBy);
  return aggregates.map((row, index) => {
    const prefix = `第 ${index + 1} 个统计指标：`;
    const fn = row.fn;
    const column = row.column;
    if (typeof fn !== "string" || !AGGREGATE_FUNCTIONS.includes(fn as never)) {
      return `${prefix}请选择聚合函数`;
    }
    if (typeof column !== "string" || column === "") {
      return `${prefix}请选择列`;
    }
    const type = types.get(column) ?? "";
    if (type === "") {
      return `${prefix}列不存在`;
    }
    if (fn !== "count" && type !== "int" && type !== "float") {
      return `${prefix}该函数仅适用于数值列`;
    }
    const name =
      typeof row.as === "string" && row.as.trim() !== ""
        ? row.as.trim()
        : aggregateDefaultName(fn, column);
    if (!COLUMN_NAME_PATTERN.test(name)) {
      return `${prefix}结果列名不合法（中文/字母/数字/下划线，≤64 位）`;
    }
    if (seen.has(name)) {
      return `${prefix}结果列名重复：${name}`;
    }
    seen.add(name);
    return null;
  });
}

export function AggregateEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const types = new Map(shape.map((column) => [column.name, column.type]));
  const names = shape.map((column) => column.name);
  const groupBy = Array.isArray(node.params.group_by)
    ? (node.params.group_by as string[])
    : [];
  const aggregates = Array.isArray(node.params.aggregates)
    ? (node.params.aggregates as EditorRow[])
    : [];
  const toggleGroup = (name: string) => {
    onChange({
      ...node.params,
      group_by: groupBy.includes(name)
        ? groupBy.filter((item) => item !== name)
        : [...groupBy, name],
    });
  };
  const updateAggregate = (index: number, patch: Partial<EditorRow>) => {
    const row = aggregates[index] ?? {};
    const merged = { ...row, ...patch };
    const nextType =
      typeof merged.column === "string" ? (types.get(merged.column) ?? "") : "";
    if (
      patch.column !== undefined &&
      typeof merged.fn === "string" &&
      merged.fn !== "count" &&
      nextType !== "int" &&
      nextType !== "float"
    ) {
      merged.fn = "count";
    }
    const fn = typeof merged.fn === "string" ? merged.fn : "";
    const column = typeof merged.column === "string" ? merged.column : "";
    const oldDefault = aggregateDefaultName(
      typeof row.fn === "string" ? row.fn : "",
      typeof row.column === "string" ? row.column : "",
    );
    let next = { ...merged };
    const currentAs = typeof merged.as === "string" ? merged.as : "";
    if (
      !("as" in patch) &&
      fn !== "" &&
      column !== "" &&
      (currentAs === "" || (typeof row.as === "string" && row.as === oldDefault))
    ) {
      next.as = aggregateDefaultName(fn, column);
    }
    next = normalizeAggregateRow(next);
    onChange({
      ...node.params,
      aggregates: aggregates.map((item, i) => (i === index ? next : item)),
    });
  };
  const errors = aggregateErrors(groupBy, aggregates, shape);
  return (
    <div className="aggregate-inline">
      <section className="aggregate-section">
        <h4 className="aggregate-section-title">统计维度（{groupBy.length}）</h4>
        {names.length === 0 ? (
          <p className="analysis-editor-empty">未连接数据源</p>
        ) : (
          <ul className="aggregate-group-list">
            {names.map((name) => (
              <li key={name}>
                <label>
                  <input
                    type="checkbox"
                    checked={groupBy.includes(name)}
                    onChange={() => toggleGroup(name)}
                  />
                  <span>
                    {name}（{types.get(name) ?? ""}）
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="aggregate-section">
        <h4 className="aggregate-section-title">统计指标（{aggregates.length}）</h4>
        {aggregates.map((row, index) => (
          <AggregateRow
            key={index}
            row={row}
            shape={shape}
            types={types}
            error={errors[index]}
            onChange={(patch) => updateAggregate(index, patch)}
            onRemove={() =>
              onChange({
                ...node.params,
                aggregates: aggregates.filter((_, i) => i !== index),
              })
            }
          />
        ))}
        <button
          type="button"
          className="filter-add-button"
          onClick={() =>
            onChange({
              ...node.params,
              aggregates: [...aggregates, normalizeAggregateRow({ fn: "sum", column: "" })],
            })
          }
        >
          ＋ 添加统计指标
        </button>
        {groupBy.length === 0 && aggregates.length === 0 && (
          <p className="analysis-editor-empty">至少选择一个统计维度或添加一个统计指标</p>
        )}
      </section>
    </div>
  );
}

function AggregateRow({
  row,
  shape,
  types,
  error,
  onChange,
  onRemove,
}: {
  row: EditorRow;
  shape: TableShape[];
  types: Map<string, string>;
  error: string | null;
  onChange: (patch: Partial<EditorRow>) => void;
  onRemove: () => void;
}) {
  const fn = typeof row.fn === "string" ? row.fn : "";
  const column = typeof row.column === "string" ? row.column : "";
  const type = column === "" ? "" : (types.get(column) ?? "");
  const functions = aggregateFunctionsForType(type, fn);
  const defaultName = fn !== "" && column !== "" ? aggregateDefaultName(fn, column) : "";
  const as = typeof row.as === "string" ? row.as : "";
  return (
    <div className="aggregate-row">
      <div className="aggregate-line">
        <select value={fn} onChange={(event) => onChange({ fn: event.target.value })}>
          <option value="">函数…</option>
          {functions.map((item) => (
            <option key={item} value={item}>
              {AGGREGATE_FUNCTION_LABELS[item] ?? item}
            </option>
          ))}
        </select>
        <select value={column} onChange={(event) => onChange({ column: event.target.value })}>
          <option value="">列…</option>
          {shape.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}（{item.type}）
            </option>
          ))}
        </select>
        <input
          value={as}
          placeholder={defaultName === "" ? "结果列名" : `默认：${defaultName}`}
          onChange={(event) => onChange({ as: event.target.value })}
        />
        <button type="button" className="filter-row-remove" title="移除指标" onClick={onRemove}>
          ×
        </button>
      </div>
      {error !== null && <p className="filter-row-error">{error}</p>}
    </div>
  );
}
