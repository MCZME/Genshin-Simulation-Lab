import { inputKeyDef } from "../../workflow/inputKeys";

export interface TraceEventItem {
  frame: number;
  events: Array<{ key: string; phase: "press" | "release" }>;
}

export interface TraceBlock {
  id: string;
  key: string;
  press: number;
  release: number | null;
  invalid?: boolean;
}

export interface TraceViewport {
  startFrame: number;
  endFrame: number;
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface TraceTimelineItemData {
  id: string;
  key: string;
  start: number;
  end: number;
  content: string;
  className: string;
  style: string;
  title: string;
  cap: string;
}

export interface TraceTimelineItemSnapshot {
  id: string;
  start: number;
  end: number;
  className: string;
  style: string;
}

export interface TraceGhostPlacement {
  left: number;
  top: number;
  width: number;
  blocked: boolean;
  cap: string;
  color: string;
}

export const TRACE_MAX_FRAME = 100000;
export const FRAMES_PER_SECOND = 60;
export const SNAP_FRAMES = 1;
export const DEFAULT_TAP_FRAMES = 15;
export const MIN_TIMELINE_FRAMES = 360;
export const TIMELINE_TAIL_FRAMES = 30;

/** 1 帧映射为 1000/60 毫秒，时间轴刻度步长恰好对应 0.1s/0.5s/1s/5s… */
export const FRAME_MS = 1000 / FRAMES_PER_SECOND;
export const FRAME_EPOCH = 0;

export const RULER_HEIGHT = 28;
export const TRACK_HEIGHT = 38;
export const MIN_TIMELINE_HEIGHT = 120;
export const MAX_TIMELINE_HEIGHT = 360;

export function frameToMs(frame: number): number {
  return FRAME_EPOCH + frame * FRAME_MS;
}

export function frameToDate(frame: number): Date {
  return new Date(frameToMs(frame));
}

export function msToFrame(ms: number): number {
  return Math.max(1, Math.round((ms - FRAME_EPOCH) / FRAME_MS));
}

export function dateToFrame(value: unknown): number {
  const ms = toTimeMs(value);
  return ms === null ? 1 : msToFrame(ms);
}

export function snapFrame(frame: number): number {
  return Math.max(1, Math.round(frame / SNAP_FRAMES) * SNAP_FRAMES);
}

export function compareTraceBlocks(a: TraceBlock, b: TraceBlock): number {
  return (
    a.press - b.press ||
    (a.key < b.key ? -1 : a.key > b.key ? 1 : 0) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

export function buildBlocks(items: TraceEventItem[]): TraceBlock[] {
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

export function blocksToItems(blocks: TraceBlock[]): TraceEventItem[] {
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

export function layoutBlocks(blocks: TraceBlock[]): {
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

export function maxFrameOf(blocks: TraceBlock[]): number {
  return blocks.reduce((max, block) => Math.max(max, block.release ?? block.press), 0);
}

export function formatTraceSeconds(frames: number): string {
  return `${(frames / FRAMES_PER_SECOND).toFixed(1)}s`;
}

export function formatSecondsLabel(seconds: number): string {
  const rounded = Math.round(seconds * 10) / 10;
  if (rounded < 60) {
    return `${rounded}s`;
  }
  const minutes = Math.floor(rounded / 60);
  const rest = Math.round((rounded - minutes * 60) * 10) / 10;
  return rest === 0 ? `${minutes}m` : `${minutes}m${rest}s`;
}

export function sameKeyBounds(
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

export function clampTracePress(
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

export function clampTraceRelease(
  block: TraceBlock,
  press: number,
  release: number,
  blocks: TraceBlock[],
): number {
  const { nextStart } = sameKeyBounds(block, blocks);
  return Math.max(press + SNAP_FRAMES, Math.min(release, nextStart - 1));
}

export function clampMovePress(
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

/**
 * 根据时间轴编辑产生的 press/release 帧号，把块钳制到合法位置。
 * open 块在时间轴中以 press+1 帧的最小宽度呈现，因此需要区分
 * 「整体移动」「左端调整（保持 open）」和「右端拉长（转为 closed）」。
 */
export function clampBlockEdit(
  prev: TraceBlock,
  press: number,
  release: number | null,
  blocks: TraceBlock[],
): TraceBlock {
  const others = blocks.filter((block) => block.id !== prev.id);
  if (prev.release === null) {
    const prevOpenEndFrame = prev.press + SNAP_FRAMES;
    const deltaStart = press - prev.press;
    const deltaEnd = release === null ? null : release - prevOpenEndFrame;
    const moving = deltaEnd !== null && deltaEnd === deltaStart;
    const resizingLeft =
      !moving && press !== prev.press && (deltaEnd === null || deltaEnd === 0);
    if (moving || resizingLeft) {
      const nextPress = clampTracePress(prev, press, null, others);
      return { ...prev, press: nextPress, release: null };
    }
    const nextRelease = clampTraceRelease(
      { ...prev, release },
      press,
      release ?? press + SNAP_FRAMES,
      others,
    );
    return {
      ...prev,
      press,
      release: Math.max(press + SNAP_FRAMES, nextRelease),
    };
  }

  const duration = prev.release - prev.press;
  const moving = release !== null && release - press === duration;
  if (moving) {
    const nextPress = clampMovePress(prev, press, duration, others);
    return { ...prev, press: nextPress, release: nextPress + duration };
  }
  if (press !== prev.press) {
    const nextPress = clampTracePress(prev, press, release, others);
    return {
      ...prev,
      press: nextPress,
      release: Math.max(nextPress + SNAP_FRAMES, release ?? nextPress + SNAP_FRAMES),
    };
  }
  const nextRelease = clampTraceRelease(
    prev,
    press,
    release ?? press + SNAP_FRAMES,
    others,
  );
  return { ...prev, press, release: Math.max(press + SNAP_FRAMES, nextRelease) };
}

export function overlapsSameKey(created: TraceBlock, blocks: TraceBlock[]): boolean {
  const release = created.release ?? created.press;
  return blocks.some(
    (block) =>
      block.key === created.key &&
      created.press < (block.release ?? block.press) &&
      block.press < release,
  );
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function blockToTimelineItem(block: TraceBlock): TraceTimelineItemData {
  const def = inputKeyDef(block.key);
  const cap = def?.cap ?? "?";
  const color = def?.color ?? "#64748b";
  const classes = ["trace-item"];
  if (block.release === null || block.invalid) {
    classes.push("trace-block-unclosed");
  }
  if (def === null) {
    classes.push("trace-block-unsupported");
  }
  return {
    id: block.id,
    key: block.key,
    start: frameToMs(block.press),
    end: frameToMs(Math.max(block.press + SNAP_FRAMES, block.release ?? block.press + SNAP_FRAMES)),
    content: `<span class="trace-block-cap">${cap}</span>`,
    className: classes.join(" "),
    style: `--key-color: ${color}; background: ${color}; border-color: ${color};`,
    title: `${def?.label ?? block.key} ${formatTraceSeconds(block.press)} → ${
      block.release === null ? "未松开" : formatTraceSeconds(block.release)
    }（${block.press}–${block.release ?? "?"} 帧）`,
    cap,
  };
}

export function toTimeMs(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.getTime();
  }
  if (value !== null && typeof value === "object") {
    const valueOf = (value as { valueOf?: unknown }).valueOf;
    if (typeof valueOf === "function") {
      const resolved = valueOf.call(value);
      if (typeof resolved === "number" && Number.isFinite(resolved)) {
        return resolved;
      }
      if (resolved instanceof Date && !Number.isNaN(resolved.getTime())) {
        return resolved.getTime();
      }
    }
  }
  return null;
}

export function timelineItemToBlock(
  raw: unknown,
  previousById: ReadonlyMap<string, TraceBlock>,
): TraceBlock | null {
  if (raw === null || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const id = typeof record.id === "string" || typeof record.id === "number" ? String(record.id) : "";
  const key = typeof record.key === "string" ? record.key : "";
  if (id === "" || key === "") {
    return null;
  }
  const startMs = toTimeMs(record.start);
  const endMs = record.end === null || record.end === undefined ? null : toTimeMs(record.end);
  if (startMs === null || (endMs !== null && endMs < startMs)) {
    return null;
  }
  const press = msToFrame(startMs);
  const release = endMs === null ? null : Math.max(press + SNAP_FRAMES, msToFrame(endMs));
  const prev = previousById.get(id);
  if (prev?.release === null && release !== null && release === press + SNAP_FRAMES) {
    // 未闭合块在时间轴中以最小宽度呈现；移动/左端调整后仍保持未闭合。
    return { id, key, press, release: null };
  }
  return { id, key, press, release };
}

export function sameTimelineItem(
  left: TraceTimelineItemSnapshot,
  right: TraceTimelineItemSnapshot,
): boolean {
  return (
    left.id === right.id &&
    left.start === right.start &&
    left.end === right.end &&
    left.className === right.className &&
    left.style === right.style
  );
}

export function frameFromViewport(viewport: TraceViewport, clientX: number): number | null {
  if (viewport.width <= 0 || viewport.endFrame <= viewport.startFrame) {
    return null;
  }
  const ratio = (clientX - viewport.left) / viewport.width;
  if (ratio < 0 || ratio > 1) {
    return null;
  }
  const frame = Math.round(viewport.startFrame + ratio * (viewport.endFrame - viewport.startFrame));
  return Math.min(TRACE_MAX_FRAME, Math.max(1, frame));
}

export function computeGhostPlacement(
  drag: { key: string; x: number; y: number },
  blocks: TraceBlock[],
  viewport: TraceViewport | null,
): TraceGhostPlacement | null {
  if (viewport === null) {
    return null;
  }
  if (
    drag.x < viewport.left ||
    drag.x > viewport.left + viewport.width ||
    drag.y < viewport.top ||
    drag.y > viewport.top + viewport.height
  ) {
    return null;
  }
  const frame = frameFromViewport(viewport, drag.x);
  if (frame === null) {
    return null;
  }
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
  const pxPerFrame = viewport.width / (viewport.endFrame - viewport.startFrame);
  return {
    left: (press - viewport.startFrame) * pxPerFrame,
    top: RULER_HEIGHT + row * TRACK_HEIGHT + 5,
    width: Math.max(1, DEFAULT_TAP_FRAMES * pxPerFrame),
    blocked: overlapsSameKey(virtual, blocks),
    cap: def?.cap ?? "?",
    color: def?.color ?? "#1d4ed8",
  };
}
