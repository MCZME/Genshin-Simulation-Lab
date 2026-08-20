import { useEffect, useState } from "react";
import type { WorkflowNode } from "../../workflow/types";
import type { EnumValue } from "../../workflow/types";
import { AssetPicker } from "../common/AssetPicker";
import {
  CollapsibleGroup,
  FieldRow,
  InlineError,
  NumberField,
  SelectField,
  TextAreaField,
  TextField,
} from "../common/fields";
import { isRunTerminal, useRunState } from "../run_state_context";

export interface NodeEditorProps {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
  fieldErrors?: Record<string, string[]>;
}

type ErrorOnlyProps = Pick<NodeEditorProps, "fieldErrors">;

const ENUM_VALUE_TYPES = [
  { value: "asset", label: "资产" },
  { value: "number", label: "数值" },
  { value: "string", label: "文本" },
  { value: "json_fragment", label: "JSON 片段" },
] as const;

export function RootEditor({ fieldErrors = {} }: ErrorOnlyProps) {
  return (
    <div className="node-editor">
      <p className="node-note">根数据：空模拟输入骨架（文件导入后置）</p>
      {firstError(fieldErrors, "file_path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "file_path")!} />
      )}
    </div>
  );
}

export function MetaEditor({ fieldErrors = {} }: ErrorOnlyProps) {
  return (
    <div className="node-editor">
      <p className="node-note">写入工作流名称到输入文档 meta</p>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function CharacterEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="角色" error={firstError(fieldErrors, "asset")}>
        <AssetPicker
          assetType="characters"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="命座" error={firstError(fieldErrors, "constellation")}>
        <NumberField
          value={asNumber(params.constellation)}
          min={0}
          max={6}
          onChange={(value) => onChange({ ...params, constellation: value ?? 0 })}
        />
      </FieldRow>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function WeaponEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="武器" error={firstError(fieldErrors, "asset")}>
        <AssetPicker
          assetType="weapons"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="精炼" error={firstError(fieldErrors, "refinement")}>
        <NumberField
          value={asNumber(params.refinement)}
          min={1}
          max={5}
          onChange={(value) => onChange({ ...params, refinement: value ?? 1 })}
        />
      </FieldRow>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function ArtifactEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="套装" error={firstError(fieldErrors, "asset")}>
        <AssetPicker
          assetType="artifact-sets"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="件数" error={firstError(fieldErrors, "pieces")}>
        <NumberField
          value={asNumber(params.pieces)}
          min={1}
          onChange={(value) => onChange({ ...params, pieces: value ?? 4 })}
        />
      </FieldRow>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function TargetEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="索引" error={firstError(fieldErrors, "index")}>
        <NumberField
          value={asNumber(params.index)}
          min={0}
          onChange={(value) => onChange({ ...params, index: value ?? 0 })}
        />
      </FieldRow>
      <FieldRow label="名称" error={firstError(fieldErrors, "id")}>
        <TextField
          value={asString(params.id) ?? ""}
          onChange={(value) => onChange({ ...params, id: value })}
        />
      </FieldRow>
      <FieldRow label="等级" error={firstError(fieldErrors, "level")}>
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

export function InputTraceEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const [text, setText] = useState(() => JSON.stringify(node.params.items ?? [], null, 2));
  const [invalid, setInvalid] = useState(false);
  const items = Array.isArray(node.params.items) ? (node.params.items as TraceEvent[]) : [];

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setText(JSON.stringify(node.params.items ?? [], null, 2));
  }, [node.params.items]);

  function handleChange(next: string) {
    setText(next);
    try {
      const parsed = JSON.parse(next) as unknown;
      if (Array.isArray(parsed)) {
        setInvalid(false);
        onChange({ ...node.params, items: parsed });
      } else {
        setInvalid(true);
      }
    } catch {
      setInvalid(true);
    }
  }

  return (
    <div className="node-editor">
      <CollapsibleGroup
        title="按键轨迹"
        summary={`${items.length} 个事件 · ${traceRange(items)}`}
        defaultOpen={false}
      >
        <TextAreaField value={text} onChange={handleChange} rows={7} invalid={invalid} />
        {(invalid || firstError(fieldErrors, "items") !== undefined) && (
          <InlineError message={invalid ? "必须是 JSON 数组" : firstError(fieldErrors, "items")!} />
        )}
      </CollapsibleGroup>
    </div>
  );
}

export function RunOptionsEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="最大帧数" error={firstError(fieldErrors, "max_frames")}>
        <NumberField
          value={asNumber(params.max_frames)}
          min={1}
          onChange={(value) => onChange({ ...params, max_frames: value ?? 18000 })}
        />
      </FieldRow>
    </div>
  );
}

