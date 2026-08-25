/** 分析区域节点编辑器（取数、关系算子、展示配置、数据提供）。 */

import { useEffect, useState } from "react";

import { listResults } from "../../api/client";
import type { RunListItem } from "../../api/client";
import type { AnalysisSchemaCatalog, FilterCondition, TableShape } from "../../workflow/templates";
import { AGGREGATE_FUNCTIONS, CONDITION_OPERATORS } from "../../workflow/templates";
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

export function DataProviderEditor({ node, onChange }: EditorProps) {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  useEffect(() => {
    let alive = true;
    listResults({ limit: 50 })
      .then((response) => {
        if (alive) {
          setRuns(response.items);
        }
      })
      .catch(() => {
        // 结果库读取失败时编辑器保持空列表，节点仍可保存会话选择。
      });
    return () => {
      alive = false;
    };
  }, []);
  const selected = Array.isArray(node.params.session_ids)
    ? (node.params.session_ids as unknown[]).filter(
        (item): item is string => typeof item === "string",
      )
    : [];

  const toggle = (sessionId: string) => {
    const next = selected.includes(sessionId)
      ? selected.filter((item) => item !== sessionId)
      : [...selected, sessionId];
    onChange({ ...node.params, session_ids: next });
  };

  return (
    <div className="analysis-editor">
      <div className="analysis-editor-summary">已选 {selected.length} 场</div>
      {runs.length === 0 ? (
        <div className="analysis-editor-empty">没有可用的历史运行</div>
      ) : (
        <ul className="analysis-run-list">
          {runs.map((run) => (
            <li key={run.session_id}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(run.session_id)}
                  onChange={() => toggle(run.session_id)}
                />
                <span>{run.name}</span>
                <span className="analysis-run-state">{run.state}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
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

export function FetchRunsEditor({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const columns = env.catalog?.runsColumns() ?? [];
  return (
    <div className="analysis-editor">
      <div className="analysis-field">
        <span>快照提取列</span>
      </div>
      <RowList
        rows={Array.isArray(node.params.snapshot_columns) ? (node.params.snapshot_columns as EditorRow[]) : []}
        columns={[
          { key: "path", placeholder: "快照路径，如 team[0].character.asset_key" },
          { key: "name", placeholder: "列名" },
          { key: "type", placeholder: "类型 string/int/float/bool" },
        ]}
        onCreate={() => onChange({ ...node.params, snapshot_columns: [...(Array.isArray(node.params.snapshot_columns) ? node.params.snapshot_columns : []), { path: "", name: "", type: "string" }] })}
        onUpdate={(index, patch) => {
          const next = [...(Array.isArray(node.params.snapshot_columns) ? (node.params.snapshot_columns as EditorRow[]) : [])];
          next[index] = { ...next[index], ...patch };
          onChange({ ...node.params, snapshot_columns: next });
        }}
        onRemove={(index) => {
          const next = (Array.isArray(node.params.snapshot_columns) ? (node.params.snapshot_columns as EditorRow[]) : []).filter((_, i) => i !== index);
          onChange({ ...node.params, snapshot_columns: next });
        }}
      />
      <details>
        <summary>可用字段</summary>
        <ul>
          {columns.map((column) => (
            <li key={column.name}>
              {column.name}（{column.type}）{column.description ? "：" + column.description : ""}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

export function FetchEventsEditor({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const eventTypes = env.catalog?.eventTypes() ?? [];
  const selected = Array.isArray(node.params.event_types) ? (node.params.event_types as string[]) : [];
  const extracts = Array.isArray(node.params.payload_columns) ? (node.params.payload_columns as EditorRow[]) : [];
  const toggleType = (name: string) => {
    const next = selected.includes(name) ? selected.filter((t) => t !== name) : [...selected, name];
    onChange({ ...node.params, event_types: next });
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
      <RowList
        rows={extracts}
        columns={[
          { key: "path", placeholder: "载荷路径，如 result.final_damage" },
          { key: "name", placeholder: "列名" },
          { key: "type", placeholder: "类型 string/int/float/bool" },
        ]}
        onCreate={() => onChange({ ...node.params, payload_columns: [...extracts, { path: "", name: "", type: "float" }] })}
        onUpdate={(index, patch) => {
          const next = [...extracts];
          next[index] = { ...next[index], ...patch };
          onChange({ ...node.params, payload_columns: next });
        }}
        onRemove={(index) =>
          onChange({ ...node.params, payload_columns: extracts.filter((_, i) => i !== index) })
        }
      />
    </div>
  );
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
