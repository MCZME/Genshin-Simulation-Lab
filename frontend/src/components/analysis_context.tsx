import { createContext, useContext } from "react";

import type { AnalysisNodeResult } from "../workflow/analysis_runner";
import type { AnalysisSchemaCatalog, AnalysisTableResult } from "../workflow/templates";

export const AnalysisSchemaCatalogContext = createContext<AnalysisSchemaCatalog | null>(null);

export function useAnalysisSchemaCatalog(): AnalysisSchemaCatalog | null {
  return useContext(AnalysisSchemaCatalogContext);
}

/** 视图 selection 输出的瞬态选择表：所有视图点击后都以 table 形式呈现。 */
export interface AnalysisSelectionStore {
  selections: Map<string, AnalysisTableResult>;
  select: (nodeId: string, table: AnalysisTableResult | null) => void;
}

export const AnalysisSelectionContext = createContext<AnalysisSelectionStore | null>(null);

export function useAnalysisSelection(): AnalysisSelectionStore | null {
  return useContext(AnalysisSelectionContext);
}

/** 视图点击选择意图：行选择（表格）或分组选择（饼图/柱状图）。 */
export type AnalysisStageSelectionRecord =
  | { kind: "row"; row_index: number }
  | { kind: "group"; groupColumns: string[]; groupValues: unknown[] };

export interface AnalysisStageSelectionStore {
  records: ReadonlyMap<string, AnalysisStageSelectionRecord | null>;
  select: (nodeId: string, record: AnalysisStageSelectionRecord | null) => void;
  contextIdFor: (regionId: string) => string | null;
}

export const AnalysisStageSelectionContext =
  createContext<AnalysisStageSelectionStore | null>(null);

export function useAnalysisStageSelection(): AnalysisStageSelectionStore | null {
  return useContext(AnalysisStageSelectionContext);
}

/** 分析区域节点结果表的运行时只读视图：供单项详情节点读取上游单行表。 */
export const AnalysisResultsContext = createContext<Map<string, AnalysisNodeResult> | null>(null);

export function useAnalysisResults(): Map<string, AnalysisNodeResult> | null {
  return useContext(AnalysisResultsContext);
}
