import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties } from "react";
import { ELEMENT_COLORS, ELEMENT_LABELS } from "../../theme/elements";
import { INPUT_KEY_DEFS, inputKeyDef } from "../../workflow/inputKeys";
import { RESISTANCE_ELEMENT_KEYS } from "../../workflow/registry";
import type { WorkflowNode } from "../../workflow/types";
import type { EnumValue } from "../../workflow/types";
import { AssetPicker } from "../common/AssetPicker";
import {
  CollapsibleGroup,
  FieldRow,
  InlineError,
  NumberField,
  SelectField,
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
          max={4}
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
  const position = isPlainObject(params.position) ? params.position : {};
  const resistance = isPlainObject(params.resistance) ? params.resistance : {};
  function updatePosition(axis: "x" | "y" | "z", value: number) {
    onChange({ ...params, position: { ...position, [axis]: value } });
  }
  function updateResistance(key: string, value: number) {
    onChange({ ...params, resistance: { ...resistance, [key]: value } });
  }
  return (
    <div className="node-editor">
      <FieldRow label="索引" error={firstError(fieldErrors, "index")}>
        <NumberField
          value={asNumber(params.index)}
          min={0}
          onChange={(value) => onChange({ ...params, index: value ?? 0 })}
        />
      </FieldRow>
      <FieldRow label="目标名称" error={firstError(fieldErrors, "label")}>
        <TextField
          value={asString(params.label) ?? "遗迹守卫"}
          onChange={(value) => onChange({ ...params, label: value })}
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
      <div className="node-editor-group">
        <span className="node-editor-group-title">位置</span>
        <div className="target-position-row">
          {POSITION_AXES.map((axis) => (
            <div key={axis.key} className="target-position-axis">
              <div className="target-position-field">
                <span className="target-position-label">{axis.label}</span>
                <NumberField
                  value={asNumber(position[axis.key]) ?? axis.default}
                  onChange={(value) => updatePosition(axis.key, value ?? axis.default)}
                />
              </div>
              {firstError(fieldErrors, `position.${axis.key}`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `position.${axis.key}`)!} />
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="node-editor-group">
        <span className="node-editor-group-title">目标抗性</span>
        <div className="target-resistance-grid">
          {RESISTANCE_ELEMENT_KEYS.map((key) => (
            <div key={key} className="target-resistance-cell">
              <div
                className="target-resistance-field"
                style={
                  {
                    "--element-color": ELEMENT_COLORS[key] ?? "#64748b",
                  } as CSSProperties
                }
              >
                <span className="target-resistance-badge">
                  {ELEMENT_LABELS[key] ?? key}
                </span>
                <NumberField
                  value={asNumber(resistance[key]) ?? 10}
                  onChange={(value) => updateResistance(key, value ?? 10)}
                />
              </div>
              {firstError(fieldErrors, `resistance.${key}`) !== undefined && (
                <InlineError message={firstError(fieldErrors, `resistance.${key}`)!} />
              )}
            </div>
          ))}
        </div>
      </div>
      {firstError(fieldErrors, "path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "path")!} />
      )}
    </div>
  );
}

const POSITION_AXES = [
  { key: "x", label: "X", default: 0 },
  { key: "y", label: "Y", default: 0 },
  { key: "z", label: "Z", default: 5 },
] as const;

export function InputTraceEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const items = useMemo(
    () => (Array.isArray(node.params.items) ? (node.params.items as TraceEventItem[]) : []),
    [node.params.items],
  );
  const blocks = useMemo(() => buildBlocks(items), [items]);
  const [gesture, setGesture] = useState<TraceGesture | null>(null);
  const [pendingBlock, setPendingBlock] = useState<TraceBlock | null>(null);
  const [deleteHint, setDeleteHint] = useState<{ x: number; y: number } | null>(null);
  const [paletteDrag, setPaletteDrag] = useState<PaletteDrag | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const visibleBlocks = useMemo(() => {
    let result = blocks;
    if (gesture !== null) {
      result = result.map((block) =>
        block.id === gesture.blockId
          ? { ...block, press: gesture.press, release: gesture.release }
          : block,
      );
    }
    if (pendingBlock !== null) {
      result = result.map((block) =>
        block.id === pendingBlock.id
          ? { ...block, press: pendingBlock.press, release: pendingBlock.release }
          : block,
      );
    }
    return result;
  }, [blocks, gesture, pendingBlock]);

  const layout = useMemo(() => layoutBlocks(visibleBlocks), [visibleBlocks]);
  const maxFrame = useMemo(() => {
    const last = blocks.reduce((max, block) => Math.max(max, block.release ?? block.press), 0);
    return Math.max(MIN_TIMELINE_FRAMES, last + TIMELINE_TAIL_FRAMES);
  }, [blocks]);
  const timelineWidth = Math.ceil(maxFrame * PX_PER_FRAME) + 24;
  const timelineHeight = RULER_HEIGHT + Math.max(1, layout.rows) * TRACK_HEIGHT;
  const unclosedCount = blocks.filter((block) => block.release === null).length;
  const unsupportedKeys = useMemo(() => {
    const result = new Set<string>();
    for (const block of blocks) {
      if (inputKeyDef(block.key) === null) {
        result.add(block.key);
      }
    }
    return result;
  }, [blocks]);
  const totalFrames = blocks.reduce(
    (max, block) => Math.max(max, block.release ?? block.press),
    0,
  );
  const ghost =
    paletteDrag === null
      ? null
      : computeGhostPlacement(paletteDrag, blocks);
  if (pendingBlock !== null) {
    const committed = blocks.find(
      (block) =>
        block.key === pendingBlock.key &&
        block.press === pendingBlock.press &&
        block.release === pendingBlock.release,
    );
    if (committed !== undefined) {
      setPendingBlock(null);
    }
  }

  function commitBlocks(next: TraceBlock[]) {
    onChange({ ...node.params, items: blocksToItems(next) });
  }

  function createBlock(key: string, frame: number) {
    const press = snapFrame(frame);
    const created: TraceBlock = {
      id: `${key}:${press}:${blocks.length}`,
      key,
      press,
      release: press + DEFAULT_TAP_FRAMES,
    };
    if (overlapsSameKey(created, blocks)) {
      return;
    }
    commitBlocks([...blocks, created]);
  }

  function startPaletteDrag(
    event: React.PointerEvent<HTMLElement>,
    key: string,
  ) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const timeline = timelineRef.current;
    if (timeline === null) {
      return;
    }
    const rect = timeline.getBoundingClientRect();
    const zoom = rect.width / timelineWidth;
    setPaletteDrag({
      key,
      x: event.clientX,
      y: event.clientY,
      zoom,
      rect: {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      },
    });
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function movePaletteDrag(event: React.PointerEvent<HTMLElement>) {
    if (paletteDrag === null) {
      return;
    }
    setPaletteDrag({ ...paletteDrag, x: event.clientX, y: event.clientY });
  }

  function endPaletteDrag(event: React.PointerEvent<HTMLElement>) {
    if (paletteDrag === null) {
      return;
    }
    const drag = paletteDrag;
    setPaletteDrag(null);
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    const rect = drag.rect;
    if (rect.width === 0 && rect.height === 0) {
      return;
    }
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    ) {
      return;
    }
    const frame = Math.min(
      TRACE_MAX_FRAME,
      Math.max(1, Math.round((event.clientX - rect.left) / (PX_PER_FRAME * drag.zoom))),
    );
    createBlock(drag.key, frame);
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
      open: block.release === null,
      startX: event.clientX,
      startPress: block.press,
      startRelease,
      press: block.press,
      release: startRelease,
    });
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function moveGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture === null) {
      return;
    }
    const block = visibleBlocks.find((item) => item.id === gesture.blockId);
    if (block === undefined) {
      return;
    }
    const timeline = timelineRef.current;
    const zoom =
      timeline === null ? 1 : timeline.getBoundingClientRect().width / timelineWidth;
    const deltaFrames = Math.round(
      (event.clientX - gesture.startX) / (PX_PER_FRAME * zoom),
    );
    if (timeline !== null) {
      const rect = timeline.getBoundingClientRect();
      const inside =
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom;
      setDeleteHint(inside ? null : { x: event.clientX, y: event.clientY });
    }
    if (gesture.mode === "move") {
      if (gesture.open) {
        const press = snapFrame(
          clampTracePress(block, gesture.startPress + deltaFrames, null, blocks),
        );
        setGesture({ ...gesture, press, release: press });
      } else {
        const duration = Math.max(
          SNAP_FRAMES,
          snapFrame(gesture.startRelease) - snapFrame(gesture.startPress),
        );
        const press = snapFrame(
          clampMovePress(block, gesture.startPress + deltaFrames, duration, blocks),
        );
        setGesture({ ...gesture, press, release: press + duration });
      }
    } else if (gesture.mode === "resize-left") {
      const release = gesture.open ? null : gesture.startRelease;
      const press = snapFrame(
        clampTracePress(block, gesture.startPress + deltaFrames, release, blocks),
      );
      setGesture({ ...gesture, press, release: release ?? press });
    } else {
      const release = snapFrame(
        clampTraceRelease(block, gesture.press, gesture.startRelease + deltaFrames, blocks),
      );
      setGesture({ ...gesture, release });
    }
  }

  function endGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture === null) {
      return;
    }
    const final = { ...gesture };
    setGesture(null);
    setDeleteHint(null);
    const timeline = timelineRef.current;
    if (timeline !== null) {
      const rect = timeline.getBoundingClientRect();
      const outside =
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom;
      if (outside) {
        commitBlocks(blocks.filter((block) => block.id !== final.blockId));
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        return;
      }
    }
    const release =
      final.open && final.mode !== "resize-right"
        ? null
        : Math.max(final.release, final.press + SNAP_FRAMES);
    const nextBlocks = blocks.map((block) =>
      block.id === final.blockId
        ? { ...block, press: final.press, release }
        : block,
    );
    commitBlocks(nextBlocks);
    const nextBlock = nextBlocks.find((block) => block.id === final.blockId);
    if (nextBlock !== undefined) {
      setPendingBlock(nextBlock);
    }
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }

  return (
    <div className="node-editor">
      <div className="trace-toolbar">
        <span className="trace-toolbar-label">拖拽按键到时间轴</span>
        <div className="trace-palette">
          {INPUT_KEY_DEFS.map((def) => (
            <span
              key={def.key}
              className="trace-palette-chip nodrag nowheel"
              style={{ "--key-color": def.color } as CSSProperties}
              title={`${def.cap} · ${def.label}`}
              onPointerDown={(event) => startPaletteDrag(event, def.key)}
              onPointerMove={movePaletteDrag}
              onPointerUp={endPaletteDrag}
              onPointerCancel={() => setPaletteDrag(null)}
            >
              <span className="trace-block-cap">{def.cap}</span>
            </span>
          ))}
        </div>
      </div>
      <div
        ref={timelineRef}
        className="trace-timeline nodrag nowheel"
        style={{ width: timelineWidth, height: timelineHeight }}
      >
        <div className="trace-ruler">
          {Array.from({ length: Math.floor(maxFrame / FRAMES_PER_SECOND) + 1 }, (_, index) => {
            const frame = index * FRAMES_PER_SECOND;
            return (
              <span
                className="trace-tick trace-tick-major"
                key={`major-${frame}`}
                style={{ left: frame * PX_PER_FRAME }}
              >
                {Math.round(frame / FRAMES_PER_SECOND)}s
              </span>
            );
          })}
          {Array.from({ length: Math.floor(maxFrame / RULER_MINOR_FRAMES) + 1 }, (_, index) => {
            const frame = index * RULER_MINOR_FRAMES;
            if (frame % FRAMES_PER_SECOND === 0) {
              return null;
            }
            return (
              <span
                className="trace-tick trace-tick-minor"
                key={`minor-${frame}`}
                style={{ left: frame * PX_PER_FRAME }}
              />
            );
          })}
        </div>
        {Array.from({ length: Math.max(1, layout.rows) }, (_, row) => (
          <div className="trace-row" key={row} />
        ))}
        {visibleBlocks.map((block) => {
          const def = inputKeyDef(block.key);
          const row = layout.rowById.get(block.id) ?? 0;
          const duration = Math.max(1, (block.release ?? block.press) - block.press);
          const width = Math.max(1, duration * PX_PER_FRAME);
          const showChip = width >= MIN_BLOCK_TEXT_PX;
          return (
            <div
              key={block.id}
              className={`trace-block ${block.release === null || block.invalid ? "trace-block-unclosed" : ""} ${def === null ? "trace-block-unsupported" : ""}`}
              style={{
                left: roundPx(block.press * PX_PER_FRAME),
                top: roundPx(RULER_HEIGHT + row * TRACK_HEIGHT + 5),
                width: roundPx(width),
                "--key-color": def?.color ?? "#64748b",
              } as CSSProperties}
              title={`${def?.label ?? block.key} ${formatTraceSeconds(block.press)} → ${block.release === null ? "未松开" : formatTraceSeconds(block.release)}（${block.press}–${block.release ?? "?"} 帧）`}
      onPointerDown={(event) => startGesture(event, block, "move")}
      onPointerMove={moveGesture}
      onPointerUp={endGesture}
      onPointerCancel={() => {
        setGesture(null);
        setDeleteHint(null);
      }}
            >
              {showChip && (
                <span className="trace-block-chip">
                  <span className="trace-block-cap">{def?.cap ?? "?"}</span>
                </span>
              )}
              <span
                className="trace-block-handle trace-block-handle-left"
                onPointerDown={(event) => startGesture(event, block, "resize-left")}
              />
              <span
                className="trace-block-handle trace-block-handle-right"
                onPointerDown={(event) => startGesture(event, block, "resize-right")}
              />
            </div>
          );
        })}
        {visibleBlocks.length === 0 && (
          <p className="trace-empty">从上方拖拽按键到时间轴</p>
        )}
      {ghost !== null && (
        <span
          className={`trace-drag-ghost ${ghost.blocked ? "trace-drag-ghost-blocked" : ""}`}
            style={
              {
                left: ghost.left,
                top: ghost.top,
                width: ghost.width,
                "--key-color": ghost.color,
              } as CSSProperties
            }
          >
          {ghost.cap}
        </span>
      )}
      </div>
      {deleteHint !== null &&
        createPortal(
          <span
            className="trace-delete-ghost"
            style={{ left: deleteHint.x, top: deleteHint.y }}
          >
            × 删除
          </span>,
          document.body,
        )}
      <div className="trace-summary">
        <span>{visibleBlocks.length} 个操作</span>
        <span>总长 {formatTraceSeconds(totalFrames)}</span>
        <span>同时最多 {layout.rows} 层</span>
        {unclosedCount > 0 && (
          <span className="trace-summary-warning">{unclosedCount} 个未闭合按键</span>
        )}
        {unsupportedKeys.size > 0 && (
          <span className="trace-summary-warning">{unsupportedKeys.size} 个不支持按键</span>
        )}
      </div>
      {firstError(fieldErrors, "items") !== undefined && (
        <InlineError message={firstError(fieldErrors, "items")!} />
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
  open: boolean;
  startX: number;
  startPress: number;
  startRelease: number;
  press: number;
  release: number;
}

interface TraceRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

interface PaletteDrag {
  key: string;
  x: number;
  y: number;
  zoom: number;
  rect: TraceRect;
}

const TRACE_MAX_FRAME = 100000;
const FRAMES_PER_SECOND = 60;
const SNAP_FRAMES = 1; // 编辑精度：1 帧
const RULER_MINOR_FRAMES = 6; // 标尺次刻度：0.1 秒
const DEFAULT_TAP_FRAMES = 15; // 0.25 秒
const PX_PER_FRAME = 1.6; // 96px / 秒
const RULER_HEIGHT = 18;
const TRACK_HEIGHT = 36;
const MIN_TIMELINE_FRAMES = 360; // 6 秒
const TIMELINE_TAIL_FRAMES = 30; // 尾部留白 0.5 秒
const MIN_BLOCK_TEXT_PX = 20;

function compareTraceBlocks(a: TraceBlock, b: TraceBlock): number {
  return (
    a.press - b.press ||
    (a.key < b.key ? -1 : a.key > b.key ? 1 : 0) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

function layoutBlocks(blocks: TraceBlock[]): {
  rows: number;
  rowById: Map<string, number>;
} {
  const sorted = [...blocks].sort(compareTraceBlocks);
  const trackEnds: number[] = [];
  const rowById = new Map<string, number>();
  sorted.forEach((block) => {
    const start = block.press;
    const end = block.release ?? block.press;
    let row = trackEnds.findIndex((lastEnd) => lastEnd <= start);
    if (row === -1) {
      row = trackEnds.length;
      trackEnds.push(end);
    } else {
      trackEnds[row] = end;
    }
    rowById.set(block.id, row);
  });
  return { rows: trackEnds.length, rowById };
}

function sameKeyBounds(
  block: TraceBlock,
  blocks: TraceBlock[],
): { prevEnd: number; nextStart: number } {
  const siblings = blocks
    .filter((item) => item.key === block.key && item.id !== block.id)
    .sort(compareTraceBlocks);
  let prevEnd = 0;
  let nextStart = TRACE_MAX_FRAME + 1;
  for (const sibling of siblings) {
    if (compareTraceBlocks(sibling, block) < 0) {
      prevEnd = Math.max(prevEnd, sibling.release ?? sibling.press);
    } else {
      nextStart = Math.min(nextStart, sibling.press);
    }
  }
  return { prevEnd, nextStart };
}

function clampTracePress(
  block: TraceBlock,
  press: number,
  release: number | null,
  blocks: TraceBlock[],
): number {
  const { prevEnd, nextStart } = sameKeyBounds(block, blocks);
  const upper =
    release === null ? nextStart - 1 : Math.min(release - SNAP_FRAMES, nextStart - 1);
  return Math.max(1, prevEnd + 1, Math.min(press, upper));
}

function clampTraceRelease(
  block: TraceBlock,
  press: number,
  release: number,
  blocks: TraceBlock[],
): number {
  const { nextStart } = sameKeyBounds(block, blocks);
  return Math.max(press + SNAP_FRAMES, Math.min(release, nextStart - 1));
}

function clampMovePress(
  block: TraceBlock,
  targetPress: number,
  duration: number,
  blocks: TraceBlock[],
): number {
  const siblings = blocks
    .filter((item) => item.key === block.key && item.id !== block.id)
    .sort(compareTraceBlocks);
  let cursor = 1;
  let bestStart = 1;
  let bestEnd = TRACE_MAX_FRAME;
  let bestDist = Number.POSITIVE_INFINITY;
  const consider = (start: number, end: number) => {
    const fitEnd = end - duration + 1;
    if (fitEnd < start) {
      return;
    }
    const dist =
      targetPress < start ? start - targetPress : targetPress > fitEnd ? targetPress - fitEnd : 0;
    if (dist < bestDist) {
      bestDist = dist;
      bestStart = start;
      bestEnd = fitEnd;
    }
  };
  for (const sibling of siblings) {
    consider(cursor, sibling.press - 1);
    cursor = Math.max(cursor, (sibling.release ?? sibling.press) + 1);
  }
  consider(cursor, TRACE_MAX_FRAME);
  if (!Number.isFinite(bestDist)) {
    return Math.max(1, Math.min(targetPress, TRACE_MAX_FRAME - duration + 1));
  }
  return Math.max(bestStart, Math.min(targetPress, bestEnd));
}

function overlapsSameKey(created: TraceBlock, blocks: TraceBlock[]): boolean {
  const release = created.release ?? created.press;
  return blocks.some(
    (block) =>
      block.key === created.key &&
      created.press < (block.release ?? block.press) &&
      block.press < release,
  );
}

function formatTraceSeconds(frames: number): string {
  return `${(frames / FRAMES_PER_SECOND).toFixed(1)}s`;
}

function snapFrame(frame: number): number {
  return Math.max(1, Math.round(frame / SNAP_FRAMES) * SNAP_FRAMES);
}

function roundPx(value: number): number {
  return Math.round(value * 10) / 10;
}

function computeGhostPlacement(
  drag: PaletteDrag,
  blocks: TraceBlock[],
): {
  left: number;
  top: number;
  width: number;
  blocked: boolean;
  cap: string;
  color: string;
} | null {
  const rect = drag.rect;
  if (rect.width === 0 && rect.height === 0) {
    return null;
  }
  if (
    drag.x < rect.left ||
    drag.x > rect.right ||
    drag.y < rect.top ||
    drag.y > rect.bottom
  ) {
    return null;
  }
  const frame = Math.min(
    TRACE_MAX_FRAME,
    Math.max(1, Math.round((drag.x - rect.left) / (PX_PER_FRAME * drag.zoom))),
  );
  const press = snapFrame(frame);
  const virtual: TraceBlock = {
    id: "ghost",
    key: drag.key,
    press,
    release: press + DEFAULT_TAP_FRAMES,
  };
  const layout = layoutBlocks([...blocks, virtual]);
  const row = layout.rowById.get("ghost") ?? 0;
  const def = inputKeyDef(drag.key);
  return {
    left: roundPx(press * PX_PER_FRAME),
    top: roundPx(RULER_HEIGHT + row * TRACK_HEIGHT + 5),
    width: roundPx(Math.max(1, DEFAULT_TAP_FRAMES * PX_PER_FRAME)),
    blocked: overlapsSameKey(virtual, blocks),
    cap: def?.cap ?? "?",
    color: def?.color ?? "#1d4ed8",
  };
}

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
  const sorted = [...blocks].sort(compareTraceBlocks);
  const byFrame = new Map<number, Array<{ key: string; phase: "press" | "release" }>>();
  for (const block of sorted) {
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
