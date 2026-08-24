/** 分析区域节点编辑器（模板驱动的处理节点、查询参数配置、展示配置、数据提供）。 */

import { useEffect, useState } from "react";

import { listResults } from "../../api/client";
import type { RunListItem } from "../../api/client";
import type { TemplateParam } from "../../workflow/templates";
import { useTemplateCatalog } from "../analysis_context";
import type { NodeEditorProps } from "./common";
import { asString, isPlainObject } from "./common";

export function DataProviderEditor({ node, onChange }: NodeEditorProps) {
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

export function ProcessingEditor({ node, onChange }: NodeEditorProps) {
  const catalog = useTemplateCatalog();
  const templateId = asString(node.params.template_id) ?? "";
  const templates = catalog?.list() ?? [];
  const template = templateId === "" ? null : catalog?.get(templateId) ?? null;
  const values = isPlainObject(node.params.values) ? node.params.values : {};
  const valueBindings = isPlainObject(node.params.value_bindings)
    ? node.params.value_bindings
    : {};

  const setValues = (name: string, value: unknown) => {
    onChange({ ...node.params, values: { ...values, [name]: value } });
  };
  const setBinding = (name: string, column: string) => {
    onChange({ ...node.params, value_bindings: { ...valueBindings, [name]: column } });
  };

  return (
    <div className="analysis-editor">
      <label className="analysis-field">
        <span>模板</span>
        <select
          value={templateId}
          onChange={(event) =>
            onChange({
              ...node.params,
              template_id: event.target.value,
              values: {},
              value_bindings: {},
            })
          }
        >
          <option value="">选择模板…</option>
          {templates.map((item) => (
            <option key={item.template_id} value={item.template_id}>
              {item.display_name}
            </option>
          ))}
        </select>
      </label>
      {template === null ? null : (
        <div className="analysis-param-list">
          {template.params.map((param) => (
            <ParamEditor
              key={param.name}
              param={param}
              value={values[param.name]}
              column={valueBindings[param.name]}
              onValue={(value) => setValues(param.name, value)}
              onColumn={(column) => setBinding(param.name, column)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ParamEditor({
  param,
  value,
  column,
  onValue,
  onColumn,
}: {
  param: TemplateParam;
  value: unknown;
  column: unknown;
  onValue: (value: unknown) => void;
  onColumn: (column: string) => void;
}) {
  const bindingText = param.binding.join(" / ");
  return (
    <div className="analysis-param">
      <div className="analysis-param-head">
        <span>{param.name}</span>
        <span className="analysis-param-meta">
          {param.type}
          {param.required ? " 必填" : ""} · {bindingText}
        </span>
      </div>
      {param.binding.includes("static") && (
        <input
          value={value === undefined ? "" : String(value)}
          onChange={(event) => onValue(parseScalar(param.type, event.target.value))}
        />
      )}
      {param.binding.includes("upstream_column") && (
        <input
          placeholder="上游表列名"
          value={column === undefined ? "" : String(column)}
          onChange={(event) => onColumn(event.target.value)}
        />
      )}
    </div>
  );
}

function parseScalar(type: string, text: string): unknown {
  if (type === "int") {
    return text === "" ? "" : Number(text);
  }
  if (type === "float") {
    return text === "" ? "" : Number(text);
  }
  if (type === "bool") {
    return text === "true";
  }
  return text;
}

export function QueryConfigEditor({ node, onChange }: NodeEditorProps) {
  const rows = Array.isArray(node.params.rows)
    ? (node.params.rows as Array<Record<string, unknown>>)
    : [];
  const update = (next: Array<Record<string, unknown>>) => {
    onChange({ ...node.params, rows: next });
  };
  return (
    <div className="analysis-editor">
      {rows.map((row, index) => (
        <div key={index} className="analysis-param-row">
          <input
            placeholder="参数名"
            value={typeof row.param === "string" ? row.param : ""}
            onChange={(event) =>
              update(rows.map((item, idx) => (idx === index ? { ...item, param: event.target.value } : item)))
            }
          />
          <input
            placeholder="值"
            value={row.value === undefined ? "" : String(row.value)}
            onChange={(event) =>
              update(rows.map((item, idx) => (idx === index ? { ...item, value: event.target.value } : item)))
            }
          />
          <button
            type="button"
            onClick={() => update(rows.filter((_, idx) => idx !== index))}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" onClick={() => update([...rows, { param: "", value: "" }])}>
        添加参数
      </button>
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

export function DisplayConfigEditor({ node, onChange }: NodeEditorProps) {
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
