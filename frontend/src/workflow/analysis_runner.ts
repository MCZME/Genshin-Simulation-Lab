/**
 * 分析区域执行：把区域内可达子图编译为查询计划，一次端点调用完成。
 *
 * 执行模型（契约 v2）：前端只做可达性、拓扑序与参数收集；
 * SQL 由后端编译，中间结果不出后端；响应携带视图终端表。
 */

import { executeAnalysisQuery } from "../api/client";
import type { AnalysisTableResponse } from "../api/client";
import type { AnalysisTableResult } from "./templates";
import { REGION_BOUNDARY_IN_PORT } from "./types";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";

export interface AnalysisNodeResult {
  status: "idle" | "loading" | "ready" | "error" | "stale";
  table?: AnalysisTableResult;
  error?: string;
}

export function createIdleResult(): AnalysisNodeResult {
  return { status: "idle" };
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/** 解析分析区域边界输入的会话组：多源按连线顺序合并并保序去重。 */
export function resolveBoundarySessionGroup(
  definition: WorkflowDefinition,
  regionId: string,
): string[] {
  const sessionIds: string[] = [];
  const seen = new Set<string>();
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const edges = definition.edges
    .filter(
      (edge) =>
        edge.target_node_id === regionId && edge.target_port_id === REGION_BOUNDARY_IN_PORT,
    )
    .sort((left, right) => edgeOrder(definition, left.id) - edgeOrder(definition, right.id));
  for (const edge of edges) {
    const source = nodeById.get(edge.source_node_id);
    let values: string[] = [];
    if (source?.kind === "simulation") {
      values = asStringArray(source.params.last_sessions);
    } else if (source?.kind === "data_provider") {
      values = asStringArray(source.params.session_ids);
    }
    for (const value of values) {
      if (!seen.has(value)) {
        seen.add(value);
        sessionIds.push(value);
      }
    }
  }
  return sessionIds;
}

function edgeOrder(definition: WorkflowDefinition, edgeId: string): number {
  return definition.edges.findIndex((edge) => edge.id === edgeId);
}

const FETCH_KINDS = new Set(["fetch"]);
const TABLE_NODE_KINDS = new Set([
  ...FETCH_KINDS,
  "filter",
  "project",
  "sort",
  "aggregate",
  "limit",
  "join",
  "compute",
]);

/** 区域内取数节点：边界输入的直接消费者（会话组经边界注入）。 */
export function planFetchNodes(
  definition: WorkflowDefinition,
  regionId: string,
): WorkflowNode[] {
  const regionNodes = new Set(
    definition.nodes
      .filter((node) => node.region_id === regionId && TABLE_NODE_KINDS.has(node.kind))
      .map((node) => node.id),
  );
  const fedFetches = new Set(
    definition.edges
      .filter((edge) => edge.source_node_id === regionId && regionNodes.has(edge.target_node_id))
      .map((edge) => edge.target_node_id),
  );
  return definition.nodes.filter((node) => fedFetches.has(node.id));
}

/** 从取数节点沿算子边可达的节点集合（含取数节点本身）。 */
function reachableTableNodes(
  definition: WorkflowDefinition,
  regionId: string,
): WorkflowNode[] {
  const regionNodes = new Map(
    definition.nodes
      .filter((node) => node.region_id === regionId)
      .map((node) => [node.id, node]),
  );
  const outgoing = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    const list = outgoing.get(edge.source_node_id) ?? [];
    list.push(edge);
    outgoing.set(edge.source_node_id, list);
  }
  const result: WorkflowNode[] = [];
  const seen = new Set<string>();
  const queue = planFetchNodes(definition, regionId).map((node) => node.id);
  for (const id of queue) {
    seen.add(id);
  }
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const node = regionNodes.get(current);
    if (node !== undefined) {
      result.push(node);
    }
    for (const edge of outgoing.get(current) ?? []) {
      const target = regionNodes.get(edge.target_node_id);
      if (
        !seen.has(edge.target_node_id) &&
        target !== undefined &&
        TABLE_NODE_KINDS.has(target.kind)
      ) {
        // 视图不是表节点，不进入计划，也不阻断其上游链的遍历。
        seen.add(edge.target_node_id);
        queue.push(edge.target_node_id);
      }
    }
  }
  return result;
}

/** 计划输出清单：区域内不再被其他表节点或视图消费的终端表。 */
export function planOutputs(definition: WorkflowDefinition, regionId: string): string[] {
  const nodes = reachableTableNodes(definition, regionId);
  const consumed = new Set<string>();
  for (const edge of definition.edges) {
    if (nodes.some((node) => node.id === edge.source_node_id)) {
      consumed.add(edge.source_node_id);
    }
  }
  // 被视图消费不算被下游表节点消费：视图输入源必须是计划输出。
  const viewSources = new Set(
    definition.edges
      .filter((edge) => {
        const target = definition.nodes.find((node) => node.id === edge.target_node_id);
        return (
          target !== undefined &&
          target.region_id === regionId &&
          !TABLE_NODE_KINDS.has(target.kind)
        );
      })
      .map((edge) => edge.source_node_id),
  );
  return nodes
    .filter((node) => !consumed.has(node.id) || viewSources.has(node.id))
    .map((node) => node.id);
}

