import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import { Timeline } from "vis-timeline/standalone";
import type { TimelineItem, TimelineOptions } from "vis-timeline/standalone";
import "vis-timeline/styles/vis-timeline-graph2d.css";
import type { TraceBlock, TraceViewport } from "./traceModel";
import {
  FRAME_EPOCH,
  MAX_TIMELINE_HEIGHT,
  MIN_TIMELINE_FRAMES,
  MIN_TIMELINE_HEIGHT,
  SNAP_FRAMES,
  TIMELINE_TAIL_FRAMES,
  TRACE_MAX_FRAME,
  blockToTimelineItem,
  clampBlockEdit,
  dateToFrame,
  frameFromViewport,
  frameToDate,
  frameToMs,
  formatSecondsLabel,
  layoutBlocks,
  maxFrameOf,
  msToFrame,
  toTimeMs,
  timelineItemToBlock,
} from "./traceModel";

type TraceTimelineItem = Omit<TimelineItem, "content"> & {
  content: string;
  key: string;
  cap: string;
};

export interface TraceTimelineHandle {
  frameFromClientX(clientX: number): number | null;
  getViewport(): TraceViewport | null;
  isInside(clientX: number, clientY: number): boolean;
}

export interface TraceTimelineProps {
  blocks: TraceBlock[];
  onCommitBlocks: (blocks: TraceBlock[]) => void;
  onViewportChange?: (viewport: TraceViewport) => void;
}

const MIN_ZOOM_MS = 500;
const MAX_ZOOM_MS = frameToMs(TRACE_MAX_FRAME + TIMELINE_TAIL_FRAMES);
const TRACK_HEIGHT_OPTION = 38;

function toTimelineItem(block: TraceBlock): TraceTimelineItem {
  const data = blockToTimelineItem(block);
  return { ...data, type: "range" } as TraceTimelineItem;
}

function timelineHeightFor(blocks: TraceBlock[]): number {
  const rows = layoutBlocks(blocks).rows;
  return Math.max(MIN_TIMELINE_HEIGHT, Math.min(MAX_TIMELINE_HEIGHT, 46 + rows * TRACK_HEIGHT_OPTION));
}

function traceLabelFor(value: unknown): string {
  const ms = toTimeMs(value);
  return ms === null ? "" : formatSecondsLabel((ms - FRAME_EPOCH) / 1000);
}

