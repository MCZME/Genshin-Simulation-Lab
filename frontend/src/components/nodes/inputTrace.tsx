import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties } from "react";
import { INPUT_KEY_DEFS, inputKeyDef } from "../../workflow/inputKeys";
import { InlineError } from "../common/fields";
import type { NodeEditorProps } from "./common";
import { firstError } from "./common";
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
