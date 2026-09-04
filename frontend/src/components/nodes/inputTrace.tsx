import { useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { INPUT_KEY_DEFS, inputKeyDef } from "../../workflow/inputKeys";
import { InlineError } from "../common/fields";
import type { NodeEditorProps } from "./common";
import { firstError } from "./common";
import type { TraceBlock, TraceEventItem, TraceViewport } from "./traceModel";
import {
  DEFAULT_TAP_FRAMES,
  MIN_TIMELINE_FRAMES,
  TIMELINE_TAIL_FRAMES,
  buildBlocks,
  blocksToItems,
  computeGhostPlacement,
  formatTraceSeconds,
  frameFromViewport,
  layoutBlocks,
  maxFrameOf,
  overlapsSameKey,
  snapFrame,
} from "./traceModel";
import { TraceTimeline } from "./traceTimeline";
import type { TraceTimelineHandle } from "./traceTimeline";

interface PaletteDrag {
  key: string;
  x: number;
  y: number;
  viewport: TraceViewport | null;
}

export function InputTraceEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const items = useMemo(
    () => (Array.isArray(node.params.items) ? (node.params.items as TraceEventItem[]) : []),
    [node.params.items],
  );
  const blocks = useMemo(() => buildBlocks(items), [items]);
  const layout = useMemo(() => layoutBlocks(blocks), [blocks]);
  const timelineRef = useRef<TraceTimelineHandle>(null);
  const [paletteDrag, setPaletteDrag] = useState<PaletteDrag | null>(null);

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
  const totalFrames = maxFrameOf(blocks);
  const maxFrame = Math.max(MIN_TIMELINE_FRAMES, totalFrames + TIMELINE_TAIL_FRAMES);
  const ghost =
    paletteDrag === null
      ? null
      : computeGhostPlacement(paletteDrag, blocks, paletteDrag.viewport);

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
    setPaletteDrag({
      key,
      x: event.clientX,
      y: event.clientY,
      viewport: timelineRef.current?.getViewport() ?? null,
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
    if (drag.viewport === null) {
      return;
    }
    if (
      event.clientY < drag.viewport.top ||
      event.clientY > drag.viewport.top + drag.viewport.height
    ) {
      return;
    }
    const frame = frameFromViewport(drag.viewport, event.clientX);
    if (frame === null) {
      return;
    }
    createBlock(drag.key, frame);
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
      <div className="trace-timeline-wrap">
        <TraceTimeline
          ref={timelineRef}
          blocks={blocks}
          onCommitBlocks={commitBlocks}
        />
        {blocks.length === 0 && (
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
      <div className="trace-summary">
        <span>{blocks.length} 个操作</span>
        <span>总长 {formatTraceSeconds(totalFrames)}</span>
        <span>同时最多 {layout.rows} 层</span>
        <span>窗口 {formatTraceSeconds(maxFrame)}</span>
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
