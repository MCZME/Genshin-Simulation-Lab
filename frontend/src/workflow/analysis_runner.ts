/**
 * 分析区域执行：把区域内可达子图编译为查询计划，一次端点调用完成。
 *
 * 执行模型（契约 v2）：前端只做可达性、拓扑序与参数收集；
 * SQL 由后端编译，中间结果不出后端；响应携带视图终端表。
 */

import {
  closeAnalysisContext,
  createAnalysisContext,
  executeAnalysisNode,
  executeAnalysisQuery,
  mergeAnalysisStages,
} from "../api/client";
import type {
  AnalysisTableResponse,
  CreateAnalysisContextResponse,
  NodeExecutionRequest,
  StageResponse,
} from "../api/client";
import {
  ANALYSIS_VIEW_NODE_KINDS,
  type AnalysisTableResult,
} from "./templates";
import { REGION_BOUNDARY_IN_PORT } from "./types";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";

export interface AnalysisNodeResult {
  status: "idle" | "loading" | "ready" | "error" | "stale";
  table?: AnalysisTableResult;
  /** 节点运行时物化的后端阶段引用。 */
  stage_id?: string;
  /** 获取单行节点计算的 item（上游表第一行）。 */
  item?: unknown;
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
  "derive",
]);
const CONFIG_NODE_KINDS = new Set(["table_config", "pie_config", "bar_config"]);

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

function isStageNodeKind(kind: string): boolean {
  return TABLE_NODE_KINDS.has(kind) || ANALYSIS_VIEW_NODE_KINDS.has(kind);
}

/** 展示配置节点是数据链转发：解析到它背后真正的表/视图阶段源。 */
function resolveStageSource(
  definition: WorkflowDefinition,
  sourceId: string,
): string | null {
  const seen = new Set<string>();
  let current = sourceId;
  while (!seen.has(current)) {
    seen.add(current);
    const node = definition.nodes.find((item) => item.id === current);
    if (node === undefined || !CONFIG_NODE_KINDS.has(node.kind)) {
      return node === undefined ? null : current;
    }
    const input = definition.edges.find(
      (edge) => edge.target_node_id === current && edge.target_port_id === "in",
    );
    if (input === undefined) {
      return null;
    }
    current = input.source_node_id;
  }
  return null;
}

/** 节点运行时输入：join 按端口，其余按入线顺序并解析展示配置转发。 */
function stageInputIdsFor(
  definition: WorkflowDefinition,
  node: WorkflowNode,
): string[] {
  const edges = definition.edges
    .filter((edge) => edge.target_node_id === node.id)
    .sort((left, right) => edgeOrder(definition, left.id) - edgeOrder(definition, right.id));
  const resolved: string[] = [];
  const push = (edge: WorkflowEdge) => {
    const sourceId = resolveStageSource(definition, edge.source_node_id);
    const sourceNode =
      sourceId === null ? undefined : definition.nodes.find((item) => item.id === sourceId);
    if (
      sourceId !== null &&
      sourceNode !== undefined &&
      isStageNodeKind(sourceNode.kind) &&
      !resolved.includes(sourceId)
    ) {
      resolved.push(sourceId);
    }
  };
  if (node.kind === "join") {
    for (const port of ["left", "right"]) {
      const edge = edges.find((item) => item.target_port_id === port);
      if (edge !== undefined) {
        push(edge);
      }
    }
    return resolved;
  }
  for (const edge of edges) {
    push(edge);
  }
  return resolved;
}

/**
 * 收集节点运行时需要执行的阶段节点：取数/表算子 + 饼图/柱状图输入阶段。
 * 视图不输出 data 透传；selection 下游只在用户点击后由选择分支执行。
 */
