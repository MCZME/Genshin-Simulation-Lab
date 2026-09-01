/** 视图节点尺寸语义：高度始终手动；宽度按视图声明（表格/柱状图内容驱动，饼图手动几何）。 */

import type { NodeSize } from "./types";

/** 视图节点最小宽度（也作为空态/未测量时的兜底宽度）。 */
export const MIN_VIEW_WIDTH = 560;
/** 新建视图节点的默认高度（高度纯手动，随画布几何保存）。 */
export const DEFAULT_VIEW_HEIGHT = 360;
/** 手动调节高度的下限/上限（也是自动高度的软上限）。 */
export const MIN_VIEW_HEIGHT = 240;
export const MAX_VIEW_HEIGHT = 720;
/**
 * 内容自适应的宽度软上限（内部常量，不对用户开放）：
 * 自动宽度不超过该值；用户拖宽手柄可超过软上限，上限为内容自然宽/内容估算宽。
 */
export const VIEW_SOFT_CAP_WIDTH = 960;

/** 柱状图宽度估算：每根柱的目标宽度（保证可点击性）。 */
export const BAR_TARGET_WIDTH = 16;
/** 柱状图宽度估算：同 X 类目内系列柱之间的间隙。 */
export const BAR_SERIES_GAP = 4;
/** 柱状图宽度估算：X 类目槽位两侧的预留。 */
export const BAR_CATEGORY_GAP = 16;
/** 柱状图宽度估算：类目标签文本两侧的预留。 */
export const BAR_LABEL_PADDING = 24;
/** 柱状图宽度估算：Y 轴刻度与图表边距预留。 */
export const BAR_AXIS_RESERVE = 64;
/** 柱状图高度估算：最小非零值柱的目标高度（保证可读/可点）。 */
export const BAR_MIN_HEIGHT = 6;
/** 柱状图高度估算：坐标轴标签、图例与边距预留。 */
export const BAR_HEIGHT_EXTRAS = 68;
/** 内容估算高度封顶：自动高度软上限之上的手柄可拖上限（柱状图/表格共用）。 */
export const MAX_VIEW_FIT_HEIGHT = 1440;
/** 表格高度估算：表头、工具条、页脚与边框的固定占用。 */
export const TABLE_HEIGHT_EXTRAS = 86;

/**
 * 单项详情卡（伤害详情）宽度语义：宽度手动可调并随节点保存，高度随内容自适应。
 * 与视图卡互不影响；上限沿用视图软上限。
 */
export const DEFAULT_DETAIL_WIDTH = 320;
export const MIN_DETAIL_WIDTH = 280;
export const MAX_DETAIL_WIDTH = VIEW_SOFT_CAP_WIDTH;

/** 按键轨迹节点宽度语义：宽度手动可调并随节点保存，高度随内容自适应。 */
export const DEFAULT_TRACE_WIDTH = 720;
export const MIN_TRACE_WIDTH = 560;
export const MAX_TRACE_WIDTH = 1280;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * 解析内容驱动视图宽度（表格/柱状图）：
 * - 未保存手动宽度：min(内容自然宽, 软上限)，未测量时用默认宽；
 * - 已保存手动宽度：夹持在 [最小宽, 内容自然宽]（未测量时上限回落软上限），内容缩小后自动夹回。
 */
export function resolveViewWidth(
  fitWidth: number | null,
  manualWidth: number | undefined,
): number {
  const cap = VIEW_SOFT_CAP_WIDTH;
  if (manualWidth !== undefined) {
    const hardMax = fitWidth === null ? cap : Math.max(MIN_VIEW_WIDTH, fitWidth);
    return clamp(Math.round(manualWidth), MIN_VIEW_WIDTH, hardMax);
  }
  const natural = fitWidth === null ? MIN_VIEW_WIDTH : Math.max(MIN_VIEW_WIDTH, fitWidth);
  return clamp(Math.round(natural), MIN_VIEW_WIDTH, cap);
}

/** 解析手动画布宽度（饼图）：夹持在最小宽与软上限之间。 */
export function resolveManualViewWidth(width: number | undefined): number {
  return clamp(
    Math.round(width ?? MIN_VIEW_WIDTH),
    MIN_VIEW_WIDTH,
    VIEW_SOFT_CAP_WIDTH,
  );
}

/**
 * 解析柱状图节点高度：
 * - 未保存手动高度：min(内容估算高, 高度软上限)，未测量时用默认高；
 * - 已保存手动高度：夹持在 [最小高, 内容估算高]（未测量时上限回落高度软上限）。
 */
export function resolveBarHeight(
  fitHeight: number | null,
  manualHeight: number | undefined,
): number {
  if (manualHeight !== undefined) {
    const hardMax =
      fitHeight === null ? MAX_VIEW_HEIGHT : Math.max(MIN_VIEW_HEIGHT, fitHeight);
    return clamp(Math.round(manualHeight), MIN_VIEW_HEIGHT, hardMax);
  }
  const natural =
    fitHeight === null ? DEFAULT_VIEW_HEIGHT : Math.max(MIN_VIEW_HEIGHT, fitHeight);
  return clamp(Math.round(natural), MIN_VIEW_HEIGHT, MAX_VIEW_HEIGHT);
}

/**
 * 解析视图节点高度（表格/饼图）：
 * - 未保存手动高度：默认 360px；
 * - 已保存手动高度：夹持在 [最小高, 内容估算高]（表格未测量时回落高度软上限；饼图无内容估算，恒为软上限）。
 */
export function resolveViewHeight(
  height: number | undefined,
  fitHeight: number | null = null,
): number {
  if (height !== undefined) {
    const hardMax =
      fitHeight === null ? MAX_VIEW_HEIGHT : Math.max(MIN_VIEW_HEIGHT, fitHeight);
    return clamp(Math.round(height), MIN_VIEW_HEIGHT, hardMax);
  }
  return DEFAULT_VIEW_HEIGHT;
}

/** 解析按键轨迹节点宽度：纯手动，夹持在上下限内。 */
export function resolveTraceWidth(width: number | undefined): number {
  return clamp(
    Math.round(width ?? DEFAULT_TRACE_WIDTH),
    MIN_TRACE_WIDTH,
    MAX_TRACE_WIDTH,
  );
}

/** 内容驱动视图宽度拖拽上限：内容自然宽；未测量时回落软上限。 */
export function resolveDragMaxWidth(fitWidth: number | null): number {
  return fitWidth === null
    ? VIEW_SOFT_CAP_WIDTH
    : Math.max(MIN_VIEW_WIDTH, fitWidth);
}

export function normalizeNodeSize(
  size: Partial<NodeSize> | null | undefined,
  fallback: NodeSize,
): NodeSize {
  return {
    width: size?.width ?? fallback.width,
    height: size?.height ?? fallback.height,
  };
}
