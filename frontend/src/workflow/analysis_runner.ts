/**
 * 分析区域执行：把分析子图编译为模板执行步骤，按拓扑序逐节点执行。
 *
 * 执行模型（分析区域设计 2.5）：前端按拓扑序逐节点调用模板执行端点，
 * 上游结果表随下游请求传回（关系链）；值链由前端把上游列值取出来放进 params。
 */

import { REGION_BOUNDARY_IN_PORT } from "./types";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";
import type { TemplateCatalog, TemplateParam, TemplateRelation } from "./templates";
import { canBindSessionGroup } from "./templates";

export interface TemplateColumn {
  name: string;
  type: string;
}

export interface TemplateResult {
  columns: TemplateColumn[];
  rows: unknown[][];
  truncated: boolean;
}

export interface ExecutionRequest {
  params: Record<string, unknown>;
  relations: Record<string, { columns: string[]; rows: unknown[][] }>;
}

export type ExecuteTemplate = (
  templateId: string,
  request: ExecutionRequest,
) => Promise<TemplateResult>;

export interface AnalysisExecutionStep {
  nodeId: string;
  templateId: string;
}

export interface AnalysisNodeResult {
  status: "idle" | "loading" | "ready" | "error" | "stale";
  table?: TemplateResult;
  error?: string;
}

export function createIdleResult(): AnalysisNodeResult {
  return { status: "idle" };
}

/** 解析分析区域边界输入的会话组：多源按连线顺序合并（模拟节点最近批次 + 数据提供节点所选）。 */
export function resolveBoundarySessionGroup(
  definition: WorkflowDefinition,
  regionId: string,
): string[] {
  const sessionIds: string[] = [];
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const edges = definition.edges
    .filter(
      (edge) =>
        edge.target_node_id === regionId && edge.target_port_id === REGION_BOUNDARY_IN_PORT,
    )
    .sort((left, right) => edgeOrder(definition, left.id) - edgeOrder(definition, right.id));
  for (const edge of edges) {
    const source = nodeById.get(edge.source_node_id);
    if (source?.kind === "simulation") {
      sessionIds.push(...asStringArray(source.params.last_sessions));
    } else if (source?.kind === "data_provider") {
      sessionIds.push(...asStringArray(source.params.session_ids));
    }
  }
  return sessionIds;
}

function edgeOrder(definition: WorkflowDefinition, edgeId: string): number {
  return definition.edges.findIndex((edge) => edge.id === edgeId);
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/** 分析区域内处理节点的拓扑序（仅统计从边界输入可达的节点）。 */
export function planProcessingNodes(
  definition: WorkflowDefinition,
  regionId: string,
): AnalysisExecutionStep[] {
  const regionNodeIds = new Set(
    definition.nodes
      .filter((node) => node.region_id === regionId)
      .map((node) => node.id),
  );
  const outgoing = new Map<string, WorkflowEdge[]>();
  const incoming = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    const from = outgoing.get(edge.source_node_id) ?? [];
    from.push(edge);
    outgoing.set(edge.source_node_id, from);
    const to = incoming.get(edge.target_node_id) ?? [];
    to.push(edge);
    incoming.set(edge.target_node_id, to);
  }

  const reachable = new Set<string>();
  const queue = [regionId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const edge of outgoing.get(current) ?? []) {
      if (!regionNodeIds.has(edge.target_node_id)) {
        continue;
      }
      if (!reachable.has(edge.target_node_id)) {
        reachable.add(edge.target_node_id);
        queue.push(edge.target_node_id);
      }
    }
  }

  const processing = definition.nodes.filter(
    (node) =>
      node.kind === "processing" &&
      node.region_id === regionId &&
      reachable.has(node.id),
  );
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const visited = new Set<string>();
  const order: WorkflowNode[] = [];

  const visit = (node: WorkflowNode): void => {
    if (visited.has(node.id)) {
      return;
    }
    visited.add(node.id);
    for (const edge of incoming.get(node.id) ?? []) {
      const upstream = nodeById.get(edge.source_node_id);
      if (
        upstream !== undefined &&
        upstream.kind === "processing" &&
        upstream.region_id === regionId &&
        reachable.has(upstream.id)
      ) {
        visit(upstream);
      }
    }
    order.push(node);
  };
  for (const node of processing) {
    visit(node);
  }
  return order.map((node) => ({
    nodeId: node.id,
    templateId: String(node.params.template_id ?? ""),
  }));
}

