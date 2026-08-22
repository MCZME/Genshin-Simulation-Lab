import type {
  Diagnostic,
  DiagnosticSeverity,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRegion,
} from "./types";
import {
  MAX_BATCH_MEMBERS,
  REGION_BOUNDARY_OUT_PORT,
  WORKFLOW_SCHEMA_VERSION,
} from "./types";
import {
  getNodeKindSpec,
  isProjectionPort,
  memberItemIds,
  projectionItemId,
  validateNode,
} from "./registry";
import { expandConfigurationRegion } from "./compiler";

type EndpointKind = "node" | "region";

interface Endpoint {
  kind: EndpointKind;
  id: string;
}

export function validateWorkflow(definition: WorkflowDefinition): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  if (definition.schema_version !== WORKFLOW_SCHEMA_VERSION) {
    diagnostics.push(
      diagnostic("error", "SCHEMA_VERSION_UNSUPPORTED", `不支持的 schema_version：${definition.schema_version}`),
    );
  }
  if (typeof definition.meta?.name !== "string") {
    diagnostics.push(diagnostic("error", "META_INVALID", "meta.name 必须是字符串"));
  }

  const regionById = new Map<string, WorkflowRegion>();
  for (const region of definition.regions) {
    if (regionById.has(region.id)) {
      diagnostics.push(
        diagnostic("error", "DUPLICATE_ID", `区域 id 重复：${region.id}`, { region_id: region.id }),
      );
    }
    regionById.set(region.id, region);
    if (region.kind !== "configuration" && region.kind !== "analysis") {
      diagnostics.push(
        diagnostic("error", "REGION_KIND_INVALID", `未知区域类型：${region.kind}`, {
          region_id: region.id,
        }),
      );
    }
  }

  const nodeById = new Map<string, WorkflowNode>();
  const rootCountByRegion = new Map<string | null, number>();
  for (const node of definition.nodes) {
    if (nodeById.has(node.id) || regionById.has(node.id)) {
      diagnostics.push(
        diagnostic("error", "DUPLICATE_ID", `节点 id 重复或与区域冲突：${node.id}`, {
          node_id: node.id,
        }),
      );
    }
    nodeById.set(node.id, node);
    rootCountByRegion.set(
      node.region_id,
      (rootCountByRegion.get(node.region_id) ?? 0) + (node.kind === "root" ? 1 : 0),
    );

    const spec = getNodeKindSpec(node.kind);
    if (spec === null) {
      diagnostics.push(
        diagnostic("error", "UNKNOWN_NODE_KIND", `未注册节点类型：${node.kind}`, {
          node_id: node.id,
        }),
      );
      continue;
    }

    if (node.region_id === null) {
      if (spec.region === null) {
        diagnostics.push(...validateNode(node));
        continue;
      }
      diagnostics.push(
        diagnostic("warning", "FREE_NODE_DRAFT", "节点未归属区域，作为游离草稿不参与运行", {
          node_id: node.id,
        }),
      );
      continue;
    }

    const region = regionById.get(node.region_id);
    if (region === undefined) {
      diagnostics.push(
        diagnostic("error", "UNKNOWN_REGION_REFERENCE", `引用了不存在的区域：${node.region_id}`, {
          node_id: node.id,
          region_id: node.region_id,
        }),
      );
      continue;
    }
    if (spec.region === null) {
      diagnostics.push(
        diagnostic("error", "CANVAS_NODE_REGION_INVALID", "模拟节点不能归属区域", {
          node_id: node.id,
          region_id: node.region_id,
        }),
      );
    } else if (spec.region !== region.kind) {
      diagnostics.push(
        diagnostic(
          "error",
          "REGION_KIND_MISMATCH",
          `${spec.displayName}节点不能放在 ${region.kind} 区域`,
          { node_id: node.id, region_id: node.region_id },
        ),
      );
    }

    diagnostics.push(...validateNode(node));
  }

  for (const [regionId, count] of rootCountByRegion) {
    if (regionId !== null && count > 1) {
      diagnostics.push(
        diagnostic("error", "MULTIPLE_ROOT_NODES", "同一配置区域只能有一个根节点", {
          region_id: regionId,
        }),
      );
    }
  }

  const edgeById = new Set<string>();
  for (const edge of definition.edges) {
    if (edgeById.has(edge.id)) {
      diagnostics.push(
        diagnostic("error", "DUPLICATE_ID", `连线 id 重复：${edge.id}`, { edge_id: edge.id }),
      );
    }
    edgeById.add(edge.id);
  }

  const endpoints = new Map<string, Endpoint>();
  for (const region of regionById.values()) {
    endpoints.set(region.id, { kind: "region", id: region.id });
  }
  for (const node of nodeById.values()) {
    endpoints.set(node.id, { kind: "node", id: node.id });
  }

  markCycles(definition, endpoints, diagnostics);

  const connectionCounts = new Map<string, number>();
  for (const edge of definition.edges) {
    validateEdge(edge, regionById, nodeById, endpoints, connectionCounts, diagnostics);
  }

  const connectedToSimulation = simulationLinkedRegions(definition, regionById, nodeById);
  validateMemberCap(definition, regionById, connectedToSimulation, diagnostics);
  validateTeamSlotConflicts(definition, regionById, diagnostics);
  warnNodesOutsideRegions(definition, regionById, diagnostics);
  validateRegionToSimulationLinks(definition, regionById, nodeById, connectedToSimulation, diagnostics);  return diagnostics;
}

