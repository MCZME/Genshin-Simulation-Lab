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
  /** 单元格值的显示类别：asset:* 走资产名解析，enum:* 走词表，缺省为原文。 */
  valueKind?: string;
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
  runsColumns(): { name: string; type: string; description: string; value_kind: string }[];
  eventsColumns(): { name: string; type: string; description: string; value_kind: string }[];
  eventTypes(): {
    name: string;
    fields: { path: string; type: string; description: string; value_kind: string }[];
  }[];
  snapshotTree(): AnalysisSchemaNode | null;
}

/** 输入快照结构树节点：对象 / 列表 / 标量；列表不枚举位置。 */
export interface AnalysisSchemaNode {
  key: string;
  label: string;
  kind: "object" | "list" | "scalar";
  type?: string;
  description?: string;
  value_kind?: string;
  default_name?: string;
  default_name_template?: string;
  children?: AnalysisSchemaNode[];
}

/** 树中的标量叶子：路径模板 + 标签链 + 默认列名模板。 */
export interface SnapshotLeaf {
  pathTemplate: string;
  labels: string[];
  listLabels: string[];
  defaultNameTemplate: string | null;
  type: string;
  description: string;
  valueKind?: string;
}

/** 把结构树拍平成叶子清单（列表位置用 {n} 占位，由用户输入）。 */
export function snapshotLeaves(tree: AnalysisSchemaNode | null): SnapshotLeaf[] {
  if (tree === null) {
    return [];
  }
  const leaves: SnapshotLeaf[] = [];
  const visit = (
    node: AnalysisSchemaNode,
    segments: string[],
    labels: string[],
    listLabels: string[],
    isRoot: boolean,
  ) => {
    const nextSegments =
      isRoot
        ? segments
        : node.kind === "list"
        ? [...segments, `${node.key}.{${listLabels.length}}`]
        : [...segments, node.key];
    const nextLabels = [...labels, node.label];
    const nextListLabels =
      node.kind === "list" ? [...listLabels, node.label] : listLabels;
    if (node.kind === "scalar") {
      leaves.push({
        pathTemplate: nextSegments.join("."),
        labels: nextLabels,
        listLabels: nextListLabels,
        defaultNameTemplate:
          node.default_name_template ?? node.default_name ?? null,
        type: node.type ?? "",
        description: node.description ?? "",
        valueKind: node.value_kind ?? "",
      });
      return;
    }
    for (const child of node.children ?? []) {
      visit(child, nextSegments, nextLabels, nextListLabels, false);
    }
  };
  visit(tree, [], [], [], true);
  return leaves;
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
    eventsColumns() {
      const table = schema?.tables.find((item) => item.name === "simulation_events");
      return table ? table.columns : [];
    },
    eventTypes() {
      return schema ? schema.event_types : [];
    },
    snapshotTree() {
      return schema ? schema.snapshot_tree : null;
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

export const TYPE_VOCABULARY = new Set(["string", "int", "float", "bool"]);
const NUMERIC_TYPES = new Set(["int", "float"]);
export const COLUMN_NAME_PATTERN = /^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$/;

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

function extractShape(
  raw: unknown,
  requireEventType = false,
  valueKindFor?: (item: Record<string, unknown>) => string,
): TableShape[] | null {
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
    if (requireEventType && (typeof item.event_type !== "string" || item.event_type === "")) {
      return null;
    }
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
    const valueKind = valueKindFor?.(item) ?? "";
    output.push(valueKind === "" ? { name, type } : { name, type, valueKind });
  }
  return output;
}

/** 路径模板（{0}/{1} 占位）与具体路径是否匹配。 */
function matchesPathTemplate(path: string, template: string): boolean {
  const pattern = template
    .split(".")
    .map((segment) => segment.replace(/^\{(\d+)\}$/, "[0-9]+"))
    .join("\\.");
  return new RegExp(`^${pattern}$`).test(path);
}

/** 快照提取列的 value_kind：按路径匹配结构树叶子声明。 */
function snapshotValueKind(catalog: AnalysisSchemaCatalog | null, path: string): string {
  const leaves = snapshotLeaves(catalog?.snapshotTree() ?? null);
  const leaf = leaves.find((item) => matchesPathTemplate(path, item.pathTemplate));
  return leaf?.valueKind ?? "";
}

/** 事件载荷提取列的 value_kind：按事件类型 + 路径匹配字段声明。 */
function payloadValueKind(
  catalog: AnalysisSchemaCatalog | null,
  eventType: string,
  path: string,
): string {
  const field = catalog
    ?.eventTypes()
    .find((item) => item.name === eventType)
    ?.fields.find((item) => item.path === path);
  return field?.value_kind ?? "";
}

/** 取数节点固定输出列：优先 schema 目录，未加载时降级用内置清单。 */
export function fetchBaseColumns(
  source: unknown,
  catalog: AnalysisSchemaCatalog | null,
): TableShape[] | undefined {
  if (catalog === null || !catalog.ready()) {
    return undefined;
  }
  const columns =
    source === "events" ? catalog.eventsColumns() : catalog.runsColumns();
  return columns.length === 0
    ? undefined
    : columns.map((column) => ({
        name: column.name,
        type: column.type,
        ...(column.value_kind === "" ? {} : { valueKind: column.value_kind }),
      }));
}

/** 单节点输出形状（不含上游解析；取数节点形状只依赖自身参数）。 */
export function fetchShape(
  node: WorkflowNode,
  baseColumns?: TableShape[],
  catalog?: AnalysisSchemaCatalog | null,
): TableShape[] | null {
  const source = node.params.source;
  if (source === "runs") {
    const extracts = extractShape(node.params.snapshot_columns, false, (item) => {
      const path = typeof item.path === "string" ? item.path : "";
      return snapshotValueKind(catalog ?? null, path);
    });
    return extracts === null ? null : [...(baseColumns ?? RUN_BASE_COLUMNS), ...extracts];
  }
  if (source === "events") {
    const eventTypes = node.params.event_types;
    if (
      eventTypes !== undefined &&
      (!Array.isArray(eventTypes) || eventTypes.some((item) => typeof item !== "string"))
    ) {
      return null;
    }
    const extracts = extractShape(node.params.payload_columns, true, (item) => {
      const eventType = typeof item.event_type === "string" ? item.event_type : "";
      const path = typeof item.path === "string" ? item.path : "";
      return payloadValueKind(catalog ?? null, eventType, path);
    });
    return extracts === null
      ? null
      : [...(baseColumns ?? EVENT_BASE_COLUMNS), ...extracts];
  }
  return null;
}

export const ANALYSIS_TABLE_NODE_KINDS = new Set([
  "fetch",
  "filter",
  "project",
  "sort",
  "aggregate",
  "limit",
  "single",
  "join",
  "compute",
  "derive",
]);

/** 展示视图：为选择输出提供输入形状，不进入 SQL 查询计划。 */
export const ANALYSIS_VIEW_NODE_KINDS = new Set([
  "member_table",
  "pie",
  "bar",
]);

/** 展示配置转发节点：消费 table 并原样转发给视图，不进入查询计划。 */
export const ANALYSIS_CONFIG_NODE_KINDS = new Set([
  "table_config",
  "pie_config",
  "bar_config",
]);

const CATEGORY_COLUMN_TYPES = new Set(["string", "int", "float"]);

/** 直连饼图视图的默认绑定：第一个数值列做值列，第一个合法列做分组列。 */
export function defaultPieBinding(
  columns: { name: string; type: string }[],
): { group: string; value: string; label: null } | null {
  const value = columns.find((column) => column.type === "int" || column.type === "float")?.name;
  if (value === undefined) {
    return null;
  }
  const group = columns.find(
    (column) => column.name !== value && CATEGORY_COLUMN_TYPES.has(column.type),
  )?.name;
  return group === undefined ? null : { group, value, label: null };
}

/** 直连柱状图视图的默认绑定：第一个数值列做 Y 轴，第一个合法列做 X 轴。 */
export function defaultBarBinding(
  columns: { name: string; type: string }[],
): { x: string; y: string; series: null } | null {
  const y = columns.find((column) => column.type === "int" || column.type === "float")?.name;
  if (y === undefined) {
    return null;
  }
  const x = columns.find(
    (column) => column.name !== y && CATEGORY_COLUMN_TYPES.has(column.type),
  )?.name;
  return x === undefined ? null : { x, y, series: null };
}

function isAnalysisShapeNode(
  node: WorkflowNode | undefined,
): node is WorkflowNode {
  return (
    node !== undefined &&
    (ANALYSIS_TABLE_NODE_KINDS.has(node.kind) ||
      ANALYSIS_VIEW_NODE_KINDS.has(node.kind))
  );
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
  const valueKinds = new Map(
    source.map((column) => [column.name, column.valueKind ?? ""]),
  );
  const output: TableShape[] = [];
  const seen = new Set<string>();
  for (const name of groupBy) {
    const type = types.get(name);
    if (type === undefined || seen.has(name)) {
      return null;
    }
    seen.add(name);
    const valueKind = valueKinds.get(name) ?? "";
    output.push(valueKind === "" ? { name, type } : { name, type, valueKind });
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
  const valueKinds = new Map(
    source.map((column) => [column.name, column.valueKind ?? ""]),
  );
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
    const valueKind = valueKinds.get(item.name) ?? "";
    output.push(
      valueKind === ""
        ? { name: final, type: types.get(item.name) as string }
        : { name: final, type: types.get(item.name) as string, valueKind },
    );
  }
  return output;
}

function joinShape(node: WorkflowNode, left: TableShape[], right: TableShape[]): TableShape[] | null {
  const leftNames = new Set(left.map((column) => column.name));
  const rightByKey = new Map(right.map((column) => [column.name, column]));
  const mode = node.params.mode ?? "inner";
  if (
    (mode !== "inner" && mode !== "left") ||
    typeof node.params.left_key !== "string" ||
    !leftNames.has(node.params.left_key) ||
    typeof node.params.right_key !== "string" ||
    !rightByKey.has(node.params.right_key)
  ) {
    return null;
  }
  const output = [...left];
  for (const [name, column] of rightByKey) {
    if (!leftNames.has(name)) {
      output.push(column);
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

function deriveShape(node: WorkflowNode, source: TableShape[]): TableShape[] | null {
  const output = [...source];
  const taken = new Set(source.map((column) => column.name));
  const sourceTypes = new Map(source.map((column) => [column.name, column.type]));
  const overridden = new Set<string>();
  if (!Array.isArray(node.params.columns) || node.params.columns.length === 0) {
    return null;
  }
  const columns = node.params.columns as {
    name?: unknown;
    type?: unknown;
    value?: unknown;
  }[];
  for (const item of columns) {
    if (
      !isRecord(item) ||
      typeof item.name !== "string" ||
      !COLUMN_NAME_PATTERN.test(item.name) ||
      typeof item.type !== "string" ||
      !TYPE_VOCABULARY.has(item.type) ||
      !literalMatches(item.type, item.value) ||
      (sourceTypes.has(item.name) &&
        (item.type !== sourceTypes.get(item.name) || overridden.has(item.name))) ||
      (!sourceTypes.has(item.name) && taken.has(item.name))
    ) {
      return null;
    }
    if (sourceTypes.has(item.name)) {
      overridden.add(item.name);
      continue;
    }
    taken.add(item.name);
    output.push({ name: item.name, type: item.type });
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

/** 获取单行：输出形状与输入一致；行数语义（≤1）由执行时保证。 */
function singleShape(source: TableShape[]): TableShape[] | null {
  return source;
}

/**
 * 全图分析表形状推导：按拓扑序求值每个取数/算子节点的输出形状。
 * 无法推导的节点形状记为 null（校验器据此报错，列选择器隐藏该下游）。
 */
export function computeAnalysisShapes(
  definition: WorkflowDefinition,
  catalog?: AnalysisSchemaCatalog | null,
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
    if (!isAnalysisShapeNode(node)) {
      shapes.set(nodeId, null);
      return null;
    }
    visiting.add(nodeId);
    if (ANALYSIS_VIEW_NODE_KINDS.has(node.kind)) {
      for (const edge of incoming.get(nodeId) ?? []) {
        if (edge.target_port_id !== "in") {
          continue;
        }
        const sourceId = resolveTableSource(definition, edge.source_node_id);
        const sourceNode = sourceId === null ? undefined : nodeById.get(sourceId);
        if (isAnalysisShapeNode(sourceNode)) {
          visit(sourceId as string);
        }
      }
      const shape = viewInputShape(shapes, definition, node.id);
      shapes.set(
        node.id,
        shape.length === 0 ? null : shape,
      );
      visiting.delete(node.id);
      return shape.length === 0 ? null : shape;
    }
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
      case "fetch":
        shape = fetchShape(
          node,
          fetchBaseColumns(node.params.source, catalog ?? null),
          catalog,
        );
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
      case "single":
        shape = inputShapes[0] ? singleShape(inputShapes[0]) : null;
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
      case "derive":
        shape = inputShapes[0] ? deriveShape(node, inputShapes[0]) : null;
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
    if (isAnalysisShapeNode(node)) {
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

/** 视图数据输入形状：多条同结构入线取第一条可推导的形状。 */
export function viewInputShape(
  shapes: Map<string, TableShape[] | null>,
  definition: WorkflowDefinition,
  viewNodeId: string,
): TableShape[] {
  const dataEdges = definition.edges.filter(
    (edge) => edge.target_node_id === viewNodeId && edge.target_port_id === "in",
  );
  for (const edge of dataEdges) {
    const shape = shapes.get(resolveTableSource(definition, edge.source_node_id) ?? "");
    if (shape !== undefined && shape !== null) {
      return shape;
    }
  }
  return [];
}

/** 解析表节点经展示配置转发后的实际数据源（配置节点不进入形状推导）。 */
function resolveTableSource(
  definition: WorkflowDefinition,
  nodeId: string,
): string | null {
  const seen = new Set<string>();
  let current = nodeId;
  while (!seen.has(current)) {
    seen.add(current);
    const node = definition.nodes.find((item) => item.id === current);
    if (node === undefined) {
      return null;
    }
    if (!ANALYSIS_CONFIG_NODE_KINDS.has(node.kind)) {
      return node.id;
    }
    const inputEdge = definition.edges.find(
      (item) => item.target_node_id === node.id && item.target_port_id === "in",
    );
    if (inputEdge === undefined) {
      return null;
    }
    current = inputEdge.source_node_id;
  }
  return null;
}

/** 视图的数据链配置节点：在视图 in 入线中按 kind 匹配，未连接时返回 null。 */
export function connectedConfigNode(
  definition: WorkflowDefinition,
  viewNodeId: string,
  kind: string,
): WorkflowNode | null {
  const edge = definition.edges.find(
    (item) =>
      item.target_node_id === viewNodeId &&
      item.target_port_id === "in" &&
      definition.nodes.find((node) => node.id === item.source_node_id)?.kind === kind,
  );
  if (edge === undefined) {
    return null;
  }
  const node = definition.nodes.find((item) => item.id === edge.source_node_id);
  return node !== undefined && node.kind === kind ? node : null;
}
