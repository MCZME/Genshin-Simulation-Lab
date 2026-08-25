/**
 * 分析可读 schema 目录与形状推导：契约 v2 的前端真值镜像。
 *
 * 目录来自 GET /api/v1/analysis/schema（后端冻结清单的聚合转发）；
 * 形状推导规则与《分析系统契约》第 5 节一致，供校验诊断与列下拉选择器使用。
 */

import type { AnalysisSchemaResponse } from "../api/client";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";

export interface TableShape {
  name: string;
  type: string;
}

export interface FetchExtractColumn {
  path: string;
  name: string;
  type: string;
}

export interface FilterCondition {
  column: string;
  op: string;
  value?: unknown;
}

export interface AnalysisSchemaCatalog {
  load(schema: AnalysisSchemaResponse): void;
  ready(): boolean;
  runsColumns(): { name: string; type: string; description: string }[];
  eventTypes(): { name: string; fields: { path: string; type: string; description: string }[] }[];
}

export function createAnalysisSchemaCatalog(): AnalysisSchemaCatalog {
  let schema: AnalysisSchemaResponse | null = null;
  return {
    load(next) {
      schema = next;
    },
    ready() {
      return schema !== null;
    },
    runsColumns() {
      const table = schema?.tables.find((item) => item.name === "simulation_runs");
      return table ? table.columns : [];
    },
    eventTypes() {
      return schema ? schema.event_types : [];
    },
  };
}

export interface AnalysisTableColumn {
  name: string;
  type: string;
}

/** 查询计划输出结果表形状。 */
export interface AnalysisTableResult {
  columns: AnalysisTableColumn[];
  rows: unknown[][];
  truncated: boolean;
}

const RUN_BASE_COLUMNS: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "state", type: "string" },
  { name: "name", type: "string" },
  { name: "input_schema_version", type: "int" },
  { name: "created_at", type: "string" },
  { name: "started_at", type: "string" },
  { name: "finished_at", type: "string" },
  { name: "stop_reason", type: "string" },
  { name: "end_frame", type: "int" },
  { name: "frames_run", type: "int" },
  { name: "event_count", type: "int" },
  { name: "error_code", type: "string" },
  { name: "error_message", type: "string" },
  { name: "asset_version", type: "string" },
  { name: "content_version", type: "string" },
  { name: "seed", type: "string" },
];

const EVENT_BASE_COLUMNS: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "ordinal", type: "int" },
  { name: "frame", type: "int" },
  { name: "event_type", type: "string" },
];

export const AGGREGATE_FUNCTIONS = ["sum", "count", "avg", "max", "min", "stddev", "p95"] as const;

export const CONDITION_OPERATORS = [
  "eq",
  "ne",
  "not_in",
  "in",
  "gt",
  "gte",
  "lt",
  "lte",
  "is_null",
  "is_not_null",
] as const;

