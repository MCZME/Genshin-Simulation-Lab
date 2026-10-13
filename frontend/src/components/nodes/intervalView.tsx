/**
 * 区间图视图：vis-timeline 渲染「泳道 + 区间」。
 *
 * 纯渲染终端：只做列绑定与渲染，不折叠、不配对、不聚合；区间数据由上游算子构建。
 * 时间轴不随数据长度膨胀——节点宽度是手动画布几何，可视帧范围由节点内缩放决定。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Timeline } from "vis-timeline/standalone";
import type { TimelineItem, TimelineOptions } from "vis-timeline/standalone";
import "vis-timeline/styles/vis-timeline-graph2d.css";
import {
  computeAnalysisShapes,
  connectedConfigNode,
  defaultIntervalBinding,
  viewInputShape,
  type AnalysisTableResult,
} from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { useAnalysisSchemaCatalog } from "../analysis_context";
import { asString } from "./common";
import { useAssetNames } from "./useAssetNames";
import { MAX_RENDERED_ROWS, formatCell, type ViewFitInfo } from "./views";
import {
  MAX_VIEW_FIT_HEIGHT,
  MIN_VIEW_HEIGHT,
  MIN_VIEW_WIDTH,
  clamp,
} from "../../workflow/view_size";

/** 1 帧 = 1000/60 毫秒，与按键轨迹时间轴共用同一时间基准。 */
const MS_PER_FRAME = 1000 / 60;
/** 内容估算：每条堆叠行的目标高与图轴固定占用。 */
const LANE_ROW_HEIGHT = 26;
const INTERVAL_HEIGHT_EXTRAS = 48;
/** 可视跨度超过该帧数时，主刻度改用秒显示。 */
const SECONDS_AXIS_THRESHOLD = 600;

const COLOR_PALETTE = [
  "#378ADD",
  "#D85A30",
  "#1D9E75",
  "#BA7517",
  "#7F77DD",
  "#D4537E",
  "#639922",
  "#0F6E56",
];

export interface IntervalBinding {
  lane: string;
  start: string;
  /** 结束列；未绑定为 null，此时全部渲染为瞬时点。 */
  end: string | null;
  label: string | null;
  value: string | null;
  color: string | null;
  laneOrder: string | null;
}

export interface IntervalItemRecord {
  id: string;
  rowIndex: number;
  laneKey: string;
  start: number;
  /** 结束帧；null 或缺省/相等时渲染为瞬时点。 */
  end: number | null;
  label: string;
  value: number | null;
  colorKey: string | null;
}

export interface IntervalLane {
  key: string;
  label: string;
  order: number;
}

export interface IntervalData {
  lanes: IntervalLane[];
  items: IntervalItemRecord[];
  colorKeys: string[];
}

function toFrame(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value) : null;
}