function orderedInputs(
  definition: WorkflowDefinition,
  nodeId: string,
): { params: Record<string, unknown>; inputs: string[] } {
  const node = definition.nodes.find((item) => item.id === nodeId);
  const edgesInto = definition.edges
    .filter((edge) => edge.target_node_id === nodeId)
    .sort((left, right) => edgeOrder(definition, left.id) - edgeOrder(definition, right.id));
  // 只把表节点之间的连线作为算子输入；区域边界注入的会话组不进入 inputs。
  const tableEdges = edgesInto.filter((edge) => {
    const source = definition.nodes.find((item) => item.id === edge.source_node_id);
    return source !== undefined && TABLE_NODE_KINDS.has(source.kind);
  });
  if (node?.kind === "join") {
    const byPort = new Map(tableEdges.map((edge) => [edge.target_port_id, edge.source_node_id]));
    const left = byPort.get("left");
    const right = byPort.get("right");
    if (left !== undefined && right !== undefined) {
      return { params: node.params, inputs: [left, right] };
    }
  }
  return {
    params: node?.params ?? {},
    inputs: tableEdges.map((edge) => edge.source_node_id),
  };
}

/** 编译查询计划请求（契约 v2 第 6.1 节形状）。 */
export function buildAnalysisPlanRequest(
  definition: WorkflowDefinition,
  regionId: string,
): {
  session_ids: string[];
  nodes: { id: string; kind: string; params: Record<string, unknown>; inputs: string[] }[];
  outputs: string[];
} {
  const nodes = reachableTableNodes(definition, regionId);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const outgoing = new Map<string, number>();
  for (const edge of definition.edges) {
    if (nodeById.has(edge.source_node_id)) {
      outgoing.set(edge.source_node_id, (outgoing.get(edge.source_node_id) ?? 0) + 1);
    }
  }
  const viewSources = new Set(
    definition.edges
      .filter((edge) => {
        const target = definition.nodes.find((node) => node.id === edge.target_node_id);
        return (
          target !== undefined &&
          target.region_id === regionId &&
          !TABLE_NODE_KINDS.has(target.kind)
        );
      })
      .map((edge) => edge.source_node_id),
  );
  const ordered = topologicalOrder(nodes, definition);
  return {
    session_ids: resolveBoundarySessionGroup(definition, regionId),
    nodes: ordered.map((node) => {
      const wired = orderedInputs(definition, node.id);
      return { id: node.id, kind: node.kind, params: wired.params, inputs: wired.inputs };
    }),
    outputs: nodes
      .filter((node) => (outgoing.get(node.id) ?? 0) === 0 || viewSources.has(node.id))
      .map((node) => node.id),
  };
}

/** 对可达表节点做稳定拓扑排序（Kahn，节点原始顺序保序）。 */
function topologicalOrder(
  nodes: WorkflowNode[],
  definition: WorkflowDefinition,
): WorkflowNode[] {
  const ids = new Set(nodes.map((node) => node.id));
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, number>(nodes.map((node) => [node.id, 0]));
  const dependents = new Map<string, string[]>();
  for (const edge of definition.edges) {
    if (!ids.has(edge.source_node_id) || !ids.has(edge.target_node_id)) {
      continue;
    }
    incoming.set(edge.target_node_id, (incoming.get(edge.target_node_id) ?? 0) + 1);
    const list = dependents.get(edge.source_node_id) ?? [];
    list.push(edge.target_node_id);
    dependents.set(edge.source_node_id, list);
  }
  const queue = nodes
    .filter((node) => (incoming.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const ordered: WorkflowNode[] = [];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const node = byId.get(current);
    if (node !== undefined) {
      ordered.push(node);
    }
    for (const next of dependents.get(current) ?? []) {
      const count = (incoming.get(next) ?? 0) - 1;
      incoming.set(next, count);
      if (count === 0) {
        queue.push(next);
      }
    }
  }
  return ordered;
}

export type ExecuteAnalysisQueryFn = typeof executeAnalysisQuery;

/** 顺序执行分析区域：编译计划并一次调用查询端点，返回各终端表状态。 */
export async function executeAnalysisRegion(
  definition: WorkflowDefinition,
  regionId: string,
  execute: ExecuteAnalysisQueryFn = executeAnalysisQuery,
): Promise<Map<string, AnalysisNodeResult>> {
  const results = new Map<string, AnalysisNodeResult>();
  const request = buildAnalysisPlanRequest(definition, regionId);
  try {
    const response = await execute(request);
    for (const [nodeId, table] of Object.entries(response.tables)) {
      results.set(nodeId, { status: "ready", table: toAnalysisTableResult(table) });
    }
    for (const nodeId of request.outputs) {
      if (!results.has(nodeId)) {
        results.set(nodeId, { status: "error", error: "查询结果缺少该节点的输出表" });
      }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    for (const nodeId of request.outputs) {
      results.set(nodeId, { status: "error", error: message });
    }
  }
  return results;
}

function toAnalysisTableResult(table: AnalysisTableResponse): AnalysisTableResult {
  return {
    columns: table.columns.map((column) => ({ name: column.name, type: column.type })),
    rows: table.rows,
    truncated: table.truncated,
  };
}

/** 视图数据输入：多条同结构入线的行拼接（单表语义）。 */
export function viewInputTable(
  viewNodeId: string,
  definition: WorkflowDefinition,
  results: Map<string, AnalysisNodeResult>,
): import("./templates").AnalysisTableResult | null {
  const dataEdges = definition.edges.filter(
    (edge) => edge.target_node_id === viewNodeId && edge.target_port_id === "in",
  );
  const tables: NonNullable<AnalysisNodeResult["table"]>[] = [];
  for (const edge of dataEdges) {
    const result = results.get(edge.source_node_id);
    if (result?.status !== "ready" || result.table === undefined) {
      return null;
    }
    tables.push(result.table);
  }
  if (tables.length === 0) {
    return null;
  }
  return {
    columns: tables[0].columns,
    rows: tables.flatMap((table) => table.rows),
    truncated: tables.some((table) => table.truncated),
  };
}