function collectStageNodeIds(
  definition: WorkflowDefinition,
  regionId: string,
): string[] {
  const regionNodeIds = new Set(
    definition.nodes
      .filter((node) => node.region_id === regionId)
      .map((node) => node.id),
  );
  const seen = new Set<string>();
  const queue = planFetchNodes(definition, regionId).map((node) => node.id);
  for (const id of queue) {
    seen.add(id);
  }
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const currentNode = definition.nodes.find((item) => item.id === current);
    const currentIsView =
      currentNode !== undefined && ANALYSIS_VIEW_NODE_KINDS.has(currentNode.kind);
    for (const edge of definition.edges.filter(
      (item) => item.source_node_id === current,
    )) {
      const target = definition.nodes.find((item) => item.id === edge.target_node_id);
      if (target === undefined || !regionNodeIds.has(target.id) || seen.has(target.id)) {
        continue;
      }
      if (
        currentIsView &&
        edge.source_port_id === "selection"
      ) {
        continue;
      }
      if (target.kind === "table_config" || target.kind === "pie_config" || target.kind === "bar_config") {
        for (const configEdge of definition.edges.filter(
          (item) => item.source_node_id === target.id,
        )) {
          const configTarget = definition.nodes.find(
            (item) => item.id === configEdge.target_node_id,
          );
          if (
            configTarget !== undefined &&
            regionNodeIds.has(configTarget.id) &&
            (configTarget.kind === "pie" || configTarget.kind === "bar")
          ) {
            seen.add(configTarget.id);
            queue.push(configTarget.id);
          }
        }
        continue;
      }
      if (
        isStageNodeKind(target.kind) &&
        (TABLE_NODE_KINDS.has(target.kind) ||
          target.kind === "pie" ||
          target.kind === "bar")
      ) {
        seen.add(target.id);
        queue.push(target.id);
      }
    }
  }
  return Array.from(seen);
}