/** 顺序执行分析区域：构建请求（静态/配置/值链/关系链）并逐节点调用。 */
export async function executeAnalysisRegion(
  definition: WorkflowDefinition,
  regionId: string,
  catalog: TemplateCatalog,
  sessionGroup: string[],
  execute: ExecuteTemplate,
): Promise<Map<string, AnalysisNodeResult>> {
  const steps = planProcessingNodes(definition, regionId);
  const results = new Map<string, AnalysisNodeResult>();
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const edgesByTarget = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    const list = edgesByTarget.get(edge.target_node_id) ?? [];
    list.push(edge);
    edgesByTarget.set(edge.target_node_id, list);
  }

  for (const step of steps) {
    const template = catalog.get(step.templateId);
    if (template === null) {
      results.set(step.nodeId, { status: "error", error: `模板不存在：${step.templateId}` });
      continue;
    }
    const request = buildExecutionRequest(
      nodeById.get(step.nodeId),
      template.params,
      template.relations,
      edgesByTarget,
      nodeById,
      sessionGroup,
      results,
    );
    try {
      const table = await execute(step.templateId, request);
      results.set(step.nodeId, { status: "ready", table });
    } catch (error) {
      results.set(step.nodeId, {
        status: "error",
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return results;
}

function buildExecutionRequest(
  node: WorkflowNode | undefined,
  params: TemplateParam[],
  relations: TemplateRelation[],
  edgesByTarget: Map<string, WorkflowEdge[]>,
  nodeById: Map<string, WorkflowNode>,
  sessionGroup: string[],
  results: Map<string, AnalysisNodeResult>,
): ExecutionRequest {
  const request: ExecutionRequest = { params: {}, relations: {} };
  if (node === undefined) {
    return request;
  }
  const values = isRecord(node.params.values) ? node.params.values : {};
  const valueBindings = isRecord(node.params.value_bindings)
    ? node.params.value_bindings
    : {};
  const incoming = edgesByTarget.get(node.id) ?? [];
  const sessionEdges = incoming.filter((edge) => edge.target_port_id === "in_session");
  const paramEdges = incoming.filter((edge) => edge.target_port_id === "in_params");
  const valueEdges = incoming.filter((edge) => edge.target_port_id === "in_value");
  const relationEdges = incoming.filter((edge) => edge.target_port_id === "in_relation");

  const configRows: Array<{ param: string; value: unknown }> = [];
  for (const edge of paramEdges) {
    const source = nodeById.get(edge.source_node_id);
    if (source?.kind !== "query_config" || !Array.isArray(source.params.rows)) {
      continue;
    }
    for (const raw of source.params.rows) {
      const row = raw as { param?: unknown; value?: unknown } | null;
      if (row !== null && typeof row.param === "string" && row.param !== "") {
        configRows.push({ param: row.param, value: row.value });
      }
    }
  }

  for (const param of params) {
    if (canBindSessionGroup(param) && sessionEdges.length > 0) {
      request.params[param.name] = sessionGroup;
    } else if (Object.prototype.hasOwnProperty.call(values, param.name)) {
      request.params[param.name] = values[param.name];
    } else {
      const config = configRows.find((row) => row.param === param.name);
      if (config !== undefined) {
        request.params[param.name] = config.value;
      } else if (valueBindings[param.name] !== undefined) {
        const columnValues = resolveColumnValues(
          valueEdges,
          String(valueBindings[param.name]),
          nodeById,
          results,
        );
        if (columnValues !== null) {
          request.params[param.name] = columnValues;
        }
      }
    }
  }

  for (const [index, relation] of relations.entries()) {
    const edge = relationEdges[index];
    if (edge === undefined) {
      continue;
    }
    const table = edgeSourceResult(edge, nodeById, results);
    if (table !== null) {
      request.relations[relation.name] = {
        columns: table.columns.map((column) => column.name),
        rows: table.rows,
      };
    }
  }
  return request;
}

function resolveColumnValues(
  valueEdges: WorkflowEdge[],
  column: string,
  nodeById: Map<string, WorkflowNode>,
  results: Map<string, AnalysisNodeResult>,
): unknown[] | null {
  for (const edge of valueEdges) {
    const table = edgeSourceResult(edge, nodeById, results);
    if (table === null) {
      continue;
    }
    const index = table.columns.findIndex((item) => item.name === column);
    if (index >= 0) {
      return table.rows.map((row) => row[index]);
    }
  }
  return null;
}

function edgeSourceResult(
  edge: WorkflowEdge,
  nodeById: Map<string, WorkflowNode>,
  results: Map<string, AnalysisNodeResult>,
): TemplateResult | null {
  const source = nodeById.get(edge.source_node_id);
  if (source?.kind !== "processing") {
    return null;
  }
  return results.get(source.id)?.table ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 视图数据输入：多条同结构入线的行拼接（单表语义）。 */
export function viewInputTable(
  viewNodeId: string,
  definition: WorkflowDefinition,
  results: Map<string, AnalysisNodeResult>,
): TemplateResult | null {
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const dataEdges = definition.edges.filter(
    (edge) => edge.target_node_id === viewNodeId && edge.target_port_id === "in",
  );
  const tables: TemplateResult[] = [];
  for (const edge of dataEdges) {
    const source = nodeById.get(edge.source_node_id);
    if (source?.kind !== "processing") {
      continue;
    }
    const result = results.get(source.id);
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