export function EnumEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const values = Array.isArray(params.values) ? (params.values as EnumValue[]) : [];
  const valueType = asString(params.value_type) ?? "asset";

  function updateValues(next: EnumValue[]) {
    onChange({ ...params, values: next });
  }

  return (
    <div className="node-editor">
      <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="值类型" error={firstError(fieldErrors, "value_type")}>
        <SelectField
          value={valueType}
          options={[...ENUM_VALUE_TYPES]}
          onChange={(value) => onChange({ ...params, value_type: value })}
        />
      </FieldRow>
      <CollapsibleGroup title="取值" summary={`${values.length} 个取值`}>
        {firstErrorPrefix(fieldErrors, "values") !== undefined && (
          <InlineError message={firstErrorPrefix(fieldErrors, "values")!} />
        )}
        <div className="enum-values">
          {values.map((item, index) => (
            <div className="enum-value-row" key={item.item_id}>
              <span className="enum-item-id">{item.item_id}</span>
              {valueType === "number" ? (
                <NumberField
                  value={typeof item.value === "number" ? item.value : Number(item.value)}
                  onChange={(value) => {
                    const next = [...values];
                    next[index] = { ...item, value: value ?? 0 };
                    updateValues(next);
                  }}
                />
              ) : (
                <TextField
                  value={String(item.value ?? "")}
                  mono
                  onChange={(value) => {
                    const next = [...values];
                    next[index] = { ...item, value };
                    updateValues(next);
                  }}
                />
              )}
              <TextField
                value={item.label ?? ""}
                placeholder="标签"
                onChange={(value) => {
                  const next = [...values];
                  next[index] = { ...item, label: value === "" ? null : value };
                  updateValues(next);
                }}
              />
              <button
                type="button"
                className="icon-button"
                title="删除取值"
                onClick={() => updateValues(values.filter((_, valueIndex) => valueIndex !== index))}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              updateValues([
                ...values,
                { item_id: nextEnumId(values), value: valueType === "number" ? 0 : "", label: null },
              ])
            }
          >
            + 添加取值
          </button>
        </div>
      </CollapsibleGroup>
    </div>
  );
}

export function RangeEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="起点" error={firstError(fieldErrors, "start")}>
        <NumberField
          value={asNumber(params.start)}
          onChange={(value) => onChange({ ...params, start: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="终点" error={firstError(fieldErrors, "end")}>
        <NumberField
          value={asNumber(params.end)}
          onChange={(value) => onChange({ ...params, end: value ?? 10 })}
        />
      </FieldRow>
      <FieldRow label="步长" error={firstError(fieldErrors, "step")}>
        <NumberField
          value={asNumber(params.step)}
          onChange={(value) => onChange({ ...params, step: value ?? 1 })}
        />
      </FieldRow>
    </div>
  );
}

export function SimulationEditor() {
  const { runState, onCancelRun } = useRunState();
  const members = runState.members;
  return (
    <div className="simulation-editor">
      {members.length === 0 ? (
        <p className="node-note">连接配置区域边界后运行批次</p>
      ) : (
        <ul className="member-list">
          {members.map((member) => (
            <li className="member-row" key={member.item_id}>
              <span className="member-id">{member.item_id}</span>
              <span className={`status-badge status-${member.state}`}>{member.state}</span>
            </li>
          ))}
        </ul>
      )}
      {runState.runId !== null && !isRunTerminal(runState.state) && (
        <button type="button" className="text-button danger" onClick={onCancelRun}>
          取消整批
        </button>
      )}
    </div>
  );
}

export function UnknownEditor({ node }: NodeEditorProps) {
  return <p className="node-note">未注册编辑器：{node.kind}</p>;
}

function firstError(errors: Record<string, string[]>, path: string): string | undefined {
  return errors[path]?.[0];
}

function firstErrorPrefix(
  errors: Record<string, string[]>,
  prefix: string,
): string | undefined {
  const key = Object.keys(errors).find(
    (path) => path === prefix || path.startsWith(`${prefix}[`),
  );
  return key === undefined ? undefined : errors[key]?.[0];
}

interface TraceEvent {
  frame: number;
  events: unknown[];
}

function traceRange(items: TraceEvent[]): string {
  if (items.length === 0) {
    return "无事件";
  }
  let min = Infinity;
  let max = -Infinity;
  for (const item of items) {
    if (item.frame < min) {
      min = item.frame;
    }
    if (item.frame > max) {
      max = item.frame;
    }
  }
  return `首帧 ${min} · 末帧 ${max}`;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nextEnumId(values: EnumValue[]): string {
  const max = values.reduce((current, item) => {
    const suffix = Number(item.item_id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `e-${max + 1}`;
}
