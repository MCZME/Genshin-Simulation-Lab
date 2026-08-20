export const WORKFLOW_SCHEMA_VERSION = 1;

export const MAX_BATCH_MEMBERS = 200;

/**
 * 区域边界端口是区域的一部分，不作为独立节点。
 * 配置区域只有边界输出：`out` 同时作为区域内节点链的汇入目标和连接模拟桥的输出源；
 * 分析区域只有边界输入：`in` 作为模拟桥结果的接收目标（MVP 之后实现）。
 */
export const REGION_BOUNDARY_OUT_PORT = "out";
export const REGION_BOUNDARY_IN_PORT = "in";

export type RegionKind = "configuration" | "analysis";

export const NODE_KINDS = [
  "root",
  "meta",
  "character",
  "weapon",
  "artifact",
  "target",
  "input_trace",
  "run_options",
  "enum",
  "range",
  "simulation",
] as const;

export type NodeKind = (typeof NODE_KINDS)[number];

export type PortCardinality = "single" | "group";

export type DataLanguage = "fragment" | "input_document" | "session";

export type DiagnosticSeverity = "error" | "warning" | "info";

export type EnumValueType = "asset" | "number" | "string" | "json_fragment";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WorkflowRegion {
  id: string;
  kind: RegionKind;
  name: string;
  rect: Rect;
}

export interface WorkflowNode {
  id: string;
  /** 与节点类型注册表一致；加载/校验阶段对未注册 kind 报错。 */
  kind: string;
  region_id: string | null;
  position: { x: number; y: number };
  params: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source_node_id: string;
  source_port_id: string;
  target_node_id: string;
  target_port_id: string;
}

export interface WorkflowDefinition {
  schema_version: number;
  meta: { name: string };
  regions: WorkflowRegion[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  layout: Record<string, unknown>;
}

export interface Diagnostic {
  severity: DiagnosticSeverity;
  code: string;
  message: string;
  node_id: string | null;
  edge_id: string | null;
  region_id: string | null;
  path: string | null;
}

export interface CompiledMember {
  item_id: string;
  input: Record<string, unknown>;
}

export interface CompileResult {
  ok: boolean;
  region_id: string;
  members: CompiledMember[];
  diagnostics: Diagnostic[];
}

export interface EnumValue {
  item_id: string;
  value: string | number;
  label: string | null;
}
