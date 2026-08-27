// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { computeAnalysisShapes } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { setAnalysisEditorEnvironment, TableConfigEditor } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

function definitionWith(configParams: Record<string, unknown>): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [
      {
        id: "analysis-1",
        kind: "analysis",
        name: "分析",
        rect: { x: 0, y: 0, width: 800, height: 600 },
      },
    ],
    nodes: [
      {
        id: "fetch-1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: {
          source: "runs",
          snapshot_columns: [
            { path: "team.slots.0.character.asset_key", name: "char_key", type: "string" },
            { path: "team.slots.0.weapon.asset_key", name: "weapon_key", type: "string" },
          ],
        },
      },
      {
        id: "view-1",
        kind: "member_table",
        region_id: "analysis-1",
        position: { x: 200, y: 0 },
        params: {},
      },
      {
        id: "config-1",
        kind: "table_config",
        region_id: "analysis-1",
        position: { x: 200, y: 200 },
        params: configParams,
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

function renderEditor(configParams: Record<string, unknown>, onChange = vi.fn()) {
  const definition = definitionWith(configParams);
  setAnalysisEditorEnvironment({
    catalog: null,
    definition,
    shapes: computeAnalysisShapes(definition),
  });
  const node = definition.nodes.find((item) => item.id === "config-1") as WorkflowNode;
  render(<TableConfigEditor node={node} onChange={onChange} />);
  return onChange;
}

describe("表格配置节点编辑器", () => {
  it("渲染条件列/数据列两个分区，绑定列显示在行内下拉", () => {
    renderEditor({
      condition_columns: ["weapon_key"],
      data_columns: ["frames_run"],
    });
    const conditionSelect = screen.getByLabelText("条件列第 1 行");
    expect((conditionSelect as HTMLSelectElement).value).toBe("weapon_key");
    const dataSelect = screen.getByLabelText("数据列第 1 行");
    expect((dataSelect as HTMLSelectElement).value).toBe("frames_run");
  });

  it("添加列时排除已绑定列并写入新数组", () => {
    const onChange = renderEditor({
      condition_columns: ["weapon_key"],
      data_columns: [],
    });
    const addSelect = screen.getByLabelText("添加数据列") as HTMLSelectElement;
    const options = Array.from(addSelect.options).map((option) => option.value);
    expect(options).not.toContain("weapon_key");
    fireEvent.change(addSelect, { target: { value: "frames_run" } });
    expect(onChange).toHaveBeenCalledWith({
      condition_columns: ["weapon_key"],
      data_columns: ["frames_run"],
      width_mode: "auto",
    });
  });

  it("支持上移/下移与移除", () => {
    const onChange = renderEditor({
      condition_columns: ["char_key", "weapon_key"],
      data_columns: [],
    });
    fireEvent.click(screen.getByRole("button", { name: "下移 char_key" }));
    expect(onChange).toHaveBeenLastCalledWith({
      condition_columns: ["weapon_key", "char_key"],
      data_columns: [],
      width_mode: "auto",
    });
    fireEvent.click(screen.getByRole("button", { name: "移除 weapon_key" }));
    expect(onChange).toHaveBeenLastCalledWith({
      condition_columns: ["char_key"],
      data_columns: [],
      width_mode: "auto",
    });
  });

  it("宽度模式写入表格配置参数", () => {
    const onChange = renderEditor({
      condition_columns: ["weapon_key"],
      data_columns: [],
    });
    fireEvent.change(screen.getByLabelText("宽度模式"), {
      target: { value: "fixed" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      condition_columns: ["weapon_key"],
      data_columns: [],
      width_mode: "fixed",
    });
  });

  it("未连接视图时提示无可用列", () => {
    const definition = definitionWith({ condition_columns: [], data_columns: [] });
    const disconnected = {
      ...definition,
      edges: definition.edges.filter((edge) => edge.id !== "e-config"),
    };
    setAnalysisEditorEnvironment({
      catalog: null,
      definition: disconnected,
      shapes: computeAnalysisShapes(disconnected),
    });
    const node = definition.nodes.find((item) => item.id === "config-1") as WorkflowNode;
    render(<TableConfigEditor node={node} onChange={vi.fn()} />);
    expect(screen.getByText(/连接视图并接通数据源/)).not.toBeNull();
  });
});