/** 已连接到任一模拟节点输入的配置区域集合（决策 2.32：连接决定批次参与）。 */
function simulationLinkedRegions(
  definition: WorkflowDefinition,
  regionById: Map<string, WorkflowRegion>,
  nodeById: Map<string, WorkflowNode>,
): Set<string> {
  const linked = new Set<string>();
  for (const edge of definition.edges) {
    const sourceRegion = regionById.get(edge.source_node_id);
    const targetNode = nodeById.get(edge.target_node_id);
    if (
      sourceRegion?.kind === "configuration" &&
      edge.source_port_id === REGION_BOUNDARY_OUT_PORT &&
      targetNode?.kind === "simulation" &&
      edge.target_port_id === "in"
    ) {
      linked.add(sourceRegion.id);
    }
  }
  return linked;
}

/**
 * 区域与模拟节点的连接语义（决策 2.32）：
 * 未连接模拟节点的配置区域给警告并不参与运行；未连接任何配置区域的模拟节点批次无法成立，报错。
 */
function validateRegionToSimulationLinks(
  definition: WorkflowDefinition,
  regionById: Map<string, WorkflowRegion>,
  nodeById: Map<string, WorkflowNode>,
  connectedToSimulation: Set<string>,
  diagnostics: Diagnostic[],
): void {
  for (const region of regionById.values()) {
    if (region.kind === "configuration" && !connectedToSimulation.has(region.id)) {
      diagnostics.push(
        diagnostic("warning", "REGION_NOT_CONNECTED", "配置区域未连接模拟节点，不参与运行", {
          region_id: region.id,
        }),
      );
    }
  }
  for (const node of nodeById.values()) {
    if (node.kind !== "simulation") {
      continue;
    }
    const hasRegionSource = definition.edges.some(
      (edge) =>
        edge.target_node_id === node.id &&
        edge.target_port_id === "in" &&
        regionById.get(edge.source_node_id)?.kind === "configuration",
    );
    if (!hasRegionSource) {
      diagnostics.push(
        diagnostic("error", "SIM_BATCH_EMPTY", "模拟节点未连接配置区域，批次无法成立", {
          node_id: node.id,
        }),
      );
    }
  }
}