/** 节点运行时执行计划：阶段节点拓扑序 + 已解析输入。 */
export function buildStageRegionPlan(
  definition: WorkflowDefinition,
  regionId: string,
): {
  session_ids: string[];
  nodes: { id: string; kind: string; params: Record<string, unknown>; inputs: string[] }[];
} {
  const ids = collectStageNodeIds(definition, regionId);
  const byId = new Map(
    definition.nodes
      .filter((node) => ids.includes(node.id))
      .map((node) => [node.id, node]),
  );
  const inputsOf = new Map<string, string[]>();
  for (const id of ids) {
    const node = byId.get(id);
    if (node !== undefined) {
      inputsOf.set(
        id,
        stageInputIdsFor(definition, node).filter((inputId) => ids.includes(inputId)),
      );
    }
  }
  const ordered: string[] = [];
  const remaining = new Set(ids);
  while (remaining.size > 0) {
    const ready = Array.from(remaining)
      .filter((id) => (inputsOf.get(id) ?? []).every((inputId) => !remaining.has(inputId)))
      .sort((left, right) => byId.get(left)?.id.localeCompare(byId.get(right)?.id ?? "") ?? 0);
    if (ready.length === 0) {
      break;
    }
    for (const id of ready) {
      ordered.push(id);
      remaining.delete(id);
    }
  }
  return {
    session_ids: resolveBoundarySessionGroup(definition, regionId),
    nodes: ordered.map((id) => {
      const node = byId.get(id);
      return {
        id,
        kind: node?.kind ?? "fetch",
        params: node?.params ?? {},
        inputs: inputsOf.get(id) ?? [],
      };
    }),
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

export type CreateAnalysisContextFn = (
  sessionIds: string[],
) => Promise<CreateAnalysisContextResponse>;
export type ExecuteAnalysisNodeFn = (
  contextId: string,
  execution: NodeExecutionRequest,
) => Promise<StageResponse>;
export type CloseAnalysisContextFn = (contextId: string) => Promise<void>;
export type MergeAnalysisStagesFn = (
  contextId: string,
  stageIds: string[],
) => Promise<StageResponse>;

export interface RegionStageRun {
  /** 保留给交互选择的后端上下文；调用方负责关闭。 */
  context_id: string | null;
  results: Map<string, AnalysisNodeResult>;
}

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

/**
 * 节点运行时执行（草案：分析节点运行时/阶段执行）：
 * 后端为每个节点独立执行并物化阶段；前端按拓扑序提交节点，不再整图一次查询。
 */
export async function executeAnalysisRegionByNodes(
  definition: WorkflowDefinition,
  regionId: string,
  executeNode: ExecuteAnalysisNodeFn = executeAnalysisNode,
  createContext: CreateAnalysisContextFn = createAnalysisContext,
  closeContext: CloseAnalysisContextFn = closeAnalysisContext,
  mergeStages: MergeAnalysisStagesFn = mergeAnalysisStages,
): Promise<Map<string, AnalysisNodeResult>> {
  const run = await runAnalysisRegionStages(
    definition,
    regionId,
    false,
    executeNode,
    createContext,
    closeContext,
    mergeStages,
  );
  return run.results;
}

/** 执行分析区域并把后端节点运行时上下文保留给交互使用。 */
export async function runAnalysisRegionStages(
  definition: WorkflowDefinition,
  regionId: string,
  keepContext = true,
  executeNode: ExecuteAnalysisNodeFn = executeAnalysisNode,
  createContext: CreateAnalysisContextFn = createAnalysisContext,
  closeContext: CloseAnalysisContextFn = closeAnalysisContext,
  mergeStages: MergeAnalysisStagesFn = mergeAnalysisStages,
): Promise<RegionStageRun> {
  const request = buildStageRegionPlan(definition, regionId);
  const results = new Map<string, AnalysisNodeResult>();
  if (request.nodes.length === 0) {
    return { context_id: null, results };
  }
  let contextId: string | null;
  try {
    const created = await createContext(request.session_ids);
    contextId = created.context_id;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    for (const node of request.nodes) {
      results.set(node.id, { status: "error", error: message });
    }
    return { context_id: null, results };
  }
  try {
    for (const node of request.nodes) {
      const inputErrors = node.inputs
        .map((inputId) => results.get(inputId))
        .filter((item) => item?.status === "error");
      if (inputErrors.length > 0) {
        const first = inputErrors[0];
        results.set(node.id, {
          status: "error",
          error: first?.error ?? "上游节点失败",
        });
        continue;
      }
      try {
        if (ANALYSIS_VIEW_NODE_KINDS.has(node.kind)) {
          const inputStages = node.inputs
            .map((inputId) => results.get(inputId)?.stage_id)
            .filter((stageId): stageId is string => stageId !== undefined);
          if (inputStages.length === 0) {
            results.set(node.id, {
              status: "error",
              error: "视图缺少可物化的数据输入",
            });
            continue;
          }
          if (inputStages.length === 1) {
            results.set(node.id, {
              status: "ready",
              stage_id: inputStages[0],
            });
          } else {
            const merged = await mergeStages(contextId, inputStages);
            results.set(node.id, {
              status: "ready",
              stage_id: merged.stage_id,
            });
          }
        } else {
          const stage = await executeNode(contextId, {
            node_id: node.id,
            kind: node.kind,
            params: node.params,
            input_stages: node.inputs
              .map((inputId) => results.get(inputId)?.stage_id)
              .filter((stageId): stageId is string => stageId !== undefined),
          });
          results.set(node.id, {
            status: "ready",
            table: toAnalysisTableResult(stage),
            stage_id: stage.stage_id,
          });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        results.set(node.id, { status: "error", error: message });
      }
    }
  } finally {
    if (contextId !== null && !keepContext) {
      try {
        await closeContext(contextId);
      } catch {
        // 上下文回收失败不覆盖节点结果；阶段会随后端超时回收。
      }
    }
  }
  return { context_id: contextId, results };
}

/**
 * 执行由视图选择阶段驱动的下游分支：
 * 表格/图表点击已由后端物化为选择阶段，这里从选择阶段按拓扑序执行后续表算子。
 */
export async function executeAnalysisSelectionBranch(
  definition: WorkflowDefinition,
  regionId: string,
  viewId: string,
  contextId: string,
  selectionStageId: string,
  existingStages: ReadonlyMap<string, string>,
  executeNode: ExecuteAnalysisNodeFn = executeAnalysisNode,
): Promise<Map<string, AnalysisNodeResult>> {
  const regionNodeIds = new Set(
    definition.nodes
      .filter((node) => node.region_id === regionId && TABLE_NODE_KINDS.has(node.kind))
      .map((node) => node.id),
  );
  const branchIds = new Set<string>();
  const queue: string[] = [];
  for (const edge of definition.edges) {
    if (
      edge.source_node_id === viewId &&
      edge.source_port_id === "selection" &&
      regionNodeIds.has(edge.target_node_id)
    ) {
      branchIds.add(edge.target_node_id);
      queue.push(edge.target_node_id);
    }
  }
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const edge of definition.edges) {
      if (
        edge.source_node_id === current &&
        regionNodeIds.has(edge.target_node_id) &&
        !branchIds.has(edge.target_node_id)
      ) {
        branchIds.add(edge.target_node_id);
        queue.push(edge.target_node_id);
      }
    }
  }

  const byId = new Map(
    definition.nodes
      .filter((node) => branchIds.has(node.id))
      .map((node) => [node.id, node]),
  );
  const results = new Map<string, AnalysisNodeResult>();
  const ordered: string[] = [];
  const processed = new Set<string>();
  const remaining = new Set(branchIds);
  while (remaining.size > 0) {
    const ready = Array.from(remaining).filter((id) => {
      const node = byId.get(id);
      if (node === undefined) {
        return true;
      }
      return branchDependenciesFor(definition, node, viewId, byId).every(
        (item) => processed.has(item),
      );
    });
    if (ready.length === 0) {
      for (const id of remaining) {
        ordered.push(id);
      }
      break;
    }
    for (const id of ready.sort()) {
      ordered.push(id);
      remaining.delete(id);
      processed.add(id);
    }
  }

  for (const nodeId of ordered) {
    const node = byId.get(nodeId);
    if (node === undefined) {
      continue;
    }
    const inputs = branchInputsFor(
      definition,
      node,
      viewId,
      selectionStageId,
      existingStages,
      results,
      byId,
    );
    const missing = inputs.some((item) => item === null);
    if (missing) {
      results.set(nodeId, {
        status: "error",
        error: "选择分支缺少可用的上游阶段",
      });
      continue;
    }
    try {
      const stage = await executeNode(contextId, {
        node_id: node.id,
        kind: node.kind,
        params: node.params,
        input_stages: inputs.filter((item): item is string => item !== null),
      });
      results.set(node.id, {
        status: "ready",
        table: toAnalysisTableResult(stage),
        stage_id: stage.stage_id,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      results.set(node.id, { status: "error", error: message });
    }
  }
  return results;
}

function branchDependenciesFor(
  definition: WorkflowDefinition,
  node: WorkflowNode,
  viewId: string,
  byId: Map<string, WorkflowNode>,
): string[] {
  const result: string[] = [];
  for (const edge of definition.edges) {
    if (
      edge.target_node_id === node.id &&
      !(edge.source_node_id === viewId && edge.source_port_id === "selection") &&
      byId.has(edge.source_node_id) &&
      !result.includes(edge.source_node_id)
    ) {
      result.push(edge.source_node_id);
    }
  }
  return result;
}

function branchInputsFor(
  definition: WorkflowDefinition,
  node: WorkflowNode,
  viewId: string,
  selectionStageId: string,
  existingStages: ReadonlyMap<string, string>,
  branchResults: Map<string, AnalysisNodeResult>,
  branchById: Map<string, WorkflowNode>,
): (string | null)[] {
  const edges = definition.edges
    .filter((edge) => edge.target_node_id === node.id)
    .sort((left, right) => edgeOrder(definition, left.id) - edgeOrder(definition, right.id));
  const orderedEdges =
    node.kind === "join"
      ? (["left", "right"] as const)
          .map((port) => edges.find((edge) => edge.target_port_id === port))
          .filter((edge): edge is WorkflowEdge => edge !== undefined)
      : edges;
  const inputs: (string | null)[] = [];
  for (const edge of orderedEdges) {
    if (edge.source_node_id === viewId && edge.source_port_id === "selection") {
      inputs.push(selectionStageId);
      continue;
    }
    if (branchById.has(edge.source_node_id)) {
      const branchStage = branchResults.get(edge.source_node_id)?.stage_id;
      if (branchStage !== undefined) {
        inputs.push(branchStage);
      } else {
        // 本次分支内的上游失败/未执行时不得回退旧阶段，避免旧数据流入下游。
        inputs.push(null);
      }
      continue;
    }
    const existing = existingStages.get(edge.source_node_id);
    if (existing !== undefined) {
      inputs.push(existing);
      continue;
    }
    inputs.push(null);
  }
  return inputs;
}

function toAnalysisTableResult(table: AnalysisTableResponse): AnalysisTableResult {
  return {
    columns: table.columns.map((column) => ({ name: column.name, type: column.type })),
    rows: table.rows,
    truncated: table.truncated,
  };
}

/** 表行转 item 对象：列名 -> 单元格值。 */
export function rowItem(
  table: { columns: { name: string }[] },
  row: unknown[],
): Record<string, unknown> {
  const item: Record<string, unknown> = {};
  table.columns.forEach((column, index) => {
    item[column.name] = row[index] ?? null;
  });
  return item;
}

/** 从结果表按行下标构造行集输出表：保持列结构、行顺序与截断标记，不做其它处理。 */
export function tableRowsByIndex(
  table: AnalysisTableResult,
  rowIndexes: readonly number[],
): AnalysisTableResult {
  return {
    columns: table.columns,
    rows: rowIndexes
      .map((index) => table.rows[index])
      .filter((row): row is unknown[] => row !== undefined),
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
    const sourceNode = definition.nodes.find(
      (node) => node.id === edge.source_node_id,
    );
    if (
      sourceNode !== undefined &&
      ANALYSIS_VIEW_NODE_KINDS.has(sourceNode.kind) &&
      edge.source_port_id === "selection"
    ) {
      // selection 输出是瞬态选择，不是视图/获取单行的数据输入；
      // 未选中时不能把视图的整组输入表当成上游数据。
      continue;
    }
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

/**
 * 把区域内展示终端（config 转发、视图、获取单行）按当前表结果补齐。
 * 供整区刷新与选择分支执行共用，避免两种路径的状态收尾不一致。
 */
export function populateAnalysisTerminalResults(
  definition: WorkflowDefinition,
  regionId: string,
  results: Map<string, AnalysisNodeResult>,
): Map<string, AnalysisNodeResult> {
  for (const node of definition.nodes) {
    if (
      node.region_id !== regionId ||
      !CONFIG_NODE_KINDS.has(node.kind)
    ) {
      continue;
    }
    const table = viewInputTable(node.id, definition, results);
    results.set(
      node.id,
      table === null ? { status: "stale" } : { status: "ready", table },
    );
  }
  for (const node of definition.nodes) {
    if (
      node.region_id !== regionId ||
      !ANALYSIS_VIEW_NODE_KINDS.has(node.kind)
    ) {
      continue;
    }
    const table = viewInputTable(node.id, definition, results);
    const stageId = terminalViewStageId(definition, node.id, results);
    results.set(
      node.id,
      table === null
        ? { status: "stale" }
        : {
            status: "ready",
            table,
            ...(stageId === undefined ? {} : { stage_id: stageId }),
          },
    );
  }
  for (const node of definition.nodes) {
    if (node.region_id !== regionId || node.kind !== "single") {
      continue;
    }
    if (hasViewSelectionInput(definition, node.id)) {
      const existing = results.get(node.id);
      if (existing?.status === "ready") {
        // 点击选择后由调用方写入的选中行 item，整区刷新不能清掉。
        continue;
      }
      results.set(node.id, { status: "idle" });
      continue;
    }
    const table = viewInputTable(node.id, definition, results);
    results.set(
      node.id,
      table === null
        ? { status: "stale" }
        : table.rows.length === 0
          ? { status: "ready" }
          : { status: "ready", item: rowItem(table, table.rows[0]) },
    );
  }
  return results;
}

/** 获取单行是否由饼图/柱状图 selection 瞬态输出驱动。 */
function hasViewSelectionInput(
  definition: WorkflowDefinition,
  nodeId: string,
): boolean {
  return definition.edges.some((edge) => {
    if (edge.target_node_id !== nodeId || edge.source_port_id !== "selection") {
      return false;
    }
    const source = definition.nodes.find(
      (node) => node.id === edge.source_node_id,
    );
    return (
      source !== undefined &&
      ANALYSIS_VIEW_NODE_KINDS.has(source.kind)
    );
  });
}

/** 饼图/柱状图 selection 直接驱动的获取单行 id（不经过表算子）。 */
export function directSelectionSingleIds(
  definition: WorkflowDefinition,
  regionId: string,
  viewId: string,
): string[] {
  return definition.edges
    .filter(
      (edge) =>
        edge.source_node_id === viewId &&
        edge.source_port_id === "selection" &&
        definition.nodes.some(
          (node) =>
            node.id === edge.target_node_id &&
            node.region_id === regionId &&
            node.kind === "single",
        ),
    )
    .map((edge) => edge.target_node_id);
}

/** 把点击后后端派生的选择阶段第一行写入直接下游获取单行。 */
export function applyViewSelectionSingles(
  definition: WorkflowDefinition,
  regionId: string,
  viewId: string,
  stage: StageResponse,
  results: Map<string, AnalysisNodeResult>,
): void {
  for (const singleId of directSelectionSingleIds(
    definition,
    regionId,
    viewId,
  )) {
    const first = stage.rows[0];
    results.set(
      singleId,
      first === undefined
        ? { status: "ready" }
        : { status: "ready", item: rowItem(stage, first) },
    );
  }
}

/** 视图的阶段引用：单数据源直接取源阶段，无法推导时保留已有值。 */
function terminalViewStageId(
  definition: WorkflowDefinition,
  viewNodeId: string,
  results: Map<string, AnalysisNodeResult>,
): string | undefined {
  const stageIds: string[] = [];
  for (const edge of definition.edges) {
    if (edge.target_node_id !== viewNodeId || edge.target_port_id !== "in") {
      continue;
    }
    const sourceId = resolveStageSource(definition, edge.source_node_id);
    const stageId =
      sourceId === null ? undefined : results.get(sourceId)?.stage_id;
    if (stageId !== undefined) {
      stageIds.push(stageId);
    }
  }
  if (stageIds.length === 1) {
    return stageIds[0];
  }
  return results.get(viewNodeId)?.stage_id;
}
