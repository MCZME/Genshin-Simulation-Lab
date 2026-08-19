import type { WorkflowDefinition, WorkflowRegion } from "../workflow/types";
import { createDefaultParams, getNodeKindSpec } from "../workflow/registry";

export interface EditorSelection {
  regions: string[];
  nodes: string[];
  edges: string[];
}

export interface EditorState {
  definition: WorkflowDefinition;
  selection: EditorSelection;
  dirty: boolean;
}

export function createEmptyEditorState(name = "未命名工作流"): EditorState {
  return {
    definition: {
      schema_version: 1,
      meta: { name },
      regions: [],
      nodes: [],
      edges: [],
      layout: {},
    },
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
  };
}

export function renameWorkflow(state: EditorState, name: string): EditorState {
  return withDefinition(state, {
    ...state.definition,
    meta: { ...state.definition.meta, name },
  });
}

export function addRegion(
  state: EditorState,
  kind: "configuration" | "analysis",
  name: string,
  rect: { x: number; y: number; width: number; height: number },
): EditorState {
  const id = nextId("region", state.definition.regions.map((region) => region.id));
  const region: WorkflowRegion = { id, kind, name, rect };
  return withDefinition(state, {
    ...state.definition,
    regions: [...state.definition.regions, region],
  });
}

export function renameRegion(state: EditorState, regionId: string, name: string): EditorState {
  return withDefinition(state, {
    ...state.definition,
    regions: state.definition.regions.map((region) =>
      region.id === regionId ? { ...region, name } : region,
    ),
  });
}

export function updateRegionRect(
  state: EditorState,
  regionId: string,
  rect: { x: number; y: number; width: number; height: number },
): EditorState {
  return withDefinition(state, {
    ...state.definition,
    regions: state.definition.regions.map((region) =>
      region.id === regionId ? { ...region, rect } : region,
    ),
  });
}

export function addNode(
  state: EditorState,
  kind: string,
  position: { x: number; y: number },
  regionId: string | null,
): EditorState {
  const spec = getNodeKindSpec(kind);
  if (spec === null) {
    return state;
  }
  const id = nextId("node", state.definition.nodes.map((node) => node.id));
  return withDefinition(state, {
    ...state.definition,
    nodes: [
      ...state.definition.nodes,
      { id, kind, region_id: regionId, position, params: createDefaultParams(kind) },
    ],
  });
}

export function moveNode(
  state: EditorState,
  nodeId: string,
  position: { x: number; y: number },
): EditorState {
  return withDefinition(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, position } : node,
    ),
  });
}

export function setNodeRegion(
  state: EditorState,
  nodeId: string,
  regionId: string | null,
): EditorState {
  return withDefinition(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, region_id: regionId } : node,
    ),
  });
}

export function setNodeParams(
  state: EditorState,
  nodeId: string,
  params: Record<string, unknown>,
): EditorState {
  return withDefinition(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, params } : node,
    ),
  });
}

export function deleteNode(state: EditorState, nodeId: string): EditorState {
  const next = withDefinition(state, {
    ...state.definition,
    nodes: state.definition.nodes.filter((node) => node.id !== nodeId),
    edges: state.definition.edges.filter(
      (edge) => edge.source_node_id !== nodeId && edge.target_node_id !== nodeId,
    ),
  });
  return {
    ...next,
    selection: {
      ...next.selection,
      nodes: next.selection.nodes.filter((id) => id !== nodeId),
      edges: next.selection.edges.filter((id) =>
        next.definition.edges.some((edge) => edge.id === id),
      ),
    },
  };
}

export function deleteRegion(state: EditorState, regionId: string): EditorState {
  const next = withDefinition(state, {
    ...state.definition,
    regions: state.definition.regions.filter((region) => region.id !== regionId),
    nodes: state.definition.nodes.map((node) =>
      node.region_id === regionId ? { ...node, region_id: null } : node,
    ),
    edges: state.definition.edges.filter(
      (edge) => edge.source_node_id !== regionId && edge.target_node_id !== regionId,
    ),
  });
  return {
    ...next,
    selection: {
      ...next.selection,
      regions: next.selection.regions.filter((id) => id !== regionId),
    },
  };
}

export function addEdge(
  state: EditorState,
  connection: {
    source_node_id: string;
    source_port_id: string;
    target_node_id: string;
    target_port_id: string;
  },
): EditorState {
  const duplicate = state.definition.edges.some(
    (edge) =>
      edge.source_node_id === connection.source_node_id &&
      edge.source_port_id === connection.source_port_id &&
      edge.target_node_id === connection.target_node_id &&
      edge.target_port_id === connection.target_port_id,
  );
  if (duplicate) {
    return state;
  }
  const id = nextId("edge", state.definition.edges.map((edge) => edge.id));
  return withDefinition(state, {
    ...state.definition,
    edges: [...state.definition.edges, { id, ...connection }],
  });
}

export function deleteEdge(state: EditorState, edgeId: string): EditorState {
  const next = withDefinition(state, {
    ...state.definition,
    edges: state.definition.edges.filter((edge) => edge.id !== edgeId),
  });
  return {
    ...next,
    selection: {
      ...next.selection,
      edges: next.selection.edges.filter((id) => id !== edgeId),
    },
  };
}

export function setSelection(
  state: EditorState,
  selection: Partial<EditorSelection>,
): EditorState {
  return { ...state, selection: { ...state.selection, ...selection } };
}

export function markSaved(state: EditorState): EditorState {
  return { ...state, dirty: false };
}

function withDefinition(state: EditorState, definition: WorkflowDefinition): EditorState {
  return { ...state, definition, dirty: true };
}

function nextId(prefix: string, existing: string[]): string {
  const max = existing.reduce((current, id) => {
    const suffix = Number(id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `${prefix}-${max + 1}`;
}
