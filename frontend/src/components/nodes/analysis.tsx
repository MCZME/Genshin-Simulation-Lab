/** 分析区域节点编辑器（取数、关系算子、展示配置、数据提供）。 */

import { useState } from "react";
import type {
  AnalysisSchemaCatalog,
  AnalysisSnapshotPath,
  FilterCondition,
  TableShape,
} from "../../workflow/templates";
import { AGGREGATE_FUNCTIONS, CONDITION_OPERATORS, fetchColumns } from "../../workflow/templates";
import { configTargetView, viewInputShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";

type EditorRow = Record<string, unknown>;
type EditorParams = Record<string, unknown>;
interface EditorProps {
  node: WorkflowNode;
  onChange: (params: EditorParams) => void;
  fieldErrors?: Record<string, string[]>;
}
import { asString } from "./common";

export interface AnalysisEditorEnvironment {
  catalog: AnalysisSchemaCatalog | null;
  definition: WorkflowDefinition;
  shapes: Map<string, TableShape[] | null>;
}

const EditorEnvironmentContext = {
  current: null as AnalysisEditorEnvironment | null,
};

export function setAnalysisEditorEnvironment(env: AnalysisEditorEnvironment | null): void {
  EditorEnvironmentContext.current = env;
}

export function getAnalysisEditorEnvironment(): AnalysisEditorEnvironment | null {
  return EditorEnvironmentContext.current;
}

export const ANALYSIS_EDITOR_CONTEXT = Symbol("analysis-editor-context");

export function useContextEnv(): AnalysisEditorEnvironment {
  return (
    EditorEnvironmentContext.current ?? {
      catalog: null,
      definition: { schema_version: 1, meta: { name: "" }, regions: [], nodes: [], edges: [], layout: {} },
      shapes: new Map(),
    }
  );
}

function inputShapeFor(nodeId: string, portId: string): TableShape[] {
  const env = getAnalysisEditorEnvironment();
  if (env === null) {
    return [];
  }
  const edge = env.definition.edges.find(
    (item) => item.target_node_id === nodeId && item.target_port_id === portId,
  );
  if (edge === undefined) {
    return [];
  }
  return env.shapes.get(edge.source_node_id) ?? [];
}

function upstreamShape(nodeId: string): TableShape[] {
  return inputShapeFor(nodeId, "in");
}

interface RowListProps {
  rows: Record<string, unknown>[];
  columns: {
    key: string;
    placeholder: string;
    input?: "text" | "number";
    options?: string[];
  }[];
  onCreate: () => void;
  onUpdate: (index: number, patch: Record<string, unknown>) => void;
  onRemove: (index: number) => void;
}

function RowList({ rows, columns, onCreate, onUpdate, onRemove }: RowListProps) {
  return (
    <div className="analysis-editor">
      {rows.map((row, index) => (
        <div key={index} className="analysis-param-row">
          {columns.map((column) => (
            column.options !== undefined ? (
              <select
                key={column.key}
                value={row[column.key] === undefined || row[column.key] === null ? "" : String(row[column.key])}
                onChange={(event) => onUpdate(index, { [column.key]: event.target.value })}
              >
                <option value="">{column.placeholder}</option>
                {column.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <input
                key={column.key}
                placeholder={column.placeholder}
                value={row[column.key] === undefined || row[column.key] === null ? "" : String(row[column.key])}
                onChange={(event) =>
                  onUpdate(index, {
                    [column.key]:
                      column.input === "number" && event.target.value !== ""
                        ? Number(event.target.value)
                        : event.target.value,
                  })
                }
              />
            )
          ))}
          <button type="button" onClick={() => onRemove(index)}>
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onCreate()}
      >
        添加一行
      </button>
    </div>
  );
}

/** 获取数据节点：一个入口 + 来源切换（运行记录 / 事件记录）。 */
export function FetchEditor({ node, onChange }: EditorProps) {
  const source = node.params.source === "events" ? "events" : "runs";
  const switchSource = (next: "runs" | "events") => {
    if (next === source) {
      return;
    }
    if (next === "runs") {
      onChange({
        source: next,
        snapshot_columns: Array.isArray(node.params.snapshot_columns)
          ? node.params.snapshot_columns
          : [],
      });
    } else {
      onChange({
        source: next,
        event_types: Array.isArray(node.params.event_types) ? node.params.event_types : [],
        frame_min: node.params.frame_min,
        frame_max: node.params.frame_max,
        payload_columns: Array.isArray(node.params.payload_columns)
          ? node.params.payload_columns
          : [],
      });
    }
  };
  return (
    <div className="analysis-editor">
      <div className="fetch-source-switch">
        <button
          type="button"
          className={source === "runs" ? "active" : ""}
          onClick={() => switchSource("runs")}
        >
          运行记录
        </button>
        <button
          type="button"
          className={source === "events" ? "active" : ""}
          onClick={() => switchSource("events")}
        >
          事件记录
        </button>
      </div>
      {source === "runs" ? (
        <FetchRunsSource node={node} onChange={onChange} />
      ) : (
        <FetchEventsSource node={node} onChange={onChange} />
      )}
      <FetchShapeSummary node={node} />
    </div>
  );
}

/** 输出形状摘要：固定列折叠 + 提取列常显（只读，编辑在参数区）。 */
function FetchShapeSummary({ node }: { node: WorkflowNode }) {
  const columns = fetchColumns(node);
  if (columns === null) {
    return null;
  }
  const sourceLabel = node.params.source === "events" ? "事件记录" : "运行记录";
  return (
    <div className="fetch-shape-summary">
      <details className="fetch-shape-fixed">
        <summary>
          {sourceLabel}固定列 {columns.fixed.length}
        </summary>
        <ul className="fetch-shape-fixed-list">
          {columns.fixed.map((column) => (
            <li key={column.name}>
              <span className="fetch-shape-chip">
                {column.name}
                <em>{column.type}</em>
              </span>
            </li>
          ))}
        </ul>
      </details>
      <div className="fetch-shape-extracts">
        <span className="fetch-shape-label">提取列</span>
        {columns.extracts.length === 0 ? (
          <span className="fetch-shape-empty">无提取列</span>
        ) : (
          columns.extracts.map((column) => (
            <span key={column.name} className="fetch-shape-chip">
              {column.name}
              <em>{column.type}</em>
            </span>
          ))
        )}
      </div>
    </div>
  );
}

function FetchRunsSource({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const paths = env.catalog?.snapshotPaths() ?? [];
  const rows = Array.isArray(node.params.snapshot_columns)
    ? (node.params.snapshot_columns as EditorRow[])
    : [];
  /** 级联选择器的本地瞬态：行号 → 已选路径段；完整选中后才写入参数。 */
  const [selections, setSelections] = useState<Record<number, string[]>>({});
  const MAX_SEGMENTS = 5;

  const entryFor = (row: EditorRow): AnalysisSnapshotPath | null =>
    paths.find((item) => item.path === row.path) ?? null;
  const entryBySegments = (selected: string[]): AnalysisSnapshotPath | null =>
    paths.find(
      (item) =>
        item.segments.length === selected.length &&
        item.segments.every((segment, index) => segment === selected[index]),
    ) ?? null;
  const optionsAt = (selected: string[], level: number): string[] => {
    const prefix = selected.slice(0, level);
    return Array.from(
      new Set(
        paths
          .filter((item) => prefix.every((segment, index) => item.segments[index] === segment))
          .map((item) => item.segments[level])
          .filter((segment): segment is string => segment !== undefined),
      ),
    );
  };

  const updateRow = (index: number, patch: Record<string, unknown>) => {
    const next = [...rows];
    next[index] = { ...next[index], ...patch };
    onChange({ ...node.params, snapshot_columns: next });
  };

  const handleSegment = (index: number, level: number, value: string) => {
    const current = entryFor(rows[index]);
    const base = selections[index] ?? current?.segments ?? [];
    const selected = [...base.slice(0, level), value];
    setSelections((all) => ({ ...all, [index]: selected }));
    const match = entryBySegments(selected);
    if (match !== null) {
      updateRow(index, { path: match.path, type: match.type, name: match.default_name });
    }
  };

  const addRow = () => {
    const index = rows.length;
    setSelections((all) => ({ ...all, [index]: [] }));
    updateRow(index, { path: "", name: "", type: "string" });
  };

  const removeRow = (index: number) => {
    setSelections((all) => {
      const next = { ...all };
      delete next[index];
      return next;
    });
    onChange({
      ...node.params,
      snapshot_columns: rows.filter((_, itemIndex) => itemIndex !== index),
    });
  };

  return (
    <div className="analysis-editor">
      <div className="analysis-field">
        <span>快照提取列</span>
      </div>
      {rows.length === 0 && <p className="analysis-editor-empty">未添加提取列</p>}
      {rows.map((row, index) => {
        const entry = entryFor(row);
        const selected = selections[index] ?? entry?.segments ?? [];
        const isDraft = row.path === "" || row.path === undefined;
        const unknown = !isDraft && entry === null;
        const levelCount = entry !== null ? entry.segments.length : MAX_SEGMENTS;
        return (
          <div key={index} className="snapshot-extract-row">
            {!unknown && (
              <div className="snapshot-cascade">
                {Array.from({ length: levelCount }, (_, level) => (
                  <select
                    key={level}
                    aria-label={`快照路径第 ${level + 1} 段`}
                    value={selected[level] ?? ""}
                    onChange={(event) => handleSegment(index, level, event.target.value)}
                  >
                    <option value="">…</option>
                    {optionsAt(selected, level).map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ))}
              </div>
            )}
            {unknown && (
              <input
                className="snapshot-path-input"
                placeholder="快照路径（目录外，手动填写）"
                value={asString(row.path) ?? ""}
                onChange={(event) => updateRow(index, { path: event.target.value })}
              />
            )}
            <input
              aria-label={`提取列名 ${index + 1}`}
              placeholder="列名"
              value={asString(row.name) ?? ""}
              onChange={(event) => updateRow(index, { name: event.target.value })}
            />
            <span className="snapshot-type">{asString(row.type) ?? ""}</span>
            <button
              type="button"
              className="icon-button danger"
              title="移除"
              aria-label={`移除提取列 ${index + 1}`}
              onClick={() => removeRow(index)}
            >
              ×
            </button>
          </div>
        );
      })}
      <button type="button" className="snapshot-add" onClick={addRow}>
        ＋ 添加提取列
      </button>
    </div>
  );
}

function FetchEventsSource({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const eventTypes = env.catalog?.eventTypes() ?? [];
  const selected = Array.isArray(node.params.event_types) ? (node.params.event_types as string[]) : [];
  const extracts = Array.isArray(node.params.payload_columns) ? (node.params.payload_columns as EditorRow[]) : [];
  /** 载荷行的本地瞬态：行号 → 已选事件类型；选字段后才写入路径。 */
  const [eventTypeFor, setEventTypeFor] = useState<Record<number, string>>({});
  const toggleType = (name: string) => {
    const next = selected.includes(name) ? selected.filter((t) => t !== name) : [...selected, name];
    onChange({ ...node.params, event_types: next });
  };
  const updateRow = (index: number, patch: Record<string, unknown>) => {
    const next = [...extracts];
    next[index] = { ...next[index], ...patch };
    onChange({ ...node.params, payload_columns: next });
  };
  const typeOfRow = (index: number, row: EditorRow): string => {
    const known = eventTypeFor[index];
    if (known !== undefined && known !== "") {
      return known;
    }
    return (
      eventTypes.find((item) => item.fields.some((field) => field.path === row.path))?.name ?? ""
    );
  };
  const handleTypeChange = (index: number, name: string) => {
    setEventTypeFor((all) => ({ ...all, [index]: name }));
    updateRow(index, { path: "", type: "float", name: "" });
  };
  return (
    <div className="analysis-editor">
      <details>
        <summary>事件类型（已选 {selected.length}）</summary>
        <ul>
          {eventTypes.map((eventType) => (
            <li key={eventType.name}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(eventType.name)}
                  onChange={() => toggleType(eventType.name)}
                />
                <span>{eventType.name}</span>
              </label>
            </li>
          ))}
        </ul>
      </details>
      <div className="analysis-param-row">
        <input
          placeholder="起始帧"
          value={node.params.frame_min === undefined ? "" : String(node.params.frame_min)}
          onChange={(e) =>
            onChange({
              ...node.params,
              frame_min: e.target.value === "" ? undefined : Number(e.target.value),
            })
          }
        />
        <input
          placeholder="结束帧"
          value={node.params.frame_max === undefined ? "" : String(node.params.frame_max)}
          onChange={(e) =>
            onChange({
              ...node.params,
              frame_max: e.target.value === "" ? undefined : Number(e.target.value),
            })
          }
        />
      </div>
      <div className="analysis-field">
        <span>载荷提取列</span>
      </div>
      {extracts.length === 0 && <p className="analysis-editor-empty">未添加提取列</p>}
      {extracts.map((row, index) => {
        const typeName = typeOfRow(index, row);
        const unknown = row.path !== "" && row.path !== undefined && typeName === "";
        const fields = eventTypes.find((item) => item.name === typeName)?.fields ?? [];
        return (
          <div key={index} className="payload-extract-row">
            <select
              aria-label={`载荷事件类型 ${index + 1}`}
              value={typeName}
              onChange={(event) => handleTypeChange(index, event.target.value)}
            >
              <option value="">事件类型…</option>
              {eventTypes.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
            {typeName !== "" ? (
              <select
                aria-label={`载荷字段 ${index + 1}`}
                value={asString(row.path) ?? ""}
                onChange={(event) => {
                  const field = fields.find((item) => item.path === event.target.value);
                  if (field !== undefined) {
                    updateRow(index, {
                      path: field.path,
                      type: field.type,
                      name: defaultFieldName(field.path),
                    });
                  }
                }}
              >
                <option value="">字段…</option>
                {fields.map((field) => (
                  <option key={field.path} value={field.path}>
                    {field.path}
                  </option>
                ))}
              </select>
            ) : unknown ? (
              <input
                className="snapshot-path-input"
                placeholder="载荷路径（目录外，手动填写）"
                value={asString(row.path) ?? ""}
                onChange={(event) => updateRow(index, { path: event.target.value })}
              />
            ) : null}
            <input
              aria-label={`载荷列名 ${index + 1}`}
              placeholder="列名"
              value={asString(row.name) ?? ""}
              onChange={(event) => updateRow(index, { name: event.target.value })}
            />
            <span className="snapshot-type">{asString(row.type) ?? ""}</span>
            <button
              type="button"
              className="icon-button danger"
              title="移除"
              aria-label={`移除载荷列 ${index + 1}`}
              onClick={() => {
                setEventTypeFor((all) => {
                  const next = { ...all };
                  delete next[index];
                  return next;
                });
                onChange({
                  ...node.params,
                  payload_columns: extracts.filter((_, itemIndex) => itemIndex !== index),
                });
              }}
            >
              ×
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="snapshot-add"
        onClick={() => updateRow(extracts.length, { path: "", name: "", type: "float" })}
      >
        ＋ 添加提取列
      </button>
    </div>
  );
}

function defaultFieldName(path: string): string {
  const leaf = path.split(".").pop() ?? "";
  return leaf === "" ? "value" : leaf;
}

export function FilterEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const names = shape.map((column) => column.name);
  const conditions = Array.isArray(node.params.conditions) ? (node.params.conditions as FilterCondition[]) : [];
  const update = (next: FilterCondition[]) => onChange({ ...node.params, conditions: next });
  return (
    <div className="analysis-editor">
      <label className="analysis-field">
        <span>组合</span>
        <select
          value={node.params.mode === "any" ? "any" : "all"}
          onChange={(e) => onChange({ ...node.params, mode: e.target.value })}
        >
          <option value="all">全部满足</option>
          <option value="any">任一满足</option>
        </select>
      </label>
      {conditions.map((condition, index) => (
        <div key={index} className="analysis-param-row">
          <select
            value={condition.column}
            onChange={(e) =>
              update(conditions.map((item, i) => (i === index ? { ...item, column: e.target.value } : item)))
            }
          >
            <option value="">列…</option>
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={condition.op}
            onChange={(e) =>
              update(
                conditions.map((item, i) => {
                  if (i !== index) {
                    return item;
                  }
                  const op = e.target.value;
                  if (op === "is_null" || op === "is_not_null") {
                    return { column: item.column, op };
                  }
                  return { ...item, op };
                }),
              )
            }
          >
            {CONDITION_OPERATORS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
          {condition.op !== "is_null" && condition.op !== "is_not_null" && (
            <input
              placeholder="值"
              value={condition.value === undefined || condition.value === null ? "" : String(condition.value)}
              onChange={(e) =>
                update(
                  conditions.map((item, i) =>
                    i === index
                      ? {
                          ...item,
                          value:
                            e.target.value !== "" && !Number.isNaN(Number(e.target.value))
                              ? Number(e.target.value)
                              : e.target.value,
                        }
                      : item,
                  ),
                )
              }
            />
          )}
          <button type="button" onClick={() => update(conditions.filter((_, i) => i !== index))}>
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => update([...conditions, { column: "", op: "eq", value: "" }])}
      >
        添加条件
      </button>
    </div>
  );
}

function ColumnListEditor({
  node,
  onChange,
  paramKey,
  nameKey,
  extraColumns = [],
  options,
}: {
  node: WorkflowNode;
  onChange: (p: EditorParams) => void;
  paramKey: string;
  nameKey: string;
  extraColumns?: { key: string; placeholder: string; options?: string[] }[];
  options?: string[];
}) {
  const rows = Array.isArray(node.params[paramKey]) ? (node.params[paramKey] as EditorRow[]) : [];
  return (
    <RowList
      rows={rows}
      columns={[{ key: nameKey, placeholder: "列", options }, ...extraColumns]}
      onCreate={() => onChange({ ...node.params, [paramKey]: [...rows, {}] })}
      onUpdate={(index, patch) => {
        const next = [...rows];
        next[index] = { ...next[index], ...patch };
        onChange({ ...node.params, [paramKey]: next });
      }}
      onRemove={(index) =>
        onChange({ ...node.params, [paramKey]: rows.filter((_, i) => i !== index) })
      }
    />
  );
}

export function ProjectEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  return (
    <ColumnListEditor
      node={node}
      onChange={onChange}
      paramKey="columns"
      nameKey="name"
      options={shape.map((column) => column.name)}
      extraColumns={[{ key: "as", placeholder: "新列名（可选）" }]}
    />
  );
}

export function SortEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  return (
    <ColumnListEditor
      node={node}
      onChange={onChange}
      paramKey="keys"
      nameKey="column"
      options={shape.map((column) => column.name)}
      extraColumns={[
        { key: "direction", placeholder: "asc / desc", options: ["asc", "desc"] },
      ]}
    />
  );
}

export function AggregateEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const names = shape.map((column) => column.name);
  const groupBy = Array.isArray(node.params.group_by) ? (node.params.group_by as string[]) : [];
  const aggregates = Array.isArray(node.params.aggregates) ? (node.params.aggregates as EditorRow[]) : [];
  const toggleGroup = (name: string) => {
    onChange({
      ...node.params,
      group_by: groupBy.includes(name)
        ? groupBy.filter((item) => item !== name)
        : [...groupBy, name],
    });
  };
  return (
    <div className="analysis-editor">
      <details>
        <summary>分组列（已选 {groupBy.length}）</summary>
        <ul>
          {names.map((name) => (
            <li key={name}>
              <label>
                <input
                  type="checkbox"
                  checked={groupBy.includes(name)}
                  onChange={() => toggleGroup(name)}
                />
                <span>{name}</span>
              </label>
            </li>
          ))}
        </ul>
      </details>
      <RowList
        rows={aggregates}
        columns={[
          { key: "fn", placeholder: "聚合函数", options: [...AGGREGATE_FUNCTIONS] },
          { key: "column", placeholder: "列", options: names },
          { key: "as", placeholder: "别名（可选）" },
        ]}
        onCreate={() => onChange({ ...node.params, aggregates: [...aggregates, { fn: "sum", column: "" }] })}
        onUpdate={(index, patch) => {
          const next = [...aggregates];
          next[index] = { ...next[index], ...patch };
          onChange({ ...node.params, aggregates: next });
        }}
        onRemove={(index) =>
          onChange({ ...node.params, aggregates: aggregates.filter((_, i) => i !== index) })
        }
      />
    </div>
  );
}

export function LimitEditor({ node, onChange }: EditorProps) {
  return (
    <div className="analysis-editor">
      <input
        type="number"
        min={1}
        value={node.params.count === undefined ? "" : String(node.params.count)}
        onChange={(e) =>
          onChange({ ...node.params, count: e.target.value === "" ? undefined : Number(e.target.value) })
        }
      />
    </div>
  );
}

export function JoinEditor({ node, onChange }: EditorProps) {
  const leftShape = inputShapeFor(node.id, "left");
  const rightShape = inputShapeFor(node.id, "right");
  return (
    <div className="analysis-editor">
      <label className="analysis-field">
        <span>模式</span>
        <select
          value={node.params.mode === "left" ? "left" : "inner"}
          onChange={(e) => onChange({ ...node.params, mode: e.target.value })}
        >
          <option value="inner">inner</option>
          <option value="left">left</option>
        </select>
      </label>
      <label className="analysis-field">
        <span>左表键</span>
        <select
          value={asString(node.params.left_key) ?? ""}
          onChange={(e) => onChange({ ...node.params, left_key: e.target.value })}
        >
          <option value="">列…</option>
          {leftShape.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </select>
      </label>
      <label className="analysis-field">
        <span>右表键</span>
        <select
          value={asString(node.params.right_key) ?? ""}
          onChange={(e) => onChange({ ...node.params, right_key: e.target.value })}
        >
          <option value="">列…</option>
          {rightShape.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

export function ComputeEditor({ node, onChange }: EditorProps) {
  const extracts = Array.isArray(node.params.columns) ? (node.params.columns as EditorRow[]) : [];
  return (
    <div className="analysis-editor">
      <div className="analysis-field">
        <span>计算列（数值四则，如 total_damage / (frames_run / 60)）</span>
      </div>
      <textarea
        rows={3}
        value={JSON.stringify(extracts)}
        onChange={(e) => {
          try {
            const parsed = JSON.parse(e.target.value);
            if (Array.isArray(parsed)) {
              onChange({ ...node.params, columns: parsed });
            }
          } catch {
            // 非法 JSON 时保留原值，待输入合法后覆盖。
          }
        }}
      />
    </div>
  );
}

type RoleConfig =
  | { role: string; required: boolean; list?: false }
  | { role: string; required: boolean; list: true };

const ROLE_CONFIGS: Record<string, RoleConfig[]> = {
  table_config: [
    { role: "condition_columns", required: false, list: true },
    { role: "data_columns", required: false, list: true },
  ],
  timeline_config: [
    { role: "track", required: true },
    { role: "start", required: true },
    { role: "end", required: false },
    { role: "value", required: false },
    { role: "label", required: false },
  ],
  pie_config: [
    { role: "group", required: true },
    { role: "value", required: true },
    { role: "label", required: false },
  ],
  bar_config: [
    { role: "x", required: true },
    { role: "y", required: true },
    { role: "series", required: false },
  ],
};

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function moveBinding(columns: string[], index: number, delta: -1 | 1): string[] {
  const target = index + delta;
  if (target < 0 || target >= columns.length) {
    return columns;
  }
  const next = [...columns];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

function BindingList({
  title,
  hint,
  columns,
  available,
  taken,
  onChange,
}: {
  title: string;
  hint: string;
  columns: string[];
  available: string[];
  taken: Set<string>;
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="table-binding-zone">
      <div className="table-binding-title">
        <span>{title}</span>
        <span className="table-binding-hint">{hint}</span>
      </div>
      {columns.length === 0 ? (
        <p className="table-binding-empty">未选择列</p>
      ) : (
        <ul className="table-binding-list">
          {columns.map((column, index) => (
            <li key={`${column}-${index}`} className="table-binding-row">
              <select
                aria-label={`${title}第 ${index + 1} 行`}
                value={column}
                onChange={(event) =>
                  onChange(columns.map((item, i) => (i === index ? event.target.value : item)))
                }
              >
                <option value="">列…</option>
                {available
                  .filter((name) => !taken.has(name) || name === column)
                  .map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="icon-button"
                title="上移"
                aria-label={`上移 ${column}`}
                disabled={index === 0}
                onClick={() => onChange(moveBinding(columns, index, -1))}
              >
                ↑
              </button>
              <button
                type="button"
                className="icon-button"
                title="下移"
                aria-label={`下移 ${column}`}
                disabled={index === columns.length - 1}
                onClick={() => onChange(moveBinding(columns, index, 1))}
              >
                ↓
              </button>
              <button
                type="button"
                className="icon-button danger"
                title="移除"
                aria-label={`移除 ${column}`}
                onClick={() => onChange(columns.filter((_, i) => i !== index))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <select
        className="table-binding-add"
        aria-label={`添加${title}`}
        value=""
        onChange={(event) => {
          if (event.target.value !== "") {
            onChange([...columns, event.target.value]);
          }
        }}
      >
        <option value="">＋ 添加{title}</option>
        {available
          .filter((name) => !taken.has(name))
          .map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
      </select>
    </div>
  );
}

/** 表格配置编辑器：条件列 / 数据列两个分区列表（契约：绑定归属配置节点）。 */
export function TableConfigEditor({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const view = configTargetView(env.definition, node.id);
  const shape = view === null ? [] : viewInputShape(env.shapes, env.definition, view.id);
  const available = shape.map((column) => column.name);
  const condition = asStringArray(node.params.condition_columns);
  const data = asStringArray(node.params.data_columns);
  const taken = new Set([...condition, ...data]);
  return (
    <div className="analysis-editor table-config-editor">
      {available.length === 0 && (
        <p className="analysis-editor-empty">连接视图并接通数据源后，这里会出现可绑定的列。</p>
      )}
      <BindingList
        title="条件列"
        hint="说明这一行是什么配置"
        columns={condition}
        available={available}
        taken={taken}
        onChange={(next) => onChange({ ...node.params, condition_columns: next })}
      />
      <BindingList
        title="数据列"
        hint="要分析的指标"
        columns={data}
        available={available}
        taken={taken}
        onChange={(next) => onChange({ ...node.params, data_columns: next })}
      />
    </div>
  );
}

export function DisplayConfigEditor({ node, onChange }: EditorProps) {
  const roles = ROLE_CONFIGS[node.kind] ?? [];
  return (
    <div className="analysis-editor">
      {roles.map((config) => (
        <label key={config.role} className="analysis-field">
          <span>
            {config.role}
            {config.required ? "（必选）" : ""}
          </span>
          {config.list ? (
            <input
              value={
                Array.isArray(node.params[config.role])
                  ? (node.params[config.role] as unknown[]).join(",")
                  : ""
              }
              placeholder="列名，逗号分隔"
              onChange={(event) =>
                onChange({
                  ...node.params,
                  [config.role]: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter((item) => item !== ""),
                })
              }
            />
          ) : (
            <input
              value={asString(node.params[config.role]) ?? ""}
              onChange={(event) =>
                onChange({ ...node.params, [config.role]: event.target.value })
              }
            />
          )}
        </label>
      ))}
    </div>
  );
}
