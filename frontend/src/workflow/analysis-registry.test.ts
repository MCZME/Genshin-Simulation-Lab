import { describe, expect, it } from "vitest";

import { definitionToEditorState } from "../state/converters";
import type { WorkflowDefinition, WorkflowNode } from "./types";
import { REGION_BOUNDARY_IN_PORT } from "./types";
import { getNodeKindSpec, validateNode } from "./registry";
import {
  PARAM_BINDING_CONFIG,
  PARAM_BINDING_SESSION_GROUP,
  PARAM_BINDING_STATIC,
  PARAM_BINDING_UPSTREAM_COLUMN,
  TemplateCatalog,
  canBindSessionGroup,
} from "./templates";

describe("分析模板目录", () => {
  it("加载、查询模板声明与输出列", () => {
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
            binding: [PARAM_BINDING_SESSION_GROUP, PARAM_BINDING_UPSTREAM_COLUMN],
          },
          { name: "frame_min", type: "int", required: false, binding: [PARAM_BINDING_STATIC, PARAM_BINDING_CONFIG] },
        ],
        relations: [],
        output: { columns: [{ name: "session_id", type: "string" }] },
      },
    ]);

    expect(catalog.list().map((item) => item.template_id)).toEqual(["session_metrics"]);
    expect(catalog.outputColumns("session_metrics")).toEqual([
      { name: "session_id", type: "string" },
    ]);
    expect(catalog.paramNames("session_metrics")).toEqual(["session_ids", "frame_min"]);
    expect(catalog.get("missing")).toBeNull();
    expect(canBindSessionGroup(catalog.params("session_metrics")[0])).toBe(true);
  });
});

describe("分析节点注册表", () => {
  const kinds = [
    "data_provider",
    "processing",
    "query_config",
    "table_config",
    "timeline_config",
    "pie_config",
    "bar_config",
    "member_table",
    "timeline",
    "pie",
    "bar",
  ] as const;

  it.each(kinds)("%s 已注册且归属正确", (kind) => {
    const spec = getNodeKindSpec(kind);
    expect(spec).not.toBeNull();
    expect(spec?.displayName).toBeTruthy();
    if (kind === "data_provider") {
      expect(spec?.region).toBeNull();
    } else {
      expect(spec?.region).toBe("analysis");
    }
  });

  it("处理节点端口语言符合模型", () => {
    const spec = getNodeKindSpec("processing");
    expect(spec?.ports.inputs.map((port) => port.dataLanguage)).toEqual([
      "session_group",
      "query_param",
      "table",
      "table",
    ]);
    expect(spec?.ports.outputs).toEqual([
      expect.objectContaining({ id: "out", dataLanguage: "table" }),
    ]);
  });

  it("视图节点数据输入允许多条、配置输入限一条", () => {
    const spec = getNodeKindSpec("member_table");
    expect(spec?.ports.inputs).toEqual([
      expect.objectContaining({ id: "in", dataLanguage: "table", connectionLimit: Number.POSITIVE_INFINITY }),
      expect.objectContaining({ id: "config", dataLanguage: "table_config", connectionLimit: 1 }),
    ]);
  });

  it("处理节点缺模板时报错", () => {
    const node: WorkflowNode = {
      id: "n1",
      kind: "processing",
      region_id: "r1",
      position: { x: 0, y: 0 },
      params: { template_id: "", values: {}, value_bindings: {} },
    };
    expect(validateNode(node).some((item) => item.code === "PARAM_INVALID")).toBe(true);
  });

  it("查询参数配置节点拒绝重复参数行", () => {
    const node: WorkflowNode = {
      id: "n1",
      kind: "query_config",
      region_id: "r1",
      position: { x: 0, y: 0 },
      params: { rows: [{ param: "frame_min", value: 0 }, { param: "frame_min", value: 1 }] },
    };
    const diagnostics = validateNode(node);
    expect(diagnostics.some((item) => item.message.includes("参数重复"))).toBe(true);
  });

  it("时间轴配置缺必选角色时报错", () => {
    const node: WorkflowNode = {
      id: "n1",
      kind: "timeline_config",
      region_id: "r1",
      position: { x: 0, y: 0 },
      params: { track: "track", start: "", end: "", value: "", label: "" },
    };
    expect(validateNode(node).some((item) => item.message.includes("start"))).toBe(true);
  });
});

describe("分析节点工作流定义往返", () => {
  it("definition -> editor state 保留分析节点参数", () => {
    const definition: WorkflowDefinition = {
      schema_version: 1,
      meta: { name: "分析工作流" },
      regions: [{ id: "r1", kind: "analysis", name: "分析区域", rect: { x: 0, y: 0, width: 400, height: 300 } }],
      nodes: [
        {
          id: "n1",
          kind: "processing",
          region_id: "r1",
          position: { x: 0, y: 0 },
          params: { template_id: "session_metrics", values: {}, value_bindings: {} },
        },
      ],
      edges: [],
      layout: {},
    };

    const state = definitionToEditorState(definition);

    expect(state.definition.nodes[0].params).toEqual({
      template_id: "session_metrics",
      values: {},
      value_bindings: {},
    });
    expect(REGION_BOUNDARY_IN_PORT).toBe("in");
  });
});