function formatNumberValue(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return Number.isInteger(value)
    ? String(value)
    : value.toFixed(2).replace(/\.?0+$/, "");
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * 把绑定的表折叠成渲染所需的泳道与区间记录。
 * 必填列缺失或类型不符的行整行丢弃，不静默补值。
 */
export function buildIntervalData(
  table: AnalysisTableResult,
  binding: IntervalBinding,
  formatValue: (column: string, value: unknown) => string,
): IntervalData | null {
  const columnIndex = new Map(table.columns.map((column, index) => [column.name, index]));
  const typeOf = new Map(table.columns.map((column) => [column.name, column.type]));
  const laneIndex = columnIndex.get(binding.lane);
  const startIndex = columnIndex.get(binding.start);
  if (laneIndex === undefined || startIndex === undefined) {
    return null;
  }
  const startType = typeOf.get(binding.start);
  if (startType !== "int" && startType !== "float") {
    return null;
  }
  const optionalIndexes = {
    end: binding.end === null ? undefined : columnIndex.get(binding.end),
    label: binding.label === null ? undefined : columnIndex.get(binding.label),
    value: binding.value === null ? undefined : columnIndex.get(binding.value),
    color: binding.color === null ? undefined : columnIndex.get(binding.color),
    laneOrder: binding.laneOrder === null ? undefined : columnIndex.get(binding.laneOrder),
  };
  if (
    (binding.end !== null && optionalIndexes.end === undefined) ||
    (binding.label !== null && optionalIndexes.label === undefined) ||
    (binding.value !== null && optionalIndexes.value === undefined) ||
    (binding.color !== null && optionalIndexes.color === undefined) ||
    (binding.laneOrder !== null && optionalIndexes.laneOrder === undefined)
  ) {
    return null;
  }

  const lanes = new Map<string, IntervalLane>();
  const items: IntervalItemRecord[] = [];
  table.rows.forEach((row, rowIndex) => {
    const laneRaw = row[laneIndex];
    if (typeof laneRaw !== "string" || laneRaw === "") {
      return;
    }
    const start = toFrame(row[startIndex]);
    if (start === null) {
      return;
    }
    let end: number | null = null;
    if (optionalIndexes.end !== undefined) {
      const endRaw = row[optionalIndexes.end];
      if (endRaw !== null && endRaw !== undefined) {
        end = toFrame(endRaw);
        if (end === null) {
          return;
        }
      }
    }
    if (!lanes.has(laneRaw)) {
      let order = lanes.size;
      if (optionalIndexes.laneOrder !== undefined) {
        const orderRaw = toFrame(row[optionalIndexes.laneOrder]);
        if (orderRaw !== null) {
          order = orderRaw;
        }
      }
      lanes.set(laneRaw, {
        key: laneRaw,
        label: formatValue(binding.lane, laneRaw),
        order,
      });
    }
    const label =
      optionalIndexes.label === undefined
        ? ""
        : formatValue(binding.label ?? "", row[optionalIndexes.label]);
    const valueRaw = optionalIndexes.value === undefined ? null : row[optionalIndexes.value];
    const value =
      typeof valueRaw === "number" && Number.isFinite(valueRaw) ? valueRaw : null;
    let colorKey: string | null = null;
    if (optionalIndexes.color !== undefined) {
      const colorRaw = row[optionalIndexes.color];
      if (typeof colorRaw === "string" && colorRaw !== "") {
        colorKey = colorRaw;
      }
    }
    items.push({
      id: String(rowIndex),
      rowIndex,
      laneKey: laneRaw,
      start,
      end,
      label,
      value,
      colorKey,
    });
  });

  const orderedLanes = [...lanes.values()].sort(
    (left, right) => left.order - right.order || left.label.localeCompare(right.label, "zh-CN"),
  );
  const colorKeys = [
    ...new Set(items.map((item) => item.colorKey).filter((key): key is string => key !== null)),
  ].sort((left, right) => left.localeCompare(right, "zh-CN"));
  return { lanes: orderedLanes, items, colorKeys };
}

/** 单泳道内并发区间的堆叠层数：起点升序贪心分配到最早可用的堆叠行。 */
function laneLayers(items: IntervalItemRecord[]): number {
  const sorted = [...items].sort((left, right) => left.start - right.start);
  const laneEnds: number[] = [];
  for (const item of sorted) {
    const end =
      item.end === null || item.end <= item.start ? item.start + 1 : item.end;
    let placed = false;
    for (let index = 0; index < laneEnds.length; index += 1) {
      if ((laneEnds[index] ?? 0) <= item.start) {
        laneEnds[index] = end;
        placed = true;
        break;
      }
    }
    if (!placed) {
      laneEnds.push(end);
    }
  }
  return Math.max(1, laneEnds.length);
}

/** 估算区间图内容高度：泳道数 × 堆叠层数 × 目标行高 + 图轴占用（封顶内容估算上限）。 */
export function estimateIntervalFit(
  data: IntervalData | null,
): { fitWidth: number; fitHeight: number | null } {
  if (data === null || data.lanes.length === 0) {
    return { fitWidth: MIN_VIEW_WIDTH, fitHeight: null };
  }
  const byLane = new Map<string, IntervalItemRecord[]>();
  for (const item of data.items) {
    const list = byLane.get(item.laneKey);
    if (list === undefined) {
      byLane.set(item.laneKey, [item]);
    } else {
      list.push(item);
    }
  }
  let rows = 0;
  for (const lane of data.lanes) {
    rows += laneLayers(byLane.get(lane.key) ?? []);
  }
  const fitHeight = clamp(
    Math.round(rows * LANE_ROW_HEIGHT + INTERVAL_HEIGHT_EXTRAS),
    MIN_VIEW_HEIGHT,
    MAX_VIEW_FIT_HEIGHT,
  );
  // 宽度为手动画布几何，不参与内容估算；回传最小宽仅作占位。
  return { fitWidth: MIN_VIEW_WIDTH, fitHeight };
}

function colorFor(colorKey: string | null, colorIndex: ReadonlyMap<string, number>): string | null {
  if (colorKey === null) {
    return null;
  }
  const index = colorIndex.get(colorKey);
  if (index === undefined) {
    return null;
  }
  return COLOR_PALETTE[index % COLOR_PALETTE.length] ?? null;
}

function itemTitle(item: IntervalItemRecord): string {
  const parts: string[] = [];
  if (item.label !== "") {
    parts.push(`<strong>${escapeHtml(item.label)}</strong>`);
  }
  if (item.end === null || item.end <= item.start) {
    parts.push(`帧 ${item.start}（${(item.start / 60).toFixed(1)}s）`);
  } else {
    parts.push(
      `帧 ${item.start} → ${item.end}（${(item.start / 60).toFixed(1)}s → ${(item.end / 60).toFixed(1)}s）`,
    );
    parts.push(`时长 ${item.end - item.start} 帧`);
  }
  if (item.value !== null) {
    parts.push(`数值 ${formatNumberValue(item.value)}`);
  }
  return parts.join("<br/>");
}

function toTimelineItems(
  data: IntervalData,
  colorIndex: ReadonlyMap<string, number>,
  hiddenColors: ReadonlySet<string>,
): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const item of data.items) {
    if (item.colorKey !== null && hiddenColors.has(item.colorKey)) {
      continue;
    }
    const isPoint = item.end === null || item.end <= item.start;
    const timelineItem: TimelineItem = {
      id: item.id,
      group: item.laneKey,
      start: item.start * MS_PER_FRAME,
      content: escapeHtml(item.label),
      title: itemTitle(item),
      type: isPoint ? "point" : "range",
    };
    if (!isPoint) {
      timelineItem.end = (item.end as number) * MS_PER_FRAME;
    }
    const color = colorFor(item.colorKey, colorIndex);
    if (color !== null) {
      timelineItem.style = `background-color:${color};border-color:${color};color:#ffffff;`;
    }
    items.push(timelineItem);
  }
  return items;
}

