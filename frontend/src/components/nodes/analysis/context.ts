/** 分析区域编辑器共享上下文与基础类型。 */

import type { AnalysisSchemaCatalog, TableShape } from "../../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../../workflow/types";

export type EditorRow = Record<string, unknown>;
export type EditorParams = Record<string, unknown>;
export interface EditorProps {
  node: WorkflowNode;
  onChange: (params: EditorParams) => void;
  fieldErrors?: Record<string, string[]>;
}


export interface AnalysisEditorEnvironment {
  catalog: AnalysisSchemaCatalog | null;
  definition: WorkflowDefinition;
  shapes: Map<string, TableShape[] | null>;
}


const EditorEnvironmentContext = {
  current: null as AnalysisEditorEnvironment | null,
};

export function setAnalysisEditorEnvironment(env: AnalysisEditorEnvironment | null): void {
  EditorEnvironmentContext.current = env;
}

export function getAnalysisEditorEnvironment(): AnalysisEditorEnvironment | null {
  return EditorEnvironmentContext.current;
}

export const ANALYSIS_EDITOR_CONTEXT = Symbol("analysis-editor-context");

export function useContextEnv(): AnalysisEditorEnvironment {
  return (
    EditorEnvironmentContext.current ?? {
      catalog: null,
      definition: { schema_version: 1, meta: { name: "" }, regions: [], nodes: [], edges: [], layout: {} },
      shapes: new Map(),
    }
  );
}

export function inputShapeFor(nodeId: string, portId: string): TableShape[] {
  const env = getAnalysisEditorEnvironment();
  if (env === null) {
    return [];
  }
  const edge = env.definition.edges.find(
    (item) => item.target_node_id === nodeId && item.target_port_id === portId,
  );
  if (edge === undefined) {
    return [];
  }
  return env.shapes.get(edge.source_node_id) ?? [];
}

export function upstreamShape(nodeId: string): TableShape[] {
  return inputShapeFor(nodeId, "in");
}


export const COLUMN_NAME_PATTERN = /^[A-Za-z0-9_]{1,64}$/;
