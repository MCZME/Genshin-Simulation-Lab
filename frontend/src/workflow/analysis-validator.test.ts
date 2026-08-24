import { describe, expect, it } from "vitest";

import type { WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowRegion } from "./types";
import { TemplateCatalog } from "./templates";
import { validateWorkflow } from "./validator";

function catalog(): TemplateCatalog {
  const catalog = new TemplateCatalog();
  catalog.load([
    {
      template_id: "session_metrics",
      display_name: "每会话指标",
      params: [
        {
          name: "session_ids",
          type: "string[]",
          required: true,
          binding: ["session_group", "upstream_column"],
        },
        { name: "frame_min", type: "int", required: false, binding: ["static", "config"] },
      ],
      relations: [],
      output: {
        columns: [
          { name: "session_id", type: "string" },
          { name: "total_damage", type: "float" },
        ],
      },
    },
    {
      template_id: "metric_summary",
      display_name: "指标汇总",
      params: [],
      relations: [{ name: "source", columns: ["total_damage"], required: true }],
      output: { columns: [{ name: "metric", type: "string" }] },
    },
  ]);
  return catalog;
}

function analysisRegion(): WorkflowRegion {
  return {
    id: "analysis-1",
    kind: "analysis",
    name: "分析区域",
    rect: { x: 0, y: 0, width: 600, height: 400 },
  };
}

function processingNode(
  id: string,
  templateId: string,
  params: Record<string, unknown> = {},
): WorkflowNode {
  return {
    id,
    kind: "processing",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params: { template_id: templateId, values: {}, value_bindings: {}, ...params },
  };
}

function edge(
  id: string,
  sourceNodeId: string,
  sourcePortId: string,
  targetNodeId: string,
  targetPortId: string,
): WorkflowEdge {
  return { id, source_node_id: sourceNodeId, source_port_id: sourcePortId, target_node_id: targetNodeId, target_port_id: targetPortId };
}

function definition(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
  regions: WorkflowRegion[] = [analysisRegion()],
): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "分析工作流" },
    regions,
    nodes,
    edges,
    layout: {},
  };
}

const codes = (result: ReturnType<typeof validateWorkflow>) =>
  result.map((item) => item.code);

