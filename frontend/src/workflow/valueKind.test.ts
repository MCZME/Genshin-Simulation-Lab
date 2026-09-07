import { describe, expect, it } from "vitest";
import type { AnalysisSchemaCatalog } from "./templates";
import { computeAnalysisShapes } from "./templates";
import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";

function catalog(): AnalysisSchemaCatalog {
  return {
    load() {},
    ready: () => true,
    runsColumns: () => [
      { name: "session_id", type: "string", description: "会话 ID", value_kind: "" },
      {
        name: "state",
        type: "string",
        description: "运行状态",
        value_kind: "enum:run_state",
      },
    ],
    eventsColumns: () => [
      { name: "session_id", type: "string", description: "会话 ID", value_kind: "" },
      {
        name: "event_type",
        type: "string",
        description: "事件类型",
        value_kind: "enum:event_type",
      },
    ],
    eventTypes: () => [
      {
        name: "DAMAGE_RESOLVED",
        fields: [
          {
            path: "result.element",
            type: "string",
            description: "伤害元素",
            value_kind: "enum:element",
          },
        ],
      },
    ],
    snapshotTree: () => ({
      key: "root",
      label: "输入快照",
      kind: "object",
      children: [
        {
          key: "team",
          label: "队伍",
          kind: "list",
          children: [
            {
              key: "character",
              label: "角色",
              kind: "object",
              children: [
                {
                  key: "asset_key",
                  label: "资产",
                  kind: "scalar",
                  type: "string",
                  value_kind: "asset:characters",
                  default_name_template: "char_{0}_key",
                },
              ],
            },
          ],
        },
      ],
    }),
  };
}

function node(id: string, kind: string, params: Record<string, unknown>): WorkflowNode {
  return {
    id,
    kind,
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

function definition(nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [],
    nodes,
    edges,
    layout: {},
  };
}

function edge(
  id: string,
  sourceNodeId: string,
  targetNodeId: string,
  targetPortId = "in",
): WorkflowEdge {
  return {
    id,
    source_node_id: sourceNodeId,
    source_port_id: "out",
    target_node_id: targetNodeId,
    target_port_id: targetPortId,
  };
}

describe("value_kind 形状传播", () => {
  it("取数固定列与快照提取列继承 schema 声明的 value_kind", () => {
    const fetchNode = node("f1", "fetch", {
      source: "runs",
      snapshot_columns: [
        {
          path: "team.0.character.asset_key",
          name: "角色1",
          type: "string",
        },
      ],
    });
    const shapes = computeAnalysisShapes(definition([fetchNode], []), catalog());

    const shape = shapes.get("f1");
    expect(shape?.find((column) => column.name === "state")?.valueKind).toBe(
      "enum:run_state",
    );
    expect(shape?.find((column) => column.name === "角色1")?.valueKind).toBe(
      "asset:characters",
    );
    expect(shape?.find((column) => column.name === "session_id")?.valueKind).toBe(
      undefined,
    );
  });

  it("事件载荷提取列按事件类型与路径匹配 value_kind", () => {
    const fetchNode = node("f1", "fetch", {
      source: "events",
      payload_columns: [
        {
          event_type: "DAMAGE_RESOLVED",
          path: "result.element",
          name: "伤害元素",
          type: "string",
        },
      ],
    });
    const shapes = computeAnalysisShapes(definition([fetchNode], []), catalog());

    const shape = shapes.get("f1");
    expect(shape?.find((column) => column.name === "event_type")?.valueKind).toBe(
      "enum:event_type",
    );
    expect(shape?.find((column) => column.name === "伤害元素")?.valueKind).toBe(
      "enum:element",
    );
  });

  it("投影改名保留 value_kind，聚合分组列保留、聚合输出列不携带", () => {
    const fetchNode = node("f1", "fetch", {
      source: "runs",
      snapshot_columns: [
        {
          path: "team.0.character.asset_key",
          name: "角色1",
          type: "string",
        },
      ],
    });
    const projectNode = node("p1", "project", {
      columns: [{ name: "角色1", as: "主C" }],
    });
    const aggregateNode = node("a1", "aggregate", {
      group_by: ["主C"],
      aggregates: [{ fn: "count", column: "主C", as: "场次数" }],
    });
    const shapes = computeAnalysisShapes(
      definition(
        [fetchNode, projectNode, aggregateNode],
        [edge("e1", "f1", "p1"), edge("e2", "p1", "a1")],
      ),
      catalog(),
    );

    expect(shapes.get("p1")?.find((column) => column.name === "主C")?.valueKind).toBe(
      "asset:characters",
    );
    expect(shapes.get("a1")?.find((column) => column.name === "主C")?.valueKind).toBe(
      "asset:characters",
    );
    expect(shapes.get("a1")?.find((column) => column.name === "场次数")?.valueKind).toBe(
      undefined,
    );
  });
});
