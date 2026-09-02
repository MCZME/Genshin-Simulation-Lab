import { createContext, useContext } from "react";

import type { AnalysisSchemaCatalog } from "../workflow/templates";

export const AnalysisSchemaCatalogContext = createContext<AnalysisSchemaCatalog | null>(null);

export function useAnalysisSchemaCatalog(): AnalysisSchemaCatalog | null {
  return useContext(AnalysisSchemaCatalogContext);
}

/** 视图 selection 输出的瞬态选择存储：节点 id -> item（表格）或行集表（饼图/柱状图）。 */
export interface AnalysisSelectionStore {
  selections: Map<string, unknown>;
  select: (nodeId: string, item: unknown | null) => void;
}

export const AnalysisSelectionContext = createContext<AnalysisSelectionStore | null>(null);

export function useAnalysisSelection(): AnalysisSelectionStore | null {
  return useContext(AnalysisSelectionContext);
}

/** 分析区域节点结果表的运行时只读视图：供单项详情节点解析上游 item。 */
export const AnalysisResultsContext = createContext<Map<string, unknown> | null>(null);

export function useAnalysisResults(): Map<string, unknown> | null {
  return useContext(AnalysisResultsContext);
}
