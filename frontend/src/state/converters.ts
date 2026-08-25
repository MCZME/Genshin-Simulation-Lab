import type { WorkflowDefinition } from "../workflow/types";
import type { EditorState } from "./editor_state";

/**
 * 存量工作流迁移：
 * - 算子化重做（决策 2.32）后，processing 与 query_config 节点及其连线在加载时移除；
 * - 取数节点合并（2026-08-26 修订）后，fetch_runs / fetch_events 转为 fetch + source。
 */
const RETIRED_NODE_KINDS = new Set(["processing", "query_config"]);
const FETCH_SOURCE_BY_KIND: Record<string, "runs" | "events"> = {
  fetch_runs: "runs",
  fetch_events: "events",
};

export function migrateWorkflowDefinition(
  definition: WorkflowDefinition,
): WorkflowDefinition {
  const hasRetired = definition.nodes.some((node) => RETIRED_NODE_KINDS.has(node.kind));
  const hasLegacyFetch = definition.nodes.some((node) => node.kind in FETCH_SOURCE_BY_KIND);
  if (!hasRetired && !hasLegacyFetch) {
    return definition;
  }
  const retiredIds = new Set(
    definition.nodes
      .filter((node) => RETIRED_NODE_KINDS.has(node.kind))
      .map((node) => node.id),
  );
  const nodes = definition.nodes
    .filter((node) => !retiredIds.has(node.id))
    .map((node) => {
      const source = FETCH_SOURCE_BY_KIND[node.kind];
      if (source === undefined) {
        return node;
      }
      return {
        ...node,
        kind: "fetch" as const,
        params: { source, ...node.params },
      };
    });
  return {
    ...definition,
    nodes,
    edges: definition.edges.filter(
      (edge) => !retiredIds.has(edge.source_node_id) && !retiredIds.has(edge.target_node_id),
    ),
  };
}

export function definitionToEditorState(definition: WorkflowDefinition): EditorState {
  const saved = deepClone(migrateWorkflowDefinition(definition));
  return {
    definition: saved,
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
    past: [],
    future: [],
    saved,
  };
}

export function editorStateToDefinition(state: EditorState): WorkflowDefinition {
  return deepClone(state.definition);
}

export function cloneEditorState(state: EditorState): EditorState {
  return {
    definition: deepClone(state.definition),
    selection: {
      regions: [...state.selection.regions],
      nodes: [...state.selection.nodes],
      edges: [...state.selection.edges],
    },
    dirty: state.dirty,
    past: state.past.map((definition) => deepClone(definition)),
    future: state.future.map((definition) => deepClone(definition)),
    saved: state.saved === null ? null : deepClone(state.saved),
  };
}

function deepClone<T>(value: T): T {
  return structuredClone(value);
}
