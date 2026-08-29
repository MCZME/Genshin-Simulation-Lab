// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { DisplayConfigEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const EMPTY_DEFINITION: WorkflowDefinition = {
  schema_version: 1,
  meta: { name: "测试" },
  regions: [],
  nodes: [],
  edges: [],
  layout: {},
};

function definitionWithView(): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [],
    nodes: [
      {
        id: "fetch-1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      {
        id: "view-1",
        kind: "bar",
        region_id: "analysis-1",
        position: { x: 200, y: 0 },
        params: {},
      },
      {
        id: "config-1",
        kind: "bar_config",
        region_id: "analysis-1",
        position: { x: 200, y: 200 },
        params: { x: "", y: "", series: "" },
      },
    ],
    edges: [
      {
        id: "e-data",
        source_node_id: "fetch-1",
        source_port_id: "out",
        target_node_id: "view-1",
        target_port_id: "in",
      },
      {
        id: "e-config",
        source_node_id: "config-1",
        source_port_id: "out",
        target_node_id: "view-1",
        target_port_id: "config",
      },
    ],
    layout: {},
  };
}

function withEnv(definition: WorkflowDefinition, shapes: Map<string, TableShape[] | null>) {
  setAnalysisEditorEnvironment({ catalog: null, definition, shapes });
}

const BAR_CONFIG_NODE: WorkflowNode = {
  id: "config-1",
  kind: "bar_config",
  region_id: "analysis-1",
  position: { x: 200, y: 200 },
  params: { x: "", y: "", series: "" },
};

describe("DisplayConfigEditor", () => {
  it("用业务语义展示角色标签并提供列下拉", () => {
    withEnv(definitionWithView(), new Map([["fetch-1", [
      { name: "角色", type: "string" },
      { name: "伤害", type: "float" },
    ]]]));
    const onChange = vi.fn();
    render(<DisplayConfigEditor node={BAR_CONFIG_NODE} onChange={onChange} />);

    expect(screen.getByText("X 轴列")).toBeTruthy();
    expect(screen.getByText("Y 轴列")).toBeTruthy();
    expect(screen.getByText("系列列")).toBeTruthy();
    expect(document.querySelectorAll(".display-config-required-label")).toHaveLength(2);
    expect(document.querySelectorAll(".display-config-optional")).toHaveLength(1);

    const selects = screen.getAllByRole("combobox");
    const xOptions = Array.from(selects[0]?.querySelectorAll("option") ?? []).map(
      (option) => option.value,
    );
    expect(xOptions).toEqual(["", "角色", "伤害"]);

    fireEvent.change(selects[0]!, { target: { value: "角色" } });
    expect(onChange).toHaveBeenCalledWith({ x: "角色", y: "", series: "" });
  });

  it("摘要行展示当前绑定，未绑定字段显示占位符", () => {
    withEnv(definitionWithView(), new Map([["fetch-1", [
      { name: "角色", type: "string" },
      { name: "伤害", type: "float" },
    ]]]));
    render(
      <DisplayConfigEditor
        node={{ ...BAR_CONFIG_NODE, params: { x: "角色", y: "伤害", series: "" } }}
        onChange={() => {}}
      />,
    );
    const summary = document.querySelector(".display-config-summary")!;
    expect(summary.querySelectorAll(".display-config-summary-item")).toHaveLength(3);
    expect(summary.textContent).toContain("X=角色");
    expect(summary.textContent).toContain("Y=伤害");
    expect(summary.textContent).toContain("系列=—");
  });

  it("必选角色未绑定时显示行内提示", () => {
    withEnv(definitionWithView(), new Map([["fetch-1", [
      { name: "角色", type: "string" },
    ]]]));
    render(<DisplayConfigEditor node={BAR_CONFIG_NODE} onChange={() => {}} />);
    expect(screen.getAllByText("必选，尚未绑定")).toHaveLength(2);
  });

  it("字段级校验错误显示为行内错误", () => {
    withEnv(definitionWithView(), new Map([["fetch-1", [
      { name: "角色", type: "string" },
    ]]]));
    render(
      <DisplayConfigEditor
        node={BAR_CONFIG_NODE}
        onChange={() => {}}
        fieldErrors={{ x: ["X 轴列绑定无效"] }}
      />,
    );
    expect(screen.getByText("X 轴列绑定无效")).toBeTruthy();
    const select = screen.getAllByRole("combobox")[0]!;
    expect(select.className).toContain("field-invalid");
  });

  it("当前绑定列不在上游形状中时仍保留该选项并标红提示", () => {
    withEnv(definitionWithView(), new Map([["fetch-1", [
      { name: "角色", type: "string" },
    ]]]));
    render(
      <DisplayConfigEditor
        node={{ ...BAR_CONFIG_NODE, params: { x: "旧列", y: "", series: "" } }}
        onChange={() => {}}
      />,
    );
    const select = screen.getAllByRole("combobox")[0]!;
    const values = Array.from(select.querySelectorAll("option")).map((option) => option.value);
    expect(values).toContain("旧列");
    expect(select).toHaveProperty("value", "旧列");
    expect(select.className).toContain("field-invalid");
    expect(screen.getByText("列不在上游表中")).toBeTruthy();
  });

  it("未连接视图时不提供列选项并提示", () => {
    withEnv(EMPTY_DEFINITION, new Map());
    render(<DisplayConfigEditor node={BAR_CONFIG_NODE} onChange={() => {}} />);
    expect(screen.getByText("连接柱状图视图后可绑定列")).toBeTruthy();
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.getAllByText("—")).toHaveLength(3);
  });

  it("已连视图但未接通数据源时提示接通上游", () => {
    withEnv(definitionWithView(), new Map());
    render(<DisplayConfigEditor node={BAR_CONFIG_NODE} onChange={() => {}} />);
    expect(screen.getByText("视图未接通数据源，接通后出现可绑定列")).toBeTruthy();
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
  });

  it("饼图配置的空态文案按节点类型定制", () => {
    withEnv(EMPTY_DEFINITION, new Map());
    render(
      <DisplayConfigEditor
        node={{ ...BAR_CONFIG_NODE, kind: "pie_config", params: { group: "", value: "", label: "" } }}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("连接饼图视图后可绑定列")).toBeTruthy();
  });
});
