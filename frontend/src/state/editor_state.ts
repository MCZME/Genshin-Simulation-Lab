import type {
  NodeSize,
  Rect,
  WorkflowDefinition,
  WorkflowRegion,
} from "../workflow/types";
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
  past: WorkflowDefinition[];
  future: WorkflowDefinition[];
  /** 最后保存的完整定义；dirty 由当前定义与它比较派生。 */
  saved: WorkflowDefinition | null;
}

export function createEmptyEditorState(name = "未命名工作流"): EditorState {
  const definition: WorkflowDefinition = {
    schema_version: 1,
    meta: { name },
    regions: [],
    nodes: [],
    edges: [],
    layout: {},
  };
  return {
    definition,
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
    past: [],
    future: [],
    saved: clone(definition),
  };
}

export function renameWorkflow(state: EditorState, name: string): EditorState {
  return performEdit(state, {
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
  return performEdit(state, {
    ...state.definition,
    regions: [...state.definition.regions, region],
  });
}

export function renameRegion(state: EditorState, regionId: string, name: string): EditorState {
  return performEdit(state, {
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
  return performEdit(state, {
    ...state.definition,
    regions: state.definition.regions.map((region) =>
      region.id === regionId ? { ...region, rect } : region,
    ),
  });
}

/** 移动区域时同步平移区域内节点的绝对坐标，作为一个原子历史步骤。 */
export function moveRegionWithChildren(
  state: EditorState,
  regionId: string,
  position: { x: number; y: number },
): EditorState {
  const region = state.definition.regions.find((item) => item.id === regionId);
  if (region === undefined) {
    return state;
  }
  const dx = position.x - region.rect.x;
  const dy = position.y - region.rect.y;
  return performEdit(state, {
    ...state.definition,
    regions: state.definition.regions.map((item) =>
      item.id === regionId ? { ...item, rect: { ...item.rect, x: position.x, y: position.y } } : item,
    ),
    nodes: state.definition.nodes.map((node) =>
      node.region_id === regionId
        ? { ...node, position: { x: node.position.x + dx, y: node.position.y + dy } }
        : node,
    ),
  });
}

/** 调整区域矩形；内部节点保持绝对位置不变，不做内容缩放。 */
export function resizeRegion(
  state: EditorState,
  regionId: string,
  rect: Rect,
): EditorState {
  const region = state.definition.regions.find((item) => item.id === regionId);
  if (region === undefined) {
    return state;
  }
  return performEdit(state, {
    ...state.definition,
    regions: state.definition.regions.map((item) =>
      item.id === regionId ? { ...item, rect } : item,
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
  return performEdit(state, {
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
  return performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, position } : node,
    ),
  });
}

/** 更新节点画布几何（宽高）；与位置同类，作为一个原子编辑步骤。 */
export function resizeNode(
  state: EditorState,
  nodeId: string,
  size: NodeSize,
): EditorState {
  return performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, size } : node,
    ),
  });
}

/**
 * 视图节点从「自适应宽度」拖宽结束时的一次原子提交：
 * 同时写入节点尺寸并把表格配置切到固定模式，避免拆成两步历史。
 */
export function resizeNodeWithFixedMode(
  state: EditorState,
  nodeId: string,
  size: NodeSize,
  configNodeId: string,
): EditorState {
  return performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) => {
      if (node.id === nodeId) {
        return { ...node, size };
      }
      if (node.id === configNodeId && node.kind === "table_config") {
        return { ...node, params: { ...node.params, width_mode: "fixed" } };
      }
      return node;
    }),
  });
}

/** 拖动节点时同时更新位置与区域归属；仅当区域成员被拖出成草稿时断开关联连线。 */
export function moveNodeWithRegion(
  state: EditorState,
  nodeId: string,
  position: { x: number; y: number },
  regionId: string | null,
): EditorState {
  const previous = state.definition.nodes.find((node) => node.id === nodeId);
  if (previous === undefined) {
    return state;
  }
  // 画布级节点（region 为 null 的类型）始终不属于任何区域，拖动不得断线。
  const leftRegion = previous.region_id !== null && regionId === null;
  const next = performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, position, region_id: regionId } : node,
    ),
    edges: leftRegion
      ? state.definition.edges.filter(
          (edge) => edge.source_node_id !== nodeId && edge.target_node_id !== nodeId,
        )
      : state.definition.edges,
  });
  return {
    ...next,
    selection: pruneSelection(state.selection, next.definition),
  };
}

export function setNodeRegion(
  state: EditorState,
  nodeId: string,
  regionId: string | null,
): EditorState {
  return performEdit(state, {
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
  return performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      node.id === nodeId ? { ...node, params } : node,
    ),
  });
}

