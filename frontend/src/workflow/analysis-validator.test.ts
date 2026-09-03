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

function canvasNode(
  id: string,
  kind: string,
  params: Record<string, unknown> = {},
): WorkflowNode {
  return { id, kind, region_id: null, position: { x: 0, y: 0 }, params };
}

const codes = (result: ReturnType<typeof validateWorkflow>) =>
  result.map((item) => item.code);

function fedRuns(id = "runs1"): WorkflowNode {
  return node(id, "fetch", { source: "runs" });
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

it("载荷提取列事件类型未在事件类型筛选中时报警告", () => {
  const nodes = [
    node("ev1", "fetch", {
      source: "events",
      event_types: ["DAMAGE_RESOLVED"],
      payload_columns: [
        {
          event_type: "HEALING_RESOLVED",
          path: "result.source_ref",
          name: "src",
          type: "string",
        },
      ],
    }),
  ];
  const edges = [boundaryFeed("ev1")];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("EXTRACT_EVENT_TYPE_FILTERED");
});

it("载荷提取列缺少事件类型时报 PARAM_INVALID", () => {
  const nodes = [
    node("ev1", "fetch", {
      source: "events",
      payload_columns: [
        { path: "result.final_damage", name: "damage", type: "float" },
      ],
    }),
  ];
  const edges = [boundaryFeed("ev1")];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("PARAM_INVALID");
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

it("视图直连数据且无展示配置时合法", () => {
  const nodes = [
    fedRuns(),
    node("view1", "member_table"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "view1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("VIEW_CONFIG_MISSING");
  expect(codes(result)).not.toContain("CONFIG_OUTPUT_INVALID");
});

it("表格视图 selection（单行表）可进入下游数据算子", () => {
  const nodes = [
    fedRuns(),
    node("view1", "member_table"),
    node("lim1", "limit", { count: 5 }),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "view1", "in"),
    edge("e2", "view1", "selection", "lim1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("ANALYSIS_SHAPE_INVALID");
  expect(codes(result)).not.toContain("ITEM_OUTPUT_INVALID");
});

it("饼图 selection（行集表）可进入下游数据算子", () => {
  const nodes = [
    fedRuns(),
    node("view1", "pie"),
    node("lim1", "limit", { count: 5 }),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "view1", "in"),
    edge("e2", "view1", "selection", "lim1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("ANALYSIS_SHAPE_INVALID");
  expect(codes(result)).not.toContain("ITEM_OUTPUT_INVALID");
});

it("运行记录经设置列值后可构成角色状态详情描述符", () => {
  const nodes = [
    fedRuns(),
    node("x1", "derive", {
      columns: [
        { name: "slot", type: "int", value: 1 },
        { name: "attribute_key", type: "string", value: "stat.crit_rate" },
      ],
    }),
    node("view1", "member_table"),
    node("detail1", "attribute_detail"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "x1", "in"),
    edge("e2", "x1", "out", "view1", "in"),
    edge("e3", "view1", "selection", "detail1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("ANALYSIS_SHAPE_INVALID");
  expect(codes(result)).not.toContain("DETAIL_INPUT_MISSING");
  expect(codes(result)).not.toContain("DATA_LANGUAGE_MISMATCH");
});

it("展示配置节点经数据链转发给对应视图时合法", () => {
  const nodes = [
    fedRuns(),
    node("cfg1", "table_config", { condition_columns: [], data_columns: [] }),
    node("view1", "member_table"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "cfg1", "in"),
    edge("e2", "cfg1", "out", "view1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).not.toContain("CONFIG_INPUT_INVALID");
  expect(codes(result)).not.toContain("CONFIG_OUTPUT_INVALID");
  expect(codes(result)).not.toContain("VIEW_CONFIG_CHAIN_INVALID");
});

it("展示配置节点输出连接错误视图时报 CONFIG_OUTPUT_INVALID", () => {
  const nodes = [
    fedRuns(),
    node("cfg1", "table_config", { condition_columns: [], data_columns: [] }),
    node("view1", "pie"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "cfg1", "in"),
    edge("e2", "cfg1", "out", "view1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("CONFIG_OUTPUT_INVALID");
});

it("视图多条数据入线结构不一致时报 VIEW_INPUT_SHAPE_MISMATCH", () => {
  const nodes = [
    fedRuns(),
    node("projA", "project", { columns: [{ name: "session_id" }] }),
    node("projB", "project", { columns: [{ name: "frames_run" }] }),
    node("view1", "member_table"),
  ];
  const edges = [
    boundaryFeed(),
    edge("e1", "runs1", "out", "projA", "in"),
    edge("e2", "runs1", "out", "projB", "in"),
    edge("e3", "projA", "out", "view1", "in"),
    edge("e4", "projB", "out", "view1", "in"),
  ];
  const result = validateWorkflow(definition(nodes, edges));
  expect(codes(result)).toContain("VIEW_INPUT_SHAPE_MISMATCH");
});

it("空数据提供节点连入边界时报警告", () => {
  const nodes = [canvasNode("prov1", "data_provider")];
  const edges = [edge("b1", "prov1", "out", "analysis-1", "in")];

  const result = validateWorkflow(definition(nodes, edges));

  expect(result.some((item) => item.code === "DATA_PROVIDER_EMPTY_SELECTION")).toBe(true);
});

it("边界多源合并会话数超限时报错误", () => {
  const nodes = [
    canvasNode(
      "prov1",
      "data_provider",
      { session_ids: Array.from({ length: 600 }, (_, index) => `p${index}`) },
    ),
    canvasNode(
      "sim1",
      "simulation",
      { last_sessions: Array.from({ length: 600 }, (_, index) => `s${index}`) },
    ),
  ];
  const edges = [
    edge("b1", "prov1", "out", "analysis-1", "in"),
    edge("b2", "sim1", "out", "analysis-1", "in"),
  ];

  const result = validateWorkflow(definition(nodes, edges));

  expect(result.some((item) => item.code === "BOUNDARY_SESSION_LIMIT_EXCEEDED")).toBe(true);
});

it("边界多源合并保序去重后不误报超限", () => {
  const nodes = [
    canvasNode("sim1", "simulation", { last_sessions: ["s1", "s2"] }),
    canvasNode("prov1", "data_provider", { session_ids: ["s2", "s3"] }),
  ];
  const edges = [
    edge("b1", "sim1", "out", "analysis-1", "in"),
    edge("b2", "prov1", "out", "analysis-1", "in"),
  ];

  const result = validateWorkflow(definition(nodes, edges));

  expect(result.some((item) => item.code === "BOUNDARY_SESSION_LIMIT_EXCEEDED")).toBe(false);
});
