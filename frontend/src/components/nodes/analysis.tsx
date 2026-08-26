/** 分析区域节点编辑器（取数、关系算子、展示配置、数据提供）。 */

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type {
  AnalysisSchemaCatalog,
  AnalysisSchemaNode,
  FilterCondition,
  SnapshotLeaf,
  TableShape,
} from "../../workflow/templates";
import {
  AGGREGATE_FUNCTIONS,
  CONDITION_OPERATORS,
  snapshotLeaves,
} from "../../workflow/templates";
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

/** 输出列类型选项（与后端类型词表一致）。 */
const EXTRACT_TYPES = ["string", "int", "float", "bool"] as const;
const COLUMN_NAME_PATTERN = /^[A-Za-z0-9_]{1,64}$/;

const QUICK_SNAPSHOT_PATHS = [
  "team.0.character.asset_key",
  "team.0.character.level",
  "team.0.weapon.refinement",
  "scene.targets.0.level",
] as const;

const QUICK_EVENT_FIELDS: { event_type: string; path: string; label: string }[] = [
  { event_type: "DAMAGE_RESOLVED", path: "result.final_damage", label: "伤害值" },
  {
    event_type: "DAMAGE_RESOLVED",
    path: "result.source_ref.entity_id",
    label: "伤害来源",
  },
  { event_type: "HEALING_RESOLVED", path: "result.final_healing", label: "治疗值" },
  {
    event_type: "HEALING_RESOLVED",
    path: "result.source_ref.entity_id",
    label: "治疗来源",
  },
];

interface FetchDraft {
  source: "runs" | "events";
  event_types: string[];
  snapshot_columns: EditorRow[];
  payload_columns: EditorRow[];
}

function cloneDraft(params: Record<string, unknown>): FetchDraft {
  return {
    source: params.source === "events" ? "events" : "runs",
    event_types: Array.isArray(params.event_types)
      ? [...(params.event_types as string[])]
      : [],
    snapshot_columns: Array.isArray(params.snapshot_columns)
      ? (params.snapshot_columns as EditorRow[]).map((row) => ({ ...row }))
      : [],
    payload_columns: Array.isArray(params.payload_columns)
      ? (params.payload_columns as EditorRow[]).map((row) => ({ ...row }))
      : [],
  };
}

function hasRunParams(params: { snapshot_columns?: unknown }): boolean {
  return Array.isArray(params.snapshot_columns) && params.snapshot_columns.length > 0;
}

function hasEventParams(params: {
  event_types?: unknown;
  payload_columns?: unknown;
}): boolean {
  return (
    (Array.isArray(params.event_types) && params.event_types.length > 0) ||
    (Array.isArray(params.payload_columns) && params.payload_columns.length > 0)
  );
}

function draftErrors(draft: FetchDraft): string[] {
  const errors: string[] = [];
  const rows = draft.source === "runs" ? draft.snapshot_columns : draft.payload_columns;
  const seen = new Set<string>();
  rows.forEach((row, index) => {
    const name = row.name;
    if (typeof name !== "string" || !COLUMN_NAME_PATTERN.test(name)) {
      errors.push(`第 ${index + 1} 个输出列名不合法（字母/数字/下划线，≤64 位）`);
    } else if (seen.has(name)) {
      errors.push(`输出列名重复：${name}`);
    } else {
      seen.add(name);
    }
    if (
      draft.source === "events" &&
      (typeof row.event_type !== "string" || row.event_type === "")
    ) {
      errors.push(`第 ${index + 1} 个输出列缺少事件类型`);
    }
  });
  return errors;
}

/** 获取数据节点：卡内摘要 + 大弹层配置器（2026-08-26 重构）。 */
export function FetchEditor({ node, onChange }: EditorProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="analysis-editor">
      <FetchSummary node={node} onEdit={() => setOpen(true)} />
      {open && (
        <FetchConfigModal
          node={node}
          onClose={() => setOpen(false)}
          onCommit={(params) => {
            onChange(params);
            setOpen(false);
          }}
        />
      )}
    </div>
  );
}

