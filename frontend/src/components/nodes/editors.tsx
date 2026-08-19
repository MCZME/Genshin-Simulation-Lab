import { useEffect, useState } from "react";
import type { WorkflowNode } from "../../workflow/types";
import type { EnumValue } from "../../workflow/types";
import { AssetPicker } from "../common/AssetPicker";
import {
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
}

const ENUM_VALUE_TYPES = [
  { value: "asset", label: "资产" },
  { value: "number", label: "数值" },
  { value: "string", label: "文本" },
  { value: "json_fragment", label: "JSON 片段" },
] as const;

export function RootEditor() {
  return <p className="node-note">根数据：空模拟输入骨架（文件导入后置）</p>;
}

export function MetaEditor() {
  return <p className="node-note">写入工作流名称到输入文档 meta</p>;
}

export function CharacterEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位">
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="角色">
        <AssetPicker
          assetType="characters"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级">
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="命座">
        <NumberField
          value={asNumber(params.constellation)}
          min={0}
          max={6}
          onChange={(value) => onChange({ ...params, constellation: value ?? 0 })}
        />
      </FieldRow>
    </div>
  );
}

export function WeaponEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位">
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="武器">
        <AssetPicker
          assetType="weapons"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="等级">
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
      <FieldRow label="精炼">
        <NumberField
          value={asNumber(params.refinement)}
          min={1}
          max={5}
          onChange={(value) => onChange({ ...params, refinement: value ?? 1 })}
        />
      </FieldRow>
    </div>
  );
}

export function ArtifactEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="槽位">
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          onChange={(value) => onChange({ ...params, slot: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="套装">
        <AssetPicker
          assetType="artifact-sets"
          value={asString(params.asset) ?? ""}
          onChange={(asset) => onChange({ ...params, asset })}
        />
      </FieldRow>
      <FieldRow label="件数">
        <NumberField
          value={asNumber(params.pieces)}
          min={1}
          onChange={(value) => onChange({ ...params, pieces: value ?? 4 })}
        />
      </FieldRow>
    </div>
  );
}

export function TargetEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="索引">
        <NumberField
          value={asNumber(params.index)}
          min={0}
          onChange={(value) => onChange({ ...params, index: value ?? 0 })}
        />
      </FieldRow>
      <FieldRow label="id">
        <TextField
          value={asString(params.id) ?? ""}
          onChange={(value) => onChange({ ...params, id: value })}
        />
      </FieldRow>
      <FieldRow label="等级">
        <NumberField
          value={asNumber(params.level)}
          min={1}
          onChange={(value) => onChange({ ...params, level: value ?? 90 })}
        />
      </FieldRow>
    </div>
  );
}

export function InputTraceEditor({ node, onChange }: NodeEditorProps) {
  const [text, setText] = useState(() => JSON.stringify(node.params.items ?? [], null, 2));
  const [invalid, setInvalid] = useState(false);

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
      <TextAreaField value={text} onChange={handleChange} rows={7} invalid={invalid} />
      {invalid && <InlineError message="必须是 JSON 数组" />}
    </div>
  );
}

export function RunOptionsEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="最大帧数">
        <NumberField
          value={asNumber(params.max_frames)}
          min={1}
          onChange={(value) => onChange({ ...params, max_frames: value ?? 18000 })}
        />
      </FieldRow>
    </div>
  );
}

export function EnumEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  const values = Array.isArray(params.values) ? (params.values as EnumValue[]) : [];
  const valueType = asString(params.value_type) ?? "asset";

  function updateValues(next: EnumValue[]) {
    onChange({ ...params, values: next });
  }

  return (
    <div className="node-editor">
      <FieldRow label="路径">
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="值类型">
        <SelectField
          value={valueType}
          options={[...ENUM_VALUE_TYPES]}
          onChange={(value) => onChange({ ...params, value_type: value })}
        />
      </FieldRow>
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
    </div>
  );
}

export function RangeEditor({ node, onChange }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="路径">
        <TextField
          value={asString(params.path) ?? ""}
          mono
          onChange={(value) => onChange({ ...params, path: value })}
        />
      </FieldRow>
      <FieldRow label="起点">
        <NumberField
          value={asNumber(params.start)}
          onChange={(value) => onChange({ ...params, start: value ?? 1 })}
        />
      </FieldRow>
      <FieldRow label="终点">
        <NumberField
          value={asNumber(params.end)}
          onChange={(value) => onChange({ ...params, end: value ?? 10 })}
        />
      </FieldRow>
      <FieldRow label="步长">
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