function validateEdge(
  edge: WorkflowEdge,
  regionById: Map<string, WorkflowRegion>,
  nodeById: Map<string, WorkflowNode>,
  endpoints: Map<string, Endpoint>,
  connectionCounts: Map<string, number>,
  diagnostics: Diagnostic[],
): void {
  const source = endpoints.get(edge.source_node_id);
  const target = endpoints.get(edge.target_node_id);
  if (source === undefined || target === undefined) {
    diagnostics.push(
      diagnostic("error", "UNKNOWN_ENDPOINT", "连线引用了不存在的节点或区域", {
        edge_id: edge.id,
      }),
    );
    return;
  }

  if (source.kind === "region") {
    validateRegionEndpoint(edge, source.id, "source", regionById, diagnostics);
  } else {
    validateNodeEndpoint(edge, source.id, "source", nodeById, diagnostics);
  }
  if (target.kind === "region") {
    validateRegionEndpoint(edge, target.id, "target", regionById, diagnostics);
  } else {
    validateNodeEndpoint(edge, target.id, "target", nodeById, diagnostics);
  }

  const sourcePort = resolvePort(edge.source_node_id, edge.source_port_id, "source", regionById, nodeById);
  const targetPort = resolvePort(edge.target_node_id, edge.target_port_id, "target", regionById, nodeById);

  if (source.kind === "node" && target.kind === "node") {
    const sourceNode = nodeById.get(edge.source_node_id);
    const targetNode = nodeById.get(edge.target_node_id);
    if (
      sourceNode !== undefined &&
      targetNode !== undefined &&
      sourceNode.region_id !== null &&
      targetNode.region_id !== null &&
      sourceNode.region_id !== targetNode.region_id
    ) {
      diagnostics.push(
        diagnostic("error", "CROSS_REGION_CONNECTION", "配置节点只能在同一区域内直接连线", {
          edge_id: edge.id,
          node_id: targetNode.id,
        }),
      );
    }
  }
  if (source.kind === "node" && source.id === target.id) {
    diagnostics.push(
      diagnostic("error", "SELF_CONNECTION", "节点不能连接自身", {
        edge_id: edge.id,
        node_id: source.id,
      }),
    );
  }

  if (sourcePort !== null && targetPort !== null) {
    if (sourcePort.dataLanguage !== targetPort.dataLanguage) {
      diagnostics.push(
        diagnostic(
          "error",
          "DATA_LANGUAGE_MISMATCH",
          `数据语言不匹配：${sourcePort.dataLanguage} → ${targetPort.dataLanguage}`,
          { edge_id: edge.id },
        ),
      );
    }
    if (source.kind === "region" && edge.source_port_id === REGION_BOUNDARY_OUT_PORT) {
      const targetNode = nodeById.get(edge.target_node_id);
      if (targetNode === undefined || targetNode.kind !== "simulation") {
        diagnostics.push(
          diagnostic("error", "CONNECTION_INVALID", "配置区域边界输出只能连接模拟节点输入", {
            edge_id: edge.id,
          }),
        );
      }
    }
    if (source.kind === "node" && sourcePort.id === "out" && target.kind === "region") {
      const sourceNode = nodeById.get(edge.source_node_id);
      if (sourceNode !== undefined && sourceNode.kind === "simulation") {
        diagnostics.push(
          diagnostic("error", "ANALYSIS_NOT_IMPLEMENTED", "模拟节点输出与分析区域连线不在 MVP 范围", {
            edge_id: edge.id,
          }),
        );
      }
    }
  }

  const freeNodeId = isFreeConnectedNode(source, nodeById)
    ? source.id
    : isFreeConnectedNode(target, nodeById)
      ? target.id
      : null;
  if (freeNodeId !== null) {
    diagnostics.push(
      diagnostic("error", "FREE_NODE_CONNECTED", "游离草稿节点不能参与连线", {
        edge_id: edge.id,
        node_id: freeNodeId,
      }),
    );
  }

  for (const [endpointId, portId, role] of [
    [edge.source_node_id, edge.source_port_id, "source"],
    [edge.target_node_id, edge.target_port_id, "target"],
  ] as const) {
    const key = `${endpointId}:${portId}:${role}`;
    connectionCounts.set(key, (connectionCounts.get(key) ?? 0) + 1);
    const port = resolvePort(endpointId, portId, role, regionById, nodeById);
    const count = connectionCounts.get(key) ?? 0;
    if (port !== null && count > port.connectionLimit) {
      diagnostics.push(
        diagnostic("error", "CONNECTION_LIMIT_EXCEEDED", `端口连接数超过上限：${endpointId}.${portId}`, {
          edge_id: edge.id,
        }),
      );
    }
  }
}

function isFreeConnectedNode(endpoint: Endpoint, nodeById: Map<string, WorkflowNode>): boolean {
  if (endpoint.kind !== "node") {
    return false;
  }
  const node = nodeById.get(endpoint.id);
  if (node === undefined || node.region_id !== null) {
    return false;
  }
  const spec = getNodeKindSpec(node.kind);
  return spec === null || spec.region !== null;
}

function validateRegionEndpoint(
  edge: WorkflowEdge,
  regionId: string,
  role: "source" | "target",
  regionById: Map<string, WorkflowRegion>,
  diagnostics: Diagnostic[],
): void {
  const region = regionById.get(regionId);
  if (region === undefined) {
    return;
  }
  if (region.kind === "analysis") {
    diagnostics.push(
      diagnostic("error", "ANALYSIS_NOT_IMPLEMENTED", "分析区域连线不在 MVP 范围", {
        edge_id: edge.id,
        region_id: regionId,
      }),
    );
    return;
  }
  const portId = role === "source" ? edge.source_port_id : edge.target_port_id;
  const expected = REGION_BOUNDARY_OUT_PORT;
  if (portId !== expected) {
    diagnostics.push(
      diagnostic("error", "PORT_INVALID", `区域边界端口方向错误：${portId}`, {
        edge_id: edge.id,
        region_id: regionId,
      }),
    );
  }
}

