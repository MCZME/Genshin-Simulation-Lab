/** 视图节点尺寸语义：高度始终手动，宽度支持自适应/固定（表格视图定稿 2026-08-27）。 */

import type { NodeSize } from "./types";

/** 视图节点最小宽度（固定模式拖拽下限，也作为空态/未测量时的兜底宽度）。 */
export const MIN_VIEW_WIDTH = 560;
/** 新建视图节点的默认高度（高度纯手动，随画布几何保存）。 */
export const DEFAULT_VIEW_HEIGHT = 360;
/** 手动调节高度的下限/上限。 */
export const MIN_VIEW_HEIGHT = 240;
export const MAX_VIEW_HEIGHT = 720;
/**
 * 自适应宽度软上限（内部常量，不对用户开放）：
 * 内容自然宽超过该值后裁剪隐藏，由用户拖宽查看。
 */
export const VIEW_SOFT_CAP_WIDTH = 960;

export type TableWidthMode = "auto" | "fixed";

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** 归一化表格配置的宽度模式；缺失或非法值回落 auto。 */
export function normalizeWidthMode(value: unknown): TableWidthMode {
  return value === "fixed" ? "fixed" : "auto";
}

/**
 * 解析表格视图节点宽度：
 * - auto：min(内容自然宽, 软上限)，未测量时用默认宽；
 * - fixed：手动宽，硬上限 = 内容自然宽（没有数据时回落软上限），随数据更新自动夹回。
 */
export function resolveViewWidth(
  mode: TableWidthMode,
  fitWidth: number | null,
  fixedWidth: number | undefined,
): number {
  const cap = VIEW_SOFT_CAP_WIDTH;
  if (mode === "fixed") {
    const hardMax =
      fitWidth === null ? VIEW_SOFT_CAP_WIDTH : Math.max(MIN_VIEW_WIDTH, fitWidth);
    return clamp(Math.round(fixedWidth ?? MIN_VIEW_WIDTH), MIN_VIEW_WIDTH, hardMax);
  }
  const natural = fitWidth === null ? MIN_VIEW_WIDTH : Math.max(MIN_VIEW_WIDTH, fitWidth);
  return clamp(Math.round(natural), MIN_VIEW_WIDTH, cap);
}

/** 解析视图节点高度：纯手动，夹持在上下限内。 */
export function resolveViewHeight(height: number | undefined): number {
  return clamp(
    Math.round(height ?? DEFAULT_VIEW_HEIGHT),
    MIN_VIEW_HEIGHT,
    MAX_VIEW_HEIGHT,
  );
}

/** 固定宽度拖拽时允许的最大宽度：全部列完整显示所需宽度；未测量时回落软上限。 */
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
