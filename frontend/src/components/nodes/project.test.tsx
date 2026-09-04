// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TableShape } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { ProjectEditor, setAnalysisEditorEnvironment } from "./analysis";

afterEach(() => {
  setAnalysisEditorEnvironment(null);
  cleanup();
});

const SHAPE: TableShape[] = [
  { name: "session_id", type: "string" },
  { name: "dps", type: "float" },
  { name: "hit_count", type: "int" },
  { name: "element", type: "string" },
];

function withUpstream() {
  const definition: WorkflowDefinition = {
    schema_version: 1,
    meta: { name: "测试" },
    regions: [],
    nodes: [
      {
        id: "upstream-1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      {
        id: "project-1",
        kind: "project",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: {},
      },
    ],
    edges: [
      {
        id: "edge-1",
        source_node_id: "upstream-1",
        source_port_id: "out",
        target_node_id: "project-1",
        target_port_id: "in",
      },
    ],
    layout: {},
  };
  setAnalysisEditorEnvironment({
    catalog: null,
    definition,
    shapes: new Map([["upstream-1", SHAPE]]),
  });
}

function projectNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "project-1",
    kind: "project",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

function Harness({
  node,
  onChange,
}: {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const [current, setCurrent] = useState(node);
  return (
    <ProjectEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("投影节点编辑器（卡片直编）", () => {
  it("卡片内直编：列下拉带类型提示，输出列名默认沿用列名", () => {
    withUpstream();
    render(
      <ProjectEditor
        node={projectNode({ columns: [{ name: "dps" }] })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("option", { name: "dps（float）" })).not.toBeNull();
    expect(screen.getByPlaceholderText("默认：dps")).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("添加列并选择后写回不带 as", () => {
    withUpstream();
    const onChange = vi.fn();
    render(<Harness node={projectNode({})} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加列" }));
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "element" },
    });

    expect(onChange).toHaveBeenLastCalledWith({ columns: [{ name: "element" }] });
  });

  it("重命名输出列写回 as", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness node={projectNode({ columns: [{ name: "dps" }] })} onChange={onChange} />,
    );
    fireEvent.change(screen.getByPlaceholderText("默认：dps"), {
      target: { value: "total_damage" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ name: "dps", as: "total_damage" }],
    });
  });

  it("输出列名支持中文并写回 as", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness node={projectNode({ columns: [{ name: "dps" }] })} onChange={onChange} />,
    );
    fireEvent.change(screen.getByPlaceholderText("默认：dps"), {
      target: { value: "总伤害" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ name: "dps", as: "总伤害" }],
    });
  });

  it("输入法组合期间不写回 as，组合结束写回最终值", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness node={projectNode({ columns: [{ name: "dps" }] })} onChange={onChange} />,
    );
    const input = screen.getByPlaceholderText("默认：dps");

    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "角" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "角色" } });
    fireEvent.compositionEnd(input);

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ name: "dps", as: "角色" }],
    });
  });

  it("输出列名是旧列默认名时切换列自动跟随", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={projectNode({ columns: [{ name: "dps", as: "dps" }] })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "element" },
    });

    expect(onChange).toHaveBeenLastCalledWith({ columns: [{ name: "element" }] });
  });

  it("自定义输出列名在切换列后保留", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={projectNode({ columns: [{ name: "dps", as: "total" }] })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "element" },
    });

    expect(onChange).toHaveBeenLastCalledWith({
      columns: [{ name: "element", as: "total" }],
    });
  });

  it("未选列时行内提示", () => {
    withUpstream();
    render(
      <ProjectEditor node={projectNode({ columns: [{}] })} onChange={vi.fn()} />,
    );
    expect(screen.getByText("第 1 列：请选择列")).not.toBeNull();
  });

  it("输出列名重复时行内提示", () => {
    withUpstream();
    render(
      <ProjectEditor
        node={projectNode({
          columns: [
            { name: "dps", as: "same" },
            { name: "element", as: "same" },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("第 2 列：输出列名重复：same")).not.toBeNull();
  });

  it("未选择任何列时提示", () => {
    withUpstream();
    render(<ProjectEditor node={projectNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("至少选择一列")).not.toBeNull();
  });

  it("移除列行", () => {
    withUpstream();
    const onChange = vi.fn();
    render(
      <Harness
        node={projectNode({
          columns: [{ name: "dps" }, { name: "element" }],
        })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "×" })[0]);

    expect(onChange).toHaveBeenLastCalledWith({ columns: [{ name: "element" }] });
  });
});