/** 节点卡摘要：数据范围 + 输出列，编辑进入大弹层。 */
function FetchSummary({ node, onEdit }: { node: WorkflowNode; onEdit: () => void }) {
  const env = useContextEnv();
  const source = node.params.source === "events" ? "events" : "runs";
  const eventTypes = Array.isArray(node.params.event_types)
    ? (node.params.event_types as string[])
    : [];
  const columns =
    source === "runs"
      ? (Array.isArray(node.params.snapshot_columns)
          ? (node.params.snapshot_columns as EditorRow[])
          : [])
      : (Array.isArray(node.params.payload_columns)
          ? (node.params.payload_columns as EditorRow[])
          : []);
  const runLeaves = snapshotLeaves(env.catalog?.snapshotTree() ?? null);
  const sourceOf = (column: EditorRow): string => {
    if (source === "runs") {
      const path = asString(column.path) ?? "";
      const leaf = runLeaves.find((item) => matchesTemplate(path, item.pathTemplate));
      return leaf === undefined
        ? pathLabel(column.path)
        : describeLeaf(leaf, path);
    }
    const typeName = asString(column.event_type) ?? "";
    const field = env.catalog
      ?.eventTypes()
      .find((item) => item.name === typeName)
      ?.fields.find((item) => item.path === column.path);
    const label =
      field !== undefined && field.description !== ""
        ? field.description
        : pathLabel(column.path);
    return `${typeName}·${label}`;
  };
  return (
    <div className="fetch-summary">
      <div className="fetch-summary-head">
        <span className="fetch-source-badge">
          {source === "runs" ? "运行记录" : "事件记录"}
        </span>
        <button type="button" className="fetch-edit-button" onClick={onEdit}>
          编辑数据…
        </button>
      </div>
      <div className="fetch-summary-line">
        {source === "runs"
          ? `输入条件列 ${columns.length} 列`
          : `事件范围 ${eventTypes.length === 0 ? "全部" : `${eventTypes.length} 类`}`}
      </div>
      {columns.length === 0 ? (
        <p className="fetch-summary-empty">未添加输出列</p>
      ) : (
        <table className="fetch-summary-table">
          <thead>
            <tr>
              <th>列名</th>
              <th>类型</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column, index) => (
              <tr key={`${column.name ?? ""}-${index}`}>
                <td>{asString(column.name) ?? ""}</td>
                <td>{asString(column.type) ?? ""}</td>
                <td title={asString(column.path) ?? ""}>{sourceOf(column)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** 大弹层配置器：数据范围 + 输出列（目录勾选）。 */
function FetchConfigModal({
  node,
  onClose,
  onCommit,
}: {
  node: WorkflowNode;
  onClose: () => void;
  onCommit: (params: Record<string, unknown>) => void;
}) {
  const env = useContextEnv();
  const eventTypes = env.catalog?.eventTypes() ?? [];
  const snapshotTree = env.catalog?.snapshotTree() ?? null;
  const [draft, setDraft] = useState<FetchDraft>(() => cloneDraft(node.params));
  const [pendingSwitch, setPendingSwitch] = useState<"runs" | "events" | null>(null);
  const update = (patch: Partial<FetchDraft>) =>
    setDraft((current) => ({ ...current, ...patch }));

  const switchSource = (next: "runs" | "events") => {
    if (next === draft.source) {
      setPendingSwitch(null);
      return;
    }
    const currentHasParams =
      draft.source === "runs" ? hasRunParams(draft) : hasEventParams(draft);
    if (currentHasParams && pendingSwitch !== next) {
      setPendingSwitch(next);
      return;
    }
    setPendingSwitch(null);
    setDraft((current) =>
      next === "runs"
        ? {
            source: "runs",
            event_types: [],
            payload_columns: [],
            snapshot_columns: current.snapshot_columns,
          }
        : {
            source: "events",
            snapshot_columns: [],
            event_types: current.event_types,
            payload_columns: current.payload_columns,
          },
    );
  };

  const commit = () => {
    if (draft.source === "runs") {
      onCommit({ source: "runs", snapshot_columns: draft.snapshot_columns });
    } else {
      onCommit({
        source: "events",
        event_types: draft.event_types,
        payload_columns: draft.payload_columns,
      });
    }
  };

  const errors = draftErrors(draft);

  return createPortal(
    <>
      <div className="data-provider-backdrop" onMouseDown={onClose} />
      <section
        className="fetch-config-modal"
        role="dialog"
        aria-modal="true"
        aria-label="配置获取数据"
      >
        <header className="fetch-modal-header">
          <span>配置获取数据</span>
          <button type="button" className="icon-button" title="关闭" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="fetch-modal-body">
          <section className="fetch-modal-section">
            <h3>数据范围</h3>
            <div className="fetch-source-switch">
              <button
                type="button"
                className={draft.source === "runs" ? "active" : ""}
                onClick={() => switchSource("runs")}
              >
                {pendingSwitch === "runs" ? "确认切换？" : "运行记录"}
              </button>
              <button
                type="button"
                className={draft.source === "events" ? "active" : ""}
                onClick={() => switchSource("events")}
              >
                {pendingSwitch === "events" ? "确认切换？" : "事件记录"}
              </button>
            </div>
            {pendingSwitch !== null && (
              <p className="fetch-switch-hint">切换来源将清空当前来源的参数，再次点击确认。</p>
            )}
          </section>
          <section className="fetch-modal-section">
            <h3>输出列</h3>
            {draft.source === "runs" ? (
              <SnapshotColumnCatalog
                tree={snapshotTree}
                columns={draft.snapshot_columns}
                onChange={(columns) => update({ snapshot_columns: columns })}
              />
            ) : (
              <EventColumnCatalog
                eventTypes={eventTypes}
                selectedTypes={draft.event_types}
                columns={draft.payload_columns}
                onChangeTypes={(eventTypes) => update({ event_types: eventTypes })}
                onChangeColumns={(columns) => update({ payload_columns: columns })}
              />
            )}
          </section>
          {errors.length > 0 && (
            <div className="fetch-modal-errors">
              {errors.map((message) => (
                <p key={message} className="fetch-inline-error">
                  {message}
                </p>
              ))}
            </div>
          )}
        </div>
        <footer className="fetch-modal-footer">
          <button type="button" className="text-button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="fetch-popover-primary" onClick={commit}>
            完成
          </button>
        </footer>
      </section>
    </>,
    document.body,
  );
}

/** 运行记录：输入条件结构树勾选（列表位置由用户输入）。 */
function SnapshotColumnCatalog({
  tree,
  columns,
  onChange,
}: {
  tree: AnalysisSchemaNode | null;
  columns: EditorRow[];
  onChange: (next: EditorRow[]) => void;
}) {
  const leaves = useMemo(() => snapshotLeaves(tree), [tree]);
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const visibleLeaves = leaves.filter((leaf) =>
    leaf.labels.join(" ").toLowerCase().includes(query),
  );
  const [pending, setPending] = useState<{ leaf: SnapshotLeaf; values: number[] } | null>(
    null,
  );
  const updateName = (index: number, name: string) =>
    onChange(columns.map((row, i) => (i === index ? { ...row, name } : row)));
  const quickEntries = QUICK_SNAPSHOT_PATHS.flatMap((path) => {
    const template = toPathTemplate(path);
    const leaf = leaves.find((item) => item.pathTemplate === template);
    return leaf === undefined ? [] : [leaf];
  });
  const addLeaf = (leaf: SnapshotLeaf, values: number[]) => {
    if (columns.some((row) => matchesTemplate(asString(row.path) ?? "", leaf.pathTemplate))) {
      return;
    }
    onChange([
      ...columns,
      {
        path: resolvePath(leaf.pathTemplate, values),
        name: resolveName(leaf.defaultNameTemplate, values),
        type: leaf.type,
      },
    ]);
  };
  const removeTemplate = (leaf: SnapshotLeaf) =>
    onChange(
      columns.filter(
        (row) => !matchesTemplate(asString(row.path) ?? "", leaf.pathTemplate),
      ),
    );

  return (
    <div className="fetch-catalog">
      <div className="fetch-catalog-left">
        <input
          className="field"
          placeholder="搜索输入条件…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {tree === null ? (
          <p className="analysis-editor-empty">结构目录不可用（schema 未加载）</p>
        ) : search.trim() !== "" ? (
          <ul className="fetch-catalog-list">
            {visibleLeaves.map((leaf) => (
              <SnapshotLeafRow
                key={leaf.pathTemplate}
                leaf={leaf}
                columns={columns}
                pending={pending}
                onPending={setPending}
                onAdd={addLeaf}
                onRemove={removeTemplate}
              />
            ))}
            {visibleLeaves.length === 0 && (
              <li className="analysis-editor-empty">无匹配输入条件</li>
            )}
          </ul>
        ) : (
          <ul className="fetch-catalog-list">
            <SnapshotTreeNode
              node={tree}
              context={{ segments: [], labels: [], listLabels: [], isRoot: true }}
              columns={columns}
              pending={pending}
              onPending={setPending}
              onAdd={addLeaf}
              onRemove={removeTemplate}
            />
          </ul>
        )}
      </div>
      <div className="fetch-catalog-right">
        <div className="fetch-catalog-right-title">
          <span>已选输出列</span>
          {quickEntries.length > 0 && (
            <span className="fetch-quick-row">
              <span className="fetch-quick-label">常用</span>
              {quickEntries.map((entry) => (
                <button
                  key={entry.pathTemplate}
                  type="button"
                  className="fetch-quick-button"
                  onClick={() => addLeaf(entry, entry.listLabels.map(() => 1))}
                >
                  {quickSnapshotLabel(entry)}
                </button>
              ))}
            </span>
          )}
        </div>
        {columns.length === 0 && <p className="analysis-editor-empty">未选择输出列</p>}
        {columns.map((row, index) => (
          <div key={`${row.path ?? ""}-${index}`} className="fetch-selected-row">
            <span className="fetch-selected-source" title={asString(row.path) ?? ""}>
              {describeSelectedSource(leaves, row)}
            </span>
            <input
              aria-label={`输入条件列名 ${index + 1}`}
              value={asString(row.name) ?? ""}
              onChange={(event) => updateName(index, event.target.value)}
            />
            <span className="snapshot-type">{asString(row.type) ?? ""}</span>
            <button
              type="button"
              className="icon-button danger"
              aria-label={`移除输出列 ${index + 1}`}
              onClick={() => onChange(columns.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
        ))}
        <ManualColumnAdder
          key="runs-manual"
          onAdd={(row) => onChange([...columns, row])}
        />
      </div>
    </div>
  );
}

/** 树节点递归渲染：列表节点只出现一次，叶子勾选时输入位置。 */
function SnapshotTreeNode({
  node,
  context,
  columns,
  pending,
  onPending,
  onAdd,
  onRemove,
}: {
  node: AnalysisSchemaNode;
  context: {
    segments: string[];
    labels: string[];
    listLabels: string[];
    isRoot: boolean;
  };
  columns: EditorRow[];
  pending: { leaf: SnapshotLeaf; values: number[] } | null;
  onPending: (pending: { leaf: SnapshotLeaf; values: number[] } | null) => void;
  onAdd: (leaf: SnapshotLeaf, values: number[]) => void;
  onRemove: (leaf: SnapshotLeaf) => void;
}) {
  if (node.kind === "scalar") {
    const leaf: SnapshotLeaf = {
      pathTemplate:
        context.isRoot
          ? node.key
          : [...context.segments, node.key].join("."),
      labels: [...context.labels, node.label],
      listLabels: context.listLabels,
      defaultNameTemplate: node.default_name_template ?? node.default_name ?? null,
      type: node.type ?? "",
      description: node.description ?? "",
    };
    return (
      <SnapshotLeafRow
        leaf={leaf}
        columns={columns}
        pending={pending}
        onPending={onPending}
        onAdd={onAdd}
        onRemove={onRemove}
      />
    );
  }
  const nextContext = {
    segments:
      context.isRoot
        ? context.segments
        : node.kind === "list"
        ? [...context.segments, `${node.key}.{${context.listLabels.length}}`]
        : [...context.segments, node.key],
    labels: [...context.labels, node.label],
    listLabels:
      node.kind === "list" ? [...context.listLabels, node.label] : context.listLabels,
    isRoot: false,
  };
  return (
    <li className="fetch-tree-folder">
      <span className="fetch-tree-folder-label">
        {node.label}
        {node.kind === "list" ? "[]" : ""}
      </span>
      <ul className="fetch-tree-children">
        {(node.children ?? []).map((child) => (
          <SnapshotTreeNode
            key={child.key}
            node={child}
            context={nextContext}
            columns={columns}
            pending={pending}
            onPending={onPending}
            onAdd={onAdd}
            onRemove={onRemove}
          />
        ))}
      </ul>
    </li>
  );
}

/** 结构树叶子行：普通叶子直接勾选，列表叶子勾选后输入位置。 */
function SnapshotLeafRow({
  leaf,
  columns,
  pending,
  onPending,
  onAdd,
  onRemove,
}: {
  leaf: SnapshotLeaf;
  columns: EditorRow[];
  pending: { leaf: SnapshotLeaf; values: number[] } | null;
  onPending: (pending: { leaf: SnapshotLeaf; values: number[] } | null) => void;
  onAdd: (leaf: SnapshotLeaf, values: number[]) => void;
  onRemove: (leaf: SnapshotLeaf) => void;
}) {
  const selected = columns.some((row) =>
    matchesTemplate(asString(row.path) ?? "", leaf.pathTemplate),
  );
  const pendingOpen = pending?.leaf.pathTemplate === leaf.pathTemplate;
  const listCount = leaf.listLabels.length;
  return (
    <li className="fetch-tree-leaf">
      <label title={leaf.pathTemplate}>
        <input
          type="checkbox"
          checked={selected || pendingOpen}
          onChange={() => {
            if (selected) {
              onRemove(leaf);
              return;
            }
            if (listCount === 0) {
              onAdd(leaf, []);
              return;
            }
            onPending({ leaf, values: leaf.listLabels.map(() => 1) });
          }}
        />
        <span className="fetch-catalog-label">{leaf.labels[leaf.labels.length - 1]}</span>
        <em className="fetch-catalog-default">{leaf.type}</em>
      </label>
      {pendingOpen && listCount > 0 && (
        <div className="fetch-index-panel">
          {leaf.listLabels.map((label, index) => (
            <label key={`${label}-${index}`} className="fetch-index-field">
              {label} 第
              <input
                type="number"
                min={1}
                value={pending?.values[index] ?? 1}
                onChange={(event) => {
                  const next = [...(pending?.values ?? [])];
                  next[index] = Math.max(1, Number(event.target.value) || 1);
                  onPending({ leaf, values: next });
                }}
              />
              个
            </label>
          ))}
          <button
            type="button"
            className="fetch-quick-button"
            onClick={() => onAdd(leaf, pending?.values ?? [])}
          >
            添加
          </button>
          <button type="button" className="text-button" onClick={() => onPending(null)}>
            取消
          </button>
        </div>
      )}
    </li>
  );
}

/** 事件记录：事件类型 + 字段目录勾选。 */
function EventColumnCatalog({
  eventTypes,
  selectedTypes,
  columns,
  onChangeTypes,
  onChangeColumns,
}: {
  eventTypes: { name: string; fields: { path: string; type: string; description: string }[] }[];
  selectedTypes: string[];
  columns: EditorRow[];
  onChangeTypes: (next: string[]) => void;
  onChangeColumns: (next: EditorRow[]) => void;
}) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const visible = eventTypes.filter((item) => item.name.toLowerCase().includes(query));
  const toggleType = (name: string) =>
    onChangeTypes(
      selectedTypes.includes(name)
        ? selectedTypes.filter((item) => item !== name)
        : [...selectedTypes, name],
    );
  const hasColumn = (type: string, path: string) =>
    columns.some((row) => row.event_type === type && row.path === path);
  const toggleField = (type: { name: string }, field: { path: string; type: string }) => {
    if (hasColumn(type.name, field.path)) {
      onChangeColumns(
        columns.filter(
          (row) => !(row.event_type === type.name && row.path === field.path),
        ),
      );
    } else {
      onChangeColumns([
        ...columns,
        {
          event_type: type.name,
          path: field.path,
          name: defaultFieldName(field.path),
          type: field.type,
        },
      ]);
      if (!selectedTypes.includes(type.name)) {
        onChangeTypes([...selectedTypes, type.name]);
      }
    }
  };
  const updateName = (index: number, name: string) =>
    onChangeColumns(columns.map((row, i) => (i === index ? { ...row, name } : row)));
  const quickEntries = QUICK_EVENT_FIELDS.filter((quick) =>
    eventTypes.some(
      (item) =>
        item.name === quick.event_type &&
        item.fields.some((field) => field.path === quick.path),
    ),
  );

  return (
    <div className="fetch-catalog">
      <div className="fetch-catalog-left">
        <div className="fetch-scope-status">
          事件范围：
          {selectedTypes.length === 0 ? "全部（未筛选）" : `已选 ${selectedTypes.length} 类`}
        </div>
        <input
          className="field"
          placeholder="搜索事件类型…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <ul className="fetch-catalog-list">
          {visible.map((type) => (
            <li key={type.name} className="fetch-event-type-item">
              <label>
                <input
                  type="checkbox"
                  checked={selectedTypes.includes(type.name)}
                  onChange={() => toggleType(type.name)}
                />
                <span>{type.name}</span>
              </label>
              <ul className="fetch-field-list">
                {type.fields.map((field) => (
                  <li key={field.path}>
                    <label title={field.path}>
                      <input
                        type="checkbox"
                        checked={hasColumn(type.name, field.path)}
                        onChange={() => toggleField(type, field)}
                      />
                      <span className="fetch-field-label">
                        {field.description !== "" ? field.description : field.path}
                      </span>
                      <em>{field.type}</em>
                    </label>
                  </li>
                ))}
                {type.fields.length === 0 && (
                  <li className="analysis-editor-empty">暂无可选字段</li>
                )}
              </ul>
            </li>
          ))}
          {visible.length === 0 && <li className="analysis-editor-empty">无匹配事件类型</li>}
        </ul>
      </div>
      <div className="fetch-catalog-right">
        <div className="fetch-catalog-right-title">
          <span>已选输出列</span>
          {quickEntries.length > 0 && (
            <span className="fetch-quick-row">
              <span className="fetch-quick-label">常用</span>
              {quickEntries.map((quick) => (
                <button
                  key={`${quick.event_type}:${quick.path}`}
                  type="button"
                  className="fetch-quick-button"
                  onClick={() => {
                    const type = eventTypes.find((item) => item.name === quick.event_type);
                    const field = type?.fields.find((item) => item.path === quick.path);
                    if (field !== undefined && !hasColumn(quick.event_type, quick.path)) {
                      onChangeColumns([
                        ...columns,
                        {
                          event_type: quick.event_type,
                          path: quick.path,
                          name: defaultFieldName(quick.path),
                          type: field.type,
                        },
                      ]);
                      if (!selectedTypes.includes(quick.event_type)) {
                        onChangeTypes([...selectedTypes, quick.event_type]);
                      }
                    }
                  }}
                >
                  {quick.label}
                </button>
              ))}
            </span>
          )}
        </div>
        {columns.length === 0 && <p className="analysis-editor-empty">未选择输出列</p>}
        {columns.map((row, index) => (
          <div key={`${row.event_type ?? ""}-${row.path ?? ""}-${index}`} className="fetch-selected-row">
            <span className="fetch-selected-source" title={asString(row.path) ?? ""}>
              {asString(row.event_type) ?? "?"}
            </span>
            <input
              aria-label={`事件数据列名 ${index + 1}`}
              value={asString(row.name) ?? ""}
              onChange={(event) => updateName(index, event.target.value)}
            />
            <span className="snapshot-type">{asString(row.type) ?? ""}</span>
            <button
              type="button"
              className="icon-button danger"
              aria-label={`移除输出列 ${index + 1}`}
              onClick={() => onChangeColumns(columns.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </div>
        ))}
        <ManualColumnAdder
          key="events-manual"
          eventTypes={eventTypes.map((item) => item.name)}
          onAdd={(row) => {
            onChangeColumns([...columns, row]);
            if (
              typeof row.event_type === "string" &&
              !selectedTypes.includes(row.event_type)
            ) {
              onChangeTypes([...selectedTypes, row.event_type]);
            }
          }}
        />
      </div>
    </div>
  );
}

/** 手动添加列：目录外的路径回退。 */
function ManualColumnAdder({
  eventTypes,
  onAdd,
}: {
  eventTypes?: string[];
  onAdd: (row: EditorRow) => void;
}) {
  const [open, setOpen] = useState(false);
  const [eventType, setEventType] = useState("");
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("string");
  const canAdd = path.trim() !== "" && name.trim() !== "" && (eventTypes === undefined || eventType !== "");
  const add = () => {
    if (!canAdd) {
      return;
    }
    onAdd({
      ...(eventTypes === undefined ? {} : { event_type: eventType }),
      path: path.trim(),
      name: name.trim(),
      type,
    });
    setPath("");
    setName("");
  };
  return (
    <div className="fetch-manual-adder">
      {open ? (
        <div className="fetch-manual-adder-form">
          {eventTypes !== undefined && (
            <select value={eventType} onChange={(event) => setEventType(event.target.value)}>
              <option value="">事件类型…</option>
              {eventTypes.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          )}
          <input
            placeholder="路径（目录外）"
            value={path}
            onChange={(event) => setPath(event.target.value)}
          />
          <input
            placeholder="列名"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <select value={type} onChange={(event) => setType(event.target.value)}>
            {EXTRACT_TYPES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="fetch-quick-button"
            disabled={!canAdd}
            onClick={add}
          >
            添加
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setOpen(false)}
          >
            取消
          </button>
        </div>
      ) : (
        <button type="button" className="snapshot-add" onClick={() => setOpen(true)}>
          ＋ 手动添加列
        </button>
      )}
    </div>
  );
}

function quickSnapshotLabel(leaf: SnapshotLeaf): string {
  const owner = leaf.listLabels[0] ?? leaf.labels[1] ?? "";
  const leafLabel = leaf.labels[leaf.labels.length - 1] ?? "";
  return `${owner}·${leafLabel}`;
}

/** 已选行来源展示：优先结构树标签链 + 位置，找不到回退路径叶子。 */
function describeSelectedSource(leaves: SnapshotLeaf[], row: EditorRow): string {
  const path = asString(row.path) ?? "";
  const leaf = leaves.find((item) => matchesTemplate(path, item.pathTemplate));
  return leaf === undefined ? pathLabel(row.path) : describeLeaf(leaf, path);
}

/** 路径模板匹配：{n} 占位符对应任意数字段。 */
function matchesTemplate(path: string, template: string): boolean {
  const pattern = template.replace(/\{\d+\}/g, "\\d+");
  return new RegExp(`^${pattern}$`).test(path);
}

/** 绝对路径（0 基）转路径模板：数字段按出现顺序变成 {0}/{1}... */
function toPathTemplate(path: string): string {
  let index = 0;
  return path.replace(/\.\d+(?=\.|$)/g, () => `.{${index++}}`);
}

/** 用位置值（显示 1 基）填充路径模板，路径存储 0 基。 */
function resolvePath(template: string, values: number[]): string {
  let index = 0;
  return template.replace(/\{\d+\}/g, () => String((values[index++] ?? 1) - 1));
}

/** 用位置值（显示 1 基）填充默认列名模板。 */
function resolveName(template: string | null, values: number[]): string {
  if (template === null) {
    return "";
  }
  let index = 0;
  return template.replace(/\{\d+\}/g, () => String(values[index++] ?? 1));
}

/** 从具体路径反推各列表位置（显示 1 基）。 */
function pathIndices(path: string, template: string): number[] {
  const source = template.replace(/\{\d+\}/g, "(\\d+)");
  const match = new RegExp(`^${source}$`).exec(path);
  return match === null ? [] : match.slice(1).map((value) => Number(value) + 1);
}

/** 叶子展示名：标签链 + 列表位置（如「队伍 第1个 / 角色 / 资产」）。 */
function describeLeaf(leaf: SnapshotLeaf, path: string): string {
  const indices = pathIndices(path, leaf.pathTemplate);
  const parts: string[] = [];
  let listPos = 0;
  for (let index = 1; index < leaf.labels.length; index++) {
    const label = leaf.labels[index];
    if (leaf.listLabels.includes(label)) {
      parts.push(`${label} 第${indices[listPos] ?? 1}个`);
      listPos += 1;
    } else {
      parts.push(label);
    }
  }
  return parts.join(" / ");
}

function pathLabel(path: unknown): string {
  const value = asString(path) ?? "";
  if (value === "") {
    return "手动路径";
  }
  const parts = value.split(".");
  return parts[parts.length - 1] ?? value;
}

function defaultFieldName(path: string): string {
  const leaf = path.split(".").pop() ?? "";
  return leaf === "" ? "value" : leaf;
}

const FILTER_OPERATOR_LABELS: Record<string, string> = {
  eq: "等于",
  ne: "不等于",
  gt: "大于",
  gte: "大于等于",
  lt: "小于",
  lte: "小于等于",
  in: "属于",
  not_in: "不属于",
  is_null: "为空",
  is_not_null: "不为空",
};

const OPERATORS_BY_TYPE: Record<string, string[]> = {
  string: ["eq", "ne", "in", "not_in", "is_null", "is_not_null"],
  bool: ["eq", "ne", "is_null", "is_not_null"],
  int: ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "is_not_null"],
  float: ["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "is_null", "is_not_null"],
};

const FILTER_NUMERIC_TYPES = new Set(["int", "float"]);

function operatorsForType(type: string, currentOp: string): string[] {
  const base = OPERATORS_BY_TYPE[type] ?? [...CONDITION_OPERATORS];
  return base.includes(currentOp) ? base : [...base, currentOp];
}

function filterValueMatchesType(type: string, value: unknown): boolean {
  if (type === "string") {
    return typeof value === "string";
  }
  if (type === "bool") {
    return typeof value === "boolean";
  }
  if (type === "int") {
    return typeof value === "number" && Number.isInteger(value);
  }
  if (type === "float") {
    return typeof value === "number" && Number.isFinite(value);
  }
  return true;
}

function formatFilterValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(formatFilterValue).join("、");
  }
  if (value === true) {
    return "真";
  }
  if (value === false) {
    return "假";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return value === null || value === undefined ? "" : String(value);
}

function filterConditionError(
  condition: FilterCondition,
  index: number,
  shape: TableShape[],
): string | null {
  const prefix = `第 ${index + 1} 个条件：`;
  if (typeof condition.column !== "string" || condition.column === "") {
    return `${prefix}请选择列`;
  }
  const type = shape.find((column) => column.name === condition.column)?.type ?? "";
  if (type === "") {
    return `${prefix}列不存在`;
  }
  if (typeof condition.op !== "string" || !CONDITION_OPERATORS.includes(condition.op as never)) {
    return `${prefix}请选择操作符`;
  }
  const op = condition.op;
  if (op === "gt" || op === "gte" || op === "lt" || op === "lte") {
    if (!FILTER_NUMERIC_TYPES.has(type)) {
      return `${prefix}该操作符不适用于${type === "string" ? "文本" : type}列`;
    }
  }
  if (op === "is_null" || op === "is_not_null") {
    return null;
  }
  if (op === "in" || op === "not_in") {
    if (!Array.isArray(condition.value) || condition.value.length === 0) {
      return `${prefix}请至少添加一个值`;
    }
    if (condition.value.some((item) => !filterValueMatchesType(type, item))) {
      return `${prefix}值的类型与列类型不一致`;
    }
    return null;
  }
  if (!filterValueMatchesType(type, condition.value)) {
    return type === "bool" ? `${prefix}请选择真或假` : `${prefix}请填写与列类型匹配的值`;
  }
  return null;
}

function toArrayValue(value: unknown, type: string): unknown[] {
  if (Array.isArray(value)) {
    return value.filter((item) => filterValueMatchesType(type, item));
  }
  return filterValueMatchesType(type, value) &&
    value !== undefined &&
    value !== null &&
    value !== ""
    ? [value]
    : [];
}

function toScalarValue(value: unknown, type: string): unknown {
  if (Array.isArray(value) && value.length === 1 && filterValueMatchesType(type, value[0])) {
    return value[0];
  }
  return filterValueMatchesType(type, value) ? value : undefined;
}

export function FilterEditor({ node, onChange }: EditorProps) {
  const shape = upstreamShape(node.id);
  const mode = node.params.mode === "any" ? "any" : "all";
  const conditions = Array.isArray(node.params.conditions)
    ? (node.params.conditions as FilterCondition[])
    : [];
  const updateCondition = (index: number, patch: Partial<FilterCondition>) => {
    onChange({
      ...node.params,
      conditions: conditions.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  };
  const replaceCondition = (index: number, next: FilterCondition) => {
    onChange({
      ...node.params,
      conditions: conditions.map((item, i) => (i === index ? next : item)),
    });
  };
  const removeCondition = (index: number) => {
    onChange({ ...node.params, conditions: conditions.filter((_, i) => i !== index) });
  };
  const changeColumn = (index: number, column: string) => {
    const type = shape.find((item) => item.name === column)?.type ?? "";
    const target = conditions[index];
    const op = operatorsForType(type, "").includes(target.op) ? target.op : "eq";
    const value = op === target.op ? target.value : toScalarValue(target.value, type);
    replaceCondition(index, { column, op, value });
  };
  const changeOp = (index: number, op: string) => {
    const target = conditions[index];
    const type = shape.find((item) => item.name === target.column)?.type ?? "";
    const next: FilterCondition = { column: target.column, op };
    if (op !== "is_null" && op !== "is_not_null") {
      next.value =
        op === "in" || op === "not_in"
          ? toArrayValue(target.value, type)
          : toScalarValue(target.value, type);
    }
    replaceCondition(index, next);
  };
  const errors = conditions.map((condition, index) =>
    filterConditionError(condition, index, shape),
  );
  return (
    <div className="filter-inline">
      <div className="fetch-source-switch">
        <button
          type="button"
          className={mode === "all" ? "active" : ""}
          onClick={() => onChange({ ...node.params, mode: "all", conditions })}
        >
          满足全部
        </button>
        <button
          type="button"
          className={mode === "any" ? "active" : ""}
          onClick={() => onChange({ ...node.params, mode: "any", conditions })}
        >
          满足任一
        </button>
      </div>
      {conditions.map((condition, index) => (
        <FilterConditionRow
          key={index}
          condition={condition}
          shape={shape}
          error={errors[index]}
          onChangeColumn={(column) => changeColumn(index, column)}
          onChangeOp={(op) => changeOp(index, op)}
          onChangeValue={(value) => updateCondition(index, { value })}
          onRemove={() => removeCondition(index)}
        />
      ))}
      <button
        type="button"
        className="filter-add-button"
        onClick={() =>
          onChange({
            ...node.params,
            conditions: [...conditions, { column: "", op: "eq", value: "" }],
          })
        }
      >
        ＋ 添加条件
      </button>
    </div>
  );
}

function FilterConditionRow({
  condition,
  shape,
  error,
  onChangeColumn,
  onChangeOp,
  onChangeValue,
  onRemove,
}: {
  condition: FilterCondition;
  shape: TableShape[];
  error: string | null;
  onChangeColumn: (column: string) => void;
  onChangeOp: (op: string) => void;
  onChangeValue: (value: unknown) => void;
  onRemove: () => void;
}) {
  const type = shape.find((column) => column.name === condition.column)?.type ?? "";
  const ops = operatorsForType(type, condition.op);
  return (
    <div className="filter-condition-row">
      <div className="filter-condition-line">
        <select
          value={condition.column}
          onChange={(event) => onChangeColumn(event.target.value)}
        >
          <option value="">选择列…</option>
          {shape.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}（{column.type}）
            </option>
          ))}
        </select>
        <select value={condition.op} onChange={(event) => onChangeOp(event.target.value)}>
          {ops.map((op) => (
            <option key={op} value={op}>
              {FILTER_OPERATOR_LABELS[op] ?? op}
            </option>
          ))}
        </select>
        <FilterValueControl condition={condition} type={type} onChange={onChangeValue} />
        <button
          type="button"
          className="filter-row-remove"
          title="移除条件"
          onClick={onRemove}
        >
          ×
        </button>
      </div>
      {error !== null && <p className="filter-row-error">{error}</p>}
    </div>
  );
}

function FilterValueControl({
  condition,
  type,
  onChange,
}: {
  condition: FilterCondition;
  type: string;
  onChange: (value: unknown) => void;
}) {
  const op = condition.op;
  if (op === "is_null" || op === "is_not_null") {
    return null;
  }
  if (op === "in" || op === "not_in") {
    return (
      <FilterMultiValue
        values={Array.isArray(condition.value) ? condition.value : []}
        type={type === "int" ? "int" : type === "float" ? "float" : "string"}
        placeholder={type === "string" ? "输入值后回车" : "输入数字后回车"}
        onChange={onChange}
      />
    );
  }
  if (type === "bool") {
    return (
      <select
        value={condition.value === true ? "true" : condition.value === false ? "false" : ""}
        onChange={(event) => onChange(event.target.value === "true")}
      >
        <option value="">真/假…</option>
        <option value="true">真</option>
        <option value="false">假</option>
      </select>
    );
  }
  if (type === "int" || type === "float") {
    return (
      <input
        type="number"
        step={type === "int" ? 1 : "any"}
        placeholder={type === "int" ? "整数" : "数值"}
        value={
          typeof condition.value === "number" && Number.isFinite(condition.value)
            ? String(condition.value)
            : ""
        }
        onChange={(event) =>
          onChange(event.target.value === "" ? undefined : Number(event.target.value))
        }
      />
    );
  }
  return (
    <input
      placeholder="输入值"
      value={typeof condition.value === "string" ? condition.value : ""}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** 多值 chips：回车或逗号添加，退格删除最后一个，chip 内可移除。 */
function FilterMultiValue({
  values,
  type,
  placeholder,
  onChange,
}: {
  values: unknown[];
  type: "string" | "int" | "float";
  placeholder: string;
  onChange: (value: unknown) => void;
}) {
  const [text, setText] = useState("");
  const commitText = (raw: string) => {
    const parts = raw
      .split(/[,，]/)
      .map((part) => part.trim())
      .filter((part) => part !== "");
    if (parts.length === 0) {
      setText("");
      return;
    }
    const next = [...values];
    for (const part of parts) {
      if (type === "string") {
        next.push(part);
        continue;
      }
      const number = Number(part);
      if (Number.isFinite(number) && (type === "float" || Number.isInteger(number))) {
        next.push(number);
      }
    }
    onChange(next);
    setText("");
  };
  return (
    <div className="filter-chips">
      {values.map((value, index) => (
        <span key={`${String(value)}-${index}`} className="filter-chip">
          {formatFilterValue(value)}
          <button
            type="button"
            title="移除"
            onClick={() => onChange(values.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="filter-chip-input"
        value={text}
        placeholder={placeholder}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === "," || event.key === "，") {
            event.preventDefault();
            commitText(text);
          } else if (event.key === "Backspace" && text === "" && values.length > 0) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={() => {
          if (text.trim() !== "") {
            commitText(text);
          }
        }}
      />
    </div>
  );
}

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
      return `${prefix}输出列名不合法（字母/数字/下划线，≤64 位）`;
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
      return `${prefix}结果列名不合法（字母/数字/下划线，≤64 位）`;
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

const LIMIT_MAX = 10_000;

export function LimitEditor({ node, onChange }: EditorProps) {
  const count = node.params.count;
  const raw = typeof count === "number" ? String(count) : "";
  const valid =
    typeof count === "number" && Number.isInteger(count) && count >= 1 && count <= LIMIT_MAX;
  return (
    <div className="limit-inline">
      <label className="limit-line">
        <span>保留前</span>
        <input
          type="number"
          min={1}
          max={LIMIT_MAX}
          step={1}
          value={raw}
          placeholder="1000"
          onChange={(event) => {
            const next = { ...node.params };
            if (event.target.value === "") {
              delete next.count;
            } else {
              next.count = Number(event.target.value);
            }
            onChange(next);
          }}
        />
        <span>行</span>
      </label>
      {!valid && <p className="filter-row-error">请输入 1–10000 的整数</p>}
    </div>
  );
}

const JOIN_MODE_OPTIONS = [
  {
    value: "inner",
    title: "只保留两边匹配上的行",
    description: "对不上号的行都丢弃",
  },
  {
    value: "left",
    title: "保留主表全部行",
    description: "副表匹配不上的补空，多余的行丢弃",
  },
] as const;

export function JoinEditor({ node, onChange }: EditorProps) {
  const leftShape = inputShapeFor(node.id, "left");
  const rightShape = inputShapeFor(node.id, "right");
  const mode = node.params.mode === "left" ? "left" : "inner";
  const leftKey = asString(node.params.left_key) ?? "";
  const rightKey = asString(node.params.right_key) ?? "";
  const leftType = leftShape.find((column) => column.name === leftKey)?.type ?? "";
  const rightType = rightShape.find((column) => column.name === rightKey)?.type ?? "";
  const typeMismatch =
    leftKey !== "" && rightKey !== "" && leftType !== "" && rightType !== "" && leftType !== rightType;
  const outputCount =
    leftShape.length +
    rightShape.filter((column) => !leftShape.some((left) => left.name === column.name)).length;
  const connected = leftShape.length > 0 && rightShape.length > 0;
  return (
    <div className="join-inline">
      <p className="join-hint">第一路输入为主表，第二路为副表</p>
      <div className="join-mode-grid" role="radiogroup" aria-label="合并方式">
        {JOIN_MODE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`join-mode-card${mode === option.value ? " active" : ""}`}
            onClick={() => onChange({ ...node.params, mode: option.value })}
          >
            <span className="join-mode-title">{option.title}</span>
            <span className="join-mode-description">{option.description}</span>
          </button>
        ))}
      </div>
      {!connected ? (
        <p className="analysis-editor-empty">连接两路输入后配置匹配键</p>
      ) : (
        <>
          <div className="join-key-row">
            <span className="join-key-label">主表</span>
            <select
              value={leftKey}
              onChange={(event) => onChange({ ...node.params, left_key: event.target.value })}
            >
              <option value="">匹配列…</option>
              {leftShape.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}（{column.type}）
                </option>
              ))}
            </select>
            <span className="join-equals">＝</span>
            <span className="join-key-label">副表</span>
            <select
              value={rightKey}
              onChange={(event) => onChange({ ...node.params, right_key: event.target.value })}
            >
              <option value="">匹配列…</option>
              {rightShape.map((column) => (
                <option key={column.name} value={column.name}>
                  {column.name}（{column.type}）
                </option>
              ))}
            </select>
          </div>
          {leftKey === "" && <p className="filter-row-error">请选择主表匹配列</p>}
          {rightKey === "" && <p className="filter-row-error">请选择副表匹配列</p>}
          {typeMismatch && (
            <p className="join-warning">
              主表键（{leftType}）与副表键（{rightType}）类型不一致，可能永远匹配不上
            </p>
          )}
          <p className="join-hint">合并后 {outputCount} 列（副表与主表重名的列只输出一份）</p>
        </>
      )}
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