const TYPE_VOCABULARY = new Set(["string", "int", "float", "bool"]);
const NUMERIC_TYPES = new Set(["int", "float"]);
const COLUMN_NAME_PATTERN = /^[A-Za-z0-9_]{1,64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function literalMatches(type: string, value: unknown): boolean {
  if (type === "string") {
    return typeof value === "string";
  }
  if (type === "bool") {
    return typeof value === "boolean";
  }
  if (type === "int") {
    return typeof value === "number" && Number.isInteger(value);
  }
  if (type === "float") {
    return typeof value === "number";
  }
  return false;
}

function extractShape(raw: unknown): TableShape[] | null {
  if (raw === undefined) {
    return [];
  }
  if (!Array.isArray(raw) || raw.length > 64) {
    return null;
  }
  const output: TableShape[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    if (!isRecord(item)) {
      return null;
    }
    const path = item.path;
    const name = item.name;
    const type = item.type;
    if (
      typeof path !== "string" ||
      path === "" ||
      path.includes("'") ||
      path.startsWith(".") ||
      typeof name !== "string" ||
      !COLUMN_NAME_PATTERN.test(name) ||
      typeof type !== "string" ||
      !TYPE_VOCABULARY.has(type) ||
      seen.has(name)
    ) {
      return null;
    }
    seen.add(name);
    output.push({ name, type });
  }
  return output;
}

/** 单节点输出形状（不含上游解析；取数节点形状只依赖自身参数）。 */
export function fetchShape(node: WorkflowNode): TableShape[] | null {
  if (node.kind === "fetch_runs") {
    const extracts = extractShape(node.params.snapshot_columns);
    return extracts === null ? null : [...RUN_BASE_COLUMNS, ...extracts];
  }
  if (node.kind === "fetch_events") {
    const eventTypes = node.params.event_types;
    if (
      eventTypes !== undefined &&
      (!Array.isArray(eventTypes) || eventTypes.some((item) => typeof item !== "string"))
    ) {
      return null;
    }
    const frameMin = node.params.frame_min;
    const frameMax = node.params.frame_max;
    const validFrame = (value: unknown): boolean =>
      value === undefined || (typeof value === "number" && Number.isInteger(value));
    if (!validFrame(frameMin) || !validFrame(frameMax)) {
      return null;
    }
    if (
      typeof frameMin === "number" &&
      typeof frameMax === "number" &&
      frameMin > frameMax
    ) {
      return null;
    }
    const extracts = extractShape(node.params.payload_columns);
    return extracts === null ? null : [...EVENT_BASE_COLUMNS, ...extracts];
  }
  return null;
}

export const ANALYSIS_TABLE_NODE_KINDS = new Set([
  "fetch_runs",
  "fetch_events",
  "filter",
  "project",
  "sort",
  "aggregate",
  "limit",
  "join",
  "compute",
]);

function isAnalysisTableNode(node: WorkflowNode): boolean {
  return ANALYSIS_TABLE_NODE_KINDS.has(node.kind);
}

function aggregateShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const groupByRaw = node.params.group_by;
  const aggregatesRaw = node.params.aggregates;
  if (
    (groupByRaw !== undefined && !Array.isArray(groupByRaw)) ||
    (aggregatesRaw !== undefined && !Array.isArray(aggregatesRaw))
  ) {
    return null;
  }
  const groupBy = (groupByRaw ?? []) as string[];
  const aggregates = (aggregatesRaw ?? []) as {
    fn?: string;
    column?: string;
    as?: string;
  }[];
  if (groupBy.length === 0 && aggregates.length === 0) {
    return null;
  }
  const types = new Map(source.map((column) => [column.name, column.type]));
  const output: TableShape[] = [];
  const seen = new Set<string>();
  for (const name of groupBy) {
    const type = types.get(name);
    if (type === undefined || seen.has(name)) {
      return null;
    }
    seen.add(name);
    output.push({ name, type });
  }
  for (const item of aggregates) {
    if (!isRecord(item)) {
      return null;
    }
    const fn = item.fn;
    const column = item.column;
    if (typeof fn !== "string" || !AGGREGATE_FUNCTIONS.includes(fn as never)) {
      return null;
    }
    if (typeof column !== "string") {
      return null;
    }
    const type = types.get(column);
    if (type === undefined) {
      return null;
    }
    if (fn !== "count" && !NUMERIC_TYPES.has(type)) {
      return null;
    }
    const final = (item.as as string | undefined) ?? (fn + "_" + column);
    if (typeof final !== "string" || !COLUMN_NAME_PATTERN.test(final) || seen.has(final)) {
      return null;
    }
    seen.add(final);
    const resultType =
      fn === "avg" || fn === "stddev" || fn === "p95"
        ? "float"
        : fn === "count"
          ? "int"
          : type;
    output.push({ name: final, type: resultType });
  }
  return output;
}

function projectShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const types = new Map(source.map((column) => [column.name, column.type]));
  if (!Array.isArray(node.params.columns) || node.params.columns.length === 0) {
    return null;
  }
  const columns = node.params.columns as { name?: string; as?: string }[];
  const output: TableShape[] = [];
  const seen = new Set<string>();
  for (const item of columns) {
    if (!isRecord(item) || typeof item.name !== "string" || !types.has(item.name)) {
      return null;
    }
    const final = (item.as as string | undefined) ?? item.name;
    if (typeof final !== "string" || !COLUMN_NAME_PATTERN.test(final) || seen.has(final)) {
      return null;
    }
    seen.add(final);
    output.push({ name: final, type: types.get(item.name) as string });
  }
  return output;
}

