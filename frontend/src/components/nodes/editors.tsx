import { useEffect, useMemo, useState } from "react";
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

/** 角色等级：1-90 每级，外加正式等级点 95、100。 */
const CHARACTER_LEVELS = [...Array.from({ length: 90 }, (_, index) => index + 1), 95, 100];

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

export function MetaEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="名称" error={firstError(fieldErrors, "name")}>
        <TextField
          value={asString(params.name) ?? ""}
          onChange={(value) => onChange({ ...params, name: value })}
        />
      </FieldRow>
      <FieldRow label="描述" error={firstError(fieldErrors, "description")}>
        <TextField
          value={asString(params.description) ?? ""}
          onChange={(value) => onChange({ ...params, description: value })}
        />
      </FieldRow>
    </div>
  );
}

export function CharacterEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const talents = isPlainObject(params.talents) ? params.talents : {};
  function updateTalent(key: string, level: number) {
    onChange({ ...params, talents: { ...talents, [key]: level } });
  }
  return (
    <div className="node-editor">
      <FieldRow label="槽位" error={firstError(fieldErrors, "slot")}>
        <NumberField
          value={asNumber(params.slot)}
          min={1}
          max={4}
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
          options={CHARACTER_LEVELS}
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
      <div className="node-editor-group">
        <span className="node-editor-group-title">天赋</span>
        <FieldRow label="普通攻击" error={firstError(fieldErrors, "talents.normal_attack")}>
          <NumberField
            value={asNumber(talents.normal_attack) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("normal_attack", value ?? 1)}
          />
        </FieldRow>
        <FieldRow label="元素战技" error={firstError(fieldErrors, "talents.elemental_skill")}>
          <NumberField
            value={asNumber(talents.elemental_skill) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("elemental_skill", value ?? 1)}
          />
        </FieldRow>
        <FieldRow label="元素爆发" error={firstError(fieldErrors, "talents.elemental_burst")}>
          <NumberField
            value={asNumber(talents.elemental_burst) ?? 1}
            min={1}
            max={10}
            onChange={(value) => updateTalent("elemental_burst", value ?? 1)}
          />
        </FieldRow>
      </div>
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
          max={90}
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
          max={5}
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
          max={100}
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
  const items = useMemo(
    () => (Array.isArray(node.params.items) ? (node.params.items as TraceEventItem[]) : []),
    [node.params.items],
  );
  const declaredTracks = useMemo(
    () =>
      Array.isArray(node.params.tracks)
        ? node.params.tracks.filter((track): track is string => typeof track === "string")
        : [],
    [node.params.tracks],
  );
  const blocks = useMemo(() => buildBlocks(items), [items]);
  const [scale, setScale] = useState(0.5);
  const [newTrackKey, setNewTrackKey] = useState("");
  const [gesture, setGesture] = useState<TraceGesture | null>(null);
  const [text, setText] = useState(() => JSON.stringify(node.params.items ?? [], null, 2));
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setText(JSON.stringify(node.params.items ?? [], null, 2));
  }, [node.params.items]);

  const keys = useMemo(() => {
    const result: string[] = [...declaredTracks];
    for (const block of blocks) {
      if (!result.includes(block.key)) {
        result.push(block.key);
      }
    }
    return result;
  }, [blocks, declaredTracks]);
  const maxFrame = useMemo(() => {
    const last = blocks.reduce((max, block) => Math.max(max, block.release ?? block.press), 0);
    return Math.max(120, last + 120);
  }, [blocks]);
  const width = Math.ceil(maxFrame * scale) + 48;

  function commitBlocks(next: TraceBlock[]) {
    onChange({ ...node.params, items: blocksToItems(next) });
  }

  function commitTracks(nextTracks: string[], nextBlocks: TraceBlock[]) {
    onChange({
      ...node.params,
      tracks: nextTracks,
      items: blocksToItems(nextBlocks),
    });
  }

  function startGesture(
    event: React.PointerEvent<HTMLElement>,
    block: TraceBlock,
    mode: TraceGesture["mode"],
  ) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const startRelease = block.release ?? block.press;
    setGesture({
      blockId: block.id,
      mode,
      startX: event.clientX,
      startPress: block.press,
      startRelease,
      press: block.press,
      release: startRelease,
    });
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture === null) {
      return;
    }
    const delta = Math.round((event.clientX - gesture.startX) / scale);
    let press = gesture.startPress;
    let release = gesture.startRelease;
    if (gesture.mode === "move") {
      press = Math.max(1, gesture.startPress + delta);
      release = Math.max(press + 1, gesture.startRelease + delta);
    } else if (gesture.mode === "resize-left") {
      press = Math.min(gesture.startPress + delta, gesture.startRelease - 1);
      press = Math.max(1, press);
    } else {
      release = Math.max(gesture.startRelease + delta, gesture.startPress + 1);
    }
    setGesture({ ...gesture, press, release });
  }

  function endGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture === null) {
      return;
    }
    const final = { ...gesture };
    setGesture(null);
    commitBlocks(
      blocks.map((block) =>
        block.id === final.blockId
          ? { ...block, press: final.press, release: final.release }
          : block,
      ),
    );
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function cancelGesture(event: React.PointerEvent<HTMLDivElement>) {
    setGesture(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleLanePointerDown(
    event: React.PointerEvent<HTMLDivElement>,
    key: string,
  ) {
    if (event.button !== 0 || (event.target as HTMLElement).closest(".trace-block") !== null) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const frame = Math.min(
      TRACE_MAX_FRAME,
      Math.max(1, Math.round((event.clientX - rect.left) / scale)),
    );
    const open = blocks.find((block) => block.key === key && block.release === null);
    if (open !== undefined) {
      if (frame <= open.press) {
        return;
      }
      commitBlocks(
        blocks.map((block) => (block.id === open.id ? { ...block, release: frame } : block)),
      );
    } else {
      commitBlocks([
        ...blocks,
        {
          id: `${key}:${frame}:${blocks.length}`,
          key,
          press: frame,
          release: null,
        },
      ]);
    }
  }

  const visibleBlocks = blocks.map((block) => {
    if (gesture === null || gesture.blockId !== block.id) {
      return block;
    }
    return { ...block, press: gesture.press, release: gesture.release };
  });

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
      <div className="trace-toolbar">
        <span className="trace-zoom-label">{scale} px/帧</span>
        <button
          type="button"
          className="text-button"
          onClick={() => setScale((current) => Math.max(0.125, current / 2))}
        >
          缩小
        </button>
        <button
          type="button"
          className="text-button"
          onClick={() => setScale((current) => Math.min(4, current * 2))}
        >
          放大
        </button>
        <form
          className="trace-add-track"
          onSubmit={(event) => {
            event.preventDefault();
            const key = newTrackKey.trim();
            if (key === "" || declaredTracks.includes(key)) {
              return;
            }
            commitTracks([...declaredTracks, key], blocks);
            setNewTrackKey("");
          }}
        >
          <input
            className="field nowheel"
            value={newTrackKey}
            placeholder="新轨道 key"
            onChange={(event) => setNewTrackKey(event.target.value)}
          />
          <button type="submit" className="text-button">
            + 轨道
          </button>
        </form>
      </div>
      <div className="trace-scroll">
        <div className="trace-canvas" style={{ width }}>
          <div className="trace-ruler">
            {Array.from({ length: Math.floor(maxFrame / 60) }, (_, index) => (index + 1) * 60).map(
              (frame) => (
                <span className="trace-tick" key={frame} style={{ left: frame * scale }}>
                  {frame}
                </span>
              ),
            )}
          </div>
          {keys.length === 0 && (
            <p className="node-note">点击轨道空白处添加按下事件，再次点击闭合松开</p>
          )}
          {keys.map((key) => (
            <div className="trace-track" key={key}>
              <div className="trace-track-label">
                <span className="trace-key">{key}</span>
                <button
                  type="button"
                  className="icon-button"
                  title="删除轨道"
                  onClick={() =>
                    commitTracks(
                      declaredTracks.filter((track) => track !== key),
                      blocks.filter((block) => block.key !== key),
                    )
                  }
                >
                  ×
                </button>
              </div>
              <div
                className="trace-track-lane"
                onPointerDown={(event) => handleLanePointerDown(event, key)}
              >
                {visibleBlocks
                  .filter((block) => block.key === key)
                  .map((block) => (
                    <div
                      key={block.id}
                      className={`trace-block ${block.release === null || block.invalid ? "trace-block-unclosed" : ""}`}
                      style={{
                        left: block.press * scale,
                        width: Math.max(
                          6,
                          ((block.release ?? block.press) - block.press) * scale,
                        ),
                      }}
                      onPointerDown={(event) => startGesture(event, block, "move")}
                      onPointerMove={moveGesture}
                      onPointerUp={endGesture}
                      onPointerCancel={cancelGesture}
                    >
                      <button
                        type="button"
                        className="trace-block-delete"
                        title="删除事件"
                        onClick={(event) => {
                          event.stopPropagation();
                          commitBlocks(blocks.filter((item) => item.id !== block.id));
                        }}
                      >
                        ×
                      </button>
                      <span
                        className="trace-block-handle trace-block-handle-left"
                        onPointerDown={(event) => startGesture(event, block, "resize-left")}
                      />
                      <span
                        className="trace-block-handle trace-block-handle-right"
                        onPointerDown={(event) => startGesture(event, block, "resize-right")}
                      />
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <CollapsibleGroup
        title="JSON 高级编辑"
        summary={`${items.length} 个事件 · ${traceRange(items)} · ${keys.length} 条轨道`}
        defaultOpen={false}
      >
        <TextAreaField value={text} onChange={handleChange} rows={7} invalid={invalid} />
      </CollapsibleGroup>
      {(invalid || firstError(fieldErrors, "items") !== undefined) && (
        <InlineError message={invalid ? "必须是 JSON 数组" : firstError(fieldErrors, "items")!} />
      )}
    </div>
  );
}

interface TraceEventItem {
  frame: number;
  events: Array<{ key: string; phase: "press" | "release" }>;
}

interface TraceBlock {
  id: string;
  key: string;
  press: number;
  release: number | null;
  invalid?: boolean;
}

interface TraceGesture {
  blockId: string;
  mode: "move" | "resize-left" | "resize-right";
  startX: number;
  startPress: number;
  startRelease: number;
  press: number;
  release: number;
}

const TRACE_MAX_FRAME = 100000;

function buildBlocks(items: TraceEventItem[]): TraceBlock[] {
  const byKey = new Map<string, Array<{ frame: number; phase: "press" | "release" }>>();
  for (const item of items) {
    if (typeof item.frame !== "number" || !Array.isArray(item.events)) {
      continue;
    }
    for (const event of item.events) {
      if (typeof event.key !== "string" || event.key === "") {
        continue;
      }
      const list = byKey.get(event.key) ?? [];
      list.push({ frame: item.frame, phase: event.phase === "release" ? "release" : "press" });
      byKey.set(event.key, list);
    }
  }

  const blocks: TraceBlock[] = [];
  for (const [key, events] of byKey) {
    events.sort((a, b) => a.frame - b.frame);
    let open: { press: number } | null = null;
    for (const event of events) {
      if (event.phase === "press") {
        if (open !== null) {
          blocks.push({
            id: `${key}:${open.press}:${blocks.length}`,
            key,
            press: open.press,
            release: null,
          });
        }
        open = { press: event.frame };
      } else {
        if (open !== null) {
          blocks.push({
            id: `${key}:${open.press}:${blocks.length}`,
            key,
            press: open.press,
            release: Math.max(event.frame, open.press + 1),
          });
          open = null;
        } else {
          blocks.push({
            id: `${key}:${event.frame}:${blocks.length}`,
            key,
            press: event.frame,
            release: event.frame,
            invalid: true,
          });
        }
      }
    }
    if (open !== null) {
      blocks.push({
        id: `${key}:${open.press}:${blocks.length}`,
        key,
        press: open.press,
        release: null,
      });
    }
  }
  return blocks;
}

function blocksToItems(blocks: TraceBlock[]): TraceEventItem[] {
  const byFrame = new Map<number, Array<{ key: string; phase: "press" | "release" }>>();
  for (const block of blocks) {
    const pressEvents = byFrame.get(block.press) ?? [];
    pressEvents.push({ key: block.key, phase: "press" });
    byFrame.set(block.press, pressEvents);
    if (block.release !== null) {
      const releaseEvents = byFrame.get(block.release) ?? [];
      releaseEvents.push({ key: block.key, phase: "release" });
      byFrame.set(block.release, releaseEvents);
    }
  }
  return [...byFrame.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([frame, events]) => ({ frame, events }));
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

function traceRange(items: TraceEventItem[]): string {
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

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nextEnumId(values: EnumValue[]): string {
  const max = values.reduce((current, item) => {
    const suffix = Number(item.item_id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `e-${max + 1}`;
}
