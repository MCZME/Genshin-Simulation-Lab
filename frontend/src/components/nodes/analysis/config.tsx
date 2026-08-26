/** 展示配置节点：表格 / 时间轴 / 饼图 / 柱状图绑定编辑。 */

import { configTargetView, viewInputShape } from "../../../workflow/templates";
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