/** vis-timeline 的刻度回调可能传 Date，也可能直接传毫秒数，统一归一到毫秒。 */
function timeToMs(value: unknown): number | null {
  if (value instanceof Date) {
    return value.getTime();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

/** 刻度标签：次刻度显示帧号；主刻度在可视跨度较大时改用秒。 */
export function formatAxisLabel(value: unknown, spanFrames: number, major: boolean): string {
  const ms = timeToMs(value);
  if (ms === null) {
    return "";
  }
  const frame = Math.round(ms / MS_PER_FRAME);
  if (!major) {
    return String(frame);
  }
  return spanFrames >= SECONDS_AXIS_THRESHOLD
    ? `${(frame / 60).toFixed(1)}s`
    : `${frame}帧`;
}

/**
 * 容器宽度变化后，在**保持每像素时间不变**的前提下算出新的可见窗口。
 * 返回 null 表示无需调整（宽度无效或未变化）。
 */
export function rescaleWindowForWidth(
  windowStartMs: number,
  windowEndMs: number,
  previousWidth: number,
  width: number,
): { start: number; end: number } | null {
  if (previousWidth <= 0 || width <= 0 || previousWidth === width) {
    return null;
  }
  const msPerPx = (windowEndMs - windowStartMs) / previousWidth;
  return { start: windowStartMs, end: windowStartMs + msPerPx * width };
}

export function IntervalChartView({
  node,
  definition,
  table,
  onFitChange,
}: {
  node: WorkflowNode;
  definition: WorkflowDefinition;
  table: AnalysisTableResult;
  /** 内容自然高变化时上报；宽度为手动画布几何，不参与内容驱动。 */
  onFitChange?: (info: ViewFitInfo) => void;
}) {
  const config = useMemo(
    () => connectedConfigNode(definition, node.id, "interval_config"),
    [definition, node.id],
  );
  const defaultBinding = useMemo(
    () => (config === null ? defaultIntervalBinding(table.columns) : null),
    [config, table.columns],
  );
  const binding = useMemo<IntervalBinding>(() => {
    if (config !== null) {
      return {
        lane: asString(config.params.lane) ?? "",
        start: asString(config.params.start) ?? "",
        end: asString(config.params.end) || null,
        label: asString(config.params.label) || null,
        value: asString(config.params.value) || null,
        color: asString(config.params.color) || null,
        laneOrder: asString(config.params.lane_order) || null,
      };
    }
    if (defaultBinding === null) {
      return {
        lane: "",
        start: "",
        end: null,
        label: null,
        value: null,
        color: null,
        laneOrder: null,
      };
    }
    return {
      lane: defaultBinding.lane,
      start: defaultBinding.start,
      end: defaultBinding.end,
      label: null,
      value: null,
      color: null,
      laneOrder: null,
    };
  }, [config, defaultBinding]);

  const catalog = useAnalysisSchemaCatalog();
  const shapes = useMemo(() => computeAnalysisShapes(definition, catalog), [definition, catalog]);
  const inputShape = useMemo(
    () => viewInputShape(shapes, definition, node.id),
    [shapes, definition, node.id],
  );
  const valueKinds = useMemo(
    () => new Map(inputShape.map((column) => [column.name, column.valueKind ?? ""])),
    [inputShape],
  );
  const typeOf = useMemo(
    () => new Map(table.columns.map((column) => [column.name, column.type])),
    [table.columns],
  );
  const columnIndex = useMemo(
    () => new Map(table.columns.map((column, index) => [column.name, index])),
    [table.columns],
  );

  const assetKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const column of [binding.lane, binding.label]) {
      if (column === null || column === "" || !valueKinds.get(column)?.startsWith("asset:")) {
        continue;
      }
      const index = columnIndex.get(column);
      if (index === undefined) {
        continue;
      }
      for (const row of table.rows) {
        const value = row[index];
        if (typeof value === "string" && value !== "") {
          keys.add(value);
        }
      }
    }
    return Array.from(keys);
  }, [binding.lane, binding.label, valueKinds, columnIndex, table.rows]);
  const assetNames = useAssetNames(assetKeys);

  const formatValue = useMemo(
    () => (column: string, value: unknown) =>
      formatCell(value, typeOf.get(column), valueKinds.get(column), assetNames),
    [typeOf, valueKinds, assetNames],
  );

  const missingColumn = [
    binding.lane,
    binding.start,
    binding.end,
    binding.label,
    binding.value,
    binding.color,
    binding.laneOrder,
  ].find((name) => name !== null && name !== "" && !columnIndex.has(name));

  const startType = typeOf.get(binding.start) ?? "";
  const bindingReady =
    binding.lane !== "" &&
    binding.start !== "" &&
    missingColumn === undefined &&
    (startType === "int" || startType === "float");

  const data = useMemo(
    () => (bindingReady ? buildIntervalData(table, binding, formatValue) : null),
    [bindingReady, table, binding, formatValue],
  );

  // 渲染前置状态。视图只在无阻塞时挂载时间轴容器，故该标记同时作为时间轴重建的依赖：
  // 否则「先出错、再恢复」时容器不会重新拿到 Timeline 实例。
  let stateMessage: string | null = null;
  let stateIsError = false;
  if (binding.lane === "" || binding.start === "") {
    stateMessage = config === null ? "直连视图未找到可用的泳道列与起始列" : "区间图配置未就绪";
  } else if (missingColumn !== undefined) {
    stateMessage = `绑定列不在上游表中：${missingColumn}`;
    stateIsError = true;
  } else if (startType !== "int" && startType !== "float") {
    stateMessage = `起始列必须是数值列：${binding.start}`;
    stateIsError = true;
  } else if (data === null || data.items.length === 0) {
    stateMessage = "无可渲染区间（泳道或起始列为空、或类型不符）";
  }
  const chartReady = stateMessage === null;

  const colorIndex = useMemo(
    () => new Map((data?.colorKeys ?? []).map((key, index) => [key, index])),
    [data],
  );

  const [hiddenColors, setHiddenColors] = useState<ReadonlySet<string>>(new Set());
  const colorKeySignature = (data?.colorKeys ?? []).join("|");
  const [prevColorSignature, setPrevColorSignature] = useState(colorKeySignature);
  if (colorKeySignature !== prevColorSignature) {
    setPrevColorSignature(colorKeySignature);
    setHiddenColors(new Set());
  }

  const groups = useMemo(
    () =>
      (data?.lanes ?? []).map((lane) => ({
        id: lane.key,
        content: escapeHtml(lane.label),
        order: lane.order,
      })),
    [data],
  );

  const items = useMemo(
    () => (data === null ? [] : toTimelineItems(data, colorIndex, hiddenColors)),
    [data, colorIndex, hiddenColors],
  );

  const bounds = useMemo(() => {
    if (data === null || data.items.length === 0) {
      return { minFrame: 0, maxFrame: 1 };
    }
    let minFrame = 0;
    let maxFrame = 1;
    for (const item of data.items) {
      minFrame = Math.min(minFrame, item.start);
      maxFrame = Math.max(maxFrame, item.end ?? item.start);
    }
    return { minFrame, maxFrame };
  }, [data]);

  const fit = useMemo(() => estimateIntervalFit(data), [data]);
  useEffect(() => {
    onFitChange?.({ fitWidth: fit.fitWidth, fitHeight: fit.fitHeight, hiddenColumns: 0 });
  }, [fit, onFitChange]);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const timelineRef = useRef<Timeline | null>(null);
  const spanFramesRef = useRef(SECONDS_AXIS_THRESHOLD);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    // 高度下发实测像素值而不是 "100%"：vis-timeline 在构造时按容器尺寸布局内部面板，
    // 若此刻百分比高度尚未解析（flex 链未定高）就会按 0 布局且不再自行重算，
    // 表现为「必须交互一次（点击/缩放触发内部 redraw）才显示」。同按键轨迹节点的做法。
    const initialHeight = Math.max(1, Math.round(container.clientHeight));
    const options: TimelineOptions = {
      width: "100%",
      height: initialHeight,
      editable: false,
      selectable: false,
      stack: true,
      horizontalScroll: true,
      verticalScroll: true,
      zoomable: true,
      moveable: true,
      showCurrentTime: false,
      orientation: { axis: "bottom", item: "top" },
      margin: { axis: 8, item: { horizontal: 4, vertical: 2 } },
      maxMinorChars: 8,
      format: {
        minorLabels: (value: unknown) => formatAxisLabel(value, spanFramesRef.current, false),
        majorLabels: (value: unknown) => formatAxisLabel(value, spanFramesRef.current, true),
      },
      tooltip: { followMouse: true, delay: 150 },
    };
    const timeline = new Timeline(container, [], options);
    timelineRef.current = timeline;
    const handleRangeChange = (properties: { start: Date; end: Date }) => {
      spanFramesRef.current = Math.max(
        1,
        Math.round((properties.end.getTime() - properties.start.getTime()) / MS_PER_FRAME),
      );
    };
    timeline.on("rangechange", handleRangeChange);
    timeline.on("rangechanged", handleRangeChange);
    // vis-timeline 的 autoResize 只跟随窗口，不监听容器自身尺寸，尺寸变化必须手动同步。
    let lastWidth = container.clientWidth;
    let syncFrame: number | null = null;
    const syncToContainer = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width <= 0 || height <= 0) {
        return;
      }
      const previous = lastWidth;
      lastWidth = width;
      if (previous > 0 && previous !== width) {
        // 宽度变化保持「每像素对应的时间」不变，改的是可见时间跨度：
        // 拖宽看到更多帧、拖窄看到更少，而不是把同一段窗口等比缩放。
        const current = timeline.getWindow();
        const next = rescaleWindowForWidth(
          current.start.getTime(),
          current.end.getTime(),
          previous,
          width,
        );
        if (next !== null) {
          timeline.setWindow(next.start, next.end, { animation: false });
        }
      }
      timeline.setOptions({ height: Math.round(height) });
      timeline.redraw();
    };
    const scheduleSync = () => {
      if (syncFrame !== null) {
        return;
      }
      syncFrame = window.requestAnimationFrame(() => {
        syncFrame = null;
        syncToContainer();
      });
    };
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleSync);
    resizeObserver?.observe(container);
    // 首次布局后主动同步一次，避免容器尺寸晚于构造就绪时停留在空白。
    scheduleSync();
    return () => {
      resizeObserver?.disconnect();
      if (syncFrame !== null) {
        window.cancelAnimationFrame(syncFrame);
      }
      timeline.destroy();
      timelineRef.current = null;
    };
  }, [chartReady]);

  const boundsKey = `${bounds.minFrame}:${bounds.maxFrame}`;
  const appliedBoundsRef = useRef("");
  useEffect(() => {
    const timeline = timelineRef.current;
    if (timeline === null) {
      return;
    }
    if (groups.length === 0 || items.length === 0) {
      timeline.setGroups([]);
      timeline.setItems([]);
      appliedBoundsRef.current = "";
      return;
    }
    timeline.setGroups(groups);
    timeline.setItems(items);
    // 可配置时间范围两侧各留一个数据跨度：保持每帧像素宽时，拖宽需要能把窗口
    // 延伸到数据以外，否则会被 min/max 夹回、又退化成等比缩放。
    const span = Math.max(1, bounds.maxFrame - bounds.minFrame);
    timeline.setOptions({
      min: (bounds.minFrame - span) * MS_PER_FRAME,
      max: (bounds.maxFrame + span) * MS_PER_FRAME,
      zoomMin: MS_PER_FRAME * Math.max(1, Math.floor(span / 200)),
      zoomMax: MS_PER_FRAME * Math.ceil(span * 3),
    });
    if (appliedBoundsRef.current !== boundsKey) {
      appliedBoundsRef.current = boundsKey;
      timeline.setWindow(
        bounds.minFrame * MS_PER_FRAME,
        bounds.maxFrame * MS_PER_FRAME,
        { animation: false },
      );
    }
  }, [groups, items, bounds.minFrame, bounds.maxFrame, boundsKey]);

  if (stateMessage !== null || data === null) {
    return (
      <div
        className={`analysis-view-state${stateIsError ? " analysis-view-error" : ""}`}
      >
        {stateMessage ?? "无可渲染区间"}
      </div>
    );
  }

  return (
    <div className="analysis-chart-view">
      {data.colorKeys.length > 0 && (
        <div className="analysis-interval-legend nodrag nowheel">
          {data.colorKeys.map((key) => {
            const hidden = hiddenColors.has(key);
            return (
              <button
                key={key}
                type="button"
                className={`analysis-interval-chip${hidden ? " muted" : ""}`}
                onClick={() =>
                  setHiddenColors((current) => {
                    const next = new Set(current);
                    if (next.has(key)) {
                      next.delete(key);
                    } else {
                      next.add(key);
                    }
                    return next;
                  })
                }
              >
                <span
                  className="analysis-interval-swatch"
                  style={{ backgroundColor: colorFor(key, colorIndex) ?? "transparent" }}
                />
                {key}
              </button>
            );
          })}
        </div>
      )}
      {/* nowheel/nodrag：滚轮缩放与拖拽平移交给时间轴自身，不冒泡到画布（同 traceTimeline）。 */}
      <div
        className="analysis-chart analysis-interval-canvas nodrag nowheel"
        ref={containerRef}
      />
      {table.truncated && (
        <div className="analysis-member-footer">
          <span className="analysis-member-truncated">
            仅显示前 {MAX_RENDERED_ROWS} 行
          </span>
        </div>
      )}
    </div>
  );
}