export function deleteNode(state: EditorState, nodeId: string): EditorState {
  const next = performEdit(state, {
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
  const next = performEdit(state, {
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
  return performEdit(state, {
    ...state.definition,
    edges: [...state.definition.edges, { id, ...connection }],
  });
}

export function deleteEdge(state: EditorState, edgeId: string): EditorState {
  const next = performEdit(state, {
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

/** 删除当前选中的区域、节点与连线，作为一个原子撤销步骤。 */
export function deleteSelection(state: EditorState): EditorState {
  const { regions, nodes, edges } = state.selection;
  if (regions.length + nodes.length + edges.length === 0) {
    return state;
  }
  const regionSet = new Set(regions);
  const nodeSet = new Set(nodes);
  const edgeSet = new Set(edges);
  const definition: WorkflowDefinition = {
    ...state.definition,
    regions: state.definition.regions.filter((region) => !regionSet.has(region.id)),
    nodes: state.definition.nodes
      .filter((node) => !nodeSet.has(node.id))
      .map((node) =>
        regionSet.has(node.region_id ?? "") ? { ...node, region_id: null } : node,
      ),
    edges: state.definition.edges.filter(
      (edge) =>
        !edgeSet.has(edge.id) &&
        !nodeSet.has(edge.source_node_id) &&
        !nodeSet.has(edge.target_node_id) &&
        !regionSet.has(edge.source_node_id) &&
        !regionSet.has(edge.target_node_id),
    ),
  };
  const next = performEdit(state, definition);
  return {
    ...next,
    selection: pruneSelection(state.selection, next.definition),
  };
}

/** 方向键微移选中的节点，作为一个原子撤销步骤。 */
export function nudgeSelection(
  state: EditorState,
  dx: number,
  dy: number,
): EditorState {
  const selected = new Set(state.selection.nodes);
  if (selected.size === 0) {
    return state;
  }
  return performEdit(state, {
    ...state.definition,
    nodes: state.definition.nodes.map((node) =>
      selected.has(node.id)
        ? { ...node, position: { x: node.position.x + dx, y: node.position.y + dy } }
        : node,
    ),
  });
}

export function setSelection(
  state: EditorState,
  selection: Partial<EditorSelection>,
): EditorState {
  return { ...state, selection: { ...state.selection, ...selection } };
}

export function markSaved(state: EditorState): EditorState {
  return { ...state, saved: clone(state.definition), dirty: false };
}

export function undo(state: EditorState): EditorState {
  if (state.past.length === 0) {
    return state;
  }
  const previous = state.past[state.past.length - 1];
  return {
    ...state,
    definition: previous,
    past: state.past.slice(0, -1),
    future: [state.definition, ...state.future],
    selection: pruneSelection(state.selection, previous),
    dirty: state.saved === null || !sameDefinition(previous, state.saved),
  };
}

export function redo(state: EditorState): EditorState {
  if (state.future.length === 0) {
    return state;
  }
  const next = state.future[0];
  return {
    ...state,
    definition: next,
    past: [...state.past, state.definition],
    future: state.future.slice(1),
    selection: pruneSelection(state.selection, next),
    dirty: state.saved === null || !sameDefinition(next, state.saved),
  };
}

export function canUndo(state: EditorState): boolean {
  return state.past.length > 0;
}

export function canRedo(state: EditorState): boolean {
  return state.future.length > 0;
}

/** 在同一输入端口组内上移/下移一条连线；连线数组顺序即生效顺序。 */
export function moveEdgeIncomingOrder(
  state: EditorState,
  targetNodeId: string,
  targetPortId: string,
  edgeId: string,
  direction: "up" | "down",
): EditorState {
  const edges = state.definition.edges;
  const group = edges.filter(
    (edge) => edge.target_node_id === targetNodeId && edge.target_port_id === targetPortId,
  );
  const groupIds = group.map((edge) => edge.id);
  const groupIndex = groupIds.indexOf(edgeId);
  if (groupIndex < 0) {
    return state;
  }
  const swapIndex = groupIndex + (direction === "up" ? -1 : 1);
  if (swapIndex < 0 || swapIndex >= group.length) {
    return state;
  }
  const from = edges.indexOf(group[groupIndex]);
  const to = edges.indexOf(group[swapIndex]);
  const next = [...edges];
  [next[from], next[to]] = [next[to], next[from]];
  return performEdit(state, { ...state.definition, edges: next });
}

function performEdit(state: EditorState, definition: WorkflowDefinition): EditorState {
  return {
    ...state,
    past: [...state.past, state.definition],
    future: [],
    definition,
    dirty: state.saved === null || !sameDefinition(definition, state.saved),
  };
}

function pruneSelection(
  selection: EditorSelection,
  definition: WorkflowDefinition,
): EditorSelection {
  const regionIds = new Set(definition.regions.map((region) => region.id));
  const nodeIds = new Set(definition.nodes.map((node) => node.id));
  const edgeIds = new Set(definition.edges.map((edge) => edge.id));
  return {
    regions: selection.regions.filter((id) => regionIds.has(id)),
    nodes: selection.nodes.filter((id) => nodeIds.has(id)),
    edges: selection.edges.filter((id) => edgeIds.has(id)),
  };
}

function sameDefinition(left: WorkflowDefinition, right: WorkflowDefinition): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function nextId(prefix: string, existing: string[]): string {
  const max = existing.reduce((current, id) => {
    const suffix = Number(id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `${prefix}-${max + 1}`;
}