function validateNodeEndpoint(
  edge: WorkflowEdge,
  nodeId: string,
  role: "source" | "target",
  nodeById: Map<string, WorkflowNode>,
  diagnostics: Diagnostic[],
): void {
  const node = nodeById.get(nodeId);
  if (node === undefined) {
    return;
  }
  const spec = getNodeKindSpec(node.kind);
  if (spec === null) {
    return;
  }
  const portId = role === "source" ? edge.source_port_id : edge.target_port_id;
  if (role === "source" && isProjectionPort(node, portId)) {
    if (!memberItemIds(node).includes(projectionItemId(portId))) {
      diagnostics.push(
        diagnostic("error", "PORT_NOT_FOUND", `节点缺少端口：${nodeId}.${portId}`, {
          edge_id: edge.id,
          node_id: nodeId,
        }),
      );
    }
    return;
  }
  const ports = role === "source" ? spec.ports.outputs : spec.ports.inputs;
  if (!ports.some((port) => port.id === portId)) {
    diagnostics.push(
      diagnostic("error", "PORT_NOT_FOUND", `节点缺少端口：${nodeId}.${portId}`, {
        edge_id: edge.id,
        node_id: nodeId,
      }),
    );
  }
}

function resolvePort(
  endpointId: string,
  portId: string,
  role: "source" | "target",
  regionById: Map<string, WorkflowRegion>,
  nodeById: Map<string, WorkflowNode>,
) {
  const region = regionById.get(endpointId);
  if (region !== undefined) {
    return {
      id: portId,
      cardinality: role === "source" ? "group" : "single",
      dataLanguage: role === "source" ? "input_document" : "fragment",
      connectionLimit: role === "source" ? 1 : Number.POSITIVE_INFINITY,
    } as const;
  }
  const node = nodeById.get(endpointId);
  if (node === undefined) {
    return null;
  }
  const spec = getNodeKindSpec(node.kind);
  if (spec === null) {
    return null;
  }
  if (role === "source" && isProjectionPort(node, portId)) {
    return {
      id: portId,
      cardinality: "single",
      dataLanguage: "fragment",
      connectionLimit: Number.POSITIVE_INFINITY,
    } as const;
  }
  const ports = role === "source" ? spec.ports.outputs : spec.ports.inputs;
  return ports.find((port) => port.id === portId) ?? null;
}

function markCycles(
  definition: WorkflowDefinition,
  endpoints: Map<string, Endpoint>,
  diagnostics: Diagnostic[],
): void {
  const adjacency = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    if (!endpoints.has(edge.source_node_id) || !endpoints.has(edge.target_node_id)) {
      continue;
    }
    const list = adjacency.get(edge.source_node_id) ?? [];
    list.push(edge);
    adjacency.set(edge.source_node_id, list);
  }

  const state = new Map<string, "visiting" | "visited">();
  const stack: string[] = [];
  for (const id of endpoints.keys()) {
    if (state.get(id) === "visited") {
      continue;
    }
    if (visit(id, adjacency, state, stack, diagnostics)) {
      return;
    }
  }
}

function visit(
  id: string,
  adjacency: Map<string, WorkflowEdge[]>,
  state: Map<string, "visiting" | "visited">,
  stack: string[],
  diagnostics: Diagnostic[],
): boolean {
  state.set(id, "visiting");
  stack.push(id);
  for (const edge of adjacency.get(id) ?? []) {
    const next = edge.target_node_id;
    if (state.get(next) === "visited") {
      continue;
    }
    if (state.get(next) === "visiting") {
      const start = stack.indexOf(next);
      for (const cycleId of stack.slice(start).concat(next)) {
        diagnostics.push(
          diagnostic("error", "CYCLE_DETECTED", "工作流图存在环", {
            edge_id: edge.id,
            node_id: cycleId,
          }),
        );
      }
      return true;
    }
    if (visit(next, adjacency, state, stack, diagnostics)) {
      return true;
    }
  }
  stack.pop();
  state.set(id, "visited");
  return false;
}

