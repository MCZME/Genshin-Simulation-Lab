/** 展示配置节点：表格 / 时间轴 / 饼图 / 柱状图绑定编辑。 */

import { useState } from "react";
import { configTargetView, viewInputShape } from "../../../workflow/templates";
import { normalizeWidthMode } from "../../../workflow/view_size";
import { asString } from "../common";
import { useContextEnv, type EditorProps } from "./context";

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

/** 绑定角色的可读名：列名即显示名，角色标签统一用业务语义。 */
const ROLE_LABELS: Record<string, string> = {
  track: "轨道",
  start: "起点",
  end: "终点",
  value: "值列",
  label: "标签列",
  group: "分组列",
  x: "X 轴列",
  y: "Y 轴列",
  series: "系列列",
};

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/** 表格配置参数统一归一化：存量节点缺省宽度参数时按默认值补齐。 */
function normalizeTableParams(params: Record<string, unknown>): Record<string, unknown> {
  return {
    ...params,
    width_mode: normalizeWidthMode(params.width_mode),
  };
}

type BindingZone = "condition" | "data";

interface BindingDragSource {
  zone: BindingZone;
  index: number;
  column: string;
}

function BindingList({
  zone,
  title,
  hint,
  columns,
  available,
  taken,
  onChange,
  dragSource,
  onDragStart,
  onDragEnd,
  onDropAt,
  onDropAppend,
}: {
  zone: BindingZone;
  title: string;
  hint: string;
  columns: string[];
  available: string[];
  taken: Set<string>;
  onChange: (next: string[]) => void;
  dragSource: BindingDragSource | null;
  onDragStart: (source: BindingDragSource) => void;
  onDragEnd: () => void;
  onDropAt: (zone: BindingZone, index: number) => void;
  onDropAppend: (zone: BindingZone) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<string[]>([]);
  const keyword = search.trim().toLowerCase();
  const filtered = available.filter(
    (name) =>
      !taken.has(name) && (keyword === "" || name.toLowerCase().includes(keyword)),
  );
  const toggleAdd = () => {
    setAddOpen((current) => !current);
    setSearch("");
    setPending([]);
  };
  const confirmAdd = () => {
    if (pending.length > 0) {
      onChange([...columns, ...pending]);
    }
    setAddOpen(false);
    setSearch("");
    setPending([]);
  };
  return (
    <div
      className={`table-binding-zone ${zone === "data" ? "zone-data" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        onDropAppend(zone);
      }}
    >
      <div className="table-binding-header">
        <button
          type="button"
          className="table-binding-collapse"
          aria-label={collapsed ? `展开${title}` : `折叠${title}`}
          onClick={() => {
            setCollapsed((current) => !current);
            setAddOpen(false);
          }}
        >
          {collapsed ? "▸" : "▾"}
        </button>
        <span className="table-binding-title">{title}</span>
        <span className="table-binding-count">{columns.length}</span>
        {!collapsed && (
          <button
            type="button"
            className="table-binding-add-button"
            aria-label={`添加${title}`}
            title={`添加${title}`}
            onClick={toggleAdd}
          >
            ＋
          </button>
        )}
      </div>
      {!collapsed && (
        <>
          <span className="table-binding-hint">{hint}</span>
          {columns.length === 0 ? (
            <p className="table-binding-empty">未选择列</p>
          ) : (
            <ul className="table-binding-list">
              {columns.map((column, index) => (
                <li
                  key={`${column}-${index}`}
                  className={`table-binding-row ${
                    dragSource !== null &&
                    !(dragSource.zone === zone && dragSource.index === index)
                      ? "drag-target"
                      : ""
                  }`}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onDropAt(zone, index);
                  }}
                >
                  <span
                    className="table-binding-drag nodrag"
                    draggable
                    title="拖拽调整顺序或移动分区"
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", column);
                      onDragStart({ zone, index, column });
                    }}
                    onDragEnd={onDragEnd}
                  >
                    ⋮⋮
                  </span>
                  <select
                    aria-label={`${title}第 ${index + 1} 行`}
                    value={column}
                    onChange={(event) =>
                      onChange(
                        columns.map((item, i) =>
                          i === index ? event.target.value : item,
                        ),
                      )
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
          {addOpen && (
            <div className="table-binding-add-panel">
              <input
                className="table-binding-add-search"
                type="search"
                placeholder="搜索列名"
                aria-label={`搜索${title}`}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              {filtered.length === 0 ? (
                <p className="table-binding-empty">没有可添加的列</p>
              ) : (
                <ul className="table-binding-add-options">
                  {filtered.map((name) => (
                    <li key={name} className="table-binding-add-option">
                      <label>
                        <input
                          type="checkbox"
                          checked={pending.includes(name)}
                          aria-label={`选择列 ${name}`}
                          onChange={(event) =>
                            setPending((current) =>
                              event.target.checked
                                ? [...current, name]
                                : current.filter((item) => item !== name),
                            )
                          }
                        />
                        {name}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              <div className="table-binding-add-actions">
                <button type="button" className="text-button" onClick={toggleAdd}>
                  取消
                </button>
                <button
                  type="button"
                  className="text-button"
                  aria-label={`确认添加${title}`}
                  disabled={pending.length === 0}
                  onClick={confirmAdd}
                >
                  添加 {pending.length} 列
                </button>
              </div>
            </div>
          )}
        </>
      )}
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
  const widthMode = node.params.width_mode === "fixed" ? "fixed" : "auto";
  const [dragSource, setDragSource] = useState<BindingDragSource | null>(null);

  function commitMove(
    source: BindingDragSource,
    targetZone: BindingZone,
    targetIndex?: number,
  ) {
    const next = {
      condition_columns: [...condition],
      data_columns: [...data],
    };
    const sourceList =
      source.zone === "condition" ? next.condition_columns : next.data_columns;
    const targetList =
      targetZone === "condition" ? next.condition_columns : next.data_columns;
    const [moved] = sourceList.splice(source.index, 1);
    if (moved === undefined) {
      setDragSource(null);
      return;
    }
    targetList.splice(targetIndex ?? targetList.length, 0, moved);
    onChange(
      normalizeTableParams({
        ...node.params,
        condition_columns: next.condition_columns,
        data_columns: next.data_columns,
      }),
    );
    setDragSource(null);
  }

  return (
    <div className="analysis-editor table-config-editor">
      {available.length === 0 && (
        <p className="analysis-editor-empty table-config-editor-empty">
          连接视图并接通数据源后，这里会出现可绑定的列。
        </p>
      )}
      <BindingList
        zone="condition"
        title="条件列"
        hint="说明这一行是什么配置"
        columns={condition}
        available={available}
        taken={taken}
        onChange={(next) =>
          onChange(normalizeTableParams({ ...node.params, condition_columns: next }))
        }
        dragSource={dragSource}
        onDragStart={setDragSource}
        onDragEnd={() => setDragSource(null)}
        onDropAt={(targetZone, index) => {
          if (dragSource !== null) {
            commitMove(dragSource, targetZone, index);
          }
        }}
        onDropAppend={(targetZone) => {
          if (dragSource !== null) {
            commitMove(dragSource, targetZone);
          }
        }}
      />
      <BindingList
        zone="data"
        title="数据列"
        hint="要分析的指标"
        columns={data}
        available={available}
        taken={taken}
        onChange={(next) =>
          onChange(normalizeTableParams({ ...node.params, data_columns: next }))
        }
        dragSource={dragSource}
        onDragStart={setDragSource}
        onDragEnd={() => setDragSource(null)}
        onDropAt={(targetZone, index) => {
          if (dragSource !== null) {
            commitMove(dragSource, targetZone, index);
          }
        }}
        onDropAppend={(targetZone) => {
          if (dragSource !== null) {
            commitMove(dragSource, targetZone);
          }
        }}
      />
      <div className="table-display-zone">
        <div className="table-binding-title">
          <span>展示</span>
          <span className="table-binding-hint">
            高度手动调节；自适应内容超出上限时裁剪，拖宽查看
          </span>
        </div>
        <label className="table-size-field">
          <span>宽度模式</span>
          <select
            value={widthMode}
            onChange={(event) =>
              onChange(
                normalizeTableParams({ ...node.params, width_mode: event.target.value }),
              )
            }
          >
            <option value="auto">自适应</option>
            <option value="fixed">固定</option>
          </select>
        </label>
      </div>
    </div>
  );
}

/** 展示配置编辑器：单值角色用列下拉（列选项沿「配置 → 视图 → 上游」解析）。 */
export function DisplayConfigEditor({ node, onChange }: EditorProps) {
  const env = useContextEnv();
  const view = configTargetView(env.definition, node.id);
  const shape = view === null ? [] : viewInputShape(env.shapes, env.definition, view.id);
  const available = shape.map((column) => column.name);
  const roles = ROLE_CONFIGS[node.kind] ?? [];
  return (
    <div className="analysis-editor">
      {available.length === 0 && (
        <p className="analysis-editor-empty">
          连接视图并接通数据源后，这里会出现可绑定的列。
        </p>
      )}
      {roles.map((config) => {
        const current = asString(node.params[config.role]) ?? "";
        return (
          <label key={config.role} className="analysis-field">
            <span>
              {ROLE_LABELS[config.role] ?? config.role}
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
              <select
                value={current}
                onChange={(event) =>
                  onChange({ ...node.params, [config.role]: event.target.value })
                }
              >
                <option value="">列…</option>
                {available.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
                {current !== "" && !available.includes(current) && (
                  <option value={current}>{current}</option>
                )}
              </select>
            )}
          </label>
        );
      })}
    </div>
  );
}