export const TraceTimeline = forwardRef<TraceTimelineHandle, TraceTimelineProps>(
  function TraceTimeline({ blocks, onCommitBlocks, onViewportChange }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const timelineRef = useRef<Timeline | null>(null);
    const blocksRef = useRef<TraceBlock[]>(blocks);
    const viewportRef = useRef<{ startFrame: number; endFrame: number } | null>(null);
    const onCommitRef = useRef(onCommitBlocks);
    const onViewportChangeRef = useRef(onViewportChange);

    useEffect(() => {
      onCommitRef.current = onCommitBlocks;
      onViewportChangeRef.current = onViewportChange;
    }, [onCommitBlocks, onViewportChange]);

    const publishViewport = useCallback((timeline: Timeline) => {
      const window = timeline.getWindow();
      const next = {
        startFrame: dateToFrame(window.start),
        endFrame: dateToFrame(window.end),
      };
      viewportRef.current = next;
      const container = containerRef.current;
      if (container !== null) {
        const rect = container.getBoundingClientRect();
        onViewportChangeRef.current?.({
          ...next,
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
        });
      }
    }, []);

    const clampTimelineItem = useCallback((item: TimelineItem): TimelineItem => {
      const id = String(item.id);
      const prev = blocksRef.current.find((block) => block.id === id);
      if (prev === undefined) {
        return item;
      }
      const startMs = toTimeMs(item.start);
      const endMs = toTimeMs(item.end);
      if (startMs === null) {
        return item;
      }
      const press = msToFrame(startMs);
      const release =
        endMs === null ? null : Math.max(press + SNAP_FRAMES, msToFrame(endMs));
      const clamped = clampBlockEdit(prev, press, release, blocksRef.current);
      return {
        ...item,
        start: frameToDate(clamped.press),
        end: frameToDate(clamped.release ?? clamped.press + SNAP_FRAMES),
      };
    }, []);

    const commitFromTimelineItem = useCallback((item: TimelineItem) => {
      const previous = blocksRef.current;
      const previousById = new Map(previous.map((block) => [block.id, block]));
      const nextBlock = timelineItemToBlock(item, previousById);
      if (nextBlock !== null) {
        onCommitRef.current(
          previous.map((block) => (block.id === nextBlock.id ? nextBlock : block)),
        );
      }
    }, []);

    useEffect(() => {
      const container = containerRef.current;
      if (container === null) {
        return;
      }
      const initial = blocksRef.current.map(toTimelineItem);
      const height = timelineHeightFor(blocksRef.current);
      const options: TimelineOptions = {
        width: "100%",
        height,
        minHeight: MIN_TIMELINE_HEIGHT,
        maxHeight: MAX_TIMELINE_HEIGHT,
        editable: {
          add: false,
          remove: true,
          updateTime: true,
          updateGroup: false,
        },
        selectable: true,
        multiselect: false,
        stack: true,
        horizontalScroll: true,
        verticalScroll: true,
        zoomable: true,
        moveable: true,
        zoomMin: MIN_ZOOM_MS,
        zoomMax: MAX_ZOOM_MS,
        min: frameToMs(1),
        max: frameToMs(TRACE_MAX_FRAME + TIMELINE_TAIL_FRAMES),
        showCurrentTime: false,
        showMajorLabels: true,
        showMinorLabels: true,
        orientation: { axis: "top", item: "top" },
        margin: { axis: 8, item: { horizontal: 6, vertical: 4 } },
        maxMinorChars: 10,
        snap: (date: Date) => {
          const ms = toTimeMs(date);
          if (ms === null) {
            return date;
          }
          return frameToMs(msToFrame(ms));
        },
        format: {
          minorLabels: (date: Date) => traceLabelFor(date),
          majorLabels: (date: Date) => traceLabelFor(date),
        },
        tooltip: {
          followMouse: true,
          delay: 200,
        },
        onMoving: (item, callback) => {
          callback(clampTimelineItem(item));
        },
        onMove: (item, callback) => {
          const next = clampTimelineItem(item);
          callback(next);
          commitFromTimelineItem(next);
        },
        onRemove: (item, callback) => {
          callback(null);
          const id = String(item.id);
          onCommitRef.current(blocksRef.current.filter((block) => block.id !== id));
        },
      };

      const timeline = new Timeline(container, initial, options);
      timelineRef.current = timeline;

      const handleRangeChange = (properties: { start: Date; end: Date }) => {
        viewportRef.current = {
          startFrame: dateToFrame(properties.start),
          endFrame: dateToFrame(properties.end),
        };
        publishViewport(timeline);
      };
      timeline.on("rangechange", handleRangeChange);
      timeline.on("rangechanged", handleRangeChange);

      const endMs = frameToMs(
        Math.max(
          MIN_TIMELINE_FRAMES,
          maxFrameOf(blocksRef.current) + TIMELINE_TAIL_FRAMES,
        ),
      );
      timeline.setWindow(frameToMs(1), endMs, { animation: false });
      publishViewport(timeline);

      return () => {
        timeline.destroy();
        timelineRef.current = null;
      };
    }, [clampTimelineItem, commitFromTimelineItem, publishViewport]);

    useEffect(() => {
      blocksRef.current = blocks;
      const timeline = timelineRef.current;
      if (timeline === null) {
        return;
      }
      timeline.setItems(blocks.map(toTimelineItem));
      timeline.setOptions({ height: timelineHeightFor(blocks) });
    }, [blocks, publishViewport]);

    useImperativeHandle(
      ref,
      () => ({
        frameFromClientX(clientX: number): number | null {
          const container = containerRef.current;
          const viewport = viewportRef.current;
          if (container === null || viewport === null) {
            return null;
          }
          const rect = container.getBoundingClientRect();
          return frameFromViewport(
            {
              ...viewport,
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height,
            },
            clientX,
          );
        },
        getViewport(): TraceViewport | null {
          const container = containerRef.current;
          const viewport = viewportRef.current;
          if (container === null || viewport === null) {
            return null;
          }
          const rect = container.getBoundingClientRect();
          return {
            ...viewport,
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
          };
        },
        isInside(clientX: number, clientY: number): boolean {
          const container = containerRef.current;
          if (container === null) {
            return false;
          }
          const rect = container.getBoundingClientRect();
          return (
            clientX >= rect.left &&
            clientX <= rect.right &&
            clientY >= rect.top &&
            clientY <= rect.bottom
          );
        },
      }),
      [],
    );

    return <div ref={containerRef} className="trace-timeline nodrag nowheel" />;
  },
);