describe("分析区域校验", () => {
  it("模拟节点和数据提供节点可连入分析边界，配置节点不可", () => {
    const simulation: WorkflowNode = {
      id: "sim",
      kind: "simulation",
      region_id: null,
      position: { x: 0, y: 0 },
      params: {},
    };
    const provider: WorkflowNode = {
      id: "provider",
      kind: "data_provider",
      region_id: null,
      position: { x: 0, y: 0 },
      params: { session_ids: [] },
    };
    const configNode: WorkflowNode = {
      id: "bad",
      kind: "character",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: { slot: 1, asset: "character:barbara" },
    };

    const okResult = validateWorkflow(
      definition(
        [simulation, provider],
        [
          edge("e1", "sim", "out", "analysis-1", "in"),
          edge("e2", "provider", "out", "analysis-1", "in"),
        ],
      ),
      catalog(),
    );
    expect(codes(okResult)).not.toContain("ANALYSIS_BOUNDARY_SOURCE_INVALID");
    expect(codes(okResult)).not.toContain("ANALYSIS_NOT_IMPLEMENTED");

    const badResult = validateWorkflow(
      definition([configNode], [edge("e1", "bad", "out", "analysis-1", "in")]),
      catalog(),
    );
    expect(codes(badResult)).toContain("ANALYSIS_BOUNDARY_SOURCE_INVALID");
  });

  it("处理节点必填会话组参数未连接时报错", () => {
    const node = processingNode("p1", "session_metrics");

    const result = validateWorkflow(definition([node], []), catalog());

    expect(codes(result)).toContain("PROCESSING_PARAM_UNBOUND");
  });

  it("会话组参数已连接则通过", () => {
    const node = processingNode("p1", "session_metrics");
    const provider: WorkflowNode = {
      id: "provider",
      kind: "data_provider",
      region_id: null,
      position: { x: 0, y: 0 },
      params: { session_ids: ["a1"] },
    };
    const result = validateWorkflow(
      definition(
        [provider, node],
        [
          edge("e1", "provider", "out", "analysis-1", "in"),
          edge("e2", "analysis-1", "in", "p1", "in_session"),
        ],
      ),
      catalog(),
    );

    expect(codes(result)).not.toContain("PROCESSING_PARAM_UNBOUND");
  });

  it("静态值与查询参数配置同时提供同一参数时报冲突", () => {
    const node = processingNode("p1", "session_metrics", {
      values: { frame_min: 0 },
    });
    const config: WorkflowNode = {
      id: "qc",
      kind: "query_config",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: { rows: [{ param: "frame_min", value: 10 }] },
    };
    const provider: WorkflowNode = {
      id: "provider",
      kind: "data_provider",
      region_id: null,
      position: { x: 0, y: 0 },
      params: { session_ids: ["a1"] },
    };
    const result = validateWorkflow(
      definition(
        [provider, node, config],
        [
          edge("e1", "provider", "out", "analysis-1", "in"),
          edge("e2", "analysis-1", "in", "p1", "in_session"),
          edge("e3", "qc", "out", "p1", "in_params"),
        ],
      ),
      catalog(),
    );

    expect(codes(result)).toContain("PROCESSING_PARAM_CONFLICT");
  });

  it("值链绑定列不存在时报错", () => {
    const node = processingNode("p1", "session_metrics", {
      value_bindings: { session_ids: "missing_column" },
    });

    const result = validateWorkflow(definition([node], []), catalog());

    expect(codes(result)).toContain("PROCESSING_BINDING_COLUMN");
  });

  it("关系输入缺失时报错", () => {
    const node = processingNode("p1", "metric_summary");

    const result = validateWorkflow(definition([node], []), catalog());

    expect(codes(result)).toContain("PROCESSING_RELATION_MISSING");
  });

  it("视图缺少展示配置时报错", () => {
    const table: WorkflowNode = {
      id: "view",
      kind: "member_table",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: {},
    };

    const result = validateWorkflow(definition([table], []), catalog());

    expect(codes(result)).toContain("VIEW_CONFIG_MISSING");
  });

  it("视图多条数据入线表结构不一致时报错", () => {
    const first = processingNode("p1", "session_metrics");
    const second = processingNode("p2", "metric_summary");
    const view: WorkflowNode = {
      id: "view",
      kind: "member_table",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: {},
    };
    const config: WorkflowNode = {
      id: "cfg",
      kind: "table_config",
      region_id: "analysis-1",
      position: { x: 0, y: 0 },
      params: { condition_columns: [], data_columns: ["total_damage"] },
    };
    const result = validateWorkflow(
      definition(
        [first, second, view, config],
        [
          edge("e1", "p1", "out", "view", "in"),
          edge("e2", "p2", "out", "view", "in"),
          edge("e3", "cfg", "out", "view", "config"),
        ],
      ),
      catalog(),
    );

    expect(codes(result)).toContain("VIEW_INPUT_SHAPE_MISMATCH");
  });

  it("分析边界向非本区域节点供数时报错", () => {
    const simulation: WorkflowNode = {
      id: "sim",
      kind: "simulation",
      region_id: null,
      position: { x: 0, y: 0 },
      params: {},
    };
    const outside = processingNode("outside", "session_metrics");
    outside.region_id = null;
    const result = validateWorkflow(
      definition(
        [simulation, outside],
        [
          edge("e1", "sim", "out", "analysis-1", "in"),
          edge("e2", "analysis-1", "in", "outside", "in_session"),
        ],
      ),
      catalog(),
    );

    expect(codes(result)).toContain("ANALYSIS_BOUNDARY_TARGET_INVALID");
  });
});
