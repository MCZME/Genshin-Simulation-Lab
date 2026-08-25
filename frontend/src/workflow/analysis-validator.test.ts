/** 分析区域校验（契约 v2：取数/算子/视图规则）。 */

import { expect, it } from "vitest";

import type { WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowRegion } from "./types";
import { validateWorkflow } from "./validator";

function analysisRegion(): WorkflowRegion {
  return {
    id: "analysis-1",
    kind: "analysis",
    name: "分析区域",
    rect: { x: 0, y: 0, width: 600, height: 400 },
  };
}

function node(
  id: string,
  kind: string,
  params: Record<string, unknown> = {},
): WorkflowNode {
  return { id, kind, region_id: "analysis-1", position: { x: 0, y: 0 }, params };
}

function edge(
  id: string,
  sourceNodeId: string,
  sourcePortId: string,
  targetNodeId: string,
  targetPortId: string,
): WorkflowEdge {
  return {
    id,
    source_node_id: sourceNodeId,
    source_port_id: sourcePortId,
    target_node_id: targetNodeId,
    target_port_id: targetPortId,
  };
}

function definition(nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "t" },
    regions: [analysisRegion()],
    nodes,
    edges,
    layout: {},
  };
}

const codes = (result: ReturnType<typeof validateWorkflow>) =>
  result.map((item) => item.code);

function fedRuns(id = "runs1"): WorkflowNode {
  return node(id, "fetch_runs");
}

function boundaryFeed(runsId = "runs1"): WorkflowEdge {
  return edge("b1", "analysis-1", "in", runsId, "in");
}

it("取数节点已连接边界且链路完整时无形状错误", () => {
  const nodes = [
    fedRuns(),
    node("lim1", "limit", { count: 10 }),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "lim1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("FETCH_SESSION_UNBOUND");
  expect(codes(result)).not.toContain("ANALYSIS_SHAPE_INVALID");
});

it("取数节点未连接边界时报 FETCH_SESSION_UNBOUND", () => {
  const result = validateWorkflow(definition([fedRuns()], []));
  expect(codes(result)).toContain("FETCH_SESSION_UNBOUND");
});

it("算子缺少上游表输入时报 ANALYSIS_SHAPE_INVALID", () => {
  const nodes = [
    fedRuns(),
    node("proj1", "project", { columns: [{ name: "session_id" }] }),
  ];
  const edges = [boundaryFeed()];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("ANALYSIS_SHAPE_INVALID");
});

it("未知列导致投影无法推导时报 ANALYSIS_SHAPE_INVALID", () => {
  const nodes = [
    fedRuns(),
    node("proj1", "project", { columns: [{ name: "ghost" }] }),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "proj1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("ANALYSIS_SHAPE_INVALID");
});

it("视图缺少展示配置时报 VIEW_CONFIG_MISSING", () => {
  const nodes = [
    fedRuns(),
    node("view1", "member_table"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "view1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("VIEW_CONFIG_MISSING");
});

it("视图多条数据入线结构不一致时报 VIEW_INPUT_SHAPE_MISMATCH", () => {
  const nodes = [
    fedRuns(),
    node("projA", "project", { columns: [{ name: "session_id" }] }),
    node("projB", "project", { columns: [{ name: "frames_run" }] }),
    node("view1", "member_table"),
    node("cfg1", "table_config", { condition_columns: [], data_columns: [] }),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "projA", "in"),
    edge("e2", "runs1", "out", "projB", "in"),
    edge("e3", "projA", "out", "view1", "in"),
    edge("e4", "projB", "out", "view1", "in"),
    edge("e5", "cfg1", "out", "view1", "config"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("VIEW_INPUT_SHAPE_MISMATCH");
});