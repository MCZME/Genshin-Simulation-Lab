import { describe, expect, it } from "vitest";

import type { WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowRegion } from "./types";
import { TemplateCatalog } from "./templates";
import {
  executeAnalysisRegion,
  planProcessingNodes,
  resolveBoundarySessionGroup,
  viewInputTable,
} from "./analysis_runner";
import type { AnalysisNodeResult, ExecutionRequest, TemplateResult } from "./analysis_runner";

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

function region(): WorkflowRegion {
  return { id: "analysis-1", kind: "analysis", name: "分析区域", rect: { x: 0, y: 0, width: 600, height: 400 } };
}

function node(
  id: string,
  kind: string,
  regionId: string | null,
  params: Record<string, unknown>,
): WorkflowNode {
  return { id, kind, region_id: regionId, position: { x: 0, y: 0 }, params };
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

function definition(nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "分析工作流" },
    regions: [region()],
    nodes,
    edges,
    layout: {},
  };
}

describe("resolveBoundarySessionGroup", () => {
  it("按连线顺序合并模拟节点与数据提供节点的会话", () => {
    const simulation = node("sim", "simulation", null, { last_sessions: ["s1", "s2"] });
    const provider = node("provider", "data_provider", null, { session_ids: ["h1"] });
    const definitionData = definition(
      [simulation, provider],
      [
        edge("e2", "provider", "out", "analysis-1", "in"),
        edge("e1", "sim", "out", "analysis-1", "in"),
      ],
    );

    expect(resolveBoundarySessionGroup(definitionData, "analysis-1")).toEqual(["h1", "s1", "s2"]);
  });
});

describe("planProcessingNodes", () => {
  it("返回边界可达处理节点的拓扑序，跳过未连接草稿", () => {
    const first = node("p1", "processing", "analysis-1", { template_id: "session_metrics" });
    const second = node("p2", "processing", "analysis-1", { template_id: "metric_summary" });
    const draft = node("p3", "processing", "analysis-1", { template_id: "session_metrics" });
    const provider = node("provider", "data_provider", null, { session_ids: ["s1"] });
    const definitionData = definition(
      [provider, first, second, draft],
      [
        edge("e1", "provider", "out", "analysis-1", "in"),
        edge("e2", "analysis-1", "in", "p1", "in_session"),
        edge("e3", "p1", "out", "p2", "in_relation"),
      ],
    );

    const steps = planProcessingNodes(definitionData, "analysis-1");

    expect(steps.map((step) => step.nodeId)).toEqual(["p1", "p2"]);
  });
});

describe("executeAnalysisRegion", () => {
  it("按拓扑序执行并解析参数与关系", async () => {
    const first = node("p1", "processing", "analysis-1", {
      template_id: "session_metrics",
      values: { frame_min: 5 },
      value_bindings: {},
    });
    const second = node("p2", "processing", "analysis-1", {
      template_id: "metric_summary",
      values: {},
      value_bindings: {},
    });
    const provider = node("provider", "data_provider", null, { session_ids: ["s1", "s2"] });
    const definitionData = definition(
      [provider, first, second],
      [
        edge("e1", "provider", "out", "analysis-1", "in"),
        edge("e2", "analysis-1", "in", "p1", "in_session"),
        edge("e3", "p1", "out", "p2", "in_relation"),
      ],
    );
    const requests: Array<{ templateId: string; request: ExecutionRequest }> = [];
    const execute = async (templateId: string, request: ExecutionRequest): Promise<TemplateResult> => {
      requests.push({ templateId, request });
      if (templateId === "session_metrics") {
        return {
          columns: [
            { name: "session_id", type: "string" },
            { name: "total_damage", type: "float" },
          ],
          rows: [
            ["s1", 100],
            ["s2", 200],
          ],
          truncated: false,
        };
      }
      return { columns: [{ name: "metric", type: "string" }], rows: [["total_damage"]], truncated: false };
    };

    const results = await executeAnalysisRegion(definitionData, "analysis-1", catalog(), ["s1", "s2"], execute);

    expect(requests[0].templateId).toBe("session_metrics");
    expect(requests[0].request.params).toEqual({ session_ids: ["s1", "s2"], frame_min: 5 });
    expect(requests[1].templateId).toBe("metric_summary");
    expect(requests[1].request.relations.source.columns).toEqual(["session_id", "total_damage"]);
    expect(results.get("p1")?.status).toBe("ready");
    expect(results.get("p2")?.status).toBe("ready");
  });

  it("值链把上游列值放进下游参数", async () => {
    const first = node("p1", "processing", "analysis-1", {
      template_id: "session_metrics",
      values: {},
      value_bindings: {},
    });
    const second = node("p2", "processing", "analysis-1", {
      template_id: "session_metrics",
      values: {},
      value_bindings: { session_ids: "session_id" },
    });
    const provider = node("provider", "data_provider", null, { session_ids: [] });
    const definitionData = definition(
      [provider, first, second],
      [
        edge("e1", "provider", "out", "analysis-1", "in"),
        edge("e2", "analysis-1", "in", "p1", "in_session"),
        edge("e3", "p1", "out", "p2", "in_value"),
      ],
    );
    const requests: Array<{ templateId: string; request: ExecutionRequest }> = [];
    const execute = async (templateId: string, request: ExecutionRequest): Promise<TemplateResult> => {
      requests.push({ templateId, request });
      return {
        columns: [
          { name: "session_id", type: "string" },
          { name: "total_damage", type: "float" },
        ],
        rows: [["s1", 100]],
        truncated: false,
      };
    };

    await executeAnalysisRegion(definitionData, "analysis-1", catalog(), [], execute);

    expect(requests[1].request.params.session_ids).toEqual(["s1"]);
  });
});

describe("viewInputTable", () => {
  it("拼接多条同结构入线的行", () => {
    const first = node("p1", "processing", "analysis-1", { template_id: "session_metrics" });
    const second = node("p2", "processing", "analysis-1", { template_id: "session_metrics" });
    const view = node("view", "member_table", "analysis-1", {});
    const definitionData = definition(
      [first, second, view],
      [
        edge("e1", "p1", "out", "view", "in"),
        edge("e2", "p2", "out", "view", "in"),
      ],
    );
    const results: Map<string, AnalysisNodeResult> = new Map([
      [
        "p1",
        {
          status: "ready",
          table: {
            columns: [{ name: "session_id", type: "string" }],
            rows: [["a"]],
            truncated: false,
          },
        },
      ],
      [
        "p2",
        {
          status: "ready",
          table: {
            columns: [{ name: "session_id", type: "string" }],
            rows: [["b"], ["c"]],
            truncated: false,
          },
        },
      ],
    ]);

    const table = viewInputTable("view", definitionData, results);

    expect(table?.rows).toEqual([["a"], ["b"], ["c"]]);
  });
});
