/** 获取数据节点：卡内摘要 + 大弹层配置器。 */

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type {
  AnalysisSchemaNode,
  SnapshotLeaf,
} from "../../../workflow/templates";
import { snapshotLeaves } from "../../../workflow/templates";
import type { WorkflowNode } from "../../../workflow/types";
import { asString } from "../common";
import {
  COLUMN_NAME_PATTERN,
  useContextEnv,
  type EditorProps,
  type EditorRow,
} from "./context";

/** 输出列类型选项（与后端类型词表一致）。 */
const EXTRACT_TYPES = ["string", "int", "float", "bool"] as const;

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
      errors.push(`第 ${index + 1} 个输出列名不合法（中文/字母/数字/下划线，≤64 位）`);
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