function validateMemberCap(
  definition: WorkflowDefinition,
  regionById: Map<string, WorkflowRegion>,
  connectedToSimulation: Set<string>,
  diagnostics: Diagnostic[],
): void {
  for (const region of regionById.values()) {
    if (region.kind !== "configuration") {
      continue;
    }
    const boundaryEdges = definition.edges.filter(
      (edge) =>
        edge.target_node_id === region.id && edge.target_port_id === REGION_BOUNDARY_OUT_PORT,
    );
    if (boundaryEdges.length === 0) {
      // 仅连接了模拟节点的区域，空汇入才意味着批次无法成立（决策 2.32）。
      if (connectedToSimulation.has(region.id)) {
        diagnostics.push(
          diagnostic("warning", "EMPTY_REGION", "配置区域没有数据汇入，所连批次无法成立", {
            region_id: region.id,
          }),
        );
      }
      continue;
    }
    const result = expandConfigurationRegion(definition, region.id);
    if (!result.ok) {
      for (const item of result.diagnostics) {
        if (item.code === "MEMBER_LIMIT_EXCEEDED") {
          diagnostics.push(item);
        }
      }
    } else if (result.members.length > MAX_BATCH_MEMBERS) {
      diagnostics.push(
        diagnostic(
          "error",
          "MEMBER_LIMIT_EXCEEDED",
          `展开成员数 ${result.members.length} 超过上限 ${MAX_BATCH_MEMBERS}`,
          { region_id: region.id },
        ),
      );
    }
  }
}

/** 同一配置区域内，同类别的角色/武器/圣遗物节点不能重复占用同一队伍槽位。 */
function validateTeamSlotConflicts(
  definition: WorkflowDefinition,
  regionById: Map<string, WorkflowRegion>,
  diagnostics: Diagnostic[],
): void {
  const nodesByRegionKindSlot = new Map<
    string,
    Map<string, Map<number, WorkflowNode[]>>
  >();
  for (const node of definition.nodes) {
    const regionId = node.region_id;
    if (regionId === null) {
      continue;
    }
    const region = regionById.get(regionId);
    if (region === undefined || region.kind !== "configuration") {
      continue;
    }
    if (node.kind !== "character" && node.kind !== "weapon" && node.kind !== "artifact") {
      continue;
    }
    const slot = nodeSlot(node);
    if (slot === null) {
      continue;
    }
    const byKind = nodesByRegionKindSlot.get(regionId) ?? new Map<string, Map<number, WorkflowNode[]>>();
    const bySlot = byKind.get(node.kind) ?? new Map<number, WorkflowNode[]>();
    const list = bySlot.get(slot) ?? [];
    list.push(node);
    bySlot.set(slot, list);
    byKind.set(node.kind, bySlot);
    nodesByRegionKindSlot.set(regionId, byKind);
  }

  for (const [regionId, byKind] of nodesByRegionKindSlot) {
    for (const [kind, bySlot] of byKind) {
      for (const [slot, nodes] of bySlot) {
        if (nodes.length < 2) {
          continue;
        }
        for (const node of nodes) {
          diagnostics.push(
            diagnostic(
              "error",
              "TEAM_SLOT_CONFLICT",
              `队伍槽位 ${slot} 被多个${kind === "character" ? "角色" : kind === "weapon" ? "武器" : "圣遗物"}节点占用`,
              {
                node_id: node.id,
                region_id: regionId,
              },
            ),
          );
        }
      }
    }
  }
}

function nodeSlot(node: WorkflowNode): number | null {
  const value = node.params.slot;
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

/** 节点卡片默认尺寸，用于判断区域是否可能遮挡内容；实际高度以渲染为准。 */
const DEFAULT_NODE_CARD_WIDTH = 260;
const DEFAULT_NODE_CARD_HEIGHT = 80;

function warnNodesOutsideRegions(
  definition: WorkflowDefinition,
  regionById: Map<string, WorkflowRegion>,
  diagnostics: Diagnostic[],
): void {
  for (const region of regionById.values()) {
    for (const node of definition.nodes) {
      if (node.region_id !== region.id) {
        continue;
      }
      const spec = getNodeKindSpec(node.kind);
      if (spec === null || spec.region === null) {
        continue;
      }
      const inside =
        node.position.x >= region.rect.x &&
        node.position.y >= region.rect.y &&
        node.position.x + DEFAULT_NODE_CARD_WIDTH <= region.rect.x + region.rect.width &&
        node.position.y + DEFAULT_NODE_CARD_HEIGHT <= region.rect.y + region.rect.height;
      if (!inside) {
        diagnostics.push(
          diagnostic(
            "warning",
            "NODE_OUTSIDE_REGION",
            "节点超出区域边界，缩小区域可能遮挡内容",
            { node_id: node.id, region_id: region.id },
          ),
        );
      }
    }
  }
}

function diagnostic(
  severity: DiagnosticSeverity,
  code: string,
  message: string,
  refs: {
    node_id?: string | null;
    edge_id?: string | null;
    region_id?: string | null;
    path?: string | null;
  } = {},
): Diagnostic {
  return {
    severity,
    code,
    message,
    node_id: refs.node_id ?? null,
    edge_id: refs.edge_id ?? null,
    region_id: refs.region_id ?? null,
    path: refs.path ?? null,
  };
}