function joinShape(node: WorkflowNode, left: TableShape[], right: TableShape[]): TableShape[] | null {
  const leftNames = new Set(left.map((column) => column.name));
  const rightTypes = new Map(right.map((column) => [column.name, column.type]));
  const mode = node.params.mode ?? "inner";
  if (
    (mode !== "inner" && mode !== "left") ||
    typeof node.params.left_key !== "string" ||
    !leftNames.has(node.params.left_key) ||
    typeof node.params.right_key !== "string" ||
    !rightTypes.has(node.params.right_key)
  ) {
    return null;
  }
  const output = [...left];
  for (const [name, type] of rightTypes) {
    if (!leftNames.has(name)) {
      output.push({ name, type });
    }
  }
  return output;
}

function computeShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const types = new Map(source.map((column) => [column.name, column.type]));
  const output = [...source];
  const taken = new Set(source.map((column) => column.name));
  if (!Array.isArray(node.params.columns) || node.params.columns.length === 0) {
    return null;
  }
  const columns = node.params.columns as { name?: string; expr?: unknown }[];
  for (const item of columns) {
    if (
      !isRecord(item) ||
      typeof item.name !== "string" ||
      !COLUMN_NAME_PATTERN.test(item.name) ||
      taken.has(item.name)
    ) {
      return null;
    }
    taken.add(item.name);
    const type = exprType(item.expr, types);
    if (type === null) {
      return null;
    }
    output.push({ name: item.name, type });
  }
  return output;
}

function exprType(
  expr: unknown,
  types: Map<string, string>,
  depth = 0,
): string | null {
  if (depth > 16 || !isRecord(expr)) {
    return null;
  }
  if ("col" in expr) {
    const name = expr.col;
    if (typeof name !== "string") {
      return null;
    }
    const type = types.get(name);
    return type !== undefined && NUMERIC_TYPES.has(type) ? type : null;
  }
  if ("lit" in expr) {
    const value = expr.lit;
    if (typeof value === "number") {
      return Number.isInteger(value) ? "int" : "float";
    }
    return null;
  }
  if (expr.op === "/") {
    const left = exprType(expr.left, types, depth + 1);
    const right = exprType(expr.right, types, depth + 1);
    return left !== null && right !== null ? "float" : null;
  }
  if (expr.op === "+" || expr.op === "-" || expr.op === "*") {
    const left = exprType(expr.left, types, depth + 1);
    const right = exprType(expr.right, types, depth + 1);
    if (left === null || right === null) {
      return null;
    }
    return left === "int" && right === "int" ? "int" : "float";
  }
  return null;
}

function filterShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const mode = node.params.mode ?? "all";
  if (mode !== "all" && mode !== "any") {
    return null;
  }
  const rawConditions = node.params.conditions;
  if (rawConditions !== undefined && !Array.isArray(rawConditions)) {
    return null;
  }
  const types = new Map(source.map((column) => [column.name, column.type]));
  for (const raw of rawConditions ?? []) {
    if (!isRecord(raw)) {
      return null;
    }
    const column = raw.column;
    const op = raw.op;
    if (typeof column !== "string" || !types.has(column)) {
      return null;
    }
    if (typeof op !== "string" || !CONDITION_OPERATORS.includes(op as never)) {
      return null;
    }
    const columnType = types.get(column) as string;
    if (
      (op === "gt" || op === "gte" || op === "lt" || op === "lte") &&
      !NUMERIC_TYPES.has(columnType)
    ) {
      return null;
    }
    if (op === "is_null" || op === "is_not_null") {
      if ("value" in raw) {
        return null;
      }
      continue;
    }
    const value = raw.value;
    if (op === "in" || op === "not_in") {
      if (
        !Array.isArray(value) ||
        value.length === 0 ||
        value.some((item) => !literalMatches(columnType, item))
      ) {
        return null;
      }
      continue;
    }
    if (!literalMatches(columnType, value)) {
      return null;
    }
  }
  return source;
}

function sortShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const keys = node.params.keys;
  if (!Array.isArray(keys) || keys.length === 0) {
    return null;
  }
  const names = new Set(source.map((column) => column.name));
  for (const raw of keys) {
    if (!isRecord(raw)) {
      return null;
    }
    const column = raw.column;
    const direction = raw.direction ?? "asc";
    if (typeof column !== "string" || !names.has(column)) {
      return null;
    }
    if (direction !== "asc" && direction !== "desc") {
      return null;
    }
  }
  return source;
}

function limitShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const count = node.params.count;
  if (
    typeof count !== "number" ||
    !Number.isInteger(count) ||
    count < 1 ||
    count > 10_000
  ) {
    return null;
  }
  return source;
}

/**
 * 全图分析表形状推导：按拓扑序求值每个取数/算子节点的输出形状。
 * 无法推导的节点形状记为 null（校验器据此报错，列选择器隐藏该下游）。
 */
export function computeAnalysisShapes(
  definition: WorkflowDefinition,
): Map<string, TableShape[] | null> {
  const nodeById = new Map(definition.nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, WorkflowEdge[]>();
  for (const edge of definition.edges) {
    const list = incoming.get(edge.target_node_id) ?? [];
    list.push(edge);
    incoming.set(edge.target_node_id, list);
  }

  const shapes = new Map<string, TableShape[] | null>();
  const visiting = new Set<string>();

  const visit = (nodeId: string): TableShape[] | null => {
    const cached = shapes.get(nodeId);
    if (cached !== undefined) {
      return cached;
    }
    if (visiting.has(nodeId)) {
      shapes.set(nodeId, null);
      return null;
    }
    const node = nodeById.get(nodeId);
    if (node === undefined || !isAnalysisTableNode(node)) {
      shapes.set(nodeId, null);
      return null;
    }
    visiting.add(nodeId);
    const edgesInto = (incoming.get(nodeId) ?? []).filter(
      (edge) => edge.source_node_id !== nodeId && nodeById.has(edge.source_node_id),
    );
    const inputShapes: (TableShape[] | null)[] = [];
    for (const upstreamId of orderInputsFor(node, edgesInto)) {
      inputShapes.push(visit(upstreamId));
    }
    visiting.delete(nodeId);

    let shape: TableShape[] | null;
    switch (node.kind) {
      case "fetch_runs":
      case "fetch_events":
        shape = fetchShape(node);
        break;
      case "filter":
        shape = inputShapes[0] ? filterShape(node, inputShapes[0]) : null;
        break;
      case "sort":
        shape = inputShapes[0] ? sortShape(node, inputShapes[0]) : null;
        break;
      case "limit":
        shape = inputShapes[0] ? limitShape(node, inputShapes[0]) : null;
        break;
      case "project":
        shape = inputShapes[0] ? projectShape(node, inputShapes[0]) : null;
        break;
      case "aggregate":
        shape = inputShapes[0] ? aggregateShape(node, inputShapes[0]) : null;
        break;
      case "compute":
        shape = inputShapes[0] ? computeShape(node, inputShapes[0]) : null;
        break;
      case "join":
        shape =
          inputShapes[0] && inputShapes[1]
            ? joinShape(node, inputShapes[0], inputShapes[1])
            : null;
        break;
      default:
        shape = null;
    }
    shapes.set(nodeId, shape);
    return shape;
  };

  for (const node of definition.nodes) {
    if (isAnalysisTableNode(node)) {
      visit(node.id);
    }
  }
  return shapes;
}

function orderInputsFor(node: WorkflowNode, edgesInto: WorkflowEdge[]): string[] {
  // 单输入算子取第一条入线；join 按端口名 left/right 对齐输入顺序。
  if (node.kind === "join") {
    const ordered = ["left", "right"].map((port) =>
      edgesInto.find((edge) => edge.target_port_id === port),
    );
    if (ordered.every((edge) => edge !== undefined)) {
      return ordered.map((edge) => (edge as WorkflowEdge).source_node_id);
    }
  }
  return edgesInto.map((edge) => edge.source_node_id).slice(0, 1);
}

/** 上游形状查询：列选择器的数据源；无法推导时返回空数组。 */
export function upstreamShape(
  shapes: Map<string, TableShape[] | null>,
  definition: WorkflowDefinition,
  nodeId: string,
): TableShape[] {
  const edge = definition.edges.find(
    (item) => item.target_node_id === nodeId && item.source_node_id !== nodeId,
  );
  if (edge === undefined) {
    return [];
  }
  return shapes.get(edge.source_node_id) ?? [];
}
