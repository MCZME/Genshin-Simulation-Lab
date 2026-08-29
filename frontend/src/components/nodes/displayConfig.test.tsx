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

    expect(screen.getByText("X 轴列（必选）")).toBeTruthy();
    expect(screen.getByText("Y 轴列（必选）")).toBeTruthy();
    expect(screen.getByText("系列列")).toBeTruthy();

    const selects = screen.getAllByRole("combobox");
    const xOptions = Array.from(selects[0]?.querySelectorAll("option") ?? []).map(
      (option) => option.value,
    );
    expect(xOptions).toEqual(["", "角色", "伤害"]);

    fireEvent.change(selects[0]!, { target: { value: "角色" } });
    expect(onChange).toHaveBeenCalledWith({ x: "角色", y: "", series: "" });
  });

  it("当前绑定列不在上游形状中时仍保留该选项", () => {
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
  });

  it("未连接视图时不提供列选项并提示", () => {
    withEnv(EMPTY_DEFINITION, new Map());
    render(<DisplayConfigEditor node={BAR_CONFIG_NODE} onChange={() => {}} />);
    expect(
      screen.getByText("连接视图并接通数据源后，这里会出现可绑定的列。"),
    ).toBeTruthy();
    const values = Array.from(
      screen.getAllByRole("combobox")[0]!.querySelectorAll("option"),
    ).map((option) => option.value);
    expect(values).toEqual([""]);
  });
});
